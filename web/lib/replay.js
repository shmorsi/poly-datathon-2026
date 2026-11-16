/* The Replay stage's words and timings (lane U2, design doc §2 item 2 a–e, rulings R1, R3, R13, R15): pure, no DOM, no network.
   Every number it hands the stage is a Result key or a sum of the Result's own trace rows (the receipt's seconds); the browser
   never judges a check: statuses and verdicts are the server's (pitfall 5). PF (web/lib.js) is read at call time, never at
   import time. Sentences are segments [[text, kind]] (kind "num" sets tabular figures, "move" the move's colour). */

import { FLOOR_WORDS, bindingWord } from "./status.js";
import { dialModel } from "./dial.js";
import { plainLabel } from "./funds.js";        // the plain names of the holdings (lane hold's labels: XBB.TO = "Canadian bonds")          // lane U4's model of the size curve: the stage's start-month line reads its band

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const arr = (x) => (Array.isArray(x) ? x : []);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const own = (o, k) => !!o && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
const PFx = () => (typeof globalThis !== "undefined" && globalThis.PF) || null;
const NB = " ", MINUS = "−", DASH = "–";
const fmt = () => (PFx() && PFx().fmt) || null;
const pct = (x) => (fmt() && isNum(x) ? fmt().pct(x) : "");
const share = (x) => (fmt() && isNum(x) ? fmt().share(x) : "");
const money = (x) => (fmt() && isNum(x) ? fmt().money(x) : "");
const dateText = (d) => (fmt() && d ? fmt().date(d) : "");
const seg = (...parts) => parts.filter((p) => Array.isArray(p) && p[0]);
const unsigned = (s) => String(s || "").replace(MINUS, "");
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
/* R18: typographic quotes and apostrophes in every string the stage shows ("Liberation Day" -> “Liberation Day”, Trump's -> Trump’s) */
export function smart(text) {
  return String(text == null ? "" : text).replace(/"([^"]*)"/g, "\u201c$1\u201d").replace(/(\w)'(\w)/g, "$1\u2019$2")
    .replace(/'([^']*)'/g, "\u2018$1\u2019").replace(/"/g, "\u201d").replace(/'/g, "\u2019");
}

export const STEPS = ["OBSERVE", "UNDERSTAND", "COMPARE", "EXPLAIN", "VERIFY"];
export const STEP_WORDS = {      // pipeline.STEP_LABELS, shortened for one line
  OBSERVE: { name: "Observe", what: "Read the plan and screen the question" },
  UNDERSTAND: { name: "Understand", what: "Turn the words into a move and pick the shocks" },
  COMPARE: { name: "Compare", what: "Replay today’s mix and the move" },
  EXPLAIN: { name: "Explain", what: "Write the explanation from the computed facts" },
  VERIFY: { name: "Verify", what: "Trace every number to the data" },
};
export const FAMILY = { tariffs: "Tariff war", war_oil: "War & oil", chips: "Chip war", rates: "Rate shock" };   // config.FAMILY_LABELS
const NOUN = { tariffs: "tariff war", war_oil: "war and oil", chips: "chip war", rates: "rate shock" };
const PERSONAS = new Set(["robert", "mateo", "amira", "canadian"]);
const PERSONA_NOTE = " (assumed for this fictional profile)";

/* a ms count as the receipt prints it: "240 ms" under a second, else "2.5 s" (one decimal) */
export function duration(msv) {
  if (!isNum(msv) || msv < 0) return "";
  return msv < 1000 ? `${Math.round(msv)}${NB}ms` : `${(Math.round(msv / 100) / 10).toFixed(1)}${NB}s`;
}

/* "us.anthropic.claude-sonnet-5-5" -> "Claude Sonnet 5.5"; another Claude id -> "Claude"; anything else as given */
export function modelName(id) {
  const s = str(id);
  if (!s) return null;
  const m = /claude-([a-z]+)-(\d+)(?:-(\d+))?/i.exec(s);
  if (m) return `Claude ${m[1].charAt(0).toUpperCase()}${m[1].slice(1).toLowerCase()} ${m[2]}${m[3] ? "." + m[3] : ""}`;
  return /claude/i.test(s) ? "Claude" : s;
}

/* the date a saved run was recorded on (pipeline._as_replay writes it into the message: "... recorded on 15 Nov 2026") */
export function recordedOn(r) {
  const m = /recorded on (\d{1,2}[\s ][A-Z][a-z]{2}[\s ]\d{4})/.exec(String((obj(r) || {}).message || ""));
  return m ? m[1].replace(/\s/g, NB) : null;
}
/* a Result the page did not just run: a demo replay, or anything loaded from the saved runs (opts.live = it just landed live) */
export const isRecorded = (r, opts) => !(obj(opts) && opts.live === true) || (obj(r) || {}).mode === "demo_replay";

/* the years this replay covers, from the Result's own series dates: "2021–26" */
export function replayYears(r) {
  r = obj(r) || {};
  const d = arr(obj(r.series) && r.series.dates).length ? r.series.dates : arr(obj(r.tipping_point) && obj(r.tipping_point.paths) && r.tipping_point.paths.dates);
  const a = str(d[0]), z = str(d[d.length - 1]);
  if (!a || !z || !/^\d{4}/.test(a) || !/^\d{4}/.test(z)) return null;
  return a.slice(0, 4) === z.slice(0, 4) ? a.slice(0, 4) : `${a.slice(0, 4)}${DASH}${z.slice(2, 4)}`;
}

/* whose limits these are: a persona's (assumed for a fictional profile, R13) unless the investor edited that limit */
function voice(r) {
  r = obj(r) || {};
  const p = obj(r.profile) || {}, l = obj(r.limits) || {}, PF = PFx();
  const v = PF ? PF.view(r) : { who: {} };
  const who = obj(v.who) || {};
  const persona = PERSONAS.has(str(r.pilot) || "");
  const edited = new Set(arr(l.edited));
  /* R18: one voice. Inside the instrument the investor is "you" (like the verdict words); the persona's name only frames it */
  return { v, persona, edited, his: "your", him: "you", name: str(p.name) || who.name || null, mine: (key) => !persona || edited.has(key) };
}

