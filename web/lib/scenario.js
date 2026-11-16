/* EPICENTRE Replay, lane sc-u: the pure helpers of #scenario, "Would it survive a future you imagine?" (rulings R21, R22).
   No DOM, no network, no globals: PF (web/lib.js) is passed in. Tests: tests/web_scenario_test.mjs.
   The engine (lane sc-b, tools/factors.py) computes every number: result.scenarios {factors, betas, presets, validation, method}
   and POST /api/scenario for one custom shock vector; the navigator (lane sc-a) reads words into shocks (POST /api/scenario/read).
   This module only names, orders and places those numbers: it never adds, multiplies or judges one (red gate 2). A slider's
   position and a bar's length are geometry from the Result's own values; a floor class comes from the server (web/lib/status.js). */
import { floorClass, FLOOR_WORDS } from "./status.js";
import { holdingName } from "./funds.js";

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const MINUS = "−", NB = " ";

/* the command box's examples (the investor's kind of words; a French one works live, ruling R19c) */
export const EXAMPLES = Object.freeze([
  "What if the war with Iran escalates and oil spikes?",
  "What if AI stocks slump like in 2022?",
  "Et si les taux montaient de 3 points?",
]);

/* the closed section is ONE line with no number (controller, 12:40): the question and the way in */
export const LINE = Object.freeze({ question: "Would it survive a future you imagine?", open: "Try your own scenario", close: "Close your scenario",
  staticOnly: "Building your own shock needs the live app; this saved page has no saved scenario for this investor." });

/* at most this many factor chips stay in view (ruling R22: about six numbers a screen); the rest open with the details */
export const VISIBLE_CHIPS = 3;

/* a holding's plain name (words only; the ticker when the page has none): the page's one ticker map, web/lib/funds.js */
export { holdingName };

/* the floor class in the page's one vocabulary (web/lib/status.js) and its tone, as the dial and the race draw it (R20); the
   engine's "too_close" (the margin to the floor inside its own gap on real episodes) and any status the page does not know
   read amber, never a pass word, never green (controller, 14:00) */
const TONE = { broke: { tone: "outside", icon: "i-out" }, touched: { tone: "caveat", icon: "i-warn" }, held: { tone: "neutral", icon: null },
  too_close: { tone: "caveat", icon: "i-warn" }, unknown: { tone: "caveat", icon: "i-warn" } };
/* the same class said as a made-up future (a scenario is never past tense: "would") */
const WOULD = { broke: "your floor would break" };                   // never a reassuring clause (bank juror, 17:20)
const CLOSE_WORD = "Too close to call";
export const UNJUDGED = "Too close to call against your floor.";
/* "Too close to call: 0.5 points from your floor, inside the engine’s 11.5-point gap on real episodes." (the engine's own
   margin_pp and gap_pp; without them the neutral line) */
export function tooCloseLine(side, worstGap) {
  const m = side && isNum(side.margin_pp) ? Math.abs(side.margin_pp) : null;
  const g = side && isNum(side.gap_pp) ? Math.abs(side.gap_pp) : isNum(worstGap) ? Math.abs(worstGap) : null;
  if (g === null) return UNJUDGED;
  const gap = `inside the engine\u2019s ${tenthsText(g)}\u2011point gap on real episodes.`;   // U+2011: "11.5-point" never splits
  return m === null ? `${CLOSE_WORD}: ${gap}` : `${CLOSE_WORD}: ${pointsText(m)} from your floor, ${gap}`;
}
/* inside the engine's own miss on real episodes (the widest gap_pp the run reports): the server's too_close, or the margin to
   the floor (rounded tenths, as status.js names "touched"; never shown) no wider than that gap. Outside it, a fall past the
   floor still breaks it; anything else is said plainly, with no pass word. */
