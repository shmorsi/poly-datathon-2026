/* Lane U1 pure helpers: the hero's words and the globe's choreography, from one Result and its PF.view. No DOM, no network.
   Every number the hero prints is a Result key (via PF.view); nothing here invents one. A missing key gives null and the hero
   hides that line. Imported by web/sections/hero.js and web/globe.js; tested by tests/web_u1_test.mjs under node. */

export const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const NB = "\u00a0";

/* the view the hero opens on: the lead's composition (Sun 01:00, R25): North America, the disc centre at 20° N, 80° W */
export const HOME = Object.freeze({ lat: 20, lon: -80 });
/* the investors' home market (every persona's mix is held in Canada): the turn when the question names no shock */
export const HOME_MARKET = Object.freeze({ lat: 43.65, lon: -79.38, place: "Toronto" });
/* the first five seconds: the Earth sweeps east to west (Asia, then Europe and the Middle East, then the Americas) while the
   shocks ignite, and settles on the investor's view. SWEEP degrees of turn; the start is the end turned that far east. */
export const SWEEP = 195;
export const sweepStart = (end) => ({ lat: end.lat, lon: end.lon + SWEEP });
/* the first frame is always the sweep poster's view (sweepStart(HOME): 20° N, 115° E, Asia), whoever the investor is, so the
   poster and the first WebGL frame match. The turn then goes west to the investor's view (Robert: 195°, past Europe and the
   Middle East to the Americas), or the short way east when west is most of a full turn (Amira's chip war is already in view).
   Literal longitudes, for globe.sweep. */
export const SWEEP_FROM = Object.freeze(sweepStart(HOME));
export function sweepPath(end) {
  const e = obj(end) && isNum(end.lat) && isNum(end.lon) ? end : HOME;
  const west = (((SWEEP_FROM.lon - e.lon) % 360) + 360) % 360;
  return { from: { ...SWEEP_FROM }, to: { lat: e.lat, lon: west > 270 ? SWEEP_FROM.lon + (360 - west) : SWEEP_FROM.lon - west } };
}

/* the motion tokens of web/styles.css, as functions of p in [0, 1] (the same cubic-bezier curves CSS uses) */
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (t) => ((ax * t + bx) * t + cx) * t, Y = (t) => ((ay * t + by) * t + cy) * t, dX = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (p) => {
    if (!(p > 0)) return 0;
    if (p >= 1) return 1;
    let t = p;
    for (let i = 0; i < 8; i++) { const e = X(t) - p, d = dX(t); if (Math.abs(e) < 1e-7) return Y(t); if (Math.abs(d) < 1e-6) break; t -= e / d; }
    let lo = 0, hi = 1; t = p;                                   // bisection when Newton stalls (flat ends of the curve)
    for (let i = 0; i < 40; i++) { const x = X(t); if (Math.abs(x - p) < 1e-7) break; if (x < p) lo = t; else hi = t; t = (lo + hi) / 2; }
    return Y(t);
  };
}
export const easeOut = bezier(0.23, 1, 0.32, 1);          // --ease-out
export const easeInOut = bezier(0.77, 0, 0.175, 1);       // --ease-in-out
/* the first-five-second turn only, the one long camera move: a gentle in-out (peak 1.6 x the mean speed, about 65° a second
   over 195°), so Asia, then Europe and the Middle East, then the Americas read as they pass; --ease-in-out would whip through
   Europe at 210° a second */
export const easeTurn = bezier(0.37, 0, 0.63, 1);

/* the family the investor asked about: the navigator's first family (scenario.families[0]); null when no shock is named */
export function askedFamily(result) {     // the same rule as replay.js askedFamilyOf: the first family the navigator picked a precedent in
  const s = obj(result) && obj(result.scenario);
  if (s && obj(s.weather) && s.weather.no_precedent === true && !arr(s.event_ids).length) return null;   // the abstention
  const fams = s ? arr(s.families).map(str).filter(Boolean) : [];
  const picked = arr(obj(result) && result.events).filter((e) => obj(e) && e.picked === true);
  return fams.find((f) => picked.some((e) => e.family === f)) || fams[0] || null;
}

