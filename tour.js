/* EPICENTRE Replay: "Take the tour" (ruling R22, lane U0; about 45 s). One button after the hero's Replay (and presenter key T)
   plays the page like a keynote: it presses Replay, follows the stage to its end frame, then glides section by section (the
   stage, money, deep, scenario, investors, how, record; only the sections on this page) with ONE caption line at the bottom,
   about 5 s a stop. Any key, wheel, touch or click stops it; Esc ends it. Reduced motion or paused motion: no auto-scroll,
   the captions only. One rAF loop for the glide; the captions are plain sentences (true for any investor), no meta dots. */

const PAUSE_MS = 5000;
const GLIDE_MS = 900;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

const broke = (r) => !!(r && Array.isArray(r.breaches) && r.breaches.length);
export const STOPS = [
  { id: "replay", phase: "reading", text: () => "The AI reads the question" },
  { id: "replay", phase: "flying", text: (r) => (broke(r) ? "The shock flies home and breaks your floor" : "The shock flies home and meets your floor") },
  { id: "why", text: () => "Why this answer: every number traced to the data" },
  { id: "money", text: () => "Where the money sits, and where the risk sits" },
  { id: "investors", text: () => "A different check decides each answer" },
  { id: "how", text: () => "What the AI did, and what code checked" },
  { id: "deep", text: () => "Not just 2022: earlier crises, by stand-in" },
  { id: "scenario", text: () => "Build your own shock: a scenario, not a forecast" },
  { id: "record", text: () => "The record you keep, sealed" },
];

/* the stops of this page: a section that is mounted and shown (a folded or flagged-off one is skipped) */
export function stopsOn(doc) {
  return STOPS.filter((s) => {
    const el = doc.getElementById(s.id);
    return !!el && el.dataset.mount === "ready" && el.getClientRects().length > 0;
  });
}

export function createTour(store, { motionOn }) {
  let run = 0;                                     // a newer start or any stop invalidates the running tour
  const cap = document.createElement("p");
  cap.className = "tour-cap";
  cap.setAttribute("role", "status");
  cap.setAttribute("aria-live", "polite");
  cap.hidden = true;
  const num = document.createElement("span");
  num.className = "tour-n";
  const words = document.createElement("span");
  words.className = "tour-t";
  cap.append(num, words);
  document.body.append(cap);

  const show = (i, total, stop) => {
    num.textContent = `${i}/${total}`;
    words.textContent = stop.text(store.get().result);
    cap.hidden = false;
  };

  const interrupt = (e) => { if (e.type !== "keydown" || !e.repeat) stop(); };
  const listen = (on) => {
    for (const type of ["keydown", "wheel", "touchmove", "pointerdown"]) {
      if (on) window.addEventListener(type, interrupt, { capture: true, passive: true });
      else window.removeEventListener(type, interrupt, { capture: true });
    }
  };

  function stop() {
    run += 1;
    listen(false);
    cap.hidden = true;
    document.documentElement.classList.remove("is-touring");
  }

  const phaseIs = (...names) => names.includes(store.get().phase);
  async function until(test, ms, me) {
    const t0 = performance.now();
    while (!test()) { if (me !== run || performance.now() - t0 > ms) return false; await sleep(100); }
    return me === run;
  }

  function glide(el, me) {                          // one rAF loop, ease-in-out, from here to the section's top under the bar
    const bar = parseFloat(getComputedStyle(el).scrollMarginTop) || parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--bar")) || 0;
    const from = window.scrollY, to = Math.max(0, el.getBoundingClientRect().top + window.scrollY - bar);   // lands where an anchor would
    if (!motionOn()) return Promise.resolve();      // reduced or paused motion: no auto-scroll, the captions only
    return new Promise((done) => {
      const t0 = performance.now();
      const frame = (now) => {
        if (me !== run) return done();
        const p = Math.min(1, (now - t0) / GLIDE_MS);
        window.scrollTo(0, from + (to - from) * easeInOut(p));
        if (p < 1) requestAnimationFrame(frame); else done();
      };
      requestAnimationFrame(frame);
    });
  }

  async function start() {
    stop();
    const me = run;
    const stops = stopsOn(document);
    if (!stops.length) return;
    document.documentElement.classList.add("is-touring");
    setTimeout(() => { if (me === run) listen(true); }, 0);     // the press that started it is not an interruption
    const total = stops.length;
    let i = 0;
    if (stops[0].id === "replay") {
      store.set({ replay: Date.now() });                          // the stage scrolls itself into view and plays
      show(++i, total, stops[0]);
      await until(() => phaseIs("reading", "flying", "racing"), 4000, me);   // it has begun (reduced motion lands at once)
      if (me !== run) return;
      await until(() => phaseIs("flying", "racing", "landed"), 9000, me);
      if (me !== run) return;
      if (stops[1] && stops[1].id === "replay") show(++i, total, stops[1]);
      await until(() => phaseIs("landed"), 12000, me);
      if (me !== run) return;
      await sleep(PAUSE_MS);
    }
    for (const s of stops.slice(i)) {
      if (me !== run) return;
      await glide(document.getElementById(s.id), me);
      if (me !== run) return;
      show(++i, total, s);
      await sleep(PAUSE_MS);
    }
    if (me === run) stop();
  }

  return { start, stop, get running() { return document.documentElement.classList.contains("is-touring"); } };
}

/* a quiet text button on its own line under the hero's command bar (lane U1's form; Replay stays the one primary button and
   the question keeps its width); a page without the hero gets none */
export function mountTourButton(tour) {
  const form = document.querySelector("#hero .hx-ask") || document.querySelector("#hero .hx-go");
  if (!form) return null;
  const SVG = "http://www.w3.org/2000/svg";
  const b = document.createElement("button");
  b.type = "button";
  b.className = "linkbtn tour-btn";
  const icon = document.createElementNS(SVG, "svg");
  icon.setAttribute("class", "icon");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", "#i-play");
  icon.append(use);
  b.append(icon, document.createTextNode("Take the tour"));
  b.addEventListener("click", () => tour.start());
  form.after(b);
  return b;
}
