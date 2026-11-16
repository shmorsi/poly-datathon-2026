/* The dial's pure helpers (#dial, "Where it breaks"; design doc §2 item 3, rulings R1, R2, R5, R13). No DOM, no network.
   Every number comes from the Result: tipping_point.curve[i] {weight, verdict, fails, max_drawdown, scenario_shock, end_value,
   loss_dollars?}, tipping_band {lo, hi, starts}, limits.floor, amount. Words and numbers go through web/lib.js (PF.fmt, PF.VERDICT),
   passed in or read from globalThis.PF at call time.
   One judge (pitfall 5): the browser never compares a fall with the floor. A size's status is curve[i].verdict as the server wrote
   it. "Your floor breaks" sits at the first Incompatible size because the floor (max_drawdown) is the only hard rule in
   governance.py, and only a hard fail makes a size Incompatible. */

import { FLOOR_WORDS } from "./status.js";     // the page's one status vocabulary (lane U5): Broke / Touched / Held above your floor

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
/* R20: the verdict words belong to the size the investor asked; any other size on the dial shows only its worst fall against the
   floor, in the floor's own words, with this caption and no end value */
export const WHAT_IF = "A replay at another size, not a recommendation.";
const FLOOR_TONE = { broke: { tone: "outside", icon: "i-out" }, touched: { tone: "caveat", icon: "i-warn" }, held: { tone: "neutral", icon: null } };
/* governance.round_pp's tenths of a point (web/lib.js tenths) */
const tenths = (x) => Math.sign(x) * Math.round(Number((Math.abs(x) * 1000).toPrecision(12)));

/* what a size's worst fall did to the floor. Broke = the server's verdict (Incompatible needs the floor, the one hard rule).
   A size that held is "touched" when its fall came within 1 point of the floor (the Result's own fall and floor, in governance's
   tenths), else "held above"; the browser never turns a held size into a break or a break into a hold. */
function floorClassOf(verdict, dd, floor) {
  if (verdict === "Incompatible") return "broke";
  if (!isNum(dd) || !isNum(floor) || !verdict) return null;
  return tenths(dd) - tenths(floor) <= 10 ? "touched" : "held";
}
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const ISO = /^\d{4}-\d{2}-\d{2}/;
export const PAGE_STEP = 5;          // Page Up / Page Down move five sizes (the arrows move one)

/* the display name of a ticker, from lib.js's one name table (moveOf is the only door to it) */
function nameOf(PF, tk) {
  const m = PF.moveOf({ question_type: "change", portfolio: { [tk]: 1 }, tipping_point: { ticker: tk } });
  return (m && m.name) || tk;
}

/* the index of the curve point whose weight is nearest to w (ties to the lower size) */
function nearestWeight(points, w) {
  let best = 0;
  for (let i = 1; i < points.length; i++) if (Math.abs(points[i].weight - w) < Math.abs(points[best].weight - w) - 1e-12) best = i;
  return best;
}

/* "2021-11", "2021-11-30" or {start|month|date: …} as an ISO day, else null */
function monthOf(x) {
  const s = str(typeof x === "string" ? x : obj(x) && (x.start || x.month || x.date));
  if (!s) return null;
  if (/^\d{4}-\d{2}$/.test(s)) return s + "-01";
  return ISO.test(s) ? s.slice(0, 10) : null;
}

/* the start-month band (lane B3's tipping_band {lo, hi, starts[{start, first_break}], holds[], n_starts}): the first weight where the
   floor check failed, lowest and highest over the start months. Null without two numbers; `held` says how many starts never broke. */
function bandOf(r, points, fmt) {
  const b = obj(r.tipping_band);
  if (!b) return null;
  const starts = arr(b.starts).map((s) => ({ month: monthOf(s), at: obj(s) && isNum(s.first_break) ? s.first_break : null })).filter((s) => s.month)
    .sort((x, y) => (x.month < y.month ? -1 : 1));
  const n = isNum(b.n_starts) ? b.n_starts : starts.length, held = arr(b.holds).length;
  const first = starts[0] || null, last = starts[starts.length - 1] || null;
  const base = { n, held, first: first && fmt.month(first.month), last: last && fmt.month(last.month) };
  if (!isNum(b.lo) || !isNum(b.hi)) return held && held === n ? { ...base, allHeld: true } : null;
  const scale = b.lo > 1 || b.hi > 1 ? 100 : 1;          // weights are fractions like the curve's; points (7, 12) are read as 7 %, 12 %
  const lo = b.lo / scale, hi = b.hi / scale;
  if (lo > hi) return null;
  const iLo = nearestWeight(points, lo), iHi = nearestWeight(points, hi);
  const at = (s) => (s && s.at !== null ? points[nearestWeight(points, s.at / scale)].weightText : null);
  const ticks = [...new Set(starts.filter((s) => s.at !== null).map((s) => nearestWeight(points, s.at / scale)))].sort((a, z) => a - z).map((i) => edge(points, i));
  return { ...base, allHeld: false, iLo, iHi, loText: fmt.share(points[iLo].weight), hiText: fmt.share(points[iHi].weight),
    x0: edge(points, iLo), x1: edge(points, iHi), firstAt: at(first), lastAt: at(last), ticks };
}

