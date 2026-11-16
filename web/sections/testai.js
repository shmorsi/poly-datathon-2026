/* EPICENTRE Replay, lane judge: #testai, "Try to trip it up" (ruling R25), and the bar's "Judging? Start here" popover.
   Six one-click experiments from data/demo_runs/tests.json (INTERFACES.md): each card shows the question in typographic quotes,
   what it shows in one line, and "Run it". Static: a "run" card puts its saved run (runs/<key>.json) on the stage and the
   replay plays; a "blocked" or "clarify" card opens its recorded answer in place, with who stopped it or what the AI asked.
   Live: every card sends its question down the app's normal path (store question + replay; the stage runs it live).
   No tests.json signal (lib/judge.js testsSource): no request at all and the section stays hidden. Pure logic: lib/judge.js.
   DOM from createElement / textContent only (R16). Motion answers a press only: the answer's reveal (opacity + clip-path, one
   panel duration), never on a keyboard press, never under reduced motion or html.motion-off. */
import * as J from "../lib/judge.js";
import * as H from "../lib/how.js";
import { land, loadRun } from "../data.js";
import { head } from "./clarity.js";
import { keepRanges } from "../lib/meaning.js";             // "2021–26" never breaks at its dash

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
/* who answered, in #how's glyph language: diamond = Amazon Bedrock Guardrails, disc = Amazon Bedrock (the AI reader), square = code */
function glyph(kind, cls) {
  const s = h("svg:svg", { class: `ta-glyph ta-glyph-${kind}${cls ? ` ${cls}` : ""}`, viewBox: "-8 -8 16 16", "aria-hidden": "true", focusable: "false" });
  if (kind === "ring") s.append(h("svg:circle", { r: "5" }));
  else if (kind === "diamond") s.append(h("svg:path", { d: "M0 -6 6 0 0 6 -6 0Z" }));
  else if (kind === "disc") s.append(h("svg:circle", { r: "6" }), h("svg:circle", { r: "2.6", class: "ta-glyph-core" }));
  else s.append(h("svg:rect", { x: "-4.5", y: "-4.5", width: "9", height: "9", rx: "1.5" }));
  return s;
}
const metaOf = (name) => { const m = document.querySelector(`meta[name="epicentre-${name}"]`); return m ? m.content : null; };
const motionOK = () => window.EPI_MOTION !== false && !document.documentElement.classList.contains("motion-off")
  && !!window.matchMedia && window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

