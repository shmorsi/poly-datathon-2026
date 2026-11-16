/* EPICENTRE Replay, lane hold: what each investor holds, and what is inside the funds. Not a section of its own (index.html
   names none): hero.js mounts the list under the investor picker and replay.js mounts the strip beside the move chip; both are
   plain mount(el, store) pieces, so they can move. DOM by createElement / textContent only (R16); words and numbers from
   web/lib/hold.js (pure, node-tested); every number is a Result key or amount x weight.
   mountHoldings(el, store)  "What Robert holds today": one row per holding (plain label, ticker, weight, dollars), today's
                             stacked bar, ONE look-through line and the "What's inside the funds" disclosure (countries and
                             industries, today vs with the move, the funds' public names, the holdings date and coverage).
                             Simple: the list and the line; the disclosure opens on a click, or with the page's Detailed switch.
   mountMoveStrip(el, store) TODAY vs WITH THE MOVE: two thin stacked bars, the same tone per holding, the move in magenta;
                             each part names itself on hover or tap; hidden when the question has no move. */
import { holdModel, stripModel, lookModel, WHY, EDITED_TITLE, seedRows, totalOf, totalOk, editProblems, customFrom, customFor, customModel,
  ranOn, resetLabel, staticEditLine, youSeed, YOU_ASSUMED, limitsCard, limitWordsLine } from "../lib/hold.js";
import { UNIVERSE, plainLabel, fundName, universeGroups } from "../lib/funds.js";
import { sharebarModel, sharebar } from "../lib/sharebar.js";   // lane funds: ONE share bar for every breakdown of the money
import { mean } from "./clarity.js";
import { keepRanges } from "../lib/meaning.js";

const PF = () => globalThis.PF;
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
const SVG = "http://www.w3.org/2000/svg";
function chevron() {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "cl-chev"); s.setAttribute("viewBox", "0 0 12 12"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  for (const [k, v] of Object.entries({ d: "M2.5 4.5 6 8l3.5-3.5", fill: "none", stroke: "currentColor", "stroke-width": "1.6", "stroke-linecap": "round", "stroke-linejoin": "round" })) p.setAttribute(k, v);
  s.append(p);
  return s;
}
function ensureCss() {                       // the integrated page links it; a harness that does not still gets it once
  if (typeof document === "undefined" || document.querySelector('link[href$="css/hold.css"]')) return;
  document.head.append(h("link", { rel: "stylesheet", href: new URL("../css/hold.css", import.meta.url).href }));
}
/* an icon from the page's sprite (index.html's symbols) */
function sprite(id, cls) {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", cls || "hd-i"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  const u = document.createElementNS(SVG, "use");
  u.setAttribute("href", `#${id}`);
  s.append(u);
  return s;
}
const segsInto = (el, segs, meaning) => el.replaceChildren(...(segs || []).map(([t, k]) =>
  (k === "num" ? mean(h("span", { class: "fig hd-fig", text: t }), meaning, { focus: false }) : document.createTextNode(keepRanges(t)))));
const tone = (t) => (t === "move" ? "move" : `t${t}`);

/* the page's one share bar (lane funds, web/lib/sharebar.js): its segments, tones, tooltip and keyboard; here without its own
   legend (step 1 names its parts under its ticks; the stage and #investors stay one line) */
function shareBar(rows, P, label, cls) {
  const model = sharebarModel(rows.map((r) => ({ id: r.id, label: r.label, items: r.segs.map((x) => ({ key: x.ticker, name: x.label,
    share: x.weight, dollars: isNum(x.dollars) ? x.dollars : undefined, move: x.tone === "move" })) })), { top: 6 });
  const fig = sharebar(model, { fmt: P && P.fmt, label, family: "fund", unit: "of the money" });
  fig.classList.add("hd-sb", cls);
  return fig;
}
const isNum = (x) => typeof x === "number" && Number.isFinite(x);

