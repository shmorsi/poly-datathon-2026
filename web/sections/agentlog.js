/* "Watch the AI work" (lane agentlog, ruling R42): the run's own trace as a mission log. Two views of the same rows
   (web/lib/agentlog.js, pure):
   1. THE RUN SCREEN, in the stage's slot ([data-agentlog-slot], lane U2b): when Replay is pressed the rows stream in the
      pipeline's true order on the stage's own clock (store.phaseClock {phase, at, T, instant, live}): OBSERVE + UNDERSTAND while
      the stage reads, one COMPARE line while the globe flies and the race runs, EXPLAIN + VERIFY in one line once the verdict
      lands, then the line rests on the fold ("One AI decision, checked by code; a defect caught and fixed.") and the button that
      opens the log. A saved run plays on a compressed clock; a live run streams store.steps on the real clock, then its rows.
   2. THE LOG, a drawer: every row at once, the code-held loop, what the AI changed. Opened by the stage's button, by any
      a[href="#agentlog"] or [data-agentlog-open] (the #why link), or by #agentlog in the address.
   Mounted by app.js from index.html (<div data-module="agentlog">); without the stage's slot only the drawer exists. Text is set
   with textContent only. Motion: opacity and transform only, one rAF loop while the run screen plays, at most one text write per
   frame; Esc, Skip, reduced motion or window.EPI_MOTION === false show the end state at once. */
import { logOf, liveRows, scheduleOf, tickText, timeText, ACTOR } from "../lib/agentlog.js";

