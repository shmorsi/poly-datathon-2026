/* EPICENTRE Replay: the step rail and the answer chip in the top bar (lane U0; the direction research and the cold usability
   test, Sun 15 Nov). The rail names the workshop's method plus our check, Observe / Understand / Compare / Explain / Verify, and
   "More" for the rest; the step on screen is marked (aria-current="step"). On the stage the rail follows the replay: the
   reading is Understand, the race is Compare. Wide screens: one line in the bar, More a small disclosure. Narrow screens (the
   bar's own links fold away at 1000 px): a compact scroller under the bar once the page has moved off the hero.
   The answer chip: once a replay has landed it keeps the investor's answer in the bar, in the stage's own words (lib/replay.js
   pillOf: the verdict at the size asked; at any other size only what that size did to the floor, never green, R20), and a
   press scrolls back to the stage. DOM from createElement only; links are plain anchors (a keyboard jump never animates). */
import { pillOf } from "./lib/replay.js";
import { standingLine } from "./lib/status.js";

export const STEPS = [
  { key: "observe", label: "Observe", target: "hero" },
  { key: "understand", label: "Understand", target: "replay" },
  { key: "compare", label: "Compare", target: "money" },
  { key: "explain", label: "Explain", target: "why" },
  { key: "verify", label: "Verify", target: "how" },
];
export const MORE = [
  { label: "Three investors", target: "investors" },
  { label: "Not just 2022", target: "deep" },
  { label: "Build your own shock", target: "scenario" },
];
/* which step a section belongs to (the stage is Understand while it reads, Compare once the race starts) */
export const STEP_OF = { hero: "observe", replay: "understand", money: "compare", why: "explain", checklist: "explain",
  testai: "verify", how: "verify", record: "verify", investors: "more", deep: "more", scenario: "more" };
const NAMES = { robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "Too Canadian?" };

export function stepFor(id, phase) {
  if (id === "replay") return ["flying", "racing", "landed"].includes(phase) ? "compare" : "understand";
  return STEP_OF[id] || null;
}

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const SVG = "http://www.w3.org/2000/svg";
const icon = (id) => {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "icon");
  s.setAttribute("aria-hidden", "true");
  const u = document.createElementNS(SVG, "use");
  u.setAttribute("href", `#${id}`);
  s.append(u);
  return s;
};
const shown = (id) => {
  const t = document.getElementById(id);
  return !!t && t.dataset.mount === "ready" && !t.hidden && t.getClientRects().length > 0 && t.offsetHeight >= 8;
};

