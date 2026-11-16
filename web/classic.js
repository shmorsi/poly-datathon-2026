/* EPICENTRE, the classic page (web/classic.html; frozen copy of the page before the Replay, kept until the integrated page
   passes review; nothing links to it). Originally: the page (plan W, W-S1: the spike ported onto the Result). Every number on screen comes from the Result through
   PF.view (web/lib.js, node-tested); text is set with textContent only; the browser never judges (one judge: the server).
   Motion thesis (spec §22 rule 1):
   (a) focal sequences: the hero, the shocks ignite once in date order on the turning Earth while the ruler's playhead crosses
       their dates, then stillness; the cockpit, the verdict landing after a run (bezel, lamp, word, sentence, the fall drawn
       left to right, the rows), timeline in the task report;
   (b) continuity: the poster to globe crossfade, the investor card crossfade on a tab click, the bar's ground on scroll;
   (c) feedback: every pressable scales to 0.97 on press, hover colour only under a fine pointer, the Run spinner;
   (d) expensive: the WebGL globe (this file's one rAF loop) sleeps off-screen, on a hidden tab, on "Pause motion" and under
       reduced motion. Keyboard actions never animate. Static on purpose: headings, the card's values, chart axes, the footer. */
const PF = window.PF;
const $ = (s, r = document) => r.querySelector(s);
const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs = {}, ...kids) {           // elements from data: textContent and attributes, never HTML strings
  const el = attrs.svg ? document.createElementNS(SVGNS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "svg" || v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else if (k === "class") el.setAttribute("class", v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
}
const s = (tag, attrs = {}, ...kids) => h(tag, { ...attrs, svg: true }, ...kids);
const icon = (id, cls = "icon") => s("svg", { class: cls, "aria-hidden": "true" }, s("use", { href: "#" + id }));
const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const ms = (name) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--" + name)) || 0;   // motion tokens, one source
const meta = (n) => { const m = document.querySelector(`meta[name="epicentre-${n}"]`); return m ? m.content : null; };
const params = new URLSearchParams(location.search);
const FAKE = params.has("fake");
const STATIC = !FAKE && meta("mode") === "static";
window.__errors = [];
/* S.r = the Result on screen; S.last, per investor: the last Result that rendered fully (a failed run puts back the same
   investor's, never another's: PF.lastGood); S.pid = the investor tab */
const S = { r: null, last: {}, v: null, pid: "robert", running: false, investors: null, index: null, runs: {}, fake: null, custom: null, base: null };

/* segments [[text, "num" | "verdict"]] from PF.view into a block: numbers in B612 (.num), the verdict words in their tone */
function fill(el, segs, tone) {
  el.replaceChildren(...(segs || []).map(([t, k]) => (k === "num" ? h("span", { class: "num", text: t }) : k === "verdict" ? h("b", { class: "verdict", text: t }) : t)));
  if (tone !== undefined) el.dataset.tone = tone || "";
  return el;
}
const said = (el, text) => { el.textContent = text || ""; el.hidden = !text; };

/* ---- loading ---- */
async function getJSON(url) { const r = await fetch(url, { cache: "no-store" }); if (!r.ok) throw Object.assign(new Error(url), { status: r.status }); return r.json(); }
async function problemOf(res) {    // what the server said, in one plain sentence
  let body = null;
  try { body = await res.json(); } catch (e) { body = null; }
  if (body && typeof body.message === "string" && body.message) return body.message;
  return "The server answered with an error (" + res.status + "). Try again in a moment.";
}

/* POST /api/run and read the NDJSON stream: progress lines, then one result line (D Task 5's bridge, kept as it was).
   Throws an Error with .plain = true for a non-200 (the server's JSON sentence, or ours), and one with .dropped = true when
   the stream ends or breaks before the result line arrived. Only those two carry text the page may show; any other
   exception (a render bug in onLine, say) gets PF.UNSHOWN, never its own message (lib.js, PF.failureLine). */
const DROPPED = "The connection dropped before the answer arrived. Run the check again.";
const plain = (message) => Object.assign(new Error(message), { plain: true });
async function realStream(body, onLine) {
  const dropped = () => Object.assign(new Error(DROPPED), { dropped: true });
  let res;
  try { res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  catch (e) { throw plain("The server could not be reached. Check the connection, then try again."); }
  if (!res.ok) throw plain(await problemOf(res));
  if (!res.body) throw dropped();
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = "", gotResult = false;
  const feed = (text) => {
    let ev; try { ev = JSON.parse(text); } catch (e) { throw dropped(); }
    if (ev && ev.type === "result") gotResult = true;
    onLine(ev);
  };
  for (;;) {
    let chunk; try { chunk = await reader.read(); } catch (e) { throw dropped(); }
    if (chunk.done) break;
    buf += dec.decode(chunk.value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) { const ln = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1); if (ln) feed(ln); }
  }
  if (buf.trim()) feed(buf.trim());
  if (!gotResult) throw dropped();
}

/* a saved or FAKE Result replayed as the stream it came from: one line per step of its own trace (step, ms, service).
   A replay never ticks a call that did not happen: the steps are the trace's, the detail says "saved run". */
const STEP_ORDER = ["OBSERVE", "UNDERSTAND", "COMPARE", "EXPLAIN", "VERIFY"];
const STEP_LABEL = { OBSERVE: "Read your plan and screen the question", UNDERSTAND: "The navigator reads your words and picks the shocks",
  COMPARE: "Replay your mix on real history", EXPLAIN: "Write the explanation from the computed facts", VERIFY: "Trace every number to data" };
function replayLines(r, detail) {
  const rows = Array.isArray(r && r.trace) ? r.trace : [];
  return STEP_ORDER.filter((st) => rows.some((t) => t && t.step === st)).map((st) => {
    const mine = rows.filter((t) => t && t.step === st);
    const total = mine.reduce((a, t) => a + (Number.isFinite(t.ms) ? t.ms : 0), 0);
    const svc = mine.find((t) => t.service && t.service !== "Python");
    return { type: "progress", step: st, label: STEP_LABEL[st], status: "done", ms: Math.round(total), service: svc ? svc.service : "Python", detail };
  });
}
function playLines(lines, onLine, done) {          // the replay's pace: each step for about its share of 1.6 s, instant under reduce
  const timers = [], step = reduce.matches ? 0 : Math.max(180, Math.min(420, 1600 / Math.max(1, lines.length)));
  lines.forEach((ln, i) => {
    timers.push(setTimeout(() => onLine({ ...ln, status: "run" }), i * step));
    timers.push(setTimeout(() => onLine(ln), i * step + step * 0.8));
  });
  timers.push(setTimeout(done, lines.length * step + (reduce.matches ? 0 : ms("dur-panel"))));
  return () => timers.forEach(clearTimeout);
}

/* ---- the investors and their runs, in the page's three modes ---- */
const COPY = {   // words only, from the official personas (the official case); every number on the card comes from the Result or /api/pilots
  robert: "Healthcare professional, close to retirement. Prefers established companies he understands.",
  mateo: "Operations manager with a young family. Wants balance, and no companies in serious controversies.",
  amira: "Software engineer, drawn to AI and crypto, but not only tech.",
  canadian: "The workshop’s own question: a mix that looks very Canadian.",
};
async function loadInvestors() {
  if (FAKE) { S.fake = await getJSON("fake_result.json"); return; }
  if (STATIC) { try { S.index = await getJSON("runs/index.json"); } catch (e) { S.index = []; } return; }
  try { const p = await getJSON("/api/pilots"); S.investors = p && p.pilots; } catch (e) { S.investors = null; }
}
const COMMIT = new WeakMap();                       // the static demo's commit per saved run (runs/index.json)
async function resultFor(pid) {                    // the saved (or FAKE) run of one investor, or null: never a stand-in
  if (pid in S.runs) return S.runs[pid];
  let r = null;
  if (FAKE) {
    const f = S.fake || {};
    r = pid === "robert" ? Object.fromEntries(Object.entries(f).filter(([k]) => k !== "_investors")) : (f._investors || {})[pid] || null;
  } else if (STATIC) {
    const run = PF.staticRun(S.index, pid);
    if (run) { try { r = await getJSON(run.file); if (r && typeof r === "object") COMMIT.set(r, run.commit); } catch (e) { r = null; } }
  } else {
    try { const res = await fetch("/api/demo-run?pilot=" + encodeURIComponent(pid), { cache: "no-store" }); r = res.ok ? await res.json() : null; }
    catch (e) { r = null; }
  }
  S.runs[pid] = r && typeof r === "object" && r.status !== "error" ? r : null;
  return S.runs[pid];
}

/* One place that makes any Result safe to draw: PF.withPaths gives a no-change Result its second path (D Task 5), and the view
   is PF.view's. Idempotent; a missing key hides its line, never prints "undefined". */
function bridge(r) {
  if (!r || typeof r !== "object") return r;
  PF.withPaths(r);
  return r;
}
const viewOf = (r) => PF.view(r, { commit: COMMIT.get(r) || (STATIC ? meta("commit") : null) });

/* ---- screen 1, the hero ---- */
const hero = $("#hero"), canvas = $("#globe"), slot = $("#globe-slot");
const G = { globe: null, events: [], lon: -18, last: 0, frame: 0, visible: true, paused: false, startAt: 0, next: 0, t0: 0, t1: 1,
  px: 0, py: 0, sx: 0, sy: 0, scrollP: 0, done: false };
const LON0 = -18, TILT = 26, IGNITE_MS = 4200;      // the poster's turn and tilt; the ignition crosses the five years in 4.2 s
function renderHero(v) {
  const hc = PF.heroCopy(v);
  const line = $("#hero-line");
  line.replaceChildren();
  if (hc.segs) { line.append(icon(v.verdict.icon)); line.append(fill(h("span"), hc.segs)); line.dataset.tone = v.verdict.tone; }
  $("#replay-label").textContent = hc.button;
  const ro = $("#readout");
  ro.hidden = !hc.readout;
  if (hc.readout) {
    const [n, rest] = hc.readout[0].split(/ (.*)/);
    $("#readout-n").replaceChildren(h("span", { class: "num", text: n }), " " + rest);
    $("#readout-span").textContent = hc.readout[1];
    const ruler = $("#ruler"), head = $("#playhead");
    ruler.replaceChildren(head);
    G.t0 = Date.parse(v.shocks.first); G.t1 = Date.parse(v.shocks.last);
    for (const e of v.shocks.events) { const i = h("i"); i.style.left = `${pos(Date.parse(e.date)) * 100}%`; ruler.append(i); }
    $("#hero-summary").textContent = `${hc.readout[0]}, ${hc.readout[1]}, each drawn at its epicentre on the night Earth; a line’s length is how far ${v.move ? "the move" : "the mix"} fell after it.`;
  }
  drawRings(v);
}
const pos = (t) => (G.t1 > G.t0 ? Math.min(1, Math.max(0, (t - G.t0) / (G.t1 - G.t0))) : 1);
function drawRings(v) {   // the no-WebGL poster's shocks, where web/globe.js draws them (PF.globeProject), sized by the same trough
  const svg = $("#rings");
  svg.replaceChildren();
  for (const e of v.shocks ? v.shocks.events : []) {
    const p = PF.globeProject(e.lat, e.lon, { tilt: TILT, lon0: LON0 });
    if (!p.visible) continue;
    if (typeof e.trough === "number" && e.trough < 0) {          // a fall only: a rise never reads as one (Minor 8)
      const len = Math.min(0.3, 0.02 + 2 * Math.abs(e.trough)), q = PF.globeProject(e.lat, e.lon, { tilt: TILT, lon0: LON0, r: 1 + len });
      svg.append(s("line", { x1: p.x.toFixed(4), y1: p.y.toFixed(4), x2: q.x.toFixed(4), y2: q.y.toFixed(4) }));
    }
    svg.append(s("circle", { cx: p.x.toFixed(4), cy: p.y.toFixed(4), r: 0.022 }), s("circle", { class: "core", cx: p.x.toFixed(4), cy: p.y.toFixed(4), r: 0.007 }));
  }
}

/* the one rAF loop: the globe turns (1.2° a second), the shocks ignite as the playhead crosses their dates, the turn eases to a
   stop, then the loop sleeps and wakes only for the pointer and scroll parallax (≤ 2°). Off-screen, a hidden tab, Pause motion
   and reduced motion: no frames at all after one still render with every shock lit. */
const still = () => reduce.matches || G.paused;
function layoutGlobe() {
  if (!G.globe) return;
  const hb = hero.getBoundingClientRect(), sb = slot.getBoundingClientRect();
  const r = Math.max(60, Math.min(sb.width, sb.height) / 2);
  G.globe.resize(hb.width, hb.height, { cx: (sb.left - hb.left + sb.width / 2) / hb.width, cy: (sb.top - hb.top + sb.height / 2) / hb.height, r, lat: TILT });
  wake();
}
function settle() {                                  // every shock lit at once, the playhead at the end
  if (G.globe) for (let i = G.next; i < G.events.length; i++) G.globe.ignite(i, true);
  G.next = G.events.length; G.done = true;
  playheadEnd();
  wake();
}
const playheadEnd = () => { $("#playhead").style.transform = `translateX(${$("#ruler").clientWidth}px)`; };
let spinV = 1.2;
function tick(now) {
  G.frame = 0;
  const dt = Math.min(0.05, G.last ? (now - G.last) / 1000 : 0); G.last = now;
  let moving = false;
  if (!still() && G.startAt) {
    const p = Math.max(0, (now - G.startAt) / IGNITE_MS);
    while (G.next < G.events.length && pos(Date.parse(G.events[G.next].date)) <= p) { G.globe.ignite(G.next); G.next += 1; }
    $("#playhead").style.transform = `translateX(${Math.min(1, p) * $("#ruler").clientWidth}px)`;
    if (G.next >= G.events.length && p >= 1) G.done = true;
    if (G.done) spinV = Math.max(0, spinV - dt * 0.4);                    // three seconds to a stop: then stillness
    G.lon += dt * spinV;
    const k = 1 - Math.exp(-dt / 0.6);
    G.sx += (G.px - G.sx) * k; G.sy += (G.py + G.scrollP - G.sy) * k;
    moving = spinV > 0 || Math.abs(G.px - G.sx) > 1e-3 || Math.abs(G.py + G.scrollP - G.sy) > 1e-3 || p < 1.4;
  }
  const tilt = Math.max(-2, Math.min(2, G.sy * 2)), turn = Math.max(-2, Math.min(2, G.sx * 2));
  G.globe.draw(G.lon + turn, dt, tilt);
  if (moving && G.visible && !document.hidden) G.frame = requestAnimationFrame(tick); else G.last = 0;
}
function wake() { if (G.globe && !G.frame && G.visible && !document.hidden) G.frame = requestAnimationFrame(tick); }

async function startGlobe(v) {
  G.events = v.shocks ? v.shocks.events : [];
  /* the one WebGL context, asked for here first: without it the poster stays and three.js is never downloaded (no console error) */
  let gl = null;
  try { gl = canvas.getContext("webgl2", { antialias: true, alpha: false, depth: true, stencil: false, powerPreference: "default", failIfMajorPerformanceCaveat: true }); } catch (e) { gl = null; }
  if (!gl) { hero.classList.add("no-webgl"); playheadEnd(); return; }
  let mod = null;
  try { mod = await import("./classic-globe.js"); } catch (e) { mod = null; }
  const globe = mod && mod.createGlobe(canvas, G.events, { context: gl, lon0: LON0, tierWidth: Math.min(innerWidth, innerHeight * 1.6),
    onReady() { hero.classList.add("is-lit"); if (still()) settle(); else G.startAt = performance.now() + 500; wake(); },
    onLost(isLost) { hero.classList.toggle("no-webgl", isLost); if (!isLost) wake(); } });
  if (!globe) { hero.classList.add("no-webgl"); playheadEnd(); return; }
  G.globe = globe; G.lon = LON0;
  layoutGlobe();
  new ResizeObserver(layoutGlobe).observe(hero);
  new IntersectionObserver(([en]) => { G.visible = en.isIntersecting; wake(); }).observe(hero);
  document.addEventListener("visibilitychange", () => { G.last = 0; wake(); });
  hero.addEventListener("pointermove", (ev) => {
    if (ev.pointerType !== "mouse" || still()) return;
    const b = hero.getBoundingClientRect();
    G.px = ((ev.clientX - b.left) / b.width - 0.5); G.py = ((ev.clientY - b.top) / b.height - 0.5); wake();
  });
  addEventListener("scroll", () => { if (!still()) { G.scrollP = Math.min(1, Math.max(0, scrollY / hero.offsetHeight)) * 0.5; wake(); } }, { passive: true });
  reduce.addEventListener("change", () => { if (still()) settle(); else wake(); });
}
const pauseBtn = $("#pause");
pauseBtn.addEventListener("click", () => {
  G.paused = !G.paused;
  pauseBtn.setAttribute("aria-pressed", String(G.paused));
  const word = G.paused ? "Play motion" : "Pause motion";
  pauseBtn.setAttribute("aria-label", word); pauseBtn.title = word;
  pauseBtn.replaceChildren(icon(G.paused ? "i-play" : "i-pause"));
  if (G.paused) settle(); else { G.last = 0; spinV = G.done ? 0 : 1.2; wake(); }
});

/* ---- the fall (ledger §14: series / running high − 1, the floor flat where the rule measures it), our own SVG. Its shape is
   the fraction; every dollar on it is a Result key (ruling R18: the trough's kpis.loss_dollars, the breaches' loss_dollars,
   the capacity), and the hatch is the Result's below_floor. Used twice: the thesis beat (third person, the default run) and
   the cockpit (second person, the investor on screen). ---- */
function txt(parent, x, y, t, attrs = {}) { const e = s("text", { x, y, ...attrs }); e.textContent = t; parent.append(e); return e; }
function drawFall(box, v, { story = false } = {}) {
  const P = v.paths;
  if (!P) { box.replaceChildren(h("p", { class: "chart-empty", text: "The fall below the floor is drawn here once a check has run." })); return null; }
  const W = box.clientWidth || 800, H = box.clientHeight || 320, mob = W < 640;
  const his = story ? v.who.his : "your", His = his.charAt(0).toUpperCase() + his.slice(1);
  const main = P.after || P.today, side = P.after ? v.fall.after : v.fall.today;
  const L = mob ? 4 : 132, R = mob ? 4 : (P.after ? 176 : 132), T = mob ? 62 : 20, B = 40, x0 = L, x1 = W - R, y0 = T, y1 = H - B;
  const ts = P.dates.map((d) => Date.parse(d)), tA = ts[0], tZ = ts[ts.length - 1];
  const vals = main.concat(P.today).filter((x) => typeof x === "number");
  const lo = Math.min(P.floor !== null ? P.floor : 0, ...vals), YMIN = lo < 0 ? lo * 1.14 : -0.01;
  const X = (t) => x0 + ((t - tA) / (tZ - tA)) * (x1 - x0), Y = (val) => y0 + (val / YMIN) * (y1 - y0);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0", "aria-label": `Drop from the running high, ${PF.fmt.date(P.dates[0])} to ${PF.fmt.date(P.dates[P.dates.length - 1])}` });
  const defs = s("defs"), pat = s("pattern", { id: `hatch-${box.id}`, width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
  pat.append(s("rect", { class: "breach-wash", width: 8, height: 8 }), s("line", { class: "breach-hatch", x1: 0, y1: 0, x2: 0, y2: 8 }));
  defs.append(pat); svg.append(defs);
  const yF = P.floor !== null ? Y(P.floor) : null;
  if (yF !== null) svg.append(s("rect", { class: "ground", x: x0, y: yF, width: x1 - x0, height: Math.max(0, y1 - yF) }));
  svg.append(s("line", { class: "base", x1: x0, x2: x1, y1: Y(0), y2: Y(0) }));
  const ax = { class: "ax" };                       // no computed tick (R18): the zero line, the floor and the Result's dollars
  if (mob) txt(svg, x0, Y(0) - 8, "$0", ax); else txt(svg, x0 - 14, Y(0) + 5, "$0", { ...ax, "text-anchor": "end" });
  for (let yr = new Date(tA).getUTCFullYear() + 1; yr <= new Date(tZ).getUTCFullYear(); yr++) {
    const xx = X(Date.UTC(yr, 0, 1));
    svg.append(s("line", { class: "base", x1: xx, x2: xx, y1: y1, y2: y1 + 6 }));
    txt(svg, xx, y1 + 26, String(yr), { class: "ax yr", "text-anchor": "middle" });
  }
  const paths = s("g", { class: "reveal" });
  if (yF !== null) {             // the breach: hatched over the Result's below_floor stretches only (the server decides, R18)
    const at = (i) => Y(typeof main[i] === "number" ? Math.min(main[i], P.floor) : P.floor);
    for (const [i0, i1] of P.hatch) {
      const p = [[X(ts[i0]), yF]];
      for (let i = i0; i <= i1; i++) p.push([X(ts[i]), at(i)]);
      p.push([X(ts[i1]), yF]);
      paths.append(s("polygon", { points: p.map((q) => q.map((n) => n.toFixed(1)).join(",")).join(" "), fill: `url(#hatch-${box.id})` }));
    }
  }
  const pts = (arr) => arr.map((val, i) => (typeof val === "number" ? `${X(ts[i]).toFixed(1)},${Y(val).toFixed(1)}` : null)).filter(Boolean).join(" ");
  paths.append(s("polyline", { class: "today", points: pts(P.today) }));
  if (P.after) paths.append(s("polyline", { class: "after-move", points: pts(P.after) }));
  svg.append(paths);
  if (yF !== null) {
    svg.append(s("line", { class: "floor", x1: x0, x2: x1, y1: yF, y2: yF }));
    if (mob) { const t = txt(svg, x1, yF - 8, `${His} floor `, { class: "floor-t", "text-anchor": "end" }); t.append(Object.assign(s("tspan", { class: "floor-v" }), { textContent: v.floor.label })); }
    else { txt(svg, x0 - 14, yF - 6, `${His} floor`, { class: "floor-t", "text-anchor": "end" }); txt(svg, x0 - 14, yF + 16, v.floor.label, { class: "floor-v", "text-anchor": "end" }); }
  }
  return finishFall({ box, svg, v, P, main, side, ts, X, Y, x0, x1, y0, y1, mob, his, story });
}
function finishFall(o) {
  const { box, svg, v, P, main, side, ts, X, Y, x0, x1, y0, y1, mob, his, story } = o;
  const notes = s("g", { class: "notes" });
  const todayLabel = P.after ? (story ? `${his.charAt(0).toUpperCase() + his.slice(1)} mix today` : "Today") : (story ? `${his.charAt(0).toUpperCase() + his.slice(1)} mix` : "Your mix");
  const lab = [[todayLabel, "lbl-today", P.today]];
  if (P.after && v.move) lab.push([`With ${v.move.weightText} in ${v.move.name}`, "lbl-after-move", P.after]);
  const lastOf = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (typeof arr[i] === "number") return arr[i]; return 0; };
  if (mob) lab.forEach(([t, cls], i) => { notes.append(s("line", { class: cls === "lbl-today" ? "today" : "after-move", x1: x0, x2: x0 + 20, y1: 12 + i * 22, y2: 12 + i * 22 }));
    txt(notes, x0 + 28, 17 + i * 22, t, { class: cls }); });
  else { let prev = -1e9; lab.map(([t, cls, arr]) => [t, cls, Y(lastOf(arr))]).sort((a, b) => a[2] - b[2]).forEach(([t, cls, yy]) => {
    const yv = Math.max(yy + 5, prev + 22); prev = yv; txt(notes, x1 + 12, yv, t, { class: cls }); }); }
  // the trough: ring, leader, and the dollar figure where the lines have recovered (the empty ground under them)
  let ti = P.trough;                                   // the Result's trough date (PF.view pins its quoted value there)
  if (!(ti >= 0) || typeof main[ti] !== "number") { ti = 0; main.forEach((val, i) => { if (typeof val === "number" && val < main[ti]) ti = i; }); }
  const tx = X(ts[ti]), ty = Y(main[ti]);
  if (side && side.dollarsText) {
    let ri = ti; while (ri < main.length - 1 && main[ri] < 0.3 * main[ti]) ri++;
    const big = mob ? 30 : Math.round(Math.min(56, Math.max(36, (x1 - x0) / 16)));
    const ax = Math.min(X(ts[ri]) + (mob ? 10 : 24), x1 - (mob ? 170 : big * 6.2)), gap = mob ? 18 : 24;
    /* the figure and its line never cross the floor or leave the frame: below the trough, else astride it, else stacked above */
    const yF = P.floor !== null ? Y(P.floor) : null, clear = (top, bottom) => (yF === null || bottom < yF - 8 || top > yF + 8) && top > y0 && bottom < y1 + 4;
    const tries = [[ty + big * 0.36, ty + big * 0.36 + gap], [ty - 6, ty + 20], [ty - 6, ty - 6 - big * 0.82 - 8]];
    const [by, sy] = tries.find(([b1, s1]) => clear(Math.min(b1 - big * 0.78, s1 - 14), Math.max(b1, s1 + 4))) || tries[0];
    notes.append(s("circle", { class: "mark", cx: tx, cy: ty, r: mob ? 6 : 8 }), s("line", { class: "lead-line", x1: tx + (mob ? 8 : 11), x2: ax - 10, y1: ty, y2: ty }));
    const fig = txt(notes, ax, by, side.dollarsText, { class: "big" }); fig.style.setProperty("--fall-big", `${big}px`);
    txt(notes, ax, sy, mob ? `${side.ddText} from its high` : `${side.ddText} from its high, the same fall on ${his} ${v.amountText}`, { class: "sub" });
  }
  for (const b of v.breaches.slice(1, mob ? 1 : 3)) {   // the other drops deeper than the floor: a ring, the date and the dollars (not on phones)
    const i = P.dates.findIndex((d) => d >= b.trough); if (i < 0 || typeof main[i] !== "number") continue;
    const bx = X(ts[i]), byy = Y(main[i]), right = bx + 190 < (box.clientWidth || x1);   // to the right while it fits the frame
    notes.append(s("circle", { class: "mark", cx: bx, cy: byy, r: mob ? 5 : 7 }));
    const t = txt(notes, bx + (right ? 14 : -14), byy + 22, `${b.troughText} `, { class: "sub", "text-anchor": right ? "start" : "end" });
    t.append(Object.assign(s("tspan", { class: "small" }), { textContent: b.dollarsText || b.ddText }));   // the Result's dollars, else its depth
  }
  svg.append(notes);
  /* the readout under the pointer or the arrow keys: the drop from the high on that day, no easing (direct manipulation). In
     percent: the page never prices a day in dollars (R18); at the Result's own troughs it reads the quoted number. */
  const cur = s("g", { class: "cursor", opacity: 0 }), cl = s("line", { y1: y0, y2: y1 }), cd = txt(cur, 0, Math.max(12, y0 - 8), "", { "text-anchor": "middle" });
  const cv = [txt(cur, 0, 0, "", { class: "cv-today" }), txt(cur, 0, 0, "", { class: "cv-after-move" })];
  cur.prepend(cl); svg.append(cur);
  let ci = ti;
  const show = (i) => { ci = Math.max(0, Math.min(P.dates.length - 1, i)); const xx = X(ts[ci]), left = xx > x1 - 150 || ci === ti;   // clear of the trough's label
    cl.setAttribute("x1", xx); cl.setAttribute("x2", xx); cd.setAttribute("x", xx); cd.textContent = PF.fmt.date(P.dates[ci]);
    [P.today, P.after].forEach((arr, k) => { const val = arr && arr[ci]; cv[k].textContent = typeof val === "number" ? PF.fmt.pct(val) : "";
      if (typeof val === "number") { cv[k].setAttribute("x", xx + (left ? -10 : 10)); cv[k].setAttribute("text-anchor", left ? "end" : "start"); cv[k].setAttribute("y", Y(val) + (k ? 20 : -8)); } });
    cur.setAttribute("opacity", 1); };
  svg.addEventListener("pointermove", (ev) => { const b = svg.getBoundingClientRect(), t = ts[0] + ((ev.clientX - b.left - x0) / (x1 - x0)) * (ts[ts.length - 1] - ts[0]);
    const i = ts.findIndex((val) => val >= t); show(i < 0 ? ts.length - 1 : i); });
  svg.addEventListener("pointerleave", () => cur.setAttribute("opacity", 0));
  svg.addEventListener("blur", () => cur.setAttribute("opacity", 0));
  svg.addEventListener("keydown", (ev) => { const k = { ArrowRight: 5, ArrowLeft: -5, Home: -1e6, End: 1e6 }[ev.key]; if (k === undefined) return; ev.preventDefault(); show(ci + k); });
  const desc = s("desc"); desc.textContent = [side && side.dollarsText ? `The worst fall was ${side.dollarsText} (${side.ddText})${side.troughText ? ` on ${side.troughText}` : ""}.` : "",
    v.floor ? `The floor is ${v.floor.label}.` : "", "Use the arrow keys to read any week."].filter(Boolean).join(" ");
  svg.prepend(desc);
  box.replaceChildren(svg);
  return svg;
}

/* ---- screen 2, the thesis beat: the default run's growth against its floor, and the fall in dollars ---- */
function renderThesis(v) {
  const line = $("#thesis-line");
  fill(line, v.lines.thesis);
  line.hidden = !v.lines.thesis;
  drawFall($("#thesis-chart"), v, { story: true });
  $("#thesis-foot").textContent = v.paths ? "In CAD, unhedged, rebalanced daily, no costs." : "";
}

/* ---- screen 3, the cockpit ---- */
const tabs = [...document.querySelectorAll(".tab")];
function investorSource(pid, r) {                   // the card's source: the investor's run, else its definition (live), else nothing
  if (S.custom && S.custom.pid === pid)      // your answers; once their own run is back, its profile and limits (Minor 10)
    return r && r === S.custom.result ? { ...r } : { ...(r || {}), ...S.custom.src };
  if (r) return r;
  const p = S.investors && S.investors[pid];
  return p ? { pilot: pid, amount: p.amount, profile: { name: p.name, age: p.age, ...p.profile }, question: p.question } : null;
}
function renderCard(pid, r) {
  const src = investorSource(pid, r), v = viewOf(src || {});
  const name = S.custom && S.custom.pid === pid ? "You" : v.who.name || (tabs.find((t) => t.dataset.id === pid) || {}).textContent || "";
  $("#who-name").textContent = v.who.age !== null && name !== "You" ? `${name}, ${v.who.age}` : name;
  $("#who-line").textContent = S.custom && S.custom.pid === pid ? "Your own answers, on this mix." : COPY[pid] || "";
  $("#facts").replaceChildren(...PF.youRows(src).map((row) => h("div", { class: row.note ? "has-note" : null },
    h("dt", { text: row.label }), h("dd", {}, numText(row.value)), row.note ? h("span", { class: "note", text: row.note }) : null)));
}
/* the question box shows the investor's own question on a tab change (and the hero's replay), never after a run: a blocked,
   clarify or failed answer keeps the words the investor typed (W-S1 review I2) */
function fillQuestion(pid) {
  const src = investorSource(pid, S.runs[pid]);
  $("#q").value = (src && src.question) || "";
}
function numText(t) {     // a card value: its figures set in B612, its words in Archivo
  return String(t).split(/([−-]?\$?\d[\d,.]*(?:\u00a0%)?)/).filter(Boolean).map((p) => (/^[−-]?\$?\d/.test(p) ? h("span", { class: "num", text: p }) : p));
}
function renderLabels(v) {
  const box = $("#labels"); box.replaceChildren();
  if (FAKE) box.append(h("span", { class: "label is-saved", text: "FAKE data for design review" }));
  else if (v.saved) box.append(h("span", { class: "label is-saved", text: "Saved run" }));
  if (v.asOf) box.append(h("span", { class: "label", text: `As of ${v.asOf}` }));
  if (v.commit) box.append(h("span", { class: "label", text: `Code ${v.commit}` }));
}
function renderIdle(pid) {                          // the designed empty state: the same boxes, nothing moves when the answer lands
  const src = investorSource(pid, null), v = viewOf(src || {});
  $("#lamp").dataset.tone = "idle"; $("#lamp-icon").setAttribute("href", "#i-pending"); $("#lamp-word").textContent = "Not run yet";
  $("#today-line").classList.add("is-off");
  $("#dollar").textContent = `Run the check to replay ${v.who.name ? `${v.who.name}’s` : "this"} question on real history.`;
  $("#dollar-note").textContent = v.capacityText ? `The answer lands here, in dollars, next to the ${v.capacityText} you said you could absorb.` : "";
  drawFall($("#chart"), { paths: null }); $("#chart-foot").textContent = "";
  $("#rows").replaceChildren(); $("#labels").replaceChildren(); $("#read-as").hidden = true;
}
function renderAnswer(v, { landing = false } = {}) {
  const ans = $("#answer");
  ans.classList.remove("is-landing");
  renderLabels(v);
  const tl = $("#today-line");
  tl.classList.toggle("is-off", !v.lines.today);
  if (v.lines.today) { tl.dataset.tone = v.today.tone; tl.querySelector("use").setAttribute("href", "#" + v.today.icon); $("#today-word").textContent = v.lines.today; }
  const lamp = $("#lamp");
  lamp.hidden = !v.verdict;
  if (v.verdict) { lamp.dataset.tone = v.verdict.tone; $("#lamp-icon").setAttribute("href", "#" + v.verdict.icon); $("#lamp-word").textContent = v.verdict.word; }
  fill($("#dollar"), v.lines.dollar || [[v.message || ""]]);
  fill($("#dollar-note"), v.paths ? v.lines.note : null);
  drawFall($("#chart"), v);
  $("#chart-foot").textContent = v.paths ? `Drop from the running high, in dollars on your ${v.amountText}. In CAD, unhedged, rebalanced daily, no costs.` : "";
  $("#rows").replaceChildren(...v.rows.slice(0, 3).map((row) => h("li", { "data-tone": row.tone },
    h("span", { class: "st" }, icon(row.icon), row.word), h("span", { class: "nm", text: row.name }),
    h("span", { class: "cmp" }, row.compare ? numText(row.compare) : row.reason || ""), h("span", { class: "tier", text: row.tier || "" }))));
  const ra = $("#read-as");
  ra.hidden = !v.move;
  if (v.move) $("#read-as-move").textContent = v.move.readAs;
  if (landing) { void ans.offsetWidth; ans.classList.add("is-landing"); }
}
/* the whole page for the Result on screen. first = the default run: the hero and the thesis read it; later runs only the cockpit */
function renderAll(first, land = false) {
  const r = S.r, v = (S.v = viewOf(r));
  if (first) { renderHero(v); renderThesis(v); S.base = v; }
  renderCard(S.pid, v.stop || !v.ok ? S.runs[S.pid] : r);     // a stopped run never empties the card: it keeps the investor's own
  if (v.stop || !v.ok) { renderStop(v); return; }
  renderAnswer(v, { landing: land && !reduce.matches });
  if (land && reduce.matches) $("#lamp").focus({ preventScroll: false });   // reduced motion jumps to the answer
}
function renderStop(v) {                            // blocked, clarify, limits missing, error: the server's one plain sentence
  renderIdle(S.pid);
  const lamp = $("#lamp");
  lamp.hidden = false; lamp.dataset.tone = "none"; $("#lamp-icon").setAttribute("href", "#i-warn");
  $("#lamp-word").textContent = v.verdict ? v.verdict.word : v.status === "blocked" ? "Not a simulation question" : "No answer";
  $("#dollar").textContent = v.message || PF.UNSHOWN; $("#dollar-note").textContent = "";
}
/* no Result to show (no saved run yet, or nothing loaded): the idle state and the question box ready */
function renderEmpty() {
  S.r = null;
  renderCard(S.pid, S.runs[S.pid] || null);          // the investor on the tab, from its own saved run or its definition
  renderIdle(S.pid);
}
function askLine(message) {
  const box = $("#ask-line"); box.replaceChildren();
  if (message) box.append(icon("i-warn"), h("span", { text: message }));
}

/* ---- the run: progress lines into the log, then the answer lands ---- */
const LOG = { run: "run", done: "done", skipped: "skip", error: "fail", warn: "warn", fail: "fail" };
const LOG_WORD = { run: "Running", done: "Done", skip: "Skipped", warn: "Caution", fail: "Failed" };
function onProgress(ln) {
  if (!ln || ln.type !== "progress" || !ln.step) return;
  const box = $("#runlog");
  let li = [...box.children].find((x) => x.dataset.step === ln.step);
  if (!li) { li = h("li", { "data-step": ln.step, class: "is-new" }, icon("i-pending", "st"), h("span", { class: "nm" }), h("span", { class: "sv" }), h("span", { class: "dt" })); box.append(li); }
  const st = LOG[ln.status];
  if (st) {
    li.dataset.state = st; li.querySelector(".st use").setAttribute("href", "#" + ({ done: "i-in", warn: "i-warn", fail: "i-out" }[st] || "i-pending"));
    const ic = li.querySelector(".st");                   // the state in words too, never the icon alone (Minor 10)
    ic.removeAttribute("aria-hidden"); ic.setAttribute("role", "img"); ic.setAttribute("aria-label", LOG_WORD[st]);
  }
  li.querySelector(".nm").textContent = ln.label || ln.step;
  if (typeof ln.detail === "string" && ln.detail) li.querySelector(".dt").textContent = ln.detail;
  li.querySelector(".sv").textContent = [ln.service, Number.isFinite(ln.ms) && ln.status !== "run" ? `${Math.round(ln.ms).toLocaleString("en-CA")} ms` : ""].filter(Boolean).join(" ");
}
const READ_ONLY = "This read-only demo replays its saved runs; the live app runs any question.";
const NO_RUN = "There is no saved run for this investor yet.";
const norm = (q) => String(q || "").toLowerCase().replace(/\s+/g, " ").trim();
function planFor() {                                 // what POST /api/run gets: the investor's mix and answers, the words in the box
  const pid = S.pid, def = S.investors && S.investors[pid];
  const plan = def ? PF.planFrom({ ...def, pilot: pid }, pid) : PF.planFrom(S.runs[pid] || S.r || {}, pid);
  if (S.custom && S.custom.pid === pid) Object.assign(plan, S.custom.plan);
  plan.q = $("#q").value.trim();
  return plan;
}
async function startRun() {
  if (S.running) return;
  const btn = $("#run");
  S.running = true; btn.disabled = true; $("#run-label").textContent = "Checking"; $("#run-spin").hidden = false;
  askLine(null); $("#runlog").replaceChildren();
  const unlock = () => { S.running = false; btn.disabled = false; $("#run-label").textContent = "Run the check"; $("#run-spin").hidden = true; };
  /* the run gave no Result to draw: this investor's last good Result stays on screen (never another investor's) and one plain
     line says why (a plain sentence from the server, or ours; never the text of an exception), and the focus goes back to Run. */
  const fail = (message, wasDropped) => {
    unlock();
    const last = PF.lastGood(S.last, S.pid);
    if (last) { try { S.r = last; renderAll(false); } catch (e) { console.error(e); renderEmpty(); } askLine(message); }
    else if (wasDropped) { renderEmpty(); askLine(message); }
    else { try { S.r = bridge({ status: "error", message }); renderAll(false); } catch (e) { console.error(e); renderEmpty(); askLine(message); } }
    btn.focus();
  };
  const done = (r) => {
    unlock();
    if (!r || typeof r !== "object") { fail(PF.failureLine(null)); return; }
    if (r.status === "error") { fail(PF.failureLine(r)); return; }
    try {   // a drawing bug must not hide the last good Result
      S.r = bridge(r);
      if (S.custom && S.custom.pid === S.pid) S.custom.result = S.r;     // the run of your own answers
      renderAll(false, true);
      if (!PF.view(r).stop) S.last[S.pid] = r;
    } catch (e) { console.error(e); fail(PF.failureLine(e)); }
  };
  const progress = (ln) => { try { onProgress(ln); } catch (e) { console.error(e); } };   // a line that cannot be drawn never loses the answer
  try {
    if (FAKE || STATIC) {
      const saved = await resultFor(S.pid);
      const edited = S.custom && S.custom.pid === S.pid;
      if (!saved || (STATIC && (edited || norm(saved.question) !== norm($("#q").value)))) {
        unlock(); askLine(saved ? READ_ONLY : NO_RUN); if (STATIC && meta("live")) $("#ask-line").append(" ", h("a", { href: meta("live"), text: "Open the live app" }));
        return;
      }
      const replay = structuredClone(saved);
      if (COMMIT.has(saved)) COMMIT.set(replay, COMMIT.get(saved));      // the copy keeps the run's own commit (W-S1 review I3)
      playLines(replayLines(saved, FAKE ? "FAKE replay" : "saved run"), progress, () => done(replay));
    } else {
      await realStream(PF.requestBody(planFor(), null, false), (ln) => { if (ln.type === "progress") progress(ln); else if (ln.type === "result") done(ln.result); });
    }
  } catch (err) {
    if (!(err && (err.dropped || err.plain))) console.error(err);   // a bug, for the developer; the page shows the fixed sentence
    fail(PF.failureLine(err), !!(err && err.dropped));
  }
}

/* ---- You: four quiet tabs, one card; "Start with you" opens the five questions in place ---- */
async function select(pid, { keyboard = false } = {}) {
  if (pid === S.pid || S.running) return;
  S.pid = pid;
  tabs.forEach((t) => { const on = t.dataset.id === pid; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
  $("#card").setAttribute("aria-labelledby", `tab-${pid}`);
  closeFive(); askLine(null); $("#runlog").replaceChildren();
  const body = $("#card-body");
  const swap = async () => {
    const r = await resultFor(pid);
    if (S.pid !== pid) return;
    S.r = r ? bridge(r) : null;
    if (r) { renderAll(false); if (!PF.view(r).stop) S.last[pid] = r; } else renderEmpty();
    fillQuestion(pid);
    body.classList.remove("is-swapping");
  };
  if (keyboard || reduce.matches) swap(); else { body.classList.add("is-swapping"); setTimeout(swap, ms("dur-list")); }
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => select(t.dataset.id));
  t.addEventListener("keydown", (ev) => {
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[ev.key]; if (j === undefined) return;   // APG tabs
    ev.preventDefault(); const n = tabs[(j + tabs.length) % tabs.length]; n.focus(); select(n.dataset.id, { keyboard: true });
  });
});
const five = $("#five");
function openFive() {
  const src = investorSource(S.pid, S.runs[S.pid]) || {}, p = src.profile || {}, cap = [p.capacity, p.capacity_dollars].find(Number.isFinite);
  five.elements.goal.value = p.goal || "balance"; five.elements.horizon.value = Number.isFinite(p.horizon_years) ? p.horizon_years : "";
  five.elements.loss.value = Number.isFinite(cap) ? Math.round(cap) : ""; five.elements.unit.value = "$";
  const in22 = p.in_2022 || { sold: "sold", held: "held", bought: "bought more" }[p.reaction_2022] || "held";
  for (const el of five.querySelectorAll('[name="in_2022"]')) el.checked = el.value === in22;
  five.elements.esg.checked = !!p.esg; five.elements.crypto.checked = !!p.crypto;
  five.hidden = false; $("#start").setAttribute("aria-expanded", "true"); $("#five-err").textContent = ""; five.elements.goal.focus();
}
function closeFive() { five.hidden = true; $("#start").setAttribute("aria-expanded", "false"); $("#five-err").textContent = ""; }
$("#start").addEventListener("click", () => (five.hidden ? openFive() : closeFive()));
$("#five-cancel").addEventListener("click", () => { closeFive(); $("#start").focus(); });
five.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const src = investorSource(S.pid, S.runs[S.pid]) || {}, f = five.elements;
  const checked = five.querySelector('[name="in_2022"]:checked');
  const res = PF.profileFromAnswers({ goal: f.goal.value, horizon: f.horizon.value, loss: f.loss.value, unit: f.unit.value,
    in_2022: checked ? checked.value : null, esg: f.esg.checked, crypto: f.crypto.checked }, src.amount);
  if (res.error) { $("#five-err").textContent = res.error; return; }
  const p = res.profile;
  S.custom = { pid: S.pid, src: { profile: p, limits: null },
    plan: { goal: p.goal, horizon: p.horizon_years, capacity: p.capacity, in_2022: checked.value, esg: p.esg, crypto: p.crypto } };
  closeFive(); renderCard(S.pid, S.runs[S.pid]);
  askLine(STATIC ? READ_ONLY : null); $("#run").focus();
});
$("#ask").addEventListener("submit", (ev) => { ev.preventDefault(); startRun(); });
$("#replay").addEventListener("click", async (ev) => {   // the hero's one action: Robert's move, replayed in the cockpit
  ev.preventDefault();
  if (S.pid !== "robert") await select("robert", { keyboard: true });
  fillQuestion("robert");                               // the button replays Robert's own question, whatever the box held
  $("#cockpit").scrollIntoView({ behavior: reduce.matches ? "auto" : "smooth", block: "start" });
  setTimeout(startRun, reduce.matches ? 0 : 600);
});
const bar = $("#bar");
const solid = () => bar.classList.toggle("is-solid", scrollY > 24);
addEventListener("scroll", solid, { passive: true }); solid();
let rz = 0;
addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (S.base) drawFall($("#thesis-chart"), S.base, { story: true }); if (S.v && S.v.ok) drawFall($("#chart"), S.v); }, 150); });
addEventListener("error", (e) => { window.__errors.push(String(e.message)); });

async function init() {
  if (FAKE) $("#fake-badge").hidden = false;
  await loadInvestors();
  const r = await resultFor("robert");
  if (r) { S.r = bridge(r); renderAll(true); if (!PF.view(r).stop) S.last.robert = r; }
  else { const v0 = viewOf({}); renderHero(v0); renderThesis(v0); renderEmpty(); }
  fillQuestion("robert");
  const v = S.base || viewOf({});
  $("#source-line").textContent = v.asOf ? `Data to ${v.asOf}` : "";
  startGlobe(v);
}
window.__epi = { run: startRun, select, ready: () => hero.classList.contains("is-lit") || hero.classList.contains("no-webgl") };
init().catch((e) => { console.error(e); renderEmpty(); askLine("The page could not load its data. Reload the page."); });
/* Enter submits the question (Shift+Enter is a new line); keyboard actions never animate anything themselves */
$("#q").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); startRun(); } });