/* the shocks the globe draws, from PF.view(result).shocks (date order, each at its epicentre, its trough on the evaluated mix:
   events[].after with a move, else today; null when the Result has none, never invented) */
export function shocksOf(view) {
  const s = obj(view) && obj(view.shocks);
  return s ? arr(s.events).filter((e) => obj(e) && str(e.id) && isNum(e.lat) && isNum(e.lon)) : [];
}

/* ignition order: date order, ties by id (the order the shocks happened) */
export function ignitionOrder(events) {
  return arr(events).filter((e) => obj(e) && str(e.id) && typeof e.date === "string")
    .map((e, i) => [e, i]).sort(([a, i], [b, j]) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : i - j))
    .map(([e]) => e.id);
}

/* when each shock ignites, in ms from the start: evenly spaced so the last ring has settled (ringMs) by totalMs */
export function ignitionSchedule(ids, totalMs, ringMs = 600) {
  const list = arr(ids), n = list.length, span = Math.max(0, (isNum(totalMs) ? totalMs : 0) - ringMs);
  return list.map((id, i) => ({ id, at: n > 1 ? Math.round((i * span) / (n - 1)) : 0 }));
}

/* a ring's radius as a share of the globe's radius: it encodes how far the mix fell after the shock (the measured trough).
   No fall (a missing trough, a rise, or one that rounds to 0.0 %) gives null: no ring, just the light. */
export const RING_MIN = 0.012, RING_PER_FALL = 0.45, RING_CAP = 0.5;
export function ringRadius(trough) {
  if (!isNum(trough) || trough >= 0 || Math.round(Math.abs(trough) * 1000) === 0) return null;
  return RING_MIN + RING_PER_FALL * Math.min(RING_CAP, Math.abs(trough));
}

/* the asked family's worst precedent: its shock with the deepest trough on the evaluated mix (ties: the earlier one) */
export function worstPrecedent(view, family) {
  if (!str(family)) return null;
  let best = null;
  for (const e of shocksOf(view)) {
    if (e.family !== family || !isNum(e.trough) || ringRadius(e.trough) === null) continue;
    if (!best || e.trough < best.trough || (e.trough === best.trough && e.date < best.date)) best = e;
  }
  return best;
}

/* degrees of arc between two points on the globe */
export function arcDeg(a, b) {
  const R = Math.PI / 180, p1 = a.lat * R, p2 = b.lat * R, dl = (b.lon - a.lon) * R;
  const c = Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(dl);
  return Math.acos(Math.max(-1, Math.min(1, c))) / R;
}

/* the hero's turn for this investor: the lead's composition when the asked shock's epicentre is in good view from it (within
   45° of the disc centre); else the globe turns so that epicentre sits where Washington sits in the composition */
export function heroView(worst) {
  if (!obj(worst) || !isNum(worst.lat) || !isNum(worst.lon)) return { ...HOME };
  if (arcDeg(HOME, worst) <= 45) return { ...HOME };
  const lon = ((((worst.lon - 3) + 180) % 360) + 360) % 360 - 180;
  return { lat: Math.max(-10, Math.min(35, Math.round(worst.lat - 19))), lon: Math.round(lon) };
}

/* the one calm caption under the globe: the asked family's name and how many episodes of it the Result counts
   (turbulence[family].n, the count sentence 2 uses). A question that names no shock says so (the replay covers the mix's own
   five years); null only without a Result. */
export function heroCaption(result, view) {
  if (!obj(result)) return null;
  const fam = askedFamily(result), v = obj(view) || {};
  if (!fam) {   // nothing asked (Too Canadian?), or an abstention (a shock with no close precedent: askedFamily's rule)
    const named = arr(obj(result.scenario) && result.scenario.families).some(str);
    return { family: null, label: named ? "No close precedent on record:" : "No shock named:", n: null,
      count: "the replay covers your mix\u2019s own five years", none: true };
  }
  const label = (shocksOf(v).find((e) => e.family === fam && str(e.familyLabel)) || {}).familyLabel || str(v.shockFamily);
  if (!label) return null;
  const t = obj(obj(result) && obj(result.turbulence) && result.turbulence[fam]);
  const n = t && Number.isInteger(t.n) && t.n > 0 ? t.n : null;
  return { family: fam, label, n, count: n === null ? null : `${n} earlier episode${n === 1 ? "" : "s"} on record` };
}