/* ---- the five steps, from the Result's trace (a saved run replays them at a calm pace) or from live progress lines ---- */
const nested = (t) => /^navigator\./.test(String(t.tool || ""));        // the navigator's own rows sit inside run_scenario's time
export function stepRows(r) {
  const trace = arr((obj(r) || {}).trace).map(obj).filter(Boolean);
  return STEPS.map((step) => {
    const rows = trace.filter((t) => t.step === step);
    const services = [...new Set(rows.map((t) => str(t.service)).filter((s) => s && !/^Python\b/.test(s)))];
    const own_ = rows.filter((t) => !nested(t)), use = own_.length ? own_ : rows, msv = use.reduce((a, t) => a + (isNum(t.ms) ? t.ms : 0), 0);
    /* a step's time is every trace row the trace files under it (as the live progress line times the whole step); when a service
       and code share it, each part is named with its own ms, so the guardrail's own time reads as #how's station does */
    const by = new Map();
    for (const t of use) if (isNum(t.ms) && t.ms > 0) { const k = /^Python\b/.test(String(t.service || "")) || !str(t.service) ? "code" : str(t.service); by.set(k, (by.get(k) || 0) + t.ms); }
    return { step, ...STEP_WORDS[step], status: rows.length ? "done" : "skipped", service: rows.length ? (services.join(" and ") || "Python") : null,
      ms: rows.length ? msv : null, parts: by.size > 1 ? [...by].map(([service, ms]) => ({ service, ms })).sort((a, b) => (a.service === "code") - (b.service === "code")) : null };
  });
}
/* live progress lines ({step, status, service, ms, detail}) folded into the same five rows; unknown steps are ignored */
export function foldStep(steps, ev) {
  const e = obj(ev);
  const base = arr(steps).length === STEPS.length ? arr(steps) : STEPS.map((step) => ({ step, ...STEP_WORDS[step], status: "waiting", service: null, ms: null }));
  if (!e || !STEPS.includes(e.step)) return base;
  return base.map((s) => {
    if (s.step !== e.step) return s;
    if (e.status === "detail") return { ...s, detail: str(e.detail) || s.detail || null };
    const status = { run: "running", done: "done", skipped: "skipped", error: "error" }[e.status] || s.status;
    return { ...s, status, service: str(e.service) || s.service, ms: isNum(e.ms) ? e.ms : s.ms, detail: str(e.detail) || s.detail || null };
  });
}
/* the one receipt line the steps collapse into: "5 steps in 21.6 s", the services that answered, recorded on <date> */
export function receiptOf(steps, r, opts) {
  const done = arr(steps).filter((s) => obj(s) && s.status === "done");
  if (!done.length) return null;
  const total = done.reduce((a, s) => a + (isNum(s.ms) ? s.ms : 0), 0);
  const svc = new Set(done.flatMap((s) => String(s.service || "").split(" and ")).filter((x) => x && x !== "Python"));
  const bedrock = svc.has("Amazon Bedrock"), guard = svc.has("Bedrock Guardrails");
  const services = bedrock && guard ? "Amazon Bedrock and Guardrails" : bedrock ? "Amazon Bedrock" : guard ? "Bedrock Guardrails"
    : svc.size ? [...svc].join(" and ") : "Code only, no model";
  const recorded = isRecorded(r, opts) ? (recordedOn(r) ? `recorded on ${recordedOn(r)}` : "recorded earlier") : null;
  const skipped = arr(steps).filter((s) => obj(s) && s.status === "skipped").length;
  const head = `${done.length} step${done.length === 1 ? "" : "s"} in ${duration(total)}`;
  const text = svc.size ? `${head}, with ${services}.` : `${head}, all computed by code.`;
  const sub = [recorded && cap(recorded) + ".", skipped ? `${skipped} step${skipped === 1 ? "" : "s"} not run: no model in this run.` : null].filter(Boolean).join(" ") || null;
  /* R22: the closed stage shows the receipt without its timings (they fold behind "Show the details"): "Five steps, with …" */
  const count = WORDS_N[done.length] ? cap(WORDS_N[done.length]) : String(done.length);
  const short = `${count} step${done.length === 1 ? "" : "s"}, ${svc.size ? `with ${services}` : "all computed by code"}.`;
  return { steps: head, services, recorded, skipped, text, sub, short };
}
const WORDS_N = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

/* ---- READ: the navigator's reading as chips (move, family, precedents), who read it, the families it set aside ---- */
const KEYWORDS = { tariffs: ["tariff war", "tariffs", "tariff", "trade war", "new levies", "levies", "levy", "duties"], war_oil: ["oil shock", "oil", "war"],
  chips: ["chip war", "chips", "chip", "semiconductor"], rates: ["interest rates", "rate shock", "rates", "rate"] };
function cleanReason(label, why) {
  let t = String(why || "").trim();
  if (label && t.toLowerCase().startsWith(label.toLowerCase() + ":")) t = t.slice(label.length + 1).trim();
  return smart(t.replace(/;\s*best score[^;]*$/i, "").replace(/\.$/, "").trim());
}
const msAtLeast1 = (x) => (isNum(x) && x >= 1 ? duration(x) : "");
const stepTrace = (r, step) => arr((obj(r) || {}).trace).map(obj).filter((t) => t && t.step === step);

export function readingOf(r, opts) {
  r = obj(r) || {};
  const sc = obj(r.scenario) || {}, PF = PFx(), vo = voice(r);
  const mv = PF ? PF.moveOf(r) : null, change = obj(sc.change);
  const base = obj(obj(r.baseline) && r.baseline.portfolio) || {};
  let move;
  if (mv) {
    const before = isNum(base[mv.ticker]) ? base[mv.ticker] : 0, op = change && str(change.op);
    const pctText = share(mv.weight), n = unsigned(pctText).replace(/ %$/, "");
    move = op === "replace" && str(change.from_ticker)
      ? { value: `${change.from_ticker} → ${mv.name}`, sub: null, needles: [mv.name, mv.ticker, change.from_ticker] }
      : { value: `${mv.name} → ${pctText}`, sub: null, needles: [`${n} %`, `${n}%`, `${n} percent`, mv.name, mv.ticker] };
    Object.assign(move, { ticker: mv.ticker, name: mv.name, weight: mv.weight });
  } else move = { value: `${cap(vo.his)} mix, unchanged`, sub: "no move in the question", none: true, needles: [] };
  const fams = arr(sc.families).filter((f) => own(FAMILY, f));
  /* the AI's translation, visible (R8): the investor's own words the navigator read the shock from, when the Result carries them
     (scenario.read_from) and they stand in the question as written; never words the browser picked itself */
  const said = str(sc.read_from), from = said && str(r.question) && r.question.toLowerCase().includes(said.toLowerCase()) ? smart(said) : null;
  const quoted = !!from && !!obj(r.navigator_effect) && arr(r.navigator_effect.diffs).some((d) => obj(d) && d.what === "families");
  const family = fams.length ? { value: fams.map((f) => FAMILY[f]).join(", "), ids: fams, sub: null, from: from && !quoted ? `read from: ${from}` : null, said: from,
    needles: [from && said, ...fams.flatMap((f) => KEYWORDS[f] || [])].filter(Boolean) } : { value: "No shock named", sub: "every family replayed", ids: [], needles: [], none: true };
  const ck = arr(r.checks).map(obj).find((c) => c && c.rule === "scenario_stress");
  const t0 = fams.length && obj(obj(r.turbulence) && r.turbulence[fams[0]]);
  const n = t0 && isNum(t0.n) ? t0.n : ck && isNum(ck.n_episodes) ? ck.n_episodes : null;
  const precedents = n === null ? null : { value: `${n} earlier episode${n === 1 ? "" : "s"}`, sub: fams.length ? "on record" : "on record, every family",
    n, needles: family.needles };
  /* who read it: Amazon Bedrock only when a trace row proves a model answered (R15: never claim it otherwise) */
  const und = stepTrace(r, "UNDERSTAND"), turn = und.find((t) => t.service === "Amazon Bedrock" && str(t.model));
  const recorded = isRecorded(r, opts) ? (recordedOn(r) ? `recorded on ${recordedOn(r)}` : "recorded earlier") : null;
  const by = turn && str(sc.method) !== "fallback"
    ? { kind: "model", service: "Amazon Bedrock", model: modelName(turn.model), msText: duration(turn.ms), request: str(turn.request_id) ? turn.request_id.slice(0, 8) : null, recorded }
    : { kind: "rules", service: "Code rules", model: "keyword rules, no model", msText: msAtLeast1(und.filter((t) => !nested(t)).reduce((a, t) => a + (isNum(t.ms) ? t.ms : 0), 0)),
      request: null, recorded, why: str(sc.fallback_reason) };
  const rejected = Object.entries(obj(sc.rejected) || {}).map(([id, why]) => ({ id, label: FAMILY[id] || id, reason: cleanReason(FAMILY[id] || id, why) }))
    .filter((x) => x.label);
  const same = rejected.length > 1 && rejected.every((x) => x.reason === rejected[0].reason);
  const aside = !rejected.length ? null : same
    ? { labels: rejected.map((x) => x.label), reason: cap(rejected[0].reason.replace(/\bpoint to it$/, "point to them")) + "." }
    : { labels: rejected.map((x) => x.label), reasons: rejected.map((x) => `${x.label}: ${x.reason}.`) };
  return { question: str(r.question) && smart(r.question), who: vo.name,
    whose: !vo.name ? "The question" : /[?!]$/.test(vo.name) ? `The \u201c${vo.name}\u201d question` : `${vo.name}\u2019s question`, persona: vo.persona, mix: mv ? "this mix" : `${vo.his} mix`, move, family, precedents, by, rejected, aside,
    intent: str(sc.intent), stop: r.status === "clarify" || r.status === "blocked" ? str(r.message) : null };
}

