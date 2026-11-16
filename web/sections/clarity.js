/* EPICENTRE Replay, lane clarity: the one shape the finished sections open with (ruling R22; the lead 12:35: "an insane UI, but
   simple to use"). Not a section (index.html names none): #dial, #money, #checklist, #why, #investors, #how, #record and
   #footer import it, so they read as one voice. DOM by createElement / textContent only.
   head(id, question, answer)   ONE plain question as the heading, ONE answer sentence under it (answer: a string or nodes).
   details(key, store, kids, o)  the ONE quiet "Show the details" disclosure of a section: a button (aria-expanded,
                                 aria-controls) and its panel, closed by default; the open state is remembered per section
                                 while the page lives (a re-render keeps it); the page's depth switch (store key `depth`:
                                 "simple" | "detailed", lane u0) opens or closes every one; a reader's own toggle still works.
                                 o.onToggle(open) runs after a change (a piece that measures itself redraws there).
   mean(node, sentence)          a number's plain-words meaning (web/lib/meaning.js): a title plus one accessible tooltip on
                                 hover, focus or tap (role="tooltip", aria-describedby while it shows; Esc closes it). */
import { keepRanges, TERMS } from "../lib/meaning.js";

const SVG = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}

function chevron() {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "cl-chev");
  s.setAttribute("viewBox", "0 0 12 12");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", "M2.5 4.5 6 8l3.5-3.5");
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", "1.6");
  p.setAttribute("stroke-linecap", "round");
  p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
}

/* ---- red gate 4: the legend of the kind marks, always in view wherever a mark shows (pre-freeze 1) ---- */
const MARKS = [["m-fact", "fact"], ["m-assumption", "assumption or limit"], ["m-fiction", "scenario or fiction"]];
function use(id, cls) {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", cls || "kind");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  const u = document.createElementNS(SVG, "use");
  u.setAttribute("href", `#${id}`);
  s.append(u);
  return s;
}
export function marks() {
  return h("ul", { class: "cl-marks", "aria-label": "What the marks mean" }, MARKS.map(([id, word]) => h("li", {}, use(id, "kind"), word)));
}
export const markIcon = (kind) => use(kind === "fact" ? "m-fact" : kind === "fiction" ? "m-fiction" : "m-assumption", "kind");

/* ---- the question and its answer ---- */
export function head(id, question, answer, extra) {
  return h("header", { class: "cl-head" },
    h("h2", { class: "cl-q", id }, question),
    answer ? h("p", { class: "cl-a" }, typeof answer === "string" ? keepRanges(answer) : answer) : null,
    extra || null);
}

/* a sentence with its figures set apart: each listed figure (its first occurrence, in order) becomes a .cl-fig with its meaning */
export function figs(text, list) {
  const out = [];
  let rest = keepRanges(text);
  for (const f of list || []) {
    if (!f || !f.text) continue;
    const i = rest.indexOf(f.text);
    if (i < 0) continue;
    if (i) out.push(rest.slice(0, i));
    out.push(mean(h("span", { class: "cl-fig" }, f.text), f.meaning));
    rest = rest.slice(i + f.text.length);
  }
  if (rest) out.push(rest);
  return out;
}

/* ---- the one disclosure per section ---- */
const OPEN = new Map();            // section key -> true | false, while the page lives (a reader's own choice)
const LIVE = new Map();            // section key -> the setter of the disclosure on screen now
let bound = null;

const detailed = (store) => ((store && store.get && store.get()) || {}).depth === "detailed";

function bind(store) {
  if (!store || bound === store || typeof store.on !== "function") return;
  bound = store;
  store.on("depth", (d) => {
    OPEN.clear();                                          // the page-level switch wins over every earlier choice
    for (const set of LIVE.values()) set(d === "detailed", false);
  });
}

export function details(key, store, kids, o = {}) {
  bind(store);
  const id = `${key}-details`;
  const startOpen = OPEN.has(key) ? OPEN.get(key) : detailed(store);
  const word = h("span", { class: "cl-more-word" }, startOpen ? "Hide the details" : "Show the details");
  const btn = h("button", { type: "button", class: "cl-more", "aria-expanded": startOpen ? "true" : "false", "aria-controls": id },
    word, chevron());
  const panel = h("div", { class: "cl-details", id, hidden: !startOpen, role: "region", "aria-label": o.label || "The details" }, kids);
  const set = (on, animate) => {
    const was = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", on ? "true" : "false");
    word.textContent = on ? "Hide the details" : "Show the details";
    panel.hidden = !on;
    panel.classList.toggle("is-new", !!(on && animate));
    if (was !== on && typeof o.onToggle === "function") {
      try { o.onToggle(on); } catch (e) { console.error("[clarity] a details toggle failed:", e); }
    }
  };
  btn.addEventListener("click", (ev) => {
    const on = btn.getAttribute("aria-expanded") !== "true";
    OPEN.set(key, on);
    set(on, ev.detail !== 0);                              // a keyboard action never animates
  });
  LIVE.set(key, set);
  return h("div", { class: "cl-fold" }, btn, panel);
}

