"""The receipt (spec 10, 7 VERIFY; plan D Task 1). Pure and deterministic: no market data, no AWS, no model.

verify_numbers checks a debrief against the facts rows it cites: every number must equal the value of a cited
row (fractions x 100 for percents, ROUND_HALF_UP to the digits written, dollars to the dollar), the sentence must
name that row's entity, and its kind must be allowed. It also checks the verdict words, the failed rules, the
caveats, the four sections and any date after as_of. Values come only from `facts`, never from trace outputs or
chart arrays. Decimal everywhere; never a float comparison.

Parser rules (ledger 16): a number after a year is its own number; hyphenated quantities ("400-day") are numbers;
"percent", "per cent", "pct" mean %, "percentage points" mean pp; every minus glyph is a minus and an explicit plus
is a sign that must match the row; "$214k" and "$1.2M" are scaled; a spelled-out quantity or fraction ("ten percent",
"half") is a named defect (write the number in digits), never skipped; entity names match as whole words only.

Meaning rules (board resolution 4, spec 24; plan D Task 1b): a number is traced only when its row also agrees with the
words around it. (1) A direction word in the number's clause ("fell", "lost", "a loss of", "was down" / "rose", "gained",
"grew", "was up") must agree with the row's `sign`: "gained 10.6 %" on a falling row is a named defect, "fell to 8 %"
or "past your floor of 15 %" (a level, not a change) is not read. (2) A clause that names only today ("today", "as it
is", "your mix") must cite a today row, and one that names only the move ("the move", "after the move") a row of the
move; a ticker or shock-family row takes its side from its label, a fictional input (the amount, the move) has none.
(3) Advice and forecast words ("should", "recommend", "buy", "sell", "hold" as an instruction, "cut ... to", "will fall",
"expect", "unsuitable"...) are a named defect even when every number is traced; only the label noun in "not a
recommendation" is exempt. A clean receipt is `defects == []`, never `verified == total`: advice, a missing section or a
wrong verdict leave every number traced. scripts/receipt_mutation.py measures all three rules (docs/receipt_mutation.md)."""
import re
from bisect import bisect_left, bisect_right
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

VERDICT_WORDS = {"Compatible": "Inside your limits", "Tension": "Inside, with caveats",
                 "Incompatible": "Outside your limits", None: "Limits missing"}

SECTION_ORDER = ("data", "why", "limits", "would_change")
SECTION_TITLES = {"data": "What data?", "why": "Why this verdict?", "limits": "What limits?",
                  "would_change": "What would change the answer?"}
SECTION_KINDS = {"data": "fact", "why": "assumption", "limits": "limit", "would_change": "scenario"}

# sentence kind -> the facts-row kinds it may cite (the verdict sentence may cite any)
KIND_ALLOWED = {"fact": {"fact"}, "assumption": {"fact", "assumption"}, "limit": {"fact", "assumption"},
                "scenario": {"fact", "assumption", "fiction"}}

ENTITY_ALIASES = {"today": ["today", "as it is", "current"],
                  "after": ["the move", "after", "with the move"],
                  "your floor": ["floor", "capacity", "could absorb", "as your limit"],
                  "your amount": ["amount", "replayed on", "invested", "fictional"],
                  "one company": ["single company", "single stock"], "one sector": ["single sector"],
                  "recovery": ["recover", "recovered", "recovering"],
                  "your capacity": ["capacity", "afford", "could absorb", "can absorb", "stay above", "as your limit"],
                  "shock check": ["shock check", "shock limit", "half your floor", "turbulence"],
                  "illustration": ["illustration", "fictional mix"]}
TICKER_NAMES = {"NVDA": "nvidia", "TSLA": "tesla", "SHOP.TO": "shopify", "CNQ.TO": "canadian natural",
                "MSFT": "microsoft", "BTC-USD": "bitcoin", "XIU.TO": "xiu", "SPY": "spy", "QQQ": "qqq",
                "ESGV": "esgv", "XBB.TO": "xbb", "GLD": "gold"}
FAMILY_WORDS = {"tariffs": ["tariff"], "war_oil": ["war", "oil"], "chips": ["chip"], "rates": ["rate"]}

SECTOR_CAP = "sector_cap:"      # governance.SECTOR_CAP: one row per industry the investor limited ("sector_cap:Energy")


class _PerIndustry(dict):
    """A rule table that also answers for governance's industry rows ("sector_cap:<GICS sector>", lane sector-limits):
    the investor names the industry, so the rows cannot be listed; `make(sector)` writes the entry. `.get` and `[]` see
    them, the keys stay the listed rules."""

    def __init__(self, table, make):
        super().__init__(table)
        self._make = make

    def _sector(self, rule):
        named = isinstance(rule, str) and rule.startswith(SECTOR_CAP) and rule[len(SECTOR_CAP):].strip()
        return named if named and not super().__contains__(rule) else None

    def get(self, rule, default=None):
        sector = self._sector(rule)
        return self._make(sector) if sector else super().get(rule, default)

    def __missing__(self, rule):
        sector = self._sector(rule)
        if sector:
            return self._make(sector)
        raise KeyError(rule)


_INDUSTRY_STEM = {"information technology": "technology", "communication services": "communication",
                  "consumer discretionary": "discretionary", "consumer staples": "staples", "health care": "health"}


def _industry_words(sector: str) -> list[str]:
    """The words that name an industry limit in a debrief: its GICS name, its plain stem ("technology", "financial",
    "energy"), or the words industry, sector and excluded. People say "your technology limit" or "the energy you
    excluded", so the bare GICS name alone is too strict a test of naming the failed limit."""
    low = " ".join(sector.lower().split())
    return [low, _INDUSTRY_STEM.get(low, low.rstrip("s")), "industry", "industries", "sector", "excluded"]


RULE_WORDS = _PerIndustry({"max_drawdown": ["floor"], "scenario_stress": ["shock", "turbulence"],
                           "single_stock": ["one company", "single company", "single stock"], "sector": ["sector"],
                           "crypto": ["crypto"], "esg_direct": ["values", "excluded", "exclusion"]},
                          _industry_words)
RULE_NAMES = _PerIndustry({"max_drawdown": "Your floor", "scenario_stress": "Shock check", "single_stock": "One company",
                           "sector": "One sector", "crypto": "Crypto share", "esg_direct": "Values",
                           "esg_indirect": "Values, inside your ETFs", "risk_concentration": "Risk concentration",
                           "recovery": "Recovery time", "short_horizon": "Short horizon", "missing_data": "Missing data"},
                          lambda sector: f"Your {sector} limit")

# unit written after the number -> row units it may cite
UNIT_COMPAT = {"%": {"pct", "pp"}, "pp": {"pp", "pct"}, "$": {"CAD"}, "day": {"days"}, "month": {"months"},
               "year": {"years"}, "": {"count", "number", "days", "years"}}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}
