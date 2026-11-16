/* #hero (lane U1; the first screen's layout lane polish-hero, R41). The headline across the frame ("Crash-test your move before
   you make it.") with its one sub-line and the French line; under it, left, the three steps: the investor chips and one line
   about the (fictional) investor, ① what they hold (lane hold), ② the move in their words (the command bar, lane picker's row
   in it), ③ one Replay button; right, the night Earth as an instrument turned to the asked shock: the counter on top, the disc
   with one calm caption on its lower edge, the key under it. All of it above the fold at 1440x900 and 1280x800. No verdict here.
   The globe (web/globe.js) is created after first paint on a fixed full-viewport canvas and put on the store as `globe`; the
   #replay stage reuses it through setLayout("stage"). Every number is a Result key, through PF.view and web/lib/u1.js.
   Store: reads mode, investor, result, view, phase; writes investor (chips), question + replay (Replay / Enter), globe. */
import { askedFamily, shocksOf, ignitionOrder, worstPrecedent, heroView, heroCopy, stageFrame,
  stickyBox, ringRadius, mixFrame, easeInOut, unproject, counterText, sweepPath, SWEEP_FROM, PERSONA_NOTE, HOME, HOME_MARKET, caseLine, STACK_LINE } from "../lib/u1.js";
import { askLabel, throughWords, goLabel, namesMove } from "../lib/movepicker.js";

const INVESTORS = [["robert", "Robert"], ["mateo", "Mateo"], ["amira", "Amira"], ["canadian", "Too Canadian?"], ["you", "You"]];   // "You": lane profile-ui (R46)
const POSTER = new URL("../vendor/nasa/earth-poster-americas.jpg", import.meta.url).href;      // the hero's view (the lead's)
const POSTER_SWEEP = new URL("../vendor/nasa/earth-poster-sweep.jpg", import.meta.url).href;   // where the first-five-second sweep starts
const IGNITE_MS = 4000, SWEEP_MS = 4600, SVG = "http://www.w3.org/2000/svg";
const PF = () => globalThis.PF;