function gapClass(x, cls, floor, worstGap) {
  if (cls === "too_close" || cls === "touched") return "too_close";
  const g = isNum(x.gap_pp) ? Math.abs(x.gap_pp) : isNum(worstGap) ? Math.abs(worstGap) : null;
  const tenth = (v) => Math.sign(v) * Math.round(Number((Math.abs(v) * 1000).toPrecision(12)));
  const m = isNum(x.margin_pp) ? Math.abs(x.margin_pp) * 10 : isNum(x.fall) && isNum(floor) ? Math.abs(tenth(x.fall) - tenth(floor)) : null;
  if (cls && cls !== "unknown" && g !== null && m !== null && m <= Math.round(g * 10)) return "too_close";
  return cls;
}
const STATUS_ALIASES = { fail: true, breach: true, below: true, beyond: true, pass: false, ok: false, above: false, inside: false };

/* ---- formatting (PF.fmt underneath: U+2212, U+00A0 before %, tenths ties away from zero) ---- */
const plus = (text) => (text && text[0] !== MINUS && !/^0(\.0+)? /.test(text) ? `+${text}` : text);
function tenthsText(v) {                          // a value already in points, one decimal, ties away from zero
  const t = Math.sign(v) * Math.round(Number((Math.abs(v) * 10).toPrecision(12)));
  return (t < 0 ? MINUS : "") + (Math.abs(t) / 10).toFixed(1);
}
/* a factor's move as the chip prints it: "+52.0 %", "−29.0 %", "+1.9 points" (rates move in percentage points) */
export function shockText(value, unit, PF) {
  if (!isNum(value)) return "";
  const text = plus(PF.fmt.pct(value));
  if (unit !== "pp") return text;                 // rates: a change of the yield as a fraction (0.01 = 1 point, lane sc-b)
  return text.replace(/\u00a0%$/, /^[+\u2212]?1\.0\u00a0%$/.test(text) ? `${NB}point` : `${NB}points`);
}
/* a move with its sign: "+21.3 %", "−8.5 %" (PF.fmt.pct underneath) */
export const signedPct = (x, PF) => (isNum(x) ? plus(PF.fmt.pct(x)) : "");
/* a gap in words: the engine's move minus the real one, in points ("1.3 points higher": the engine's fall was smaller) */
export function gapWords(v) {
  if (!isNum(v)) return "";
  const t = pointsText(v);
  return t.startsWith("0.0") ? "the same" : `${t} ${v > 0 ? "higher" : "lower"}`;
}
/* a gap between the engine and the real fall, in points (gap_pp is in percentage points) */
export const pointsText = (v) => (isNum(v) ? `${tenthsText(Math.abs(v))}${NB}${Math.abs(v) >= 0.95 && Math.abs(v) < 1.05 ? "point" : "points"}` : "");

/* ---- the Result's scenarios block, read once ---- */
function factorsOf(sc) {
  return arr(sc.factors).filter((f) => obj(f) && str(f.id)).map((f) => ({ id: f.id, label: shortLabel(str(f.label) || f.id), full: str(f.label) || f.id,
    unit: f.unit === "pp" ? "pp" : "pct", source: str(f.source),
    bounds: boundsOf(f), anchors: arr(f.anchors).filter((a) => obj(a) && isNum(a.value)) }));
}
/* a factor's name on its chip: the engine's label without its tickers in brackets ("Tech stocks (QQQ)" reads "Tech stocks") */
const shortLabel = (label) => label.replace(/\s*\([^)]*\)\s*$/, "") || label;
function boundsOf(f) {                             // the engine's own bounds ({lo, hi}, [lo, hi] or ±bound); null when it gave none
  const b = f.bounds;
  if (Array.isArray(b) && b.length === 2 && isNum(b[0]) && isNum(b[1]) && b[0] < b[1]) return { lo: b[0], hi: b[1], given: true };
  if (obj(b) && isNum(b.lo) && isNum(b.hi) && b.lo < b.hi) return { lo: b.lo, hi: b.hi, given: true };
  if (isNum(f.bound) && f.bound > 0) return { lo: -f.bound, hi: f.bound, given: true };
  return null;
}
function presetsOf(sc) {
  return arr(sc.presets).filter((p) => obj(p) && str(p.id) && obj(p.shocks)).map((p) => {
    const all = cleanShocks(p.shocks), named = arr(p.measured).filter((k) => isNum(all[k]));
    const shocks = named.length ? Object.fromEntries(named.map((k) => [k, all[k]])) : all;
    return { id: p.id, label: str(p.label) || p.id, source: str(p.source), shocks, all, answer: p };
  });
}
export function cleanShocks(shocks) {
  const out = {};
  for (const [k, v] of Object.entries(obj(shocks) || {})) if (isNum(v)) out[k] = v;
  return out;
}