/* where the words of a chip sit in the question, to select them for editing: [start, end] or null */
export function editRange(question, needles) {
  const q = String(question || ""), low = q.toLowerCase();
  for (const n of arr(needles).map(str).filter(Boolean)) {
    const i = low.indexOf(n.toLowerCase());
    if (i >= 0) return [i, i + n.length];
  }
  return null;
}

/* "3 Apr to 2 May 2025" (days) or "Jan to Apr 2025" (months), the year once when both ends share it */
function spanOf(a, b, days) {
  const F = fmt();
  if (!F || !str(a) || !str(b)) return null;
  const ya = a.slice(0, 4), yb = b.slice(0, 4), one = (d) => (days ? F.date(d) : F.month(d));
  const strip = (txt) => txt.replace(new RegExp(`[\\s\\u00a0]${ya}$`), "");
  return ya === yb ? `${strip(one(a))} to ${one(b)}` : `${one(a)} to ${one(b)}`;
}

/* the trading days from a shock's start to its window's end, counted on the Result's own daily series (null when the series is
   not daily, e.g. a weekly public cut: then the caption counts weeks) */
function tradingDays(r, t0, t1) {
  const ds = arr(obj(r.series) && r.series.dates).map(str).filter(Boolean);
  if (ds.length < 3) return null;
  const gap = (Date.parse(ds[ds.length - 1]) - Date.parse(ds[0])) / (ds.length - 1) / 864e5;
  if (!(gap < 2.5)) return null;
  return ds.filter((d) => d.slice(0, 10) > t0 && d.slice(0, 10) <= t1).length || null;
}
/* ---- EPICENTRE: the asked family's worst precedent (its deepest trough on the evaluated mix: after with a move, else today) ----
   The asked family is the first of scenario.families that holds a precedent the navigator picked (events[].picked), else the
   first family: families come in config order, so "China invades Taiwan" (war and oil + chips, every pick a chip event) flew to
   Tehran (lane navcheck). A relief event (sign "positive") is never the epicentre of a shock (ruling R29); only when the
   navigator picked a relief event of that family, which it does only when the words ask for relief. An abstention (no close
   precedent, nothing picked: pipeline._abstains) has no asked family: nothing was replayed, so the globe flies nowhere. */
export function askedFamilyOf(r) {
  const sc = obj(obj(r) && r.scenario);
  if (!sc || (obj(sc.weather) && sc.weather.no_precedent === true && !arr(sc.event_ids).length)) return null;
  const fams = arr(sc.families).map(str).filter(Boolean);
  const picked = arr(obj(r) && r.events).map(obj).filter((e) => e && e.picked === true);
  return fams.find((f) => picked.some((e) => e.family === f)) || fams[0] || null;
}
export function worstPrecedent(r) {
  r = obj(r) || {};
  const fam = askedFamilyOf(r);
  if (!fam) return null;
  const PF = PFx(), move = PF ? PF.moveOf(r) : null;
  const relief = arr(r.events).map(obj).some((e) => e && e.family === fam && e.picked === true && e.sign === "positive");
  let best = null;
  for (const e of arr(r.events).map(obj)) {
    if (!e || e.family !== fam || !isNum(e.lat) || !isNum(e.lon) || !str(e.date)) continue;
    if (e.sign === "positive" && !relief) continue;
    const side = obj(move ? e.after : e.today), t = side && isNum(side.trough) ? side.trough : null;
    if (t === null) continue;
    if (!best || t < best.trough || (t === best.trough && e.date < best.date)) best = { e, trough: t, date: e.date.slice(0, 10) };
  }
  if (!best) return null;
  const e = best.e, t0 = str(e.t0) ? e.t0.slice(0, 10) : best.date, t1 = str(e.window_end) ? e.window_end.slice(0, 10) : null;
  const b = arr(r.breaches).map(obj).find((x) => x && isNum(x.depth) && str(x.peak_date) && str(x.trough_date)
    && x.peak_date.slice(0, 10) <= best.date && best.date <= x.trough_date.slice(0, 10));
  return { id: str(e.event_id) || best.date, date: best.date, dateText: dateText(best.date), title: str(e.title) && smart(e.title), place: str(e.place) && smart(e.place),
    lat: e.lat, lon: e.lon, family: fam, familyLabel: FAMILY[fam], noun: NOUN[fam], trough: best.trough, troughText: pct(best.trough),
    windowText: t1 ? spanOf(t0, t1, true) : null,
    windowDays: t1 ? tradingDays(r, t0, t1) : null, windowWeeks: t1 ? Math.round((Date.parse(t1) - Date.parse(t0)) / 6048e5) || null : null,
    fall: b ? { depth: b.depth, ddText: pct(b.depth), span: spanOf(b.peak_date, b.trough_date, false) } : null };
}

/* ---- VERDICT: the lamp (the server's verdict, or curve[i].verdict when the dial moved), its qualifier and the sentences ---- */
const closest = (curve, w) => {
  let k = null;
  curve.forEach((c, i) => { if (obj(c) && isNum(c.weight) && (k === null || Math.abs(c.weight - w) < Math.abs(curve[k].weight - w))) k = i; });
  return k;
};
const curveOf = (r) => arr(obj(obj(r) && r.tipping_point) && r.tipping_point.curve);
export function askedIndex(r) {
  const PF = PFx(), mv = PF && obj(r) ? PF.moveOf(r) : null, curve = curveOf(r);
  return mv && curve.length ? closest(curve, mv.weight) : null;
}
export function todayIndex(r) {
  const tp = obj(obj(r) && r.tipping_point), curve = curveOf(r);
  if (!tp || !curve.length) return null;
  const base = obj(obj(r.baseline) && r.baseline.portfolio) || {};
  return closest(curve, isNum(base[tp.ticker]) ? base[tp.ticker] : 0);
}

/* a size on the dial other than the one asked is a what-if, never a verdict (R20): the verdict words stay with the move asked, a
   what-if is never green, and its words are the page's one floor vocabulary (web/lib/status.js FLOOR_WORDS, lane U5). The class
   is the size ruler's own (lane U4, web/lib/dial.js), so the lamp and the ruler beside it always agree: broke = the server's
   verdict at that size is Incompatible (the floor is governance's one hard rule); a size that held is "touched" when its fall
   came within 1 point of the floor, in governance's tenths of a point (pitfall 5); else "held above". */