function h(tag, attrs = {}, ...kids) {        // elements from data: textContent and attributes, never HTML strings
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") n.textContent = v; else if (k === "class") n.className = v; else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}
const s = (tag, attrs = {}) => { const n = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };
const segsTo = (el, segs) => el.replaceChildren(...(segs || []).map(([t, kind]) => (kind === "num" ? h("span", { class: "fig hx-num", text: t }) : document.createTextNode(t))));
const ringKey = () => { const k = s("svg", { class: "hx-key", viewBox: "0 0 20 20", "aria-hidden": "true" });
  k.append(s("circle", { cx: 10, cy: 10, r: 7.25, class: "hx-key-ring" }), s("circle", { cx: 10, cy: 10, r: 4, class: "hx-key-halo" }), s("circle", { cx: 10, cy: 10, r: 1.75, class: "hx-key-core" }));
  return k; };

function build() {
  const R = {};
  R.canvas = h("canvas", { class: "hx-canvas", "aria-hidden": "true" });
  R.poster = h("img", { class: "hx-poster", alt: "", width: 1600, height: 1600, decoding: "async", fetchpriority: "high", draggable: "false" });
  R.rings = s("svg", { class: "hx-rings", viewBox: "-1 -1 2 2", "aria-hidden": "true" });
  R.slot = h("div", { class: "hx-globe", "aria-hidden": "true" }, R.poster, R.rings);
  R.q = h("textarea", { id: "hx-q", class: "hx-q", rows: 2, spellcheck: "false", autocomplete: "off", "aria-describedby": "hx-hint" });
  /* R24 and the design director (15:55): ① what the investor holds (lane hold), ② "The move, in Robert’s words" (this box, and
     lane picker's "Try another move" under it), ③ a 56 px pill naming the move, then the years; words from web/lib/movepicker.js */
  const play = s("svg", { class: "icon hx-go-i", "aria-hidden": "true", focusable: "false" }); play.append(s("use", { href: "#i-play" }));
  R.goText = h("span", { class: "hx-go-t", text: "Replay" });
  R.go = h("button", { class: "btn btn-primary hx-go", type: "submit", "aria-describedby": "hx-go-years" },
    h("span", { class: "sr", text: "Step 3: " }), play, R.goText);
  R.goYears = h("span", { class: "hx-go-years", id: "hx-go-years" });   // ③ reads "Replay Robert’s move through 2021–26"
  R.hint = h("p", { class: "hx-hint", id: "hx-hint", text: "" });
  R.askT = h("span", { class: "step-t" });
  R.pick = h("div", { class: "hx-pick" });          // lane picker: "Try another move" (sections/movepicker.js mounts it)
  R.textFns = [];                                   // called after the box's words change (the picker reads them back)
  R.form = h("form", { class: "hx-ask", novalidate: true, "aria-label": "The question to replay" },
    h("label", { class: "step hx-step", for: "hx-q" }, ...stepN(2), R.askT), h("div", { class: "hx-field" }, R.q), R.pick,
    h("div", { class: "hx-go-row" }, h("span", { class: "step-n", "aria-hidden": "true", text: "3" }), R.go, R.goYears), R.hint);
  /* each case chip carries what it tests (a short tag under the name), so the jury sees all four cases at once */
  R.chips = INVESTORS.map(([id, label]) => { const c = caseLine(id);
    return h("button", { class: "chip hx-chip" + (c ? " hx-chip-case" : ""), type: "button", "data-id": id, "aria-pressed": "false" },
      h("span", { class: "hx-chip-txt" }, h("span", { class: "hx-chip-name", text: label }), c ? h("span", { class: "hx-chip-tag", text: c.tag }) : null)); });
  R.who = h("div", { class: "hx-who", role: "group", "aria-label": "Investor" }, ...R.chips);
  R.you = h("div", { class: "hx-you", hidden: true });   // lane profile-ui: "You" describes yourself (sections/you.js mounts it)
  R.case = h("p", { class: "hx-case", id: "hx-case", "aria-live": "polite" });   // what this case tests, in one sentence
  R.persona = h("p", { class: "hx-persona" });
  R.lims = h("p", { class: "hx-lims" });           // the limits, one quiet line (the lead 19:10)
  R.note = h("p", { class: "hx-note" });
  /* R41 (the controller, from the lead's words): the headline, one sub-line under it, the French line small under that. One line
     across the frame on a desktop, so the three steps and Replay fit the first screen; "Crash-test" never breaks at its hyphen */
  R.title = h("h1", { class: "hx-title", id: "hero-title" }, h("span", { class: "hx-nb", text: "Crash-test" }), " your move before you make it.");
  R.sub = h("p", { class: "hx-sub" }, "See whether it would have stayed inside your own limits, replayed through real ",
    h("span", { class: "hx-nb", text: "2021\u201326" }), " market shocks.");
  /* R19 (c), R41: the French line, its own line, marked as French; guillemets with no-break spaces */
  R.fr = h("p", { class: "hx-fr", lang: "fr", text: "\u00ab\u00a0Passez votre placement au crash-test avant d\u2019agir.\u00a0\u00bb" });
  R.hold = h("div", { class: "hx-hold" });          // lane hold: what the investor holds (sections/hold.js mounts it)
  R.head = h("div", { class: "hx-head" }, R.title, R.sub, R.fr, h("p", { class: "hx-stack", text: STACK_LINE }));   // where it fits, what runs it
  R.copy = h("div", { class: "hx-copy" }, R.who, R.you, R.case, R.persona, R.lims, R.hold, R.form, R.note);   // step 1 (holdings) before 2 (the question)
  R.legendLead = h("span", { class: "hx-legend-lead" }); R.legendRing = h("span", { class: "hx-legend-ring" });
  R.capName = h("span", { class: "hx-cap-name" }); R.capCount = h("span", { class: "hx-cap-count" });
  R.caption = h("p", { class: "hx-caption", "aria-live": "polite" }, h("span", { class: "hx-cap-dot", "aria-hidden": "true" }), R.capName, R.capCount);
  R.legendPast = h("p", { class: "hx-legend-past" });
  R.counterN = h("span", { class: "fig hx-counter-n" }); R.counterRest = h("span", { class: "hx-counter-rest" });
  R.counter = h("p", { class: "hx-counter is-empty", "aria-hidden": "true" }, R.counterN, R.counterRest);
  R.legend = h("div", { class: "hx-legend" }, h("p", { class: "hx-legend-lead" }, R.legendLead),
    h("p", { class: "hx-legend-key" }, ringKey(), R.legendRing), R.legendPast);
  R.summary = h("p", { class: "sr", id: "hx-summary" });
  /* polish-hero (R41): the globe is an instrument in the right half: its counter on top, the disc (the slot the canvas follows)
     with its caption, the key under it. The words: the headline across the frame, then the three steps in the left half */
  R.orb = h("div", { class: "hx-orb" }, R.slot, R.caption);
  R.instr = h("div", { class: "hx-instr" }, R.counter, R.orb, R.legend);
  R.grid = h("div", { class: "hx-grid" }, R.head, R.copy, R.instr);
  return R;
}

/* a step's number: the ring is drawn by css/movepicker.css (.step-n), the words say "Step n" to a screen reader */
const stepN = (n) => [h("span", { class: "step-n", "aria-hidden": "true", text: String(n) }), h("span", { class: "sr", text: `Step ${n}: ` })];
const nameOf = (id) => (INVESTORS.find(([k]) => k === id) || [])[1] || null;
/* ② and ③ and the button's words: the investor's name, whether the box names a move, the run's own years */
function relabel(R, st) {
  const name = nameOf(st.investor), moved = namesMove(R.q.value, st.result);
  R.askT.textContent = askLabel(name, moved);
  R.goText.textContent = goLabel(name, moved);
  R.goYears.textContent = throughWords(st.result);
}

/* the command bar grows with the words where CSS field-sizing is not supported (Safari) */
const FIELD_SIZING = typeof CSS !== "undefined" && CSS.supports && CSS.supports("field-sizing", "content");
function fitQ(q) {
  if (FIELD_SIZING || !q.isConnected) return;
  q.style.height = "auto"; q.style.height = `${q.scrollHeight + q.offsetHeight - q.clientHeight}px`;   // border-box: add the hairline
}

/* the words of this run (no verdict in the hero) */
function renderText(R, st) {
  const r = st.result, v = st.view;
  const live = st.mode === "live";
  for (const c of R.chips) c.setAttribute("aria-pressed", String(c.dataset.id === st.investor));
  const kase = caseLine(st.investor); R.case.textContent = kase ? kase.tests : ""; R.case.hidden = !kase;
  /* the run's own words; a figure keeps its unit on one line ("40 %", never "40 / %"); the space goes back on submit */
  if (!R.edited && r && typeof r.question === "string") { R.q.value = r.question.replace(/(\d) (?=%)/g, "$1\u00a0"); fitQ(R.q); }
  R.q.readOnly = !live;
  R.hint.textContent = live ? "Edit the words, then press Enter or Replay." : "A saved replay keeps the investor’s own words. The live version reads yours.";
  const c = heroCopy(r, v), p = c.persona, l = c.legend, cap = c.cap;
  segsTo(R.persona, p ? [...p.who, ...(c.aim ? [[` ${c.aim}`]] : [])] : null); R.persona.hidden = !p;   // + the objective (G3)
  segsTo(R.lims, p && p.limits.length ? p.limits : null); R.lims.hidden = !(p && p.limits.length);
  R.note.textContent = p ? p.note : PERSONA_NOTE;
  R.legendLead.textContent = l.lead; R.legendRing.textContent = l.ring; R.legendPast.textContent = l.past;
  R.caption.hidden = !cap;
  R.capName.textContent = cap ? cap.label : ""; R.capCount.textContent = cap && cap.count ? cap.count : "";
  R.caption.classList.toggle("is-none", !!(cap && cap.none));
  relabel(R, st);
  for (const fn of R.textFns) fn();
  const full = c.counter;
  R.summary.textContent = [`Night Earth. ${full ? full.n + full.rest + "." : ""} ${l.lead}`,
    cap && cap.none ? `${cap.label} ${cap.count}.` : cap ? `${cap.label}${cap.count ? `, ${cap.count}` : ""}: its epicentres are lit, the others dimmed.` : "", l.ring, l.past]
    .filter(Boolean).join(" ");
}

/* ---- no WebGL: the night Earth in 2D from the globe's own camera (lib unproject), at any turn; the poster JPEG for the home view ---- */
const TEX2D = new URL("../vendor/nasa/black-marble-2016-2048.jpg", import.meta.url).href;
let texPromise = null;
function texture2d() {                     // the flat night map's pixels, once (same origin; a tainted canvas rejects: the poster stays)
  if (!texPromise) texPromise = new Promise((res, rej) => {
    const im = new Image(); im.decoding = "async";
    im.onload = () => { try {
      const c = document.createElement("canvas"); c.width = im.naturalWidth; c.height = im.naturalHeight;
      const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(im, 0, 0);
      res({ w: c.width, h: c.height, d: x.getImageData(0, 0, c.width, c.height).data });
    } catch (e) { rej(e); } };
    im.onerror = rej; im.src = TEX2D;
  });
  return texPromise;
}
const LIN = Float32Array.from({ length: 256 }, (_, i) => Math.pow(i / 255, 2.2));
const ENC = Uint8ClampedArray.from({ length: 4096 }, (_, i) => Math.round(255 * Math.pow(i / 4095, 1 / 2.2)));
const enc = (v) => ENC[v >= 1 ? 4095 : v <= 0 ? 0 : (v * 4095) | 0];
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
/* the disc of radius rCss (CSS px) and its glow, on a canvas 1.1 × 2r wide: the same city and rim terms as globe.js's shader */
async function drawEarth2d(canvas, view, rCss) {
  const T = await texture2d(), dpr = Math.min(window.devicePixelRatio || 1, 1.5), r = Math.max(8, rCss * dpr), half = Math.ceil(r * 1.1);
  const n = half * 2; canvas.width = canvas.height = n;
  const ctx = canvas.getContext("2d"), img = ctx.createImageData(n, n), o = img.data;
  for (let py = 0; py < n; py++) for (let px = 0; px < n; px++) {
    const sx = (px + 0.5 - half) / r, sy = (py + 0.5 - half) / r, rho2 = sx * sx + sy * sy, i = (py * n + px) * 4;
    if (rho2 <= 1) {
      const q = unproject(sx, sy, view); if (!q) continue;
      const tx = Math.min(T.w - 1, ((q.lon + 180) / 360 * T.w) | 0), ty = Math.min(T.h - 1, Math.max(0, ((90 - q.lat) / 180 * T.h) | 0)), j = (ty * T.w + tx) * 4;
      const cr = LIN[T.d[j]], cg = LIN[T.d[j + 1]], cb = LIN[T.d[j + 2]], m = smooth(0.06, 0.38, 0.299 * cr + 0.587 * cg + 0.114 * cb);
      const f = Math.pow(1 - Math.max(q.facing, 0), 4) * 0.58;
      o[i] = enc(cr * (0.40 + m * (2.438 - 0.40)) + 0.16 * f); o[i + 1] = enc(cg * (0.40 + m * (2.208 - 0.40)) + 0.36 * f);
      o[i + 2] = enc(cb * (0.40 + m * (1.886 - 0.40)) + f); o[i + 3] = 255;
    } else if (rho2 < 1.1) {                                             // the thin rim just past the limb (globe.js's shell)
      const a = Math.pow(1 - smooth(1.0, 1.045, Math.sqrt(rho2)), 1.6) * 0.62;
      o[i] = 77; o[i + 1] = 140; o[i + 2] = 255; o[i + 3] = Math.round(255 * a);
    }
  }
  ctx.putImageData(img, 0, 0);
}
/* each shock's light and ring on a disc seen from `view` (an svg with viewBox -1 -1 2 2 over the disc), where globe.js draws them */
function ringsInto(svg, st, view) {
  svg.replaceChildren();
  const v = st.view, fam = st.result ? askedFamily(st.result) : null, gp = PF() && PF().globeProject;
  if (!v || !gp) return;
  for (const e of shocksOf(v)) {
    const p = gp(e.lat, e.lon, { tilt: view.lat, lon0: view.lon });
    if (!p.visible) continue;
    const dim = fam && e.family !== fam ? " is-dim" : "", rr = ringRadius(e.trough), k = Math.sqrt(35) / (6 - p.z);
    if (rr) svg.append(s("circle", { class: "hx-r" + dim, cx: p.x.toFixed(4), cy: p.y.toFixed(4), r: (rr * k).toFixed(4) }));
    svg.append(s("circle", { class: "hx-c" + dim, cx: p.x.toFixed(4), cy: p.y.toFixed(4), r: 0.008 }));
  }
}
/* no WebGL in the hero: the poster (home view) or the 2D Earth turned to the asked shock, with its lights and rings */
function drawRings(R, st) {
  const v = st.view, hv = v && st.result ? heroView(worstPrecedent(v, askedFamily(st.result))) : HOME;
  const home = hv.lat === HOME.lat && hv.lon === HOME.lon;
  if (R.poster.getAttribute("src") !== POSTER) R.poster.src = POSTER;        // no sweep without WebGL: the hero's own view
  R.slot.classList.toggle("is-turned", !home);
  if (!home) {
    if (!R.poster2d) { R.poster2d = h("canvas", { class: "hx-poster2d", "aria-hidden": "true" }); R.slot.prepend(R.poster2d); }
    drawEarth2d(R.poster2d, hv, R.slot.getBoundingClientRect().width / 2)
      .catch(() => { R.slot.classList.remove("is-turned"); ringsInto(R.rings, st, HOME); });   // no pixels (file://): the poster
  }
  ringsInto(R.rings, st, home ? HOME : hv);
}

const reduceMQ = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : { matches: false, addEventListener() {} };
const still = () => reduceMQ.matches || globalThis.EPI_MOTION === false || document.documentElement.classList.contains("motion-off") ||
  document.body.classList.contains("motion-paused");

export function mount(el, store) {
  const R = build();
  el.classList.add("hx");
  if (!el.hasAttribute("aria-labelledby")) el.setAttribute("aria-labelledby", "hero-title");
  el.replaceChildren(R.canvas, R.grid, R.summary);
  R.poster.src = still() ? POSTER : POSTER_SWEEP;      // the first paint is the first frame of what follows
  if (!still()) { const home = new Image(); home.decoding = "async"; home.src = POSTER; }   // the hero's own view, ready for a lost context
  let G = null, ignited = false, raf = 0;
  const fit = () => fitQ(R.q);

  /* ---- the frames the globe draws in, in CSS px of the viewport ---- */
  const replayEl = () => document.getElementById("replay");
  function region() {       // where the globe may show: from the hero's top to the end of the #replay stage (the hero alone without one)
    const hb = el.getBoundingClientRect(), r = replayEl(), sb = r ? stickyBox(r.getBoundingClientRect(), innerHeight) : null;
    return { top: hb.top, bottom: sb ? Math.max(sb.bottom, hb.bottom) : hb.bottom };
  }
  function heroBox() {
    const b = R.slot.getBoundingClientRect(), hb = el.getBoundingClientRect(), vh = innerHeight;
    if (!(b.width > 0)) return null;
    const natural = { cx: b.left + b.width / 2, cy: b.top + b.height / 2, r: b.width / 2 };
    /* phones: the globe scrolls with the hero, then travels into the stage's slot as the hero leaves (the reader is there) */
    if (innerWidth <= 760) {
      const sf = stageBox(), t = Math.min(1, Math.max(0, (vh * 0.5 - hb.bottom) / (vh * 0.5)));
      return sf && t > 0 ? mixFrame(natural, sf, easeInOut(t)) : natural;
    }
    /* desktop: held in place while the page scrolls from the hero to the stage, then lifted with the stage as it leaves */
    const reg = region(), lift = reg ? Math.max(0, vh - reg.bottom) : 0;
    return { cx: natural.cx, cy: natural.cy - Math.min(0, hb.top) - lift, r: natural.r };
  }
  function stageBox() {
    const r = replayEl(); if (!r) return null;
    const slot = r.querySelector("[data-globe-slot]");
    return slot ? stageFrame(slot.getBoundingClientRect(), true) : stageFrame(stickyBox(r.getBoundingClientRect(), innerHeight), false);
  }

  /* ---- scroll and resize: one rAF; the canvas is clipped to the region and sleeps once the region has gone ---- */
  /* motion QA (17:40): every read first (the region, the hero's and the stage's boxes), then the writes, and a style written
     only when it changes (no forced style recalc and no re-layerized canvas on each scroll frame) */
  let lastVis = null, lastClip = null;
  function sync() {
    raf = 0;
    const reg = region(), vh = innerHeight, gone = !reg || reg.bottom <= 0 || reg.top >= vh;
    const hb = el.getBoundingClientRect(), rEl = replayEl(), rb = rEl ? rEl.getBoundingClientRect() : null;
    const vis = gone ? "hidden" : "", clip = reg && reg.bottom < vh ? `inset(0 0 ${Math.ceil(vh - reg.bottom)}px 0)` : "";
    if (vis !== lastVis) { lastVis = vis; R.canvas.style.visibility = vis; }
    if (clip !== lastClip) { lastClip = clip; R.canvas.style.clipPath = clip; }
    if (G) { G.setActive(!gone && !document.hidden); G.requestRender(); autoLayout(hb, rb); }
    if (lastW !== innerWidth) { lastW = innerWidth; fit(); }
  }
  let lastW = 0;
  const schedule = () => { if (!raf) raf = requestAnimationFrame(sync); };
  addEventListener("scroll", schedule, { passive: true });
  addEventListener("resize", schedule);
  document.addEventListener("visibilitychange", schedule);

  /* the investor's view: the lead's composition, or a turn to the asked shock when it is out of view from there */
  const st = () => store.get();
  const worstNow = () => { const s0 = st(); return s0.view && s0.result ? worstPrecedent(s0.view, askedFamily(s0.result)) : null; };
  /* when the reader scrolls back to the hero after a replay landed, the globe returns to the hero; and to the stage again */
  function autoLayout(hb0, rb0) {          // hb0 / rb0: the boxes sync() has just read (else read here)
    const phase = st().phase;
    if (!G || !G.ready || (phase && phase !== "idle" && phase !== "landed")) return;
    const hb = hb0 || el.getBoundingClientRect(), heroShown = hb.bottom > innerHeight * 0.5;
    const r = replayEl(), rb = rb0 || (r && r.getBoundingClientRect());
    const stageShown = r && phase === "landed" && rb.top <= innerHeight * 0.5 && !heroShown;
    if (heroShown && G.layout === "stage") G.setLayout("hero", 700);
    else if (stageShown && G.layout === "hero") G.setLayout("stage", 700);
  }

  /* ---- no WebGL: an Earth card in the stage's slot from the stage's first frame, centred on the asked shock (the docked
     globe's view); lane U2 docks onto it. Its epicentre point for U2's thread: data-x / data-y and --x / --y, px in the card ---- */
  let card = null, cardKey = "", cardMO = null, cardT = 0;
  function stageCard() {
    if (!el.classList.contains("no-webgl")) { if (card) { card.remove(); card = null; cardKey = ""; } return; }
    const r = replayEl(), slot = r && r.querySelector("[data-globe-slot]");
    if (!slot) {
      if (r && !cardMO) { cardMO = new MutationObserver(() => { if (r.querySelector("[data-globe-slot]")) { cardMO.disconnect(); cardMO = null; stageCard(); } });
        cardMO.observe(r, { childList: true, subtree: true }); }
      return;
    }
    if (!card || !slot.contains(card)) {
      card = h("div", { class: "hx-stage-card", "aria-hidden": "true" }, h("canvas", { class: "hx-stage-earth" }), s("svg", { class: "hx-stage-rings", viewBox: "-1 -1 2 2" }));
      slot.prepend(card); cardKey = "";
    }
    const b = slot.getBoundingClientRect(), d = Math.round(0.9 * Math.min(b.width, b.height));
    const s0 = st(), w = s0.view && s0.result ? worstPrecedent(s0.view, askedFamily(s0.result)) : null, view = w ? { lat: w.lat, lon: w.lon } : HOME;
    const key = `${d}|${view.lat},${view.lon}|${s0.result ? s0.result.run_id : ""}`;
    if (key === cardKey || d < 40) return;
    cardKey = key;
    card.style.setProperty("--d", `${d}px`);
    if (w) { card.dataset.x = card.dataset.y = String(d / 2); card.style.setProperty("--x", `${d / 2}px`); card.style.setProperty("--y", `${d / 2}px`); }
    else { delete card.dataset.x; delete card.dataset.y; }
    ringsInto(card.lastChild, s0, view);
    drawEarth2d(card.firstChild, view, d / 2).catch(() => { /* no pixels (file://): the card keeps its lights and rings */ });
  }
  addEventListener("resize", () => { clearTimeout(cardT); cardT = setTimeout(stageCard, 200); });

  async function startGlobe() {
    let gl = null;      // the one WebGL context, asked for here first: without it the poster stays and three.js is never fetched
    try { gl = R.canvas.getContext("webgl2", { antialias: true, alpha: true, premultipliedAlpha: true, depth: true, stencil: false,
      powerPreference: "default", failIfMajorPerformanceCaveat: true }); } catch (e) { gl = null; }
    if (!gl) { el.classList.add("no-webgl"); drawRings(R, st()); stageCard(); setCounter(Infinity); return; }
    let mod = null;
    try { mod = await import("../globe.js"); } catch (e) { mod = null; }
    const s0 = st(), hv0 = heroView(worstNow());   /* the first light is the sweep poster's view (any investor); still: the end view */
    G = mod && mod.createGlobe(R.canvas, { context: gl, events: shocksOf(s0.view), view: still() ? hv0 : SWEEP_FROM, still,
      onIgnite: (n) => setCounter(n),
      frames: { hero: heroBox, stage: stageBox }, tierWidth: Math.min(innerWidth, innerHeight * 1.6),
      onReady() { el.classList.add("is-lit"); ignite(); },
      /* back in the hero (by anyone, the stage included) outside a replay: the hero's own turn again */
      onLayout(name, ms) { const ph = st().phase; if (name === "hero" && G && (!ph || ph === "idle" || ph === "landed")) { const hv = heroView(worstNow()); G.turnTo(hv.lat, hv.lon, ms || 0); } },
      onLost(isLost) { el.classList.toggle("no-webgl", !!isLost); if (isLost) drawRings(R, st()); stageCard(); } });
    if (!G) { el.classList.add("no-webgl"); drawRings(R, st()); stageCard(); setCounter(Infinity); return; }
    G.focusFamily(null, 0);
    store.set({ globe: G });
    sync();
  }
  function ignite() {
    if (ignited || !G) return; ignited = true;
    const go = () => {
      const s0 = st(), fam = s0.result ? askedFamily(s0.result) : null, hv = heroView(worstNow());
      /* the first five seconds: the Earth sweeps east to west while the shocks light in date order, then rests on this view */
      if (G.layout === "hero") { const sw = sweepPath(hv); G.sweep(sw.from, sw.to, still() ? 0 : SWEEP_MS); }
      G.igniteAll(ignitionOrder(shocksOf(s0.view)), IGNITE_MS).then(() => {   // the focus of the run on screen by then
        G.focusFamily(st().result ? askedFamily(st().result) : fam); el.classList.add("is-focused"); });
    };
    if (still()) go(); else setTimeout(go, 450);        // after the poster has crossfaded into the first frame
  }
  /* the counter rises in step with the lights, "1 shock on record" to "37 shocks on record" (the Result's own count) */
  function setCounter(n) {
    const v = st().view, sh = v && v.shocks;
    const ct = sh && n > 0 ? counterText(Math.min(n, sh.n)) : null;
    if (!ct) { R.counter.classList.add("is-empty"); return; }
    if (R.counterN.textContent !== ct.n) { R.counterN.textContent = ct.n; R.counterRest.textContent = ct.rest; }
    R.counter.classList.remove("is-empty");
  }
  /* ---- the reader's controls ---- */
  for (const c of R.chips) c.addEventListener("click", () => {
    if (c.dataset.id === st().investor) return;
    R.edited = false;
    for (const x of R.chips) x.setAttribute("aria-pressed", String(x === c));
    store.set({ investor: c.dataset.id });
  });
  R.q.addEventListener("input", () => { R.edited = true; fit(); relabel(R, st()); for (const fn of R.textFns) fn(); });
  R.q.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); R.form.requestSubmit(); } });
  R.form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = R.q.value.replace(/\u00a0/g, " ").trim() || (st().result && st().result.question) || "";
    store.set({ question: q, replay: Date.now() });
  });
  /* lane picker: "Try another move" under the question (its own module in R.pick; the hero works without it). The box stays the
     single source: the picker writes into it or reads it back, never around it */
  /* a new move from the picker: its words settle in, and one ring eases out of the Replay pill (step ③ is next) */
  const settle = () => {
    for (const [n, c] of [[R.q, "is-new"], [R.go, "is-armed"]]) { n.classList.remove(c); void n.offsetWidth; n.classList.add(c); }
  };
  const pickApi = {
    text: () => R.q.value,
    write(q) { R.q.value = String(q).replace(/(\d) (?=%)/g, "$1\u00a0"); R.edited = true; fit(); settle(); relabel(R, st()); for (const fn of R.textFns) fn(); },
    follow(cue) { R.edited = false; renderText(R, st()); if (cue) settle(); },   // cue: the picker put a saved move on screen
    name: nameOf,
    onText(fn) { if (typeof fn === "function") R.textFns.push(fn); },
  };
  import("./movepicker.js").then((m) => m.mountPicker(R.pick, store, pickApi))
    .catch((e) => { R.pick.hidden = true; console.warn("[hero] the move picker is not available:", e && e.message); });

  /* ---- the store ---- */
  let lastResult = null;
  let swapT = 0;
  function onRun() {
    const s0 = st();
    /* another run: the caption dips out and back while the globe turns to it (an instant swap under reduced motion) */
    const changed = s0.result !== lastResult;
    if (changed && lastResult !== null && !still() && el.classList.contains("is-focused")) {
      el.classList.add("is-swapping"); clearTimeout(swapT);
      swapT = setTimeout(() => { renderText(R, st()); el.classList.remove("is-swapping"); }, 140);
    } else if (!el.classList.contains("is-swapping")) renderText(R, s0);
    if (!changed) return;
    const first = lastResult === null; lastResult = s0.result;
    if (el.classList.contains("no-webgl")) { drawRings(R, s0); stageCard(); }
    if (!G) return;
    const fam = s0.result ? askedFamily(s0.result) : null;
    G.setEvents(shocksOf(s0.view));
    if (!first && ignited) G.focusFamily(fam);
    if (!first && G.layout === "hero") { const hv = heroView(worstNow()); G.turnTo(hv.lat, hv.lon, 900); }
    else if (!first && !fam) G.turnTo(HOME_MARKET.lat, HOME_MARKET.lon, 900);    // the stage: no shock named, the home market
    if (G && ignited && el.classList.contains("is-focused")) setCounter(Infinity);
  }
  store.on("result", onRun); store.on("view", onRun); store.on("mode", () => renderText(R, st()));
  /* the store's question is the command bar's words (INTERFACES.md): words another section sends there (a saved run landing,
     the judge's cards, the picker) show in the box; the hero's own submit sends the box's words, so it never echoes */
  store.on("question", (q) => {
    if (typeof q !== "string" || !q.trim() || q.replace(/\u00a0/g, " ").trim() === R.q.value.replace(/\u00a0/g, " ").trim()) return;
    R.q.value = q.replace(/(\d) (?=%)/g, "$1\u00a0"); R.edited = true; fit(); relabel(R, st()); for (const fn of R.textFns) fn();
  });
  store.on("investor", () => {
    R.edited = false;                             // another investor (any path: chips, cards, keys): the box shows that run's words
    for (const c of R.chips) c.setAttribute("aria-pressed", String(c.dataset.id === st().investor));
    relabel(R, st());                             // ② and ③ name the investor at once ("in your words" for You, lane profile-ui)
  });
  /* while the stage reads the question, the big globe behind it steps back; the EPICENTRE zoom brings it to full light */
  store.on("phase", (ph) => { el.classList.toggle("is-reading", ph === "reading" && !!G && G.layout === "hero"); schedule(); });
  /* motion turned off mid-way (Pause motion, reduced motion, EPI_MOTION): every light at rest at once, the focus set */
  let wasStill = still();
  const onMotion = () => {
    const now = still(); if (now === wasStill) return; wasStill = now;
    if (G && now) {
      G.igniteAll(ignitionOrder(shocksOf(st().view)), 0); G.focusFamily(st().result ? askedFamily(st().result) : null, 0); el.classList.add("is-focused");
      if (G.layout === "hero") { const hv = heroView(worstNow()); G.turnTo(hv.lat, hv.lon, 0); }   // the first-five-second turn ends at once too
    }
  };
  for (const n of [document.body, document.documentElement]) new MutationObserver(onMotion).observe(n, { attributes: true, attributeFilter: ["class"] });
  if (reduceMQ.addEventListener) reduceMQ.addEventListener("change", onMotion);
  renderText(R, st()); lastResult = st().result || null; requestAnimationFrame(fit);
  /* lane profile-ui: the fifth chip's box and card, "You" (its own module; the hero works without it) */
  import("./you.js").then((m) => m.mountYou(R.you, store))
    .catch((e) => { R.you.hidden = true; console.warn("[hero] the You card is not available:", e && e.message); });
  /* lane hold: the holdings list under the picker (its own module; the hero works without it) */
  import("./hold.js").then((m) => m.mountHoldings(R.hold, store))
    .catch((e) => { R.hold.hidden = true; console.warn("[hero] the holdings list is not available:", e && e.message); });

  /* three.js and the textures load after first paint, behind the poster */
  requestAnimationFrame(() => setTimeout(startGlobe, 30));
}
