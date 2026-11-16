/* EPICENTRE Replay, lane profile-ui: the 5th investor, "You" (R46, R49). Not a section of its own: hero.js mounts it under the
   investor chips (one mount point) and shows it while store.investor is "you". One calm box: you describe yourself; the AI reader
   (POST /api/profile/read, lane profile-ai) fills one card in plain words, each field tagged "from your words" (hover or focus
   shows the exact words) or "assumed ✎" (editable here, then "set by you"); one clarifying question shows inline. The limits the
   words set go to lane hold's limits card (store.limitsIn), the neutral starting mix to lane hold's holdings card
   (store.holdings, "assumed: edit it"); the move to the hero's box (store.question). Replay runs through the stage's own path
   (replay.js: youGate, withYou). Static demo: the one recorded example (<meta name="epicentre-you">) or one honest line.
   DOM by createElement / textContent only (R16); words from web/lib/you.js (pure, node-tested). */
import * as Y from "../lib/you.js";
import { composeQuestion } from "../lib/movepicker.js";
import { mean } from "./clarity.js";

function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(2)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}
function ensureCss() {                          // the integrated page links it; a harness that does not still gets it once
  if (typeof document === "undefined" || document.querySelector('link[href$="css/you.css"]')) return;
  document.head.append(h("link", { rel: "stylesheet", href: new URL("../css/you.css", import.meta.url).href }));
}
const meta = (name) => { const m = document.querySelector(`meta[name="epicentre-${name}"]`); return m ? m.content : null; };
const norm = (x) => (typeof x === "string" ? x.replace(/[  ]/g, " ").replace(/\s+/g, " ").trim() : "");
const still = () => globalThis.EPI_MOTION === false || document.documentElement.classList.contains("motion-off") ||
  (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
const DEFAULT_MOVE = () => composeQuestion("NVDA", 20);

export function mountYou(el, store) {
  ensureCss();
  el.classList.add("yu");
  el.hidden = true;
  const hero = el.closest(".hx") || el.parentElement;
  const st = () => store.get();
  const live = () => st().mode === "live";
  const Ys = { text: "", read: null, edits: {}, edited: [], busy: false };   // the card's state (store key "you", lane profile-ui)
  let lastYou = null, example = null, exampleTried = false, seq = 0;

  /* ---- the box ---- */
  const ta = h("textarea", { id: "yu-text", class: "yu-text", rows: 2, maxlength: Y.MAX_TEXT, placeholder: Y.EXAMPLE, spellcheck: "true",
    autocomplete: "off", "aria-describedby": "yu-status" });
  const readBtn = h("button", { type: "submit", class: "btn btn-quiet yu-read", text: Y.READ_LABEL });
  const status = h("p", { class: "yu-status", id: "yu-status", role: "status", "aria-live": "polite" });
  const form = h("form", { class: "yu-form", novalidate: true, "aria-label": "Describe yourself" },
    h("label", { class: "yu-ask", for: "yu-text", text: Y.PROMPT }), ta, h("div", { class: "yu-row" }, readBtn, status));
  /* ---- the clarifying question, inline ---- */
  const qText = h("p", { class: "yu-q", id: "yu-q" });
  const qIn = h("input", { class: "yu-q-in", id: "yu-q-in", type: "text", autocomplete: "off", "aria-labelledby": "yu-q" });
  const qBtn = h("button", { type: "submit", class: "btn btn-quiet yu-q-go", text: Y.ANSWER_LABEL });
  const qSkip = h("button", { type: "button", class: "linkbtn yu-q-skip", text: Y.SKIP_LABEL, hidden: true });   // only the capacity is open
  const ask = h("form", { class: "yu-clarify", novalidate: true, hidden: true, "aria-label": "One question" }, qText, h("div", { class: "yu-row" }, qIn, qBtn, qSkip));
  qSkip.addEventListener("click", () => { Ys.skip = true; say("", ""); publish(); });
  /* ---- the card ---- */
  const list = h("dl", { class: "yu-list" });
  const kw = h("p", { class: "yu-kw", hidden: true });
  const clash = h("div", { class: "yu-clash", hidden: true, role: "status" });   // a value you set over your words, said in one amber line
  const card = h("div", { class: "yu-card", hidden: true, role: "group", "aria-label": "Your profile, as read from your words" }, list, clash, kw);
  const note = h("p", { class: "yu-note", text: Y.PRIVACY });
  /* once read, the box folds to your words on one line (the card is what you check); "Change my words" opens it again */
  const saidText = h("q", { class: "yu-said-t" });
  const saidBtn = h("button", { type: "button", class: "linkbtn yu-said-edit", text: "Change my words", "aria-controls": "yu-text" });
  const said = h("p", { class: "yu-said", hidden: true }, saidText, saidBtn);
  el.replaceChildren(form, said, ask, card, note);
  let wording = false;                          // the reader opened the box again to change the words
  saidBtn.addEventListener("click", () => { wording = true; fold(); ta.focus(); });
  function fold() {
    const folded = !!Ys.read && Y.usable(Ys.read) && !wording && !!Ys.text;
    form.hidden = folded; said.hidden = !folded;
    saidText.textContent = Ys.text || "";
    saidBtn.hidden = !live();
  }

  const say = (text, tone) => { status.textContent = text || ""; status.dataset.tone = tone || ""; };
  function publish() {
    const you = { text: Ys.text, read: Ys.read, edits: { ...Ys.edits }, edited: [...Ys.edited], skip: !!Ys.skip };
    store.set({ you, limitsIn: Y.limitsInOf(you) });
    render();
  }

  /* ---- the card's rows: label, value, where it came from; an assumed value opens in place ---- */
  function pen(item, row, words) {             // the ✎ that changes a value in place (live only)
    const b = h("button", { type: "button", class: "yu-src yu-edit", "data-src": item.source === "assumed" ? "assumed" : "pen",
      "aria-label": `${row.label}: ${item.text}, ${words}. Change it` },
      ...(item.source === "assumed" ? [h("span", { text: Y.ASSUMED })] : []), h("span", { class: "yu-pen", "aria-hidden": "true", text: item.source === "assumed" ? " \u270e" : "\u270e" }));
    b.addEventListener("click", () => openEdit(item, row, b));
    return b;
  }
  function tag(item, row) {
    const canEdit = !!item.edit && live();
    if (item.source === "words") {
      const t = h("span", { class: "yu-src", "data-src": "words", text: item.beat ? `${Y.FROM_WORDS} (${item.beat})` : Y.FROM_WORDS });
      const w = item.words ? mean(t, `From your words: \u201c${item.words}\u201d`) : t;
      return canEdit ? [w, pen(item, row, Y.FROM_WORDS)] : [w];
    }
    if (item.source === "you") { const t = h("span", { class: "yu-src", "data-src": "you", text: Y.YOURS }); return canEdit ? [t, pen(item, row, Y.YOURS)] : [t]; }
    if (!canEdit) return [h("span", { class: "yu-src", "data-src": "assumed", text: Y.ASSUMED })];
    return [pen(item, row, Y.ASSUMED)];
  }
  function openEdit(item, row, btn) {
    const box = btn.closest(".yu-item"), val = box.querySelector(".yu-v");
    let ctl;
    if (item.edit.years) ctl = h("input", { class: "yu-ctl", type: "number", min: 1, max: 40, step: 1, value: item.edit.value, "aria-label": `${row.label}, in years` });
    else { ctl = h("select", { class: "yu-ctl", "aria-label": row.label });
      for (const [k, words] of Object.entries(item.edit.options)) ctl.append(h("option", { value: k, text: words, selected: k === item.edit.value })); }
    val.replaceChildren(ctl); for (const x of box.querySelectorAll(".yu-src")) x.hidden = true; ctl.focus();
    let done = false;
    const commit = (keep) => {
      if (done) return; done = true;
      const v = keep ? Y.editValue(item.key, ctl.value) : null;
      if (v !== null && v !== Y.valueOf(Ys, item.key)) { Ys.edits[item.key] = v; if (!Ys.edited.includes(item.key)) Ys.edited.push(item.key); publish(); }
      else render();
      const again = list.querySelector(`.yu-item[data-key="${item.key}"] .yu-edit`) || list.querySelector(`.yu-item[data-key="${item.key}"] .yu-src`);
      if (again) again.focus({ preventScroll: true });
    };
    ctl.addEventListener("change", () => commit(true));
    ctl.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); commit(false); } if (e.key === "Enter") { e.preventDefault(); commit(true); } });
    ctl.addEventListener("blur", () => commit(true));
  }
  function render() {
    const m = Y.cardModel(Ys);
    card.hidden = !m;
    if (!m) { ask.hidden = true; fold(); return; }
    list.replaceChildren(...m.rows.map((row) => h("div", { class: "yu-r", "data-key": row.key },
      h("dt", { class: "yu-l", text: row.label }),
      h("dd", { class: "yu-d" }, row.items.map((it) => h("span", { class: "yu-item", "data-key": it.key },
        h("span", { class: `yu-v${it.num ? " fig" : ""}`, text: it.text }), tag(it, row)))))));
    kw.hidden = !m.keyword; kw.textContent = m.keyword || "";
    clash.replaceChildren(...m.conflicts.map((c) => {
      const back = h("button", { type: "button", class: "linkbtn yu-back", text: Y.USE_WORDS });
      back.addEventListener("click", () => { delete Ys.edits[c.key]; Ys.edited = Ys.edited.filter((k) => k !== c.key); publish(); });
      return h("p", { class: "yu-clash-l" }, h("span", { text: c.line }), " ", back);
    }));
    clash.hidden = !m.conflicts.length;
    ask.hidden = !m.clarify || !live();
    qSkip.hidden = !m.canRun;
    qText.textContent = m.clarify ? `One question: ${m.clarify}` : "";
    if (!card.dataset.shown && !still()) { card.dataset.in = "0"; requestAnimationFrame(() => requestAnimationFrame(() => { card.dataset.in = "1"; })); }
    card.dataset.shown = "1";
    fold();
  }

  /* ---- reading the words (live) ---- */
  async function readWords(text) {
    const body = Y.readBody(text);
    if (!body) { say("Write a sentence or two about yourself first.", "need"); ta.focus(); return; }
    const mine = ++seq;
    Ys.busy = true; readBtn.setAttribute("aria-disabled", "true"); say(Y.READING, "busy"); el.dataset.busy = "1";
    let json = null, problem = null;
    try {
      const res = await fetch("/api/profile/read", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      try { json = await res.json(); } catch (e) { json = null; }
      if (!res.ok && !(res.status === 503 && json && json.profile)) problem = (json && (json.message || json.detail)) || "The reader could not be reached. Try again.";
    } catch (e) { problem = "The server could not be reached. Check the connection, then try again."; }
    if (mine !== seq) return;
    Ys.busy = false; readBtn.removeAttribute("aria-disabled"); el.dataset.busy = "0";
    const r = problem ? null : Y.readOf(json);
    if (!r || !Y.usable(r)) { say(problem || (r && r.message) || "These words could not be read as a profile. Try other words.", "error"); return; }
    Ys.text = body.text; Ys.read = r; Ys.edits = {}; Ys.edited = []; Ys.skip = false; wording = r.status === "clarify";
    say(r.status === "clarify" ? "" : "Read. Check the card, then replay.", "ok");
    readBtn.textContent = Y.AGAIN_LABEL;
    syncHoldings(true);
    if (r.move) store.set({ question: r.move });
    publish();
    if (r.status === "clarify") requestAnimationFrame(() => qIn.focus({ preventScroll: false }));
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); if (!live()) return; if (!Ys.busy) readWords(ta.value); });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
  ask.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!qIn.value.trim() || Ys.busy) { qIn.focus(); return; }
    const text = Y.withAnswer(ta.value || Ys.text, qIn.value);
    ta.value = text; qIn.value = "";
    readWords(text);
  });

  /* the neutral mix on lane hold's card (assumed: edit it) and the amount the words gave it */
  function syncHoldings(fromRead) {
    const s0 = st(), cur = s0.holdings && s0.holdings.pilot === Y.YOU ? s0.holdings : null, amount = Y.valueOf(Ys, "amount");
    if (!cur) store.set({ holdings: { pilot: Y.YOU, portfolio: { ...Y.NEUTRAL }, amount: amount || null, assumed: true } });
    else if (fromRead && amount && (cur.assumed || !cur.amount)) store.set({ holdings: { ...cur, amount } });
  }

  /* ---- the static demo: the one recorded example, or one honest line ---- */
  async function loadExample() {
    if (exampleTried) return example;
    exampleTried = true;
    const file = meta("you");
    if (!file) return null;
    try {
      const j = await fetch(new URL(file, document.baseURI), { cache: "no-store" }).then((r) => (r.ok ? r.json() : null));
      example = Y.exampleOf(j);
      if (example && example.file && !example.result) {
        const saved = await fetch(new URL(example.file, document.baseURI), { cache: "no-store" }).then((r) => (r.ok ? r.json() : null));
        const res = saved && saved.result && saved.key ? saved.result : saved;
        if (res && res.pilot === Y.YOU) example.result = res;
      }
    } catch (e) { example = null; }
    return example;
  }
  async function showStatic() {
    ta.readOnly = true; readBtn.hidden = true; note.hidden = true;     // nothing is read here: no privacy line to give
    const ex = await loadExample();
    if (st().investor !== Y.YOU) return;
    /* no recorded example: the honest line, and no move or Replay to press (they would replay nothing of yours) */
    if (hero) hero.dataset.youStatic = ex ? "0" : "1";
    if (!ex) { say(Y.STATIC_LINE, "static"); ta.placeholder = Y.EXAMPLE; return; }
    ta.value = ex.text; Ys.text = ex.text; Ys.read = ex.read;
    note.textContent = Y.EXAMPLE_LINE; note.hidden = false;           // the box folds to the words: the honest line goes under the card
    syncHoldings(true); publish();
    if (ex.result) { lastYou = ex.result; reland(); }
  }
  async function reland() {
    if (!lastYou || st().investor !== Y.YOU || st().result === lastYou) return;
    try { const d = await import("../data.js"); d.land(lastYou, { question: typeof lastYou.question === "string" ? lastYou.question : "" }); }
    catch (e) { console.warn("[you] the last run did not come back:", e && e.message); }
  }

  /* ---- the store ---- */
  function onInvestor() {
    const s0 = st(), on = s0.investor === Y.YOU;
    el.hidden = !on;
    if (hero) hero.dataset.you = on ? "1" : "0";
    if (!on) return;
    syncHoldings(false);
    const r = s0.result, ownQ = r && r.pilot !== Y.YOU && norm(s0.question) === norm(r.question);
    if (live() && !lastYou && (!norm(s0.question) || ownQ)) store.set({ question: (Ys.read && Ys.read.move) || DEFAULT_MOVE() });
    if (!live()) { showStatic(); return; }
    if (hero) hero.dataset.youStatic = "0";
    ta.readOnly = false; readBtn.hidden = false; note.hidden = false; note.textContent = Y.PRIVACY;
    if (!Ys.read) say("", "");
    reland();
  }
  store.on("investor", onInvestor);
  store.on("mode", () => { if (st().investor === Y.YOU) onInvestor(); });
  store.on("result", (r) => { if (r && r.pilot === Y.YOU) lastYou = r; });
  /* Replay before the card can run (no words read yet, or the amount is still missing): the box says what is needed */
  store.on("replay", () => {
    const s0 = st();
    if (s0.investor !== Y.YOU || Y.youGate(s0, s0.result) !== "wait") return;
    if (!live()) { if (!example) say(Y.STATIC_LINE, "need"); return; }
    if (Ys.read && Ys.read.status === "clarify") { say("Answer the one question first, then replay.", "need"); qIn.focus(); return; }
    say(Y.WAIT_LINE, "need"); ta.focus();
  });
  onInvestor();
  return { el, state: () => ({ ...Ys }) };
}
