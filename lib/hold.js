/* EPICENTRE Replay, lane hold: what each investor holds, and what is inside the funds (the workshop's first step, OBSERVE:
   positions, weights, apparent exposures). Pure: no DOM, no network; P is the page's PF (web/lib.js: fmt, moveOf), passed in.
   Every number is a Result key, or the one multiplication the page already makes elsewhere (amount x weight = dollars).
   holdModel(r, P)   the hero list: "What Robert holds today", <= 5 rows (label, ticker, weight, dollars), today's stacked bar,
                     and ONE look-through line ("Looking inside the funds: 87.6 % of the money is in Canada.")
   stripModel(r, P)  the stage's TODAY vs WITH THE MOVE bars (the same tone per holding, the move in magenta); null: no move
   lookModel(r, P)   "What's inside the funds": countries and industries (top 5, today vs with the move), the funds' public
                     names, the holdings date and coverage; mode "direct": one honest line, nothing else
   Tests: tests/web_hold_test.mjs. */
import { plainLabel, fundName, kindOf, countryName, NOT_A_COUNTRY } from "./funds.js";

export const MAX_ROWS = 5;          // the hero list: at most five rows (a sixth holding and more fold into the fifth row)
export const TOP = 5;               // the look-through: the five largest countries and industries
export const DIRECT_LINE = "Fund contents unavailable here; each fund is counted as one holding.";
export const NO_MOVE = "No move in the question";
export const SECTOR_NOTE = "Industries count only the money in company shares; bonds, gold and crypto have none.";
/* fees (RETHINK G7): the prices are adjusted closes, so each fund's own costs are already inside them */
export const FEES = "Each fund’s own fees are already in its price (adjusted close, dividends reinvested).";
/* why the replay covers these five years (the coordinator's words, 14:40, from the lead's question "what's the point of 2021?") */
export const WHY = Object.freeze({ question: "Why 2021–26?",
  answer: "It is the organizers’ official dataset: five years that include 2022, when stocks and bonds fell together, the 2023 rate shock and the 2025 tariff shocks. Older crises: see",
  link: "Not just 2022" });

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const STOP = new Set(["blocked", "clarify", "error"]);
const EPS = 1e-9;

/* a weights map as [[ticker, weight]] with weight > 0, largest first (ties by ticker: one order everywhere) */
function ranked(map) {
  return Object.entries(obj(map) || {}).filter(([tk, w]) => str(tk) && isNum(w) && w > EPS)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}
const sameMix = (a, b) => {
  const ka = ranked(a), kb = ranked(b);
  return ka.length === kb.length && ka.every(([tk, w]) => isNum(b[tk]) && Math.abs(b[tk] - w) < EPS);
};

/* today's mix and the mix with the move: baseline.portfolio and portfolio; a question with no move (a shock, a fit) carries one
   mix only (no baseline, or the same weights): today = that mix, after = null */
export function mixes(r, P) {
  r = obj(r);
  if (!r || STOP.has(str(r.status) || "")) return null;
  const port = obj(r.portfolio), base = obj(obj(r.baseline) && r.baseline.portfolio);
  const today = base && ranked(base).length ? base : port;
  if (!today || !ranked(today).length) return null;
  const moved = !!(base && port && ranked(port).length && !sameMix(base, port));
  const mv = moved && P && typeof P.moveOf === "function" ? P.moveOf(r) : null;
  let ticker = mv && str(mv.ticker);
  if (moved && !ticker) {                       // no move key: the holding that grew the most
    const up = ranked(port).map(([tk, w]) => [tk, w - (isNum(base[tk]) ? base[tk] : 0)]).sort((a, b) => b[1] - a[1])[0];
    ticker = up && up[1] > EPS ? up[0] : null;
  }
  return { today, after: moved ? port : null, move: moved && ticker ? ticker : null };
}

/* one tone per holding, the same in the hero rows, the hero bar and the stage bars: today's order (0 = the largest); the move
   is "move" (magenta, the page's colour for the move and nothing else) in the mix with the move only */
export function tones(m) {
  const t = {};
  ranked(m && m.today).forEach(([tk], i) => { t[tk] = i; });
  let next = Object.keys(t).length;
  for (const [tk] of ranked(m && m.after)) if (!(tk in t) && tk !== m.move) t[tk] = next++;
  return t;
}
const toneOf = (t, tk, m, side) => (side === "after" && m && tk === m.move ? "move" : isNum(t[tk]) ? Math.min(t[tk], 5) : 5);

/* "Robert"; a profile whose name is not a person's ("Too Canadian?") reads "this portfolio" */
function whoOf(r) {
  const name = str(obj(r.profile) && r.profile.name);
  return name && /^[A-Z][a-z]+$/.test(name) ? name : null;
}

