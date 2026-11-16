/* The race chart (lane U3; design doc §2 2d and §3; rulings R1, R13): the investor's money over time in dollars, today's mix
   (grey) against the move (magenta), the gold floor that follows every new high, the red hatch where the move fell past it.
   createRace(el, model, opts) -> { draw(p), setWeight(i), xOfDate(iso), yOfValue(v), markers(), destroy() }.
   One SVG for the marks, HTML for the words. Every figure printed is a Result key handed over by the model (web/lib/race.js);
   the renderer only places them. No timers and no loop of its own: the stage's timeline calls draw(p); the dial calls
   setWeight(i) and the chart follows 1:1. Text goes in through textContent only. */
import { raceModel, raceModelFromSeries, timeOf } from "./lib/race.js";
import { FLOOR_WORDS } from "./lib/status.js";   // the page's one status vocabulary (lane U5)
export { raceModel, raceModelFromSeries };

const NS = "http://www.w3.org/2000/svg";
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
const fmt = () => (globalThis.PF && globalThis.PF.fmt) || null;
const MONEY = new Map();                   // the readouts ask for the same weekly values again and again
const money = (x) => {
  if (!fmt() || !isNum(x)) return "";
  let t = MONEY.get(x);
  if (t === undefined) { t = fmt().money(x); if (MONEY.size > 4000) MONEY.clear(); MONEY.set(x, t); }
  return t;
};
const dateText = (d) => (fmt() && d ? fmt().date(d) || fmt().month(d) : "");
const pct = (x) => (fmt() && isNum(x) ? fmt().pct(x) : "");
let uid = 0;

function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}
function sv(tag, attrs = {}) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) e.setAttribute(k, String(v));
  return e;
}
const r1 = (x) => Math.round(x * 10) / 10;
function pathOf(xs, ys) {                  // one path through every point that has a value (inserted days skip on other lines)
  let d = "", open = false;
  for (let k = 0; k < xs.length; k++) {
    if (!isNum(ys[k])) continue;
    d += (open ? "L" : "M") + r1(xs[k]) + "," + r1(ys[k]);
    open = true;
  }
  return d;
}
function bsearch(ts, t) {                   // the last index whose time is <= t (0 when t is before the first)
  let lo = 0, hi = ts.length - 1;
  if (t <= ts[0]) return 0;
  if (t >= ts[hi]) return hi;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (ts[mid] <= t) lo = mid; else hi = mid; }
  return lo;
}
function nearest(ts, t) { const k = bsearch(ts, t); return k < ts.length - 1 && t - ts[k] > ts[k + 1] - t ? k + 1 : k; }
const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const ICONS = { broke: "M4 4l8 8M12 4l-8 8", touched: "M8 3v6M8 12.5v.5" };   // drawn glyphs: status is icon + word, never colour alone
function playIcon(playing) {                 // a drawn play / pause glyph (no character icons)
  const s = sv("svg", { class: "race-ico-play", viewBox: "0 0 16 16", "aria-hidden": "true" });
  s.append(sv("path", { d: playing ? "M5 3.5v9M11 3.5v9" : "M5 3.5l8 4.5-8 4.5z" }));
  return s;
}
function statusIcon(cls = "broke") {
  const s = sv("svg", { class: "race-ico", viewBox: "0 0 16 16", "aria-hidden": "true" });
  s.append(sv("path", { d: ICONS[cls] || ICONS.broke }));
  return s;
}