const TONE = { broke: { tone: "outside", icon: "i-out" }, touched: { tone: "caveat", icon: "i-warn" }, held: { tone: "held", icon: null } };
export function whatIfOf(r, weightIndex) {
  r = obj(r);
  const PF = PFx(), c = r && Number.isInteger(weightIndex) ? obj(curveOf(r)[weightIndex]) : null;
  if (!c || weightIndex === askedIndex(r)) return null;
  const floor = (obj(r.limits) || {}).floor, mv = PF ? PF.moveOf(r) : null;
  const tn = PF && PF.tenths;
  const state = c.verdict === "Incompatible" ? "broke"
    : isNum(c.max_drawdown) && isNum(floor) && tn && tn(c.max_drawdown) - tn(floor) <= 10 ? "touched" : "held";
  return { state, word: FLOOR_WORDS[state], ...TONE[state], weight: c.weight,
    caption: mv ? `What-if at ${share(c.weight)} ${mv.name} instead of the ${share(mv.weight)} you asked. A replay, not a recommendation.` : null };
}
export function lampOf(r, weightIndex) {
  r = obj(r);
  const PF = PFx(), V = (PF && PF.VERDICT) || {};
  if (!r || !own(r, "verdict")) return null;
  const qualifier = replayYears(r) ? `in this ${replayYears(r)} replay` : "in this replay";
  const w = whatIfOf(r, weightIndex);
  if (w) return { ...w, key: null, whatIf: true, qualifier };
  const key = r.verdict;
  const base = key === null ? { key: null, word: "No limits set", tone: "none", icon: "i-pending" } : own(V, key) ? { key, ...V[key] } : null;
  return base ? { ...base, whatIf: false, caption: null, qualifier: key === null ? "the replay shows everything that happened; add a limit to compare" : qualifier } : null;
}

/* the phone's pill right under the question: the verdict at the size asked; at any other size (R20) only what that size did to
   the floor, in the same words and tone as the lamp (never a verdict word, never green), with "what-if at 8 % NVIDIA" */
export function pillOf(r, weightIndex) {
  const lamp = lampOf(r, weightIndex);
  if (!lamp) return null;
  if (!lamp.whatIf) return { tone: lamp.tone, icon: lamp.icon, word: lamp.word, rest: `, ${lamp.qualifier}`, whatIf: false };
  const PF = PFx(), mv = PF ? PF.moveOf(r) : null;
  return { tone: lamp.tone, icon: lamp.icon, word: lamp.word, rest: `, what-if at ${share(lamp.weight)}${mv ? ` ${mv.name}` : ""}`, whatIf: true };
}

export function withoutLine(r) {
  const PF = PFx(), v = PF && obj(r) ? PF.view(r) : null;
  if (!v || !v.move || !v.today || r.verdict === null) return null;      // no limits set: no "Without the move" line
  return { text: `Without the move: ${v.today.word.charAt(0).toLowerCase()}${v.today.word.slice(1)}.`, tone: v.today.tone, icon: v.today.icon };
}

/* the check that decided the lamp when neither sentence names it (R14: values for Mateo, crypto for Amira): the server's first
   deciding row (PF.view's order: status, then check_order) with its own code-written reason, drawn in the lamp's tone, never a
   second, contradictory status */
const CHECK_WORDS = { esg_direct: "your values", esg_indirect: "your values, inside your funds", crypto: "crypto", single_stock: "one company",
  sector: "one sector", risk_concentration: "where the risk sits", recovery: "time to recover", short_horizon: "your horizon", missing_data: "data gaps" };
/* the check that decided an outside verdict: the server's first failing hard limit, in PF.view's order (status, then
   check_order); null when none is named (the floor sentence then stands) */
export function decidingCheck(r) {
  const PF = PFx();
  if (!PF || !obj(r) || r.verdict !== "Incompatible") return null;
  for (const row of arr(PF.view(r).rows)) {
    const raw = arr(r.checks).map(obj).find((c) => c && c.rule === row.rule);
    if (raw && raw.status === "fail" && raw.tier === "hard") return raw;
  }
  return null;
}
export function decidingLine(r) {
  const PF = PFx();
  if (!PF || !obj(r) || r.verdict === "Compatible") return null;     // inside: nothing decided against the move (cautions: #checklist)
  if (r.verdict === "Incompatible") return null;                     // outside: the answer sentence names the check that decided it
  const row = arr(PF.view(r).rows)[0];
  if (!row || row.status === "pass" || row.rule === "max_drawdown" || row.rule === "scenario_stress") return null;
  const text = smart(str(row.reason) || str(row.compare) || "");
  /* the page's one status vocabulary (web/lib/status.js bindingWord, as #checklist marks the row): a caveat names the check that
     added it, an outside verdict the check that decided it, in the investor's words */
  const raw = arr(r.checks).map(obj).find((c) => c && c.rule === row.rule);
  const bw = raw ? bindingWord(raw.status, raw.tier) : null;
  const lead = `The check that ${(bw || (r.verdict === "Tension" ? "Added the caveat" : "Decided the verdict")).toLowerCase()}:`;
  return text ? { rule: row.rule, name: CHECK_WORDS[row.rule] || String(row.name || "").toLowerCase(), lead, text } : null;
}

/* sentence 1, the money (R13): the worst fall, the same fall on the amount, the floor named by its source and by whose it is */
export function moneyLine(r) {
  /* R35: the fall in the path's own dollars (the deepest breach's peak and trough values), never "the same fall on your
     $600,000", and the 15 % rule never called "the $90,000 set as your limit" (the capacity is its own line: the twist) */
  r = obj(r) || {};
  const vo = voice(r), v = vo.v, move = v.move, side = move ? v.fall && v.fall.after : v.fall && v.fall.today;
  if (!side || !side.ddText) return null;
  const lead = move ? [["With "], [move.weightText, "num"], [` in ${move.name}, this mix fell `]] : [[`${cap(vo.his)} mix fell `]];
  const out = seg(...lead, [unsigned(side.ddText), "num"], [" at its worst"]);
  const deep = arr(r.breaches).map(obj).filter((x) => x && isNum(x.depth)).sort((x, y) => x.depth - y.depth)[0];
  if (deep && isNum(deep.peak_value) && isNum(deep.trough_value) && isNum(side.dd) && Math.abs(deep.depth - side.dd) < 5e-4)
    out.push([", from "], [money(deep.peak_value), "num"], [" to "], [money(deep.trough_value), "num"],
      ...(isNum(deep.fall_dollars) ? [[" ("], [money(deep.fall_dollars), "num"], [")"]] : []));
  out.push(["."]);
  const md = arr(r.checks).map(obj).find((c) => c && c.rule === "max_drawdown" && (c.status === "fail" || c.status === "pass"));
  if (md && v.floor && isNum(v.floor.v)) {
    out.push([md.status === "fail" ? ` That broke ${vo.his} floor: no fall of more than ` : ` That stayed inside ${vo.his} floor: no fall of more than `],
      [unsigned(share(v.floor.v)), "num"], [" from any high"]);
    out.push([vo.mine("floor") ? ", typed by you." : `${PERSONA_NOTE}.`]);
  }
  return out;
}

/* sentence 2, the asked shock, in the past tense (R1): the shock check's own count, worst loss, limit and status */
export function shockLine(r) {
  r = obj(r) || {};
  const PF = PFx(), vo = voice(r), move = PF ? PF.moveOf(r) : null;
  const c = arr(r.checks).map(obj).find((x) => x && x.rule === "scenario_stress" && ["warn", "pass", "fail"].includes(x.status));
  if (!c) return null;
  const tidy = (s) => (PF && PF.tidyReason ? PF.tidyReason(s) : String(s || ""));
  if (!isNum(c.value) || /^(Only \d+ clean|No clean|There is no close)/.test(String(c.reason || ""))) return { segs: seg([tidy(c.reason)]), evidence: null };
  const fams = arr(obj(r.scenario) && r.scenario.families).filter((f) => own(FAMILY, f));
  const t = fams.length === 1 ? obj(obj(r.turbulence) && r.turbulence[fams[0]]) : null;
  const n = isNum(c.n_episodes) ? c.n_episodes : t && isNum(t.n) ? t.n : null;
  const limit = isNum(c.limit) ? c.limit : null;
  if (n === null || limit === null) return { segs: seg([tidy(c.reason)]), evidence: null };
  const noun = fams.length === 1 ? NOUN[fams[0]] : "shock", over = c.status !== "pass";
  const whose = vo.persona && !vo.edited.has("scenario_stress") && !vo.edited.has("floor") ? " assumed for this profile"
    : vo.edited.has("scenario_stress") ? " you entered" : ", half your floor";
  return { segs: seg(["In the "], [String(n), "num"], [` ${noun} episode${n === 1 ? "" : "s"} on record, ${move ? "this mix" : vo.his + " mix"} lost up to `],
    [unsigned(pct(c.value)), "num"], [` within a shock\u2019s window, ${over ? "more than" : "within"} the `], [unsigned(share(limit)), "num"], [` shock limit${whose}.`]),
    evidence: t && str(t.evidence) ? t.evidence : null };
}

