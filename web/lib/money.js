/* EPICENTRE Replay, lane U5: the pure models behind #money (where the money and the risk sat) and #checklist (the checks,
   the most serious first). No DOM, no network. PF (web/lib.js) is passed in, else read from globalThis at call time.
   Every number is a Result value printed by PF.fmt; nothing here computes a check, a status, a verdict or a new number
   (one judge, red gate 2): the page only chooses which Result values to show and how to word them. A missing key gives
   null and the section hides that part (never an invented number). Tests: tests/web_u5_test.mjs. */

import { shownStatus, STATUS_LEGEND, floorClass, floorWord, bindingWord } from "./status.js";
import { capsOf, capFacts, capsFromRows, sameCaps, wordsAfter, sourceOf } from "./sectorcaps.js";

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const same = (a, b) => isNum(a) && isNum(b) && Math.abs(a - b) < 1e-9;
const pfOf = (P) => P || globalThis.PF || null;
const MINUS = "−";
const PERSONAS = new Set(["robert", "mateo", "amira", "canadian"]);
/* G4 (traceability C08): the check that answers a persona's own stated test, always in view. Amira (official case, persona 01):
   "does not want to invest exclusively in technology": her one-sector limit */
export const PERSONA_TEST = Object.freeze({ amira: Object.freeze({ rule: "sector", words: "Your own test: not only tech" }) });
const WORDS = { 2: "two", 3: "three", 4: "four", 5: "five" };
const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const bare = (t) => String(t || "").replace(MINUS, "");                 // "−15 %" -> "15 %": a fall named by its size
export const oneDecimal = (x) => (isNum(x) ? x.toLocaleString("en-CA", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : "");

/* "in this 2021–26 replay" (ruling R1): the years come from the Result's own dates, never typed */
export function replayPhrase(result) {
  const r = obj(result) || {}, dates = arr(obj(r.series) && r.series.dates);
  const year = (d) => (typeof d === "string" && /^\d{4}/.test(d) ? d.slice(0, 4) : null);
  const y0 = year(dates[0]), y1 = year(str(r.as_of) || dates[dates.length - 1]);
  if (!y0 || !y1) return "in this replay";
  return y0 === y1 ? `in this ${y0} replay` : `in this ${y0}–${y1.slice(0, 2) === y0.slice(0, 2) ? y1.slice(2) : y1} replay`;
}

/* whose money: a first name gives "Robert’s"; a case title ("Too Canadian?") is not a name. persona = a fictional profile */
export function whoOf(result, view) {
  const r = obj(result) || {}, who = obj(obj(view) && view.who) || {};
  const name = str(who.name), plain = name && /^[A-Z][A-Za-z’'-]*$/.test(name) ? name : null;
  const limits = obj(r.limits) || {};
  return { name: plain, poss: plain ? `${plain}’s` : null, persona: PERSONAS.has(str(r.pilot)) && !arr(limits.edited).length };
}

/* ruling R13: persona limits are assumptions ("assumed for this fictional profile", with the edit mark); the user's are typed.
   Ruling R18: one voice, the second person in every instrument string ("your floor", "your $600,000"), never the name. */
export function limitsNote(result, view) {
  const w = whoOf(result, view);
  if (w.persona) return { text: "Your limits are assumed for this fictional profile.", edit: true };
  return { text: "Your limits, as you typed them.", edit: false };
}

/* a ticker's display name from PF's own map (PF.nameOf when it exists, else PF.moveOf asked about a one-line mix) */
export function nameOf(ticker, P) {
  P = pfOf(P);
  if (!str(ticker) || !P) return ticker;
  if (typeof P.nameOf === "function") return P.nameOf(ticker) || ticker;
  const m = typeof P.moveOf === "function" ? P.moveOf({ question_type: "change", portfolio: { [ticker]: 1 }, baseline: { portfolio: {} }, tipping_point: { ticker } }) : null;
  return (m && m.name) || ticker;
}

/* the facts row behind a number shown (so a click can open its thread): same value, and a label that names it */
export function factFor(result, value, words) {
  const facts = obj(obj(result) && result.facts);
  if (!facts || !isNum(value) || !arr(words).length) return null;
  for (const [id, f] of Object.entries(facts)) {
    if (!obj(f) || !same(f.value, value)) continue;
    const label = String(f.label || "").toLowerCase();
    if (words.some((w) => label.includes(w))) return id;
  }
  return null;
}

/* the dial moved away from the asked size: these sections stay on the asked size and say so */
export function dialNote(result, view, weightIndex, P) {
  P = pfOf(P);
  const r = obj(result) || {}, move = obj(obj(view) && view.move), curve = arr(obj(r.tipping_point) && r.tipping_point.curve);
  if (!P || !move || !Number.isInteger(weightIndex) || !obj(curve[weightIndex]) || !isNum(curve[weightIndex].weight)) return null;
  const w = curve[weightIndex].weight;
  if (same(w, move.weight)) return null;
  return `Shown for the size asked, ${move.name} at ${move.weightText}. The dial above is at ${P.fmt.share(w)}.`;
}

/* ---- #money: where the money and the risk sat ---- */

/* the bar segments of a mix: the subject first, then the other lines by their share of the money (both bars, one order, so
   the risk bar can morph from the money bar). A share the Result does not give stays null (the bar leaves it out). */
function segments(weights, shares, subject) {
  const keys = Object.keys(weights).filter((k) => isNum(weights[k]) && weights[k] > 0)
    .sort((a, b) => (a === subject ? -1 : b === subject ? 1 : weights[b] - weights[a] || (a < b ? -1 : 1)));
  return keys.map((k) => ({ key: k, money: weights[k], risk: isNum(shares[k]) ? shares[k] : null, subject: k === subject }));
}

function checkOf(r, rule) { return arr(r.checks).map(obj).find((c) => c && c.rule === rule) || null; }

/* the limit drawn on a bar: only when that check measured exactly the number the bar shows (same holding, same value) */
function tickOf(r, rule, holding, value, label, P) {
  const c = checkOf(r, rule);
  if (!c || c.holding !== holding || !same(c.value, value) || !isNum(c.limit)) return null;
  return { v: c.limit, text: P.fmt.share(c.limit), label, status: str(c.status) };
}

function pairOf(kind, r, v, P) {
  const f = P.fmt, move = obj(v.move), risk = obj(r.risk) || {}, div = obj(r.diversification) || {};
  const shares = (side) => obj(obj(risk[side]) && risk[side].shares) || {};
  const weights = obj(r.portfolio) || {};
  if (kind === "canada") {
    const t = obj(div.today) || {}, a = obj(div.after) || {}, ct = obj(t.countries) || {}, ca = obj(a.countries) || {};
    if (!isNum(ca.CAN) || !isNum(a.can_risk_share)) return null;
    const side = (x, was) => ({ v: x, text: f.pct(x), was: isNum(was) ? { v: was, text: f.pct(was) } : null });
    return { kind, subject: "Canada", money: { ...side(ca.CAN, ct.CAN), label: "of your money was in Canada" },
      risk: { ...side(a.can_risk_share, t.can_risk_share), label: "of the risk came from Canada" }, segments: null, moneyTick: null, riskTick: null };
  }
  const side = kind === "move" ? "after" : "today", sh = shares(side);
  let tk = kind === "move" ? move.ticker : null;
  if (!tk) tk = Object.keys(sh).filter((k) => isNum(sh[k])).sort((a, b) => sh[b] - sh[a])[0] || null;   // the line that carried most risk
  if (!tk || !isNum(weights[tk]) || !isNum(sh[tk])) return null;
  const name = kind === "move" ? move.name : nameOf(tk, P);
  return { kind, subject: name, ticker: tk,
    money: { v: weights[tk], text: f.share(weights[tk]), was: null, label: `of your money was in ${name}`,
      fact: kind === "move" ? factFor(r, weights[tk], ["the move"]) : null },
    risk: { v: sh[tk], text: f.pct(sh[tk]), was: null, label: `of the risk came from ${name}`, fact: factFor(r, sh[tk], ["share of the risk"]) },
    segments: segments(weights, sh, tk),
    moneyTick: tickOf(r, "single_stock", tk, weights[tk], "One-company limit", P),
    riskTick: tickOf(r, "risk_concentration", tk, sh[tk], "Warning level", P) };
}

/* the row under the pair: today → with the move (today only without a move) */
function statsOf(kind, r, v, P) {
  const f = P.fmt, move = obj(v.move), risk = obj(r.risk) || {}, div = obj(r.diversification) || {};
  const rt = obj(risk.today) || {}, ra = kind === "mix" ? {} : obj(risk.after) || {};
  const dt = obj(div.today) || {}, da = kind === "mix" ? {} : obj(div.after) || {};
  const val = (x, text, words) => (isNum(x) ? { v: x, text, fact: factFor(r, x, words) } : null);
  const stat = (id, label, note, t, a) => (t || a ? { id, label, note, today: t, after: kind === "mix" ? null : a } : null);
  const can = (d) => obj(d.countries) || {};
  const out = [stat("bets", "Independent bets", "How many separate bets the mix behaved like.",
    val(rt.bets, oneDecimal(rt.bets), ["independent bets"]), val(ra.bets, oneDecimal(ra.bets), ["independent bets"]))];
  if (kind === "canada") {
    const sa = obj(ra.shares) || {};
    out.push(stat("move-money", `${move.name}’s share of your money`, "The move, as asked.", null, val(move.weight, f.share(move.weight), ["the move"])));
    out.push(stat("move-risk", `${move.name}’s share of the risk`, null, null, val(sa[move.ticker], f.pct(sa[move.ticker]), ["share of the risk"])));
  } else {
    out.push(stat("can-money", "Canada’s share of your money", null, val(can(dt).CAN, f.pct(can(dt).CAN)), val(can(da).CAN, f.pct(can(da).CAN))));
    out.push(stat("can-risk", "Canada’s share of the risk", null, val(dt.can_risk_share, f.pct(dt.can_risk_share)),
      val(da.can_risk_share, f.pct(da.can_risk_share))));
  }
  return out.filter((s) => s && (s.after || s.today));
}

/* "Leave 2022 out": result.not_2022, the worst fall on the dates from 2023 on (lane B3), in the investor's own floor terms */
/* R35: a fall in the path's own dollars (breaches[i] {peak_value, trough_value, fall_dollars}, lane fin-backend), matched by its
   peak date; null without them (the page then names no dollar figure for the fall) */
function pathOf(r, peakDate, f) {
  const b = arr(r.breaches).map(obj).find((x) => x && str(x.peak_date) === str(peakDate));
  if (!b || !isNum(b.peak_value) || !isNum(b.trough_value)) return null;
  const fall = isNum(b.fall_dollars) ? b.fall_dollars : null;
  return { from: f.money(b.peak_value), to: f.money(b.trough_value), fall: fall === null ? null : f.money(fall) };
}
export function breachPath(result, peakDate, P) { P = pfOf(P); return P ? pathOf(obj(result) || {}, peakDate, P.fmt) : null; }

function not2022Of(r, v, P) {
  const n = obj(r.not_2022), f = P.fmt;
  if (!n || !isNum(n.depth) || !str(n.peak_date) || !str(n.trough_date)) return null;
  const moved = n.side === "after" && !!obj(v.move);
  const floor = isNum(n.floor) ? n.floor : obj(v.floor) && v.floor.v;
  const beyond = typeof n.beyond_floor === "boolean" ? n.beyond_floor : null;
  return { side: n.side, moved, depth: n.depth, depthText: f.pct(n.depth), fallText: bare(f.pct(n.depth)),
    from: /^\d{4}-01-01/.test(String(n.from)) ? String(n.from).slice(0, 4) : f.date(n.from), peak: f.date(n.peak_date), trough: f.date(n.trough_date), back: str(n.recovery_date) ? f.date(n.recovery_date) : null,
    dollars: isNum(n.loss_dollars) ? n.loss_dollars : null, dollarsText: isNum(n.loss_dollars) ? f.money(n.loss_dollars) : null,
    path: pathOf(r, n.peak_date, f),
    amountText: isNum(n.amount) ? f.money(n.amount) : null, floorText: isNum(floor) ? bare(f.share(floor)) : null, beyond,
    status: beyond === true ? { word: "Past the floor", tone: "outside", icon: "i-out" }
      : beyond === false ? { word: "Inside the floor", tone: "inside", icon: "i-in" } : null,
    facts: { depth: factFor(r, n.depth, ["2023"]), dollars: factFor(r, n.loss_dollars, ["2023"]) } };
}

/* ruling R11: the same move weight in the broad market, in QQQ and in the moved ticker (result.ladder, judged by the engine).
   The bank juror's ruling: a bet nobody asked about never carries a verdict or an end value (a pass mark on an alternative
   reads as a recommendation); every row keeps its fall against the floor in neutral words (web/lib/status.js). Only today's
   mix and the move asked keep their verdict and end value. */
function ladderOf(r, v, P) {
  const L = obj(r.ladder), f = P.fmt, move = obj(v.move);
  if (!L || !isNum(L.weight)) return null;
  const rows = arr(L.rows).map(obj).filter((x) => x && str(x.ticker) && !x.error && isNum(x.max_drawdown)).map((x) => {
    const verdict = obj(P.VERDICT) && obj(P.VERDICT[x.verdict]) ? { key: x.verdict, ...P.VERDICT[x.verdict] } : null;
    const name = cap(str(x.label)) || (x.is_move && move && move.ticker === x.ticker ? move.name : null) || str(x.name) || x.ticker;
    const judged = x.is_move === true, beyond = typeof x.beyond_floor === "boolean" ? x.beyond_floor : null;
    return { ticker: x.ticker, name, isMove: judged, dd: x.max_drawdown, ddText: f.pct(x.max_drawdown),
      dollarsText: isNum(x.loss_dollars) ? f.money(x.loss_dollars) : null, endText: judged && isNum(x.end_value) ? f.money(x.end_value) : null,
      beyond, verdict: judged ? verdict : null, judged };
  });
  if (rows.length < 2) return null;
  const zero = arr(obj(r.tipping_point) && r.tipping_point.curve).map(obj).find((c) => c && c.weight === 0 && isNum(c.max_drawdown));
  const baseFloor = arr(obj(r.baseline) && r.baseline.checks).map(obj).find((c) => c && c.rule === "max_drawdown");   // today's own floor check
  const today = zero ? { ticker: null, name: "Today\u2019s mix", note: "without the move", isToday: true, isMove: false, judged: true, dd: zero.max_drawdown,
    ddText: f.pct(zero.max_drawdown), dollarsText: isNum(zero.loss_dollars) ? f.money(zero.loss_dollars) : null,
    endText: isNum(zero.end_value) ? f.money(zero.end_value) : null,
    beyond: baseFloor && same(baseFloor.value, zero.max_drawdown) ? (baseFloor.status === "fail" ? true : baseFloor.status === "pass" ? false : null) : null,
    verdict: obj(P.VERDICT) && obj(P.VERDICT[zero.verdict]) ? { key: zero.verdict, ...P.VERDICT[zero.verdict] } : null } : null;
  const floor = obj(v.floor) && isNum(v.floor.v) ? v.floor.v : null;
  const all = today ? [today, ...rows] : rows;
  for (const x of all) x.floorWord = floorWord(floorClass(x.dd, floor, x.beyond));
  const scale = 1.08 * Math.max(...all.map((x) => Math.abs(x.dd)), floor === null ? 0 : Math.abs(floor));   // a little room past the deepest
  return { weightText: f.share(L.weight), count: rows.length, countWord: WORDS[rows.length] || String(rows.length), rows, today,
    amountText: isNum(L.amount) ? f.money(L.amount) : obj(v) && v.amountText, floor: floor === null ? null : { v: floor, text: f.share(floor) },
    scale: scale > 0 ? scale : 1 };
}

/* ruling R19(b), "Too Canadian?": the workshop's XSP question, from result.hedge_compare (lane B3): your mix after the move
   twice, unhedged (SPY in Canadian dollars, the engine's own path: a fact) and with SPY's line on its US-dollar returns (a
   CAD-hedged stand-in, the way XSP is built: an assumption), each {worst_fall, worst_2022, end_value, kind}; spy_2022 {usd,
   cad, currency_effect_pp} gives the sentence; method is the code's own note. Hidden when absent or half there. */
function hedgeOf(r, P) {
  const H = obj(r.hedge_compare), f = P.fmt;
  if (!H) return null;
  const tk = str(H.ticker) || "SPY";
  const side = (x, kind, words) => {
    x = obj(x);
    if (!x || !isNum(x.worst_fall)) return null;
    const fact = (v) => factFor(r, v, words);
    return { kind: str(x.kind) || kind, dd: x.worst_fall, ddText: f.pct(x.worst_fall), ddFact: fact(x.worst_fall),
      y2022Text: isNum(x.worst_2022) ? f.pct(x.worst_2022) : null, y2022Fact: isNum(x.worst_2022) ? fact(x.worst_2022) : null,
      endText: isNum(x.end_value) ? f.money(x.end_value) : null, endFact: isNum(x.end_value) ? fact(x.end_value) : null };
  };
  const a = side(H.unhedged, "fact", ["unhedged"]), b = side(H.hedged_standin || H.hedged, "assumption", ["hedged stand-in"]);
  if (!a || !b) return null;
  const y = obj(H.spy_2022) || {}, pp = isNum(y.currency_effect_pp) ? y.currency_effect_pp : null;
  const sentence = isNum(y.usd) && isNum(y.cad)
    ? { usd: f.pct(y.usd), usdFact: factFor(r, y.usd, ["2022 return in us dollars"]), cad: f.pct(y.cad), cadFact: factFor(r, y.cad, ["2022 return in canadian dollars"]),
      pp: pp === null || pp === 0 ? null : oneDecimal(Math.abs(pp)), softened: pp !== null && pp > 0 }
    : null;
  /* ruling R16: the page draws the kind marks as SVG symbols; a mark written into the code's prose is dropped there */
  const method = str(H.method) ? H.method.replace(/[\u25CF\u25D0\u25CB]\s?/g, "") : null;
  return { ticker: tk, weightText: isNum(H.weight) ? f.share(H.weight) : null, unhedged: a, hedged: b, sentence, method };
}

export function moneyModel(result, view, P) {
  P = pfOf(P);
  const r = obj(result), v = obj(view);
  if (!r || !v || !P || !P.fmt || v.stop) return null;
  const move = obj(v.move);
  const canadaAsk = r.pilot === "canadian" || /\bcanad/i.test(str(obj(r.scenario) && r.scenario.intent) || "");
  let kind = move ? (canadaAsk ? "canada" : "move") : "mix";
  let pair = pairOf(kind, r, v, P);
  if (!pair && kind === "canada") { kind = "move"; pair = pairOf(kind, r, v, P); }
  const phrase = replayPhrase(r), who = whoOf(r, v);
  const stats = statsOf(kind, r, v, P), not2022 = not2022Of(r, v, P), ladder = ladderOf(r, v, P);
  const hedge = kind === "canada" ? hedgeOf(r, P) : null;
  const values = priceOfValuesOf(r, P);
  if (!pair && !stats.length && !not2022 && !ladder && !values) return null;
  const floor = obj(v.floor);
  const floorNote = floor && isNum(floor.v)
    ? `Your floor, a ${bare(P.fmt.share(floor.v))} fall from any high, ${who.persona ? "is assumed for this fictional profile." : "is the one you typed."}`
    : null;
  return { kind, who, phrase, move: move ? { ticker: move.ticker, name: move.name, weightText: move.weightText } : null,
    lede: move ? `With the move, ${phrase}` : cap(phrase), pair, stats, hedge, values, not2022, ladder,
    notes: { floor: floorNote, edit: who.persona, history: "This already happened; it is not a forecast.",
      fiction: move || ladder || values ? "Fictional illustration, not a recommendation." : null } };
}

/* ---- #checklist: the checks, the most serious first ---- */

/* a row's colour says what it did to the verdict: web/lib/status.js, the page's one vocabulary (re-exported for this lane's tests) */
export { shownStatus };

/* a code-written reason as the page prints it: ISO dates as "29 Nov 2021", a shock's id as its title; the evidence note that
   closes the shock check's reason ("(Indicative (mixed with …))") is lifted out and returned on its own */
export function readReason(text, check, result, P) {
  P = pfOf(P);
  let t = str(text);
  if (!t || !P) return { reason: t, evidence: null };
  const titles = new Map(arr(obj(result) && result.events).map(obj).filter((e) => e && str(e.event_id) && str(e.title))
    .map((e) => [e.event_id, e.title + (P.fmt.date(e.date) ? ` (${P.fmt.date(e.date)})` : "")]));
  const words = (s) => s.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (id) => titles.get(id) || id)
    .replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (d) => P.fmt.date(d) || d);
  let evidence = str(obj(check) && check.evidence);
  if (evidence && t.includes(`(${evidence})`)) t = t.replace(` (${evidence})`, "").replace(`(${evidence})`, "");
  else evidence = null;
  const curly = (x) => x.replace(/(\w)'(\w)/g, "$1\u2019$2");                                       // ruling R18: typographic apostrophes
  if (evidence) evidence = curly(words(evidence).replace(/^(\w+) \((.*)\)$/, (_, a, b) => `${a.toLowerCase()}, ${b}`));
  /* pre-freeze 5: "mixed with X, <date>" read as if the date were the asked episode's; the date belongs to the other shock */
  const mix = evidence && /^(\w+)(?::|,)?\s*\(?mixed with (.+?)(?:,\s*|\s*\()([^()]*\d{4})\)?\)?$/.exec(evidence);
  if (mix) evidence = `${mix[1].toLowerCase()}, because one of these episodes overlapped another shock: ${mix[2]}, on ${mix[3]}`;
  return { reason: curly(words(t).replace(/\s+\./g, ".").replace(/\.\.$/, ".")), evidence };
}

/* the facts rows behind a check's value and limit: the words each row's label uses (the receipt's facts, lane B), so a click
   opens the right thread; a value no facts row names stays plain text */
const RULE_FACTS = {
  max_drawdown: [["worst drop after the move", "worst drop today"], ["your floor"]],
  scenario_stress: [["shock"], ["shock limit"]],
  single_stock: [["single-company"], ["one-company limit"]],
  sector: [["sector share"], ["one-sector limit"]],
  crypto: [["crypto share"], ["crypto limit"]],
  esg_direct: [["against your values"], ["values limit"]],
  esg_indirect: [["inside your funds against"], ["values warning level"]],
  risk_concentration: [["share of the risk"], ["risk-share warning level"]],
  recovery: [["recover"], ["recovery days"]],
  short_horizon: [["your horizon"], ["short-horizon level"]],
};

const SOURCE_TAG = { you: "set by you", words: "from your words", assumed: "assumed" };     // lane hold's card says the same
/* a row's source: the engine's own (checks[].source, since 7c28484), else, for a run saved before it, the page's one rule on the
   limit the row checks (limits-QA 17:30: the main demo's rows read "assumed"); missing_data checks no limit (null) */
const RULE_KEY = { max_drawdown: "floor", scenario_stress: "scenario_stress", single_stock: "single_stock", sector: "sector", crypto: "crypto",
  esg_direct: "esg", esg_indirect: "esg", risk_concentration: "risk_share", recovery: "recovery_days", short_horizon: "short_horizon_years" };
function rowSource(c, r) {
  if (SOURCE_TAG[c && c.source]) return c.source;
  const rule = String((c && c.rule) || ""), key = rule.startsWith("sector_cap:") ? `sector_caps.${rule.slice(11)}` : RULE_KEY[rule];
  return key ? sourceOf(obj(r) && r.limits, key) : null;
}
export function checksModel(result, view, P) {
  P = pfOf(P);
  const r = obj(result), v = obj(view);
  if (!r || !v || !P || v.stop) return null;
  const raw = new Map(arr(r.checks).map(obj).filter((c) => c && str(c.rule)).map((c) => [c.rule, c]));
  const SEP = " against your limit ";
  const rows = arr(v.rows).filter((x) => x && raw.has(x.rule)).map((x) => {
    const c = raw.get(x.rule), shown = shownStatus(c.status, c.tier) || { word: x.word, tone: x.tone, icon: x.icon };
    const cmp = str(x.compare), cut = cmp ? cmp.indexOf(SEP) : -1;
    const who = (x.rule === "esg_direct" || x.rule === "risk_concentration") && str(c.holding) ? nameOf(c.holding, P) + " " : "";
    const { reason, evidence } = readReason(x.reason, c, r, P);
    return { rule: x.rule, name: x.name, status: c.status, tier: str(c.tier), tierText: x.tier, ...shown, hard: c.tier === "hard",
      value: cmp ? who + (cut >= 0 ? cmp.slice(0, cut) : cmp) : null, limit: cut >= 0 ? cmp.slice(cut + SEP.length) : null, reason, evidence,
      valueFact: (RULE_FACTS[x.rule] || capFacts(x.rule)) ? factFor(r, c.value, (RULE_FACTS[x.rule] || capFacts(x.rule))[0]) : null,
      limitFact: (RULE_FACTS[x.rule] || capFacts(x.rule)) ? factFor(r, c.limit, (RULE_FACTS[x.rule] || capFacts(x.rule))[1]) : null,
      same: str(c.same_cause_as), asked: x.rule === "scenario_stress" && str(c.family) ? c.family : null, decided: false,
      /* LIMITS_MODEL 16:40: each row says where its limit came from (the engine's own tag, governance.limit_source) */
      src: rowSource(c, r), srcText: SOURCE_TAG[rowSource(c, r)] || null };
  });
  if (!rows.length) return null;
  for (const x of rows) if (x.same) { const o = rows.find((y) => y.rule === x.same); x.same = o ? o.name : null; }
  /* R35: the floor row is the 15 % rule (tolerance), in percent only: never "$90,000 set as your limit" for it; the shock limit is
     a rule of thumb, half that rule */
  const R15 = ruleText(r, P);
  for (const x of rows) {
    if (x.rule === "max_drawdown") { x.value = pctOf(x.value); x.limit = pctOf(x.limit); if (R15) x.ruleWords = `Tolerance: ${R15.words}`; }
    if (x.rule === "scenario_stress" && R15) x.ruleWords = `Its limit is a rule of thumb: half your ${R15.pct} floor`;   // one name (controller, 17:20)
  }
  /* the row that decided it: code's check_order puts it first; a rechecked run has no new order, so it is found by the same
     rule governance.check_order writes (the first broken hard limit, else the first broken limit, else the first warning) */
  const order = arr(obj(r.scenario) && r.scenario.check_order);
  const first = r.rechecked
    ? rows.find((x) => x.status === "fail" && x.hard) || rows.find((x) => x.status === "fail") || rows.find((x) => x.status === "warn")
    : rows.find((x) => x.rule === order[0]);
  const binding = (r.verdict === "Incompatible" || r.verdict === "Tension") && first && first.status !== "pass" ? first : null;
  if (binding) { binding.decided = true; binding.decidedWord = bindingWord(binding.status, binding.tier); }
  const families = arr(obj(r.scenario) && r.scenario.families);
  const asked = families.length ? rows.find((x) => x.rule === "scenario_stress") : null;
  let visible = rows.slice(0, 3);
  if (asked && !visible.includes(asked)) visible = [...visible.slice(0, 2), asked];
  const test = PERSONA_TEST[str(r.pilot)] || null, own = test ? rows.find((x) => x.rule === test.rule) : null;
  if (own && !visible.includes(own)) {
    const out = visible.slice().reverse().find((x) => !x.decided && x !== asked && x !== binding);
    if (out) visible = visible.map((x) => (x === out ? own : x));
    own.own = test.words;
  }
  const phrase = replayPhrase(r);
  const verdict = obj(P.VERDICT) && obj(P.VERDICT[r.verdict]) ? { key: r.verdict, ...P.VERDICT[r.verdict] } : null;
  const change = sensitivityOf(r, P), floorRow = rows.find((x) => x.rule === "max_drawdown");
  if (floorRow) floorRow.change = change;
  return { rows, visible, count: rows.length, more: rows.length > visible.length, binding, verdict, phrase,
    title: binding && binding.decidedWord ? `${binding.name} ${binding.decidedWord.charAt(0).toLowerCase()}${binding.decidedWord.slice(1)}.`
      : r.verdict === "Compatible" ? "No limit broke." : "The checks.",
    sub: `${rows.length} checks, the most serious first.`, limits: limitsNote(r, v),
    legend: STATUS_LEGEND,
    history: "This already happened; it is not a forecast.",
    unmeasured: "Not measured here: credit risk inside the bond funds and how easily each holding could be sold; every holding trades daily on an exchange, crypto around the clock." };
}

/* ---- audit fixes (11:20): your limits (the workshop's "tolerance is not capacity"), a recheck with limits you type, the
   floor's sensitivity ("change a hypothesis"), the price of your values ---- */

/* your limits as rows: PF.youRows' objective, horizon, capacity and floor (with its source), then each limit from result.limits */
export function limitsBlock(result, view, mode, P) {
  P = pfOf(P);
  const r = obj(result), v = obj(view);
  if (!r || !v || !P || typeof P.youRows !== "function" || v.stop) return null;
  const f = P.fmt, L = obj(r.limits) || {}, edited = arr(L.edited), you = arr(P.youRows(r));
  const pick = (label) => you.find((x) => x && x.label === label) || null;
  /* where each limit came from (limits-QA 17:12): the engine's own tag on the row that checks it (governance.limit_source), else
     the one rule (from your words > set by you > assumed); limits your words set are in `edited` too, so never edited alone */
  const ROW_OF = { floor: "max_drawdown", floor_pct: "max_drawdown", single_stock: "single_stock", sector: "sector", crypto: "crypto" };
  const srcOf = (key) => {
    if (key === "floor" && arr(L.from_words).includes("capacity")) return "words";      // the capacity row: its own source first
    if (key === "floor" && arr(L.edited).includes("capacity")) return "you";
    const c = ROW_OF[key] ? arr(r.checks).map(obj).find((x) => x && x.rule === ROW_OF[key]) : null;
    if (c && SOURCE_TAG[c.source]) return c.source;
    return ROW_OF[key] ? sourceOf(L, key === "floor_pct" ? "floor" : key) : null;
  };
  const rows = [], add = (key, label, value, note) => {
    if (!value) return;
    const src = srcOf(key);
    rows.push({ key, label, value, note: note || null, typed: src === "you", tag: src === "words" ? "from your words" : null });
  };
  const obj1 = pick("Objective"), hz = pick("When you need the money"), cap = pick("The most you could lose"), fl = pick("Your floor");
  add("goal", "Objective", obj1 && obj1.value);
  add("horizon", "When you need the money", hz && hz.value);
  /* R35: the two limits by their workshop names: capacity (what you can afford to lose) and tolerance (the 15 % rule) */
  const C = obj(r.capacity), line = C && obj(C.today) && isNum(C.today.line) ? C.today.line : null;
  add("floor", "What you can afford to lose", cap && cap.value ? `${cap.value}${line !== null ? `: stay above ${f.money(line)}` : ""}` : null);
  const R15 = ruleText(r, P);
  add("floor_pct", "Your floor", R15 ? `No fall of more than ${R15.pct} from a high` : fl && fl.value);   // one name, defined here once
  add("single_stock", "One company", isNum(L.single_stock) ? `Up to ${f.share(L.single_stock)}` : null);
  add("sector", "One sector", isNum(L.sector) ? `Up to ${f.share(L.sector)}` : null);
  const caps = capsOf(r);              /* lane sector-limits: the industries you limited, each with where it came from */
  for (const c of caps) rows.push({ key: c.key, label: c.sector, value: c.excluded ? "Excluded (0\u00a0%)" : `Up to ${f.share(c.share)}`, note: null,
    typed: c.source === "you", tag: c.source === "words" ? "from your words" : null });
  add("crypto", "Crypto", isNum(L.crypto) ? (L.crypto === 0 ? "Excluded (0\u00a0%)" : `Up to ${f.share(L.crypto)}`) : null);
  const vals = pick("Values"), esg = obj(r.profile) ? r.profile.esg : undefined;      /* LIMITS_MODEL: the screen reads On or Off */
  add("esg", "Values", esg === true ? "On" : esg === false ? "Off" : vals && vals.value);
  if (!rows.length) return null;
  const floorSrc = srcOf("floor_pct"), typedFloor = floorSrc === "you";
  const floorNote = floorSrc === "words" ? "From your words; this check uses it." : typedFloor ? "Set by you; this check uses it."
    : R15 ? `Your tolerance, assumed from the profile, not set by you. What you can afford to lose is the other limit, in dollars.` : (fl && str(fl.note)) || null;
  const w = whoOf(r, v), amount = isNum(r.amount) && r.amount > 0 ? r.amount : null;
  const capacity = [obj(r.profile) && r.profile.capacity, L.capacity_dollars].find(isNum);
  const live = mode === "live" && !!str(r.run_id) && amount !== null;
  return { rows, floorNote, persona: w.persona, edited,
    note: limitsLine(r, v).text,
    edit: { live, why: live ? null : "Editing your limits needs the live app.", amount, amountText: amount === null ? null : f.money(amount),
      capacity: isNum(capacity) ? Math.round(capacity) : null, single: isNum(L.single_stock) ? Math.round(L.single_stock * 1000) / 10 : null,
      caps: caps.map((c) => ({ sector: c.sector, pct: c.pct, source: c.source })) } };
}

const KEPT = ["floor", "single_stock", "sector", "crypto", "scenario_stress", "recovery_days", "risk_share"];   // governance.OVERRIDE_KEYS
/* lane sector-limits (LIMITS_MODEL 16:40, "NO LIMITS is valid"): a live run judged with no limits ({none: true}: no checks, no
   verdict) still offers the editor, so "+ Add a limit" (lane hold's card) has somewhere to go; only when the answers have a risk
   band, since without one the server checks no limit at all. Null otherwise (a run with checks shows them as before). */
export function noLimitsBlock(result, view, mode, P) {
  const r = obj(result), v = obj(view), p = obj(r && r.profile) || {};
  if (!r || !v || v.stop || r.verdict !== null || r.limits !== null || arr(r.checks).length || !(str(p.risk) || str(p.reaction_2022))) return null;
  const Y = limitsBlock(r, v, mode, P);
  return Y && Y.edit.live ? { question: "Your limits", answer: "No limits set. The replay above shows everything; add a limit to check the move against it.", Y } : null;
}

/* the body of POST /api/recheck {run_id, limits} from what you typed (dollars you could lose, a one-company share in %):
   the floor is that loss over the amount (the one place the page turns your own input into a limit); {error} in plain words */
export function recheckBody(result, typed) {
  const r = obj(result) || {}, t = obj(typed) || {}, limits = {};
  const amount = isNum(r.amount) && r.amount > 0 ? r.amount : null;
  if (!str(r.run_id) || amount === null) return { error: "This run cannot be checked again here." };
  if (t.capacity !== undefined && t.capacity !== null && t.capacity !== "") {
    const d = Number(t.capacity);
    if (!Number.isFinite(d) || d <= 0 || d > amount) return { error: `Enter a loss between $1 and ${pfOf()?.fmt.money(amount) || "your amount"}.` };
    limits.capacity = d;          /* R35 (the controller, 17:41): capacity moves its own line; the 15 % rule stays as it is */
  }
  if (t.single !== undefined && t.single !== null && t.single !== "") {
    const p = Number(t.single);
    if (!Number.isFinite(p) || p <= 0 || p > 100) return { error: "Enter a one-company limit between 1 % and 100 %." };
    limits.single_stock = Math.round(p * 10) / 1000;
  }
  /* lane sector-limits: the industry rows as typed (t.caps); without them, the run's own caps go back unchanged */
  const L = obj(r.limits) || {}, before = obj(L.sector_caps) || {};
  const read = Array.isArray(t.caps) ? capsFromRows(t.caps) : { caps: before };
  if (read.error) return { error: read.error };
  const moved = !sameCaps(read.caps, before), typedKeys = Object.keys(limits);
  if (!typedKeys.length && !moved) return { error: "Change a limit first." };
  if (Object.keys(read.caps).length) limits.sector_caps = read.caps;
  /* a recheck judges only the limits it is sent: the run's other edits (typed or from your words) go back as they were */
  for (const k of arr(L.edited)) if (KEPT.includes(k) && isNum(L[k]) && !(k in limits)) limits[k] = L[k];
  /* a value you typed now is set by you, no longer from your words (LIMITS_MODEL CONFLICTS; lane hold's card) */
  const typedNow = new Set(typedKeys);
  const said = wordsAfter(L, read.caps).filter((k) => !typedNow.has(k));
  if (said.length) limits.from_words = said;
  return { body: { run_id: r.run_id, limits } };
}

/* the run judged again (pipeline.recheck: {checks, verdict, kpis, sensitivity, baseline, deep_history}) merged into the Result:
   the checks, the verdict and the limits you typed change; the replay's paths stay those of the run */
export function mergeRecheck(result, rc, body, typed) {
  const r = obj(result), x = obj(rc), b = obj(body) && obj(body.limits);
  if (!r || !x || !Array.isArray(x.checks) || !b) return null;
  const limits = { ...(obj(r.limits) || {}) }, edited = new Set(arr(limits.edited)), profile = { ...(obj(r.profile) || {}) };
  if (isNum(b.floor) && (!isNum(limits.floor) || Math.abs(b.floor - limits.floor) > 1e-12)) {   // a floor sent back unchanged is no edit
    limits.floor = b.floor; edited.add("floor");
  }
  if (isNum(b.capacity)) { limits.capacity_dollars = b.capacity; profile.capacity = b.capacity; profile.capacity_dollars = b.capacity; edited.add("capacity"); }
  if (isNum(b.single_stock)) { limits.single_stock = b.single_stock; edited.add("single_stock"); }
  if (obj(b.sector_caps) && Object.keys(b.sector_caps).length) { limits.sector_caps = { ...b.sector_caps }; edited.add("sector_caps"); }
  else { delete limits.sector_caps; edited.delete("sector_caps"); }
  if (Array.isArray(b.from_words) && b.from_words.length) limits.from_words = [...b.from_words]; else delete limits.from_words;
  const shock = x.checks.map(obj).find((c) => c && c.rule === "scenario_stress");
  if (shock && isNum(shock.limit)) limits.scenario_stress = shock.limit;
  limits.edited = [...edited];
  const base = obj(r.baseline), xb = obj(x.baseline);
  /* R35: with a typed capacity, result.capacity (lane fin-backend's path fact) is the one the server drew again for the new
     dollars (pipeline.recheck), else none: never "stay above $510,000" beside $60,000 */
  const moved = isNum(b.capacity) ? { capacity: obj(x.capacity) || null } : {};
  return { ...r, ...moved, checks: x.checks, verdict: x.verdict === undefined ? r.verdict : x.verdict, kpis: obj(x.kpis) || r.kpis,
    sensitivity: x.sensitivity === undefined ? r.sensitivity : x.sensitivity, deep_history: x.deep_history || r.deep_history,
    baseline: base && xb ? { ...base, checks: xb.checks, verdict: xb.verdict } : r.baseline, limits, profile,
    scenario: { ...(obj(r.scenario) || {}) }, rechecked: true };
}

/* the floor row's "what would change the answer" (the workshop's fourth question): result.sensitivity.sentence, as written */
export function sensitivityOf(result, P) {
  const s = obj(obj(result) && result.sensitivity), t = s && str(s.sentence);
  return t ? readReason(t, null, result, P).reason : null;
}

/* Mateo's test (the case's persona 02): what your values cost in this replay, from result.price_of_values (tools.allocation):
   your mix as it is (facts) beside the mix without the excluded lines, the rest scaled up (an assumption) */
export function priceOfValuesOf(result, P) {
  P = pfOf(P);
  const r = obj(result), pv = r && obj(r.price_of_values);
  if (!pv || !P) return null;
  const f = P.fmt, fam = arr(obj(r.scenario) && r.scenario.families)[0];
  const FAM = { tariffs: "Tariff war", war_oil: "War & oil", chips: "Chip war", rates: "Rate shock" };   // config.FAMILY_LABELS
  const famKey = fam ? `${fam}_worst` : null, famLabel = FAM[fam] || null;
  const side = (x, kind, words) => {
    x = obj(x);
    if (!x || !isNum(x.max_drawdown)) return null;
    const read = (label, v, fmt, w) => (isNum(v) ? { label, text: fmt(v), fact: kind === "fact" ? factFor(r, v, w) : null } : null);
    return { kind, label: str(x.label), rows: [read("Worst fall", x.max_drawdown, f.pct, ["worst drop"]),
      read("Growth per year", x.cagr, f.pct, ["growth per year"]),
      famKey && famLabel ? read(`Worst ${famLabel} shock`, x[famKey], f.pct, ["shock"]) : null].filter(Boolean), dd: x.max_drawdown, cagr: x.cagr };
  };
  const now = side(pv.non_esg, "fact"), alt = side(pv.esg, "assumption");
  if (!now || !alt) return null;
  const removed = arr(pv.removed).filter(str), held = obj(obj(pv.non_esg) && pv.non_esg.weights) || {};
  const parts = removed.filter((t) => isNum(held[t])).map((t) => `${t}, ${f.share(held[t])} of your money`);
  now.note = parts.length ? `Including ${parts.join(" and ")}, as the checks judged it.` : now.label;
  const sentence = isNum(alt.cagr) && isNum(now.cagr)
    ? `In this replay, your mix without ${removed.join(" and ") || "the excluded lines"} grew ${f.pct(alt.cagr)} a year against ${f.pct(now.cagr)}, and its worst fall was ${f.pct(alt.dd)} against ${f.pct(now.dd)}.`
    : null;
  return { now, alt, removed, sentence };
}

/* ---- lane clarity (ruling R22): what #money shows before "Show the details": ONE question, ONE answer (second person, past
   tense), the pair's two large figures and their limits. `shown` lists every string on screen when closed (the node test counts
   their figures: about 6 at most). Every figure is the pair's own Result value. ---- */
export function moneyLead(result, view, P) {
  P = pfOf(P);
  const m = moneyModel(result, view, P);
  if (!m) return null;
  const p = m.pair, notes = [m.notes.history, m.notes.fiction].filter(Boolean).join(" ");
  let answer = null;
  if (p && p.kind === "canada") answer = p.risk.v > 0.5 ? "With the move, Canada still carried most of your risk."
    : `With the move, ${p.risk.text} of your risk still came from Canada.`;
  else if (p && p.kind === "move") answer = `With the move, ${p.risk.text} of your risk came from ${p.subject} alone.`;
  else if (p) answer = `${p.risk.text} of your risk came from ${p.subject}, more than from any other holding.`;
  else answer = "Where your money and your risk sat, in this replay.";
  const hedge = p && p.kind === "canada" ? canadaLine(result, view, P) : null;       // R39: the run's own keys, hidden without them
  const shown = [answer, notes, hedge ? hedge.text : ""];
  if (p) {
    for (const w of ["money", "risk"]) shown.push(p[w].text, p[w].label, p[w].was ? `Today ${p[w].was.text}` : "");
    for (const t of [p.moneyTick, p.riskTick]) if (t) shown.push(`${t.label} ${t.text}`);
  }
  return { question: "Where is the risk?", answer, notes, hedge, model: m, shown: shown.filter(Boolean) };
}

/* ---- lane clarity (ruling R22): what #checklist shows before "Show the details": ONE question, ONE answer (which of your
   rules broke, in words: no figure), the three rows the model pins (the asked shock's check among them), each with its value
   against its limit; the floor row in dollars only (dollars first; its percentages are in its meaning and in the details). ---- */
const RULE_WORDS = { max_drawdown: "your floor", scenario_stress: "the shock check", single_stock: "your one-company limit",
  sector: "your one-sector limit", crypto: "your crypto share", esg_direct: "your values", esg_indirect: "your values, inside your ETFs",
  risk_concentration: "the risk-concentration warning", recovery: "the recovery time", short_horizon: "your horizon" };
export const RULE_MEANING = { max_drawdown: ["worst_fall", "floor"], scenario_stress: ["shock_loss", "shock_limit"],
  single_stock: ["money_share", "one_company_limit"], sector: ["sector", "limit"], crypto: ["crypto", "limit"],
  risk_concentration: ["risk_share", "risk_warning"], recovery: ["recovery", "limit"], short_horizon: ["horizon", "limit"],
  esg_direct: ["value", "limit"], esg_indirect: ["value", "limit"] };
const NUMWORD = { 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine" };
const ruleWord = (x) => RULE_WORDS[x.rule] || `the ${String(x.name || "check").toLowerCase()} check`;
const andList = (xs) => (xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
/* "−$207,146 (−34.5 %)" -> "−$207,146": the dollars lead; the bracket stays in the row's meaning and in the details */
export const dollarsOnly = (t) => (t ? String(t).replace(/^(.*\$[\d,.]+)\s*\([^)]*\)\s*$/, "$1") : t);

export function checklistLead(result, view, P) {
  P = pfOf(P);
  const m = checksModel(result, view, P);
  if (!m) return null;
  const broke = m.rows.filter((x) => x.tone === "outside"), cav = m.rows.filter((x) => x.tone === "caveat");
  const n = (k, one, many) => `${NUMWORD[k] || k} ${k === 1 ? one : many}`;
  let answer;
  if (broke.length) {
    const inView = m.visible.filter((x) => x.tone === "caveat").length;   // the lead never counts rows the reader cannot see (director)
    const rest = cav.length ? ` ${cap(n(cav.length, "other check", "other checks"))} raised a caution${inView < cav.length
      ? `; ${inView ? `${NUMWORD[inView] || inView} ${inView === 1 ? "is" : "are"} shown here, the rest in the details` : "they are in the details"}` : ""}.` : "";
    answer = `${cap(andList(broke.map(ruleWord)))} broke ${m.phrase}.${rest}`;
  } else if (m.binding) {
    answer = `No hard limit broke ${m.phrase}; ${ruleWord(m.binding)} added the caveat.`;
  } else {
    answer = `None of your limits broke ${m.phrase}.${cav.length ? ` ${cap(n(cav.length, "check", "checks"))} raised a caution.` : ""}`;
  }
  const rows = m.visible.map((x) => ({ ...x, valueShort: dollarsOnly(x.value), limitShort: dollarsOnly(x.limit) }));
  const capacity = capacityRow(result, view, P);                // R35: the second limit, in the path's own dollars
  const shown = [answer, m.history, ...rows.flatMap((x) => [x.word, x.name, x.valueShort, x.limitShort, x.tierText, x.decided ? x.decidedWord : "",
    x.asked ? `The shock asked about: ${x.asked}` : ""])];
  if (capacity) shown.push(capacity.word, capacity.name, capacity.meta, capacity.value || "", capacity.limit, capacity.when);
  return { question: "Which of your rules broke?", answer, rows, capacity, rest: m.rows.filter((x) => !m.visible.includes(x)), model: m,
    shown: shown.filter(Boolean) };
}

/* ---- G4 (traceability C08): the one-sector line in words, from the sector check's own value, limit and reason ---- */
export function sectorLine(result, P) {
  P = pfOf(P);
  const c = arr(obj(result) && result.checks).map(obj).find((x) => x && x.rule === "sector");
  if (!c || !P || !isNum(c.value) || !isNum(c.limit)) return null;
  const m = /^(.+?) is \d/.exec(str(c.reason) || ""), sector = m ? m[1].replace(/^Information Technology$/, "Technology") : "Your largest sector";
  const where = c.status === "pass" ? "inside" : "beyond";
  return { status: c.status, text: `${sector}: ${P.fmt.pct(c.value)} of the money, ${where} your ${P.fmt.share(c.limit)} sector limit.` };
}

/* ---- G1 (traceability C80): growth per year and volatility over the replay's own dates, today then with the move, in CAD with
   dividends reinvested (result.metrics.today / after; the after side only with a move) ---- */
export function compareOf(result, view, P) {
  P = pfOf(P);
  const r = obj(result), m = obj(r && r.metrics), t = obj(m && m.today), a = obj(m && m.after);
  if (!P || !t || !isNum(t.cagr) || !isNum(t.volatility)) return null;
  const dates = arr(obj(r.series) && r.series.dates), from = P.fmt.date(str(dates[0])), to = P.fmt.date(str(r.as_of) || str(dates[dates.length - 1]));
  const moved = !!obj(obj(view) && view.move);
  const side = (x) => ({ cagr: P.fmt.pct(x.cagr), vol: P.fmt.pct(x.volatility), cagrFact: factFor(r, x.cagr, ["growth per year"]),
    volFact: factFor(r, x.volatility, ["volatility"]) });
  return { period: from && to ? `From ${from} to ${to}, in Canadian dollars, dividends reinvested` : "In Canadian dollars, dividends reinvested",
    today: side(t), after: moved && a && isNum(a.cagr) && isNum(a.volatility) ? side(a) : null };
}

/* ---- compliance (regulation flaw hunter, MAJOR): a persona's limits are derived from its profile, not typed by the client.
   One muted line wherever limits show says which: the run's own flags only (result.limits.edited, written by the recheck path
   when you type a limit; a run that is not a persona's was typed by you) ---- */
const LIMIT_NAMES = { floor: "your floor", capacity: "what you can afford to lose", single_stock: "your one-company limit",
  sector: "your one-sector limit", crypto: "your crypto limit", sector_caps: "your industry limits" };
export function limitsLine(result, view) {
  const r = obj(result) || {}, L = obj(r.limits) || {};
  /* limits-QA (17:25): the fifth profile's limits are your words, the editor's, or assumed by the reader, never "all yours";
     a run judged with no limits says so (LIMITS_MODEL: "No limits set") */
  const you = str(r.pilot) === "you";
  if (r.limits === null && (you || !PERSONAS.has(str(r.pilot)))) return { text: "No limits set.", typed: [], persona: false };
  const said = Array.isArray(L.from_words) ? L.from_words : [];
  /* the industries split by source: all from your words, all yours, or each named on its side ("your Energy limit") */
  const capRows = capsOf(r), capWords = capRows.filter((c) => said.includes(c.key)), mixed = capWords.length && capWords.length < capRows.length;
  const allSaid = (k) => (k === "sector_caps" ? capRows.length > 0 && capWords.length === capRows.length : said.includes(k));
  /* the capacity is an answer, not an override: from your words it is in from_words only (limits-QA 17:52) */
  const keys = [...new Set([...arr(L.edited), ...(said.includes("capacity") ? ["capacity"] : [])])];
  const edited = keys.filter((k) => LIMIT_NAMES[k] && !allSaid(k)), words = keys.filter((k) => LIMIT_NAMES[k] && allSaid(k));
  const named = (ks, fromWords) => ks.flatMap((k) => (k === "sector_caps" && mixed
    ? capRows.filter((c) => said.includes(c.key) === fromWords).map((c) => `your ${c.sector} limit`) : [LIMIT_NAMES[k]]));
  if (words.length || mixed) {
    const and = (xs) => (xs.length === 1 ? xs[0] : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);
    const one = (xs) => xs.length === 1 && xs[0] !== LIMIT_NAMES.sector_caps;
    const wn = named(mixed && !words.includes("sector_caps") ? [...words, "sector_caps"] : words, true), yn = named(edited, false);
    const w = `${cap(and(wn))} ${one(wn) ? "is" : "are"} from your words`;
    const y = yn.length ? `; ${and(yn)} ${one(yn) ? "is" : "are"} set by you` : "";
    const rest = PERSONAS.has(str(r.pilot)) || you ? "; every other limit here is assumed from the profile, not set by you." : ".";
    return { text: `${w}${y}${rest}`, typed: edited, persona: PERSONAS.has(str(r.pilot)) };
  }
  const persona = PERSONAS.has(str(r.pilot)) || you;
  if (!persona) return { text: r.verdict === null ? "" : "Your limits here are set by you.", typed: edited, persona };   // nothing set: no "set by you"
  if (!edited.length) return { text: "Your limits here are assumed from the profile, not set by you.", typed: edited, persona };
  const names = edited.map((k) => LIMIT_NAMES[k]), list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return { text: `${cap(list)} ${names.length === 1 && edited[0] !== "sector_caps" ? "is" : "are"} set by you; every other limit here is assumed from the profile, not set by you.`,
    typed: edited, persona };
}

/* ---- R35 (finance F1): two limits, as the National Bank workshop teaches. TOLERANCE, the 15 % rule: "no fall of more than 15 %
   from any high" (the verdict's floor check). CAPACITY, the persona's own words: "stay above $510,000 ($90,000 of $600,000)",
   with the path's fact from result.capacity (lane fin-backend; hidden without it, never computed here) ---- */
const pctOf = (t) => { const m = /\(([^()]*%)\)\s*$/.exec(String(t || "")); return m ? m[1] : t; };
export function ruleText(result, P) {
  P = pfOf(P);
  const L = obj(obj(result) && result.limits) || {};
  return isNum(L.floor) && P ? { pct: bare(P.fmt.share(L.floor)), words: `no fall of more than ${bare(P.fmt.share(L.floor))} from a high` } : null;
}
export function capacityRow(result, view, P) {
  P = pfOf(P);
  const r = obj(result), C = obj(r && r.capacity), v = obj(view);
  if (!P || !C) return null;
  const side = obj(v && v.move ? C.after : C.today) || obj(C.today);
  if (!side || !isNum(side.line)) return null;
  const f = P.fmt, below = side.status === "broke" || side.status === "below" || side.status === "fail" || (isNum(side.sessions_below) && side.sessions_below > 0);
  const year = (d) => (str(d) ? String(d).slice(0, 4) : null), y0 = year(side.first_below), y1 = year(side.last_below);
  const capText = isNum(side.capacity) ? f.money(Math.abs(side.capacity)) : null, amountText = isNum(side.amount) ? f.money(side.amount) : null;
  return { rule: "capacity", name: "What you can afford to lose", below,
    word: below ? "Fell below" : "Stayed above", tone: below ? "outside" : "neutral", icon: below ? "i-out" : null,
    meta: `Capacity: stay above ${f.money(side.line)}${capText && amountText ? ` (${capText} of ${amountText})` : ""}`,
    value: isNum(side.low_value) ? `${f.money(side.low_value)} at its lowest` : null, limit: `above ${f.money(side.line)}`,
    when: below && y0 ? `Below it for ${isNum(side.sessions_below) ? `${side.sessions_below} sessions` : "a while"}, ${y0 === y1 || !y1 ? `in ${y0}` : `from ${y0} to ${y1}`}.` : "It never fell below it.",
    lowDate: str(side.low_date) ? f.date(side.low_date) : null };
}

/* ---- R39: "Too Canadian?" in one line from the run's keys: today's worst fall, with the move, and hedged like XSP ---- */
export function canadaLine(result, view, P) {
  P = pfOf(P);
  const r = obj(result), m = obj(r && r.metrics), H = obj(r && r.hedge_compare), f = P && P.fmt;
  const today = obj(m && m.today), un = obj(H && H.unhedged), he = obj(H && (H.hedged_standin || H.hedged));
  if (!f || !today || !isNum(today.max_drawdown) || !un || !isNum(un.worst_fall) || !he || !isNum(he.worst_fall)) return null;
  const div = obj(r.diversification) || {}, a = obj(div.after) || {}, t0 = obj(div.today) || {};
  const spread = isNum(a.can_risk_share) && isNum(t0.can_risk_share) ? a.can_risk_share < t0.can_risk_share : null;
  const softer = Math.abs(un.worst_fall) < Math.abs(today.max_drawdown);
  const lead = spread === true ? (softer ? "More spread, and softer" : "More spread, not softer") : softer ? "Softer" : "Not softer";
  return { lead, today: f.pct(today.max_drawdown), after: f.pct(un.worst_fall), hedged: f.pct(he.worst_fall), hedgedKind: str(he.kind) || "assumption",
    text: `${lead}: worst fall ${f.pct(today.max_drawdown)} → ${f.pct(un.worst_fall)} (${f.pct(he.worst_fall)} hedged like XSP, by a similar index).` };
}