/* ---- the hero card: step 1, what the investor holds now (RETHINK G10: an instrument panel, not a spreadsheet) ---- */
let insideOpen = null, whyOpen = null, rowsOpen = null, limitsOpen = null;   // the reader's own choices while the page lives (null = follow the depth switch)
function info() {                            // the small (i): the stage's own shape
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "hd-i"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  const c = document.createElementNS(SVG, "circle");
  for (const [k, v] of Object.entries({ cx: 12, cy: 12, r: 9.5, fill: "none", stroke: "currentColor", "stroke-width": 1.6 })) c.setAttribute(k, v);
  const p = document.createElementNS(SVG, "path");
  for (const [k, v] of Object.entries({ d: "M12 10.6v6", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" })) p.setAttribute(k, v);
  const d = document.createElementNS(SVG, "circle");
  for (const [k, v] of Object.entries({ cx: 12, cy: 7.4, r: 1.25, fill: "currentColor" })) d.setAttribute(k, v);
  s.append(c, p, d);
  return s;
}
/* lane funds' drawer (web/sections/fundpage.js, lazy): a fund's own page, or "owning" (what the money ends up owning). Wired
   only once the page links its stylesheet (css/fundpage.css), so nothing is fetched before the drawer exists; without it, the
   card keeps its own inline "What's inside the funds" */
const hasDrawer = () => typeof document !== "undefined" && !!document.querySelector('link[href$="css/fundpage.css"]');
const openFunds = (store, what, opener) => import("./fundpage.js").then((m) => m.openFunds(store, what, opener));
const still = () => globalThis.EPI_MOTION === false || document.documentElement.classList.contains("motion-off") ||
  (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);

export function mountHoldings(el, store) {
  ensureCss();
  el.classList.add("hd");
  el.setAttribute("role", "group");
  el.setAttribute("aria-labelledby", "hd-title");
  /* step 1 of the hero's three (lane picker writes 2 and 3 the same way: a 1 px ring, the digit, the label) */
  const name = h("span", { class: "hd-name" });
  const title = h("h2", { class: "hd-title step", id: "hd-title" }, h("span", { class: "step-n", "aria-hidden": "true", text: "1" }),
    h("span", { class: "sr", text: "Step 1: " }), name, " ", h("span", { class: "hd-fic", text: "(fictional)" }));
  const total = h("p", { class: "hd-total" });
  const gauge = h("div", { class: "hd-gauge" });
  const list = h("ul", { class: "hd-list", id: "hd-list", "aria-labelledby": "hd-title" });
  /* Simple: the bar and its readouts; the rows (tickers, weights, dollars) one tap away; Detailed: the rows */
  const rowsBtn = h("button", { type: "button", class: "cl-more hd-more hd-rows-btn", "aria-expanded": "false", "aria-controls": "hd-list" },
    h("span", { class: "cl-more-word", text: "Show the holdings" }), chevron());
  const lookText = h("span", { class: "hd-look-text" });
  const look = h("p", { class: "hd-look" }, lookText);
  const said = h("p", { class: "hd-said", hidden: true });     // limit words in a persona's question: where they work (limits-QA 5)
  const word = h("span", { class: "cl-more-word", text: "What’s inside the funds" });
  const btn = h("button", { type: "button", class: "cl-more hd-more", "aria-expanded": "false", "aria-controls": "hd-inside" }, word, chevron());
  const panel = h("div", { class: "hd-inside", id: "hd-inside", role: "region", "aria-label": "What’s inside the funds", hidden: true });
  const fold = h("div", { class: "hd-fold" }, panel);
  /* why these five years (the lead, 14:40: "what's the point of 2021?"): one quiet line, its answer one tap away */
  const whyText = h("span", { class: "hd-why-text", id: "hd-why-text" }, keepRanges(WHY.answer), " ",
    h("a", { class: "hd-why-link", href: "#deep", text: WHY.link }), ".");
  const whyBtn = h("button", { type: "button", class: "hd-why-btn", "aria-expanded": "false", "aria-controls": "hd-why-text" },
    info(), h("span", { text: keepRanges(WHY.question) }));
  const why = h("p", { class: "hd-why", hidden: true }, whyText);
  /* edit the holdings (coordinator item 4): the live app sends them with the question; the static demo says why it cannot */
  const editBtn = h("button", { type: "button", class: "hd-why-btn hd-edit-btn", "aria-expanded": "false", "aria-controls": "hd-editor" },
    sprite("i-edit", "hd-i"), h("span", { text: "Edit holdings" }));
  const resetBtn = h("button", { type: "button", class: "linkbtn hd-reset", hidden: true });
  /* the static demo: one honest line, then the whitelist the live app's editor picks from (read-only) */
  const staticWords = h("p", { class: "hd-static-line" });
  const staticLine = h("div", { class: "hd-static", id: "hd-static", hidden: true }, staticWords,
    h("p", { class: "hd-uni-lead", text: `On the live app, you build a mix from these ${UNIVERSE.length} assets (real 2021–26 prices for each):` }),
    h("dl", { class: "hd-uni" }, universeGroups().flatMap((g) => [h("dt", { text: g.label }),
      h("dd", {}, g.tickers.map((tk) => h("span", { class: "hd-uni-a", title: fundName(tk) }, plainLabel(tk), h("span", { class: "hd-tk", text: ` ${tk}` }))))])));
  const editor = h("form", { class: "hd-editor", id: "hd-editor", "aria-label": "Edit the holdings", novalidate: true, hidden: true });
  /* the limits card (LIMITS_MODEL.md): each limit, its value, where it came from, an edit pencil; "set by you" is #checklist's editor */
  const limBtn = h("button", { type: "button", class: "cl-more hd-more hd-lim-btn", "aria-expanded": "false", "aria-controls": "hd-limits" },
    h("span", { class: "cl-more-word", text: "Your limits" }), chevron());
  const limits = h("div", { class: "hd-limits", id: "hd-limits", role: "region", "aria-label": "Your limits", hidden: true });
  limBtn.addEventListener("click", () => { limitsOpen = limBtn.getAttribute("aria-expanded") !== "true"; setLimits(limitsOpen); });
  const setLimits = (on) => { limBtn.setAttribute("aria-expanded", String(on)); limits.hidden = !on; };
  const actions = h("div", { class: "hd-actions" }, rowsBtn, limBtn, btn, whyBtn, editBtn, resetBtn);   // lane polish-hero's order, then the limits
  el.replaceChildren(h("div", { class: "hd-head" }, title, total), gauge, list, look, said, actions, staticLine, editor, limits, fold, why);
  /* the pencil and "+ Add a limit": #checklist's own limits editor (live: POST /api/recheck; static: its honest line) */
  function editLimits(opener) {
    const ck = document.querySelector("#checklist .ck-you-edit");
    if (!ck || ck.disabled || store.get().mode !== "live") {
      const why = limits.querySelector(".hd-lim-why");
      if (why) { why.hidden = false; why.focus && why.focus({ preventScroll: true }); }
      return;
    }
    const sec = ck.closest(".ck-you") || ck;
    sec.scrollIntoView({ block: "start", behavior: still() ? "auto" : "smooth" });
    if (ck.getAttribute("aria-expanded") !== "true") ck.click();
    void opener;
  }
  /* folded (Simple, desktop): the head, the bar and its readouts, the look-through line and one row of actions; the rows and
     "What's inside the funds" come back with "Show the holdings" (hold.css; phones always show the rows) */
  const setRows = (on) => {
    rowsBtn.setAttribute("aria-expanded", String(on));
    rowsBtn.firstChild.textContent = on ? "Hide the holdings" : "Show the holdings";
    el.dataset.rows = on ? "1" : "0";
  };
  rowsBtn.addEventListener("click", () => { rowsOpen = rowsBtn.getAttribute("aria-expanded") !== "true"; setRows(rowsOpen); });
  let editing = false, draft = null;
  const live = () => store.get().mode === "live";
  editBtn.addEventListener("click", () => {
    if (!live()) {                           // the static demo: one honest line, no editor
      const on = staticLine.hidden;
      staticLine.hidden = !on; editBtn.setAttribute("aria-expanded", String(on)); editBtn.setAttribute("aria-controls", "hd-static");
      return;
    }
    openEditor();
  });
  resetBtn.addEventListener("click", () => {
    const s0 = store.get(), r0 = youSeed(s0) || s0.result, own = customFor(s0.holdings, r0 && r0.pilot), pilot = r0 && r0.pilot;
    store.set({ holdings: null });
    if (own && ranOn(own, r0) && pilot) {    // the run on screen used the edited holdings: back to the investor's saved run
      import("../data.js").then((d) => d.loadRun(pilot).then((saved) => { if (saved && store.get().investor === pilot) d.land(saved); }))
        .catch((e) => console.warn("[holdings] the saved run did not come back:", e && e.message));
    }
    editBtn.focus({ preventScroll: true });
  });
  function openEditor() {
    const s0 = store.get(), r0 = youSeed(s0) || s0.result, own = customFor(s0.holdings, r0 && r0.pilot);
    draft = { rows: own ? Object.entries(own.portfolio).map(([ticker, w]) => ({ ticker, pct: Math.round(w * 1000) / 10 })) : seedRows(r0),
      amount: own ? own.amount : r0 && r0.amount };
    editing = true;
    render();
    const first = editor.querySelector("input");
    if (first) first.focus({ preventScroll: true });
  }
  function closeEditor(focusBack) { editing = false; draft = null; render(); if (focusBack) editBtn.focus({ preventScroll: true }); }
  function drawEditor() {
    const rows = draft.rows;
    const total = totalOf(rows), problems = editProblems(rows, draft.amount);
    const totalN = h("span", { class: "hd-ed-total-n", text: `${String(total).replace(/\.0$/, "")}\u00a0%` });
    const use = h("button", { type: "submit", class: "btn btn-quiet hd-ed-use", text: "Use these holdings" });
    if (problems.length) use.setAttribute("aria-disabled", "true");
    /* the whitelist (the 31 assets of the dataset), grouped: Canadian stocks, US stocks, funds, crypto */
    const add = h("select", { class: "hd-ed-add", id: "hd-ed-add" }, h("option", { value: "", text: "Add a holding…" }),
      universeGroups(rows.map((x) => x.ticker)).filter((g) => g.tickers.length).map((g) => h("optgroup", { label: g.label },
        g.tickers.map((tk) => h("option", { value: tk, text: `${plainLabel(tk)} (${tk})` })))));
    add.addEventListener("change", () => {
      if (!add.value) return;
      draft.rows = [...draft.rows, { ticker: add.value, pct: "" }];
      drawEditor();
      const inputs = editor.querySelectorAll(".hd-ed-pct");
      if (inputs.length) inputs[inputs.length - 1].focus();
    });
    const amt = h("input", { class: "hd-ed-amt", id: "hd-ed-amt", type: "number", inputmode: "numeric", min: "1", step: "1000", value: draft.amount == null ? "" : String(draft.amount) });
    amt.addEventListener("input", () => { draft.amount = amt.value; refresh(); });
    editor.replaceChildren(
      h("ul", { class: "hd-ed-rows", "aria-label": "The holdings and their weights" }, rows.map((x, i) => {
        const id = `hd-ed-${i}`, inp = h("input", { class: "hd-ed-pct", id, type: "number", inputmode: "decimal", min: "0", max: "100", step: "0.1",
          value: x.pct === "" || x.pct == null ? "" : String(x.pct), "aria-label": `${plainLabel(x.ticker)}, share of the money in percent` });
        inp.addEventListener("input", () => { draft.rows[i] = { ...draft.rows[i], pct: inp.value }; refresh(); });
        const rm = h("button", { type: "button", class: "hd-ed-x", "aria-label": `Remove ${plainLabel(x.ticker)}` }, sprite("i-close", "hd-i"));
        rm.addEventListener("click", () => { draft.rows = draft.rows.filter((_, j) => j !== i); drawEditor(); add.focus(); });
        return h("li", { class: "hd-ed-row" }, h("span", { class: "hd-label", text: plainLabel(x.ticker) }), h("span", { class: "hd-tk", text: x.ticker }),
          h("span", { class: "hd-ed-field" }, inp, h("span", { class: "hd-ed-unit", "aria-hidden": "true", text: "%" })), rm);
      })),
      h("div", { class: "hd-ed-line" }, h("label", { class: "sr", for: "hd-ed-add", text: "Add a holding" }), add,
        h("span", { class: "hd-ed-amount" }, h("label", { for: "hd-ed-amt", text: "Amount" }), h("span", { class: "hd-ed-unit", "aria-hidden": "true", text: "$" }), amt)),
      h("p", { class: "hd-ed-total", "aria-live": "polite" }, h("span", { text: "Total " }), totalN,
        h("span", { class: "hd-ed-need", text: problems.length ? ` ${problems.join(" ")}` : " Ready to replay." })),
      h("div", { class: "hd-ed-actions" }, use, h("button", { type: "button", class: "linkbtn hd-ed-cancel", text: "Cancel" })));
    editor.querySelector(".hd-ed-cancel").addEventListener("click", () => closeEditor(true));
    function refresh() {                     // the live total, without redrawing the fields being typed in
      const t = totalOf(draft.rows), pr = editProblems(draft.rows, draft.amount);
      totalN.textContent = `${String(t).replace(/\.0$/, "")}\u00a0%`;
      totalN.dataset.ok = totalOk(t) ? "1" : "0";
      editor.querySelector(".hd-ed-need").textContent = pr.length ? ` ${pr.join(" ")}` : " Ready to replay.";
      if (pr.length) use.setAttribute("aria-disabled", "true"); else use.removeAttribute("aria-disabled");
    }
    refresh();
  }
  editor.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const s0 = store.get(), r0 = youSeed(s0) || s0.result, custom = draft && customFrom(draft.rows, draft.amount, r0 && r0.pilot);
    if (!custom) { const t = editor.querySelector(".hd-ed-need"); if (t) t.focus && t.focus(); return; }
    store.set({ holdings: custom });
    closeEditor(true);
  });
  editor.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { ev.stopPropagation(); closeEditor(true); } });

  const setOpen = (on, animate) => {
    btn.setAttribute("aria-expanded", on ? "true" : "false");
    panel.hidden = !on;
    fold.dataset.open = on ? "1" : "0";
    panel.classList.toggle("is-new", !!(on && animate));
  };
  const setWhy = (on) => { whyBtn.setAttribute("aria-expanded", String(on)); why.hidden = !on; };
  btn.addEventListener("click", (ev) => {
    if (hasDrawer()) {                       // the drawer takes over; the inline panel only if it does not load
      openFunds(store, "owning", btn).catch((e) => { console.warn("[funds] the drawer did not load:", e && e.message); insideOpen = true; setOpen(true, false); });
      return;
    }
    const on = btn.getAttribute("aria-expanded") !== "true";
    insideOpen = on;
    setOpen(on, ev.detail !== 0);            // a keyboard action never animates
    if (on && typeof panel.scrollIntoView === "function")
      requestAnimationFrame(() => panel.scrollIntoView({ block: "nearest", behavior: still() || ev.detail === 0 ? "auto" : "smooth" }));
  });
  whyBtn.addEventListener("click", () => { whyOpen = whyBtn.getAttribute("aria-expanded") !== "true"; setWhy(whyOpen); });

  /* the gauge's readouts (desktop): under each part's own tick, its weight, and its name (else its ticker) when that fits the
     part's width; a readout that would touch the next one stays a bare tick (the row and the part's own words still say it) */
  function fitTicks() {
    const ticks = [...gauge.querySelectorAll(".hd-tick")], W = gauge.clientWidth;
    if (!W) return;
    let prevRight = -Infinity;
    const unnamed = [];                      // the cold first-time user (17:40): every part always has its plain name
    ticks.forEach((t, i) => {
      const n = t.querySelector(".hd-tick-n"), l = t.querySelector(".hd-tick-l"), last = i + 1 === ticks.length;
      t.dataset.end = "0";
      const x0 = t.offsetLeft, next = last ? W : ticks[i + 1].offsetLeft, room = next - x0 - 5 - (last ? 0 : 6);
      l.hidden = false; l.textContent = t.dataset.label;
      if (l.offsetWidth > room) { l.hidden = true; unnamed.push(t); }       // too narrow: named on the line under the bar
      const w = Math.max(n.offsetWidth, l.hidden ? 0 : l.offsetWidth);
      let left = x0 + 5, right = left + w;
      if (last && right > W) { t.dataset.end = "1"; right = W - 5; left = right - w; }    // the last readout leans on the bar's end
      const fit = left >= prevRight + 6 && right <= (last ? W : next - 6);
      t.dataset.fit = fit ? "1" : "0";
      if (fit) prevRight = right;
      else if (!l.hidden) { l.hidden = true; unnamed.push(t); }
    });
    const below = gauge.querySelector(".hd-unnamed");
    if (below) {
      below.replaceChildren(...unnamed.map((t) => h("li", { class: "hd-unn" }, h("span", { class: "hd-key", "data-tone": t.dataset.tone, "aria-hidden": "true" }),
        h("span", { class: "hd-unn-l", text: t.dataset.label }), h("span", { class: "hd-unn-tk", text: `(${String(t.dataset.ticker).replace(/\.TO$|-USD$/, "")})` }),
        t.dataset.fit === "0" ? h("span", { class: "hd-unn-w", text: t.querySelector(".hd-tick-n").textContent }) : null)));
      below.hidden = !unnamed.length;
    }
  }
  if (typeof ResizeObserver === "function") new ResizeObserver(() => fitTicks()).observe(gauge);

  let shownFor = null;
  function reveal() {                        // a calm reveal: the gauge draws left to right, the rows settle in after it
    if (still()) { el.dataset.reveal = "done"; return; }
    el.dataset.reveal = "0";
    void el.offsetWidth;
    requestAnimationFrame(() => requestAnimationFrame(() => { el.dataset.reveal = "1"; }));
  }
  function render() {
    const s = store.get(), r = youSeed(s) || s.result, P = PF();      // "You" before its first run: profile-ui's assumed mix
    const own = r ? customFor(s.holdings, r.pilot) : null, pending = !!(own && !ranOn(own, r));   // edited, not replayed yet
    let m = r && P ? (pending ? customModel(r, own, P) : holdModel(r, P)) : null;
    if (m && own) m = own.assumed ? { ...m, fiction: YOU_ASSUMED } : { ...m, title: EDITED_TITLE, fiction: null };
    el.hidden = !m;
    if (!m) return;
    el.dataset.edited = own ? "1" : "0";
    el.dataset.editing = editing ? "1" : "0";
    editor.hidden = !editing;
    if (editing && draft) drawEditor();
    editBtn.setAttribute("aria-expanded", String(editing || !staticLine.hidden));
    staticWords.textContent = staticEditLine(r);
    if (live()) staticLine.hidden = true;
    const back = resetLabel(r);
    resetBtn.hidden = !own || editing || !!own.assumed || !back;
    resetBtn.textContent = back || "";
    const fic = title.querySelector(".hd-fic");
    fic.textContent = m.fiction ? (m.fiction.startsWith("(") ? m.fiction : `(${m.fiction})`) : "";
    fic.hidden = !m.fiction;
    name.textContent = m.title;
    total.replaceChildren(...(m.amountText ? [mean(h("span", { class: "hd-total-n", text: m.amountText }), `${m.amountText}: the fictional amount, all of it in the bar below.`, { focus: false })] : []));
    const dollarsOf = (x) => (m.amount ? m.amount * x.weight : null);
    gauge.replaceChildren(shareBar([{ id: "today", label: "", segs: m.bar.map((x) => ({ ...x, dollars: dollarsOf(x) })) }], P, m.title, "hd-sb-gauge"),
      h("div", { class: "hd-ticks", "aria-hidden": "true" }, m.bar.map((x) => h("span", { class: "hd-tick", "data-tone": tone(x.tone), "data-ticker": x.ticker,
        "data-label": x.label, style: `left:${(x.x0 * 100).toFixed(3)}%` }, h("span", { class: "hd-tick-n", text: x.weightText }), h("span", { class: "hd-tick-l", text: x.label })))),
      h("ul", { class: "hd-unnamed", "aria-hidden": "true", hidden: true }));
    const row = (x, i, extra) => h("li", { class: `hd-row${extra ? " " + extra : ""}`, "data-ticker": x.ticker || "", style: `--i:${i}` },
      h("span", { class: "hd-key", "data-tone": x.keyTone || tone(x.tone), "data-kind": x.kind || null, "aria-hidden": "true" }),
      x.kind === "fund" && hasDrawer() ? fundButton(x) : h("span", { class: "hd-label", text: x.label }),
      x.ticker ? mean(h("span", { class: "hd-tk", text: x.ticker }), x.name && x.name !== x.ticker ? `${x.ticker}: ${x.name}.` : null, { focus: false }) : h("span", { class: "hd-tk" }),
      h("span", { class: "hd-w", text: x.weightText }),
      x.dollarsText ? mean(h("span", { class: "hd-d", text: x.dollarsText }), `${x.dollarsText}: ${x.weightText} of the ${m.amountText} fictional amount.`, { focus: false }) : h("span", { class: "hd-d" }));
    const fundButton = (x) => {              // a fund's label opens its page in lane funds' drawer
      const b = h("button", { type: "button", class: "hd-label hd-fund-btn", "aria-haspopup": "dialog", text: x.label });
      b.addEventListener("click", () => openFunds(store, x.ticker, b).catch((e) => console.warn("[funds] the drawer did not load:", e && e.message)));
      return b;
    };
    const rows = m.rows.map((x, i) => row(x, i));
    if (m.more) rows.push(row({ keyTone: "more", label: m.more.label, ticker: m.more.tickers.join(", "), name: null,
      weightText: m.more.weightText, dollarsText: m.more.dollarsText }, rows.length, "hd-row-more"));
    list.replaceChildren(...rows);
    const L = m.look;
    look.hidden = !L;
    look.dataset.kind = L ? L.kind : "";
    if (L) segsInto(lookText, L.segs, L.kind === "country" ? `${L.shareText}: the share of your money in ${L.place}, counting what each fund holds inside.` : null);
    const lm = pending ? null : lookModel(r, P);             // the funds' insides belong to a run: none for holdings not replayed yet
    const canOpen = !!(lm && lm.mode === "lookthrough");
    fold.hidden = !canOpen; btn.hidden = !canOpen;
    if (hasDrawer()) { btn.setAttribute("aria-haspopup", "dialog"); btn.removeAttribute("aria-controls"); }
    if (canOpen) renderInside(panel, lm);
    setOpen(canOpen && (insideOpen === null ? s.depth === "detailed" && !hasDrawer() : insideOpen), false);   // the drawer replaces it
    setWhy(whyOpen === null ? s.depth === "detailed" : whyOpen);
    setRows(rowsOpen === null ? s.depth === "detailed" : rowsOpen);
    drawLimits(limitsCard(r, P, s.limitsIn, s.holdings));
    const lw = limitWordsLine(r);
    said.hidden = !lw;
    said.replaceChildren(...(lw ? lw.segs.map(([t]) => document.createTextNode(t)) : []));
    if (lw) said.setAttribute("aria-label", lw.text); else said.removeAttribute("aria-label");
    setLimits(limitsOpen === null ? s.depth === "detailed" : limitsOpen);
    requestAnimationFrame(fitTicks);
    const key = r && (r.run_id || r.pilot);
    if (key !== shownFor) { shownFor = key; reveal(); }
  }
  function drawLimits(lc) {
    limBtn.hidden = !lc;
    if (!lc) { limits.replaceChildren(); return; }
    const pencil = (x) => {
      const b = h("button", { type: "button", class: "hd-lim-edit", "aria-label": `Edit: ${x.label}` }, sprite("i-edit", "hd-i"));
      b.addEventListener("click", () => editLimits(b));
      return b;
    };
    const add = h("button", { type: "button", class: "linkbtn hd-lim-add", text: "+ Add a limit" });
    add.addEventListener("click", () => editLimits(add));
    /* CONFLICTS (LIMITS_MODEL.md): a value you typed over your words wins, and one amber line says so, with the way back */
    const back = () => {
      const reset = document.querySelector("#checklist .ck-you-reset");
      if (!reset) return null;
      const b = h("button", { type: "button", class: "linkbtn hd-lim-back", text: "Use my words instead" });
      b.addEventListener("click", () => reset.click());
      return b;
    };
    limits.replaceChildren(...[
      h("p", { class: "hd-lim-sum", text: lc.summary }),
      ...(lc.conflicts || []).map((c) => h("p", { class: "hd-lim-conflict", role: "note" }, sprite("i-warn", "hd-i hd-lim-warn"), h("span", { text: c.text }), back())),
      lc.rows.length ? h("dl", { class: "hd-lim-list" }, lc.rows.map((x) => h("div", { class: "hd-lim-row", "data-src": x.source || "none" },
        h("dt", { text: x.label }),
        h("dd", {}, h("span", { class: "hd-lim-v" }, x.value, x.assumed ? h("span", { class: "hd-lim-was", text: ` (${x.assumed})` }) : null),
          x.tag ? mean(h("span", { class: "tag hd-lim-tag", "data-src": x.source, text: x.tag }), x.words ? `From your words: “${x.words}”.` : x.say, { focus: false }) : null,
          pencil(x))))) : null,
      lc.precedence ? h("p", { class: "hd-lim-rule", text: lc.precedence }) : null,
      add,
      h("p", { class: "hd-lim-why", tabindex: "-1", hidden: true, text: "Editing your limits needs the live app; the replay uses the limits shown." }),
    ].filter(Boolean));
  }
  store.on("result", render);
  store.on("holdings", render);
  store.on("limitsIn", render);
  store.on("mode", render);
  store.on("investor", () => { if (editing) closeEditor(false); staticLine.hidden = true; render(); });   // "You" shows its seed at once
  store.on("depth", () => { insideOpen = null; whyOpen = null; rowsOpen = null; limitsOpen = null; render(); });   // the page-level switch wins over an earlier choice
  render();
  return { render };
}

