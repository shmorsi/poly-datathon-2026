/* "Try another move" (lane picker, ruling R24): one row under the hero's question, three controls (the asset, the size, where
   the money comes from) and the hero's one Replay button. Not a section of its own: sections/hero.js mounts it inside its form
   (mountPicker(el, store, api)). The question box stays the single source. Live: a choice composes "What if I put N % in
   <public name>?" (every holding scaled down equally) or "What if I move N % of my money from <holding> into <asset>?" into
   the box, and the Replay button runs it (the existing path: store.question + replay -> sections/replay.js -> POST /api/run).
   Static: a saved move (runs/moves.json, announced by <meta name="epicentre-moves">) loads its saved run; any other choice
   says once that it runs on the live app. The picker reads the box back, so typed words, a landed run and a pick agree.
   Words and rules: web/lib/movepicker.js (pure, tested). DOM from createElement and textContent only (R16). */
import { NO_MOVE, OWN, CUSTOM, EQUAL, EQUAL_FACE, DEFAULT_PCT, TITLE, PLACEHOLDER, CUSTOM_LABEL, SAVED_LABEL, assetOptions, askName, clampPct, stepPct, decide,
  stateOf, snapPct, snapFrom, chips, pressedOf, ownLabel, honestLine, hintLine, overLine, fromOptions, movesSource, normalizeMoves, safeLiveUrl,
  possessive } from "../lib/movepicker.js";
import { plainLabel } from "../lib/funds.js";
import { createList } from "./movelist.js";
import { customFor } from "../lib/hold.js";
import { loadRun, peekRun, land } from "../data.js";

const SVG = "http://www.w3.org/2000/svg";
function h(tag, attrs = {}, ...kids) {         // elements from data: textContent and attributes, never HTML strings
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") n.textContent = v; else if (k === "class") n.className = v; else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}
function glyph(cls, d) {                       // a small stroked icon (chevron, minus, plus), drawn here: no symbol to load
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", cls); s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", d); p.setAttribute("fill", "none"); p.setAttribute("stroke", "currentColor"); p.setAttribute("stroke-width", "1.6");
  p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
}
const meta = (name) => { const m = document.querySelector(`meta[name="epicentre-${name}"]`); return m ? m.content : null; };
const liveUrl = () => safeLiveUrl(globalThis.EPI_LIVE_URL) || safeLiveUrl(meta("live"));
const still = () => globalThis.EPI_MOTION === false || document.documentElement.classList.contains("motion-off") ||
  (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);

function build() {
  const U = {};
  U.lead = h("p", { class: "mp-lead", id: "mp-lead", text: TITLE });
  /* the asset: a face (dot, name, ticker, chevron) under the real select, which takes every click, key and tap */
  U.dot = h("span", { class: "mp-dot", "aria-hidden": "true" });
  U.name = h("span", { class: "mp-name" });
  U.tk = h("span", { class: "mp-tk" });
  U.select = h("select", { class: "mp-select", id: "mp-asset", "aria-label": "The asset of the move" });
  U.own = h("option", { value: OWN });
  U.custom = h("option", { value: CUSTOM, hidden: true, disabled: true, text: CUSTOM_LABEL });
  U.select.append(U.own, U.custom);
  for (const g of assetOptions()) {
    const og = h("optgroup", { label: g.label });
    for (const o of g.options) og.append(h("option", { value: o.ticker, text: o.text }));
    U.select.append(og);
  }
  U.asset = h("div", { class: "mp-field mp-asset" },
    h("span", { class: "mp-face", "aria-hidden": "true" }, U.dot, U.name, U.tk, glyph("mp-chev", "M4 6.5 8 10.5 12 6.5")), U.select);
  /* the size: minus, the readout (a real number field), plus; the level line is the size out of 50 % */
  U.minus = h("button", { class: "mp-step", type: "button", "data-dir": "-1", "aria-label": "Smaller move", "aria-controls": "mp-pct" }, glyph("mp-step-i", "M3.5 8h9"));
  U.plus = h("button", { class: "mp-step", type: "button", "data-dir": "1", "aria-label": "Larger move", "aria-controls": "mp-pct" }, glyph("mp-step-i", "M3.5 8h9M8 3.5v9"));
  U.pct = h("input", { class: "mp-pct", id: "mp-pct", type: "number", min: 1, max: 50, step: 1, inputmode: "numeric",
    "aria-label": "Size of the move, in percent of the money" });
  U.digits = h("span", { class: "mp-digits" }, U.pct, h("span", { class: "mp-unit", "aria-hidden": "true", text: "%" }));
  U.fill = h("i");
  U.size = h("div", { class: "mp-size", role: "group", "aria-label": "Size of the move" },
    U.minus, U.digits, U.plus, h("span", { class: "mp-gauge", "aria-hidden": "true" }, U.fill));
  /* where the money comes from: every other holding in proportion (the default), or one of today’s holdings */
  U.fromName = h("span", { class: "mp-name" });
  U.fromTk = h("span", { class: "mp-tk" });
  U.fromSel = h("select", { class: "mp-select", id: "mp-from", "aria-label": "Where the money comes from" });
  U.from = h("div", { class: "mp-field mp-from" },
    h("span", { class: "mp-face", "aria-hidden": "true" }, h("span", { class: "mp-pre", text: "from" }), U.fromName, U.fromTk,
      glyph("mp-chev", "M4 6.5 8 10.5 12 6.5")), U.fromSel);
  U.row = h("div", { class: "mp-row", role: "group", "aria-labelledby": "mp-lead" }, U.asset, U.size, U.from);
  U.saved = h("div", { class: "mp-saved", role: "group", "aria-label": SAVED_LABEL, hidden: true });
  U.note = h("p", { class: "mp-note", role: "status", "aria-live": "polite", hidden: true });
  return U;
}

