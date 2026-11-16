/* The race chart's model (lane U3, design doc §2 2d, R13): pure, no DOM, no network. raceModel(result, weightIndex) turns one
   Result into the investor's money over time, weekly, in dollars. Every number it hands the renderer is a Result key or the
   Result's own series: tipping_point.paths.values (weekly dollars), breaches[] (the server's dates, depths and dollars),
   curve[i] (end values, worst falls). The browser never judges a breach on its own terms: a fall counts only when it is past
   the floor after rounding to a tenth of a point, as governance.round_pp does (pitfall 5). PF (web/lib.js) is read at call
   time, never at import time. */

import { FLOOR_WORDS } from "./status.js";   // the page's one status vocabulary (lane U5): Broke / Touched / Held above your floor

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const arr = (x) => (Array.isArray(x) ? x : []);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const DAY = /^(\d{4})-(\d{2})(?:-(\d{2}))?/;
const PFx = () => (typeof globalThis !== "undefined" && globalThis.PF) || null;
/* the asked family, the same rule as replay.js askedFamilyOf (the globe's epicentre): the first family holding a precedent the
   navigator picked, else the first family; none for an abstention. Its shocks are the cyan ticks the epicentre's thread lands on. */
function askedFamily(r) {
  const sc = obj(r && r.scenario);
  if (!sc || (obj(sc.weather) && sc.weather.no_precedent === true && !arr(sc.event_ids).length)) return null;
  const fams = arr(sc.families).map(str).filter(Boolean), picked = arr(r.events).filter((e) => obj(e) && e.picked === true);
  return fams.find((f) => picked.some((e) => e.family === f)) || fams[0] || null;
}

/* "YYYY-MM-DD" or "YYYY-MM" (a monthly window: the first of the month) to UTC milliseconds; NaN for anything else */
export function timeOf(d) {
  const m = typeof d === "string" && DAY.exec(d);
  if (!m || +m[2] < 1 || +m[2] > 12) return NaN;
  return Date.UTC(+m[1], +m[2] - 1, m[3] ? +m[3] : 1);
}
const dayOf = (d) => (typeof d === "string" && DAY.test(d) ? d.slice(0, 10) : null);