/* the money twist (R3): ended higher, yet broke the floor on the way. Both facts are Result keys: the two end values
   (tipping_point.curve, or the series' first and last day when nothing changed) and the count of breaches[]. */
/* R35 two limits: the tolerance rule (the floor, "your 15 % rule") and the capacity (result.capacity, "the $510,000 you can
   afford"); the capacity's own fields as lane fin-backend writes them (read defensively; the clause hides without them) */
const firstNum = (...xs) => xs.find(isNum);
const yearOf = (d) => (str(d) && /^\d{4}/.test(d) ? d.slice(0, 4) : null);
export function capacityOf(r) {
  /* result.capacity (lane fin-backend): {line, today: side, after: side}; a side {falls_below, first_below, last_below, status,
     low_value, low_date}; the side of the mix this stage answers for (with the move when there is one) */
  const c = obj(obj(r) && r.capacity), PF = PFx();
  if (!c || !isNum(c.line)) return null;
  const mv = PF ? PF.moveOf(r) : null, side = obj(mv ? c.after : c.today);
  if (!side || !isNum(side.falls_below)) return null;
  const n = side.falls_below, ys = [yearOf(side.first_below), n >= 2 ? yearOf(side.last_below) : null].filter(Boolean);
  const ld = str(side.low_date) ? String(side.low_date).slice(0, 7) : null, MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const lowWhen = ld && /^\d{4}-\d{2}$/.test(ld) ? `${MON[Number(ld.slice(5, 7)) - 1]}${NB}${ld.slice(0, 4)}` : null;
  return { line: c.line, lineText: money(c.line), n, years: [...new Set(ys)], lowText: isNum(side.low_value) ? money(side.low_value) : null, lowWhen };
}
const timesWord = (n) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);
function yearsText(years) {
  const u = [...new Set(years)];
  if (!u.length) return "";
  if (u.length === 1) return ` in${NB}${u[0]}`;
  if (u.length === 2) return ` in${NB}${u[0]} and again in${NB}${u[1]}`;
  return `, first in${NB}${u[0]}`;
}
export function ruleText(r) {                       // ONE NAME on the stage (controller, 17:05): the floor, R20's word
  return "your floor";
}
/* the floor defined once, at its first mention (the answer under the lamp): "your floor (no fall of more than 15 % from a high)" */
export function floorDef(r) {
  const f = (obj(obj(r) && r.limits) || {}).floor;
  return isNum(f) ? `your floor (your limit on the biggest drop: ${unsigned(share(f))} from a high)` : "your floor";
}
export function twistLine(r) {
  r = obj(r) || {};
  const bs = arr(r.breaches).filter((b) => obj(b) && isNum(b.depth));
  if (!bs.length) return null;
  const curve = curveOf(r), a = askedIndex(r), z = todayIndex(r);
  let higher = null, than = "", ends = null;
  if (a !== null && z !== null && a !== z && isNum((obj(curve[a]) || {}).end_value) && isNum((obj(curve[z]) || {}).end_value)) {
    higher = curve[a].end_value > curve[z].end_value;
    ends = { after: money(curve[a].end_value), today: money(curve[z].end_value) };
  } else if (a === null) {
    const sr = arr(obj(r.series) && r.series.today);
    if (isNum(sr[0]) && isNum(sr[sr.length - 1])) { higher = sr[sr.length - 1] > sr[0]; than = " than it started"; }
  }
  if (higher !== true) return null;
  /* the answer right above names the years; the twist counts them (trim, don't stack) */
  const broke = `Broke ${ruleText(r)} ${timesWord(bs.length)} on the way`;
  const cap = capacityOf(r);
  const capText = !cap ? "" : cap.n === 0 ? `; stayed above the ${cap.lineText} you can afford` : `; fell below the ${cap.lineText} you can afford ${timesWord(cap.n)}${cap.years.length && cap.years.length <= 2 ? yearsText(cap.years).replace(/^ in/, ", in") : ""}`;
  if (cap && cap.n > 0 && cap.lowText && cap.lowWhen) {
    const endsText = ends ? ` (${ends.after} against ${ends.today} today)` : "";
    return { segs: seg([`Would have fallen to ${cap.lowText} in ${cap.lowWhen}, below the ${cap.lineText} you can afford. `], [`Ended higher${than}${endsText}; ${broke.charAt(0).toLowerCase()}${broke.slice(1)}.`, "small"]),
      ends, breaches: bs.length, capacity: cap };
  }
  return { segs: seg([`Ended higher${than}. `], [`${broke}${capText}.`]), ends, breaches: bs.length, capacity: cap };
}

/* ---- the start-month line under the stage's ruler (the cut #dial's one unique fact, lane U4's band: the same numbers) ---- */
export function bandLine(r) {
  const PF = PFx(), m = PF && obj(r) ? dialModel(r, PF) : null;
  if (!m) return null;
  if (m.everyStart) return seg(["Whatever the start month, your floor did not break."]);
  const b = m.band;
  if (!b || !b.loText) return null;
  /* F6: say why the band is wide, from the band's own starts: the first starts' first break (within a point) and the last
     starts' (all at the top). The falls are named only when each start carries the date of its first break (lane fin-backend) */
  const st = arr(obj(r.tipping_band) && r.tipping_band.starts).map(obj).filter((x) => x && str(x.start) && isNum(x.first_break))
    .sort((x, y) => (x.start < y.start ? -1 : 1));
  if (st.length >= 4) {
    const lo = st[0].first_break, hiV = st[st.length - 1].first_break;
    let i = 0; while (i < st.length && st[i].first_break - lo <= 0.0101) i++;
    let j = st.length - 1; while (j > 0 && st[j - 1].first_break === hiV) j--;
    if (i <= j && hiV > st[i - 1].first_break + 0.0101) {
      const F = fmt(), mon = (ym) => F.month(`${ym.slice(0, 7)}-01`), bare = (x) => unsigned(share(x)).replace(/[\s\u00a0]?%$/, "");
      const r1 = st[i - 1].first_break === lo ? share(lo) : `${bare(lo)}\u2013${share(st[i - 1].first_break)}`, after = mon(st[j - 1].start);
      const d1 = str(st[0].break_date || st[0].first_break_date), d2 = str(st[j].break_date || st[j].first_break_date);
      if (d1 && d2 && yearOf(d1) && yearOf(d2) && yearOf(d1) !== yearOf(d2)) {
        const mo = Number(d2.slice(5, 7)), when = mo <= 4 ? "early " : mo >= 9 ? "late " : "mid-";
        return seg(["Two falls decide it: "], [yearOf(d1), "num"], [" breaks it from "], [r1, "num"], [`; for starts after ${after} only ${when}`], [yearOf(d2), "num"],
          [" does, from "], [share(hiV), "num"], ["."]);
      }
      return seg(["Depending on the start month, your floor first broke at "], [r1, "num"], [` (starts to ${mon(st[i - 1].start)}) or at `], [share(hiV), "num"],
        [` (starts after ${after}).`]);
    }
  }
  const held = b.held ? ` From ${b.held} of the ${b.n} start months it did not break at all.` : "";
  if (b.iLo === b.iHi) return seg(["Whatever the start month, your floor first broke at the same "], [b.loText, "num"], ["." + held]);
  return seg(["Depending on the start month, your floor first broke between "], [b.loText, "num"], [" and "], [b.hiText, "num"], ["." + held]);
}