/* the section's model: null-safe; show is false when the Result carries no usable scenarios block (the section hides) */
export function scenarioModel(result, PF, opts) {
  const r = obj(result), sc = r && obj(r.scenarios);
  const factors = sc ? factorsOf(sc) : [], presets = sc ? presetsOf(sc) : [];
  if (!sc || !factors.length || !presets.length) {
    /* live, with no scenarios block in this Result: the navigator's reading brings its own factors and bounds (withBook) */
    if (!r) return { show: false };
    /* static, with no saved scenarios: the question and one honest line, no builder and no network call (controller, 13:00) */
    if (!(opts && opts.live)) return { show: true, staticOnly: true, factors: [], presets: [], byId: {} };
    const v = PF.view(r) || {};
    return { show: true, liveOnly: true, factors: [], presets: [], byId: {}, validation: null, method: null, kind: null, lead: null,
      move: v.move ? { name: v.move.name, weightText: v.move.weightText, ticker: v.move.ticker } : null,
      floor: v.floor ? { v: v.floor.v, text: v.floor.text } : null, amount: v.amount, amountText: v.amountText };
  }
  const v = PF.view(r) || {};
  const ids = new Set(factors.map((f) => f.id));
  for (const p of presets) for (const k of Object.keys(p.all)) if (!ids.has(k)) { delete p.shocks[k]; delete p.all[k]; }
  const live = presets.filter((p) => Object.keys(p.shocks).length);
  for (const f of factors) f.marks = marksOf(f, live);
  const vids = new Set(arr(sc.validation).map((x) => obj(x) && x.episode).filter(Boolean));
  for (const p of live) p.real = realOf(r, p, vids, v, PF);
  for (const f of factors) if (!f.bounds) f.bounds = derivedBounds(f);
  return { show: live.length > 0, factors, presets: live, byId: Object.fromEntries(factors.map((f) => [f.id, f])),
    move: v.move ? { name: v.move.name, weightText: v.move.weightText, ticker: v.move.ticker } : null,
    floor: v.floor ? { v: v.floor.v, text: v.floor.text } : null, amount: v.amount, amountText: v.amountText,
    validation: validationOf(sc.validation), method: str(sc.method), kind: str(sc.kind), lead: leadFactor(sc, v.move, ids),
    facts: factsOf(sc.facts, r.facts) };
}
/* {path: fact id} from the engine (result.scenarios.facts), kept only where result.facts has the row (U6's drawer reads it) */
function factsOf(map, facts) {
  const out = {}, rows = obj(facts) || {};
  for (const [path, id] of Object.entries(obj(map) || {})) if (typeof id === "string" && obj(rows[id])) out[path] = id;
  return out;
}
/* the fact id of one number of a move on record, while the investor has not changed it (a moved slider is a new scenario) */
export function factOf(model, path) {
  return (model && model.facts && model.facts[path]) || null;
}
/* the factor the moved holding is most sensitive to (its largest beta, read as the engine gave it): its chip stays in view */
function leadFactor(sc, move, ids) {
  const b = move && obj(sc.betas) && obj(sc.betas[move.ticker]);
  if (!b) return null;
  const best = Object.entries(b).filter(([k, x]) => ids.has(k) && isNum(x) && x !== 0).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]))[0];
  return best ? best[0] : null;
}