/* the boundary just before point i: halfway to the previous size (0 at the first point) */
function edge(points, i) { return i <= 0 ? 0 : (points[i - 1].x + points[i].x) / 2; }

/* PF.dial: everything the dial draws, from one Result. Null when the run has no size curve (the section hides). */
export function dialModel(r, PF = globalThis.PF) {
  r = obj(r);
  const tp = r && obj(r.tipping_point), curve = tp ? arr(tp.curve) : [];
  if (!PF || !tp || curve.length < 2 || !curve.every((c) => obj(c) && isNum(c.weight))) return null;
  const fmt = PF.fmt, w0 = curve[0].weight, w1 = curve[curve.length - 1].weight;
  if (!(w1 > w0)) return null;
  const ticker = str(tp.ticker) || "", name = nameOf(PF, ticker);
  const points = curve.map((c, i) => {
    const v = Object.prototype.hasOwnProperty.call(PF.VERDICT, c.verdict) ? PF.VERDICT[c.verdict] : null;
    return { i, weight: c.weight, x: (c.weight - w0) / (w1 - w0), weightText: fmt.share(c.weight), verdict: v ? c.verdict : null,
      tone: v ? v.tone : "none", word: v ? v.word : "Not judged", icon: v ? v.icon : "i-pending", fails: isNum(c.fails) ? c.fails : null,
      dd: isNum(c.max_drawdown) ? c.max_drawdown : null, ddText: fmt.pct(c.max_drawdown) || null,
      dollars: isNum(c.loss_dollars) ? c.loss_dollars : null, dollarsText: fmt.money(c.loss_dollars) || null,
      end: isNum(c.end_value) ? c.end_value : null, endText: fmt.money(c.end_value) || null,
      floorCls: floorClassOf(v ? c.verdict : null, c.max_drawdown, r.limits && r.limits.floor) };
  });
  const last = points.length - 1, port = obj(r.portfolio) || {}, base = obj(r.baseline) && obj(r.baseline.portfolio);
  const move = PF.moveOf(r);
  const askedW = move && move.ticker === ticker ? move.weight : isNum(port[ticker]) ? port[ticker] : w1;
  const asked = nearestWeight(points, askedW);
  const today = base ? nearestWeight(points, isNum(base[ticker]) ? base[ticker] : 0) : null;
  const breakAt = points.findIndex((p) => p.verdict === "Incompatible");
  const runs = [];
  for (const p of points) {
    const run = runs[runs.length - 1], cls = p.floorCls || "none";
    if (run && run.cls === cls) run.to = p.i;
    else runs.push({ cls, tone: cls === "broke" ? "outside" : cls === "touched" ? "caveat" : "none", word: FLOOR_WORDS[cls] || "not judged", from: p.i, to: p.i });
  }
  for (const run of runs) { run.x0 = edge(points, run.from); run.x1 = run.to === last ? 1 : edge(points, run.to + 1); }
  const marks = points.map((p) => {
    const pts = Math.round(p.weight * 100);
    const level = pts % 10 === 0 ? 2 : pts % 5 === 0 ? 1 : 0;
    return { i: p.i, x: p.x, level, label: level === 2 ? p.weightText : null };
  });
  const prof = obj(r.profile) || {}, owner = str(prof.name);
  const amount = isNum(r.amount) && r.amount > 0 ? r.amount : null, amountText = amount === null ? null : fmt.money(amount);
  const limits = obj(r.limits) || {}, floorText = isNum(limits.floor) ? fmt.share(limits.floor) : null;
  /* the floor in dollars only when the capacity set it (lib.js view rule, ruling R18); a persona's capacity is an assumption (R13) */
  const typed = arr(limits.edited).includes("floor");
  const capText = isNum(limits.floor) && limits.floor_source === "capacity" && !typed && isNum(limits.capacity_dollars) && limits.capacity_dollars > 0
    ? fmt.money(-limits.capacity_dollars) : null;
  const dates = arr(obj(tp.paths) && tp.paths.dates).length ? tp.paths.dates : arr(obj(r.series) && r.series.dates);
  const y0 = str(dates[0]) && dates[0].slice(0, 4), y1 = str(dates[dates.length - 1]) && dates[dates.length - 1].slice(0, 4);
  const bandAll = bandOf(r, points, fmt), band = bandAll && !bandAll.allHeld ? bandAll : null;
  const floorV = isNum(limits.floor) && limits.floor < 0 ? limits.floor : null;
  const deepest = Math.max(0, ...points.map((p) => (p.dd === null ? 0 : Math.abs(p.dd))), floorV === null ? 0 : Math.abs(floorV));
  const model = {
    ticker, name, owner, amount, amountText, floorText, floorV, capText, capWord: typed ? "Your limit" : "Assumed limit", scale: deepest > 0 ? deepest * 1.04 : 1, points, last, asked, today,
    breakAt: breakAt < 0 ? null : breakAt, band, everyStart: !!(bandAll && bandAll.allHeld), startSpan: bandAll && bandAll.first && bandAll.last ? [bandAll.first, bandAll.last] : null,
    runs, marks, hasDollars: points.every((p) => p.dollars !== null),
    notch: breakAt > 0 ? { i: breakAt, x: edge(points, breakAt), text: points[breakAt].weightText } : null,
    replay: y0 && y1 ? `in this ${y0}–${y1.slice(2)} replay` : "in this replay",
    start: fmt.month(dates[0]) || null, end: fmt.month(dates[dates.length - 1]) || null,
    label: amountText ? `${name} share of your ${amountText}` : `${name} share of your mix`,   // R18: one voice, second person
    fineprint: ["Fictional illustration, not a recommendation.", "This already happened; it is not a forecast."],
  };
  model.sentence = sentenceOf(model);
  model.bandLine = bandLineOf(model);
  model.hint = "Drag or click the ruler to replay the same history at any size.";
  model.summary = summaryOf(model);
  return model;
}

