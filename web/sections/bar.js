/* EPICENTRE Replay, lane U7: #bar, the top bar (design doc §2 item 0). The wordmark, the section anchors (only those whose
   section is on the page and drew something), "Data to <as_of>" from the Result, and an unboxed 16 px pause-motion glyph:
   pressing it sets window.EPI_MOTION = false (app.js turns that into html.motion-off), body.motion-paused, and sends
   "epi:motion" ({detail: {on}}) so every lane's script-driven motion stops too. DOM from createElement/textContent (R16). */
import * as H from "../lib/how.js";

const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs, ...kids) {
  const svg = tag.startsWith("svg:");
  const el = svg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const icon = (id, cls) => h("svg:svg", { class: cls || "icon", "aria-hidden": "true", focusable: "false" }, h("svg:use", { href: `#${id}` }));

/* the mark: an epicentre (a core and one ring), drawn, never a glyph */
const mark = () => h("svg:svg", { class: "bar-mark", viewBox: "0 0 16 16", "aria-hidden": "true", focusable: "false" },
  h("svg:circle", { cx: "8", cy: "8", r: "2.6", fill: "currentColor" }),
  h("svg:circle", { cx: "8", cy: "8", r: "6.4", fill: "none", stroke: "var(--signal)", "stroke-width": "1" }));

const motionOn = () => window.EPI_MOTION !== false;

export function mount(el, store) {
  el.classList.add("bar");
  const links = H.NAV.map((n) => h("a", { class: "bar-link", href: `#${n.id}`, "data-target": n.id, text: n.label }));
  const items = links.map((a) => h("li", {}, a));
  const date = h("p", { class: "bar-data", hidden: true });
  const glyph = icon("i-pause", "bar-glyph");
  const pause = h("button", { class: "bar-motion", type: "button", "aria-pressed": "false", "aria-label": "Pause motion", title: "Pause motion" }, glyph);
  el.replaceChildren(h("div", { class: "bar-in" },
    h("a", { class: "bar-brand", href: "#main", "aria-label": "EPICENTRE, to the top of the page" }, mark(), h("span", { class: "bar-word", text: "EPICENTRE" })),
    h("nav", { class: "bar-nav", "aria-label": "Sections" }, h("ul", { class: "bar-list" }, items)),
    h("div", { class: "bar-end" }, date, pause)));

  /* ---- the motion glyph ---- */
  const paint = () => {
    const on = motionOn();
    pause.setAttribute("aria-pressed", String(!on));
    pause.title = on ? "Pause motion" : "Motion paused: press to play";
    glyph.firstChild.setAttribute("href", on ? "#i-pause" : "#i-play");
  };
  const setMotion = (on) => {
    try { window.EPI_MOTION = on; } catch (e) { /* a page without app.js's setter */ }
    document.documentElement.classList.toggle("motion-off", !on);
    document.body.classList.toggle("motion-paused", !on);
    try { window.dispatchEvent(new CustomEvent("epi:motion", { detail: { on } })); } catch (e) { /* no CustomEvent */ }
    paint();
  };
  pause.addEventListener("click", () => setMotion(!motionOn()));
  if (!motionOn()) document.body.classList.add("motion-paused");
  paint();

  /* ---- "Data to 12 Nov 2026", from the Result on screen ---- */
  /* phones show "To 12 Nov 2026" (nothing clips at 360 px); a screen reader always hears the long form */
  const drawDate = (r) => {
    const t = H.dataTo(r), short = H.dataToShort(r);
    date.replaceChildren(...(t ? [h("span", { class: "bar-data-long", text: t }), h("span", { class: "bar-data-short", "aria-hidden": "true", text: short })] : []));
    date.hidden = !t;
  };
  store.on("result", drawDate);
  drawDate(store.get().result);

  /* ---- anchors: hidden while their section is missing, failed or empty (no link into nothing) ---- */
  const targets = () => links.map((a) => [a, document.getElementById(a.dataset.target)]);
  let queued = false;
  const refresh = () => {
    queued = false;
    for (const [a, t] of targets()) {
      const m = t && t.dataset.mount;
      a.parentElement.hidden = !t || m === "missing" || m === "failed" || (m === "ready" && t.offsetHeight < 8);
    }
  };
  const later = () => { if (!queued) { queued = true; requestAnimationFrame(refresh); } };
  const mo = typeof MutationObserver === "function" ? new MutationObserver(later) : null;
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(later) : null;
  for (const [, t] of targets()) if (t) { if (mo) mo.observe(t, { attributes: true, attributeFilter: ["data-mount"] }); if (ro) ro.observe(t); }
  later();

  /* ---- the section in view is the current anchor (the band across the middle of the viewport) ---- */
  if (typeof IntersectionObserver === "function") {
    const inView = new Set();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) (e.isIntersecting ? inView.add(e.target.id) : inView.delete(e.target.id));
      const cur = H.NAV.map((n) => n.id).filter((id) => inView.has(id)).pop() || null;
      for (const a of links) (a.dataset.target === cur ? a.setAttribute("aria-current", "true") : a.removeAttribute("aria-current"));
    }, { rootMargin: "-45% 0px -50% 0px" });
    for (const [, t] of targets()) if (t) io.observe(t);
  }

  /* ---- over the hero the bar is bare; once the page moves it takes a veil and a hairline ---- */
  let ticking = false;
  let y = 0;                                         // motion QA: read the position in the scroll event, only toggle in rAF
  const onScroll = () => {
    y = window.scrollY;
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => { ticking = false; el.classList.toggle("is-scrolled", y > 8); });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}