const fmtShare = (P, w) => (P && P.fmt ? P.fmt.share(w) : "");
const fmtPct = (P, w) => (P && P.fmt ? P.fmt.pct(w) : "");
const fmtMoney = (P, x) => (P && P.fmt ? P.fmt.money(x) : "");
const listWords = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/* a stacked bar: segments in order, x0 / x1 as fractions of the bar (the weights add up to 1) */
function bar(entries, t, m, side, P) {
  let x = 0;
  return entries.map(([tk, w]) => {
    const seg = { ticker: tk, label: plainLabel(tk), kind: kindOf(tk), weight: w, weightText: fmtShare(P, w), tone: toneOf(t, tk, m, side), x0: x, x1: x + w };
    x += w;
    return seg;
  });
}

/* the mix with the move, in today's order with the move last: the eye compares each holding where it was, and the move is
   the magenta at the end */
function afterOrder(m) {
  const a = obj(m.after) || {};
  const kept = ranked(m.today).map(([tk]) => tk).filter((tk) => tk !== m.move && isNum(a[tk]) && a[tk] > EPS);
  const added = ranked(a).map(([tk]) => tk).filter((tk) => tk !== m.move && !kept.includes(tk));
  return [...kept, ...added, ...(m.move && isNum(a[m.move]) ? [m.move] : [])].map((tk) => [tk, a[tk]]);
}

/* ---- the hero list ---- */
export function holdModel(r, P) {
  const m = mixes(r, P);
  if (!m) return null;
  const t = tones(m), who = whoOf(r), amount = isNum(r.amount) && r.amount > 0 ? r.amount : null;
  const row = ([tk, w]) => {
    const dollars = amount === null ? null : amount * w;
    return { ticker: tk, label: plainLabel(tk), name: fundName(tk), kind: kindOf(tk), weight: w, weightText: fmtShare(P, w),
      dollars, dollarsText: dollars === null ? null : fmtMoney(P, dollars), tone: toneOf(t, tk, m, "today") };
  };
  const all = ranked(m.today);
  const shown = all.length > MAX_ROWS ? all.slice(0, MAX_ROWS - 1) : all;
  const rest = all.slice(shown.length);
  let more = null;
  if (rest.length) {
    const w = rest.reduce((a, [, x]) => a + x, 0), dollars = amount === null ? null : amount * w;
    more = { count: rest.length, tickers: rest.map(([tk]) => tk), label: listWords(rest.map(([tk]) => plainLabel(tk))),
      weight: w, weightText: fmtShare(P, w), dollars, dollarsText: dollars === null ? null : fmtMoney(P, dollars),
      parts: rest.map(row) };
  }
  return { who, title: r.pilot === YOU ? YOU_TITLE : `What ${who || "this portfolio"} holds now`, fiction: "(fictional)", amount, amountText: amount === null ? null : fmtMoney(P, amount),
    rows: shown.map(row), more, bar: bar(all, t, m, "today", P), moved: !!m.after, move: m.move,
    noMove: m.after ? null : NO_MOVE, look: lookLine(r, P) };
}

/* the one look-through line: the largest share of the money in one country (a place: never gold's GLOBAL, crypto, OTHER) */
export function lookLine(r, P) {
  const lt = obj(obj(r) && r.lookthrough), today = obj(lt && lt.today);
  if (!today) return null;
  if (today.mode === "direct") return { kind: "direct", text: DIRECT_LINE, segs: [[DIRECT_LINE]] };
  const top = ranked(today.countries).find(([code]) => !NOT_A_COUNTRY.has(code));
  if (!top) return null;
  const share = fmtPct(P, top[1]), place = countryName(top[0]);
  if (!share) return null;
  const lead = "Looking inside the funds: ";
  return { kind: "country", code: top[0], share: top[1], shareText: share, place,
    text: `${lead}${share} of the money is in ${place}.`, segs: [[lead], [share, "num"], [` of the money is in ${place}.`]] };
}

/* ---- the stage strip: today and with the move ---- */
export function stripModel(r, P) {
  const m = mixes(r, P);
  if (!m || !m.after || !m.move) return null;
  const t = tones(m), today = bar(ranked(m.today), t, m, "today", P), after = bar(afterOrder(m), t, m, "after", P);
  const say = (segs) => segs.map((s) => `${s.label} ${s.weightText}`).join(", ");
  const moveLabel = plainLabel(m.move);
  return { today, after, move: { ticker: m.move, label: moveLabel, weight: m.after[m.move], weightText: fmtShare(P, m.after[m.move]) },
    summary: `Today: ${say(today)}. With the move: ${say(after)}.` };
}