/* the panel: by country and by industry (today, and with the move when there is one), then the funds and the dates */
function renderInside(panel, lm) {
  const cols = lm.moved ? ["Today", "With the move"] : ["Today"];
  const cell = (v, text, side) => h("span", { class: `hd-cell hd-cell-${side}` },
    h("span", { class: "hd-track", "aria-hidden": "true" }, h("span", { class: "hd-fill", style: `transform:scaleX(${Math.max(0, Math.min(1, v || 0)).toFixed(4)})` })),
    h("span", { class: "hd-cell-n fig", text: text || "" }));
  const table = (id, head, items) => h("div", { class: "hd-part" },
    h("h3", { class: "hd-part-h", id, text: head }),
    h("div", { class: "hd-grid", role: "table", "aria-labelledby": id, "data-cols": String(cols.length) },
      h("div", { class: "hd-grid-row hd-grid-head", role: "row" }, h("span", { role: "columnheader", class: "hd-col hd-col-0" }, h("span", { class: "sr", text: head })),
        cols.map((c) => h("span", { role: "columnheader", class: "hd-col", text: c }))),
      items.map((x) => h("div", { class: "hd-grid-row", role: "row" },
        h("span", { role: "rowheader", class: "hd-name", text: x.name }),
        h("span", { role: "cell", class: "hd-c" }, cell(x.today, x.todayText, "today")),
        lm.moved ? h("span", { role: "cell", class: "hd-c" }, cell(x.after, x.afterText, "after")) : null))));
  panel.replaceChildren(...[
    lm.noMove ? h("p", { class: "hd-nomove", text: `${lm.noMove}: one mix, as it is today.` }) : null,
    lm.countries.length ? table("hd-by-country", "By country", lm.countries) : null,
    lm.sectors.length ? table("hd-by-sector", "By industry", lm.sectors) : null,
    lm.sectors.length ? h("p", { class: "hd-note", text: lm.sectorNote }) : null,
    lm.funds.length ? h("div", { class: "hd-part" }, h("h3", { class: "hd-part-h", text: "The funds" }),
      h("ul", { class: "hd-funds" }, lm.funds.map((f) => h("li", {}, h("span", { class: "hd-fund-tk", text: f.ticker }), h("span", { class: "hd-fund", text: f.name }))))) : null,
    ...lm.notes.map((t) => h("p", { class: "hd-note", text: t }))].filter(Boolean));
}