/* a move on record that copies a real episode (every factor measured over one window, or the engine's own check window): the
   real replay of this run over that window, from the run's breaches (a fall from a high, the floor's own definition, R13):
   "The real April 2025 fall with this move: −16.9 %, past your floor." Null when the replay has no fall there. */
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function realOf(r, p, vids, v, PF) {
  const w = obj(p.answer.window), copy = p.answer.headline === null || vids.has(p.id);
  if (!copy || !w || !str(w.start) || !str(w.end)) return null;
  const end = new Date(`${w.end.slice(0, 10)}T00:00:00Z`);
  const late = new Date(end.getTime() + 31 * 864e5).toISOString().slice(0, 10);
  const b = arr(r.breaches).filter((x) => obj(x) && isNum(x.depth) && str(x.trough_date) && x.trough_date >= w.start.slice(0, 10) && x.trough_date <= late)
    .sort((x, y) => x.depth - y.depth)[0];
  if (!b || !v.floor) return null;
  const cls = floorClass(b.depth, v.floor.v, true);
  const month = MONTHS[Number(b.trough_date.slice(5, 7)) - 1], who = v.move ? "with this move" : "of your mix";
  return { lead: `The real ${month} ${b.trough_date.slice(0, 4)} fall ${who}: `, figure: PF.fmt.pct(b.depth),
    tail: cls === "touched" ? ", touching your floor." : ", past your floor.", depth: b.depth, cls };
}

/* the engraved marks on a factor's track: the engine's anchors when it sends them, else every preset that moves this factor
   (a preset is a move measured on the record, so its value is a precedent; its label names it) */
function marksOf(f, presets) {
  const raw = f.anchors.length ? f.anchors.map((a) => ({ value: a.value, label: str(a.label) || str(a.source) || "", source: str(a.source) }))
    : presets.filter((p) => isNum(p.shocks[f.id]) && p.shocks[f.id] !== 0).map((p) => ({ value: p.shocks[f.id], label: str(p.answer.short) || p.label, source: p.source, preset: p.id, id: p.id }));
  const seen = new Set();
  return raw.filter((m) => { const k = m.value.toPrecision(8); if (seen.has(k)) return false; seen.add(k); return true; });
}
/* no bounds from the engine: the server's own rule (±3 times the largest measured move, lane sc-b) over the moves the page has */
function derivedBounds(f) {
  const big = Math.max(0, ...f.marks.map((m) => Math.abs(m.value)));
  return big > 0 ? { lo: -3 * big, hi: 3 * big, given: false } : null;
}

/* a value's place on its track, 0..1, and where zero sits (geometry only) */
export function trackOf(f, value) {
  let b = f && f.bounds;
  if (!b) return null;
  if (!b.given && isNum(value) && Math.abs(value) > b.hi) b = { lo: -1.25 * Math.abs(value), hi: 1.25 * Math.abs(value), given: false };
  const at = (v) => Math.min(1, Math.max(0, (v - b.lo) / (b.hi - b.lo)));
  return { lo: b.lo, hi: b.hi, x: isNum(value) ? at(value) : at(0), zero: at(0), step: f.unit === "pp" ? 0.05 : 0.005,
    marks: laneMarks(f.marks.map((m) => ({ ...m, x: at(m.value) }))) };
}
/* labels that would overlap go to a second line; a third crowd keeps only its notch (the label is in its title) */
function laneMarks(marks) {
  const out = marks.slice().sort((a, b) => a.x - b.x), last = [-1, -1];
  for (const m of out) {
    const lane = m.x - last[0] >= 0.26 ? 0 : m.x - last[1] >= 0.26 ? 1 : -1;
    m.lane = lane;
    if (lane >= 0) last[lane] = m.x;
  }
  return out;
}

/* the keys of a factor's slider: arrows move half a point (a twentieth of a yield point), Page Up / Page Down jump to the next
   engraved precedent (or the bound), Home goes back to zero; null for any other key. Never a value between marks made up. */