const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs = {}, ...kids) {     // elements from data: textContent and attributes, never HTML strings
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
/* the actors keep #how's shapes: a disc for Claude on Amazon Bedrock, a diamond for Bedrock Guardrails, a square for code */
const MARK = {
  ai: () => s("circle", { cx: 6, cy: 6, r: 4.5 }),
  guard: () => s("path", { d: "M6 1.2 10.8 6 6 10.8 1.2 6z" }),
  code: () => s("rect", { x: 1.8, y: 1.8, width: 8.4, height: 8.4, rx: 1 }),
};
const mark = (actor) => s("svg", { class: `al-mark al-${actor}`, viewBox: "0 0 12 12", "aria-hidden": "true", focusable: "false" }, (MARK[actor] || MARK.code)());
const STATUS_ICON = {
  caught: [["path", { d: "M12 3l9.5 17h-19z", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linejoin": "round" }],
    ["path", { d: "M12 9.5v5", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 17.4, r: 1.25, fill: "currentColor" }]],
  done: [["path", { d: "M5.5 12.5l4.2 4.2 8.8-9.4", fill: "none", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" }]],
};
const icon = (k) => s("svg", { class: "al-icon", viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" }, ...(STATUS_ICON[k] || STATUS_ICON.done).map(([t, a]) => s(t, a)));
const WORD = { caught: "Caught", refused: "Refused", blocked: "Stopped", asked: "Asked you", none: "No precedent", error: "Not run" };
const tok = (name) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--" + name)) || 0;
const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const motionOn = () => globalThis.EPI_MOTION !== false && !reduced();
const GROUP = { OBSERVE: "Observe", UNDERSTAND: "Understand", COMPARE: "Compare", EXPLAIN: "Explain and verify", VERIFY: "Explain and verify" };
const PHASE_AT = { reading: (T) => 0, flying: (T) => T.fly, racing: (T) => T.race, landed: (T) => T.lamp };

/* one row of the log: time, actor mark, the sentence, its readout items, the exact words code or the AI wrote, the status */
function rowEl(r, opts = {}) {
  const status = WORD[r.status] ? h("span", { class: `al-status al-st-${r.status}` }, r.status === "caught" ? icon("caught") : null, WORD[r.status]) : null;
  const items = r.items && r.items.length ? h("dl", { class: "al-items" }, ...r.items.map((it) => h("div", { class: "al-item" },
    h("dt", { text: it.label }), h("dd", { text: it.text })))) : null;
  const quote = r.quote && r.quote.length ? h("blockquote", { class: "al-quote" }, ...r.quote.map((q) => h("p", { text: `“${q}”` }))) : null;
  return h("li", { class: "al-row", "data-id": r.id, "data-actor": r.actor, "data-status": r.status, "data-part": r.part, "data-in": opts.hidden ? "0" : "1" },
    h("span", { class: "al-time inst", text: opts.hidden ? "" : r.time || "" }),
    h("span", { class: "al-who" }, mark(r.actor), h("span", { class: "sr", text: ACTOR[r.actor] + ": " })),
    h("div", { class: "al-body" }, h("p", { class: "al-text" }, h("span", { text: r.text }), status), items, quote,
      r.sub ? h("p", { class: "al-sub", text: r.sub }) : null));
}
const legend = () => h("p", { class: "al-legend" }, ...["ai", "guard", "code"].map((a) => h("span", { class: "al-leg" }, mark(a),
  h("span", { text: { ai: "Claude on Amazon Bedrock", guard: "Bedrock Guardrails", code: "Code, no model" }[a] }))));

/* ---- the drawer: the whole log ---- */
function createDrawer() {
  const u = {};
  u.title = h("h2", { class: "al-title", id: "al-title", text: "Watch the AI work" });
  u.lede = h("p", { class: "al-lede" });
  u.loop = h("p", { class: "al-loop" });
  u.list = h("ol", { class: "al-list", "aria-label": "The run, step by step" });
  u.after = h("div", { class: "al-after" });
  u.foot = h("p", { class: "al-foot" });
  u.x = h("button", { class: "al-x", type: "button", "aria-label": "Close the log", text: "×" });
  u.panel = h("div", { class: "al-panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "al-title", tabindex: "-1" },
    h("div", { class: "al-top" }, u.title, u.x),
    h("div", { class: "al-scroll" }, u.lede, u.loop, legend(), u.list, u.after, u.foot));
  u.scrim = h("div", { class: "al-scrim" });
  /* closed, the drawer stays laid out (visibility hidden, inert): opening only composites, no forced layout (motion QA) */
  u.root = h("div", { class: "al-root", id: "agentlog-drawer", inert: true, "aria-hidden": "true", "data-motion": "off" }, u.scrim, u.panel);
  let back = null, closeT = 0, openNow = false;
  function render(log, r) {
    const who = r && typeof r.pilot === "string" && r.pilot ? { robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "The “Too Canadian?”" }[r.pilot] : null;
    const rec = log && log.recorded ? log.recorded.replace(/^Recorded/, "recorded") : null;
    u.lede.textContent = [who ? `${who}${who.startsWith("The") ? " question" : "’s question"}${rec ? `, ${rec}` : ""}.` : log && log.recorded ? `${log.recorded}.` : null,
      "The AI has two jobs: read your words and write the explanation. Code does the rest and checks both.",
      "Every line below is read from this run’s own trace."].filter(Boolean).join(" ");
    u.loop.hidden = !(log && log.loop);
    u.loop.replaceChildren(...(log && log.loop ? [h("span", { class: "al-slots", "aria-hidden": "true" },
      ...Array.from({ length: Math.max(1, log.loop.slots || 1) }, (_, i) => h("span", { class: "al-slot", "data-used": i < log.loop.decisions ? "1" : "0" }))),
    h("span", { text: log.loop.text })] : []));
    const rows = log ? log.rows : [];
    let group = null;                          // the pipeline's steps as quiet labels (the bar's step rail, the workshop's method)
    u.list.replaceChildren(...rows.filter((x) => x.part !== "after").flatMap((x) => {
      const g = GROUP[x.step] || null, out = [];
      if (g && g !== group) { group = g; out.push(h("li", { class: "al-step", text: g })); }
      out.push(rowEl(x));
      return out;
    }));
    const eff = rows.find((x) => x.part === "after");
    u.after.hidden = !eff;
    u.after.replaceChildren(...(eff ? [h("p", { class: "al-after-h", text: "What the AI changed in this run" }), h("p", { class: "al-after-t", text: eff.text })] : []));
    u.foot.textContent = log && log.totalText ? `${log.totalText} in all${log.model ? `, with ${log.model} on Amazon Bedrock and Bedrock Guardrails` : ""}. The verdict and every number come from code.` : "";
  }
  function open(from) {
    clearTimeout(closeT);
    if (openNow) return;
    openNow = true;
    back = from || document.activeElement;
    u.root.dataset.motion = motionOn() ? "on" : "off";
    u.root.inert = false;
    u.root.removeAttribute("aria-hidden");
    u.root.classList.add("is-open");
    requestAnimationFrame(() => { if (openNow) u.panel.focus({ preventScroll: true }); });   // the focus after the first frame
  }
  function close() {
    if (!openNow) return;
    openNow = false;
    u.root.classList.remove("is-open");
    closeT = setTimeout(() => { if (!openNow) { u.root.inert = true; u.root.setAttribute("aria-hidden", "true"); } }, motionOn() ? tok("dur-panel-exit") : 0);
    if (back && typeof back.focus === "function") back.focus({ preventScroll: true });
    if (location.hash === "#agentlog") history.replaceState(null, "", location.pathname + location.search);
  }
  u.x.addEventListener("click", close);
  u.scrim.addEventListener("click", close);
  /* the page behind stays still without touching the root scroller (motion QA: a lock on html re-lays out the whole page and
     fires the dial's and the race's resize observers): the scrim eats the wheel and the touch, the panel's scroller contains its own */
  const still = (e) => e.preventDefault();
  u.scrim.addEventListener("wheel", still, { passive: false });
  u.scrim.addEventListener("touchmove", still, { passive: false });
  u.panel.firstChild.addEventListener("wheel", still, { passive: false });   // the title bar is not a scroller: it holds still too
  u.root.addEventListener("keydown", (e) => {
    e.stopPropagation();                               // the page's presenter keys and the stage's Esc stay out of the open drawer
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") {                         // the focus stays inside the open drawer
      const f = [...u.panel.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")];
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === u.panel)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  return { root: u.root, render, open, close, isOpen: () => openNow };
}

/* ---- the run screen in the stage's slot: the feed (OBSERVE, UNDERSTAND, COMPARE) over the empty scene while the stage reads
   and flies, then one line (COMPARE, EXPLAIN, VERIFY), then the fold and the button that opens the log ---- */
function createRun(slot, drawer) {
  const u = {};
  u.mark = h("span", { class: "al-line-mark", "aria-hidden": "true" });
  u.a = h("span", { class: "al-line-t", "data-show": "1" });
  u.b = h("span", { class: "al-line-t", "data-show": "0" });
  u.time = h("span", { class: "al-line-time inst" });
  u.open = h("button", { class: "al-open linkbtn", type: "button", "aria-haspopup": "dialog", "aria-controls": "agentlog-drawer", text: "Watch the AI work",
    onclick: (e) => drawer.open(e.currentTarget) });
  u.line = h("div", { class: "al-line" }, u.mark, h("span", { class: "al-line-box" }, u.a, u.b), u.time, u.open);
  u.feed = h("ol", { class: "al-feed", "aria-hidden": "true" });
  u.root = h("div", { class: "al-run", "data-state": "rest", "data-feed": "0" }, u.line, u.feed);
  slot.replaceChildren(u.root);
  slot.hidden = false;
  slot.dataset.mounted = "1";
  const S = { log: null, r: null, raf: 0, start: 0, T: null, sched: null, shown: new Set(), tick: null, phase: null, live: false, liveAt: 0 };

  function setLine(text, actor, time, status) {   // a crossfade between two stacked spans: one text write, two flags
    const cur = u.a.dataset.show === "1" ? u.a : u.b, next = cur === u.a ? u.b : u.a;
    if (cur.textContent !== text) { next.textContent = text; next.dataset.show = "1"; cur.dataset.show = "0"; }
    if (u.mark.dataset.actor !== (actor || "")) { u.mark.dataset.actor = actor || ""; u.mark.replaceChildren(...(actor ? [mark(actor)] : [])); }
    if (u.line.dataset.status !== (status || "")) u.line.dataset.status = status || "";
    if (u.time.textContent !== (time || "")) u.time.textContent = time || "";
  }
  function stop() { if (S.raf) cancelAnimationFrame(S.raf); S.raf = 0; }
  function rest() {                          // the end frame and the still: the fold line and the button
    stop();
    S.live = false;
    u.root.dataset.state = "rest";
    u.root.dataset.feed = "0";
    setLine(S.log && S.log.fold ? S.log.fold : "The run’s own log:", null, "");
    u.open.hidden = !S.log;
  }
  function feedRows(rows, hidden) {
    u.feed.replaceChildren(...rows.map((x) => rowEl(x, { hidden })));
    S.shown = new Set(hidden ? [] : rows.map((x) => x.id));
  }
  function set(r) {
    S.r = r || null;
    S.log = logOf(r);
    slot.hidden = !S.log;
    if (!S.raf && !S.live) rest();
  }
  const el = (id) => u.feed.querySelector(`[data-id="${id}"]`);
  /* wide screens: the feed reads in the empty scene left of the Earth while the stage reads (fixed: any scroll ends the replay);
     one layout read when a replay starts, none per frame */
  function place() {
    const stage = slot.closest(".rp-stage"), scene = stage && stage.querySelector(".rp-scene");
    const a = (scene || slot).getBoundingClientRect(), b = (stage || slot).getBoundingClientRect();
    u.root.style.setProperty("--al-top", `${Math.round(Math.max(a.top, 72))}px`);
    u.root.style.setProperty("--al-left", `${Math.round(Math.max(b.left, 0))}px`);
  }
  function frame(now) {
    const t = now - S.start, sc = S.sched, rows = S.log.rows;
    for (const x of rows) {                  // reveal the feed's rows at their time (one row starts per frame)
      if (x.part !== "read" && x.part !== "compare") continue;
      if (S.shown.has(x.id) || !(sc.at[x.id] <= t)) continue;
      const li = el(x.id);
      if (S.tick && S.tick.li) S.tick.li.firstChild.textContent = S.tick.x.time || "";
      if (li) { li.dataset.in = "1"; S.tick = { li, x, t0: sc.at[x.id] }; }
      S.shown.add(x.id);
      break;
    }
    if (S.tick && S.tick.li) {               // the row in progress: its own time counts up and lands on the exact value
      const p = (t - S.tick.t0) / sc.tick, txt = tickText(S.tick.x.ms, p);
      if (S.tick.li.firstChild.textContent !== txt) S.tick.li.firstChild.textContent = txt;
      if (p >= 1) S.tick = null;
    }
    const T = S.T, fold = T.handoff - 120;      // the feed steps aside before the Earth glides into the stage's slot
    if (t >= fold && u.root.dataset.feed !== "0") u.root.dataset.feed = "0";
    const line = [...rows].reverse().find((x) => (x.part === "compare" || x.part === "explain") && sc.at[x.id] <= t);
    if (line && t >= fold) {
      const p = (t - sc.at[line.id]) / sc.tick;
      setLine(line.line || line.text, line.actor, line.ms !== null && line.ms !== undefined ? tickText(line.ms, line.part === "compare" ? 1 : p) : "", line.status);
      if (u.root.dataset.state !== "line") u.root.dataset.state = "line";
    }
    if (t >= sc.end) { rest(); return; }
    S.raf = requestAnimationFrame(frame);
  }
  function play(T, start) {                  // a saved run on the compressed clock, fitted to the stage's schedule
    stop();
    if (!S.log) return rest();
    S.T = { fly: 2200, handoff: 3400, race: 4200, lamp: 6720, ...(T || {}) };
    place();
    S.sched = scheduleOf(S.log.rows, S.T);
    S.start = start;
    S.tick = null;
    S.live = false;
    feedRows(S.log.rows.filter((x) => x.part === "read" || x.part === "compare"), true);
    u.root.dataset.state = "play";
    u.root.dataset.feed = "1";
    u.open.hidden = true;
    setLine("This run, replayed from its own trace", null, "");
    S.raf = requestAnimationFrame(frame);
  }
  function liveTick(now) {                   // a live run: the real clock while the server works
    const txt = timeText(now - S.liveAt).replace(/^<1/, "0");
    if (u.time.textContent !== txt) u.time.textContent = txt;
    S.raf = requestAnimationFrame(liveTick);
  }
  function steps(list) {
    if (!S.live) return;
    const rows = liveRows(list);
    for (const x of rows) {
      const li = el(x.id);
      if (!li) { const n = rowEl(x, { hidden: true }); u.feed.append(n); requestAnimationFrame(() => { n.dataset.in = "1"; }); continue; }
      li.dataset.status = x.status;
      li.querySelector(".al-text > span").textContent = x.text;
      li.firstChild.textContent = x.time || "";
    }
  }
  function clock(c) {
    if (!c || typeof c !== "object") return;
    const again = c.phase === S.phase && c.phase !== "reading";   // the stage may say "landed" twice (the lamp, then its end)
    S.phase = c.phase;
    if (c.instant || !motionOn()) return rest();
    if (again && !c.live) return;
    if (c.live && c.phase === "reading") {
      stop();
      S.live = true; S.liveAt = typeof c.at === "number" ? c.at : performance.now();
      u.feed.replaceChildren();
      place();
      u.root.dataset.state = "play"; u.root.dataset.feed = "1"; u.open.hidden = true;
      setLine("Live: this run, step by step", null, "");
      S.raf = requestAnimationFrame(liveTick);
      return;
    }
    if (c.phase === "idle") return rest();
    const T = { fly: 2200, handoff: 3400, race: 4200, lamp: 6720, ...(c.T || {}) }, base = PHASE_AT[c.phase];
    if (!base) return;
    const start = (typeof c.at === "number" ? c.at : performance.now()) - base(T);
    if (c.phase === "reading" || !S.raf || S.live) return play(T, start);   // a new replay, or a live run's result landing
    S.start = start; S.T = T; S.sched = scheduleOf(S.log.rows, T);          // the stage moved a beat: follow its clock
  }
  return { set, clock, steps, rest, destroy() { stop(); slot.replaceChildren(); delete slot.dataset.mounted; slot.hidden = true; } };
}

/* ---- the section contract (app.js): mount(el, store) ---- */
export function mount(el, store) {
  if (el) el.hidden = true;                  // the module's own element stays empty: the views live in the slot and the drawer
  const drawer = createDrawer();
  document.body.append(drawer.root);
  let run = null;
  const attach = () => {
    if (run) return;
    const slot = document.querySelector("[data-agentlog-slot]");
    if (slot) { run = createRun(slot, drawer); run.set(store.get().result); }
  };
  const onClick = (e) => {
    const a = e.target && e.target.closest ? e.target.closest('a[href="#agentlog"], [data-agentlog-open]') : null;
    if (!a || e.defaultPrevented || e.button > 0 || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    drawer.open(a);
  };
  document.addEventListener("click", onClick);
  const offs = [
    store.on("result", (r) => { drawer.render(logOf(r), r); attach(); if (run) run.set(r); }),
    store.on("phaseClock", (c) => { attach(); if (run) run.clock(c); }),
    store.on("steps", (st) => { if (run) run.steps(st); }),
  ];
  drawer.render(logOf(store.get().result), store.get().result);
  attach();
  if (location.hash === "#agentlog") drawer.open(null);
  return {
    open: (from) => drawer.open(from), close: () => drawer.close(),
    destroy() { offs.forEach((f) => f()); document.removeEventListener("click", onClick); if (run) run.destroy(); drawer.root.remove(); },
  };
}