export function mountRail(store) {
  const inner = document.querySelector("#bar .bar-in");
  if (!inner) return null;
  const nav = el("nav", "rail");
  nav.setAttribute("aria-label", "The steps of this check");
  const list = el("ol", "rail-list");
  const items = STEPS.map((s) => {
    const a = el("a", "rail-step", s.label);
    a.href = `#${s.target}`;
    a.dataset.step = s.key;
    const li = el("li", "rail-item");
    li.append(a);
    list.append(li);
    return { ...s, a, li };
  });
  const more = el("details", "rail-more");
  const summary = el("summary", "rail-step", "More");
  summary.dataset.step = "more";
  const menu = el("ul", "rail-menu");
  const moreLinks = MORE.map((m) => {
    const a = el("a", "rail-link", m.label);
    a.href = `#${m.target}`;
    a.addEventListener("click", () => { more.open = false; });
    const li = el("li");
    li.append(a);
    menu.append(li);
    return { ...m, a, li };
  });
  more.append(summary, menu);
  const moreItem = el("li", "rail-item");
  moreItem.append(more);
  list.append(moreItem);
  nav.append(list);
  document.addEventListener("pointerdown", (e) => { if (more.open && !more.contains(e.target)) more.open = false; });
  more.addEventListener("keydown", (e) => { if (e.key === "Escape" && more.open) { e.preventDefault(); more.open = false; summary.focus(); } });

  /* the answer chip: hidden until a replay has landed in this visit */
  const chip = el("button", "answer-chip");
  chip.type = "button";
  chip.hidden = true;
  const who = el("span", "answer-who"), mark = el("span", "answer-mark"), word = el("span", "answer-word"), rest = el("span", "answer-rest");
  chip.append(who, mark, word, rest);
  chip.addEventListener("click", () => {
    const stage = document.getElementById("replay");
    if (stage) stage.scrollIntoView({ block: "start" });
  });
  let landedOnce = false;
  const paintChip = () => {
    const st = store.get();
    if (st.phase === "landed") landedOnce = true;
    const pill = landedOnce && st.result ? pillOf(st.result, st.weightIndex) : null;
    chip.hidden = !pill || ["reading", "flying", "racing"].includes(st.phase);   // never gives the answer away mid-replay (design director, item 4)
    if (!pill) return;
    who.textContent = NAMES[st.investor] || "";
    mark.replaceChildren(...(pill.icon ? [icon(pill.icon)] : []));
    word.textContent = pill.word;
    rest.textContent = pill.whatIf ? pill.rest.replace(/^,\s*/, "") : "";
    chip.dataset.tone = pill.tone || "none";
    chip.dataset.whatif = pill.whatIf ? "1" : "0";
    const line = standingLine(!!(globalThis.PF && globalThis.PF.moveOf(st.result)));     // the standing line, as the tooltip
    chip.title = line;
    chip.setAttribute("aria-label", `${who.textContent}: ${pill.word}${pill.whatIf ? `, ${rest.textContent}` : ""}. ${line} Back to the replay.`);
  };

  const brand = inner.querySelector(".bar-brand");
  if (brand) brand.after(nav, chip); else inner.prepend(nav, chip);
  inner.classList.add("has-rail");

  /* a step whose section is missing or folded away is not offered */
  const refresh = () => {
    for (const s of items) s.li.hidden = !shown(s.target);
    for (const m of moreLinks) m.li.hidden = !shown(m.target);
    moreItem.hidden = moreLinks.every((m) => m.li.hidden);
  };

  /* the step on screen: the section across the middle band of the viewport (as the bar's own anchors did) */
  const ids = Object.keys(STEP_OF);
  const inView = new Set();
  let current = null;
  const mark_ = () => {
    const id = ids.filter((x) => inView.has(x)).sort((a, b) => order(a) - order(b)).pop() || null;
    const step = id ? stepFor(id, store.get().phase) : null;
    if (step === current) return;
    current = step;
    for (const s of items) (s.key === step ? s.a.setAttribute("aria-current", "step") : s.a.removeAttribute("aria-current"));
    (step === "more" ? summary.setAttribute("aria-current", "step") : summary.removeAttribute("aria-current"));
    const on = step === "more" ? summary : (items.find((s) => s.key === step) || {}).a;
    if (on && nav.scrollWidth > nav.clientWidth) on.scrollIntoView({ block: "nearest", inline: "nearest" });
  };
  const order = (id) => { const t = document.getElementById(id); return t ? [...document.querySelectorAll("[data-module]")].indexOf(t) : -1; };
  if (typeof IntersectionObserver === "function") {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) (e.isIntersecting ? inView.add(e.target.id) : inView.delete(e.target.id));
      mark_();
    }, { rootMargin: "-45% 0px -50% 0px" });
    for (const id of ids) { const t = document.getElementById(id); if (t) io.observe(t); }
  }
  store.on("phase", () => { mark_(); paintChip(); });
  store.on("result", () => { refresh(); paintChip(); });
  store.on("weightIndex", paintChip);
  store.on("investor", paintChip);
  if (typeof ResizeObserver === "function") {
    const ro = new ResizeObserver(() => requestAnimationFrame(refresh));
    for (const id of ids) { const t = document.getElementById(id); if (t) ro.observe(t); }
  }
  refresh();
  paintChip();
  return { nav, chip, refresh };
}