/* ---- the saved runs behind the run cards (static mode), fetched once each ---- */
const runs = new Map();
function fetchRun(key) {
  const path = J.runPath(key);
  if (!path) return Promise.reject(new Error("no key"));
  if (!runs.has(key)) {
    const p = fetch(new URL(`../${path}`, import.meta.url), { cache: "no-store" })
      .then((res) => { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
      .then((j) => { const r = isObj(j) && isObj(j.result) && j.key ? j.result : j; if (!isObj(r) || r.status === "error") throw new Error("not a run"); return r; });
    runs.set(key, p);
    p.catch(() => runs.delete(key));                // a failure is not remembered: the next press retries
  }
  return runs.get(key);
}

/* the investor whose portfolio the question runs on: switch to them and wait until app.js has landed their run */
function onInvestor(store, pilot, ms = 6000) {
  const st = store.get();
  if (st.investor === pilot && st.result && st.result.pilot === pilot) return Promise.resolve();
  return new Promise((resolve) => {
    let done = false, off = null, timer = 0;
    const finish = () => { if (done) return; done = true; if (off) off(); clearTimeout(timer); resolve(); };
    off = store.on("result", (r) => { if (r && r.pilot === pilot) finish(); });
    timer = setTimeout(finish, ms);
    if (store.get().investor !== pilot) store.set({ investor: pilot });
  });
}

/* ---- one card ---- */
function card(t, mode, store, S) {
  const v = J.cardView(t, mode);
  const qid = `ta-q-${t.id}`, aid = `ta-a-${t.id}`;
  const btn = h("button", { class: "btn btn-quiet ta-run", type: "button", "aria-label": v.button.label, "aria-describedby": qid },
    icon("i-play", "icon"), h("span", { class: "ta-run-word", text: v.button.text }));
  const status = h("p", { class: "ta-status", role: "status", "aria-live": "polite" });
  let mark = glyph("ring", "ta-mark");
  const li = h("li", { class: "ta-card", "data-test": t.id, "data-kind": t.kind, "data-state": "idle" },
    h("div", { class: "ta-top" }, mark, h("h3", { class: "ta-label", text: v.label || v.question }), v.investor ? h("p", { class: "ta-who", text: v.investor }) : null),
    h("div", { class: "ta-spec" },
      h("p", { class: "ta-q", id: qid, lang: /[àâçéèêëîïôûùüÿœ]|\bEt si\b/i.test(t.question) ? "fr" : null, text: v.question }),
      v.shows ? h("p", { class: "ta-shows", text: keepRanges(v.shows) }) : null),
    h("div", { class: "ta-act" }, btn));
  const outRow = h("div", { class: "ta-out" }, status);     // the fourth row: what came back (a status line, or the recorded answer)
  li.append(outRow);
  let answer = null;
  if (v.action === "inline" && v.answer) {
    const when = H.provenance(t.response);
    answer = h("div", { class: "ta-answer", id: aid, role: "region", "aria-label": `The recorded answer: ${v.label || "this question"}`, hidden: true },
      h("p", { class: "ta-badge" }, glyph(v.answer.glyph), h("span", { text: v.answer.badge })),
      h("blockquote", { class: "ta-said" }, h("p", { text: keepRanges(v.answer.text) })),
      when ? h("p", { class: "ta-when", text: `${when.text}.` }) : null);
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", aid);
    outRow.append(answer);
  }
  const word = btn.querySelector(".ta-run-word");
  /* the card's marker: the question (ring) until it ran, then who answered it (#how's glyphs); a card that ran keeps its edge lit */
  const marker = (kind, animate) => {
    li.dataset.ran = "1";
    if (mark.classList.contains(`ta-glyph-${kind}`)) return;
    const next = glyph(kind, "ta-mark");
    if (animate && motionOK()) next.classList.add("is-new");
    mark.replaceWith(next);
    mark = next;
  };
  const set = (state, line, back) => {
    li.dataset.state = state;
    status.replaceChildren(...(line ? [h("span", { text: keepRanges(line) })] : []), ...(back ? [" ", back] : []));
  };
  const busy = (on) => {
    btn.disabled = on;
    btn.setAttribute("aria-busy", on ? "true" : "false");
    word.textContent = on ? "Loading" : v.button.text;
  };
  const backBtn = () => {
    const b = h("button", { class: "linkbtn ta-back", type: "button", text: v.back });
    b.addEventListener("click", async () => {
      try { const r = await loadRun(t.pilot); S.onStage = null; land(r, { question: typeof r.question === "string" ? r.question : "" }); set("idle"); btn.focus(); }
      catch (e) { set("failed", J.LOAD_FAILED); }
    });
    return b;
  };

  btn.addEventListener("click", async (ev) => {
    const act = J.actionFor(t, mode);
    if (!act) return;
    if (act.type === "inline") {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open));
      word.textContent = open ? "Hide the answer" : v.button.text;
      btn.setAttribute("aria-label", open ? `Hide the answer: ${v.label || v.question}` : v.button.label);
      answer.hidden = !open;
      li.dataset.state = open ? "open" : "idle";
      const animate = open && ev.detail !== 0 && motionOK();                       // a keyboard press never animates
      answer.classList.toggle("is-new", animate);
      if (open) marker(v.answer.glyph, animate);
      return;
    }
    S.reset(li);
    busy(true);
    try {
      if (act.type === "load") {
        const [r] = await Promise.all([fetchRun(act.key), onInvestor(store, act.pilot)]);
        land(r, { question: typeof r.question === "string" ? r.question : t.question });
        S.onStage = { li, result: r, reset: () => set("idle") };
        set("playing", J.playingLine("load", H.qualifier(r)), backBtn());
        marker("disc", ev.detail !== 0);
        store.set({ replay: Date.now() });
      } else {
        await onInvestor(store, act.pilot);
        S.onStage = { li, result: null, live: true, reset: () => set("idle") };
        set("playing", J.playingLine(t.kind === "run" ? "live" : "live-stop", H.qualifier(store.get().result)));
        marker("disc", ev.detail !== 0);
        store.set({ question: act.question, replay: Date.now() });
      }
    } catch (e) {
      S.onStage = null;
      set("failed", J.LOAD_FAILED);
    } finally {
      busy(false);
    }
  });
  return li;
}

