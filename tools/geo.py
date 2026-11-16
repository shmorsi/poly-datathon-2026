"""The shockwave: where the money really is by country, and how a shock reaches it (spec 10; plan A Task 7).

Exposure only, never returns, and never a forecast: it says which lines a shock's country, sector or
currency touches, not what the shock did (events.py measures that). Three functions, all read the
look-through of Task 6, so a past `as_of` is direct holdings, flagged (spec 10), and a gap is named:
  * `country_exposure`: the look-through's countries, with the two borderless buckets split out:
    crypto ("CRYPTO") and gold ("GLOBAL": the universe lists GLD as USA, the listing rule, but gold has
    no country). `countries` + `borderless` add up to 1; "OTHER" stays in `countries`.
  * `transmission`: three channels from an event (`family`, `regions`) to the lines you hold, one row per
    (ticker, channel, via), biggest first, rows under 0.05 % of the money dropped:
      country: a direct line, weight = line weight x the share of its countries inside `regions` (an ETF
        by its country rows when the look-through is real, else its listing country; gold is GLOBAL,
        crypto CRYPTO, and "GLOBAL", "CRYPTO" and "OTHER" are never inside a region);
      sector: `FAMILY_SECTORS[family]` against direct equities (`via` None) and against the dataset
        stocks inside the held ETFs (`via` = the ETF), the weights of the look-through;
      currency: USD-priced direct lines (crypto included) when `regions` has USA or CAN: US or Canadian
        news moves the USD/CAD rate (the loonie effect, spec 10).
  * `transmission_report`: the rows (plain dicts) together with the flags of the look-through behind them,
    `{"rows", "gaps", "mode", "source", "as_of"}`, so "unknown" is never a silent zero: a held ETF whose
    holdings are missing is a named gap, and `mode == "direct"` says no ETF was opened up. This is the
    carrier to read: it survives JSON and any reshaping of the rows. `transmission` is the same rows as a
    plain list (the ledger shape) with the flags as attributes (`.gaps`, `.mode`, `.source`, `.as_of`),
    which slicing, `list()`, a comprehension and `json.dumps` all drop.
The run's date: when a caller passes both `as_of=` and a look-through, the EARLIER of the two dates guards and
labels the output (ledger 30). A look-through dated after `as_of=` is no picture of the run: geo builds its
own at `as_of=` (`look_through(weights, holdings=holdings, universe=universe, as_of=as_of)`; before the holdings
snapshot that is direct holdings, flagged, never a 2026 snapshot under a 2025 label). One dated on or before
`as_of=` is used as it is, under its own date. `holdings=` is the frame you would give look_through (None reads
the local file). An event dated after that date is refused, and so is an event whose date cannot be read
(red gate 3: it could be a later one); an event with no date is fine.
"""
from __future__ import annotations

import datetime
import re

import pandas as pd

from tools.data import load_universe
from tools.lookthrough import load_holdings, look_through
from tools.portfolio import _held      # the one weight check: tickers upper-cased, none below 0, sum 1

FAMILY_SECTORS = {"war_oil": "Energy", "chips": "Information Technology"}
BORDERLESS = ("CRYPTO", "GLOBAL")
NOT_A_REGION = {"CRYPTO", "GLOBAL", "OTHER"}       # buckets of the look-through, never inside an event's regions
LOONIE_REGIONS = {"USA", "CAN"}                    # news here moves USD/CAD
DUST = 0.0005                                      # a row below this share of the money is not shown


class Transmission(list):
    """The rows of `transmission` (a plain list of dicts) plus `gaps`, `mode`, `source`, `as_of` of the report.

    Reshaping the list (slicing, `list()`, a comprehension, `json.dumps`) drops the attributes: read
    `transmission_report` when the flags must travel with the rows.
    """

    def __init__(self, rows, report: dict):
        super().__init__(rows)
        self.gaps = [dict(g) for g in report.get("gaps", [])]
        self.mode, self.source, self.as_of = report["mode"], report["source"], report["as_of"]


def _look(weights, lookthrough, universe, holdings, as_of) -> dict:
    """The look-through of the run; the earlier of its own date and `as_of` (the run's date) guards and labels the output
    (ledger 30). A supplied look-through dated on or before `as_of` is used as it is (its date is the earlier one); one
    dated after it is no picture of the run, so geo builds its own at `as_of` (esg flags are not geo's business), which
    for a run before the holdings snapshot is direct mode, flagged (spec 10)."""
    run = None if as_of is None else pd.Timestamp(as_of).strftime("%Y-%m-%d")
    if lookthrough is not None and (run is None or str(lookthrough["as_of"])[:10] <= run):
        return lookthrough
    return look_through(weights, holdings=holdings, universe=universe, esg_flags=set(), as_of=run)


def _missing(value) -> bool:
    """None or a NaN scalar (a blank cell of a table): no value."""
    return value is None or (pd.api.types.is_scalar(value) and not isinstance(value, str) and bool(pd.isna(value)))


def _regions(value) -> set:
    """ISO3 codes, upper-cased, from a list, tuple, set or a `;`-joined string; nothing or NaN is no region."""
    if _missing(value):
        return set()
    items = re.split(r"[;,]", value) if isinstance(value, str) else value
    return {str(r).strip().upper() for r in items if not _missing(r) and str(r).strip()}


def _event_date(event) -> str | None:
    """The event's ISO date; None when it has none (a headline has no date). A date that cannot be read is a ValueError:
    it could be a later one, and nothing dated after the run's date may reach the output (red gate 3)."""
    value = event.get("date")
    text = "" if _missing(value) else str(value).strip()[:10]
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return datetime.date.fromisoformat(text).isoformat()
        except ValueError:
            pass                                         # shaped like a date, but a month 13 or a 30 February
    raise ValueError(f"The event's date {str(value)!r} is not a date written YYYY-MM-DD, so it cannot be checked "
                     "against the run's date.")