export function keyStep(f, value, key, step) {
  const b = f && f.bounds;
  if (!b || !isNum(value)) return null;
  const clamp = (v) => Math.min(b.hi, Math.max(b.lo, v));
  if (key === "ArrowRight" || key === "ArrowUp") return clamp(value + step);
  if (key === "ArrowLeft" || key === "ArrowDown") return clamp(value - step);
  if (key === "Home") return 0;
  const stops = [b.lo, 0, b.hi, ...f.marks.map((m) => m.value)].sort((x, y) => x - y);
  if (key === "PageUp") return stops.find((v) => v > value + 1e-12) ?? b.hi;
  if (key === "PageDown") return [...stops].reverse().find((v) => v < value - 1e-12) ?? b.lo;
  return null;
}

/* the snap: a value within a hair of an engraved mark lands on it (the precedent itself, never a nearby made-up number) */
export function snapTo(f, value) {
  const b = f && f.bounds;
  if (!b || !isNum(value)) return value;
  const near = f.marks.find((m) => Math.abs(m.value - value) <= (b.hi - b.lo) * 0.012);
  return near ? near.value : Math.abs(value) <= (b.hi - b.lo) * 0.006 ? 0 : value;
}

/* ---- the validation: the engine fed each real episode's factor moves, against what really happened ---- */
function validationOf(list) {
  const rows = arr(list).filter((x) => obj(x) && (str(x.episode) || str(x.label))).map((x) => {
    const n = (k) => (isNum(x[k]) ? x[k] : null), g = obj(x.gap_pp);
    const sides = isNum(x.gap_pp_today) || isNum(x.gap_pp_after) ? { today: n("gap_pp_today"), after: n("gap_pp_after") } : null;
    return { episode: str(x.label) || x.episode, id: x.episode, window: obj(x.window) ? { start: str(x.window.start), end: str(x.window.end) } : null,
      realToday: n("real_today"), modelToday: n("model_today"), realAfter: n("real_after"), modelAfter: n("model_after"),
      gap: sides || (g ? { today: isNum(g.today) ? g.today : null, after: isNum(g.after) ? g.after : null } : isNum(x.gap_pp) ? { one: x.gap_pp } : null) };
  });
  const gaps = rows.flatMap((x) => (x.gap ? Object.values(x.gap).filter(isNum).map(Math.abs) : []));
  return rows.length ? { rows, worstGap: gaps.length ? Math.max(...gaps) : null } : null;
}
/* the one visible line (R22): the widest gap the table shows, as the engine's own figure */
export function checkedLine(validation) {
  if (!validation || !isNum(validation.worstGap)) return null;
  return { lead: "Checked against real episodes: within ", figure: pointsText(validation.worstGap), tail: "." };
}