/* the quiet counter that rises with the ignition, in step with the lights: "1 shock on record" … "37 shocks on record" (n is
   how many have lit; at the end every shock of PF.view). No dates beside it: R22 keeps the hero to about six numbers. */
export function counterText(n) {
  if (!Number.isInteger(n) || n < 1) return null;
  return { n: String(n), rest: ` shock${n === 1 ? "" : "s"} on record` };
}

/* the legend, bottom right: what a ring is and what its size means, in the second person (R18); the count is the counter's line */
export function legendText(view) {
  const v = obj(view) || {};
  const lead = "Each ring is a shock: tariffs, war and oil, chips, rates.";   // a ring, not a light (the Earth is full of city lights); the count is the counter's
  const ring = v.move ? "The wider its ring, the further your mix with the move fell after it." : "The wider its ring, the further your mix fell after it.";
  return { lead, ring, past: "This already happened; it is not a forecast." };   // red gate 4: history is shown
}

/* the one persona sentence under the command bar (R22), as [text, kind] segments ("num" = an inline figure): plain words, no
   dot-joined meta strings (R16), the persona's name only here (the framing label), no his/her (R18). The limit is the persona's
   assumption (R13); the note says it is fiction and whose limits these are (R4). */
/* what each case tests (the official brief's three personas plus the finance workshop's worked example), one short tag for
   the chip and one sentence under the chips: the jury sees which case it is testing before it presses Replay */
const CASES = Object.freeze({
  robert: Object.freeze({ tag: "Hyped request", tests: "Robert’s case: does it push back on a hyped request?" }),
  mateo: Object.freeze({ tag: "Values decide", tests: "Mateo’s case: do his values count, not only return?" }),
  amira: Object.freeze({ tag: "Not anything goes", tests: "Amira’s case: high risk, but not anything goes." }),
  canadian: Object.freeze({ tag: "Workshop example", tests: "The workshop’s case: does adding the S&P 500 diversify a Canadian mix?" }),
});
export const caseLine = (id) => (typeof id === "string" && Object.prototype.hasOwnProperty.call(CASES, id) ? CASES[id] : null);

/* the first screen's one line on where it fits and what runs it (the lead 19:25): an order-execution-only broker may not advise,
   so the page is a pre-trade check; AWS by name, each service by its one job */
export const STACK_LINE = "A pre-trade check for self-directed investors, never advice. Claude on Amazon Bedrock reads the words, Bedrock Guardrails screens them first, and code computes every number.";
export const PERSONA_NOTE ="Fictional illustration, not a recommendation. Fictional profiles; their limits are assumed. Type your own on the live app, or describe yourself under You.";   // R38 (the controller, 16:50)
/* R35 (15:55, the workshop's "tolerance ≠ capacity"): the two limits stay apart. CAPACITY, what the profile can afford to lose in
   dollars, and the value to stay above (the amount minus that capacity, R35's own "$600,000 − $90,000"); TOLERANCE, the floor
   rule: no fall of more than the floor's percent from any high. Never one "loss limit" for both. */