def country_exposure(weights, *, lookthrough=None, universe=None, as_of=None, holdings=None) -> dict:
    """{"countries": {ISO3: w}, "borderless": {"CRYPTO": w, "GLOBAL": w}, "source", "as_of", "mode", "gaps"}.

    The look-through's countries (biggest first) with crypto and gold moved into `borderless` (0.0 when
    absent); "OTHER" stays in `countries`. `source`, `as_of`, `mode` and `gaps` come from the look-through
    unchanged (copied): a past `as_of` is direct mode and says so, a held ETF with no holdings is a gap.
    The earlier of `as_of=` and the look-through's own date labels the output (module docstring).
    """
    look = _look(weights, lookthrough, universe, holdings, as_of)
    return {"countries": {c: float(v) for c, v in look["countries"].items() if c not in BORDERLESS},
            "borderless": {c: float(look["countries"].get(c, 0.0)) for c in BORDERLESS},
            "source": look["source"], "as_of": look["as_of"], "mode": look["mode"],
            "gaps": [dict(g) for g in look.get("gaps", [])]}


def transmission_report(weights, event, *, lookthrough=None, universe=None, as_of=None, holdings=None) -> dict:
    """How an event reaches the money, with the flags of the look-through behind it:
    {"rows": [{"ticker", "channel": "country" | "sector" | "currency", "via", "weight"}], "gaps", "mode", "source", "as_of"}.

    `event` needs `family` and `regions` (a list of ISO3 or a `;`-joined string, as `load_events` gives
    them); `via` is the ETF a stock sits in (sector channel) or None for a direct line; `weight` is a share
    of the whole portfolio. Rows: biggest first (ties: ticker, channel, via), one per (ticker, channel, via),
    under 0.05 % dropped; plain dicts in a plain list, so the report survives JSON. `gaps` (named, copied),
    `mode` ("direct": no ETF was opened up), `source` and `as_of` (the earlier of `as_of=` and the look-through's
    date) are the look-through's: an empty `rows` with `mode == "direct"` or with gaps is "not known from
    holdings", never "no exposure". The module docstring has the three channels and the rule for `as_of=` and
    `holdings=`. Unknown ticker or weights not summing to 1: ValueError; so is an event dated after the
    output's `as_of` or with a date that cannot be read.
    """
    held = _held(weights)
    uni_df = load_universe() if universe is None else universe
    uni = uni_df.set_index("ticker")
    for t in held:
        if t not in uni.index:
            raise ValueError(f"Unknown ticker: {t}")
    look = _look(weights, lookthrough, uni_df, holdings, as_of)
    date = _event_date(event)
    if date is not None and date > look["as_of"]:
        raise ValueError(f"The event is dated {date}, after the run's date {look['as_of']}: it was not known then.")
    regions = _regions(event.get("regions"))
    inside = regions - NOT_A_REGION
    rows: list[dict] = []

    def add(ticker: str, channel: str, via, weight: float) -> None:
        if weight >= DUST:
            rows.append({"ticker": ticker, "channel": channel, "via": via, "weight": float(weight)})

    frame = None                                         # the ETF country rows, read only if some ETF needs them
    for t, w in held.items():                            # country: the share of the line inside the regions
        asset = str(uni.at[t, "asset_class"])
        if asset == "etf_commodity":
            shares = {"GLOBAL": 1.0}                     # gold has no country, whatever its listing says
        elif asset.startswith("etf") and look["mode"] == "lookthrough":
            if frame is None:
                found = load_holdings() if holdings is None else holdings
                frame = pd.DataFrame() if found is None else found
            shares = look_through({t: 1.0}, holdings=frame, universe=uni_df, esg_flags=set(), as_of=look["as_of"])["countries"]
        else:
            shares = {str(uni.at[t, "country"]): 1.0}    # a stock, crypto ("CRYPTO"), or an ETF counted as its market
        add(t, "country", None, w * sum(shares.get(c, 0.0) for c in inside))

    sector = FAMILY_SECTORS.get(str(event.get("family") or "").strip().lower())
    if sector:                                           # sector: direct equities, then the dataset stocks inside ETFs
        for t, w in held.items():
            if uni.at[t, "asset_class"] == "equity" and uni.at[t, "sector"] == sector:
                add(t, "sector", None, w)
        for t, entry in look["stocks"].items():
            if t in uni.index and uni.at[t, "sector"] == sector:
                for v in entry["via"]:
                    add(t, "sector", v["etf"], v["weight"])

    if regions & LOONIE_REGIONS:                         # currency: USD-priced lines, crypto included
        for t, w in held.items():
            if uni.at[t, "currency"] == "USD":
                add(t, "currency", None, w)

    rows.sort(key=lambda r: (-r["weight"], r["ticker"], r["channel"], r["via"] or ""))
    return {"rows": rows, "gaps": [dict(g) for g in look.get("gaps", [])], "mode": look["mode"],
            "source": look["source"], "as_of": look["as_of"]}


def transmission(weights, event, *, lookthrough=None, universe=None, as_of=None, holdings=None) -> Transmission:
    """`transmission_report(...)["rows"]` as the ledger's plain list, which also carries `.gaps`, `.mode`, `.source`, `.as_of`.

    Kept for compatibility. Slicing, `list()`, a comprehension and `json.dumps` drop those attributes, so a caller
    that reshapes the rows reads `transmission_report` instead (same arguments, same errors).
    """
    report = transmission_report(weights, event, lookthrough=lookthrough, universe=universe, as_of=as_of, holdings=holdings)
    return Transmission(report["rows"], report)