/* ---- one answer (a preset's precomputed numbers or POST /api/scenario's), in the page's words ---- */
function classOf(side, floor) {
  const st = side.floor_status !== undefined ? side.floor_status : side.beyond !== undefined ? side.beyond : side.status;
  if (st === "too_close") return "too_close";
  const beyond = typeof st === "string" && Object.prototype.hasOwnProperty.call(STATUS_ALIASES, st) ? STATUS_ALIASES[st] : st;
  const cls = floorClass(side.fall, floor, beyond);
  if (cls) return cls;
  return st === null || st === undefined || !isNum(floor) ? null : "unknown";     // a status the page cannot name: never a pass
}
function sideOf(raw, key, label, floor, PF, worstGap) {
  const x = obj(raw);
  if (!x || !isNum(x.fall)) return null;
  const cls = gapClass(x, classOf(x, floor), floor, worstGap);
  const t = cls ? TONE[cls] : { tone: "neutral", icon: null };
  const close = cls === "too_close" || cls === "unknown";
  return { key, label, fall: x.fall, fallText: x.fall > 0 ? plus(PF.fmt.pct(x.fall)) : PF.fmt.pct(x.fall),
    dollars: isNum(x.dollars) ? x.dollars : null, dollarsText: isNum(x.dollars) ? (x.dollars > 0 ? `+${PF.fmt.money(x.dollars)}` : PF.fmt.money(x.dollars)) : null,
    cls, word: close ? CLOSE_WORD : cls === "broke" ? "Past your floor" : null, would: close ? null : (cls && WOULD[cls]) || null,
    close: close ? (cls === "too_close" ? tooCloseLine(x, worstGap) : UNJUDGED) : null,
    plain: !close && cls !== "broke" && isNum(floor) ? `your floor is a ${PF.fmt.share(Math.abs(floor))} fall from a high` : null, tone: t.tone, icon: t.icon };
}
function contributionsOf(raw, model, key) {
  const c = obj(raw);
  if (!c) return [];
  const map = obj(c[key]) || (Object.values(c).every(isNum) ? c : null);
  if (!map) return [];
  const list = Object.entries(map).filter(([, v]) => isNum(v)).map(([tk, v]) => ({ ticker: tk, name: model.move && model.move.ticker === tk ? model.move.name : holdingName(tk),
    value: v, isMove: !!(model.move && model.move.ticker === tk) }));
  const big = Math.max(0, ...list.map((x) => Math.abs(x.value)));
  return list.sort((a, b) => a.value - b.value).map((x) => ({ ...x, w: big > 0 ? Math.abs(x.value) / big : 0 }));
}
export function outcomeOf(answer, model, PF) {
  const a = obj(answer);
  if (!a) return null;
  const floor = model.floor ? model.floor.v : null;
  const worst = model.validation ? model.validation.worstGap : null;
  const after = model.move ? sideOf(a.after, "after", `With the move, ${model.move.name} ${model.move.weightText}`, floor, PF, worst) : null;
  const today = sideOf(a.today || (isNum(a.fall) ? a : null), "today", model.move ? "Today’s mix" : "Your mix", floor, PF, worst);
  const main = after || today;
  if (!main) return null;
  const contrib = contributionsOf(a.contributions, model, main.key);
  for (const x of contrib) x.text = plus(PF.fmt.pct(x.value));
  const all = cleanShocks(a.shocks), named = arr(a.measured).filter((k) => isNum(all[k]));
  const implied = arr(a.implied).filter((k) => isNum(all[k]) && !named.includes(k));
  const uncovered = [...new Set([...arr(obj(a.today) && a.today.uncovered), ...arr(obj(a.after) && a.after.uncovered)])].filter(str);
  return { main, other: after ? today : null, sides: [after, today].filter(Boolean), contributions: contrib, sentence: sentenceOf(main, !!after),
    implied: Object.fromEntries(implied.map((k) => [k, all[k]])), uncovered };
}
/* "In this made-up scenario, your mix with the move would fall about −9.0 % (−$54,000): your floor would break." */
function sentenceOf(side, withMove) {
  const who = withMove ? "your mix with the move" : "your mix";
  const verb = side.fall < 0 && side.fallText[0] === MINUS ? "would fall about " : side.fall > 0 && side.fallText[0] === "+" ? "would rise about " : "would barely move, about ";
  return [{ text: `In this made-up scenario, ${who} ${verb}` }, { text: side.fallText, fig: true },
    side.dollarsText ? [{ text: " (" }, { text: side.dollarsText, fig: true }, { text: ")" }] : [],
    { text: side.would ? `: ${side.would}.` : side.plain ? `; ${side.plain}.` : "." }, side.close ? { text: ` ${side.close}`, close: true } : []].flat();
}

/* ---- the navigator's reading (POST /api/scenario/read): {shocks, why, unmapped, clarify} ---- */
const quoted = (w) => `‘${w}’`;
export function unmappedLine(words) {
  const w = arr(words).map(str).filter(Boolean);
  if (!w.length) return null;
  const list = w.length === 1 ? quoted(w[0]) : `${w.slice(0, -1).map(quoted).join(", ")} or ${quoted(w[w.length - 1])}`;
  return `No factor matches ${list}; say which channel you mean.`;
}
export function readingOf(answer, model) {
  const a = obj(answer) || {};
  const shocks = {}, out = [];
  for (const [k, v] of Object.entries(cleanShocks(a.shocks))) {
    const f = model.byId[k];
    if (!f) { out.push(k); continue; }                         // a factor the engine does not know never reaches a slider
    shocks[k] = v;                                             // never clamped here: the engine checks its own bounds and says so
  }
  const why = {};
  for (const [k, v] of Object.entries(obj(a.why) || {})) if (shocks[k] !== undefined && str(v)) why[k] = str(v);
  const status = str(a.status), blocked = status === "blocked";
  return { shocks: blocked ? {} : shocks, why: blocked ? {} : why, unmapped: blocked ? null : unmappedLine(a.unmapped), clarify: blocked ? null : str(a.clarify),
    dropped: out, empty: blocked || !Object.keys(shocks).length, blocked, status, message: str(a.message), by: byLine(a) };
}
/* who read the words, said once (R8: the AI's work visible; R15: never a live-looking badge for a fallback) */
function byLine(a) {
  if (a.method === "bedrock") return "Read by the navigator on Amazon Bedrock; code checked every pick against the record.";
  if (a.method === "keyword") return str(a.message) || str(a.fallback_reason) || "Read by the keyword rules: the navigator did not answer this time.";
  return null;
}