/* ---- "What's inside the funds" ---- */
function rows(today, after, P, name) {
  const keys = new Set([...Object.keys(obj(today) || {}), ...Object.keys(obj(after) || {})]);
  const val = (o, k) => (obj(o) && isNum(o[k]) ? o[k] : null);
  return [...keys].map((k) => ({ key: k, t: val(today, k), a: val(after, k) }))
    .filter((x) => (x.t !== null && x.t > EPS) || (x.a !== null && x.a > EPS))
    .sort((x, y) => Math.max(y.t || 0, y.a || 0) - Math.max(x.t || 0, x.a || 0) || (x.key < y.key ? -1 : 1))
    .slice(0, TOP)
    .map((x) => ({ key: x.key, name: name(x.key), today: x.t, todayText: x.t === null ? null : fmtPct(P, x.t),
      after: after ? x.a : null, afterText: after && x.a !== null ? fmtPct(P, x.a) : null }));
}
export function lookModel(r, P) {
  const m = mixes(r, P), lt = obj(obj(r) && r.lookthrough), today = obj(lt && lt.today);
  if (!m || !today) return null;
  const after = m.after ? obj(lt.after) : null;
  if (today.mode === "direct") return { mode: "direct", direct: DIRECT_LINE, moved: !!m.after };
  const held = [...ranked(m.today).map(([tk]) => tk), ...ranked(m.after).map(([tk]) => tk)].filter((tk, i, a) => a.indexOf(tk) === i);
  const funds = held.filter((tk) => kindOf(tk) === "fund").map((tk) => ({ ticker: tk, label: plainLabel(tk), name: fundName(tk) }));
  const cov = { ...(obj(today.coverage) || {}), ...(obj(after && after.coverage) || {}) };
  const snaps = [...Object.values(obj(today.snapshot) || {}), ...Object.values(obj(after && after.snapshot) || {})];
  const coverage = Object.entries(cov).filter(([tk, c]) => isNum(c) && held.includes(tk))
    .map(([tk, c]) => ({ ticker: tk, share: c, shareText: fmtPct(P, c) }));
  const dates = [...new Set(snaps.filter(str))].sort();
  const gaps = [...(Array.isArray(today.gaps) ? today.gaps : []), ...(after && Array.isArray(after.gaps) ? after.gaps : [])]
    .map(obj).filter((g) => g && str(g.etf)).map((g) => g.etf).filter((tk, i, a) => a.indexOf(tk) === i);
  const notes = [], asOf = str(r.as_of) || str(today.as_of), end = asOf && P && P.fmt ? P.fmt.date(asOf) : null;
  /* the holdings date (the lead, 14:40: "should the scan date be today?"): the issuers' snapshot, never after the data's last day */
  if (dates.length && end) notes.push(`Fund holdings as published ${dates.every((d) => d.slice(0, 10) === asOf.slice(0, 10)) ? "on" : "on or before"} ${end}, the last day of the data. Nothing dated later is used.`);
  if (coverage.length) notes.push(`The holdings those files name cover ${listWords(coverage.map((c) => `${c.shareText} of ${c.ticker}`))}; the country and industry splits cover each whole fund.`);
  if (gaps.length) notes.push(`No holdings list for ${listWords(gaps)}: what is inside ${gaps.length === 1 ? "it" : "them"} is unknown here, not zero.`);
  notes.push(FEES);
  return { mode: "lookthrough", moved: !!after, noMove: m.after ? null : NO_MOVE, asOf,
    countries: rows(today.countries, after && after.countries, P, countryName),
    sectors: rows(today.sectors, after && after.sectors, P, (k) => k),
    sectorNote: SECTOR_NOTE, funds, coverage, dates, notes };
}

/* ---- the holdings editor (live app; coordinator item 4, the lead: "what they hold or what they want to hold? … customizable?").
   Seeded only with the investor's own mix; the total must reach 100 %; the server judges everything else. Pure. ---- */
export const EDITED_TITLE = "Your holdings (edited)";
export const PENDING_LINE = "Replay to see these holdings through 2021–26 and what is inside their funds.";
const whose = (r) => { const w = whoOf(obj(r) || {}); return w ? `${w}’s` : "this portfolio’s"; };
export const staticEditLine = (r) => (obj(r) && r.pilot === YOU ? "Editing holdings needs the live app; this mix is an assumed example."
  : `Editing holdings needs the live app; these are ${whose(r)} fictional holdings.`);
export const resetLabel = (r) => (obj(r) && r.pilot === YOU ? null : `Back to ${whose(r)} holdings`);
const tenth = (x) => Math.round(x * 10) / 10;
const pctOf = (v) => { const n = typeof v === "number" ? v : parseFloat(String(v == null ? "" : v).replace(",", ".")); return Number.isFinite(n) ? n : NaN; };