/* ---- mount ---- */
export function mount(el, store) {
  el.classList.add("testai");
  el.hidden = true;                                   // shown only once its tests have arrived
  const S = {
    onStage: null,                                    // the card whose run is on the stage: {li, result, reset}
    reset(except) { if (S.onStage && S.onStage.li !== except) S.onStage.reset(); S.onStage = null; },
  };
  const judge = mountJudge(store);
  const src = J.testsSource({ override: typeof window.EPI_TESTS_URL === "string" ? window.EPI_TESTS_URL : null, meta: metaOf("tests") });
  if (!src) return;                                   // no tests.json on this site: no request, nothing on the page
  store.on("result", (r) => {                          // another run on the stage: the card that put its own there goes quiet
    const on = S.onStage;
    if (!on) return;
    if (on.live && on.result === null) { on.result = r; return; }          // the live run's own Result has landed
    if (r !== on.result) { on.reset(); S.onStage = null; }
  });
  fetch(new URL(src, document.baseURI), { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : null))
    .then((json) => {
      const mode = store.get().mode === "live" ? "live" : "static";
      const tests = J.readTests(json).filter((t) => J.actionFor(t, mode));
      if (!tests.length) return;
      const cols = J.spans(tests.length);
      const list = h("ul", { class: "ta-list", "aria-labelledby": "testai-title", "data-n": String(tests.length) },
        tests.map((t, i) => { const li = card(t, mode, store, S); li.style.setProperty("--span", String(cols[i] || 4)); return li; }));
      const frame = h("div", { class: "frame ta-frame" }, head("testai-title", J.TITLE, J.lede(tests.length)), list);
      el.setAttribute("aria-labelledby", "testai-title");
      el.replaceChildren(frame);
      el.hidden = false;
      judge.setTests(tests.length);
    })
    .catch(() => { /* unreadable: the section stays hidden */ });
}

/* ---- "Judging? Start here" (R25): one quiet pill in the bar's end group, one small popover of three steps. It opens only when
   pressed (design director, item 9: the pill is enough); Esc, the close button, a press outside or Tab out of it close it.
   Non-modal: the page stays usable around it. ---- */