/* ---- defect 4: the race's callout at the asked shock measures its fall from the high before it (Jan 2025 for "Liberation Day",
   so it holds January's chip sell-off too). When that high came before the shock, the callout's name says so: "From the Jan 2025
   high, through “Liberation Day”", apart from the epicentre's own fall over the shock's trading days. A copy of lane U3's model;
   its numbers are untouched. ---- */
export function relabelFalls(model, r) {
  r = obj(r);
  if (!obj(model) || !r || !Array.isArray(model.breaches)) return model;
  const F = fmt();
  const breaches = model.breaches.map((b) => {
    if (!obj(b) || b.labelKind !== "event" || !str(b.eventId) || !str(b.peakDate) || !F) return b;
    const e = arr(r.events).map(obj).find((x) => x && x.event_id === b.eventId);
    if (!e || !str(e.date) || !(b.peakDate.slice(0, 10) < e.date.slice(0, 10)) || b.peakDate.slice(0, 7) === e.date.slice(0, 7)) return b;
    const t = String(e.title || ""), q = /^["\u201c]([^"\u201d]+)["\u201d]/.exec(t), name = q ? `\u201c${q[1]}\u201d` : smart(t);
    return { ...b, label: `From the ${F.month(b.peakDate)} high, through ${name}` };
  });
  return { ...model, breaches };
}

/* ---- R36 robustness facts, each computed by code (lane fin-backend's keys; a line hides when its key is absent) ---- */
export function peerLine(r) {
  r = obj(r);
  const p = obj(r && r.peer_check), PF = PFx(), mv = PF && r ? PF.moveOf(r) : null;
  if (!p) return null;
  const n = firstNum(p.n, p.n_peers, p.total, p.pack), up = firstNum(p.higher, p.ended_higher, p.n_higher);
  const broke = firstNum(p.broke, p.n_broke, p.breaks, p.broke_floor), w = firstNum(p.weight, p.at, mv && mv.weight);
  if (!isNum(n) || !isNum(up) || !isNum(broke) || !isNum(w)) return null;
  return seg(["In this window "], [String(up), "num"], [` of the pack\u2019s `], [String(n), "num"], [" stocks, at the same "], [share(w), "num"],
    [", would also have ended higher (today\u2019s survivors); "], [String(broke), "num"], [` broke ${ruleText(r)}.`]);
}
const NEVER = (r) => (obj(r) && obj(r.never_rebalanced)) || null;       // lane fin-backend: result.never_rebalanced
export function robustLine(r) {
  r = obj(r);
  if (!r) return null;
  const out = [], f = obj(r.funding_check);
  if (f) {
    const ways = arr(f.ways || f.rows || f.fundings).map(obj).filter((w) => w && isNum(w.max_drawdown));
    const lo = firstNum(f.deepest, ways.length ? Math.min(...ways.map((w) => w.max_drawdown)) : undefined);
    const hi = firstNum(f.mildest, ways.length ? Math.max(...ways.map((w) => w.max_drawdown)) : undefined);
    const holds = typeof f.same_verdict === "boolean" ? f.same_verdict : typeof f.holds === "boolean" ? f.holds
      : ways.length && ways.every((w) => w.verdict === r.verdict) ? true : null;
    const k = firstNum(f.n, ways.length || undefined);
    const mild = isNum(lo) && isNum(hi) ? (Math.abs(lo) < Math.abs(hi) ? lo : hi) : null, deep = mild === lo ? hi : lo;   // mildest first
    if (isNum(mild) && isNum(k)) out.push(`Funded ${WORDS_N[k] || k} ways: worst fall ${pct(mild)} to ${pct(deep)}${holds === true ? "; the answer holds" : holds === false ? "; the answer changes with how it is funded" : ""}.`);
  }
  const nv = NEVER(r), PF = PFx(), mv = PF ? PF.moveOf(r) : null;
  if (nv) {
    const w = firstNum(nv.end_weight), n = firstNum(nv.breaks);
    if (isNum(w) && isNum(n) && mv) out.push(`Never rebalanced: ${mv.name} grows to ${share(w)}; ${ruleText(r)} breaks ${n === 1 ? "once" : n === 2 ? "twice" : (WORDS_N[n] || n) + " times"}.`);
  }
  return out.length ? out.join(" ") : null;
}

/* ---- where the money for the move comes from (the case's governance line: flag missing information). The Result's own change:
   a from_ticker the words named, else the replay's assumption (every other holding scaled by the same factor), marked as an assumption ---- */
export function fundingLine(r) {
  r = obj(r);
  const PF = PFx(), mv = PF && r ? PF.moveOf(r) : null, change = r && obj(obj(r.scenario) && r.scenario.change);
  if (!mv) return null;
  const from = change && str(change.from_ticker);
  if (from) {
    const label = plainLabel(from);
    const plain = label && /^(Gold|Cash|Bonds|Stocks|Short)\b/.test(label) ? label.charAt(0).toLowerCase() + label.slice(1) : label;   // "Canadian" keeps its capital
    return { kind: "said", text: label && label !== from ? `Taken from your ${plain} (${from}), as your words said.` : `Taken from ${from}, as your words said.` };
  }
  const base = obj(obj(r.baseline) && r.baseline.portfolio) || {}, before = isNum(base[mv.ticker]) ? base[mv.ticker] : 0;
  const up = mv.weight >= before;
  return { kind: "assumed", text: up
    ? `Your words didn\u2019t say where the ${share(mv.weight)} comes from, so the replay took it from every other holding in proportion (assumed).`
    : `Your words didn\u2019t say where the money goes, so the replay added it to every other holding in proportion (assumed).` };
}

/* ---- the AI's value, visible (R8): one line from result.navigator_effect (proofs.navigator_effect: the navigator's reading against
   the keyword rules' reading of the same words), shown only when the two read a different shock family ---- */
const AS = { tariffs: "the tariff war", war_oil: "a war and oil shock", chips: "the chip war", rates: "a rate shock" };
const asFams = (fs) => fs.filter((f) => own(AS, f)).map((f) => AS[f]).join(" and ");
export function effectLine(r) {
  r = obj(r);
  const ne = r && obj(r.navigator_effect), row = ne && arr(ne.diffs).map(obj).find((d) => d && d.what === "families");
  if (!row) return null;
  const nav = arr(row.navigator).map(str).filter(Boolean), kw = arr(row.fallback).map(str).filter(Boolean);
  const said = readingOf(r).family.said, words = said ? `\u201c${said}\u201d` : "your words";
  const a = asFams(nav), b = asFams(kw);
  if (nav.length && !a) return null;
  if (kw.length && !b) return null;
  const lead = a ? `The AI reader read ${words} as ${a}` : `The AI reader found no shock named in ${words}`;   // R28: "the AI reader"
  return { text: `${lead}; a plain word search ${b ? `read them as ${b}` : "found no shock"}.`, navigator: nav, fallback: kw };
}
/* the blind held-out measure behind it (web/eval_results.json holdout_v2, lane B5): "On 48 blind questions …"; null without it */
export function evalLine(ev) {
  const h = obj(obj(ev) && ev.holdout_v2);
  if (!h || !isNum(h.n) || !isNum(h.navigator_k) || !isNum(h.keyword_k)) return null;
  return `On ${h.n} blind questions the AI reader read the shock right ${h.navigator_k} times, a plain word search ${h.keyword_k}.`;
}