/* the rows the editor opens with: the investor's own mix today, in percent (one decimal), largest first */
export function seedRows(r) {
  const m = mixes(r, null);
  return m ? ranked(m.today).map(([ticker, w]) => ({ ticker, pct: tenth(w * 100) })) : [];
}
/* the live total of the rows, in percent (a blank or unreadable weight counts as nothing) */
export function totalOf(rows) {
  return tenth((rows || []).reduce((a, x) => { const p = pctOf(x && x.pct); return a + (Number.isFinite(p) && p > 0 ? p : 0); }, 0));
}
export const totalOk = (t) => Math.abs(t - 100) < 0.05;
/* what keeps "Use these holdings" off, in plain words (empty when it can be used) */
export function editProblems(rows, amount) {
  const out = [], list = (rows || []).filter((x) => x && str(x.ticker));
  const bad = list.filter((x) => { const p = pctOf(x.pct); return !Number.isFinite(p) || p <= 0 || p > 100; });
  if (!list.length) out.push("Add at least one holding.");
  if (bad.length) out.push(`Give ${listWords(bad.map((x) => plainLabel(x.ticker)))} a weight above 0 %.`);
  const t = totalOf(list);
  if (list.length && !totalOk(t)) out.push(`The weights add up to ${t.toFixed(1).replace(/\.0$/, "")} %; they must reach 100 %.`.replace(/(\d) %/g, "$1\u00a0%"));
  const a = pctOf(amount);
  if (!(Number.isFinite(a) && a > 0)) out.push("Type an amount above $0.");
  return out;
}
/* the edited holdings as the store keeps them ({pilot, portfolio: {ticker: fraction}, amount}), or null when not usable */
export function customFrom(rows, amount, pilot) {
  if (editProblems(rows, amount).length || !str(pilot)) return null;
  const portfolio = {};
  for (const x of rows) if (x && str(x.ticker)) portfolio[x.ticker] = Number(((portfolio[x.ticker] || 0) + pctOf(x.pct) / 100).toFixed(10));
  return { pilot, portfolio, amount: Math.round(pctOf(amount)) };
}
/* the edited holdings for this investor, if any */
export const customFor = (custom, pilot) => (obj(custom) && custom.pilot === pilot && obj(custom.portfolio) ? custom : null);
/* POST /api/run's body with the edited holdings as today's mix (and their amount); unchanged without them */
export function withHoldings(body, custom, pilot) {
  const c = customFor(custom, pilot);
  if (!c || !obj(body)) return body;
  return { ...body, portfolio: { ...c.portfolio }, amount: isNum(c.amount) && c.amount > 0 ? c.amount : body.amount };
}
/* the Result on screen already ran on these holdings (its today's mix is the edited one): no new run is needed */
export function ranOn(custom, r) {
  const c = obj(custom), m = mixes(r, null);
  return !!(c && m && sameMix(c.portfolio, m.today) && (!isNum(c.amount) || c.amount === r.amount));
}
/* the card for edited holdings before their run lands: the same rows and gauge, no look-through (it needs a run) */
export function customModel(r, custom, P) {
  const c = customFor(custom, obj(r) && r.pilot);
  if (!c) return null;
  const synthetic = { status: "ok", pilot: r.pilot, profile: r.profile, amount: c.amount, portfolio: c.portfolio };
  const m = holdModel(synthetic, P);
  return m && { ...m, title: EDITED_TITLE, fiction: null, look: { kind: "pending", text: PENDING_LINE, segs: [[PENDING_LINE]] }, edited: true };
}

/* ---- lane profile-ui's fifth chip, "You" (R46): until the first You run lands, the card shows the holdings profile-ui put on the
   store (an assumed example mix, holdings.assumed), never the last investor's Result. The contract of profile-ui's
   web/lib/you.js youSeed, kept here so the card never depends on a module that may not have landed. "Your holdings now", never
   "what you hold" (the release gate's hold-verb rule). ---- */
export const YOU = "you";
export const YOU_TITLE = "Your holdings now";
export const YOU_ASSUMED = "assumed: edit it";
export function youSeed(state) {
  const st = obj(state);
  if (!st || st.investor !== YOU) return null;
  const r = obj(st.result);
  if (r && r.pilot === YOU) return null;
  const c = customFor(st.holdings, YOU);
  return c ? { status: "ok", pilot: YOU, amount: c.amount, portfolio: { ...c.portfolio }, profile: null } : null;
}

/* ---- the limits card under step 1 (LIMITS_MODEL.md, 16:40): one limits object, three sources, one precedence: SET BY YOU (the
   Result's limits.edited, through #checklist's editor) > FROM YOUR WORDS (store.limitsIn, lane profile-ui: the AI reader's words,
   checked by code) > ASSUMED (the Result's limits, from the profile's risk band). Every value is a Result key or limitsIn's. ---- */