/* typographic quotes and apostrophes in the Result's own titles (ruling R18): "Liberation Day" -> “Liberation Day”, Trump's -> Trump’s */
export function typo(s) {
  if (typeof s !== "string") return s;
  return s.replace(/(^|[\s([{\u2014\u2013-])"/g, "$1\u201c").replace(/"/g, "\u201d")
    .replace(/(\w)'(\w)/g, "$1\u2019$2").replace(/(^|[\s([{\u2014\u2013-])'/g, "$1\u2018").replace(/'/g, "\u2019");
}

/* tenths of a percentage point, ties away from zero: governance.round_pp (the same rule as PF.tenths) */
export function tenths(x) {
  const v = Number(x);
  if (!Number.isFinite(v)) return NaN;
  return Math.sign(v) * Math.round(Number((Math.abs(v) * 1000).toPrecision(12)));
}
/* a fall is past the floor only when its rounded value is past the rounded floor (−15.00004 % is inside a −15 % floor) */
export function pastFloor(fall, floor) {
  if (!isNum(fall) || !isNum(floor)) return false;
  if (fall > floor + 0.002) return false;   // more than two tenths of a point either side: no rounding can cross the floor
  if (fall < floor - 0.002) return true;
  return tenths(fall) < tenths(floor);
}

/* the floor that follows every new high: the running high of the line times (1 + floor); null where the line has no value */
export function ribbonOf(values, floor) {
  let high = -Infinity;
  return arr(values).map((v) => {
    if (!isNum(v) || !isNum(floor)) return null;
    high = Math.max(high, v);
    return high * (1 + floor);
  });
}

/* the stretches where the line is past its floor, grouped by the high they fell from (one episode per high, as the server's
   breaches are): [{peak, trough, recover, depth, stretches: [[i0, i1], ...]}] in indices of `values` */
export function episodesOf(values, floor) {
  const out = [];
  let high = -Infinity, hi = -1, cur = null;
  arr(values).forEach((v, k) => {
    if (!isNum(v)) return;
    if (v >= high) {                       // a new high (or back to it) closes the open episode
      if (cur) { cur.recover = k; out.push(cur); cur = null; }
      high = v; hi = k;
      return;
    }
    const fall = v / high - 1;
    if (cur && fall < cur.depth) { cur.depth = fall; cur.trough = k; }
    if (!pastFloor(fall, floor)) return;
    if (!cur) cur = { peak: hi, trough: k, recover: null, depth: fall, stretches: [] };
    const last = cur.stretches[cur.stretches.length - 1];
    if (last && last[1] === prevIndex(values, k)) last[1] = k; else cur.stretches.push([k, k]);
  });
  if (cur) out.push(cur);
  return out;
}
function prevIndex(values, k) {            // the previous index that has a value (a line may skip inserted days)
  for (let j = k - 1; j >= 0; j--) if (isNum(values[j])) return j;
  return -1;
}

/* the hatch under the floor, in (t, value): the floor level (flat within an episode: one high) from where the line crosses it
   on the way down to where it crosses back, and the line's own points in between */
export function hatchOf(ts, values, ribbon, stretch) {
  const [i0, i1] = stretch, R = ribbon[i0];
  if (!isNum(R)) return null;
  const a = prevIndex(values, i0), n = nextIndex(values, i1);
  const cross = (j, k) => {                // where the segment j→k meets the floor level, clamped to the segment
    const vj = values[j], vk = values[k];
    const f = vj === vk ? 0 : Math.min(1, Math.max(0, (vj - R) / (vj - vk)));
    return ts[j] + f * (ts[k] - ts[j]);
  };
  const tIn = a >= 0 ? cross(a, i0) : ts[i0], tOut = n >= 0 ? cross(i1, n) : ts[i1];
  const pts = [[tIn, R]];
  for (let k = i0; k <= i1; k++) if (isNum(values[k])) pts.push([ts[k], values[k]]);
  pts.push([tOut, R]);
  return pts;
}
function nextIndex(values, k) {
  for (let j = k + 1; j < values.length; j++) if (isNum(values[j])) return j;
  return -1;
}

/* every 5th trading day (the weekly cadence of tipping_point.paths), the last day, and the days the Result names (each
   breach's high and trough, the worst fall's), so a weekly line still touches the server's own troughs */
export function weeklyIndices(dates, keep) {
  const n = arr(dates).length, out = new Set();
  for (let k = 0; k < n; k += 5) out.add(k);
  if (n) out.add(n - 1);
  const want = new Set(arr(keep).map(dayOf).filter(Boolean));
  dates.forEach((d, k) => { if (want.has(dayOf(d))) out.add(k); });
  return [...out].sort((a, b) => a - b);
}

const BASE = new WeakMap();                 // the parts of a model that do not depend on the size (one per Result)
const fmtOf = () => { const PF = PFx(); return (PF && PF.fmt) || null; };
const MONEY = new Map();                   // PF.fmt.money goes through toLocaleString (slow per call); the dial asks for the same few
const money = (x) => {
  const f = fmtOf();
  if (!f || !isNum(x)) return null;
  let t = MONEY.get(x);
  if (t === undefined) { t = f.money(x); if (MONEY.size > 4000) MONEY.clear(); MONEY.set(x, t); }
  return t;
};
const pct = (x) => { const f = fmtOf(); return f && isNum(x) ? f.pct(x) : null; };
const share = (x) => { const f = fmtOf(); return f && isNum(x) ? f.share(x) : null; };
const dateText = (d) => { const f = fmtOf(); return f && d ? f.date(d) || null : null; };

function breachesOfResult(r) {             // the server's breaches, deepest first (its dates, depths and dollars)
  return arr(r.breaches).map(obj).filter((b) => b && isNum(b.depth) && dayOf(b.trough_date) && dayOf(b.peak_date))
    .map((b) => ({ peak: dayOf(b.peak_date), trough: dayOf(b.trough_date), recover: dayOf(b.recovery_date), depth: b.depth,
      /* R35: a fall's dollars are the path's own (its high and its trough, whole dollars), never the percent times the amount */
      dollars: isNum(b.fall_dollars) ? b.fall_dollars   // lane fin-backend's own key, else the same subtraction of the Result's two values
        : isNum(b.peak_value) && isNum(b.trough_value) ? Math.round(b.trough_value) - Math.round(b.peak_value) : null,
      peakValue: isNum(b.peak_value) ? b.peak_value : null,
      troughValue: isNum(b.trough_value) ? b.trough_value : null }))
    .sort((a, b) => a.depth - b.depth);
}

function shocksOf(r, family, move, t0, t1) {
  const out = arr(r.events).map(obj).filter((e) => e && e.family === family && dayOf(e.date))
    .map((e) => {
      const side = obj(move ? e.after : e.today), t = timeOf(dayOf(e.date));
      return { id: str(e.event_id) || dayOf(e.date), date: dayOf(e.date), t, title: typo(str(e.title)), place: typo(str(e.place)),
        lat: isNum(e.lat) ? e.lat : null, lon: isNum(e.lon) ? e.lon : null, trough: side && isNum(side.trough) ? side.trough : null, worst: false };
    })
    .filter((s) => s.t >= t0 && s.t <= t1).sort((a, b) => a.t - b.t);
  let w = null;                             // the asked family's worst precedent on this mix (where the globe flies)
  for (const s of out) if (s.trough !== null && (w === null || s.trough < w.trough)) w = s;
  if (w) w.worst = true;
  return out;
}

function validPaths(p, curve) {
  const d = arr(p && p.dates), v = arr(p && p.values), w = arr(p && p.weights);
  return d.length > 1 && d.every(dayOf) && v.length > 0 && v.length === w.length && v.length === curve.length
    && v.every((row) => Array.isArray(row) && row.length === d.length && row.every(isNum)) && w.every(isNum);
}
const closest = (list, x) => list.reduce((best, w, i) => (Math.abs(w - x) < Math.abs(list[best] - x) - 1e-12 ? i : best), 0);

/* the size curve's weekly paths (tipping_point.paths). Today's line is the curve's size equal to today's weight (0 % when the
   ticker is not held); the server's own breach days join the line only when the asked size is a size of the curve ("exact") */
function pathsBase(r, b) {
  const paths = obj(r.tipping_point) && obj(r.tipping_point.paths);
  if (!b.move || b.amount === null || !validPaths(paths, b.curve) || !b.curve.every((c) => c && isNum(c.weight))) return null;
  const w = paths.weights, asked = closest(w, b.move.weight), exact = Math.abs(w[asked] - b.move.weight) < 1e-6;
  const held = obj(obj(r.baseline) && r.baseline.portfolio), w0 = held && isNum(held[b.move.ticker]) ? held[b.move.ticker] : 0;
  const k0 = w.findIndex((x) => Math.abs(x - w0) < 1e-6);
  const weekly = paths.dates.map(dayOf), have = new Set(weekly), extra = new Map();
  if (exact) for (const x of b.rb) {
    if (x.peakValue !== null && !have.has(x.peak)) extra.set(x.peak, x.peakValue);
    if (x.troughValue !== null && !have.has(x.trough)) extra.set(x.trough, x.troughValue);
  }
  const dates = [...weekly, ...extra.keys()].sort(), pos = new Map(weekly.map((d, j) => [d, j]));
  const P = { kind: "paths", dates, ts: dates.map(timeOf), values: paths.values, weights: w, asked, exact, k0,
    wk: dates.map((d) => (pos.has(d) ? pos.get(d) : -1)), ins: dates.map((d) => (extra.has(d) ? extra.get(d) : null)) };
  if (k0 < 0) {                              // today's weight is no size of the curve: today's line is the series, never priced here
    const s = obj(r.series), sd = arr(s && s.dates).map(dayOf), st = arr(s && s.today), at = new Map(sd.map((d, k) => [d, k]));
    P.todaySeries = dates.map((d) => (at.has(d) && isNum(st[at.get(d)]) ? (st[at.get(d)] * b.amount) / 100 : null));
  }
  return P;
}
/* the Result's own daily series in dollars, every 5th trading day plus the days the Result names: the one line of a question
   with no move, or the evaluated mix of a size the curve does not carry */
function seriesBase(r, b) {
  const s = obj(r.series), sd = arr(s && s.dates), st = arr(s && s.today);
  if (b.amount === null || sd.length < 2 || !sd.every(dayOf) || st.length !== sd.length) return null;
  const m = obj(r.metrics) || {}, sa = b.move && arr(s.after).length === sd.length ? s.after : null;
  const keep = [...b.rb.flatMap((x) => [x.peak, x.trough]), ...["today", "after"].flatMap((k) => [obj(m[k]) && m[k].peak_date, obj(m[k]) && m[k].trough_date])];
  const idx = weeklyIndices(sd, keep), dollars = (row) => idx.map((k) => (isNum(row[k]) ? (row[k] * b.amount) / 100 : null));
  const dates = idx.map((k) => dayOf(sd[k]));
  return { kind: "series", dates, ts: dates.map(timeOf), today: dollars(st), after: sa ? dollars(sa) : null };
}

function baseOf(r) {
  let b = BASE.get(r);
  if (b) return b;
  const PF = PFx(), v = PF && typeof PF.view === "function" ? PF.view(r) : null;
  const amount = isNum(r.amount) && r.amount > 0 ? r.amount : null, limits = obj(r.limits) || {};
  const tp = obj(r.tipping_point), curve = arr(tp && tp.curve).map(obj);
  const move = PF && typeof PF.moveOf === "function" ? PF.moveOf(r) : null;
  b = { r, v, amount, floor: isNum(limits.floor) ? limits.floor : null, move, rb: breachesOfResult(r), curve, kind: null,
    family: askedFamily(r), backdrops: arr(r.backdrops).map(obj).filter(Boolean) };
  b.P = pathsBase(r, b);
  b.S = b.P && b.P.exact ? null : seriesBase(r, b);
  b.kind = b.P ? "paths" : b.S ? "series" : null;
  if (b.kind) {
    let lo = Infinity, hi = -Infinity, t0 = Infinity, t1 = -Infinity;   // one domain for every view: the dial never rescales
    const span = (row) => { for (const x of arr(row)) if (isNum(x)) { lo = Math.min(lo, x); hi = Math.max(hi, x); } };
    if (b.P) { b.P.values.forEach((row) => { span(row); span(ribbonOf(row, b.floor)); }); span(b.P.ins); span(b.P.todaySeries); }
    if (b.S) [b.S.today, b.S.after].filter(Boolean).forEach((row) => { span(row); span(ribbonOf(row, b.floor)); });
    for (const src of [b.P, b.S]) if (src) { t0 = Math.min(t0, src.ts[0]); t1 = Math.max(t1, src.ts[src.ts.length - 1]); }
    for (const side of ["after", "today"]) { const c = capacityOf(r, side); if (c) { lo = Math.min(lo, c.line); hi = Math.max(hi, c.line); } }
    b.domain = { t0, t1, y0: lo, y1: hi };
    b.shocks = shocksOf(r, b.family, !!move, t0, t1);
    b.bands = bandsOf(b);
    b.ticker = move && move.ticker;
    b.name = move && move.name;
  }
  BASE.set(r, b);
  return b;
}

function labelOf(b, from, to) {            // a fall's name: the asked shock on record inside it (a backdrop is a band, never a cause)
  const f = timeOf(from), z = timeOf(to);
  let best = null;
  for (const s of b.shocks) if (s.title && s.t >= f && s.t <= z && (best === null || (s.trough ?? 0) < (best.trough ?? 0))) best = s;
  return best ? { label: best.title, labelKind: "event", eventId: best.id } : { label: null, labelKind: null, eventId: null };
}
/* the Result's backdrops (result.backdrops: a rate cycle) as quiet bands over their own dates, clipped to the drawn window */
function bandsOf(b) {
  const f = fmtOf(), month = (d) => (f && d ? f.month(d) || null : null);
  return b.backdrops.map((x) => ({ label: typo(str(x.label)), start: dayOf(x.start), end: dayOf(x.end) }))
    .filter((x) => x.label && x.start && timeOf(x.start) <= b.domain.t1 && (!x.end || timeOf(x.end) >= b.domain.t0))
    .map((x) => ({ ...x, t0: Math.max(timeOf(x.start), b.domain.t0), t1: x.end ? Math.min(timeOf(x.end), b.domain.t1) : b.domain.t1,
      text: month(x.start) && month(x.end) ? `${x.label}, ${month(x.start)} \u2013 ${month(x.end)}` : x.label }));
}
/* the capacity (R35, the workshop's "risk tolerance is not capacity"): what the investor said they could afford to lose, as a flat
   line at the amount minus it (result.capacity, lane fin-backend). Old runs and fresh clones carry no such key: nothing is drawn. */
function capacityOf(r, side) {
  const c = obj(r.capacity);
  if (!c) return null;
  const s = obj(c[side]) || (side === "after" ? null : obj(c.today));
  const line = [s && s.line, c.line].find(isNum);
  if (!isNum(line) || line <= 0) return null;
  const dollars = [c.dollars, c.capacity, c.capacity_dollars, s && s.dollars].find(isNum);
  const sessions = s ? [s.sessions_below, s.days_below].find(isNum) : undefined;
  /* the stretches below the line: lane fin-backend's episodes {first_date, last_date}, else its first_below .. last_below */
  let below = arr(s && s.episodes).map(obj).filter((e) => e && dayOf(e.first_date) && dayOf(e.last_date)).map((e) => [dayOf(e.first_date), dayOf(e.last_date)]);
  if (!below.length && s && dayOf(s.first_below) && dayOf(s.last_below)) below = [[dayOf(s.first_below), dayOf(s.last_below)]];
  if (!below.length) below = arr(s && (s.below || s.stretches)).filter((q) => Array.isArray(q) && dayOf(q[0]) && dayOf(q[1])).map((q) => [dayOf(q[0]), dayOf(q[1])]);
  const years = [...new Set([...arr(s && s.years).map(String), ...below.flatMap(([a, z]) => [a.slice(0, 4), z.slice(0, 4)])])].sort();
  return { line, dollars: isNum(dollars) ? dollars : null, sessions: isNum(sessions) ? sessions : null, below, years };
}
function capacityNote(cap) {                 // the fill's one label, the Result's own count and dates: "below it for 188 sessions, Apr 2022 to Jan 2023"
  if (!cap || cap.sessions === null) return null;
  if (cap.sessions === 0) return "never below it";
  const n = `below it for ${cap.sessions.toLocaleString("en-CA")} ${cap.sessions === 1 ? "session" : "sessions"}`, f = fmtOf();
  const a = cap.below.length ? cap.below[0][0] : null, z = cap.below.length ? cap.below[cap.below.length - 1][1] : null;
  if (f && a && z) { const ma = f.month(a), mz = f.month(z); if (ma && mz) return ma === mz ? `${n} in ${ma}` : `${n}, ${ma} to ${mz}`; }
  const yrs = cap.years.length > 1 ? `${cap.years.slice(0, -1).join(", ")} and ${cap.years[cap.years.length - 1]}` : cap.years[0];
  return yrs ? `${n} in ${yrs}` : n;
}
/* where the drawn line is under a flat level: the stretches of consecutive drawn points, as polygons like the hatch's */
function underOf(ts, values, level) {
  const out = [], flat = values.map(() => level);
  let cur = null;
  values.forEach((v, k) => {
    if (!isNum(v)) return;
    if (v < level) { if (cur) cur[1] = k; else cur = [k, k]; }
    else if (cur) { out.push(cur); cur = null; }
  });
  if (cur) out.push(cur);
  return out.map((st) => hatchOf(ts, values, flat, st)).filter(Boolean);
}

/* what a worst fall did to your floor, named as the dial names it (ruling R20): at a size the investor did not ask, "broke" is the
   server's own verdict at that size; else a fall that came within 1 point of the floor "touched" it; the asked size and a line
   with no move use the server's breaches */
function floorClassOf(depth, floor, broke) {
  if (broke) return "broke";
  if (!isNum(depth) || !isNum(floor)) return null;
  return tenths(depth) - tenths(floor) <= 10 ? "touched" : "held";
}
const FLOOR_TONE = { broke: "outside", touched: "caveat", held: "neutral" };

function worstPoint(line) {                // the deepest fall from a running high on the drawn line
  let high = -Infinity, best = null;
  line.forEach((v, k) => {
    if (!isNum(v)) return;
    if (v >= high) { high = v; return; }
    if (best === null || v / high - 1 < best.fall) best = { k, fall: v / high - 1 };
  });
  return best;
}

function partOf(b, src, i) {
  const paths = src.kind === "paths", asked = paths ? src.exact && i === src.asked : true, row = paths ? b.curve[i] : null;
  const D = src.dates, T = src.ts, last = D.length - 1, at = (d) => D.indexOf(d);
  const today = paths ? (src.k0 >= 0 ? src.wk.map((j) => (j >= 0 ? src.values[src.k0][j] : null)) : src.todaySeries) : src.today;
  const after = paths ? src.wk.map((j, k) => (j >= 0 ? src.values[i][j] : asked ? src.ins[k] : null)) : src.after;
  const line = after || today, ribbon = ribbonOf(line, b.floor);
  const breaches = (isNum(b.floor) ? episodesOf(line, b.floor) : []).map((ep) => {
    const from = D[ep.peak], to = D[ep.recover === null ? last : ep.recover];
    const x = asked ? b.rb.find((y) => y.trough >= from && y.trough <= to) || null : null;
    const peakDate = x ? x.peak : from, troughDate = x ? x.trough : D[ep.trough];
    return { peak: ep.peak, trough: x && at(x.trough) >= 0 ? at(x.trough) : ep.trough, recover: ep.recover, stretches: ep.stretches,
      hatch: ep.stretches.map((st) => hatchOf(T, line, ribbon, st)).filter(Boolean), result: !!x, peakDate, troughDate,
      recoverDate: x ? x.recover : ep.recover === null ? null : to, depth: x ? x.depth : null, dollars: x ? x.dollars : null,
      ...labelOf(b, peakDate, troughDate) };
  });
  /* the trough marker: the Result's worst fall (the deepest breach, else kpis.max_drawdown) on the evaluated mix; curve[i] elsewhere */
  const geo = worstPoint(line), kp = obj(obj(b.r.kpis) && b.r.kpis.max_drawdown), side = obj((obj(b.r.metrics) || {})[after ? "after" : "today"]);
  let worst = null;
  if (asked && b.rb.length) {
    const j = breaches.findIndex((x) => x.result && x.troughDate === b.rb[0].trough);
    const k = j >= 0 ? breaches[j].trough : geo ? geo.k : -1;
    if (k >= 0) worst = { k, depth: b.rb[0].depth, dollars: b.rb[0].dollars, breach: j, peakDate: b.rb[0].peak, troughDate: b.rb[0].trough,
      peakValue: b.rb[0].peakValue, troughValue: b.rb[0].troughValue };
  } else if (geo) {
    const depth = asked ? (kp && isNum(kp.value) ? kp.value : null) : row && isNum(row.max_drawdown) ? row.max_drawdown : null;
    /* R20: the dollars belong to the size asked; R35: the path's own (its high and trough), never the percent times the amount */
    const pv = kp && isNum(kp.peak_value) ? kp.peak_value : null, tv = kp && isNum(kp.trough_value) ? kp.trough_value : null;
    const dollars = asked && pv !== null && tv !== null ? Math.round(tv) - Math.round(pv) : null;
    const td = asked && side && dayOf(side.trough_date), k = td && at(td) >= 0 ? at(td) : geo.k;
    const j = breaches.findIndex((x) => k >= x.peak && k <= (x.recover === null ? last : x.recover));
    if (depth !== null) worst = { k, depth, dollars, breach: j, peakDate: asked && side ? dayOf(side.peak_date) : null, troughDate: td || D[k],
      peakValue: asked ? pv : null, troughValue: asked ? tv : null };
  }
  if (worst) {
    const named = worst.breach >= 0 ? breaches[worst.breach] : labelOf(b, worst.peakDate || worst.troughDate, worst.troughDate);
    const broke = asked ? worst.breach >= 0 && breaches[worst.breach].result : str(row && row.verdict) === "Incompatible";
    const cls = floorClassOf(worst.depth, b.floor, broke);
    Object.assign(worst, { t: T[worst.k], value: line[worst.k], past: cls === "broke", cls, word: cls ? FLOOR_WORDS[cls] : null,
      tone: cls ? FLOOR_TONE[cls] : null, depthText: pct(worst.depth), dollarsText: money(worst.dollars),
      label: named.label, labelKind: named.labelKind, eventId: named.eventId });
  }
  for (const x of breaches) Object.assign(x, { depthText: pct(x.depth), dollarsText: money(x.dollars) });
  /* the money line (R35): the path's own dollars, "−$249,413 ($1,473,670 → $1,224,257)": its high and its trough, Result keys */
  const pathText = (x) => (x && x.dollarsText && isNum(x.peakValue) && isNum(x.troughValue)
    ? `${x.dollarsText} (${money(Math.round(x.peakValue))} \u2192 ${money(Math.round(x.troughValue))})` : null);
  if (worst) worst.moneyText = pathText(worst);
  for (const x of breaches) {
    const rx = x.result ? b.rb.find((y) => y.trough === x.troughDate) : null;
    if (rx) Object.assign(x, { peakValue: rx.peakValue, troughValue: rx.troughValue });
    x.moneyText = pathText(x);
  }
  const w = paths ? b.P.weights[i] : b.move ? b.move.weight : null, k0 = b.P ? b.P.k0 : -1;
  /* the end values: the curve's own for a size of the curve; for a line drawn from the Result's series (no move, a size the
     curve does not carry, today's weight off the curve) the Result's end_values (amount x the series' last level, lane b3) */
  const ev = obj(b.r.end_values), evToday = ev && isNum(ev.today) ? ev.today : null, evAfter = ev && isNum(ev.after) ? ev.after : null;
  const ends = { today: k0 >= 0 && isNum(b.curve[k0].end_value) ? b.curve[k0].end_value : evToday,   // R20: no end value for another size
    after: paths ? (asked && row && isNum(row.end_value) ? row.end_value : null) : after ? evAfter : null };
  const cap = capacityOf(b.r, after ? "after" : "today");
  const capacity = cap ? { ...cap, under: underOf(T, line, cap.line), note: asked ? capacityNote(cap) : null,   // the count is the asked size's
    label: cap.dollars !== null ? `What you can afford to lose: ${money(cap.dollars)}` : "What you can afford to lose" } : null;
  return { today, after, ribbon, breaches, worst, capacity, weight: w, weightIndex: paths ? i : null, asked, whatIf: paths && !asked, todayPriced: paths && k0 >= 0,
    ends: { ...ends, todayText: money(ends.today), afterText: money(ends.after) }, verdict: row ? str(row.verdict) : str(b.r.verdict) };
}

const TODAY = "Today’s mix", RIBBON = "Your floor follows every new high", BELOW = "Below your floor";
const WHAT_IF = "A replay at another size, not a recommendation.";   // ruling R20, the dial's own caption

/* raceModel(result, weightIndex): weightIndex is a position on tipping_point.curve (0..40), null = the asked size. Null when
   the Result cannot draw a line (no amount, no series). The arrays are shared between the models of one Result: read-only. */
export function raceModel(result, weightIndex = null) {
  const r = obj(result);
  if (!r) return null;
  const b = baseOf(r);
  if (!b.kind) return null;
  const P = b.P, n = P ? P.weights.length : 0;
  let src = P, i = P ? P.asked : null;
  if (P && Number.isInteger(weightIndex)) i = Math.min(n - 1, Math.max(0, weightIndex));
  else if (!(P && P.exact) && b.S) { src = b.S; i = null; }   // an asked size the curve does not carry: the server's own series
  const part = partOf(b, src, i), v = b.v || {}, floorText = isNum(b.floor) ? share(Math.abs(b.floor)) : null;
  const who = v.who && v.who.name ? v.who.name : null, family = v.shockFamily || null;   // framing only (R18): never printed in the chart
  return {
    kind: src.kind, amount: b.amount, amountText: money(b.amount), floor: b.floor, floorText, dates: src.dates, ts: src.ts, domain: b.domain,
    shocks: b.shocks, ticker: b.ticker || null, name: b.name || null, who, family: b.family, familyLabel: family,
    weights: n ? P.weights : null, askedIndex: n ? P.asked : null, exact: !!(P && P.exact), ...part,
    bands: b.bands,
    labels: { after: part.after && b.name && isNum(part.weight) ? (part.whatIf ? `At ${share(part.weight)}: what-if` : `With ${share(part.weight)} ${b.name}`) : null,
      whatIf: part.whatIf ? WHAT_IF : null,
      today: part.after ? TODAY : "Your mix", ribbon: floorText ? `Your floor follows every new high` : RIBBON,
      rule: floorText ? `Your floor (${floorText} from a high)` : "Your floor", below: floorText ? `Below your floor` : BELOW,
      ribbonNote: null, shocks: family ? `${family} shocks` : null,
      start: dateText(src.dates[0]), end: dateText(src.dates[src.dates.length - 1]) },
    growth: { today: v.growth && v.growth.today ? v.growth.today.text : null, after: v.growth && v.growth.after ? v.growth.after.text : null },
    at: n ? (j) => raceModel(r, j) : null,
  };
}

/* a model from any one window of points (lane U8's deep-history panel: monthly "YYYY-MM" dates are fine). o: {dates, today,
   after?, amount?, floor?, labels?, worst?: {date, depth, dollars, label}} where every number the caller passes is a Result key.
   The breaches are the stretches past the floor, unnumbered: only `worst` carries figures. */
export function raceModelFromSeries(o) {
  o = obj(o) || {};
  const dates = arr(o.dates).map(dayOf), today = arr(o.today), after = Array.isArray(o.after) ? o.after : null;
  if (dates.length < 2 || !dates.every((d) => d && isNum(timeOf(d))) || today.length !== dates.length || (after && after.length !== dates.length)) return null;
  const floor = isNum(o.floor) ? o.floor : null, ts = dates.map(timeOf), line = after || today, ribbon = ribbonOf(line, floor);
  const breaches = (floor === null ? [] : episodesOf(line, floor)).map((ep) => ({ peak: ep.peak, trough: ep.trough, recover: ep.recover,
    stretches: ep.stretches, hatch: ep.stretches.map((s) => hatchOf(ts, line, ribbon, s)).filter(Boolean), result: false,
    peakDate: dates[ep.peak], troughDate: dates[ep.trough], recoverDate: ep.recover === null ? null : dates[ep.recover],
    depth: null, dollars: null, depthText: null, dollarsText: null, moneyText: null, label: null, labelKind: null, eventId: null }));
  let lo = Infinity, hi = -Infinity;
  for (const row of [today, after, ribbon]) for (const x of arr(row)) if (isNum(x)) { lo = Math.min(lo, x); hi = Math.max(hi, x); }
  const w = obj(o.worst), k = w ? dates.indexOf(dayOf(w.date)) : -1, amount = isNum(o.amount) && o.amount > 0 ? o.amount : null;
  const wcls = w && isNum(w.depth) ? floorClassOf(w.depth, floor, pastFloor(w.depth, floor)) : null;
  const worst = w && k >= 0 && isNum(w.depth) ? { k, t: ts[k], value: line[k], depth: w.depth, depthText: pct(w.depth), dollars: isNum(w.dollars) ? w.dollars : null,
    dollarsText: money(isNum(w.dollars) ? w.dollars : null), past: wcls === "broke", cls: wcls, word: wcls ? FLOOR_WORDS[wcls] : null, tone: wcls ? FLOOR_TONE[wcls] : null,
    moneyText: isNum(w.dollars) ? money(w.dollars) : null,   // the caller's own dollars (R35: never the percent times the amount)
    breach: breaches.findIndex((x) => k >= x.peak && (x.recover === null || k <= x.recover)),
    label: str(w.label), labelKind: str(w.label) ? "given" : null, eventId: null, peakDate: null, troughDate: dates[k] } : null;
  const L = obj(o.labels) || {};
  return { kind: "window", amount, amountText: money(amount), floor, floorText: isNum(floor) ? share(Math.abs(floor)) : null, dates, ts,
    domain: { t0: ts[0], t1: ts[ts.length - 1], y0: lo, y1: hi }, shocks: [], ticker: null, name: null, who: null, family: null, familyLabel: null,
    weights: null, askedIndex: null, today, after, ribbon, breaches, worst, capacity: null, weight: null, weightIndex: null, asked: true, whatIf: false, verdict: null, bands: [],
    ends: { today: null, after: null, todayText: null, afterText: null },
    labels: { after: str(L.after), whatIf: null, today: str(L.today) || "This mix", ribbon: str(L.ribbon) || RIBBON, below: str(L.below) || BELOW,
      ribbonNote: str(L.ribbonNote), shocks: null, start: str(L.start), end: str(L.end) },
    growth: { today: null, after: null }, at: null };
}