/* ---- R22, clarity first: the stage opens with one plain question and one answer sentence (second person, past tense), the
   lamp under it; everything else folds behind one "Show the details" ---- */
/* advice_guard.REFRAME_LINE, word for word: a question that asked for approval runs, reframed (Result `reframe` {reason}) */
export const REFRAME_LINE = "EPICENTRE can't tell you whether a move is right for you. Here is what it already did against the limits you set.";
export function reframeLine(r) {
  r = obj(r);
  return r && r.reframe !== undefined && r.reframe !== null && r.reframe !== false ? smart(REFRAME_LINE) : null;
}
/* a question about a shock and no move (Mateo, Amira): the shock check answers it (R39) */
export function shockQuestion(r) {
  r = obj(r);
  const PF = PFx();
  if (!r || !PF || PF.moveOf(r) || !askedFamilyOf(r)) return null;
  const c = arr(r.checks).map(obj).find((x) => x && x.rule === "scenario_stress" && isNum(x.value) && isNum(x.limit) && ["pass", "warn", "fail"].includes(x.status));
  return c ? { check: c, family: askedFamilyOf(r) } : null;
}
export function askLine(r) {
  r = obj(r);
  if (!r) return null;
  const PF = PFx(), mv = PF ? PF.moveOf(r) : null, fams = arr(obj(r.scenario) && r.scenario.families).filter((f) => own(FAMILY, f));
  return mv ? "Would this move have broken your limit?" : fams.length ? "Would this shock have broken your limit?" : "Would your mix have broken your limit?";
}
/* each limit by its name in the investor's words (the status vocabulary of #checklist: "your floor", "your values screen") */
const LIMIT_NAME = { max_drawdown: "your floor", scenario_stress: "your shock limit", esg_direct: "the companies you avoid",
  esg_indirect: "the companies you avoid, inside your funds", crypto: "your crypto limit", single_stock: "your one-company limit",
  sector: "your sector limit", risk_concentration: "your limit on where the risk sits", recovery: "your time-to-recover limit",
  short_horizon: "your horizon", missing_data: "the data check" };
/* the year a floor breach first went below the floor (below_floor's first span), else its trough's */
function breachYear(b) {
  const first = arr(b.below_floor).map((x) => (Array.isArray(x) ? str(x[0]) : str(x))).find(Boolean);
  const d = first || str(b.trough_date) || str(b.peak_date);
  return d && /^\d{4}/.test(d) ? d.slice(0, 4) : null;
}
/* the answer: "Yes: your floor broke in 2022 and again in 2025." from the verdict and the Result's floor breaches (the same
   count as the twist). A reframed question gets no yes or no (advice_guard: a yes / no to "is it right for me?" reads as advice) */
export function answerLine(r) {
  r = obj(r);
  if (!r || !own(r, "verdict") || r.verdict === null) return null;
  const plain = !reframeLine(r), yes = (t) => (plain ? `Yes: ${t}` : cap(t)), no = (t) => (plain ? `No: ${t}` : cap(t));
  const dk = r.verdict === "Incompatible" ? decidingCheck(r) : null;
  const sq = shockQuestion(r);
  if (sq) {                                     // R39: "would this shock have broken your limit?" answered for the shock
    const c = sq.check, open = [[" ("], [pct(c.value), "num"], [" against "], [unsigned(share(c.limit)), "num"]];
    const other = dk && dk.rule !== "scenario_stress";   // the verdict was decided by another check: said in the same breath (cold user 3)
    let reason = null;
    if (other) {
      const what = LIMIT_NAME[dk.rule] || `your ${String(dk.name || "limit").toLowerCase()} limit`;
      const why = dk.rule === "esg_direct" && str(dk.holding) ? ` (you own ${dk.holding} directly)` : dk.rule === "max_drawdown" ? ` (it broke${yearsText(arr(r.breaches).filter((b) => obj(b) && isNum(b.depth)).map(breachYear).filter(Boolean))})` : "";
      reason = `${what}${why}`;
    }
    const out = c.status === "pass"
      ? seg([no("the shock stayed inside your limit")], ...open, [other ? `), but your mix is outside for another reason: ${reason}.` : ")."])
      : seg([yes("the shock went past your limit")], ...open, [")."]);
    if (other && c.status !== "pass") out.push([` Your mix is outside for another reason: ${reason}.`]);
    return { segs: out, tone: c.status === "pass" && !dk ? "inside" : "outside", rule: dk ? dk.rule : "scenario_stress", shock: true };
  }
  if (dk && dk.rule !== "max_drawdown") {
    const what = LIMIT_NAME[dk.rule] || `your ${String(dk.name || "limit").toLowerCase()} limit`;
    if (dk.rule === "esg_direct" && str(dk.holding)) return { segs: seg([yes(`you own ${dk.holding} directly, one of the companies you avoid.`)]), tone: "outside", rule: dk.rule };
    if (dk.rule === "esg_indirect") return { segs: seg([yes("your funds own companies you avoid.")]), tone: "outside", rule: dk.rule };
    return { segs: seg([yes(`${what} broke.`)]), tone: "outside", rule: dk.rule };
  }
  if (r.verdict === "Incompatible") {
    const years = arr(r.breaches).filter((b) => obj(b) && isNum(b.depth)).map(breachYear);
    const known = years.filter(Boolean), uniq = [...new Set(known)];
    if (!years.length || known.length !== years.length) return { segs: seg([yes(`${floorDef(r)} broke.`)]), tone: "outside" };
    /* "in 2022" never splits across two lines (a no-break space before each year) */
    if (years.length === 1) return { segs: seg([yes(`${floorDef(r)} broke in${NB}`)], [known[0], "num"], ["."]), tone: "outside" };
    if (years.length === 2 && uniq.length === 2) return { segs: seg([yes(`${floorDef(r)} broke in${NB}`)], [known[0], "num"], [` and again in${NB}`], [known[1], "num"], ["."]), tone: "outside" };
    if (uniq.length === 1) return { segs: seg([yes(`${floorDef(r)} broke ${years.length === 2 ? "twice" : years.length + " times"} in${NB}`)], [known[0], "num"], ["."]), tone: "outside" };
    return { segs: seg([yes(`${floorDef(r)} broke ${years.length} times, first in${NB}`)], [known[0], "num"], ["."]), tone: "outside" };
  }
  if (r.verdict === "Tension") return { segs: seg([no(`${floorDef(r)} held, but one check added a caveat.`)]), tone: "caveat" };
  if (r.verdict === "Compatible") return { segs: seg([no("it stayed inside your limits.")]), tone: "inside" };
  return null;
}
/* F7: the shock limit is a rule of thumb, half the 15 % rule, when the Result's two limits say exactly that */
const tenthsOf = (x) => Math.round(Math.abs(x) * 1000);
function thumb(r, limit) {
  const f = (obj(r.limits) || {}).floor;
  return isNum(f) && isNum(limit) && tenthsOf(limit) * 2 === tenthsOf(f) ? ` (a rule of thumb: half your ${unsigned(share(f))} floor)` : "";
}
const SHOCK_NOUN = { tariffs: "tariff", war_oil: "war and oil", chips: "chip war", rates: "rate" };
export function shockAskedLine(r) {
  r = obj(r);
  if (r && shockQuestion(r)) return null;       // a shock question: the answer itself gives the shock against its limit
  const ev = r && worstPrecedent(r), c = r && arr(r.checks).map(obj).find((x) => x && x.rule === "scenario_stress");
  if (!ev || !c || !isNum(c.value) || !isNum(c.limit) || !own(SHOCK_NOUN, ev.family)) return null;
  const when = ev.windowDays ? [[" in "], [String(ev.windowDays), "num"], [" trading days"]] : ev.windowWeeks ? [[" in the "], [String(ev.windowWeeks), "num"], [ev.windowWeeks === 1 ? " week after it" : " weeks after it"]] : [];
  return seg([`The ${SHOCK_NOUN[ev.family]} shock you asked about: `], [pct(c.value), "num"], ...when,
    [`, ${c.status !== "pass" ? "past" : "within"} your `], [unsigned(share(c.limit)), "num"], [` shock limit${thumb(r, c.limit)}.`]);
}
export function floorBrokeLine(r) {
  r = obj(r);
  const md = r && arr(r.checks).map(obj).find((x) => x && x.rule === "max_drawdown");
  if (!md || md.status !== "fail") return null;
  const deep = arr(r.breaches).map(obj).filter((b) => b && isNum(b.depth)).sort((a, b) => a.depth - b.depth)[0];
  const y = deep && breachYear(deep);
  return deep && y ? seg(["What broke your floor: the "], [y, "num"], [" fall, "], [pct(deep.depth), "num"], ["."]) : null;
}
/* 3. one proof line, from the receipt, the trace and the guardrail keys (R15: words of a recorded run, never a live badge) */
export function proofLine(r) {
  r = obj(r);
  if (!r) return null;
  const rc = obj(r.receipt), parts = [];
  if (rc && isNum(rc.verified) && isNum(rc.total) && rc.total > 0)
    parts.push(rc.verified === rc.total ? `Every number checked by code: ${rc.verified} of ${rc.total}.` : `Numbers checked by code: ${rc.verified} of ${rc.total} traced.`);
  const rd = readingOf(r), g = obj(r.guardrail), guard = !!(g && (obj(g.input) || obj(g.output)));
  const by = rd.by.kind === "model" ? `Read by ${/^Claude\b/.test(rd.by.model || "") ? "Claude" : rd.by.model || "a model"} on Amazon Bedrock` : "Read by code rules, no model";
  parts.push(`${by}${guard ? ", with Guardrails on" : ""}.`);
  return parts.join(" ");
}