export const SOURCE_TAG = Object.freeze({ you: "set by you", words: "from your words", assumed: "assumed" });
export const SOURCE_SAY = Object.freeze({ you: "Set by you; the check uses it.", words: "Read from your words and checked by code.",
  assumed: "Assumed from the profile, not set by you." });
export const NO_LIMITS = "No limits set";
/* the precedence, said on screen (LIMITS_MODEL.md, CONFLICTS: nothing is overridden silently) */
export const PRECEDENCE = "Set by you wins over your words, and your words win over what the profile assumed.";
export function limitsCard(r, P, limitsIn, holdings) {
  r = obj(r);
  if (!r || STOP.has(str(r.status) || "") || !P || !P.fmt) return null;
  const f = P.fmt;
  let prof = obj(r.profile) || {};
  /* "You" (limits-QA, 17:20): the You card's plan (store.limitsIn, store.holdings) is the card's whenever it differs from the run
     on screen (a re-read before the replay), or before the first You run: the run's old limits, words and amount never leak in */
  const isYou = r.pilot === YOU, innYou = isYou && obj(limitsIn) && limitsIn.pilot === YOU ? limitsIn : null, hYou = isYou ? customFor(holdings, YOU) : null;
  if (innYou) {
    const L0 = obj(r.limits) || {}, W0 = obj(innYou.limits) || {};
    const runCap = [L0.capacity_dollars, prof.capacity].find(isNum);
    const differs = !obj(r.limits) || (hYou && isNum(hYou.amount) && hYou.amount !== r.amount) || (isNum(innYou.capacity) && innYou.capacity !== runCap)
      || Object.entries(W0).some(([k, v]) => isNum(v) && v !== L0[k]) || (typeof innYou.esg === "boolean" && innYou.esg !== prof.esg)
      || (Array.isArray(L0.from_words) ? L0.from_words : []).some((k) => PLAN_KEYS.test(k) && !planHas(innYou, k));   // limits the run read that the new words lack
    if (differs) return planCard(innYou, hYou && isNum(hYou.amount) ? hYou.amount : r.amount, f);
  } else if (isYou && !obj(r.limits)) return planCard({ pilot: YOU }, hYou && isNum(hYou.amount) ? hYou.amount : r.amount, f);
  /* a run with no limits ({"none": true}: result.limits null, no verdict) is valid: "No limits set", the replay still full */
  if (r.limits === null && r.pilot !== YOU) return { rows: [], none: true, summary: NO_LIMITS };
  const L = obj(r.limits) || {};
  const inn = obj(limitsIn) && limitsIn.pilot === r.pilot ? limitsIn : null;    // the words read before a run (lane profile-ui)
  const W = obj(inn && inn.limits) || {}, from = obj(inn && inn.source) || {};
  const said = obj(inn && inn.words) || {};                                       // the exact words (lane profile-ui keeps them)
  /* result.limits.from_words: the keys the words set in this run (a list; a {key: words} map is read the same way) */
  const ranWords = new Set(Array.isArray(L.from_words) ? L.from_words : Object.keys(obj(L.from_words) || {}));
  const edited = new Set(Array.isArray(L.edited) ? L.edited : []);
  if (inn && inn.none === true && !edited.size && !ranWords.size) return { rows: [], none: true, summary: NO_LIMITS };
  const rows = [];
  /* one rule for the card and the checklist (lane sector-limits): the run's from_words names it -> from your words; else edited
     names it -> set by you (words reach the engine as overrides, so from_words is read first); else assumed. Before a run, the
     words read on the page (store.limitsIn) show as from your words. */
  /* the engine's own tag first (governance.limit_source: every check row carries source, 7c28484); else the same rule here */
  const RULE_KEY = { max_drawdown: "floor", scenario_stress: "scenario_stress", single_stock: "single_stock", sector: "sector", crypto: "crypto",
    esg_direct: "esg" };
  const engine = {};
  for (const c of Array.isArray(r.checks) ? r.checks : []) {
    const k = obj(c) && typeof c.rule === "string" ? (c.rule.startsWith("sector_cap:") ? `sector_caps.${c.rule.slice(11)}` : RULE_KEY[c.rule]) : null;
    if (k && SOURCE_TAG[c.source]) engine[k] = c.source;
  }
  const youSrc = innYou && obj(innYou.source) ? innYou.source : null;          // You: the You card's own tags win over the engine's
  const own = (key, group) => (ranWords.has(key) ? "words" : edited.has(key) || (group && edited.has(group)) ? "you" : "assumed");

  /* a floor the capacity set (floor_source "capacity": the dollars you could lose over the amount) comes from where the capacity came */
  const youTag = (key) => {
    if (key === "floor" && L.floor_source === "capacity" && !SOURCE_TAG[youSrc.floor]) key = "capacity";     // one floor, one source
    const t = youSrc[key] || (key === "horizon_years" ? youSrc.horizon : null) || (ranWords.has(key) ? "words" : null);   // the run's own words next
    return SOURCE_TAG[t] ? t : "assumed";
  };
  const srcOf = (key, group) => (youSrc && !edited.has(key) ? youTag(key)
    : engine[key] || (key === "floor" && L.floor_source === "capacity" && own("floor") === "assumed" ? own("capacity") : own(key, group)));
  const pick = (key) => {
    const ran = isNum(L[key]) ? { v: L[key], src: srcOf(key) } : null;
    if (ran && ran.src === "you") return ran;                                   // set by you always wins
    if (isNum(W[key]) && (from[key] === "words" || from[key] === undefined)) return { v: W[key], src: "words" };   // words not run yet
    return ran;
  };
  const add = (key, label, x, value, assumedText) => {
    if (!value) return;
    if (!x) { rows.push({ key, label, value, source: null, tag: null, say: null, words: null, assumed: null, conflict: null }); return; }   // "No limit"
    rows.push({ key, label, value, source: x.src, tag: SOURCE_TAG[x.src], say: SOURCE_SAY[x.src], words: str(said[key]),
      assumed: x.src === "words" && assumedText ? `the profile assumed ${assumedText}` : null,
      conflict: x.src === "you" && str(said[key]) ? str(said[key]) : null });
  };
  const capOf = (v) => (v === 0 ? "Excluded (0\u00a0%)" : `Up to ${f.share(v)}`);    // 0 is never ambiguous on screen
  const assumedOf = (key, text) => (isNum(L[key]) && isNum(W[key]) && W[key] !== L[key] && !ranWords.has(key) ? text(L[key]) : null);
  const fl = pick("floor");
  add("floor", "Falls", fl, fl ? `No more than ${f.share(-fl.v)} from any high` : "No limit", assumedOf("floor", (v) => f.share(-v)));
  /* the floor the capacity set says so on hover: "15 % = the $90,000 you could lose, of $600,000" */
  const capD = [L.capacity_dollars, prof.capacity, prof.capacity_dollars].find(isNum);
  if (fl && L.floor_source === "capacity" && isNum(capD) && isNum(r.amount) && rows.length) {
    const fr = rows[rows.length - 1];
    fr.say = `${f.share(-fl.v)} = the ${f.money(capD)} you could lose, of ${f.money(r.amount)}. ${fr.say}`;
    if (!fr.words && str(said.capacity) && fr.source === "words") fr.words = str(said.capacity);
    if (fr.source !== "assumed") fr.say = fr.say.replace(SOURCE_SAY.assumed, "").trim() + (fr.say.includes(SOURCE_SAY[fr.source]) ? "" : ` ${SOURCE_SAY[fr.source]}`);
  }
  const amount = isNum(r.amount) && r.amount > 0 ? r.amount : null;
  const capW = isNum(inn && inn.capacity) ? { v: inn.capacity, src: "words" } : null;
  const capR = [L.capacity_dollars, prof.capacity, prof.capacity_dollars].find(isNum);
  const capFact = obj(r.capacity) && isNum(r.capacity.capacity) ? r.capacity.capacity : null;
  const typedCap = isNum(L.capacity_dollars) && capFact !== null && L.capacity_dollars !== capFact;   // a recheck typed it (only "floor" in edited)
  const capRan = isNum(capR) ? { v: capR, src: typedCap || (edited.has("floor") && L.floor_source === "capacity") ? "you" : srcOf("capacity") } : null;
  const cap = capRan && capRan.src === "you" ? capRan : capW || capRan;
  const C = obj(r.capacity), line = cap && cap.src === "assumed" && !typedCap && C && obj(C.today) && isNum(C.today.line) ? C.today.line
    : cap && amount !== null && cap.v < amount ? amount - cap.v : null;
  add("capacity", "Can lose", cap, cap ? `${f.money(cap.v)}${line !== null ? `, staying above ${f.money(line)}` : ""}` : "No limit",
    capW && capRan && capRan.src === "assumed" && capW.v !== capRan.v ? f.money(capRan.v) : null);
  const sh = pick("scenario_stress");
  add("scenario_stress", "One shock", sh, sh ? `No more than ${f.pct(Math.abs(sh.v)).replace(/\.0(?=\u00a0%)/, "")}` : "No limit");
  const one = pick("single_stock");
  add("single_stock", "One company", one, one ? capOf(one.v) : "No limit", assumedOf("single_stock", capOf));
  const sec = pick("sector");
  add("sector", "One industry", sec, sec ? capOf(sec.v) : "No limit", assumedOf("sector", capOf));
  const caps = { ...(obj(L.sector_caps) || {}) }, capsSrc = {};
  for (const k of Object.keys(caps)) capsSrc[k] = srcOf(`sector_caps.${k}`, "sector_caps");
  for (const [k, v] of Object.entries(obj(W.sector_caps) || {})) if (isNum(v) && capsSrc[k] !== "you") { caps[k] = v; capsSrc[k] = "words"; }
  for (const [k, v] of Object.entries(caps)) if (isNum(v)) {
    const x = { v, src: capsSrc[k] };
    rows.push({ key: `sector_caps.${k}`, label: k, value: capOf(v), source: x.src, tag: SOURCE_TAG[x.src],
      say: SOURCE_SAY[x.src], words: str(said[`sector_caps.${k}`]), assumed: null,
      conflict: x.src === "you" && str(said[`sector_caps.${k}`]) ? str(said[`sector_caps.${k}`]) : null });
  }
  const cr = pick("crypto");
  add("crypto", "Crypto", cr, cr ? capOf(cr.v) : "No limit", assumedOf("crypto", capOf));
  /* the values screen reads On or Off, never a bare 0 (the profile's esg, or the words' esg before a run) */
  const wEsg = typeof W.esg === "boolean" ? W.esg : obj(W.values) && typeof W.values.esg === "boolean" ? W.values.esg
    : inn && typeof inn.esg === "boolean" ? inn.esg : null;
  const esgRan = typeof prof.esg === "boolean" ? { v: prof.esg, src: srcOf("esg") } : null;
  const esgTag = inn && obj(inn.source) && SOURCE_TAG[inn.source.esg] ? inn.source.esg : "words";
  const esg = esgRan && esgRan.src === "you" ? esgRan : wEsg !== null ? { v: wEsg, src: esgTag } : esgRan;
  if (esg) {
    add("values", "Values screen", esg, esg.v ? "On" : "Off", wEsg !== null && esgRan && esgRan.src === "assumed" && wEsg !== esgRan.v ? (esgRan.v ? "on" : "off") : null);
    const vr = rows[rows.length - 1];
    if (vr && vr.key === "values" && !vr.words && str(said.esg)) vr.words = str(said.esg);
  }
  if (isNum(prof.horizon_years) && prof.horizon_years > 0) add("horizon", "Horizon", { src: srcOf("horizon_years") }, f.years(prof.horizon_years));
  if (!rows.some((x) => x.source)) return { rows: [], none: true, summary: NO_LIMITS };
  const conflicts = rows.filter((x) => x.conflict).map((x) => ({ key: x.key,
    text: `You said “${x.conflict}”; you set ${x.label.toLowerCase()} to ${x.value.charAt(0).toLowerCase()}${x.value.slice(1)}. The replay uses your value.` }));
  const counted = rows.filter((x) => x.source);
  const n = (s) => counted.filter((x) => x.source === s).length, you = n("you"), words = n("words");
  const assumed = n("assumed");
  const parts = [you ? `${you} set by you` : null, words ? `${words} from your words` : null, assumed ? `${assumed} assumed from the profile` : null].filter(Boolean);
  return { rows, none: false, conflicts, precedence: PRECEDENCE,
    summary: !you && !words ? `${counted.length} limits, all assumed from the profile, none set by you.` : `${counted.length} limits: ${listWords(parts)}.` };
}