const money = (x) => (isNum(x) ? "$" + Math.round(Math.abs(x)).toLocaleString("en-CA") : "");
export function personaLines(view, result) {
  const v = obj(view) || {}, who = obj(v.who) || {};
  const name = str(who.name), amount = str(v.amountText), limit = str(v.capacityText);
  if (!name) return null;
  const fl = obj(v.floor) && str(v.floor.text) ? v.floor.text.replace(/^[\u2212-]/, "") : null;
  const C = obj(obj(result) && result.capacity), runLine = C && obj(C.today) && isNum(C.today.line) ? C.today.line : null;   // the run's own line
  const above = runLine !== null ? money(runLine)
    : isNum(v.amount) && isNum(v.capacity) && v.capacity > 0 && v.capacity < v.amount ? money(v.amount - v.capacity) : null;
  /* the lead 19:10: the front page is the portfolio and the words; the limits are ONE quiet line under who the investor is.
     R35 still holds: the floor (tolerance, from any high) and the line to stay above (capacity, in dollars) stay apart. */
  const rules = [];
  if (fl) rules.push(["no fall of more than "], [fl, "num"], [" from a high"]);
  if (above) rules.push([rules.length ? ", and stay above " : "stay above "], [above, "num"]);
  else if (limit) rules.push([rules.length ? ", and lose no more than " : "lose no more than "], [limit, "num"]);
  const limits = rules.length ? [["Limits used, assumed for this fictional profile: "], ...rules, ["."]] : [];
  const segs = [];
  if (isNum(who.age)) {                                           // "Robert, 59, has $600,000."
    segs.push([`${name}, `], [String(who.age), "num"]);
    if (amount) segs.push([", has "], [amount, "num"]);
    segs.push(["."]);
  } else if (amount) segs.push(["A "], [amount, "num"], [" portfolio."]);   // no age (Too Canadian?): the portfolio itself is the fiction
  else segs.push([`${name}.`]);
  return { who: segs, limits, note: PERSONA_NOTE };
}

/* RETHINK G3 (lane hold): the profile's objective and horizon, one more sentence after the persona's, from result.profile
   (goal, horizon_years) and nothing else; the horizon in words (the persona blurbs' own "about four years"), so the closed
   hero still shows at most six figures (R22) */
const GOAL_WORDS = { preservation: "preserve capital with some growth", balance: "balance growth and stability", growth: "grow capital" };
const SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
  "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
export function aimLine(result) {
  const p = obj(obj(result) && result.profile) || {};
  const goal = typeof p.goal === "string" && Object.prototype.hasOwnProperty.call(GOAL_WORDS, p.goal) ? GOAL_WORDS[p.goal] : null;
  const y = isNum(p.horizon_years) && p.horizon_years > 0 ? Math.round(p.horizon_years) : null;
  if (!goal) return null;
  const years = y === null ? "" : `, over about ${y <= 20 ? SMALL[y] : y} year${y === 1 ? "" : "s"}`;
  return `Objective: ${goal}${years}.`;
}

/* every string the hero shows once the lights have settled (closed state, R22): the question, the persona sentence and its note,
   the counter, the caption and the legend; numbersIn counts the figures a reader sees (R22: about six in the first viewport) */
export function heroCopy(result, view) {
  const r = obj(result), v = obj(view), sh = v && obj(v.shocks);
  const question = r ? str(r.question) : null, persona = v ? personaLines(v, r) : null;
  const counter = sh && Number.isInteger(sh.n) && sh.n > 0 ? counterText(sh.n) : null;
  const cap = r && v ? heroCaption(r, v) : null, legend = legendText(v), aim = persona ? aimLine(r) : null;
  const strings = [question, persona && persona.who.map(([t]) => t).join(""), persona && persona.limits.map(([t]) => t).join(""), aim, persona ? persona.note : PERSONA_NOTE,
    counter && counter.n + counter.rest, cap && [cap.label, cap.count].filter(Boolean).join(" "), legend.lead, legend.ring, legend.past];
  return { question, persona, aim, counter, cap, legend, strings: strings.filter(Boolean) };
}
export const numbersIn = (text) => (String(text || "").match(/\d[\d,.]*/g) || []).length;

/* the hero's globe box inside the hero, in CSS px: the disc centre (cx, cy) and radius r, mirroring web/css/hero.css (R41,
   lane polish-hero; hero.js itself reads the slot's box live). Desktop: an instrument in the right half (cols 7-12; 8-12 at
   1100 px and under), under the headline's row and its counter, over its key: the largest disc that leaves, at most 540 px
   across and never more than the first screen leaves. Phone (<= 760 px): a small band above the words, 26 % of the width,
   at most 220 px across, under its counter. */