# Names that carry digits (ledger 13): exact, case-sensitive, whole-token. Masked before number extraction, so
# "the S&P 500" is not a number, while "the S&P 500 fell 25 %" still needs a [T#] for the 25 %. Years and dates
# are not names; they follow the date rule.
NAME_TOKENS = ("S&P 500", "S&P/TSX 60", "S&P/TSX Composite", "Nasdaq-100", "Russell 2000", "COVID-19", "G7", "G20",
               "Section 232", "Section 301", "Q1", "Q2", "Q3", "Q4")


_MINUS = "−"
# Every glyph that can be a minus sign (ledger 16): U+2212, -, U+2010, U+2011, U+2012, U+2013, U+2014, U+FE63, U+FF0D.
_DASHES = "−\\-‐‑‒–—﹣－"
_PLUSES = "+＋﹢"                                            # an explicit plus is a sign too and must match the row
_PCT_UNITS = ("pct", "pp")


def _quant(value, decimals):
    """ROUND_HALF_UP to `decimals` places (ties go away from zero: -9.05 -> -9.1)."""
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def fmt_number(value, unit, decimals=None):
    """A value written the way the debrief and the defect lines write it: pct/pp = fraction x 100 ("10.6 %",
    one decimal), CAD = "$207,000" (to the dollar), days/months/years = "487 days", count/number = "4".
    The sign is kept (U+2212); pass abs(value) when the words already carry the direction."""
    v = Decimal(str(value))
    if decimals is None:
        if unit in _PCT_UNITS:
            decimals = 1
        elif unit == "CAD":
            decimals = 0
        else:
            decimals = 0 if v == v.to_integral_value() else 1
    q = _quant(v * (100 if unit in _PCT_UNITS else 1), decimals)
    body = format(abs(q), ",f")
    sign = _MINUS if q < 0 else ""
    if unit == "pct":
        return f"{sign}{body} %"
    if unit == "pp":
        return f"{sign}{body} pp"
    if unit == "CAD":
        return f"{sign}${body}"
    if unit in ("days", "months", "years"):
        return f"{sign}{body} {unit[:-1] if abs(q) == 1 else unit}"
    return f"{sign}{body}"


_TAG_RE = re.compile(r"\[(T\d+(?:\s*[,;]\s*T\d+)*)\]")
_ID_RE = re.compile(r"T\d+")
_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_P_NAME = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(NAME_TOKENS, key=len, reverse=True))
                     + r")(?!\w)")


def _merge_refs(explicit, text):
    """Cited ids: the sentence's own `refs` first, then the inline [T#] tags, each once, in order."""
    out = []
    pieces = [_ID_RE.findall(str(r)) for r in (explicit or [])]
    pieces += [_ID_RE.findall(grp) for grp in _TAG_RE.findall(text)]
    for ids in pieces:
        for t in ids:
            if t not in out:
                out.append(t)
    return out


def _item(i, sentence, default_kind, section):
    s = sentence if isinstance(sentence, dict) else {"text": sentence}
    text = str(s.get("text") or "")
    return {"i": i, "text": text, "kind": s.get("kind") or default_kind,
            "refs": _merge_refs(s.get("refs"), text), "section": section}


def _sentences(debrief):
    """The debrief as numbered items {i, text, kind, refs, section}: the verdict sentence first (number 1), then the
    sections in the order data, why, limits, would_change; sentences no section lists come last (never skipped).
    A bare list of sentence dicts has no verdict sentence and no sections (numbered from 1)."""
    if isinstance(debrief, (list, tuple)):
        return [_item(n, s, None, None) for n, s in enumerate(debrief, 1)]
    debrief = debrief or {}
    pool = list(debrief.get("sentences") or [])
    items, used = [], set()
    if debrief.get("verdict_sentence"):
        items.append(_item(1, debrief["verdict_sentence"], "verdict", "verdict"))
    sections = debrief.get("sections") or {}
    for name in SECTION_ORDER:
        val = sections.get(name)
        entries = [val] if isinstance(val, (str, dict)) or type(val) is int else list(val or [])
        for e in entries:
            if type(e) is int:
                if 0 <= e < len(pool) and e not in used:
                    used.add(e)
                    items.append(_item(len(items) + 1, pool[e], SECTION_KINDS[name], name))
            elif isinstance(e, dict):
                items.append(_item(len(items) + 1, e, SECTION_KINDS[name], name))
            elif isinstance(e, str):
                for part in filter(None, (p.strip() for p in _SPLIT_RE.split(e))):
                    items.append(_item(len(items) + 1, part, SECTION_KINDS[name], name))
    for k, s in enumerate(pool):
        if k not in used:
            items.append(_item(len(items) + 1, s, None, None))
    return items