/* the You card's plan before its replay: limitsIn's values and tags, the holdings' amount; whatever the words left unstated reads
   "Assumed from the profile" (the replay sets it from the profile's band), never "No limit" */
function planCard(inn, amount, f) {
  const W = obj(inn.limits) || {}, src = obj(inn.source) || {}, said = obj(inn.words) || {};
  if (inn.none === true) return { rows: [], none: true, summary: NO_LIMITS, conflicts: [], precedence: PRECEDENCE };
  const rows = [];
  const tagOf = (k, has) => (SOURCE_TAG[src[k]] ? src[k] : has ? "words" : "assumed");
  const row = (key, label, has, value) => {
    const s0 = tagOf(key, has);
    rows.push({ key, label, value: has ? value : "Assumed from the profile", source: s0, tag: SOURCE_TAG[s0], say: SOURCE_SAY[s0],
      words: str(said[key]), assumed: null, conflict: null });
  };
  const capOf = (v) => (v === 0 ? "Excluded (0\u00a0%)" : `Up to ${f.share(v)}`);
  const cap = isNum(inn.capacity) ? inn.capacity : null, amt = isNum(amount) && amount > 0 ? amount : null;
  row("floor", "Falls", isNum(W.floor), isNum(W.floor) ? `No more than ${f.share(-W.floor)} from any high` : null);
  row("capacity", "Can lose", cap !== null, cap !== null ? `${f.money(cap)}${amt !== null && cap < amt ? `, staying above ${f.money(amt - cap)}` : ""}` : null);
  row("scenario_stress", "One shock", isNum(W.scenario_stress), isNum(W.scenario_stress) ? `No more than ${f.pct(Math.abs(W.scenario_stress))}` : null);
  row("single_stock", "One company", isNum(W.single_stock), isNum(W.single_stock) ? capOf(W.single_stock) : null);
  row("sector", "One industry", isNum(W.sector), isNum(W.sector) ? capOf(W.sector) : null);
  for (const [k, v] of Object.entries(obj(W.sector_caps) || {})) if (isNum(v)) {
    const s0 = tagOf(`sector_caps.${k}`, true);
    rows.push({ key: `sector_caps.${k}`, label: k, value: capOf(v), source: s0, tag: SOURCE_TAG[s0], say: SOURCE_SAY[s0], words: str(said[`sector_caps.${k}`]), assumed: null, conflict: null });
  }
  row("crypto", "Crypto", isNum(W.crypto), isNum(W.crypto) ? capOf(W.crypto) : null);
  const hz = isNum(inn.horizon_years) ? inn.horizon_years : isNum(inn.horizon) ? inn.horizon : null;
  if (hz !== null) {
    const s0 = SOURCE_TAG[src.horizon_years] ? src.horizon_years : SOURCE_TAG[src.horizon] ? src.horizon : "words";
    rows.push({ key: "horizon", label: "Horizon", value: f.years(hz), source: s0, tag: SOURCE_TAG[s0], say: SOURCE_SAY[s0], words: str(said.horizon_years) || str(said.horizon), assumed: null, conflict: null });
  }
  if (typeof inn.esg === "boolean") {
    const s0 = tagOf("esg", true);
    rows.push({ key: "values", label: "Values screen", value: inn.esg ? "On" : "Off", source: s0, tag: SOURCE_TAG[s0], say: SOURCE_SAY[s0], words: str(said.esg), assumed: null, conflict: null });
  }
  const you = rows.filter((x) => x.source === "you").length, words = rows.filter((x) => x.source === "words").length, assumed = rows.length - you - words;
  const parts = [you ? `${you} set by you` : null, words ? `${words} from your words` : null, assumed ? `${assumed} assumed from the profile` : null].filter(Boolean);
  return { rows, none: false, conflicts: [], precedence: PRECEDENCE, plan: true, summary: `${rows.length} limits: ${listWords(parts)}.` };
}