export function createRace(el, model, opts = {}) {
  const id = ++uid, o = { p: 1, legend: true, foot: true, compact: false, roll: true, ...opts };
  let M = model, P = clamp(isNum(o.p) ? o.p : 1, 0, 1), G = null, G0 = {}, ro = null, frame = 0, cursor = -1, alive = true, lastWeek = -1;
  let tipShape = "", tipW = 0, tipH = 0, liveT = 0, pinT = 0;
  const fig = h("figure", "race" + (o.compact ? " is-compact" : ""));
  const legend = h("ul", "race-legend"), stage = h("div", "race-stage");
  stage.tabIndex = 0;
  stage.setAttribute("role", "group");
  const svg = sv("svg", { class: "race-svg", "aria-hidden": "true", focusable: "false" });
  const hatchId = `race-hatch-${id}`, clipId = `race-clip-${id}`, defs = sv("defs");
  const pat = sv("pattern", { id: hatchId, patternUnits: "userSpaceOnUse", width: 6, height: 6, patternTransform: "rotate(45)" });
  pat.append(sv("rect", { class: "race-hatch-wash", width: 6, height: 6 }), sv("line", { class: "race-hatch-line", x1: 0, y1: 0, x2: 0, y2: 6 }));
  const clip = sv("clipPath", { id: clipId }), clipRect = sv("rect", { x: 0, y: 0, width: 0, height: 0 });
  clip.append(clipRect);
  defs.append(pat, clip);
  const gGrid = sv("g", { class: "race-grid" }), gAxis = sv("g", { class: "race-axis" }), gShock = sv("g", { class: "race-shocks" });
  const gPlot = sv("g", { class: "race-plot", "clip-path": `url(#${clipId})` });
  const gHatch = sv("g", { class: "race-hatch" }), gCapFill = sv("g", { class: "race-capfills" }), pFloorBand = sv("path", { class: "race-floorband" });
  const pToday = sv("path", { class: "race-today" }), pRibbon = sv("path", { class: "race-ribbon" }), pBreak = sv("path", { class: "race-break" });
  const pFlash = sv("path", { class: "race-ribbon-flash" });   // the floor brightens once when the dial crosses the break (lane U4)
  const pCase = sv("path", { class: "race-casing" }), pAfter = sv("path", { class: "race-after" });
  gPlot.append(pFloorBand, gCapFill, gHatch, pToday, pRibbon, pFlash, pBreak, pCase, pAfter);
  const gMarks = sv("g", { class: "race-marks" }), gCur = sv("g", { class: "race-cursor" }), gLead = sv("g", { class: "race-leads" });
  const curLine = sv("line", { class: "race-cur-line" }), curA = sv("circle", { class: "race-cur-after", r: 4 }), curT = sv("circle", { class: "race-cur-today", r: 3.5 });
  gCur.append(curLine, curT, curA);
  svg.append(defs, gGrid, gAxis, gShock, gPlot, gLead, gMarks, gCur);
  const labels = h("div", "race-labels"), head = h("div", "race-head"), headDate = h("span", "race-head-date");
  head.setAttribute("aria-hidden", "true");
  const headLine = h("span", "race-head-line"), headText = h("span", "race-head-text"), headVal = h("span", "race-head-val"), headPast = h("span", "race-head-past");
  headPast.append(statusIcon("broke"), document.createTextNode(FLOOR_WORDS.broke));
  headText.append(headDate, headVal, headPast);
  head.append(headLine, headText);
  const tip = h("div", "race-tip");
  tip.hidden = true;
  stage.append(svg, labels, head, tip);
  const controls = h("div", "race-controls"), playBtn = h("button", "race-play"), scrub = document.createElement("input");
  playBtn.type = "button";
  playBtn.setAttribute("aria-label", "Play through the weeks");
  playBtn.append(playIcon(false));
  scrub.type = "range";
  scrub.className = "race-scrub";
  scrub.min = "0";
  scrub.step = "1";
  scrub.setAttribute("aria-label", "Move through the weeks: the readout follows");
  controls.append(playBtn, scrub);
  const foot = h("p", "race-foot"), sr = h("div", "sr"), live = h("p", "sr");
  sr.id = `race-sr-${id}`;
  live.setAttribute("aria-live", "polite");
  stage.setAttribute("aria-describedby", sr.id);
  fig.append(legend, stage, controls, foot, sr, live);
  el.append(fig);

  /* ---- geometry: scales from the model's fixed domain (the same for every size, so the dial never rescales the chart) ---- */
  function layout() {
    if (!M) return;
    const W = Math.max(280, Math.round(stage.clientWidth || el.clientWidth || 800)), mob = W < 640;
    /* fill the element when it has a height of its own (the stage's grid row); size from the width when it has none (opts.fill
       forces either way) */
    stage.style.height = "";
    let H = Math.round(stage.clientHeight);
    if (o.fill === false || (o.fill !== true && H < 40)) { H = Math.round(clamp(W * (mob ? 1.15 : 0.5), 280, 560)); stage.style.height = H + "px"; }
    fig.classList.toggle("is-short", H < 340);   // a short stage (the replay's one viewport): smaller words, same marks
    fig.style.setProperty("--race-fig", `${Math.round(clamp(H / 11, 26, 48))}px`);   // the big trough figure scales with the plot
    words();                                 // the words first: the end labels' width sets the right margin on wide screens
    const ends = Math.max(0, ...(G0.items || []).filter((it) => it.kind === "end").map((it) => it.box.offsetWidth));
    const endW = ends && isNum(M.floor) ? Math.max(ends, 120) : ends;   // the margin also holds the floor's own label
    const gx = o.compact ? 8 : mob ? 12 : 56, x0 = gx, x1 = W - (mob || o.compact || !endW ? gx : Math.max(gx, endW + 28));
    const bandRow = !o.compact && (M.bands || []).length ? (mob ? 44 : 22) : 0;   // a bracket row under the years (a phone: its name under it)
    const short = H < 340, y0 = o.compact ? 16 : mob ? 40 : short ? 22 : 36, y1 = H - (o.compact ? 30 : short ? 32 : 42) - bandRow, d = M.domain, span = d.t1 - d.t0 || 1;
    /* money on a log scale: an equal fall from any high is an equal drop on the screen, so the floor rides at one distance
       under every high and 2022's fall reads as large as it was (no y ticks: the Result's own numbers label the line) */
    const log = d.y0 > 0, f = (v) => (log ? Math.log(v) : v), pad = (f(d.y1) - f(d.y0)) * 0.05 || 1, lo = f(d.y0) - pad, hi = f(d.y1) + pad;
    const X = (t) => x0 + ((t - d.t0) / span) * (x1 - x0), Y = (v) => y1 - ((f(v) - lo) / (hi - lo)) * (y1 - y0);
    G = { W, H, mob, x0, x1, y0, y1, X, Y, log, endW: mob || o.compact ? 0 : endW, items: G0.items, fresh: true, yBand: y1 + (short ? 40 : 46) };
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    clipRect.setAttribute("height", H);
    controls.hidden = !!o.compact;
    scrub.max = String(Math.max(0, M.dates.length - 1));
    if (cursor < 0) scrub.value = scrub.max;   // at rest the scrub sits at the last week
    controls.style.paddingLeft = `${Math.max(0, x0 - 40)}px`;
    scrub.style.width = `${Math.max(80, x1 - x0 - (x0 >= 40 ? 0 : 40))}px`;
    tipW = 0;                                // a new layout measures the readout again
    headLine.style.top = `${y0}px`;
    headLine.style.height = `${y1 - y0}px`;
    headText.style.top = `${Math.max(0, y0 - (mob ? 38 : short ? 21 : 38))}px`;   // a short stage reads the playhead on one line
    axis();
    render();
    draw(P);
  }

  function axis() {
    const { X, Y, x0, x1, y1, W, mob } = G, d = M.domain;
    gGrid.replaceChildren();
    gAxis.replaceChildren(sv("line", { class: "race-base", x1: x0, x2: x1, y1: y1 + 0.5, y2: y1 + 0.5 }));
    if (isNum(M.amount) && M.amount > d.y0 && M.amount < d.y1)
      gGrid.append(sv("line", { class: "race-amount", x1: x0, x2: x1, y1: Math.round(Y(M.amount)) + 0.5, y2: Math.round(Y(M.amount)) + 0.5 }));
    if (M.capacity && isNum(M.capacity.line)) {   // R35: what you can afford to lose, a flat line at the amount minus it
      const yc = Math.round(Y(M.capacity.line)) + 0.5;
      gGrid.append(sv("line", { class: "race-cap", x1: x0, x2: x1, y1: yc, y2: yc }));
    }
    const y0y = new Date(d.t0).getUTCFullYear(), y1y = new Date(d.t1).getUTCFullYear();
    const perYear = ((x1 - x0) * 31557600000) / (d.t1 - d.t0 || 1);
    const step = [1, 2, 5, 10, 20, 50].find((s) => perYear * s >= (mob ? 44 : 56)) || 50;
    for (let yr = Math.ceil((y0y + 1) / step) * step; yr <= y1y; yr += step) {
      const x = Math.round(X(Date.UTC(yr, 0, 1))) + 0.5;
      if (x < x0 + 8 || x > W - 8) continue;
      gAxis.append(sv("line", { class: "race-tick", x1: x, x2: x, y1: y1, y2: y1 + 5 }));
      const t = sv("text", { class: "race-year", x, y: y1 + (G.H < 340 ? 27 : 31), "text-anchor": "middle" });
      t.textContent = String(yr);
      gAxis.append(t);
    }
    /* a backdrop of the Result (a rate cycle): a quiet bracket along the time axis over its own dates, under the years, named
       beside it; never inside the plot and never beside a fall (correlation, never cause) */
    for (const bd of M.bands || []) {
      const a = Math.max(x0, X(bd.t0)), z = Math.min(x1, X(bd.t1)), yb = Math.round(G.yBand) + 0.5;
      if (o.compact || z - a < 2) continue;
      gAxis.append(sv("path", { class: "race-bracket", d: `M${r1(a)},${yb - 4}V${yb}H${r1(z)}V${yb - 4}` }));
    }
    gShock.replaceChildren();
    for (const s of M.shocks) {
      const x = Math.round(X(s.t)) + 0.5;
      const t = sv("line", { class: "race-shock" + (s.worst ? " is-worst" : ""), x1: x, x2: x, y1: y1 + 3, y2: y1 + 15, "data-id": s.id });   // 2 x 12 px, clear of the years
      gShock.append(t);
    }
  }

  /* ---- the marks: lines, the floor ribbon, the hatch past it, the rings at the troughs, the start and end dots ---- */
  function render() {
    const { X, Y } = G, xs = M.ts.map(X), ys = (row) => (row ? row.map((v) => (isNum(v) ? Y(v) : null)) : null);
    const yT = ys(M.today), yA = ys(M.after), yR = ys(M.ribbon), line = yA || yT;
    Object.assign(G, { xs, yT, yA, yR, line, src: M.after || M.today });
    fig.dataset.lines = M.after ? "two" : "one";
    fig.dataset.kind = M.kind;
    pToday.setAttribute("d", pathOf(xs, yT));
    const dA = yA ? pathOf(xs, yA) : "";
    pAfter.setAttribute("d", dA);
    pCase.setAttribute("d", dA);
    const floor = isNum(M.floor);
    pRibbon.setAttribute("d", floor ? pathOf(xs, yR) : "");
    pFlash.setAttribute("d", pRibbon.getAttribute("d"));
    const fb = [];                           // the floor's soft band: the ribbon's own points, closed along the plot's floor
    for (let k = 0; k < xs.length; k++) if (isNum(yR[k])) fb.push(`${r1(xs[k])},${r1(yR[k])}`);
    pFloorBand.setAttribute("d", floor && fb.length > 1 ? `M${fb[0].split(",")[0]},${G.y1}L${fb.join("L")}L${fb[fb.length - 1].split(",")[0]},${G.y1}Z` : "");
    gCapFill.replaceChildren(...(M.capacity ? M.capacity.under : []).map((poly) =>
      sv("path", { class: "race-capfill", d: "M" + poly.map(([t, v]) => r1(X(t)) + "," + r1(Y(v))).join("L") + "Z" })));
    gHatch.replaceChildren(...M.breaches.flatMap((b) => b.hatch.map((poly) =>
      sv("path", { d: "M" + poly.map(([t, v]) => r1(X(t)) + "," + r1(Y(v))).join("L") + "Z", fill: `url(#${hatchId})` }))));
    /* where the floor broke, the floor line itself turns red: a break of a few pixels still reads (the dial's 8 to 9 %) */
    pBreak.setAttribute("d", M.breaches.flatMap((b) => b.hatch.map((poly) => {
      const a = poly[0], z = poly[poly.length - 1];
      return `M${r1(X(a[0]))},${r1(Y(a[1]))}L${r1(Math.max(X(z[0]), X(a[0]) + 2))},${r1(Y(z[1]))}`;
    })).join(""));
    G.hatchBoxes = M.breaches.flatMap((b) => b.hatch.map((poly) => {
      const px = poly.map(([t]) => X(t)), py = poly.map(([, v]) => Y(v));
      return [Math.min(...px), Math.min(...py), Math.max(...px), Math.max(...py)];
    }));
    marks();
    if (!G.fresh) words();
    G.fresh = false;
    anchors();
    place();
  }
  const lastOf = (ys) => { for (let k = ys.length - 1; k >= 0; k--) if (isNum(ys[k])) return k; return -1; };
  function marks() {
    const { xs, line, yT, yA } = G;
    gMarks.replaceChildren();
    G.marks = [];
    const add = (node, x, kind, extra = {}) => { gMarks.append(node); G.marks.push({ node, x, kind, ...extra }); return node; };
    const first = line.findIndex(isNum);
    if (first >= 0) add(sv("circle", { class: "race-dot-start", cx: xs[first], cy: line[first], r: 3.5 }), xs[first], "start", { y: line[first] });
    const w = M.worst;
    M.breaches.forEach((b, j) => {
      if (w && j === w.breach) return;
      if (b.depthText && isNum(line[b.trough])) add(sv("circle", { class: "race-ring is-broke", cx: xs[b.trough], cy: line[b.trough], r: 4.5 }), xs[b.trough], "breach", { j, y: line[b.trough] });
    });
    if (w && isNum(line[w.k])) add(sv("circle", { class: "race-ring is-worst" + (w.cls ? ` is-${w.cls}` : ""), cx: xs[w.k], cy: line[w.k], r: G.mob ? 5 : 6 }), xs[w.k], "worst", { y: line[w.k] });
    const lt = lastOf(yT);
    if (lt >= 0) add(sv("circle", { class: "race-end-today", cx: xs[lt], cy: yT[lt], r: 3.5 }), xs[lt], "end-today", { y: yT[lt] });
    if (yA) { const la = lastOf(yA); if (la >= 0) add(sv("circle", { class: "race-end-after", cx: xs[la], cy: yA[la], r: 4.5 }), xs[la], "end-after", { y: yA[la] }); }
  }

  /* ---- the words: callouts at the falls (percent from its high first, then the same fall on the amount: R13), the two end
     values, the floor's own label, the starting amount. Placed where they cross no line, no hatch and no other label. ---- */
  function callout(b, main) {
    const box = h("div", "race-co" + (main ? " is-main" : "") + (b.past ? " is-past" : ""));
    if (b.label) {                           // the asked shock's name keeps the shocks' cyan: globe, tick and callout read as one thread
      const lab = h("p", "race-co-label");
      if (b.labelKind === "event") lab.append(h("span", "race-key is-shock"));
      lab.append(document.createTextNode(b.label));
      box.append(lab);
    }
    const line = h("p", "race-co-fig");
    line.append(h("span", "race-co-num", b.depthText), h("span", "race-co-from", " from its high"));
    box.append(line);
    if (b.moneyText) {                       // R35: the path's own dollars; the high-to-trough pair wraps as one unit
      const mline = h("p", "race-co-money");
      if (b.dollarsText && isNum(b.peakValue) && isNum(b.troughValue)) {
        mline.append(document.createTextNode(`${b.dollarsText} `), h("span", "race-co-path", `(${money(Math.round(b.peakValue))} \u2192 ${money(Math.round(b.troughValue))})`));
      } else mline.textContent = b.moneyText;
      box.append(mline);
    }
    if (main && b.word) {                    // the main fall names what it did to your floor; a second one is carried by its ring and hatch
      const st = h("p", `race-co-status is-${b.cls}`);
      if (b.cls !== "held") st.append(statusIcon(b.cls));
      st.append(document.createTextNode(b.word));
      box.append(st);
    }
    return box;
  }
  function endLabel(cls, name, value) {
    const box = h("div", "race-end " + cls), top = h("p", "race-end-name");
    top.append(h("span", "race-key " + cls), document.createTextNode(name));
    box.append(top);
    if (value) box.append(h("p", "race-end-val", value));
    return box;
  }
  function words() {                         // the label boxes and their texts (geometry comes later, in anchors())
    labels.replaceChildren();
    const items = [], w = M.worst, mob = (stage.clientWidth || 800) < 640;
    if (!o.compact) for (const bd of M.bands || []) items.push({ box: h("p", "race-bandlabel", bd.text), kind: "band", t0: bd.t0, t1: bd.t1, show: "always" });
    if (w && w.depthText) items.push({ box: callout(w, true), kind: "worst", k: w.k, show: "at" });
    M.breaches.forEach((b, j) => {
      if ((w && j === w.breach) || !b.depthText || mob || o.compact) return;   // phones: the main fall only
      items.push({ box: callout({ ...b, past: true }, false), kind: "breach", k: b.trough, show: "at" });
    });
    if (M.after && M.labels.after) {
      const box = endLabel("is-after", M.labels.after, M.ends.afterText);
      if (mob) box.classList.add("is-row");    // phones: one row in the band over the lines, clear of the move's own peak
      items.push({ box, kind: "end", line: "after", show: "end", top: mob });
    }
    const grow = !M.after && M.growth.today ? `${M.growth.today} a year` : null;
    if (!o.compact) items.push({ box: endLabel("is-today", M.labels.today, M.ends.todayText || grow), kind: "end", line: "today", show: "end" });
    if (isNum(M.floor) && !o.compact && !mob) {        // phones: the legend names the floor
      const box = h("div", "race-floor");
      box.append(h("p", "race-floor-name", M.labels.ribbon));
      if (M.labels.ribbonNote) box.append(h("p", "race-floor-note", M.labels.ribbonNote));
      items.push({ box, kind: "floor", show: "wipe" });
    }
    if (M.capacity && !o.compact) {
      const box = h("div", "race-cap-label"), top = h("p", "race-cap-name");
      top.append(h("span", "race-key is-cap"), document.createTextNode(M.capacity.label));
      box.append(top);
      if (M.capacity.note) box.append(h("p", "race-cap-note", M.capacity.note));
      items.push({ box, kind: "cap", show: "end" });
    }
    if (M.amountText && !o.compact && !mob) items.push({ box: h("p", "race-start", `${M.amountText} at the start`), kind: "start", show: "always" });
    for (const it of items) labels.append(it.box);
    G0.items = items;
    if (G) G.items = items;
  }
  function anchors() {                       // where each label points: its trough, its line's end, the start
    const { xs, line, yT, yA, mob } = G;
    for (const it of G.items) {
      let k = -1, ys = line;
      if (it.kind === "worst" || it.kind === "breach") { k = it.k; it.r = it.kind === "worst" ? (mob ? 5 : 6) : 4.5; }
      else if (it.kind === "end") { ys = it.line === "after" ? yA : yT; k = ys ? lastOf(ys) : -1; }
      else if (it.kind === "start") k = line.findIndex(isNum);
      else if (it.kind === "band") { it.ax = Math.max(G.x0, G.X(it.t0)); it.ay = G.y0; continue; }
      else if (it.kind === "cap") { it.ax = G.x1; it.ay = G.Y(M.capacity.line); continue; }
      else if (it.kind === "floor") { ys = G.yR; k = lastOf(ys); it.show = G.endW ? "end" : "wipe"; }
      it.ax = k >= 0 ? xs[k] : null;
      it.ay = k >= 0 && ys && isNum(ys[k]) ? ys[k] : null;
    }
    /* what words must not cross, and how much each costs: the move and the floor most, today's faint line least */
    G.lines = [[yA, 150], [G.yR, 120], [yT, yA ? 50 : 150]].filter(([ys]) => ys);
    G.capY = M.capacity && isNum(M.capacity.line) ? G.Y(M.capacity.line) : null;   // the dashed line: no word sits on it but its own
  }

  function crossings(rect, pad) {            // the cost of the lines that pass through the rectangle (exact for polylines)
    const xs = G.xs, L = rect[0] - pad, R = rect[2] + pad, T = rect[1] - pad, B = rect[3] + pad, k0 = Math.max(0, bsearch(xs, L) - 1);
    let n = 0;
    for (const [ys, cost] of G.lines) {
      let pk = -1;
      for (let k = k0; k < xs.length; k++) {
        if (!isNum(ys[k])) continue;
        if (pk >= 0) {
          const xa = xs[pk], xb = xs[k], ya = ys[pk], yb = ys[k];
          if (xa > R) break;
          const ca = Math.max(xa, L), cb = Math.min(xb, R);
          if (ca <= cb) {
            const at = (x) => (xb === xa ? ya : ya + ((x - xa) / (xb - xa)) * (yb - ya));
            if (Math.max(at(ca), at(cb)) >= T && Math.min(at(ca), at(cb)) <= B) { n += cost; break; }
          }
        }
        pk = k;
      }
    }
    return n;
  }
  const overlap = (a, b, m) => a[0] < b[2] + m && a[2] > b[0] - m && a[1] < b[3] + m && a[3] > b[1] - m;

  function candidatesOf(it, bw, bh) {
    const { ax, ay } = it, g = G.mob ? 12 : 16, out = [];
    if (it.kind === "worst" || it.kind === "breach") {
      for (const f of [1, 2.5, 4.5, 7]) {
        const d = g * f, e = 6 * f;
        out.push([ax + d, ay + e], [ax + d, ay - bh / 2], [ax - d - bw, ay + e], [ax - d - bw, ay - bh / 2], [ax - bw / 2, ay + d],
          [ax + d, ay - bh - e], [ax - d - bw, ay - bh - e], [ax - bw / 2, ay - bh - d]);
      }
      for (const d of [8, 24, 44, 64, 96, 120, 160, 200]) out.push([ax + d, G.y1 - bh - 10], [ax - d - bw, G.y1 - bh - 10]);   // the open ground under the lines
      for (const d of [8, 64, 140]) out.push([ax + d, G.y0 + 4], [ax - d - bw, G.y0 + 4]);                    // the open sky over them
      out.push([ax - bw / 2, G.y0 + 4], [G.x0, G.y0 + 4]);
      return out;
    }
    if (it.kind === "end") {
      if (G.endW) { for (const e of [0, 14, -14, 28, -28, 44, -44]) out.push([ax + 14, ay - bh / 2 + e]); return out; }   // the right margin
      if (it.top) out.push([Math.min(ax + 4, G.W - 4) - bw, 4], [Math.min(ax + 4, G.W - 4) - bw, 10]);
      for (const e of [6, 18, 32, 48]) out.push([ax - bw - 10, ay - bh - e], [ax - bw - 10, ay + e + 2]);
      return out.concat([[ax - bw - 14, ay - bh / 2]]);
    }
    if (it.kind === "band") {                // beside its bracket under the years: after its end, else before its start
      const z = Math.min(G.x1, G.X(it.t1)), yb = G.yBand - bh / 2 - 1;
      return G.mob ? [[ax, G.yBand + 4], [z + 8, yb]] : [[z + 8, yb], [ax - 8 - bw, yb], [ax, G.yBand + 2]];
    }
    if (it.kind === "cap") {                 // on its own line, right-aligned at the line's end; then along it; the margin last
      out.push([ax - bw - 4, ay - bh - 6], [ax - bw - 4, ay + 6]);
      for (const f of [0.75, 0.6, 0.45, 0.3]) { const x = G.x0 + f * (G.x1 - G.x0); out.push([x - bw / 2, ay - bh - 6], [x - bw / 2, ay + 6]); }
      if (G.endW) for (const e of [0, 16, -16, 32, -32, 52, -52]) out.push([ax + 14, ay - bh / 2 + e]);
      return out;
    }
    if (it.kind === "floor" && G.endW && isNum(ax) && isNum(ay)) {   // wide screens: in the right margin, where the floor ends
      for (const e of [0, 16, -16, 32, -32, 52, -52, 76]) out.push([ax + 14, ay - bh / 2 + e]);
      return out;
    }
    if (it.kind === "floor") {
      for (const f of [0.6, 0.5, 0.7, 0.4, 0.8, 0.3, 0.2, 0.9, 0.55, 0.65, 0.45, 0.75, 0.35, 0.85, 0.25, 0.15, 0.1]) {
        const x = G.x0 + f * (G.x1 - G.x0), k = nearest(G.xs, x), yr = G.yR[k];
        if (isNum(yr)) out.push([x - bw / 2, yr + 12], [x - bw / 2, yr - bh - 8], [x - bw / 2, yr + 28], [x - bw / 2, yr - bh - 22]);
      }
      return out.length ? out : [[G.x0, G.y1 - bh - 8]];
    }
    return [[ax + 10, ay - bh - 12], [ax + 10, ay + 12], [ax + 4, ay - bh - 28], [ax + 4, ay + 28]];   // the start
  }
  function place() {                         // writes, then one read of every size, then the positions (one layout pass)
    gLead.replaceChildren();
    const placed = [], { W, y1 } = G, todo = [];
    for (const it of G.items) {
      it.box.style.transform = "";
      it.box.style.clipPath = "";
      it.box.hidden = false;
      it.rect = null;
      it.lead = null;
      const margin = !!G.endW && (it.kind === "end" || it.kind === "floor");
      it.box.classList.toggle("is-margin", margin);
      it.box.style.maxWidth = it.kind === "floor" && margin ? `${Math.max(120, G.endW + 8)}px` : "";
      if (it.kind === "floor" || (isNum(it.ax) && isNum(it.ay))) todo.push(it);
      else it.box.hidden = true;
    }
    for (const it of todo) { it.bw = it.box.offsetWidth; it.bh = it.box.offsetHeight; }
    for (const it of todo) {
      const { bw, bh } = it;
      let best = null, bestS = Infinity;
      for (const [x, y] of candidatesOf(it, bw, bh)) {
        const rect = [x, y, x + bw, y + bh];
        const floorY = it.kind === "band" ? G.H : y1 - 4;   // the band's name lives under the axis; every other word above it
        let s = rect[0] < 2 || rect[2] > W - 2 || rect[1] < 2 || rect[3] > floorY ? 1000 : 0;
        if (G.endW && it.kind !== "end" && it.kind !== "floor" && rect[2] > G.x1 + 4) s += it.kind === "cap" && rect[0] > G.x1 ? 60 : 1000;   // the margin is the end labels'
        for (const q of placed) if (overlap(rect, q, 8)) s += 400;
        for (const q of G.hatchBoxes) if (overlap(rect, q, 3)) s += 300;
        if (it.kind !== "start" && it.kind !== "end") for (const m of G.marks) if (m.y !== undefined && overlap(rect, [m.x - 6, m.y - 6, m.x + 6, m.y + 6], 2)) s += 80;
        if (it.kind !== "band") s += crossings(rect, 5);
        if (G.capY !== null && it.kind !== "cap" && it.kind !== "band" && rect[1] - 4 < G.capY && rect[3] + 4 > G.capY && rect[0] < G.x1) s += 100;
        if (s < bestS) { best = rect; bestS = s; if (s === 0) break; }
      }
      if (!best || (bestS >= 100 && (it.kind === "floor" || it.kind === "start" || it.kind === "band" || it.kind === "cap"))) { it.box.hidden = true; continue; }   // optional words hide
      it.rect = best;
      placed.push(best);
      it.box.style.transform = `translate(${Math.round(best[0])}px, ${Math.round(best[1])}px)`;
      leader(it);
      if (it.lead) {
        const L = ["x1", "y1", "x2", "y2"].map((k) => Number(it.lead.getAttribute(k)));
        placed.push([Math.min(L[0], L[2]) - 1, Math.min(L[1], L[3]) - 1, Math.max(L[0], L[2]) + 1, Math.max(L[1], L[3]) + 1]);
      }
    }
  }
  function leader(it) {                      // a hairline from the ring to its words when they sit apart
    it.lead = null;
    if (it.kind !== "worst" && it.kind !== "breach") return;
    const [l, t, r, b] = it.rect, px = clamp(it.ax, l, r), py = clamp(it.ay, t, b), dx = px - it.ax, dy = py - it.ay, dist = Math.hypot(dx, dy);
    if (dist < it.r + 8) return;
    const ux = dx / dist, uy = dy / dist;
    it.lead = gLead.appendChild(sv("line", { class: "race-lead" + (it.kind === "worst" ? " is-worst" : ""),
      x1: r1(it.ax + ux * (it.r + 3)), y1: r1(it.ay + uy * (it.r + 3)), x2: r1(px - ux * 2), y2: r1(py - uy * 2) }));
  }

  /* ---- draw(p): the reveal, left to right, exactly reversible (a pure function of p): the plot and the leaders are clipped at
     the playhead, each callout wipes in as the playhead crosses it, the rings light when it reaches them, the end labels land
     at p = 1. The playhead reads the date and, from tipping_point.paths, the move's own dollars that week. ---- */
  function draw(p) {
    P = clamp(isNum(p) ? p : 1, 0, 1);
    if (!G) return;
    const end = P >= 1, hx = end ? G.W : G.x0 + P * (G.x1 - G.x0), moving = P > 0 && !end;
    clipRect.setAttribute("width", P <= 0 ? 0 : r1(Math.max(0, hx)));
    fig.classList.toggle("is-racing", moving);
    head.classList.toggle("is-on", moving);
    if (moving) readout(hx);
    for (const m of G.marks) m.node.classList.toggle("is-on", end || m.kind === "start" || hx >= m.x - 3);
    for (const it of G.items) {
      const r = it.rect;
      if (!r) continue;
      if (it.show === "at") {                // a callout lands when the playhead reaches its trough
        const on = end || hx >= it.ax - 3;
        it.box.classList.toggle("is-on", on);
        if (it.lead) it.lead.classList.toggle("is-on", on);
        continue;
      }
      if (it.show !== "wipe") { it.box.classList.toggle("is-on", it.show === "always" || end); continue; }
      const wdt = r[2] - r[0], cut = end ? 0 : clamp(r[2] - hx, 0, wdt);
      it.box.classList.toggle("is-on", cut < wdt);
      it.box.style.clipPath = cut > 0 && cut < wdt ? `inset(0 ${r1(cut)}px 0 0)` : "";
    }
  }
  function valueAt(row, k) { for (let j = k; j >= 0; j--) if (isNum(row[j])) return row[j]; return null; }
  function readout(hx) {
    const d = M.domain, t = d.t0 + ((hx - G.x0) / (G.x1 - G.x0)) * (d.t1 - d.t0), k = bsearch(M.ts, t);
    head.style.transform = `translateX(${r1(hx)}px)`;
    headDate.textContent = dateText(M.dates[k]);
    const v = M.kind === "paths" && M.after && !M.whatIf ? valueAt(M.after, k) : null;   // R20: dollars only at the size asked
    headVal.textContent = v === null ? "" : money(v);
    const past = M.breaches.some((b) => b.stretches.some(([a, z]) => k >= a && k <= z));
    head.classList.toggle("is-past", past);
    head.classList.toggle("is-flip", hx > G.x1 - (G.mob ? 120 : 160));
  }

  /* ---- hover and keyboard: one crosshair that snaps to the nearest drawn week, every line's value in one readout (the
     Result's weekly dollars; a line priced only by the browser shows its fall from the high instead), no easing ---- */
  function row(cls, value, name) {
    const p = h("p", "race-tip-row");
    p.append(h("span", "race-key " + cls), h("span", "race-tip-val", value), h("span", "race-tip-name", name));
    return p;
  }
  function fallAt(src, k) { let hi = -Infinity; for (let j = 0; j <= k; j++) if (isNum(src[j])) hi = Math.max(hi, src[j]); return isNum(src[k]) ? src[k] / hi - 1 : null; }
  function hover(k) {
    cursor = k;
    if (k < 0 || !G) {
      gCur.classList.remove("is-on");
      tip.hidden = true;
      for (const it of (G && G.items) || []) it.box.classList.remove("is-under");
      if (M && pinned === null && !scrub.dataset.parked) scrub.value = String(M.dates.length - 1);
      lastWeek = -1;
      return;
    }
    const x = G.xs[k], priced = M.kind === "paths";   // the curve's weekly dollars are Result keys; a series is priced by nobody here
    curLine.setAttribute("x1", r1(x)); curLine.setAttribute("x2", r1(x));
    curLine.setAttribute("y1", G.y0); curLine.setAttribute("y2", G.y1);
    for (const [c, ys] of [[curA, G.yA], [curT, G.yT]]) {
      const ok = ys && isNum(ys[k]);
      c.classList.toggle("is-off", !ok);
      if (ok) { c.setAttribute("cx", r1(x)); c.setAttribute("cy", r1(ys[k])); }
    }
    gCur.classList.add("is-on");
    const kids = [h("p", "race-tip-date", dateText(M.dates[k]))];
    const say = (cls, src, name, own) => {
      if (!src || !isNum(src[k])) return;
      if (own) kids.push(row(cls, money(src[k]), name));
      else { const f = fallAt(src, k); if (f !== null) kids.push(row(cls, pct(f), `${name}, from its high`)); }
    };
    if (M.after) say("is-after", M.after, M.whatIf ? M.labels.after : "With the move", priced && !M.whatIf);
    say("is-today", M.today, M.labels.today, priced && M.todayPriced !== false);
    if (priced && !M.whatIf && M.after && M.todayPriced !== false && isNum(M.after[k]) && isNum(M.today[k])) {   // the gap, from the two drawn values
      const g = M.after[k] - M.today[k];
      kids.push(row("is-gap", `${g >= 0 ? "+" : ""}${money(g)}`, "gap"));
    }
    const day = 3.5 * 86400000;
    for (const s of M.shocks) if (Math.abs(s.t - M.ts[k]) <= day && s.title) kids.push(row("is-shock", "", s.title));
    if (M.breaches.some((b) => b.stretches.some(([a, z]) => k >= a && k <= z))) {
      const p = h("p", "race-tip-past");
      p.append(statusIcon("broke"), document.createTextNode(FLOOR_WORDS.broke));
      kids.push(p);
    }
    tip.replaceChildren(...kids);
    tip.hidden = false;
    tip.classList.remove("is-tick");
    if (String(scrub.value) !== String(k)) scrub.value = String(k);
    if (k !== lastWeek) {                    // the stage may follow the week (bubbling, no payload but the Result's own date)
      lastWeek = k;
      fig.dispatchEvent(new CustomEvent("race:week", { bubbles: true, detail: { index: k, date: M.dates[k] } }));
    }
    /* the readout wins (TradingView's way): it sits beside the crosshair where it covers the least, and what it covers recedes */
    const shape = kids.map((n) => n.textContent.length).join(",");
    if (shape !== tipShape || !tipW) { tipShape = shape; tipW = tip.offsetWidth; tipH = tip.offsetHeight; }   // one read per shape (motion QA)
    const tw = tipW, th = tipH, COST = { worst: 400, end: 250, breach: 200 };
    const words = (G.items || []).filter((it) => it.rect && !it.box.hidden).map((it) => [it, COST[it.kind] || 60]);
    let best = null, bestS = Infinity;
    for (let f = 0; f <= 1.0001; f += 0.25) for (const left of [x + 14, x - 14 - tw]) {
      const top = G.y0 + f * Math.max(0, G.y1 - G.y0 - th - 6), r = [left, top, left + tw, top + th];
      let sc = left < 2 || left + tw > G.W - 2 ? 5000 : 0;
      for (const [it, cost] of words) if (overlap(r, it.rect, 4)) sc += cost;
      if (sc < bestS) { bestS = sc; best = r; }
    }
    /* never past the plot's own box (a readout over the edge would widen a phone's page): clamped, whatever it covers */
    const lx = clamp(best[0], 2, Math.max(2, G.W - tw - 2)), ty = clamp(best[1], 0, Math.max(0, G.H - th));
    best = [lx, ty, lx + tw, ty + th];
    tip.style.transform = `translate(${Math.round(lx)}px, ${Math.round(ty)}px)`;
    for (const [it] of words) it.box.classList.toggle("is-under", overlap(best, it.rect, 4));
    const said = kids.map((n) => [...n.childNodes].map((c) => c.textContent).filter(Boolean).join(" ")).join(", ") + ".";
    clearTimeout(liveT);
    liveT = setTimeout(() => { live.textContent = said; }, 250);
  }
  const indexAtX = (clientX) => {
    const b = svg.getBoundingClientRect(), d = M.domain, t = d.t0 + ((clientX - b.left - G.x0) / (G.x1 - G.x0)) * (d.t1 - d.t0);
    let k = nearest(M.ts, t);
    while (k > 0 && !isNum((M.after || M.today)[k])) k--;        // never park on a day the drawn line skips
    return k;
  };
  /* a shock tick named on hover: near the time axis the pointer reads the tick, not the week */
  function tickAt(clientX, clientY) {
    const b = svg.getBoundingClientRect(), x = clientX - b.left, y = clientY - b.top;
    if (y < G.y1 - 4 || y > G.y1 + 22) return null;
    let best = null, bd = 9;
    for (const sh of M.shocks) { const d = Math.abs(G.X(sh.t) - x); if (d < bd) { bd = d; best = sh; } }
    return best;
  }
  function showTick(sh) {
    gCur.classList.remove("is-on");
    for (const t of gShock.children) t.classList.toggle("is-hot", t.getAttribute("data-id") === sh.id);
    const p = h("p", "race-tip-row");
    p.append(h("span", "race-key is-shock"), h("span", "race-tip-name", sh.title || ""));
    tip.replaceChildren(h("p", "race-tip-date", dateText(sh.date)), p);
    tip.hidden = false;
    tip.classList.add("is-tick");
    const x = G.X(sh.t), tw = tip.offsetWidth, th = tip.offsetHeight, edge = G.endW ? G.x1 : G.W - 4;
    tip.style.transform = `translate(${Math.round(clamp(x - tw / 2, 2, Math.max(2, Math.min(edge, G.W - 2) - tw)))}px, ${Math.round(Math.max(0, G.y1 - th - 10))}px)`;
    live.textContent = `${dateText(sh.date)}, ${sh.title || ""}.`;
  }
  const unhot = () => { for (const t of gShock.children) t.classList.remove("is-hot"); };
  const onMove = (ev) => {
    if (!G || !M) return;
    if (pinned !== null) { clearTimeout(pinT); pinned = null; }
    delete scrub.dataset.parked;
    const sh = tickAt(ev.clientX, ev.clientY);
    if (sh) { showTick(sh); return; }
    unhot();
    hover(indexAtX(ev.clientX));
  };
  const onLeave = () => { unhot(); if (document.activeElement !== stage) hover(pinned === null ? -1 : pinned); };
  const onKey = (ev) => {
    if (!G || !M) return;
    const n = M.dates.length, step = { ArrowRight: 1, ArrowLeft: -1, PageUp: 13, PageDown: -13 }[ev.key];
    let k = cursor < 0 ? (M.worst ? M.worst.k : n - 1) : cursor;
    if (ev.key === "Home") k = 0; else if (ev.key === "End") k = n - 1; else if (step !== undefined) k = clamp(k + step, 0, n - 1);
    else if (ev.key === "Escape") { hover(-1); return; } else return;
    ev.preventDefault();
    const src = M.after || M.today, dir = step !== undefined && step < 0 ? -1 : 1;
    while (k > 0 && k < n - 1 && !isNum(src[k])) k += dir;
    hover(k);
  };
  const onFocus = () => { if (G && M && cursor < 0) hover(M.worst ? M.worst.k : M.dates.length - 1); };
  const onCross = () => {                    // the dial crossed the size where the floor first broke: one 200 ms brightening
    pFlash.classList.remove("is-flash");
    pFlash.getBoundingClientRect();
    pFlash.classList.add("is-flash");
  };
  document.addEventListener("dial:cross", onCross);
  const onBlur = () => hover(pinned === null ? -1 : pinned);
  /* the replay controls: the scrub is the crosshair's week (keys step one week, no easing); play walks the weeks, a
     user's own motion (reduced motion: straight to the last week, no walk) */
  let pinned = null, playing = 0, walk = 0;
  const drawn = (k) => { const src = M.after || M.today; while (k > 0 && !isNum(src[k])) k--; return k; };
  function setPlaying(on) {
    playing = on ? 1 : 0;
    playBtn.replaceChildren(playIcon(!!on));
    playBtn.setAttribute("aria-label", on ? "Pause" : "Play through the weeks");
    playBtn.classList.toggle("is-on", !!on);
    if (!on && walk) { cancelAnimationFrame(walk); walk = 0; }
  }
  function startPlay() {
    if (!G || !M) return;
    const n = M.dates.length;
    if (reduced()) { hover(drawn(n - 1)); return; }
    const k0 = cursor >= 0 && cursor < n - 1 ? cursor : 0, t0 = performance.now();
    setPlaying(true);
    const step = (now) => {
      if (!playing || !alive) return;
      const k = Math.min(n - 1, k0 + Math.floor(((now - t0) / 1000) * 40));   // 40 weeks a second: five years in about six
      hover(drawn(k));
      if (k >= n - 1) { setPlaying(false); return; }
      walk = requestAnimationFrame(step);
    };
    walk = requestAnimationFrame(step);
  }
  const onPlay = () => (playing ? setPlaying(false) : startPlay());
  const onScrub = () => { if (playing) setPlaying(false); if (pinned !== null) { clearTimeout(pinT); pinned = null; } if (G && M) hover(drawn(Number(scrub.value) || 0)); };
  const onScrubDown = () => { if (playing) setPlaying(false); };
  playBtn.addEventListener("click", onPlay);
  scrub.addEventListener("input", onScrub);
  scrub.addEventListener("pointerdown", onScrubDown);
  stage.addEventListener("pointermove", onMove);
  stage.addEventListener("pointerdown", onMove);   // a tap reads the week too (touch)
  stage.addEventListener("pointerleave", onLeave);
  stage.addEventListener("keydown", onKey);
  stage.addEventListener("focus", onFocus);
  stage.addEventListener("blur", onBlur);

  /* ---- the legend (the dependable identity channel; direct labels ride the marks), the footnote, the text alternative ---- */
  function chrome() {
    legend.replaceChildren();
    legend.hidden = !o.legend;
    const add = (cls, text) => { const li = h("li", "race-leg"); li.append(h("span", "race-key " + cls), document.createTextNode(text)); legend.append(li); };
    if (M.after) add("is-after", "With the move");
    add("is-today", M.labels.today);
    if (isNum(M.floor)) { add("is-floor", M.labels.rule || M.labels.ribbon); if (M.breaches.length || M.at) add("is-below", "Below it"); }
    if (M.capacity) add("is-cap", "What you can afford to lose");
    if (M.shocks.length && M.labels.shocks) add("is-shock", M.labels.shocks);
    notes();
  }
  function notes() {                         // the foot and the text alternative follow the size (R20's caption at another size)
    const lines = ["This already happened; it is not a forecast."];
    if (M.kind !== "window") lines.push("Drawn weekly; each fall is measured on daily prices.");
    if (M.after) lines.push(M.whatIf && M.labels.whatIf ? M.labels.whatIf : "Fictional illustration, not a recommendation.");
    foot.textContent = typeof o.note === "string" ? o.note : lines.join(" ");
    foot.hidden = !o.foot;
    summary();
  }
  function summary() {
    const s = [], L = M.labels, span = L.start && L.end ? ` from ${L.start} to ${L.end}` : "";
    if (M.amountText) s.push(`The growth of ${M.amountText}${span}.`);
    if (M.whatIf && L.whatIf) s.push(`${L.after}. ${L.whatIf}`);
    else if (M.after && L.after && M.ends.afterText) s.push(`${L.after}, it ended at ${M.ends.afterText}.`);
    if (M.ends.todayText) s.push(`${L.today} ended at ${M.ends.todayText}.`);
    const fall = (b) => `${b.depthText} from its high, ${dateText(b.peakDate)} to ${dateText(b.troughDate)}${b.label ? ` (${b.label})` : ""}`
      + (b.dollarsText && isNum(b.peakValue) && isNum(b.troughValue)   // R35: the path's own dollars
        ? `, from ${money(Math.round(b.peakValue))} to ${money(Math.round(b.troughValue))} (${b.dollarsText})` : "");
    const shown = M.breaches.filter((b) => b.depthText);
    if (shown.length) s.push(`It fell past the floor: ${shown.map(fall).join("; ")}.`);
    if (M.worst && (M.worst.breach < 0 || !M.breaches[M.worst.breach].depthText)) s.push(`Its worst fall: ${fall(M.worst)}${M.worst.word ? `; ${M.worst.word.toLowerCase()}` : ""}.`);
    for (const bd of M.bands || []) s.push(`Shaded on the time axis: ${bd.text}.`);
    if (isNum(M.floor) && L.ribbon) s.push(`${L.ribbon}.`);
    if (M.capacity) s.push(`${M.capacity.label}: the dashed line at ${money(M.capacity.line)}${M.capacity.note ? `; ${M.capacity.note}` : ""}.`);
    if (M.shocks.length && L.shocks) s.push(`${L.shocks} on record are marked on the time axis.`);
    s.push("This already happened; it is not a forecast.");
    sr.textContent = s.join(" ");
    stage.setAttribute("aria-label", "The race chart. Use the arrow keys to read each week.");
  }

  /* ---- the API ---- */
  function setWeight(i) {
    if (!M || typeof M.at !== "function" || !Number.isInteger(i)) return;
    const next = M.at(i);
    if (!next || next.weightIndex === M.weightIndex) return;
    M = next;
    if (!G) return;
    render();
    draw(P);
    if (cursor >= 0) hover(drawn(Math.min(cursor, M.dates.length - 1)));
    notes();
  }
  /* coordinates in CSS px: "viewport" (default, like globe.project), "el" relative to the element the chart was created in,
     "svg" inside the chart's own plot */
  function origin(space) {
    if (space === "svg") return { left: 0, top: 0 };
    const sb = svg.getBoundingClientRect();
    if (space === "viewport") return { left: sb.left, top: sb.top };
    const eb = el.getBoundingClientRect();
    return { left: sb.left - eb.left, top: sb.top - eb.top };
  }
  function xOfDate(iso, space = "viewport") {
    const t = timeOf(typeof iso === "string" ? iso.slice(0, 10) : "");
    return !G || !isNum(t) ? NaN : G.X(t) + origin(space).left;
  }
  function yOfValue(v, space = "viewport") { return !G || !isNum(v) || (G.log && v <= 0) ? NaN : G.Y(v) + origin(space).top; }
  function markers(space = "viewport") {           // where things are, for the stage's cyan leader (the shock ticks sit on the time axis)
    if (!G) return [];
    const b = origin(space), out = [];
    for (const s of M.shocks) out.push({ kind: "shock", id: s.id, date: s.date, title: s.title, worst: s.worst, x: G.X(s.t) + b.left, y: G.y1 + b.top });
    for (const m of G.marks) if (m.y !== undefined) out.push({ kind: m.kind, x: m.x + b.left, y: m.y + b.top, ...(m.kind === "worst" && M.worst ? { date: M.worst.troughDate } : {}) });
    return out;
  }
  /* the stage's landing: the crosshair opens on the week of `iso`, then closes after `hold` ms (or at unpin(), when the lamp
     lights) so the end frame keeps every callout readable; the scrub stays parked on that week. Reduced motion: no readout. */
  function pin(iso, hold = 900) {
    if (!G || !M) return false;
    const t = timeOf(typeof iso === "string" ? iso.slice(0, 10) : "");
    if (!isNum(t)) return false;
    const k = drawn(bsearch(M.ts, t));
    clearTimeout(pinT);
    if (reduced()) { scrub.value = String(k); scrub.dataset.parked = "1"; return true; }
    pinned = k;
    hover(k);
    pinT = setTimeout(() => { if (pinned === k) unpin(k); }, Math.max(0, hold));
    return true;
  }
  function unpin(keep) {
    clearTimeout(pinT);
    const k = Number.isInteger(keep) ? keep : pinned;
    pinned = null;
    if (document.activeElement !== stage) hover(-1);
    if (Number.isInteger(k) && k >= 0) { scrub.value = String(k); scrub.dataset.parked = "1"; }   // the scrub stays parked on the landing's week
  }
  function destroy() {
    alive = false;
    if (ro) ro.disconnect();
    if (frame) cancelAnimationFrame(frame);
    stage.removeEventListener("pointermove", onMove);
    stage.removeEventListener("pointerdown", onMove);
    stage.removeEventListener("pointerleave", onLeave);
    stage.removeEventListener("keydown", onKey);
    stage.removeEventListener("focus", onFocus);
    stage.removeEventListener("blur", onBlur);
    setPlaying(false);
    clearTimeout(pinT);
    clearTimeout(liveT);
    playBtn.removeEventListener("click", onPlay);
    scrub.removeEventListener("input", onScrub);
    scrub.removeEventListener("pointerdown", onScrubDown);
    document.removeEventListener("dial:cross", onCross);
    fig.remove();
  }

  if (!M) {
    fig.classList.add("is-empty");
    stage.append(h("p", "race-empty", "The race is drawn here once a replay has run."));
    return { draw() {}, setWeight() {}, xOfDate: () => NaN, yOfValue: () => NaN, markers: () => [], pin: () => false, unpin() {}, destroy, get model() { return null; }, get p() { return 1; } };
  }
  chrome();
  layout();
  const sizes = () => [Math.round(stage.clientWidth), Math.round(el.clientHeight)];
  let last = sizes();
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => {
      if (frame || !alive) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const now = sizes();
        if (!alive || (now[0] === last[0] && now[1] === last[1])) return;
        layout();
        last = sizes();
        if (cursor >= 0) hover(cursor);
      });
    });
    ro.observe(el);
    ro.observe(stage);
  }
  return { draw, setWeight, xOfDate, yOfValue, markers, pin, unpin, destroy, get model() { return M; }, get p() { return P; } };
}