function mountJudge(store) {
  const api = { setTests() {} };
  const end = document.querySelector("#bar .bar-end");
  if (!end || document.getElementById("judge-pop")) return api;
  const btn = h("button", { class: "judge-btn", type: "button", "aria-expanded": "false", "aria-controls": "judge-pop", "aria-label": J.JUDGE_LABEL },
    h("span", { class: "judge-long", text: J.JUDGE_LABEL }), h("span", { class: "judge-short", "aria-hidden": "true", text: J.JUDGE_SHORT }));
  const pop = h("div", { class: "judge-pop", id: "judge-pop", role: "dialog", "aria-modal": "false", "aria-labelledby": "judge-pop-t", hidden: true });
  end.prepend(btn);
  document.body.append(pop);
  let tests = 0, isOpen = false;

  /* the bar is full at some widths once the answer chip shows: the full words, else "Judging?", else the button steps aside
     (the investor's answer keeps its place). Measured, not guessed: the rail is the bar's one shrinking item. */
  const inn = btn.closest(".bar-in");
  let fitQueued = false;
  const overflows = () => {
    if (!inn) return false;
    const rail = inn.querySelector(".rail");
    const railIn = rail && rail.getClientRects().length && getComputedStyle(rail).position !== "absolute";
    return inn.scrollWidth - inn.clientWidth > 16 || (!!railIn && rail.scrollWidth - rail.clientWidth > 1);
  };
  function fit() {
    fitQueued = false;
    for (const f of ["full", "short", "none"]) { btn.dataset.fit = f; if (!overflows()) break; }
    if (btn.dataset.fit === "none" && isOpen) close(false);
  }
  const queueFit = () => { if (!fitQueued) { fitQueued = true; requestAnimationFrame(fit); } };
  if (inn && typeof MutationObserver === "function") {
    new MutationObserver(queueFit).observe(inn, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["hidden"] });
  }
  window.addEventListener("resize", queueFit, { passive: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(queueFit, () => {});
  queueFit();

  const usable = (t) => !!t && !t.hidden && !["missing", "failed", "off"].includes(t.dataset.mount) && t.getClientRects().length > 0;
  function jump(target) {
    target.scrollIntoView({ block: "start" });
    const hd = target.querySelector("h2");
    if (hd) { if (!hd.hasAttribute("tabindex")) hd.setAttribute("tabindex", "-1"); hd.focus({ preventScroll: true }); }
  }
  function note(text) {
    const live = store.get().mode !== "live" && metaOf("live");
    const at = text.indexOf("the live app");
    if (!live || at < 0 || !/^https:\/\//.test(live)) return h("p", { class: "judge-note", text });
    return h("p", { class: "judge-note" }, text.slice(0, at),
      h("a", { href: live, rel: "noopener", text: "the live app" }), text.slice(at + "the live app".length));
  }
  function draw() {
    const p = J.judgeSteps({ tests, mode: store.get().mode === "live" ? "live" : "static" });
    const steps = p.steps.map((s) => {
      const inner = [h("span", { class: "judge-n", "aria-hidden": "true", text: String(s.n) }), h("span", { class: "judge-text", text: s.text })];
      if (s.id === "replay") {
        const b = h("button", { class: "judge-step", type: "button", "data-step": s.id }, inner);
        b.addEventListener("click", () => { close(true); store.set({ replay: Date.now() }); });
        return h("li", {}, b);
      }
      const target = document.getElementById(s.target);
      if (!usable(target)) return h("li", {}, h("p", { class: "judge-step is-plain", "data-step": s.id }, inner));
      const a = h("a", { class: "judge-step", href: `#${s.target}`, "data-step": s.id }, inner);
      a.addEventListener("click", (e) => { e.preventDefault(); close(false); jump(target); });
      return h("li", {}, a);
    });
    const x = h("button", { class: "judge-x", type: "button", "aria-label": "Close" }, icon("i-close", "icon"));
    x.addEventListener("click", () => close(true));
    pop.replaceChildren(h("div", { class: "judge-head" }, h("h2", { class: "judge-t", id: "judge-pop-t", text: p.title }), x),
      h("ol", { class: "judge-steps" }, steps), note(p.note));
  }
  function place() {
    const r = btn.getBoundingClientRect();
    pop.style.top = `${Math.round(r.bottom + 8)}px`;
    pop.style.right = `${Math.max(12, Math.round(document.documentElement.clientWidth - r.right))}px`;
  }
  function show(focusInside, animate) {
    draw(); place();
    pop.hidden = false; isOpen = true;
    btn.setAttribute("aria-expanded", "true");
    pop.classList.toggle("is-new", !!animate && motionOK());
    if (focusInside) { const first = pop.querySelector(".judge-step:not(.is-plain)"); if (first) first.focus(); }
  }
  function close(returnFocus) {
    if (!isOpen) return;
    const inside = pop.contains(document.activeElement);
    pop.hidden = true; isOpen = false;
    btn.setAttribute("aria-expanded", "false");
    if (returnFocus && inside) btn.focus();
  }
  btn.addEventListener("click", (e) => { if (isOpen) close(true); else show(e.detail === 0, e.detail !== 0); });
  document.addEventListener("keydown", (e) => {
    if (J.keyAction(e.key, isOpen) !== "close") return;
    e.preventDefault();                                // the presenter's Esc (app.js) leaves the motion on: this Esc only closed the popover
    close(true);
  });
  document.addEventListener("pointerdown", (e) => { if (isOpen && !pop.contains(e.target) && !btn.contains(e.target)) close(false); }, true);
  pop.addEventListener("focusout", (e) => {             // Tab out of it (to anything but its own button): it closes
    const to = e.relatedTarget;
    if (isOpen && to && !pop.contains(to) && to !== btn) close(false);
  });
  window.addEventListener("resize", () => { if (isOpen) place(); }, { passive: true });

  api.setTests = (n) => { tests = Number(n) || 0; if (isOpen) draw(); };
  return api;
}