/* ---- #investors: each investor's mix today as one thin bar, the same tones; its parts name themselves on hover or tap ---- */
export function mixBar(r) {
  ensureCss();
  const P = PF(), m = r && P ? holdModel(r, P) : null;
  if (!m) return null;
  const dollarsOf = (x) => (m.amount ? m.amount * x.weight : null);
  return h("span", { class: "hd-mini" }, shareBar([{ id: "today", label: "", segs: m.bar.map((x) => ({ ...x, dollars: dollarsOf(x) })) }], P, m.title, "hd-sb-mini"));
}

/* ---- the stage strip ---- */
export function mountMoveStrip(el, store) {
  ensureCss();
  el.classList.add("hd-strip");
  function render() {
    const r = store.get().result, P = PF();
    const m = r && P ? stripModel(r, P) : null;
    el.hidden = !m;
    if (!m) { el.replaceChildren(); return; }
    const fig = shareBar([{ id: "today", label: "Today", segs: m.today }, { id: "after", label: "With the move", segs: m.after }], P,
      "Today and with the move", "hd-sb-strip");
    const rows = fig.querySelectorAll(".sb-row");
    if (rows[1]) rows[1].append(h("span", { class: "hd-strip-end", "aria-hidden": "true", text: `${m.move.label} ${m.move.weightText}` }));
    el.replaceChildren(fig);
  }
  store.on("result", render);
  render();
  return { render };
}