/* a live-only model takes its factors, bounds and engraved marks from the reading itself (POST /api/scenario/read carries
   factors, bounds {id: [lo, hi]} and marks {id: [{id, label, value}]}, the same book the engine checks against) */
export function withBook(model, answer) {
  const a = obj(answer);
  if (!model || !model.liveOnly || !a || !arr(a.factors).length) return model;
  const bounds = obj(a.bounds) || {};
  const factors = factorsOf({ factors: arr(a.factors).map((f) => (obj(f) ? { ...f, bounds: bounds[f.id] } : f)) });
  for (const f of factors) {
    f.marks = arr(obj(a.marks) && a.marks[f.id]).filter((m) => obj(m) && isNum(m.value)).map((m) => ({ value: m.value, label: str(m.label) || "", id: str(m.id) }));
    if (!f.bounds) f.bounds = derivedBounds(f);
  }
  return { ...model, factors, byId: Object.fromEntries(factors.map((f) => [f.id, f])) };
}

/* the precedent each reading anchored to (POST /api/scenario/read: anchors {factor: id}, marks {factor: [{id, label, value}]}),
   engraved on its track when the Result's own moves on record do not already carry it */
export function anchoredMarks(answer) {
  const a = obj(answer) || {}, anchors = obj(a.anchors) || {}, marks = obj(a.marks) || {}, out = {};
  for (const [f, id] of Object.entries(anchors)) {
    const m = arr(marks[f]).find((x) => obj(x) && x.id === id && isNum(x.value));
    if (m) out[f] = { value: m.value, label: str(m.label) || "", id: m.id };
  }
  return out;
}
export function withMarks(model, extra) {
  const add = obj(extra);
  if (!model || !model.show || !add || !Object.keys(add).length) return model;
  const factors = model.factors.map((f) => {
    const m = add[f.id];
    if (!m || f.marks.some((x) => Math.abs(x.value - m.value) < 1e-9)) return f;
    const nf = { ...f, marks: [...f.marks, { ...m }] };
    if (nf.bounds && !nf.bounds.given) nf.bounds = derivedBounds(nf);
    return nf;
  });
  return { ...model, factors, byId: Object.fromEntries(factors.map((f) => [f.id, f])) };
}

/* ---- the chips: one per factor that moves, in the engine's order; the most extreme ones stay in view (R22) ---- */
export function chipsOf(shocks, model, why, max = VISIBLE_CHIPS, extra, implied) {
  const s = cleanShocks(shocks), added = extra instanceof Set ? extra : new Set(), co = cleanShocks(implied);
  const moves = (f) => isNum(s[f.id]) && (s[f.id] !== 0 || added.has(f.id));
  const all = model.factors.filter(moves).map((f) => ({ id: f.id, label: f.label, unit: f.unit, value: s[f.id],
    why: (why && why[f.id]) || null, reach: f.bounds ? Math.abs(s[f.id]) / Math.max(Math.abs(f.bounds.lo), Math.abs(f.bounds.hi)) : 0 }));
  const rank = (c) => (c.id === model.lead ? 2 : 0) + c.reach;          // reach is at most 1: the lead factor always stays in view
  const keep = new Set(all.slice().sort((a, b) => rank(b) - rank(a)).slice(0, max).map((c) => c.id));
  const withIt = model.factors.filter((f) => !moves(f) && isNum(co[f.id])).map((f) => ({ id: f.id, label: f.label, unit: f.unit, value: co[f.id], why: null, implied: true }));
  return { shown: all.filter((c) => keep.has(c.id)), folded: all.filter((c) => !keep.has(c.id)), implied: withIt,
    idle: model.factors.filter((f) => !moves(f) && !isNum(co[f.id]) && f.bounds).map((f) => ({ id: f.id, label: f.label })) };
}