/* R2: where it broke in this replay (its own start), past tense, never "holds up to" */
function sentenceOf(m) {
  const P = m.points, n = m.name;
  if (m.breakAt === null) return [["In this replay, your floor did not break at any size up to "], [P[m.last].weightText, "n"], [` ${n}.`]];
  if (m.breakAt === 0) return [[`In this replay, your floor broke at every size, even with no ${n}.`]];
  return [["In this replay, your floor first broke at "], [P[m.breakAt].weightText, "n"], [` ${n}.`]];
}

/* the start-month band (R2, on by default when the Result carries it): the same replay started in each month of the span */
function bandLineOf(m) {
  const span = m.startSpan ? ` from ${m.startSpan[0]} to ${m.startSpan[1]}` : "";
  if (m.everyStart) return [[`Started in any month${span}, it did not break either.`]];
  const b = m.band;
  if (!b) return null;
  const held = b.held ? ` From ${b.held} of the ${b.n} start months it did not break at all.` : "";
  if (b.iLo === b.iHi) return [[`Started in any month${span}, it first broke at the same `], [b.loText, "n"], ["." + held]];
  return [[`Depending on the start month${span ? "," + span : ""}, it first broke between `], [b.loText, "n"], [" and "], [b.hiText, "n"], ["." + held]];
}

/* the ruler's text alternative: each stretch of sizes and the status the server gave it */
function summaryOf(m) {
  const P = m.points, span = (a, z) => (a === z ? P[a].weightText : `${P[a].weightText} to ${P[z].weightText}`);
  const parts = m.runs.map((run) => `${span(run.from, run.to)} ${m.name}: ${run.word.toLowerCase()}`);
  const comb = P[0].ddText && P[m.last].ddText ? ` The worst fall went from ${P[0].ddText} at ${P[0].weightText} to ${P[m.last].ddText} at ${P[m.last].weightText}` +
    (m.floorText ? `, against your floor of ${m.floorText}.` : ".") : "";
  const band = m.bandLine ? " " + m.bandLine.map((s) => s[0]).join("") : "";
  return `A ruler of ${m.name} sizes from ${P[0].weightText} to ${P[m.last].weightText}, ${m.replay}. ${parts.join("; ")}.${comb}${band}`;
}

/* what the readouts show at size i (aria-valuetext included). The asked size reads as the run did: its verdict, its dollars, its
   end value. Any other size (R20) reads only as a fall against the floor: no verdict word, no pass mark, no end value. */