/* api (from sections/hero.js): text() the box's words, write(q) put words in the box (the reader's), follow(cue) let the box show
   the run on screen again (cue: the picker put it there, so the words settle in and the Replay pill rings once), name(id) the
   investor's label ("Robert", "Too Canadian?", "You"), onText(fn) after the box changes */
export function mountPicker(el, store, api) {
  const U = build();
  /* pct: the size shown; pick: a choice not on screen yet (loading, or static with no saved run); busy: the latest load wins */
  const S = { who: null, pct: DEFAULT_PCT, moves: [], movesFor: null, fromFor: null, busy: 0, note: null, hintTk: null, pick: null };
  el.classList.add("mp");
  el.replaceChildren(U.lead, U.row, U.saved, U.note);
  const st = () => store.get();
  const label = () => api.name(st().investor);
  const ownRun = () => peekRun(st().investor);
  const ownTicker = (own) => { const P = globalThis.PF, mv = P && P.moveOf ? P.moveOf(own) : null; return mv ? mv.ticker : null; };
  /* today's mix, where "from" draws: the holdings the reader edited (lane hold, live), else the investor's saved run */
  const edited = () => customFor(st().holdings, st().investor);
  const mixOf = () => {
    const c = edited(), r = st().result;
    return c ? { pilot: st().investor, portfolio: c.portfolio } : (ownRun() || (r && r.pilot === st().investor ? r : null));   // never another investor's mix
  };
  /* fine pointers: the two lists open as the instrument's own panel (web/sections/movelist.js); touch keeps the system menu */
  const assetRows = () => [{ value: OWN, name: ownLabel(label()), top: true }, ...assetOptions().flatMap((g) => [{ group: g.label },
    ...g.options.map((o) => ({ value: o.ticker, name: o.name, ticker: o.ticker, hint: o.hint && o.hint !== g.label.toLowerCase() ? o.hint : null }))])];
  U.list = createList(U.asset, U.select, assetRows(), { labelledby: "mp-lead" });
  U.fromList = createList(U.from, U.fromSel, [], { labelledby: "mp-lead" });
  /* data-taken-from: lane u2b's "Change one thing" on the stage finds the source control by it and opens it, so it marks the one
     a reader can see: the list's face on a fine pointer (it opens on click), the select on a touch screen (showPicker) */
  const fine = typeof matchMedia === "function" ? matchMedia("(hover: hover) and (pointer: fine)") : null;
  const markTakenFrom = () => {
    const face = U.from.querySelector(".mp-open"), onFace = !!(fine && fine.matches);
    (onFace ? face : U.fromSel).setAttribute("data-taken-from", "");
    (onFace ? U.fromSel : face).removeAttribute("data-taken-from");
  };
  markTakenFrom();
  if (fine && fine.addEventListener) fine.addEventListener("change", markTakenFrom);

  /* ---- the note: one line at most: the honest line (static), else what the source holds, else what is inside a fund ---- */
  function note(kind, tk) {
    S.note = kind; S.hintTk = kind === "hint" ? tk : null;
    U.note.replaceChildren();
    if (kind === "honest") {
      const line = honestLine(liveUrl());
      U.note.append(line.text);
      if (line.link) U.note.append(" ", h("a", { href: line.link.href, rel: "noopener", text: line.link.text }));
    } else if (kind === "hint") {
      const line = hintLine(tk, st().result);
      if (line) U.note.append(line);
    } else if (kind === "unread") U.note.append("This saved replay could not be read. Try it again.");
    U.note.hidden = !U.note.textContent;
  }

  /* ---- what the box says (or the choice on its way), shown in the three controls ---- */
  function render() {
    const s = st();
    /* another investor: their own size (or 20 %), whichever render comes first (app.js lands a cached run before our listener) */
    if (S.who !== s.investor) { S.who = s.investor; S.pct = DEFAULT_PCT; S.pick = null; }
    const own = ownRun();
    const box = stateOf({ text: api.text(), own, pct: S.pct }), now = S.pick || box;
    const tk = now.value === OWN ? (now.sized ? ownTicker(own) : null) : now.value === CUSTOM ? null : now.value;
    S.pct = now.pct;
    U.own.textContent = ownLabel(label());
    U.select.value = now.value;
    U.list.setLabel(OWN, ownLabel(label()));
    U.list.sync();
    U.asset.classList.toggle("is-move", !!tk);
    U.asset.classList.toggle("is-empty", !tk);
    U.name.textContent = tk ? askName(tk) : now.value === CUSTOM ? CUSTOM_LABEL : PLACEHOLDER;
    U.tk.textContent = tk || "";
    setPct(now.pct, 0);
    const off = !now.sized;
    U.size.classList.toggle("is-off", off);
    U.minus.disabled = off || now.pct <= 1; U.plus.disabled = off || now.pct >= 50; U.pct.disabled = off;
    renderFrom(tk, off ? EQUAL : now.from);
    renderSaved(box);                            // the chips mark the run on screen, never a choice on its way
    const over = tk && !off ? overLine(mixOf(), edited() ? null : label(), now.from, now.pct) : null;
    if (S.note === "honest" || S.note === "unread") return;
    if (over) { S.note = "over"; S.hintTk = null; U.note.replaceChildren(over); U.note.hidden = false; return; }
    if (S.note === "over") note(null);
    if (S.note === "hint") note(S.hintTk === tk ? "hint" : null, tk);   // a fund's words follow the run on screen (looked inside?)
  }
  function renderFrom(tk, from) {
    const opts = fromOptions(mixOf(), tk), key = `${st().investor}|${tk}|${opts.map((o) => o.value).join(",")}`;
    if (S.fromFor !== key) {
      S.fromFor = key;
      U.fromSel.replaceChildren(...opts.map((o) => h("option", { value: o.value, text: o.text })));
      U.fromList.rebuild(opts.map((o) => (o.value === EQUAL ? { value: o.value, name: o.text, top: true }
        : { value: o.value, name: plainLabel(o.value), ticker: o.value })));
    }
    const value = opts.some((o) => o.value === from) ? from : EQUAL;
    U.fromSel.value = value;
    U.fromName.textContent = value === EQUAL ? EQUAL_FACE : plainLabel(value);
    U.fromTk.textContent = value === EQUAL ? "" : value;
    U.from.classList.toggle("is-equal", value === EQUAL);
    U.fromSel.disabled = !tk;
    U.from.classList.toggle("is-off", !tk);
    U.from.querySelector(".mp-open").disabled = !tk;
    U.fromList.sync();
  }
  function setPct(p, dir) {
    if (String(U.pct.value) !== String(p)) U.pct.value = String(p);
    U.size.style.setProperty("--p", String(clampPct(p) / 50));
    if (dir && !still()) {                       // the digits roll one notch, the way the press went (an instrument's counter)
      U.digits.classList.remove("is-up", "is-down"); void U.digits.offsetWidth;
      U.digits.classList.add(dir > 0 ? "is-up" : "is-down");
    }
  }

  /* ---- static mode: the investor's own question and saved moves as chips (the one chip style) ---- */
  function renderSaved(box) {
    const s = st();
    if (s.mode !== "static") {                   // live: one chip, the mix as it is (no move); the words go in the box
      if (S.movesFor !== "live") {
        S.movesFor = "live";
        const b = h("button", { class: "chip mp-chip", type: "button", "aria-pressed": "false", text: NO_MOVE.label });
        b.addEventListener("click", () => { S.pick = null; note(null); api.write(NO_MOVE.question); render(); });
        U.saved.replaceChildren(b);
        U.saved.setAttribute("aria-label", "Replay without a move");
      }
      U.saved.hidden = false;
      return;
    }
    const list = chips(S.moves, s.investor, label());
    if (S.movesFor !== s.investor || U.saved.childElementCount !== list.length) {
      S.movesFor = s.investor;
      U.saved.replaceChildren(...list.map((c) => {
        const b = h("button", { class: "chip mp-chip", type: "button", "aria-pressed": "false", text: c.label });
        b.addEventListener("click", () => (c.own ? choose(OWN) : loadSaved(c.move)));   // a chip is its own saved run
        return b;
      }));
      U.saved.setAttribute("aria-label", possessive(label()) ? `${SAVED_LABEL} for ${label() === "You" ? "you" : label()}` : SAVED_LABEL);
    }
    const pressed = pressedOf(list, s.result, box);   // the run on screen, so the own question and "with your own limit" differ
    list.forEach((c, i) => U.saved.children[i].setAttribute("aria-pressed", String(pressed[i])));
    U.saved.hidden = list.length < 2;            // the own question alone needs no chip (the list offers it)
  }
  function loadMoves() {
    const src = movesSource({ mode: st().mode, announced: meta("moves") });
    if (!src) return;                            // no announced moves.json: no request at all (lane U0's build hook)
    fetch(new URL(src.url, document.baseURI), { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { S.moves = normalizeMoves(j); S.movesFor = null; render(); })
      .catch(() => { S.moves = []; });           // unreadable: the own question only, quietly
  }

  /* ---- one choice, one action ---- */
  const runs = new Map();
  function runOf(m) {
    if (m.result) return Promise.resolve(m.result);
    if (!runs.has(m.key)) {
      runs.set(m.key, fetch(new URL(m.file, document.baseURI), { cache: "no-store" })
        .then((r) => { if (!r.ok) throw new Error(`saved run ${r.status}`); return r.json(); })
        .catch((e) => { runs.delete(m.key); throw e; }));
    }
    return runs.get(m.key);
  }
  function show(r, investor) {                   // a saved run on screen, as an investor change does (data.js land)
    if (st().investor !== investor) return;
    S.pick = null;
    if (st().result !== r) land(r, { question: r.question });
    api.follow(true);
  }
  /* snap (static): a new asset or source goes to a saved source and size, so the list never strands the reader; a size the
     reader set is kept as set */
  function choose(value, pct, from, snap) {
    const s = st(), investor = s.investor, statik = s.mode === "static" && value !== OWN;
    const src = statik && snap ? snapFrom(S.moves, investor, value, from || EQUAL) : (from || EQUAL);
    const size = clampPct(pct === undefined ? S.pct : pct), asked = statik && snap ? snapPct(S.moves, investor, value, size, src) : size;
    const d = decide({ mode: s.mode, investor, choice: { value, pct: asked, from: src }, moves: S.moves });
    const b = ++S.busy;
    if (d.kind === "write") { S.pick = null; note(null); api.write(d.question); note("hint", value); render(); return; }
    if (d.kind === "honest") { S.pick = { value, pct: asked, sized: true, from: src }; note("honest"); render(); return; }
    if (d.kind === "own") {
      note(null); S.pick = null;
      loadRun(investor).then((r) => { if (b === S.busy) show(r, investor); }, () => { if (b === S.busy) api.follow(); });
      return;
    }
    if (d.kind === "load") loadSaved(d.move, b);
  }
  /* one saved run on screen (a chip, or a saved pick from the list); the face answers at once */
  function loadSaved(m, busy) {
    const investor = st().investor, b = busy || ++S.busy;
    S.pick = { value: m.ticker, pct: m.pct, sized: true, from: fromOf(m.from) }; note(null); render();
    runOf(m).then((r) => {
      if (b !== S.busy) return;
      if (r && r.pilot === investor && r.status !== "error") { show(r, investor); note("hint", m.ticker); render(); } else note("unread");
    }, () => { if (b === S.busy) note("unread"); });
  }
  const fromOf = (f) => (f ? f : EQUAL);

  /* ---- the reader's controls ---- */
  const sizedTicker = () => {                    // the asset the size applies to: the one shown, or the own question's move
    const v = U.select.value;
    return v === OWN ? ownTicker(ownRun()) : v === CUSTOM ? null : v;
  };
  U.select.addEventListener("change", () => choose(U.select.value, undefined, U.fromSel.value, true));
  U.fromSel.addEventListener("change", () => { const tk = sizedTicker(); if (tk) choose(tk, S.pct, U.fromSel.value, true); });
  for (const b of [U.minus, U.plus]) b.addEventListener("click", () => {
    const tk = sizedTicker(); if (!tk) return;
    const dir = Number(b.dataset.dir), next = stepPct(S.pct, dir);
    S.pct = next; setPct(next, dir); choose(tk, next, U.fromSel.value);
  });
  const commit = () => { const tk = sizedTicker(); if (!tk) return; const p = clampPct(U.pct.value); S.pct = p; setPct(p, 0); choose(tk, p, U.fromSel.value); };
  U.pct.addEventListener("change", commit);
  U.pct.addEventListener("keydown", (e) => { if (e.key === "Enter") commit(); });   // then the form's Replay runs it (implicit submit)

  /* ---- the store and the box: the hero calls onText after the box shows a new run's words (or the reader's) ---- */
  store.on("investor", () => { S.busy += 1; note(null); });   // a load still on its way belongs to the investor before
  store.on("mode", () => render());
  store.on("holdings", () => render());           // edited holdings (lane hold): "from" offers what they hold
  api.onText(() => { S.pick = null; render(); });
  render();
  loadMoves();
  return { render };
}