/* the epicentre's caption: the shock's own fall, labelled by what it measures (its trading days), never the fall from a high (the
   chart labels that one) */
export function epiLines(ev, mix) {
  if (!obj(ev)) return null;
  return { title: ev.title || ev.familyLabel || "", where: [ev.dateText, ev.place].filter(Boolean).join(", "),
    why: `Deepest ${ev.noun} shock for ${mix || "this mix"}`, fig: ev.troughText,
    win: ev.windowDays ? ` in the shock\u2019s ${ev.windowDays} trading days` : ev.windowWeeks ? ` in the ${ev.windowWeeks === 1 ? "week" : ev.windowWeeks + " weeks"} after it`
      : " in the shock\u2019s window" };
}
/* every string the closed end frame shows (R22's count: at most about 6 figures besides the chart's, the ruler's and the
   labels: the replay's years, the recorded date and the shock's date and place) */
export function closedTexts(r, weightIndex = null) {
  r = obj(r);
  if (!r) return { figures: [], labels: [] };
  const rd = readingOf(r), ev = worstPrecedent(r), ep = epiLines(ev, rd.mix), lamp = lampOf(r, weightIndex);
  const rc = receiptOf(stepRows(r), r), an = answerLine(r), tw = twistLine(r), wo = withoutLine(r), dc = decidingLine(r);
  const t = (segs) => (segs || []).map((x) => x[0]).join("");
  const what = !!(lamp && lamp.whatIf);
  const ef = effectLine(r);
  const figures = [rd.move.value, rd.move.sub, rd.family.value, rd.family.from, rd.precedents && rd.precedents.value, rd.precedents && rd.precedents.sub, ef && ef.text,
    rd.by.service, rc && rc.short, ep && ep.title, ep && ep.why, ep && !shockAskedLine(r) && !shockQuestion(r) && ep.fig + ep.win, askLine(r), reframeLine(r),
    lamp && lamp.word, lamp && lamp.caption, !what && an && t(an.segs), !what && tw && t(tw.segs), !what && wo && wo.text, !what && dc && `${dc.lead} ${dc.name}. ${dc.text}`,
    "This already happened; it is not a forecast. Fictional illustration, not a recommendation."].filter(Boolean);
  /* the lines under the verdict that tie the answer to the question and to its proof (coordinator, usability test) */
  const notes = what ? [] : [t(shockAskedLine(r)), proofLine(r), t(peerLine(r)), t(bandLine(r))].filter(Boolean);
  return { figures, notes, labels: [lamp && lamp.qualifier, rd.by.model, rd.by.recorded, ep && ep.where].filter(Boolean) };
}
/* the figures in a string: a signed amount, a percentage, a count, a year (a 4-digit year counts as one) */
export function figuresIn(text) {
  return (String(text || "").match(/[\u2212-]?\$?\d[\d,\u00a0]*(?:\.\d+)?/g) || []).length;
}

/* ---- the timeline (ms from the start of a replay): one focal motion per beat, nothing else moves. A live run replaces the READ
   beat with the real progress lines, then the rest starts at `fly`. ---- */
export function schedule(opts) {
  /* R7: the Earth zooms to the epicentre in the hero layout (flyTo: zoom and one ring), holds with the caption, then docks in
     the stage's slot; meanwhile the reading streams in that empty slot, on black, never over the Earth's limb */
  const o = obj(opts) || {}, live = !!o.live, gap = 300, steps = 5;
  const t = { live, undockMs: 600, lift: 0, step0: live ? null : 400, stepGap: gap, chipGap: 120 };
  t.chips = live ? 0 : t.step0 + 2 * gap;        // the reading lands when UNDERSTAND is done (live: when the Result lands)
  t.aside = t.chips + 3 * t.chipGap + 160;
  t.fly = live ? t.aside + 240 : t.step0 + steps * gap + 300;   // the steps fold as the Earth zooms
  t.flyMs = 900;
  t.caption = t.fly + 500;
  t.handoff = t.fly + t.flyMs + 300;            // a short hold on the epicentre, then the Earth docks
  t.handoffMs = 600;
  t.by = t.handoff + 300;                       // who read it and the receipt, once the Earth has left that corner
  t.race = t.handoff + t.handoffMs + 200;
  t.raceMs = 2400;
  /* the signature moment (design director): at landing the cyan thread runs from the inset Earth to the asked shock's tick
     (500 ms), the crosshair opens on that week (lane U3's race.pin), then the verdict lights */
  t.leader = t.race + t.raceMs + 60;
  t.leaderMs = 500;
  t.pin = t.leader + t.leaderMs;
  t.lamp = t.pin + 120;
  t.lampMs = 400;
  t.lines = t.lamp + 260;
  t.twist = t.lines + 300;
  t.end = t.twist + 400;
  t.collapse = t.fly;
  return t;
}
/* which phase a moment of the timeline is in (store.phase): reading, flying (epicentre and handoff), racing, landed */
export function phaseAt(t, s) {
  if (!isNum(t) || !obj(s)) return "idle";
  return t < s.fly ? "reading" : t < s.race ? "flying" : t < s.lamp ? "racing" : "landed";
}
/* the ease-in-out curve of the tokens (cubic-bezier(0.77, 0, 0.175, 1)) as a function of p, for the race's draw(p) */
export function easeInOut(p) {
  const x = Math.min(1, Math.max(0, Number(p) || 0));
  if (x === 0 || x === 1) return x;
  const bez = (t, a, b) => 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3;
  let lo = 0, hi = 1;
  for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (bez(mid, 0.77, 0.175) < x) lo = mid; else hi = mid; }
  return bez((lo + hi) / 2, 0, 1);
}