/* for tests and the capture scripts: what each section's disclosure shows now */
export function detailsState() { return Object.fromEntries([...LIVE.keys()].map((k) => [k, OPEN.has(k) ? OPEN.get(k) : null])); }

/* ---- a number's meaning: title + one shared tooltip ---- */
let tip = null, tipFor = null;
const FOCUSABLE = /^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/;

function hide() {
  if (!tip || !tipFor) return;
  const n = tipFor;
  tipFor = null;
  tip.hidden = true;
  if (n.dataset.meaningTitle !== undefined) { n.setAttribute("title", n.dataset.meaningTitle); delete n.dataset.meaningTitle; }
  const keep = (n.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== "cl-tip");
  if (keep.length) n.setAttribute("aria-describedby", keep.join(" ")); else n.removeAttribute("aria-describedby");
}

function show(n) {
  if (!tip || !n || !n.isConnected) return;
  if (tipFor === n) return;
  hide();
  const text = n.dataset.meaning;
  if (!text) return;
  tipFor = n;
  if (n.hasAttribute("title")) { n.dataset.meaningTitle = n.getAttribute("title"); n.removeAttribute("title"); }   // one tooltip, never two
  const ids = (n.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
  if (!ids.includes("cl-tip")) n.setAttribute("aria-describedby", [...ids, "cl-tip"].join(" "));
  tip.textContent = text;
  tip.style.transform = "translate(-9999px, 0)";
  tip.hidden = false;
  const r = n.getBoundingClientRect(), W = document.documentElement.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
  const x = Math.round(Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), Math.max(8, W - tw - 8)));
  const y = Math.round(r.top - th - 10 >= 8 ? r.top - th - 10 : r.bottom + 10);
  tip.style.transform = `translate(${x}px, ${y}px)`;
}

function ensureTip() {
  if (tip || typeof document === "undefined" || !document.body || typeof document.addEventListener !== "function") return;   // no browser: no tooltip
  tip = h("div", { class: "cl-tip", id: "cl-tip", role: "tooltip", hidden: true });
  document.body.append(tip);
  const at = (e) => (e.target && e.target.closest ? e.target.closest("[data-meaning]") : null);
  document.addEventListener("pointerover", (e) => { const n = at(e); if (n) show(n); });
  document.addEventListener("pointerout", (e) => {
    const n = at(e);
    if (n && n === tipFor && !(e.relatedTarget && n.contains(e.relatedTarget)) && document.activeElement !== n) hide();
  });
  document.addEventListener("pointerdown", (e) => { if (!at(e)) hide(); }, true);
  document.addEventListener("focusin", (e) => { const n = at(e); if (n) show(n); else hide(); });
  document.addEventListener("focusout", (e) => { if (e.target === tipFor) hide(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tipFor) hide(); });
  if (typeof globalThis.addEventListener === "function") globalThis.addEventListener("scroll", () => { if (tipFor) hide(); }, { passive: true, capture: true });
}

export function mean(node, sentence, o) {
  if (!node || !sentence) return node;
  ensureTip();
  if (node.dataset) node.dataset.meaning = sentence;
  node.setAttribute("title", sentence);
  if (node.classList) node.classList.add("has-meaning");
  const focus = !(o && o.focus === false);             // a long annex: hover and tap, without a tab stop on every figure
  if (focus && !FOCUSABLE.test(node.tagName) && node.getAttribute("tabindex") === null) node.setAttribute("tabindex", "0");
  return node;
}

/* a plain term with its exact name in the tooltip (TERMS in web/lib/meaning.js): "the AI reader" says "The navigator: …" */
export function term(text, key) {
  const k = key || text, words = TERMS[k] || TERMS[String(k).toLowerCase()] || null;
  const n = h("span", { class: "cl-term" }, text);
  return words ? mean(n, words) : n;
}