/* the move on record to open with: the one that matches the investor's asked family (the page's thread), else the first */
const FAMILY_WORDS = [[/tariff/i, /tariff/i], [/oil|war/i, /oil|energy/i], [/chip|tech/i, /chip|tech|\bAI\b/i], [/rate/i, /rate/i]];
export function firstPreset(result, model) {
  if (!model.presets.length) return null;
  const fam = String((obj(result) && obj(result.scenario) && arr(result.scenario.families)[0]) || "");
  const pair = fam ? FAMILY_WORDS.find(([f]) => f.test(fam)) : null;
  return (pair && model.presets.find((p) => pair[1].test(p.label))) || model.presets[0];
}

/* the figures the closed section shows (R22: about six a screen, axes and track marks excluded); the section draws these */
export function closedFigures(chips, outcome, checked, PF, model, real) {
  const figs = chips.shown.map((c) => shockText(c.value, c.unit, PF));
  if (outcome) figs.push(outcome.main.fallText, ...(outcome.main.dollarsText ? [outcome.main.dollarsText] : []));
  if (outcome && outcome.main.close) figs.push(...(outcome.main.close.match(/\d+(?:\.\d+)?/g) || []));   // the too-close line's own figures
  else if (checked) figs.push(checked.figure);
  if (real) figs.push(real.figure);
  return figs.filter(Boolean);
}

/* ---- the two requests (the server validates every value; the page sends the run's own mixes and limits) ---- */
function mixes(r) {
  const base = obj(r.baseline) && obj(r.baseline.portfolio);
  return { portfolio: obj(r.portfolio) || {}, baseline: base || null };
}
/* the run's decision date: the engine and the reader measure only what is dated on or before it (red gate 3, no look-ahead) */
const asOf = (r) => (typeof r.as_of === "string" && /^\d{4}-\d{2}-\d{2}/.test(r.as_of) ? r.as_of.slice(0, 10) : null);
export function readBody(result, text) {                     // server.py ScenarioReadBody {text, portfolio, as_of}
  const r = obj(result) || {};
  return { text: String(text || "").trim(), portfolio: mixes(r).portfolio, as_of: asOf(r) };
}
export function scenarioBody(result, shocks) {                 // server.py ScenarioBody (lane sc-b)
  const r = obj(result) || {}, lim = obj(r.limits) || {};
  return { ...mixes(r), shocks: cleanShocks(shocks), limits: isNum(lim.floor) ? { floor: lim.floor } : {}, amount: isNum(r.amount) ? r.amount : null,
    as_of: asOf(r), fill: true };
}
/* the visible line for the factors that fold away: named ones past the first three, and the ones the engine moved with them */
const WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"];
export function moreLine(chips) {
  const a = chips.folded.length, b = chips.implied.length, n = a + b;
  if (!n) return null;
  const count = n === 1 ? "One more factor moves" : `${WORDS[n] || "More"} more factors move`;
  return `${count}${!a ? " with it, as they did week to week" : ""}; ${n === 1 ? "it is" : "they are"} in the details.`;
}
/* two shock vectors are the same scenario (a preset's numbers answer only its own shocks) */
export function sameShocks(a, b) {
  const x = cleanShocks(a), y = cleanShocks(b);
  const keys = new Set([...Object.keys(x), ...Object.keys(y)]);
  for (const k of keys) if (Math.abs((x[k] || 0) - (y[k] || 0)) > 1e-12) return false;
  return true;
}