_MON = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
        r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_MONTHS = {m: n for n, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_YEAR = r"(?:19|20)\d{2}"
_ORD = r"\d{1,2}(?:st|nd|rd|th)?"
_UNIT_AHEAD = r"\s?(?:%|pp\b|days?\b|months?\b|years?\b)"
_P_ISO = re.compile(rf"\b(?P<y>{_YEAR})[-/](?P<m>\d{{2}})[-/](?P<d>\d{{2}})\b")
_P_DMY = re.compile(rf"\b{_ORD}\s+(?P<m>{_MON})\s+(?P<y>{_YEAR})\b")
_P_MDY = re.compile(rf"\b(?P<m>{_MON})\s+{_ORD},?\s+(?P<y>{_YEAR})\b")
_P_MY = re.compile(rf"\b(?P<m>{_MON})\s+(?P<y>{_YEAR})\b")
_P_DM = re.compile(rf"\b{_ORD}\s+{_MON}(?!\w)|\b{_MON}\s+{_ORD}\b(?!{_UNIT_AHEAD})")
# A year range: 2021–2026, 2022–23. Not "2022 -15 %", "2022 -10.6 %", "2022 -25 pp": a number with its own unit or
# decimals after a year is its own number (ledger 16), and a two-digit end must climb ("2022 -15" is not 2022–2015).
_P_RANGE = re.compile(rf"\b(?P<a>{_YEAR})\s?(?P<sep>[{_DASHES}])\s?"
                      rf"(?P<b>{_YEAR}|\d{{2}}(?![.,]\d|{_UNIT_AHEAD}))\b")
_P_YEAR = re.compile(rf"(?<![\w$.,−-])(?P<y>{_YEAR})(?!\d|[.,]\d|{_UNIT_AHEAD})")


def _scan(text):
    """Blank out everything that is not a claimed number (tags, names, dates, calendar years, year ranges). A
    hyphenated quantity such as "400-day" is a number and stays. Returns (clean_text, dates): the ISO dates found;
    month- and year-level ones by their first day."""
    dates = []

    def put(y, m=1, d=1):
        try:
            dates.append(date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            pass
        return " "

    def rng(g):
        a, b = g["a"], g["b"]
        if len(b) == 2:
            if g["sep"] == "-" and 1 <= int(b) <= 12:      # 2025-04 is a month, 2022-23 a range
                return put(a, b)
            if int(b) <= int(a[2:]):                       # "2022 -15": the 15 is its own number, the year stays
                return g[0]
            b = a[:2] + b
        put(a)
        return put(b)

    text = _P_NAME.sub(" ", _TAG_RE.sub(" ", text))
    text = _P_ISO.sub(lambda g: put(g["y"], g["m"], g["d"]), text)
    for p in (_P_DMY, _P_MDY, _P_MY):
        text = p.sub(lambda g: put(g["y"], _MONTHS[g["m"][:3].lower()]), text)
    text = _P_DM.sub(" ", text)
    text = _P_RANGE.sub(rng, text)
    text = _P_YEAR.sub(lambda g: put(g["y"]), text)
    return text, dates


def _strip_ignored(text):
    return _scan(text)[0]


# A hyphenated quantity ("400-day", "12-month", "400-trading-day") is a number with a unit (ledger 16).
_SCALES = {"k": 3, "thousand": 3, "m": 6, "million": 6, "b": 9, "bn": 9, "billion": 9}   # "$214k", "$1.2M" (ledger 16)
_NUM_RE = re.compile(rf"(?P<sign>[{_PLUSES}{_DASHES}])?(?P<dollar>\$)?(?P<num>\d+(?:,\d{{3}})*(?:\.\d+)?)"
                     r"(?P<scale>(?-i:[kK]|M|B|bn)\b|\s?(?:thousand|million|billion|hundred|trillion|dozen|score)\b)?"
                     r"(?:\s?(?P<unit>%|pp\b|percentage\s+points?\b|per\s?cent\b|pct\b|days?\b|weeks?\b|months?\b|years?\b|hours?\b)"
                     r"|-(?:trading-|business-)?(?P<hunit>days?|weeks?|months?|years?|hours?|percent|pct)\b)?", re.I)
_WORD_RE = re.compile(r"\b(?P<w>" + "|".join(NUMBER_WORDS) + r")\b(?=(?:\W+\w+){0,2}?\W+"
                      r"(?:shocks?|storms?|episodes?|events?|precedents?|bets?|years?|months?|days?)\b)", re.I)
_PRONOUN_ONE = re.compile(r"\bthe\s+(?:[a-z]+\s+){0,2}(?P<one>one)\s+(?:in|of|among|from|on|at|for|with)\b", re.I)
_NEXT_UNIT_RE = re.compile(r"(?:\s+|-(?:trading-|business-)?)(?P<u>days?|months?|years?)\b", re.I)


# Spelled-out quantities (ledger 16): the receipt cannot read them, so each one is a named defect, never skipped.
# one..ten stay plain words ("one company", "no one") unless a unit follows (percent, times, dollars...); the plan's
# one..ten + shock/year/month/day nouns are read by _WORD_RE above. "half your floor" is the Shock check's own name.
_WORD = (r"(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"
         r"|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen"
         r"|seventeen|eighteen|nineteen|hundreds?|thousands?|millions?|billions?|trillions?|dozens?)")
_NOUN = (r"(?:percentage\s+points?|per\s?cent|percent|pct|pp|basis\s+points?|bps|times|dollars?|points?"
         r"|shocks?|storms?|episodes?|events?|precedents?|bets?|years?|months?|weeks?|days?|hours?)")
_P_SPELLED = re.compile(rf"\b(?:an?\s+)?(?P<body>{_WORD}(?:[-\s]+(?:and\s+)?{_WORD})*)(?:[-\s]+(?P<noun>{_NOUN}))?\b", re.I)
_FRACTIONS = "¼½¾⅐⅑⅒⅓⅔⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞"
_P_FRAC = re.compile(rf"[{_FRACTIONS}]|(?<!first\s)(?<!second\s)\bhalf\b|\bhalves\b|\b(?:an?|one|two|three|four|five"
                     r"|six|seven|eight|nine|ten)[-\s](?:thirds?(?![-\s]part)|quarters?|fourths?|fifths?|sixths?|sevenths?"
                     r"|eighths?|ninths?|tenths?)\b"
                     rf"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:in|out\s+of)\s+(?:{_WORD}|\d+)\b"
                     r"|\b(?:twice|thrice)\b|\ba\s+(?:decade|pair|couple)\b|\b(?:doubl|tripl|quadrupl)(?:ed|es|ing)\b|\bhalv(?:ed|ing)\b", re.I)
_PLAIN_RE = re.compile(r"(?:one|two|three|four|five|six|seven|eight|nine|ten)", re.I)
_UNIT_NOUN_RE = re.compile(r"(?:percentage|per\s?cent|percent|pct|pp|basis|bps|times|dollars?|weeks?|hours?)", re.I)   # not "at one point"


_HALF_FLOOR = re.compile(r"half\s+(?:of\s+)?(?:your|the)\s+floor\b", re.I)
_SHOCK = re.compile(r"\bshocks?\b", re.I)
_PCT_TAIL = re.compile(r"\s?%")
_SPELLED_SCALES = frozenset({"hundred", "trillion", "dozen", "score"})        # "2 dozen", "3 hundred": digits and a word


def _spelled(clean, digit_spans):
    """Spelled-out quantities and fractions in the cleaned sentence as [(start, end, as written)], none of them
    inside a digit expression ("1.2 million" is digits). "ten %" is one quantity. "half your floor" is the shock
    check's own name, so it passes only beside the word "shock" (ledger 20). Also returns `taken`, a byte per
    character of `clean`, 1 where a digit expression or a spelled-out quantity sits."""
    out, taken = [], bytearray(len(clean))
    for s, e in digit_spans:
        taken[s:e] = b"\x01" * (e - s)

    def free(m):
        i = m.start() - 1
        while i >= 0 and clean[i].isspace():
            i -= 1
        return not (i >= 0 and clean[i].isdigit()) and not any(taken[m.start():m.end()])   # "5 million" is digits

    def take(start, end):
        out.append((start, end, clean[start:end]))
        taken[start:end] = b"\x01" * (end - start)

    for m in _P_FRAC.finditer(clean):
        if not free(m):
            continue
        if m[0].lower() == "half" and _HALF_FLOOR.match(clean, m.start()) and _SHOCK.search(clean, max(0, m.start() - 48), m.start() + 64):
            continue
        take(m.start(), m.end())
    for m in _P_SPELLED.finditer(clean):
        tail = _PCT_TAIL.match(clean, m.end())
        if free(m) and (tail or not (_PLAIN_RE.fullmatch(m["body"]) and not _UNIT_NOUN_RE.match(m["noun"] or ""))):
            take(m.start(), tail.end() if tail else m.end())
    return out, taken


_UNIT_WORDS = {"percent": "%", "per cent": "%", "pct": "%", "percentage point": "pp"}


def _unit_name(written):
    """The unit as the parser names it: "%", "pp", "day", "month", "year" ("percent", "per cent", "pct" mean %,
    "percentage points" means pp; ledger 16), or "" when none was written."""
    u = re.sub(r"\s+", " ", written.lower()).rstrip("s")
    return _UNIT_WORDS.get(u, u)


def _numbers_pos(text):
    """(clean, found): the cleaned sentence and every number it claims as (start, end, (raw, value, decimals, unit,
    sign)), in text order, positions in `clean`. Nothing is skipped: "34,5 %" is two numbers (34 and 5 %). unit is
    "%", "pp", "$", "day", "month", "year", "week", "hour", "" or "words" (a spelled-out quantity or fraction, which
    no row can match: it gets its own defect line)."""
    clean = _strip_ignored(text)
    found, spans = [], []
    for m in _NUM_RE.finditer(clean):
        spans.append(m.span())
        if m["scale"] and m["scale"].strip().lower() in _SPELLED_SCALES:                  # "2 dozen": a scale it cannot read
            found.append((m.start(), m.end(), (m.group(0).strip(), Decimal(0), 0, "words", "")))
            continue
        num = m["num"]
        unit = "$" if m["dollar"] else _unit_name(m["unit"] or m["hunit"] or "")
        sign = ("+" if m["sign"] in tuple(_PLUSES) else "-") if m["sign"] else ""
        before = clean[m.start("sign") - 1] if m["sign"] and m.start("sign") > 0 else ""
        if before.isalnum() or before == "%":
            sign = ""                                      # "15-20 %", "9 %-12 %", "fell-10 %", "A+5 %": a range or an aside
        decimals = len(num.split(".")[1]) if "." in num else 0
        exp = _SCALES[m["scale"].strip().lower()] if m["scale"] else 0     # "$1.2M" = 1,200,000 to the 0.1 M written
        raw = m.group(0).strip()
        found.append((m.start(), m.end(), (raw if sign or not m["sign"] else raw[1:],
                                           Decimal(num.replace(",", "")).scaleb(exp), decimals - exp, unit, sign)))
    spelled, taken = _spelled(clean, spans)
    for start, end, raw in spelled:                        # unit "words" matches no row: always unverified
        found.append((start, end, (raw, Decimal(0), 0, "words", "")))
    pronouns = {p.start("one") for p in _PRONOUN_ONE.finditer(clean)}
    for m in _WORD_RE.finditer(clean):
        if taken[m.start()] or m.start() in pronouns:
            continue
        nxt = _NEXT_UNIT_RE.match(clean, m.end())
        unit = nxt["u"].lower().rstrip("s") if nxt else ""
        found.append((m.start(), m.end(), (m["w"], Decimal(NUMBER_WORDS[m["w"].lower()]), 0, unit, "")))
    return clean, sorted(found, key=lambda p: p[0])


def _numbers(text):
    """Every number a sentence claims, in text order, as (raw, value, decimals, unit, sign)."""
    return [t for _, _, t in _numbers_pos(text)[1]]


def _dates(text):
    """ISO dates a sentence mentions; a month or a year alone counts as its first day."""
    return _scan(text)[1]


def _dehyphen(s):
    """A hyphen between two letters reads as a space in an entity name: "one-company limit", "single-company"."""
    return re.sub(r"(?<=[a-z])[-‐‑](?=[a-z])", " ", s)


def _names_entity(text, entity):
    """Does the sentence name the row's entity? Case-insensitive, whole words only (a plural s is fine): the entity
    itself, an alias (today, the move, floor...), a ticker, the ticker without .TO/-USD or its company name, or a
    shock family word (tariff, war, oil, chip, rate). "history" is not RY.TO, "thereafter" is not "after", and a
    one-letter ticker (T) is never matched as a bare letter."""
    t, e = _dehyphen(re.sub(r"\s+", " ", str(text).lower())), str(entity or "").strip()
    if not e:
        return True
    key = e.lower()
    words = [key]
    if key in ENTITY_ALIASES:
        words += ENTITY_ALIASES[key]
    if key in FAMILY_WORDS:
        words += FAMILY_WORDS[key]
    if key not in ENTITY_ALIASES and _side_of_entity(e):      # "portfolio after", "your mix today"
        words += ENTITY_ALIASES[_side_of_entity(e)]
    if e.upper() in TICKER_NAMES or re.fullmatch(r"[A-Z0-9]{1,6}(?:[.-][A-Z]{1,3})?", e):
        words += [re.sub(r"(?:\.TO|-USD)$", "", e, flags=re.I).lower(), TICKER_NAMES.get(e.upper(), "")]
    return any(len(w) > 1 and re.search(rf"(?<![a-z0-9]){re.escape(_dehyphen(w))}(?:s|es)?(?![a-z0-9])", t)
               for w in words)


# ---- meaning (board resolution 4, spec 24; plan D Task 1b): direction words and today-vs-after sides ----------------
# A clause is the text between breaks (comma, semicolon, colon, brackets, a spaced dash, and, or, but, while, against...).
_BREAK = re.compile(r"(?<!\d),|,(?!\d)|[;:()\[\]]|\s[—–‒-]\s|\s(?:and|or|but|while|whereas|against|versus|vs|because|so|yet"
                    r"|although|though|which|where|then)\s", re.I)
_V_UP = frozenset("rose risen rises rising gained gains gaining grew grows growing climbed climbs jumped jumps surged "
                  "surges rallied advanced increased increases increasing appreciated earned".split())
_V_DOWN = frozenset("fell fallen falls falling lost loses lose losing dropped drops dropping declined declines declining "
                    "decreased decreases decreasing slid slides sank sinks shrank shrunk plunged tumbled slumped dipped "
                    "sagged".split())
_N_UP = frozenset("rise gain increase jump surge rally".split())                    # a noun or a bare verb: needs "of" / "by"
_N_DOWN = frozenset("fall loss losses drop decline decrease slide plunge slump".split())
_LEVEL_WORDS = frozenset("to from below above past beyond toward towards near within into onto".split())   # "fell to 8 %"
_QUALIFIERS = frozenset("by about around roughly nearly almost approximately some as much little just only at most least "
                        "over under more less than a an the full whole".split())
_AFTER_NUMBER = re.compile(r"\s*(?:(?P<up>rises?|gains?|increases?|jumps?|surges?|rallies|up)|(?P<down>falls?|loss(?:es)?"
                           r"|drops?|declines?|decreases?|slides?|plunges?|slumps?|down))\b", re.I)
_TODAY = re.compile(r"(?<![a-z0-9])(?:today|as it is|as it stands|currently|current|right now)(?:'s|’s)?(?![a-z0-9])")
_YOUR_MIX = re.compile(r"(?<![a-z0-9])your mix(?![a-z0-9])")
_THE_MOVE = re.compile(r"(?<![a-z0-9])(?:the move|your change)(?:'s|’s)?(?![a-z0-9])")
_AFTER_WORD = re.compile(r"(?<![a-z0-9])after(?![a-z0-9])")


def _side_of_entity(entity):
    """'today' or 'after' when the row's entity is one of the two sides ("today", "portfolio after", "with the move")."""
    low = str(entity or "").lower()
    today = re.search(r"(?<![a-z0-9])(?:today|as it is|current)(?![a-z0-9])", low)
    after = re.search(r"(?<![a-z0-9])(?:after|the move)(?![a-z0-9])", low)
    return "today" if today and not after else "after" if after and not today else None


def _side_of_row(row):
    """The row's side: its entity ("today", "after") or, for a ticker or a shock family, the side its label says
    ("Worst clean tariff shock after the move"). A fictional input (the amount, "The move: NVDA set to") is what the
    investor asked about, not a measure of either side: its label is not read, so "Today you are asking about 40 % [T4]
    in NVIDIA." is not a wrong side."""
    side = _side_of_entity(row.get("entity"))
    return side if side or row.get("kind") == "fiction" else _side_of_entity(row.get("label"))


def _side(text):
    """'today', 'after' or None: which side of the replay a clause is about. Only one side counts: a clause that names
    both, or neither, is not second-guessed. "your mix" is today only when nothing in the clause says "after"."""
    low = text.lower()
    today, after = bool(_TODAY.search(low)), bool(_THE_MOVE.search(low))
    if not today and not after and _YOUR_MIX.search(low) and not _AFTER_WORD.search(low):
        today = True
    return "today" if today and not after else "after" if after and not today else None


def _direction(before, after):
    """'up', 'down' or None: the word that says which way the number moved. `before` is the clause text between the
    previous number (or the clause start) and this one, `after` the text up to the next number or the clause end.
    "fell 10.6 %", "lost $207,000", "a loss of $207,000", "was up 25.2 %", "a 34.5 % drop" give a direction;
    "fell to 8 %", "fell below 15 %", "up to 9 %", "the worst drop was 40 %" do not (a level, not a change)."""
    toks = re.findall(r"[a-z]+(?:['’][a-z]+)?", before.lower())
    for k in range(len(toks) - 1, -1, -1):
        w, fill = toks[k], len(toks) - 1 - k
        if w in _LEVEL_WORDS or (w == "at" and toks[k + 1:k + 2] not in (["most"], ["least"])):
            return None
        if w in _V_UP or w in _V_DOWN:
            return None if fill > 3 else "up" if w in _V_UP else "down"
        if w in ("up", "down"):
            return ("up" if w == "up" else "down") if all(t in _QUALIFIERS for t in toks[k + 1:]) else None
        if w in _N_UP or w in _N_DOWN:
            if fill == 0 or (toks[k + 1:k + 2] in (["of"], ["by"]) and fill <= 3):
                return "up" if w in _N_UP else "down"
            return None
        if fill >= 4:
            return None
    m = _AFTER_NUMBER.match(after)
    return None if not m else "up" if m["up"] else "down"


def _row_sign(row):
    """'negative', 'positive' or 'zero': the row's `sign` (ledger 15), else the sign of its value."""
    sign = str(row.get("sign") or "").lower()
    if sign in ("negative", "positive", "zero"):
        return sign
    try:
        v = Decimal(str(row["value"]))
    except (KeyError, ArithmeticError):
        return None
    return "negative" if v < 0 else "positive" if v > 0 else "zero"


_WINDOW = (200, 120)        # characters of a clause read before and after a number: "beside" is not "anywhere in the text"


def _contexts(clean, found):
    """What the clause around each number says about it, one {'dir': up | down | None, 'side': today | after | None}
    per number of `found` (see _numbers_pos). A short opening phrase without digits ("After the move, ...", "Today,
    ...") belongs to the clause that follows its comma. Linear in the length of the sentence."""
    breaks = list(_BREAK.finditer(clean))
    starts, ends = [b.start() for b in breaks], [b.end() for b in breaks]
    head = breaks[0].start() if breaks and breaks[0].group(0) == "," else 0
    opening = bool(head) and len(clean[:head].split()) <= 6 and not re.search(r"\d", clean[:head])
    out = []
    for k, (start, end, _) in enumerate(found):
        a, b = bisect_right(ends, start) - 1, bisect_left(starts, end)       # the break before and the break after
        lo = 0 if (a == 0 and opening) or a < 0 else ends[a]
        hi = starts[b] if b < len(breaks) else len(clean)
        lo, hi = max(lo, start - _WINDOW[0]), min(hi, end + _WINDOW[1])
        prev_end = found[k - 1][1] if k else 0
        next_start = found[k + 1][0] if k + 1 < len(found) else len(clean)
        out.append({"dir": _direction(clean[max(lo, prev_end):start], clean[end:min(hi, next_start)]),
                    "side": _side(clean[lo:hi])})
    return out


def _holds(row, number):
    """Does this facts row carry the number as written? Compatible unit, value equal to the digits written
    (ROUND_HALF_UP; dollars to the dollar), and an explicit sign only on a value of that sign."""
    _, value, decimals, unit, sign = number
    try:
        if row.get("unit") not in UNIT_COMPAT.get(unit, ()):
            return False
        rv = Decimal(str(row["value"]))
        scale = 100 if row["unit"] in _PCT_UNITS else 1
        if _quant(abs(rv) * scale, decimals) != value:
            return False
    except (KeyError, ArithmeticError, AttributeError):
        return False
    return not (sign == "-" and rv >= 0) and not (sign == "+" and rv < 0)


def _kind_ok(sentence_kind, row_kind):
    allowed = KIND_ALLOWED.get(sentence_kind)
    return allowed is None or row_kind is None or row_kind in allowed     # verdict / unmarked sentences: any row


_STAGES = ("wrong_entity", "wrong_kind", "wrong_side", "wrong_direction")      # the furthest stage a candidate got to


def _bad_direction(direction, row):
    """Does a direction word contradict the row? Only money and percent rows move; days, counts and years do not."""
    if direction is None or row.get("unit") not in ("pct", "pp", "CAD"):
        return False
    sign = _row_sign(row)
    return sign == "zero" or (direction == "up" and sign == "negative") or (direction == "down" and sign == "positive")


def _only_side(row, facts):
    """A "today" row in a run with no move: no facts row is about the portfolio after the move, so "the crypto
    share" can only be today's and the side word adds nothing (ledger: entity today replaces after when there is
    no change). In a run with a move the side must be named, as before."""
    return (str(row.get("entity") or "").strip().lower() == "today"
            and not any(str(r.get("entity") or "").strip().lower() == "after" for r in facts.values() if isinstance(r, dict)))


def _check_number(number, item, facts, ctx=None):
    """(status, ref) for one claimed number: ok | wrong_entity | wrong_kind | wrong_side | wrong_direction | unverified.
    Only cited rows count; a number is traced only when its row also agrees with the clause on the side (today or after
    the move) and on the direction word (ctx = {"dir", "side"} from `_contexts`)."""
    cands = [r for r in item["refs"] if r in facts and _holds(facts[r], number)]
    if not cands:
        return "unverified", None
    ctx, bad = ctx or {}, {}
    for r in cands:
        row = facts[r]
        if not (_names_entity(item["text"], row.get("entity")) or _only_side(row, facts)):
            stage = "wrong_entity"
        elif not _kind_ok(item.get("kind"), row.get("kind")):
            stage = "wrong_kind"
        elif ctx.get("side") and _side_of_row(row) not in (None, ctx["side"]):
            stage = "wrong_side"
        elif _bad_direction(ctx.get("dir"), row):
            stage = "wrong_direction"
        else:
            return "ok", r
        bad.setdefault(stage, r)
    status = max(bad, key=_STAGES.index)
    return status, bad[status]


MIN_SHOCK_EPISODES = 2         # governance.MIN_SHOCK_EPISODES: fewer clean episodes than this cannot conclude


def _plain_text(text):
    """Lower case, no [T#] tags, one space between words (any space glyph): how a caveat phrase is looked for."""
    return " ".join(re.sub(_TAG_RE.pattern, " ", str(text), flags=re.I).lower().split())


def _shock_caveat(c):
    """The shock check's caveat in governance's own words (B Task 5, ledger 30), from the row's own fields: no value ->
    "no close precedent at this date"; fewer than 2 clean episodes -> "too few separate episodes to conclude"; else
    (beyond its threshold, a warn shown as Caution) the soft line with its count, "(Indicative)" when mixed episodes
    count. `n_episodes`, `family` and `evidence` are the analysis's counts that the pipeline copies onto the row."""
    n, value = c.get("n_episodes"), c.get("value")
    if value is None:
        return "no close precedent at this date"
    if isinstance(n, int) and not isinstance(n, bool) and n < MIN_SHOCK_EPISODES:
        return "too few separate episodes to conclude"
    family = str(c.get("family") or "shock").lower()
    which = f"in the {n} separate earlier" if isinstance(n, int) and n else "in the separate earlier"
    tag = " (Indicative)" if str(c.get("evidence") or "").startswith("Indicative") else ""   # mixed episodes counted
    return f"{which} {family} episodes, this mix lost up to {fmt_number(abs(Decimal(str(value))), 'pct')}{tag}"


def caveat_phrases(checks) -> list:
    """The caveat phrases a debrief must say, each once, in row order: the shock check's (see `_shock_caveat`) and
    "missing data". The pipeline gives the same list to the explainer (context `caveats`)."""
    out = []
    for c in checks or []:
        if c.get("status") != "warn":
            continue
        phrase = (_shock_caveat(c) if c.get("rule") == "scenario_stress"
                  else "missing data" if c.get("rule") == "missing_data" else None)
        if phrase and phrase not in out:
            out.append(phrase)
    return out


def _global_defects(items, result):
    """The debrief-wide findings, one plain sentence each: the verdict words, every failed limit named, every
    applicable caveat said, the four sections present."""
    out, low = [], " ".join(i["text"] for i in items).lower()
    result = result or {}
    if "verdict" in result and VERDICT_WORDS.get(result["verdict"]):
        want = VERDICT_WORDS[result["verdict"]]
        vs = next((i["text"].lower() for i in items if i["kind"] == "verdict"), "")
        if want.lower() not in vs or any(w.lower() in vs for w in VERDICT_WORDS.values() if w != want):
            out.append(f"The verdict must read “{want}”. Use exactly these words.")
    checks = result.get("checks") or []
    for rule in dict.fromkeys(c.get("rule") for c in checks if c.get("status") == "fail"):
        words = RULE_WORDS.get(rule) or (RULE_WORDS["esg_direct"] if rule == "esg_indirect" else
                                         [RULE_NAMES.get(rule, "").lower(), str(rule).replace("_", " ")])
        if not any(w and (w in low or w in _dehyphen(low)) for w in words):      # "the one-company limit" names it
            out.append(f"The debrief does not name the failed limit “{RULE_NAMES.get(rule, rule)}”. Name it.")
    said = _plain_text(low)
    for phrase in caveat_phrases(checks):
        line = f"The debrief must say “{phrase}”."
        if _plain_text(phrase) not in said and line not in out:
            out.append(line)
    present = {i["section"] for i in items if i["text"].strip()}
    out += [f"The section “{SECTION_TITLES[n]}” is missing. Write one sentence for it."
            for n in SECTION_ORDER if n not in present]
    return out


def _shown(row):
    """A row's value the way the debrief would write it (absolute value), for the defect lines."""
    try:
        return fmt_number(abs(Decimal(str(row["value"]))), row.get("unit"))
    except (KeyError, ArithmeticError, TypeError):
        return "not a number"


def _number_line(i, raw, status, ref, item, facts, ctx=None):
    """The defect line for one claimed number ("" when another line already says it)."""
    row, ctx = facts.get(ref) or {}, ctx or {}
    if status == "wrong_side":
        if ctx.get("side") == "today":
            return (f"Sentence {i} is about today but [{ref}] is about the portfolio after the move. "
                    "Say it is after the move, or cite today's row.")
        return (f"Sentence {i} is about the portfolio after the move but [{ref}] is about today. "
                "Say it is today, or cite the row for after the move.")
    if status == "wrong_direction":
        said, moved = ("rose", "fell") if ctx.get("dir") == "up" else ("fell", "rose")
        if _row_sign(row) == "zero":
            return (f"Sentence {i} says the value {said} but [{ref}] did not move. "
                    f"Remove the direction word, or cite the row that {said}.")
        return f"Sentence {i} says the value {said} but [{ref}] {moved}. Write that it {moved}, or cite the row that {said}."
    if status == "wrong_entity":
        return f"Sentence {i} cites {ref} for {raw} but does not name {row.get('entity')}. Name it or remove the number."
    if status == "wrong_kind":
        kind = row.get("kind")
        return (f"Sentence {i} is marked {item.get('kind')} but cites {ref}, which is "
                f"{'an' if str(kind)[:1] in 'aeiou' else 'a'} {kind}. Change the sentence's kind or its citation.")
    known = [r for r in item["refs"] if r in facts]
    if not item["refs"]:
        return f"Sentence {i} says {raw} but cites no [T#]. Cite the row that holds it or remove the number."
    if not known:
        return ""                                  # the unknown-ref line already tells the model what to fix
    if len(known) == 1:
        return (f"Sentence {i} says {raw} and cites {known[0]}, whose value is {_shown(facts[known[0]])}. "
                f"Use {known[0]}'s value or remove the number.")
    return f"Sentence {i} says {raw}, but none of {', '.join(known)} holds that value. Use a cited value or remove the number."


# ---- advice and forecast words (board resolution 4): named defects even when every number is traced ----------------
# The app never says buy / sell / hold / "you should" (red gate 1, README Limits) and the history is not a forecast. Narrow
# on purpose: "not a recommendation" (the label of a fictional mix), "sell-off", "expected shortfall", "would hold 4
# bets", "holdings" and "the Fed cut rates to" are descriptions, not advice. Only that label NOUN is exempt: "recommend"
# is a board-named advice word, so "do not recommend", "is not recommended" and "never recommended" are still advice.
_NOT_A_RECOMMENDATION = re.compile(r"\b(?:not|no|never|nor|isn['’]t|doesn['’]t|don['’]t)\s+(?:be\s+|a\s+|an\s+|any\s+|the\s+)*"
                                   r"recommendations?\b", re.I)
_FORECAST_VERB = (r"(?:fall|rise|drop|decline|lose|gain|grow|climb|cost|reach|recover|rebound|outperform|underperform|beat"
                  r"|break|breach|exceed|surge|crash|plunge|tumble|increase|decrease|double|halve|shrink|slide|sink|jump"
                  r"|rally|hit|go\s+(?:up|down)|be\s+(?:worth|higher|lower))")
_ADVICE_WORDS = (
    re.compile(r"\bshould(?:n['’]t|\s+not)?\b", re.I),
    re.compile(r"\brecommend(?:s|ed|ing|ation|ations)?\b", re.I),
    re.compile(r"\b(?:buy|buys|buying)\b", re.I),
    re.compile(r"\b(?:sell|sells|selling)\b(?!-?\s?offs?\b)", re.I),
    re.compile(r"\bexpect(?:s|ed|ing|ation|ations)?\b(?!\s+shortfall)", re.I),
    re.compile(r"\bunsuitable\b|\bnot\s+suitable\b", re.I),
    re.compile(rf"\b(?:won['’]t|will|(?:is\s+|are\s+)?going\s+to|is\s+likely\s+to|are\s+likely\s+to)\s+"
               rf"(?:also\s+|probably\s+|likely\s+|again\s+|then\s+|continue\s+to\s+|keep\s+)?{_FORECAST_VERB}\b", re.I),
)
# "hold" as a verb that tells someone what to do: opening a clause ("Hold NVIDIA"), "hold on to", "keep holding".
_HOLD = re.compile(r"(?:^|[.!?;:,]|\b(?:and|then|or|but|so)\b)\s*(?:please\s+|just\s+|simply\s+|also\s+|still\s+)?hold\b"
                   r"|\bhold\s+on(?:\s*to)?\b|\bhold\s+onto\b|\b(?:keep|keeps|keeping|continue|continues)\s+(?:to\s+)?hold(?:ing)?\b"
                   r"|\b(?:could|can|may|might|must|to)\s+hold\s+(?:it|them|this|that|these|those|your|the)\b", re.I)
# Ruling R27: advice by suggestion is advice. "Consider holding NVDA", "think about selling", "you may want to add" tell
# the investor what to do as surely as "hold"; "consider the 2022 fall" or "think about your horizon" do not (a verb of
# acting on a position must follow). agents/explainer.py uses this same pattern (a test pins that the two agree).
_SUGGEST = re.compile(r"\b(?:consider(?:s|ed|ing)?|think(?:s|ing)?\s+about|(?:you|investors?|one)\s+(?:may|might|could)"
                      r"\s+(?:want|wish|like)\s+to)\s+(?:buy|sell|hold|keep|add|trim|reduce|increase|cut|lower|raise|exit)"
                      r"(?:s|ing|ed|ping|ming|ting)?\b", re.I)
# Spec rulings R1 and R13 (Sun Nov 15): present-tense or unqualified claims about a replay and the old capacity phrase,
# named so the re-ask fixes them; not advice (they never withhold). agents/explainer.py uses this same pattern.
_R1 = re.compile(r"\bhold(?:s|ing)?\b(?:\W+\w+){0,4}?\W+up\s+to\b|\bfits?\b|\ballowed\b|\bsafe(?:r|st|ly|ty)?\b"
                 r"|\byou\s+can\b|\byou\s+said\s+you\s+could\s+absorb\b"
                 r"|\bwould\s+(?:have\s+)?pass(?:ed)?\b|\bacceptable\s+at\b"       # R20: no pass mark at a size
                 r"|\bheld\s+at\s+every\b|\bat\s+every\s+(?:[\w.-]+\s+){0,2}size\s+up\s+to\b|\bheld\b[^.;]{0,40}\bup\s+to\b"
                 r"|\bup\s+to\s+[\d.]+\s*%[^.;]{0,40}\bheld\b", re.I)
# The release gate's "hold (a verb)" and "hold up / on / through" rules (scripts/gate_rules.mjs), as a named defect with
# the plain alternative: "SPY would hold 30 % of the risk" -> "SPY would carry / make up 30 % of the risk" (Sun Nov 15).
_HOLD_VERB = re.compile(r"\b(?:you|we|i|they|investors?|to|should|could|would|will|can|may|might|must|keep|just|simply|then|"
                        r"please|always|never|don['’]t|do\s+not|better)\s+(?:hold|holds|holding)\b"
                        r"|\b(?:hold|holds|holding|held)\s+(?:up|on|onto|through|off|steady|tight|until)\b", re.I)


def _hold_verb_forms(text):
    """The gate's "hold (a verb)" forms in a sentence, each once, lower-cased; a span the advice rule (_HOLD) or the
    past-tense rule (_R1) already names is not named twice ("Keep holding it." is advice, "held up to" is R1)."""
    taken = [m.span() for rx in (_HOLD, _R1) for m in rx.finditer(text)]
    return list(dict.fromkeys(" ".join(m.group(0).lower().split()) for m in _HOLD_VERB.finditer(text)
                              if not any(a < m.end() and m.start() < b for a, b in taken)))


_HOLD_WORDS = ("hold", "holds", "holding", "held")       # a form that starts with one is a phrase ("held on"), not a verb


# "never broke" about a soft limit the mix went past (jury QA, Sun Nov 15: 40 % against a 10 % one-company limit is a
# caution, and "never broke" reads as "inside"): named, with the plain words to write instead.
_NEVER_BROKE = re.compile(r"\b(?:never|not|didn[’']t|wasn[’']t|hasn[’']t|haven[’']t)\s+(?:been\s+)?(?:broke|break|broken)\b",
                          re.I)


def _never_broke(text, result):
    """[(rule, form)] for each soft limit the mix went past (a failed row that is not hard) that the sentence names
    while saying it never broke."""
    m = _NEVER_BROKE.search(str(text))
    if not m or not isinstance(result, dict):
        return []
    low = str(text).lower()
    out = []
    for c in result.get("checks") or []:
        if c.get("status") != "fail" or c.get("tier") == "hard":
            continue
        words = RULE_WORDS.get(c.get("rule")) or [RULE_NAMES.get(c.get("rule"), "").lower()]
        if any(w and (w in low or w in _dehyphen(low)) for w in words):
            out.append((c.get("rule"), " ".join(m.group(0).lower().split())))
    return list(dict.fromkeys(out))


def _from_question(number, result, facts):
    """True when an untraced number is one the investor wrote in the question and no facts row holds it."""
    question = str((result or {}).get("question") or "") if isinstance(result, dict) else ""
    digits = re.sub(r"[^\d.]", "", str(number[0])).strip(".")
    if not digits or not question:
        return False
    asked = {d.replace(",", "").strip(".") for d in re.findall(r"\d[\d,]*(?:\.\d+)?", question)}
    return digits in asked and not any(isinstance(r, dict) and _holds(r, number) for r in (facts or {}).values())


_CUT_TO = re.compile(r"\bcut(?:s|ting)?\b(?P<mid>(?:\W+[\w.&/-]+){0,3}?)\W+to\b", re.I)
_NOT_A_POSITION = frozenset("rate rates interest policy tax taxes tariff tariffs duty duties dividend dividends guidance "
                            "forecast forecasts costs spending benefits".split())


# The reframe (controller ruling, Sun 2026-11-15): when the question asked for approval of a move (Result `reframe`,
# advice_guard.approval_seeking), a yes or a no is that approval, so the receipt names it like an advice word: re-asked
# once with the defect named, withheld if it stays (pipeline._finish). "No limit was crossed" is no answer.
_YES_NO = re.compile(r"^\W*(?:(?:so|well|in\s+short|short\s+answer|simply\s+put)\s*[,:]?\s*)?(?:yes|no|yep|nope)\b\s*"
                     r"(?:[,.!:;—–]|$)|\bthe\s+(?:short\s+)?answer\s+is\s+(?:yes|no)\b", re.I)


def _advice(text):
    """The advice and forecast phrases a sentence uses, each once, in text order ("should", "buy", "hold", "cut to",
    "will fall", "expect", "unsuitable"...), as the checker names them."""
    t = _NOT_A_RECOMMENDATION.sub(" ", text)
    hits = []
    for rx in _ADVICE_WORDS:
        hits += [(m.start(), re.sub(r"\s+", " ", m.group(0)).lower()) for m in rx.finditer(t)]
    hits += [(m.start(), "hold") for m in _HOLD.finditer(t)]
    hits += [(m.start(), " ".join(m.group(0).lower().split())) for m in _SUGGEST.finditer(t)]
    hits += [(m.start(), "cut to") for m in _CUT_TO.finditer(t)
             if not _NOT_A_POSITION & set(re.findall(r"[a-z]+", m["mid"].lower()))]
    return list(dict.fromkeys(label for _, label in sorted(hits)))


def _future_hits(item, as_of, catalog):
    """Things the sentence mentions that are dated after as_of: dates, months, years, catalog titles."""
    hits = [d for d in _dates(item["text"]) if d > as_of]
    low = item["text"].lower()
    for row in catalog or []:
        title = str(row.get("title") or "").lower()
        if title and str(row.get("date") or "")[:10] > as_of and title in low:
            hits.append(row.get("event_id") or row.get("title"))
    return hits


# A shock check that could not conclude (no close precedent, or too few separate episodes) has no result: a sentence that
# gives it one ("stayed inside the shock limit", "beyond the shock limit") is a named defect (navcheck case k, Sun Nov 15).
_SHOCK_RESULT = re.compile(r"\bshock\s+(?:check|limit)\b[^.;]*?\b(?:inside|within|beyond|past|passed|held|broke|over)\b"
                           r"|\b(?:inside|within|beyond|past)\s+(?:the\s+|your\s+)?shock\s+limit\b", re.I)


def _shock_abstained(result) -> bool:
    row = next((c for c in (result or {}).get("checks") or [] if c.get("rule") == "scenario_stress"), None)
    if row is None:
        return False
    n = row.get("n_episodes")
    return row.get("value") is None or (isinstance(n, int) and not isinstance(n, bool) and n < MIN_SHOCK_EPISODES)


def verify_numbers(sentences, facts, *, as_of=None, result=None, catalog=None):
    """The receipt: see the module docstring. Returns {verified, total, unverified, wrong_entity, wrong_kind,
    wrong_side, wrong_direction, advice, missing, future_refs, matches, defects}; item = {sentence (1-based, verdict
    = 1), number (as written), refs}; an advice item is {sentence, word, refs}."""
    facts = facts or {}
    as_of = str(as_of or (result or {}).get("as_of") or "")[:10] or None
    items = _sentences(sentences)
    abstained = _shock_abstained(result)
    out = {"verified": 0, "total": 0, "unverified": [], "wrong_entity": [], "wrong_kind": [], "wrong_side": [],
           "wrong_direction": [], "advice": [], "missing": [], "future_refs": [], "matches": [], "defects": []}
    lines = []
    for it in items:
        i, refs = it["i"], it["refs"]
        own = [f"Sentence {i} cites {r}, which is not in the facts. Cite only the facts you were given."
               for r in refs if r not in facts]
        clean, found = _numbers_pos(it["text"])
        contexts = _contexts(clean, found)
        for (_, _, number), ctx in zip(found, contexts):
            out["total"] += 1
            entry = {"sentence": i, "number": number[0], "refs": list(refs)}
            status, ref = _check_number(number, it, facts, ctx)
            if status == "unverified":
                out["unverified"].append(entry)
            else:
                out["matches"].append(entry)
                out["verified"] += status == "ok"
                if status != "ok":
                    out[status].append(entry)
            if number[3] == "words":
                own.append(f"Sentence {i} spells out a number (“{number[0]}”): write the number in digits and "
                           "cite the row that holds it, or remove it.")
            elif status == "unverified" and _from_question(number, result, facts):
                own.append(f"Sentence {i} says {number[0]}, a number from the investor's question, not a fact: "
                           "remove it.")                       # jury QA H4: "75 basis points" is the question's
            elif status != "ok":
                own.append(_number_line(i, number[0], status, ref, it, facts, ctx))
        for word in _advice(it["text"]):
            out["advice"].append({"sentence": i, "word": word, "refs": list(refs)})
            own.append(f"Sentence {i} gives advice or a forecast (“{word}”): describe what happened in this history instead.")
        if (result or {}).get("reframe") and _YES_NO.search(it["text"]):
            out["advice"].append({"sentence": i, "word": "yes / no", "refs": list(refs)})
            own.append(f"Sentence {i} answers yes or no to a question that asks for approval: EPICENTRE can't tell anyone "
                       "whether a move is right for them; say what the replay did against the limits they set.")
        own += [f"Sentence {i} says “{w}”: say what happened in this replay, in the past tense."
                for w in dict.fromkeys(" ".join(m.group(0).lower().split()) for m in _R1.finditer(it["text"]))]
        own += [f"Sentence {i} says “{w}”: " + ("write what happened without it, in plain words."
                                                if w.split()[0] in _HOLD_WORDS else
                                                "write “carry” or “make up” instead of “hold”.")
                for w in _hold_verb_forms(it["text"])]
        if {"your floor", "your capacity"} <= {(facts.get(ref) or {}).get("entity") for ref in it["refs"]}:
            own.append(f"Sentence {i} puts your capacity’s dollars beside your floor: your floor is a percentage (no "
                       "fall of more than it from any high); say the capacity and its line in their own sentence.")
        for rule, form in _never_broke(it["text"], result):
            own.append(f"Sentence {i} says “{form}”, but the mix went past {RULE_NAMES.get(rule, rule).lower()}, a soft "
                       "limit: write “went past your soft limit: a caution”.")
        if abstained and _SHOCK_RESULT.search(it["text"]):
            own.append(f"Sentence {i} gives the shock check a result, but it could not conclude. Write “No close "
                       "precedent at this date, so the shock check could not conclude.”")
        hits = _future_hits(it, as_of, catalog) if as_of else []
        out["future_refs"] += [{"sentence": i, "number": h, "refs": list(refs)} for h in hits]
        if hits:
            own.append(f"Sentence {i} refers to something dated after {as_of}. Remove it.")
        lines += [ln for ln in own if ln]
    out["missing"] = _global_defects(items, result)
    out["defects"] = list(dict.fromkeys(lines + out["missing"]))
    return out