export function readout(m, i) {
  const p = m.points[Math.max(0, Math.min(m.last, i | 0))], t = m.today !== null ? m.points[m.today] : null, asked = p.i === m.asked;
  const fc = p.floorCls ? { cls: p.floorCls, word: FLOOR_WORDS[p.floorCls], ...FLOOR_TONE[p.floorCls] } : null;
  const base = { i: p.i, weightText: p.weightText, ddText: p.ddText, isAsked: asked, isToday: p.i === m.today, floor: fc };
  if (!asked) {
    const fell = p.ddText ? `Worst fall ${p.ddText}` + (m.floorText ? `, against your floor of ${m.floorText}` : "") + "." : "";
    return { ...base, tone: fc ? fc.tone : "neutral", word: fc ? fc.word : null, icon: fc ? fc.icon : null, dollarsText: null, endText: null,
      todayEndText: null, caption: WHAT_IF,
      valuetext: [`${p.weightText} ${m.name}, a replay at another size ${m.replay}.`, fc ? `${fc.word}.` : "", fell, WHAT_IF].filter(Boolean).join(" ") };
  }
  const fall = p.ddText ? `Worst fall ${p.ddText}` + (p.dollarsText && m.amountText ? `, the same fall as ${p.dollarsText} on your ${m.amountText}` : "") + "." : "";
  return { ...base, tone: p.tone, word: p.word, icon: p.icon, dollarsText: m.hasDollars ? p.dollarsText : null, endText: p.endText,
    todayEndText: t && t.i !== p.i ? t.endText : null, caption: null,
    valuetext: [`${p.weightText} ${m.name}, the size you asked: ${p.word.toLowerCase()} ${m.replay}.`, fall, p.endText ? `Ended at ${p.endText}.` : ""].filter(Boolean).join(" ") };
}

/* the figures a readout shows for size i: what a roll starts from and lands on */
export const figuresOf = (m, i) => { const p = m.points[i]; return { dd: p.dd, dollars: m.hasDollars ? p.dollars : null, end: p.end }; };

/* the readouts on the way from the figures on screen (`from`, numbers) to size `to`, at eased progress k (0..1). The last frame
   prints the Result's own text for that size, so a roll always lands on the exact value. */
export function rollTexts(m, from, to, k, PF = globalThis.PF) {
  const b = m.points[to], f = PF.fmt;
  if (!b) return { ddText: null, dollarsText: null, endText: null };
  const exact = { ddText: b.ddText, dollarsText: m.hasDollars ? b.dollarsText : null, endText: b.endText };
  if (k >= 1 || !obj(from)) return exact;
  const mid = (x, y, fm) => (isNum(x) && isNum(y) ? fm(x + (y - x) * k) || null : null);
  return { ddText: mid(from.dd, b.dd, f.pct) || exact.ddText, dollarsText: m.hasDollars ? mid(from.dollars, b.dollars, f.money) || exact.dollarsText : null,
    endText: mid(from.end, b.end, f.money) || exact.endText };
}

/* the size under a pointer at fraction x of the ruler (0 = the first size, 1 = the last) */
export function nearestIndex(m, x) {
  const f = Math.max(0, Math.min(1, isNum(x) ? x : 0));
  let best = 0;
  for (const p of m.points) if (Math.abs(p.x - f) < Math.abs(m.points[best].x - f) - 1e-12) best = p.i;
  return best;
}

/* the slider's keys (WAI-ARIA slider pattern): arrows one size, Page Up/Down five, Home/End the ends; null for any other key */
export function keyStep(i, key, last, page = PAGE_STEP) {
  const to = { ArrowRight: i + 1, ArrowUp: i + 1, ArrowLeft: i - 1, ArrowDown: i - 1, PageUp: i + page, PageDown: i - page, Home: 0, End: last }[key];
  return to === undefined ? null : Math.max(0, Math.min(last, to));
}

/* true when a move from one size to another crosses the line where the floor first broke (either way) */
export function crossed(m, from, to) {
  const b = m.breakAt;
  return b !== null && b > 0 && isNum(from) && isNum(to) && (from < b) !== (to < b);
}

/* the page's --ease-out, cubic-bezier(0.23, 1, 0.32, 1), as a function of time (Newton steps on x, then y) */
export function easeOut(t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  const [x1, y1, x2, y2] = [0.23, 1, 0.32, 1];
  const bx = (s) => 3 * x1 * s * (1 - s) ** 2 + 3 * x2 * s * s * (1 - s) + s ** 3;
  const by = (s) => 3 * y1 * s * (1 - s) ** 2 + 3 * y2 * s * s * (1 - s) + s ** 3;
  const dx = (s) => 3 * x1 * (1 - s) ** 2 + 6 * (x2 - x1) * s * (1 - s) + 3 * (1 - x2) * s * s;
  let s = t;
  for (let n = 0; n < 8; n++) { const d = dx(s); if (Math.abs(d) < 1e-6) break; s = Math.max(0, Math.min(1, s - (bx(s) - t) / d)); }
  return by(s);
}