const clampN = (lo, x, hi) => Math.min(hi, Math.max(lo, x));
export function heroFrame(w, h, bar = 64) {
  if (!(w > 0) || !(h > 0)) return { cx: 0, cy: 0, r: 0 };
  if (w <= 760) { const r = Math.round(Math.min(0.26 * w, 110)); return { cx: w / 2, cy: bar + 8 + 27 + 8 + r, r }; }
  const margin = clampN(16, 0.045 * w, 64), gutter = clampN(16, 0.02 * w, 32), page = Math.min(1360, w - 2 * margin);
  const col = (page - 11 * gutter) / 12, from = w <= 1100 ? 7 : 6, left = (w - page) / 2 + from * (col + gutter);
  const width = (12 - from) * col + (11 - from) * gutter;
  const head = clampN(36, 12 + 0.025 * w, 48) * 0.92 + 8 + 25.2 + 4 + 21;    // the headline's line, its sub-line, the French line
  const top = bar + 12 + head + 20 + 27, bottom = h - 16 - 12 - 68;          // under the counter, over the key
  const r = Math.round(Math.max(0, Math.min(270, h / 2 - 165, width / 2, (bottom - top) / 2)));
  return { cx: Math.round(left + width / 2), cy: Math.round((top + bottom) / 2), r };
}

/* the stage's globe box (left third of the #replay stage, or the stage's own [data-globe-slot] box when it has one) */
export function stageFrame(box, slotted = false) {
  const b = obj(box);
  if (!b || !(b.width > 0) || !(b.height > 0)) return null;
  if (slotted) return { cx: b.left + b.width / 2, cy: b.top + b.height / 2, r: Math.min(b.width, b.height) / 2 };
  if (b.width <= 760) { const r = Math.round(Math.min(0.3 * b.width, 0.16 * b.height)); return { cx: b.left + b.width / 2, cy: b.top + 72 + r, r }; }
  const r = Math.round(Math.min(b.width / 6 - 24, 0.3 * b.height));
  return { cx: b.left + b.width / 6, cy: b.top + b.height / 2, r };
}

/* where a sticky one-viewport stage sits inside its (possibly taller) section, given the section's viewport box */
export function stickyBox(rect, vh) {
  const r = obj(rect);
  if (!r || !(vh > 0)) return null;
  const h = Math.min(vh, r.height), top = Math.max(r.top, Math.min(0, r.bottom - h));
  return { left: r.left, top, width: r.width, height: h, bottom: top + h };
}

export const mix = (a, b, k) => a + (b - a) * k;
export function mixFrame(a, b, k) {
  if (!a) return b; if (!b || k <= 0) return a; if (k >= 1) return b;
  return { cx: mix(a.cx, b.cx, k), cy: mix(a.cy, b.cy, k), r: mix(a.r, b.r, k) };
}

/* the inverse of the globe's camera (web/globe.js, PF.globeProject: distance D radii, the view {lat, lon} at the disc centre):
   a point of the disc in units of its radius (x right, y down) → {lat, lon, facing} under it, or null off the disc. facing is
   n·v at that point (the shader's rim uses it). The no-WebGL Earth is drawn from it pixel by pixel. */
export function unproject(sx, sy, view, D = 6) {
  const R = Math.PI / 180, tanA = 1 / Math.sqrt(D * D - 1);
  let dx = sx * tanA, dy = -sy * tanA, dz = -1;
  const len = Math.hypot(dx, dy, dz); dx /= len; dy /= len; dz /= len;
  const b = D * dz, disc = b * b - (D * D - 1);
  if (disc < 0) return null;
  const t = -b - Math.sqrt(disc);
  const X = dx * t, Y = dy * t, Z = D + dz * t;                       // the hit point, view space (unit sphere)
  const ph = view.lat * R, th = -(Math.PI / 2 + view.lon * R);
  const y = Y * Math.cos(ph) + Z * Math.sin(ph), z1 = -Y * Math.sin(ph) + Z * Math.cos(ph);   // undo the tilt
  const x = X * Math.cos(th) - z1 * Math.sin(th), z = X * Math.sin(th) + z1 * Math.cos(th);   // undo the turn
  const vx = -X, vy = -Y, vz = D - Z, vl = Math.hypot(vx, vy, vz);
  return { lat: Math.asin(Math.max(-1, Math.min(1, y))) / R, lon: Math.atan2(-z, x) / R, facing: (X * vx + Y * vy + Z * vz) / vl };
}