/* ---- limit words in a persona's question (limits-QA case 5): the four personas' limits come from their profiles, never from the
   question's words; when the question states a limit anyway, one line says where such words work, so they are never ignored
   silently. Only explicit limit statements count (a dollar loss, "no more than N %", "no crypto", "I don't care about ESG"…). ---- */
const LIMIT_WORDS = [
  /\b(could|can|can't|cannot|won't|will not)\s+(afford\s+to\s+)?lose\b/i,
  /\b(no more than|at most|max(imum)?|up to)\s+\$?\d/i,
  /\b(don't|do not|doesn't|does not|never)\s+(care|mind)\s+about\s+(esg|values|ethic)/i,
  /\bno\s+(crypto|bitcoin|oil|tobacco|weapons|limits?)\b/i,
  /\b(exclude|excluding|avoid|avoiding|without)\s+(crypto|bitcoin|oil|energy|tech|tobacco|weapons)\b/i,
  /\b(my|a|the)\s+(loss\s+)?limits?\b/i,
];
export function limitWordsLine(r) {
  r = obj(r);
  if (!r || r.pilot === YOU || STOP.has(str(r.status) || "")) return null;
  const q = str(r.question);
  if (!q || !LIMIT_WORDS.some((re) => re.test(q))) return null;
  const who = whoOf(r) || "this portfolio";
  return { segs: [["Limits in your own words work under You. "], [`${who === "this portfolio" ? "This portfolio’s" : `${who}’s`} limits are the profile’s, in the line above.`]],
    text: `Limits in your own words work under You. ${who === "this portfolio" ? "This portfolio’s" : `${who}’s`} limits are the profile’s, in the line above.` };
}

/* the limits the You card's plan always carries when its words set them (limitsIn's limits object and capacity); the values
   screen and the horizon live elsewhere on the You card, so a run's words for them never make the run stale on their own */
const PLAN_KEYS = /^(capacity|floor|scenario_stress|single_stock|sector|crypto|sector_caps\..+)$/;
/* does the You card's plan still carry a limit the run read from the words (a key of result.limits.from_words)? */
function planHas(inn, key) {
  const W = obj(inn.limits) || {}, src = obj(inn.source) || {};
  if (key === "capacity") return isNum(inn.capacity);
  if (key === "esg") return typeof inn.esg === "boolean";
  if (key.startsWith("sector_caps.")) return isNum((obj(W.sector_caps) || {})[key.slice(12)]);
  if (key === "horizon_years") return !!(src.horizon_years || src.horizon);
  return isNum(W[key]) || !!src[key];
}
