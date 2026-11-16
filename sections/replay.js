/* The Replay stage (lane U2; design doc §2 item 2, beats a–e; rulings R1, R3, R8, R9, R13, R15). One section, one viewport, one
   timeline (one rAF loop): READ (the question lifts into a strip, the navigator's reading lands as chips, the five steps stream
   and fold into one receipt line) -> EPICENTRE (the globe flies to the asked family's worst precedent) -> HANDOFF (the globe
   glides to the left third, a 1 px cyan leader drops to the chart's tick at that date) -> THE RACE (race.draw(p)) -> VERDICT
   (the unboxed lamp, "in this 2021–26 replay", the two sentences, the money twist). Skip, Esc or any user scroll jumps to the end
   frame; reduced motion, or window.EPI_MOTION === false, shows the end frame at once. Words come from web/lib/replay.js (pure,
   node-tested); text is set with textContent only; the browser never judges a check. */
import * as R from "../lib/replay.js";
import { standingLine } from "../lib/status.js";
import { withHoldings, customFor, ranOn } from "../lib/hold.js";   // lane hold: the investor's edited holdings (live)
import { youGate, withYou } from "../lib/you.js";                  // lane profile-ui: "You", the profile your words gave (R46)

const SVGNS = "http://www.w3.org/2000/svg";
const DEFAULT_MOTION = false;             // R9: the still version first; motion on once smooth (window.EPI_MOTION overrides)
const PFx = () => globalThis.PF;
/* how far below the top a section lands: its own scroll-margin-top (U0's base: the bar, plus the step rail's row under 1000 px) */
const topOffset = (el) => {
  const sec = el && el.closest ? el.closest("[data-module]") || el : null;
  const m = sec ? parseFloat(getComputedStyle(sec).scrollMarginTop) : NaN;
  return Number.isFinite(m) && m > 0 ? m : parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--bar")) || 64;
};
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
/* the status icons, drawn here (the same shapes as the page's sprite) so the stage never depends on another file's symbols */
const SHAPES = {
  "i-out": [["path", { d: "M8.2 2.5h7.6l5.7 5.7v7.6l-5.7 5.7H8.2l-5.7-5.7V8.2z", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linejoin": "round" }],
    ["path", { d: "M12 7v6.2", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 16.8, r: 1.35, fill: "currentColor" }]],
  "i-in": [["circle", { cx: 12, cy: 12, r: 9.5, fill: "none", stroke: "currentColor", "stroke-width": 2 }],
    ["path", { d: "M7.5 12.3l3 3 6-6.3", fill: "none", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" }]],
  "i-warn": [["path", { d: "M12 3l9.5 17h-19z", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linejoin": "round" }],
    ["path", { d: "M12 9.5v5", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 17.4, r: 1.25, fill: "currentColor" }]],
  "i-pending": [["circle", { cx: 12, cy: 12, r: 8.5, fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-dasharray": "3 4" }]],
  "i-spin": [["circle", { cx: 12, cy: 12, r: 8.5, fill: "none", stroke: "currentColor", "stroke-opacity": ".3", "stroke-width": 2.4 }],
    ["path", { d: "M12 3.5a8.5 8.5 0 0 1 8.5 8.5", fill: "none", stroke: "currentColor", "stroke-width": 2.4, "stroke-linecap": "round" }]],
  "i-done": [["path", { d: "M5.5 12.5l4.2 4.2 8.8-9.4", fill: "none", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" }]],
  "i-skip": [["path", { d: "M6 12h12", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" }]],
  "i-edit": [["path", { d: "M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z", fill: "none", stroke: "currentColor", "stroke-width": 1.8, "stroke-linejoin": "round" }],
    ["path", { d: "M13.5 7.5l3 3", stroke: "currentColor", "stroke-width": 1.8 }]],
  "i-info": [["circle", { cx: 12, cy: 12, r: 9.5, fill: "none", stroke: "currentColor", "stroke-width": 1.6 }],
    ["path", { d: "M12 10.6v6", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 7.4, r: 1.25, fill: "currentColor" }]],
};
const icon = (id, cls = "icon") => s("svg", { class: cls, viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" },
  ...(SHAPES[id] || SHAPES["i-pending"]).map(([t, a]) => s(t, a)));
const ms = (name) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--" + name)) || 0;   // motion tokens, one source
const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const motionOn = () => { const f = globalThis.EPI_MOTION; return (f === undefined ? DEFAULT_MOTION : f !== false) && !reduced(); };
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const norm = (q) => String(q || "").toLowerCase().replace(/\s+/g, " ").trim();
function fill(el, segs) {                 // [[text, kind]] -> text nodes, numbers in tabular figures, the closing words stronger
  el.replaceChildren(...(segs || []).map(([t, k]) => (k ? h("span", { class: k === "num" ? "fig" : "rp-" + k, text: t }) : document.createTextNode(t))));
  el.hidden = !(segs && segs.length);
}
function ensureCss() {                    // the integrated page links it; a page that does not still gets it once
  if (typeof document === "undefined" || document.querySelector('link[href$="css/replay.css"]')) return;
  document.head.append(h("link", { rel: "stylesheet", href: new URL("../css/replay.css", import.meta.url).href }));
}

/* ---- the skeleton: built once; every render only sets text, attributes and data-in flags ---- */
function build(el) {
  el.classList.add("rp");
  const u = {};
  u.q = h("blockquote", { class: "rp-q", "data-in": "1" });
  u.who = h("p", { class: "rp-who", "data-in": "1" });
  u.chips = h("ul", { class: "rp-chips", "aria-label": "How the AI reader read the question" });
  u.aside = h("p", { class: "rp-aside", "data-in": "1" });
  u.by = h("div", { class: "rp-by", "data-in": "1" });
  u.steps = h("ol", { class: "rp-steps", "aria-label": "The five steps of this run" });
  u.receipt = h("div", { class: "rp-receipt", "data-in": "1" });
  u.note = h("p", { class: "rp-note", role: "status", hidden: true });
  /* R22: one quiet "Show the details" for the whole stage: the step timings, the request id, the families set aside and the two
     sentences behind the answer open as one panel under the receipt (Esc, the button or a click elsewhere closes it) */
  u.byMeta = h("p", { class: "rp-by-meta" });
  u.total = h("p", { class: "rp-total" });
  u.s1 = h("p", { class: "rp-s1" });
  u.s2 = h("p", { class: "rp-s2" });
  u.change = h("div", { class: "rp-change-row" });
  u.details = h("div", { class: "rp-details", id: "rp-details", role: "region", "aria-label": "The details of this replay", hidden: true },
    u.changePart = h("div", { class: "rp-details-part rp-change" }, h("p", { class: "rp-details-h", text: "Change one thing, see if the answer holds:" }), u.change),
    h("div", { class: "rp-details-part" }, h("p", { class: "rp-details-h", text: "How it was read" }), u.total, u.steps, u.byMeta),
    h("div", { class: "rp-details-part" }, h("p", { class: "rp-details-h", text: "The numbers behind the answer" }), u.s1, u.s2,
      u.robust = h("p", { class: "rp-s2 rp-robust", hidden: true })),
    h("div", { class: "rp-details-part rp-details-aside" }, u.aside));
  u.reframePill = h("p", { class: "rp-reframe rp-reframe-pill", "data-in": "1", hidden: true });
  u.read = h("div", { class: "rp-read" },
    u.main = h("div", { class: "rp-read-main" }, u.q, u.reframePill, u.pill = h("p", { class: "rp-pill", "data-in": "1" }), u.who, h("div", { class: "rp-reading" }, u.chips, u.hold = h("div", { class: "rp-hold" }),
      u.funding = h("p", { class: "rp-funding", "data-in": "1", hidden: true }),
      u.effect = h("p", { class: "rp-effect", "data-in": "1", hidden: true }))),
    h("div", { class: "rp-read-side" }, u.by, u.run = h("div", { class: "rp-run" },
      u.agentSlot = h("div", { class: "rp-agentlog", "data-agentlog-slot": "", hidden: true }), u.receipt, u.details)), u.note);
  u.mapRing = h("span", { class: "rp-map-ring" });
  u.map = h("div", { class: "rp-map", "data-in": "0", "aria-hidden": "true" }, u.mapRing, h("span", { class: "rp-map-core" }));
  u.stream = h("ol", { class: "rp-stream", "aria-hidden": "true", "data-in": "0" });   // the five steps while the slot is still empty
  u.slot = h("div", { class: "rp-globe", id: "replay-globe", "data-globe-slot": "" }, u.map, u.stream);
  u.epiTitle = h("span", { class: "rp-epi-title" });
  u.epiWhere = h("span", { class: "rp-epi-where" });
  u.epiWhy = h("span", { class: "rp-epi-why" });
  u.epiWin = h("span", { class: "rp-epi-num" });
  u.epi = h("p", { class: "rp-epi", "data-in": "1" }, u.epiTitle, u.epiWhere, u.epiWhy, u.epiWin);
  u.race = h("div", { class: "rp-race", "data-in": "1" });
  /* the transport (design director, item 13): ONE 40 px round button, Pause while it plays, Resume when paused, Replay once
     landed; Esc or a scroll still jumps to the end frame */
  u.tIcon = s("svg", { class: "rp-transport-icon", viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" }, s("use", { href: "#i-play" }));
  u.transport = h("button", { class: "rp-transport", type: "button", "aria-label": "Replay", title: "Replay", hidden: true }, u.tIcon);
  u.strip = h("div", { class: "rp-strip", "data-in": "1", hidden: true });   // lane U4's compact ruler, shown from the end frame on
  u.left = h("div", { class: "rp-left" }, u.slot, u.epi);
  u.band = h("p", { class: "rp-band", "data-in": "1", hidden: true });   // the start-month line under the ruler (the cut #dial's fact)
  u.peer = h("p", { class: "rp-band rp-peer", "data-in": "1", hidden: true });   // R36: the same size in the pack's other stocks
  u.right = h("div", { class: "rp-right" }, u.race, u.strip, u.band, u.peer, u.transport);
  u.scene = h("div", { class: "rp-scene" }, u.left, u.right);
  u.lpath = s("path", { class: "rp-lpath" });
  u.lsrc = s("circle", { class: "rp-lsrc", r: 2.5 });
  u.ldot = s("circle", { class: "rp-ldot", r: 3.5 });
  u.leader = s("svg", { class: "rp-leader", "aria-hidden": "true", focusable: "false", "data-in": "0", hidden: true }, u.lpath, u.lsrc, u.ldot);
  u.lampIcon = h("span", { class: "rp-lamp-icon" });
  u.lampWord = h("span", { class: "lamp-word" });
  u.lamp = h("p", { class: "rp-lamp", "data-in": "1" }, u.lampIcon, u.lampWord);
  u.qual = h("p", { class: "rp-qual", "data-in": "1" });
  u.standing = h("p", { class: "standing-line rp-standing", "data-in": "1" });   // under every verdict (the regulation flaw hunter)
  u.dial = h("p", { class: "rp-dialnote", hidden: true });
  u.without = h("p", { class: "rp-without", "data-in": "1" });
  u.fine = h("p", { class: "rp-fine", "data-in": "1", text: "This already happened; it is not a forecast. Fictional illustration, not a recommendation." });

  u.decide = h("p", { class: "rp-decide", "data-in": "1" });
  u.twist = h("p", { class: "rp-twist", "data-in": "1" });
  u.lines = h("div", { class: "rp-lines" }, u.decide, u.fine);
  /* verdict first, and a taller chart: the question, the lamp, its qualifier, the one answer sentence and the twist sit in the
     left column under a smaller Earth, read before the chart (R22: one question, one answer) */
  u.ask = h("h2", { class: "rp-ask", id: "rp-title", "data-in": "1", text: "Would this move have broken your limit?" });
  u.reframe = h("p", { class: "rp-reframe", "data-in": "1", hidden: true });
  u.answer = h("p", { class: "rp-answer", "data-in": "1" });
  /* under the answer: the shock asked about and what broke the floor (two short lines), then one proof line and the way to "why" */
  u.shockLine = h("p", { class: "rp-sub rp-sub-shock", "data-in": "1" });
  u.floorLine = h("p", { class: "rp-sub rp-sub-floor", "data-in": "1" });
  u.proof = h("p", { class: "rp-proof", "data-in": "1" });
  /* "in this 2021–26 replay" stays directly under the lamp (R1); the line about today's mix shares its row */
  u.verdict = h("div", { class: "rp-lampcol" }, u.ask, u.reframe, h("div", { class: "rp-lampbox", "aria-live": "polite" }, u.lamp,
    h("div", { class: "rp-qualrow" }, u.qual, u.without), u.standing),
    h("div", { class: "rp-answerbox" }, u.answer, u.twist, u.dial), u.subs = h("div", { class: "rp-subs" }, u.shockLine, u.floorLine), u.proof);
  u.left.append(u.verdict);
  u.right.insertBefore(u.lines, u.transport);
  u.stage = h("div", { class: "rp-stage", "data-phase": "idle" }, u.read, u.scene, u.leader);
  el.setAttribute("aria-labelledby", "rp-title");
  el.replaceChildren(u.stage);
  return u;
}

/* ---- renders (no motion here: they set the end state's content; the timeline only flips data-in flags) ---- */
function renderRead(u, r, ctx, act) {
  const rd = R.readingOf(r, { live: ctx.live });
  const q = ctx.question || rd.question || "";
  u.q.textContent = q ? `“${q}”` : "";
  /* R28, plain words: the navigator is "the AI reader" on the page (Claude on Amazon Bedrock, named in the Read-by line beside it);
     a run the keyword rules read says so */
  u.who.textContent = `${rd.whose}, as ${rd.by.kind === "model" ? "the AI reader" : "the keyword rules"} read it:`;
  const chip = (cls, c, what) => c && h("li", { class: `chip rp-chip ${cls}`, "data-in": "1" },
    h("span", { class: "rp-chip-v", text: c.value }), c.sub || c.from ? h("span", { class: c.from ? "rp-chip-s rp-chip-from" : "rp-chip-s", text: c.from || c.sub }) : null,
    h("button", { class: "rp-edit", type: "button", "aria-label": `Edit ${what}: put the question back in the box`, text: "Edit",
      onclick: () => act.edit(c.needles) }));
  const confirmed = ctx.confirmed === (r.run_id || true);
  const confirm = ctx.live ? h("li", { class: "rp-confirm", "data-in": "1" }, confirmed
    ? h("span", { class: "rp-confirmed" }, icon("i-done", "rp-confirm-icon"), "Reading confirmed by you")
    : h("button", { class: "linkbtn rp-confirm-btn", type: "button", text: "Confirm the reading", onclick: () => act.confirm() })) : null;
  u.chips.replaceChildren(...[chip(rd.move.none ? "rp-chip-still" : "rp-chip-move", rd.move, "the move"), chip("rp-chip-shock", rd.family, "the shock"),
    chip("rp-chip-shock", rd.precedents, "the precedents"), confirm].filter(Boolean));
  u.chips.dataset.confirmed = confirmed ? "1" : "0";
  u.aside.hidden = !rd.aside;
  if (u.aside.parentNode) u.aside.parentNode.hidden = !rd.aside;
  if (rd.aside) u.aside.replaceChildren(h("span", { class: "rp-aside-lead", text: "Set aside" }),
    ...rd.aside.labels.map((l) => h("span", { class: "rp-off", text: l })),
    h("span", { class: "rp-aside-why", text: rd.aside.reason || rd.aside.reasons.join(" ") }));
  renderEffect(u, r);
  const fund = R.fundingLine(r);
  u.funding.hidden = !fund;
  if (fund) u.funding.replaceChildren(...(fund.kind === "assumed" ? [s("svg", { class: "rp-mark", viewBox: "0 0 12 12", "aria-hidden": "true", focusable: "false" },
    s("use", { href: "#m-assumption" }))] : []), h("span", { text: fund.text }));
  u.funding.dataset.kind = fund ? fund.kind : "";
  renderChange(u, r, rd, act);
  const by = rd.by;
  u.by.dataset.kind = by.kind;
  /* who read it stays visible with its recorded date (R15); its timing and request id fold into the details (R22) */
  u.by.replaceChildren(...[h("span", { class: "rp-by-lead", text: "Read by" }),     // replaceChildren(null) would write "null"
    h("span", { class: "rp-by-svc", text: by.service }), by.model ? h("span", { class: "rp-by-model", text: by.model }) : null,
    by.recorded ? h("span", { class: "rp-by-rec", text: by.recorded }) : null].filter(Boolean));
  const meta = [by.msText && `${by.kind === "model" ? "The model answered in" : "The rules ran in"} ${by.msText}`, by.request && `request ${by.request}`].filter(Boolean);
  u.byMeta.hidden = !meta.length;
  u.byMeta.textContent = meta.length ? `${R.smart(meta.join(", "))}${by.recorded ? `, ${by.recorded}` : ""}.` : "";
  const steps = ctx.steps || R.stepRows(r);
  renderSteps(u, steps);
  renderReceipt(u, R.receiptOf(steps, r, { live: ctx.live }), act);
  return rd;
}
/* "Change a hypothesis. Change a scenario. Change a profile." (the deck's own test): three small controls, each an existing path */
const INVESTORS = [["robert", "Robert"], ["mateo", "Mateo"], ["amira", "Amira"], ["canadian", "Too Canadian?"]];
function renderChange(u, r, rd, act) {
  const PF = PFx(), floor = obj(r.limits) && typeof r.limits.floor === "number" ? PF.fmt.share(r.limits.floor) : null;
  const kids = [];
  if (floor) kids.push(h("button", { class: "rp-change-btn", type: "button", onclick: () => act.limits() },
    h("span", { text: `Your floor ${floor}` }), icon("i-edit", "rp-change-icon")));
  if (rd.family && !rd.family.none) kids.push(h("button", { class: "rp-change-btn", type: "button", onclick: () => act.edit(rd.family.needles) },
    h("span", { text: `The shock: ${rd.family.value}` }), icon("i-edit", "rp-change-icon")));
  const from = typeof document !== "undefined" ? document.querySelector("[data-taken-from]") : null;
  if (from && R.fundingLine(r)) kids.push(h("button", { class: "rp-change-btn", type: "button", onclick: () => act.takenFrom() },
    h("span", { text: "Where the money comes from" }), icon("i-edit", "rp-change-icon")));
  const others = INVESTORS.filter(([id]) => id !== r.pilot);
  const sel = h("select", { class: "rp-change-select", "aria-label": "Another investor", onchange: (e) => { if (e.target.value) act.investor(e.target.value); } },
    h("option", { value: "", text: "Another investor" }), ...others.map(([id, name]) => h("option", { value: id, text: name })));
  kids.push(sel);
  u.change.replaceChildren(...kids);
}
/* the AI's value in one line (R8): what the navigator read against what the keyword rules alone read, when they differ on the
   shock; a quiet info button reveals the blind measure behind it (web/eval_results.json, when the page can reach it) */
let evalOnce = null;
const evalData = () => evalOnce || (evalOnce = fetch(new URL("../eval_results.json", import.meta.url), { cache: "force-cache" })
  .then((res) => (res.ok ? res.json() : null)).catch(() => null));
function renderEffect(u, r) {
  const ef = R.effectLine(r);
  u.effect.hidden = !ef;
  u.stage.dataset.effect = ef ? "1" : "0";
  if (!ef) { u.effect.replaceChildren(); return; }
  const more = h("span", { class: "rp-effect-more", id: "rp-effect-more", hidden: true });
  const btn = h("button", { class: "rp-info", type: "button", hidden: true, "aria-expanded": "false", "aria-controls": "rp-effect-more",
    "aria-label": "How often the AI reads the shock right", onclick: () => {
      const open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", String(open)); more.hidden = !open;
    } }, icon("i-info", "rp-info-icon"));
  u.effect.replaceChildren(h("span", { class: "rp-effect-text", text: ef.text }), btn, more);
  evalData().then((ev) => { const t = R.evalLine(ev); if (t && u.effect.contains(btn)) { more.textContent = t; btn.hidden = false; } });
}
const STEP_ICON = { done: "i-done", running: "i-spin", skipped: "i-skip", error: "i-out", waiting: "i-pending" };
function renderSteps(u, steps) {
  const svc = (st, split) => (st.status === "skipped" ? "not run" : st.status === "waiting" ? "" : split && st.parts
    ? st.parts.map((p) => `${p.service} ${R.duration(p.ms)}`).join(", ") : st.service || "");
  const rows = (split) => steps.map((st) => h("li", { class: "rp-step", "data-state": st.status, "data-in": "1" },
    icon(STEP_ICON[st.status] || "i-pending", "rp-step-icon"), h("span", { class: "rp-step-name", text: st.name }),
    h("span", { class: split ? "rp-step-svc is-split" : "rp-step-svc", text: svc(st, split) }),
    h("span", { class: "rp-step-ms", text: st.status === "done" ? R.duration(st.ms) : "" })));
  u.steps.replaceChildren(...rows(true));
  if (u.stream) {
    const keep = [...u.stream.children].map((li) => li.dataset.in);    // a live update keeps the rows already shown
    u.stream.replaceChildren(...rows(false));
    [...u.stream.children].forEach((li, i) => { if (keep[i] !== undefined) li.dataset.in = keep[i]; });
  }
}
function renderReceipt(u, rc, act) {
  u.receipt.hidden = !rc;
  if (!rc) return;
  const open = u.read.dataset.details === "open";
  u.total.textContent = rc.text + (rc.skipped ? ` ${rc.skipped} step${rc.skipped === 1 ? "" : "s"} not run: no model in this run.` : "");
  u.receipt.replaceChildren(icon("i-done", "rp-receipt-icon"),
    h("span", { class: "rp-receipt-text" }, h("span", { class: "rp-receipt-main", text: rc.short + " " }),
      h("button", { class: "rp-toggle linkbtn", type: "button", "aria-expanded": String(open), "aria-controls": "rp-details",
        text: open ? "Hide the details" : "Show the details", onclick: () => act.toggleDetails() })));
}
function renderEpi(u, ev, mix) {
  const ep = R.epiLines(ev, mix);
  u.epi.hidden = !ep;
  if (!ep) return;
  u.epiTitle.textContent = ep.title;
  u.epiWhere.textContent = ep.where;
  u.epiWhy.textContent = ep.why;
  u.epiWin.replaceChildren(h("span", { class: "fig rp-shock-fig", text: ep.fig }), document.createTextNode(ep.win));
}
function placeMap(u, ev) {                 // the no-WebGL inset: the flat night map turned to the epicentre (a crossfade, no flight)
  const W0 = u.map.clientWidth, H0 = u.map.clientHeight;
  if (!ev || !W0 || !H0) return;
  const W = Math.max(W0, H0 * 2) * 3, H = W / 2, x = ((ev.lon + 180) / 360) * W, y = ((90 - ev.lat) / 180) * H;
  const bx = Math.min(0, Math.max(W0 - W, W0 / 2 - x)), by = Math.min(0, Math.max(H0 - H, H0 / 2 - y));
  u.map.style.backgroundSize = `${W}px ${H}px`;
  u.map.style.backgroundPosition = `${bx}px ${by}px`;
  u.map.style.setProperty("--x", `${bx + x}px`);
  u.map.style.setProperty("--y", `${by + y}px`);
}
function renderVerdict(u, r, wi) {
  const lamp = R.lampOf(r, wi);
  u.verdict.hidden = !lamp; u.lines.hidden = !lamp;
  if (!lamp) return null;
  u.ask.textContent = R.askLine(r) || "";
  const rf = R.reframeLine(r);               // the reframe (advice_guard.REFRAME_LINE) right above the lamp, and above the phone pill
  for (const x of [u.reframe, u.reframePill]) { x.hidden = !rf; x.textContent = rf || ""; }
  u.lamp.dataset.tone = lamp.tone;
  u.lamp.dataset.whatif = lamp.whatIf ? "1" : "0";        // a what-if size: smaller, never the verdict words, never green
  u.lampIcon.replaceChildren(...(lamp.icon ? [icon(lamp.icon, "rp-lamp-svg")] : []));
  u.lampIcon.hidden = !lamp.icon;
  u.lampWord.textContent = lamp.word;
  u.qual.textContent = lamp.qualifier;
  u.standing.textContent = standingLine(!!(PFx() && PFx().moveOf && PFx().moveOf(r)));
  u.dial.hidden = !lamp.caption;
  u.dial.textContent = lamp.caption || "";
  const wo = R.withoutLine(r);
  u.without.hidden = !wo;
  if (wo) u.without.replaceChildren(icon(wo.icon, "rp-without-icon"), document.createTextNode(wo.text));
  const dc = R.decidingLine(r);
  u.decide.hidden = !dc;
  const asked = R.lampOf(r, null) || lamp;                 // the deciding line belongs to the asked size's verdict
  /* the phone pill follows the dial (R20): the verdict at the size asked, else only the floor words of that what-if size */
  const pill = R.pillOf(r, wi) || { tone: asked.tone, icon: asked.icon, word: asked.word, rest: `, ${asked.qualifier}` };
  u.pill.dataset.tone = pill.tone;
  u.pill.replaceChildren(...(pill.icon ? [icon(pill.icon, "rp-pill-icon")] : []),
    h("span", { class: "rp-pill-text" }, h("span", { class: "rp-pill-word", text: pill.word }), document.createTextNode(pill.rest)));
  if (dc) u.decide.replaceChildren(icon(asked.icon || "i-warn", "rp-decide-icon"), document.createTextNode(`${dc.lead} `),
    h("strong", { class: "rp-decide-name", text: dc.name }), document.createTextNode(`. ${dc.text}`));
  u.decide.dataset.tone = asked.tone;
  const an = R.answerLine(r);
  fill(u.answer, an && an.segs);
  if (an) u.answer.dataset.tone = an.tone;
  fill(u.s1, R.moneyLine(r));
  const s2 = R.shockLine(r);
  fill(u.s2, s2 && s2.segs);
  if (s2 && s2.evidence) u.s2.append(" ", h("span", { class: "rp-evidence", text: `(${s2.evidence.toLowerCase()} evidence)` }));
  const tw = R.twistLine(r);
  fill(u.twist, tw && tw.segs);
  const sl = R.shockAskedLine(r);
  fill(u.shockLine, sl); fill(u.floorLine, null);
  u.subs.hidden = !sl;
  u.epiWin.hidden = !!sl || !!R.shockQuestion(r);   // the shock's own fall is said once: under the verdict, or in the answer itself
  renderProof(u, r);
  /* R20: the answer, the twist, the deciding line and the sentences are about the size asked; at a what-if size they step out of
     sight (their space kept, so nothing shifts mid-drag) and the lamp names only what that size did to the floor */
  u.stage.dataset.whatif = lamp.whatIf ? "1" : "0";
  u.stage.dataset.reframe = rf ? "1" : "0";
  return lamp;
}

/* one proof line (receipt, trace, guardrail) and a link down to the reasons (#why), so the "why" is one tap from the verdict */
function renderProof(u, r) {
  const text = R.proofLine(r), why = typeof document !== "undefined" ? document.getElementById("why") : null;
  u.proof.hidden = !text;
  if (!text) return;
  const go = why ? h("a", { class: "rp-why linkbtn", href: "#why", text: "Why this answer \u2192", onclick: (e) => {
    const el = document.getElementById("why");
    if (!el) return;
    e.preventDefault();
    const bar = topOffset(el);                    // the section's own scroll margin: the bar, and the step rail's row on narrow screens
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - bar, behavior: motionOn() ? "smooth" : "auto" });
    const hd = el.querySelector("h2, h3, [tabindex]");
    if (hd) { if (!hd.hasAttribute("tabindex")) hd.setAttribute("tabindex", "-1"); hd.focus({ preventScroll: true }); }
  } }) : null;
  u.proof.replaceChildren(h("span", { class: "rp-proof-text", text: text + (go ? " " : "") }), ...(go ? [go] : []));
}

/* ---- the section: store wiring, the one timeline, the live run, the leader ---- */
const SCROLL_KEYS = new Set([" ", "PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End"]);
export function mount(el, store, deps = {}) {
  ensureCss();
  const u = build(el);
  const S = { r: null, rd: null, ev: null, race: null, raceFor: null, racePromise: null, raf: 0, playing: false, played: false,
    staged: false, guardUntil: 0, pending: false, live: false, liveRun: null, liveSteps: null, lastKey: 0 };
  const bar = () => topOffset(document.getElementById("replay"));
  const byKey = () => performance.now() - S.lastKey < 800;
  const flags = (on, list) => { for (const x of list) if (x) x.dataset.in = on ? "1" : "0"; };
  const parts = () => [u.q, u.who, ...u.chips.children, u.effect, u.funding, u.by, u.receipt, u.epi, u.race, u.ask, u.reframe, u.reframePill, u.lamp, u.qual, u.standing, u.answer,
    u.without, u.fine, u.decide, u.twist, u.pill, u.band, u.peer, u.shockLine, u.floorLine, u.proof];
  function instant(fn) {                   // a state change with no transition (resets, the end frame, keyboard)
    u.stage.classList.add("rp-instant");
    fn();
    void u.stage.offsetWidth;
    requestAnimationFrame(() => requestAnimationFrame(() => u.stage.classList.remove("rp-instant")));
  }
  /* store.phase as before, plus store.phaseClock {phase, at, T, instant?, live?} for lane agentlog's run log (its own module) */
  function setPhase(p, extra) {
    u.stage.dataset.phase = p;
    const changed = store.get().phase !== p;
    if (changed || extra) store.set({ phase: p, phaseClock: { phase: p, at: performance.now(), T: S.T || null, ...(extra || {}) } });
  }
  function note(text) { u.note.hidden = !text; u.note.textContent = text || ""; }

  const act = {
    edit(needles) {                         // put the reading back in the question box, the chip's words selected (R8)
      const q = (S.r && S.r.question) || "";
      if (!q) return;
      store.set({ question: q });
      const box = document.querySelector("#hero textarea, #hero input[type='text'], #hero input[type='search'], [data-question]");
      if (!box || !("value" in box)) return;
      if (box.value !== q) { box.value = q; box.dispatchEvent(new Event("input", { bubbles: true })); }
      const rg = R.editRange(q, needles) || [0, q.length];
      box.scrollIntoView({ block: "center", behavior: motionOn() && !byKey() ? "smooth" : "auto" });
      box.focus({ preventScroll: true });
      try { box.setSelectionRange(rg[0], rg[1]); } catch (e) { /* a field without a selection */ }
    },
    confirm() {                             // R8: the investor confirms the navigator's reading in one tap (live runs)
      const r = S.r;
      if (!r) return;
      S.confirmed = r.run_id || true;
      store.set({ confirmed: { run_id: r.run_id || null, at: Date.now() } });
      renderRead(u, r, { live: S.live, steps: S.liveSteps, confirmed: S.confirmed }, act);
      const done = u.chips.querySelector(".rp-confirmed");
      if (done) { done.setAttribute("tabindex", "-1"); done.focus({ preventScroll: true }); }
    },
    limits() {                              // the existing limits editor (#checklist): opened live; static shows its own note
      const sec = document.getElementById("checklist");
      if (!sec) return;
      const t = sec.querySelector('button.cl-more[aria-controls="checklist-details"]');
      if (t && t.getAttribute("aria-expanded") !== "true") t.click();
      requestAnimationFrame(() => {
        const b = sec.querySelector(".ck-you-edit"), target = (b && b.closest("section")) || sec;
        window.scrollTo({ top: target.getBoundingClientRect().top + window.scrollY - bar() - 16, behavior: motionOn() && !byKey() ? "smooth" : "auto" });
        if (b && !b.disabled && b.getAttribute("aria-expanded") !== "true") b.click();
        if (b && !b.disabled) b.focus({ preventScroll: true });
      });
    },
    investor(id) { store.set({ investor: id, replay: Date.now() }); },   // as the investor cards switch (lane U8)
    takenFrom() {                           // lane picker's "taken from" control: brought into view and opened
      const c = document.querySelector("[data-taken-from]");
      if (!c) return;
      c.scrollIntoView({ block: "center", behavior: motionOn() && !byKey() ? "smooth" : "auto" });
      if (typeof c.showPicker === "function") { try { c.focus({ preventScroll: true }); c.showPicker(); return; } catch (e) { /* not a select */ } }
      if (c.getAttribute("aria-expanded") === "false") c.click();
      c.focus({ preventScroll: true });
    },
    toggleDetails(open) {                   // R22: one quiet disclosure; its state is remembered while the page lives
      const next = typeof open === "boolean" ? open : u.read.dataset.details !== "open";
      S.details = next;
      showDetails(next);
      const t = u.receipt.querySelector(".rp-toggle");
      if (t) t.focus({ preventScroll: true });
    },
  };
  function showDetails(next) {
    u.read.dataset.details = next ? "open" : "";
    u.details.hidden = !next;
    const t = u.receipt.querySelector(".rp-toggle");
    if (t) { t.setAttribute("aria-expanded", String(next)); t.textContent = next ? "Hide the details" : "Show the details"; }
    document.removeEventListener("keydown", closeOnEsc, true);
    document.removeEventListener("pointerdown", closeOutside, true);
    if (next) { document.addEventListener("keydown", closeOnEsc, true); document.addEventListener("pointerdown", closeOutside, true); }
  }
  function closeOnEsc(e) { if (e.key === "Escape" && u.read.dataset.details === "open") { e.stopPropagation(); act.toggleDetails(false); } }
  function placeDetails() {               // Detailed (store.depth, lane U0): the panel joins the flow under the scene, open
    const inline = store.get().depth === "detailed", home = inline ? u.stage : u.run;
    if (u.details.parentNode !== home) home.append(u.details);
    u.details.dataset.inline = inline ? "1" : "0";
  }
  function closeOutside(e) {
    if (u.details.dataset.inline === "1") return;
    if (u.read.dataset.details === "open" && !u.details.contains(e.target) && !u.receipt.contains(e.target)) { S.details = false; showDetails(false); }
  }

  /* the size ruler (lane U4's mountStrip) under the race, so dragging the size morphs the chart and flips the lamp in one view */
  let stripOnce = null;
  function ensureStrip() {
    if (stripOnce) return stripOnce;
    stripOnce = (deps.strip ? Promise.resolve(deps.strip) : import("./dial.js"))
      .then((mod) => (mod && typeof mod.mountStrip === "function" ? mod.mountStrip(u.strip, store) : null))
      .catch((e) => { console.warn("[replay] the size ruler is not available:", e && e.message); u.strip.hidden = true; return null; });
    return stripOnce;
  }

  /* the race chart (lane U3): created here, inside the stage, and put on the store */
  function raceApi() {
    if (deps.race) return Promise.resolve(deps.race);
    if (!S.racePromise) S.racePromise = Promise.all([import("../race.js"), import("../lib/race.js")])
      .then(([a, b]) => (typeof a.createRace === "function" && typeof b.raceModel === "function" ? { createRace: a.createRace, raceModel: b.raceModel } : null))
      .catch((e) => { console.warn("[replay] the race chart is not available yet:", e && e.message); return null; });
    return S.racePromise;
  }
  function destroyRace() {
    if (S.race && typeof S.race.destroy === "function") { try { S.race.destroy(); } catch (e) { console.error("[replay] race.destroy failed", e); } }
    S.race = null; S.raceFor = null;
    u.race.replaceChildren();
  }
  async function ensureRace(r) {
    if (S.raceFor === r && S.race) return S.race;
    destroyRace();
    const api = await raceApi();
    if (!api || S.r !== r) return null;
    try {
      /* its foot line is the stage's; the asked shock's callout names the high its fall is measured from (defect 4) */
      S.race = api.createRace(u.race, R.relabelFalls(api.raceModel(r, null), r), { foot: false, reducedMotion: reduced() });
      S.raceFor = r;
      const wi = store.get().weightIndex;
      if (Number.isInteger(wi) && typeof S.race.setWeight === "function") S.race.setWeight(wi);
      store.set({ race: S.race });
    } catch (e) { console.error("[replay] the race chart failed:", e); S.race = null; }
    return S.race;
  }

  /* without WebGL lane U1 puts an Earth card in the slot from the stage's first frame (centred on the asked shock, its point in
     data-x / data-y); the flat inset map crossfades in only when there is neither a globe nor that card (this page's harness) */
  const card = () => u.slot.querySelector(".hx-stage-card");
  const useMap = () => !store.get().globe && !card();
  /* the globe (lane U1) when it exists; else the flat inset map crossfades in (no flight) */
  function flyGlobe(msv) {
    const g = store.get().globe, ev = S.ev;
    if (!ev) return;
    if (g && typeof g.flyTo === "function") {
      try { if (typeof g.focusFamily === "function") g.focusFamily(ev.family); g.flyTo(ev.lat, ev.lon, msv); } catch (e) { console.error("[replay] globe.flyTo failed", e); }
    } else if (useMap()) { placeMap(u, ev); u.map.dataset.in = "1"; u.map.dataset.ring = "1"; }   // the flat card: one ring fires
  }
  function stageGlobe(msv, turn) {         // the Earth docks in the stage's slot; turn = also face the epicentre (same duration)
    const g = store.get().globe, ev = S.ev;
    if (g && typeof g.setLayout === "function") {
      try {
        if (ev && turn) { if (typeof g.focusFamily === "function") g.focusFamily(ev.family); if (typeof g.flyTo === "function") g.flyTo(ev.lat, ev.lon, msv); }
        S.staged = true;
        Promise.resolve(g.setLayout("stage", msv)).then(() => { if (!S.playing) placeLeader(false); }, () => {});
      } catch (e) { console.error("[replay] globe.setLayout failed", e); }
      u.map.dataset.in = "0";
    } else if (ev && turn && useMap()) { placeMap(u, ev); u.map.dataset.in = "1"; }
  }
  function undockGlobe(msv) {              // back to the Earth's hero place (lane U1 holds it there, large, while the stage is shown)
    const g = store.get().globe;
    u.leader.setAttribute("hidden", "");
    if (!g || typeof g.setLayout !== "function") return;
    if (typeof g.layout === "string" ? g.layout !== "stage" : !S.staged) return;
    S.staged = false;
    try { g.setLayout("hero", msv); } catch (e) { console.error("[replay] globe.setLayout failed", e); }
  }
  /* the leader: one 1 px cyan thread that leaves the epicentre level and drops onto the chart's tick at the shock's date */
  function leaderPoints() {
    const ev = S.ev;
    if (!ev) return null;
    const sec = u.stage.getBoundingClientRect(), g = store.get().globe;
    let p = null;
    const staged = g && (typeof g.layout === "string" ? g.layout === "stage" : S.staged);
    if (g && staged && typeof g.project === "function") {
      const q = g.project(ev.lat, ev.lon);
      if (q && q.visible !== false && Number.isFinite(q.x) && Number.isFinite(q.y)) p = { x: q.x - sec.left, y: q.y - sec.top };
    } else if (!g && card() && card().dataset.x) {         // lane U1's Earth card: its epicentre point, px in the card
      const c = card(), b = c.getBoundingClientRect(), x = parseFloat(c.dataset.x), y = parseFloat(c.dataset.y);
      if (b.width && Number.isFinite(x) && Number.isFinite(y)) p = { x: b.left - sec.left + x, y: b.top - sec.top + y };
    } else if (!g && u.map.dataset.in === "1") {
      const m = u.map.getBoundingClientRect(), x = parseFloat(u.map.style.getPropertyValue("--x")), y = parseFloat(u.map.style.getPropertyValue("--y"));
      if (Number.isFinite(x) && Number.isFinite(y)) p = { x: m.left - sec.left + x, y: m.top - sec.top + y };
    }
    const race = S.race;
    if (!p || !race) return null;
    /* the race's markers() and xOfDate() are viewport px, like globe.project (INTERFACES.md, lane U3) */
    let x2 = null, y2 = null, xL = null;
    try {
      const mk = typeof race.markers === "function" ? race.markers("viewport") : null;
      const m = (Array.isArray(mk) ? mk : []).find((k) => k && k.kind === "shock" && (k.id === ev.id || k.date === ev.date));
      if (m && Number.isFinite(m.x) && Number.isFinite(m.y)) { x2 = m.x; y2 = m.y; }
      const first = (obj(S.r.tipping_point) && obj(S.r.tipping_point.paths) && S.r.tipping_point.paths.dates || (obj(S.r.series) || {}).dates || [])[0];
      if (typeof race.xOfDate === "function") {
        if (x2 === null) { const x = race.xOfDate(ev.date, "viewport"); if (Number.isFinite(x)) x2 = x; }
        if (first) { const x = race.xOfDate(first, "viewport"); if (Number.isFinite(x)) xL = x; }
      }
    } catch (e) { return null; }
    if (x2 === null) return null;
    if (y2 === null) { const rr = u.race.getBoundingClientRect(); y2 = rr.bottom - 28; }
    return { x1: p.x, y1: p.y, x2: x2 - sec.left, y2: y2 - sec.top, xL: xL === null ? null : xL - sec.left };
  }
  function placeLeader(animate) {
    const pt = leaderPoints();
    u.leader.toggleAttribute("hidden", !pt);
    if (!pt) return;
    const { x1, y1, x2, y2, xL } = pt, f = (v) => v.toFixed(1);
    /* down to the axis where the chart begins, then along the axis to the shock's tick: the thread never crosses a label */
    const d = xL !== null && xL > x1 + 40 && xL < x2
      ? `M${f(x1)},${f(y1)} C${f(x1 + (xL - x1) * 0.6)},${f(y1)} ${f(xL - (xL - x1) * 0.3)},${f(y2)} ${f(xL)},${f(y2)} H${f(x2)}`
      : `M${f(x1)},${f(y1)} C${f(x1 + Math.max(48, (x2 - x1) * 0.5))},${f(y1)} ${f(x2)},${f(y2 - Math.max(36, (y2 - y1) * 0.7))} ${f(x2)},${f(y2)}`;
    u.lpath.setAttribute("d", d);
    u.lsrc.setAttribute("cx", x1.toFixed(1)); u.lsrc.setAttribute("cy", y1.toFixed(1));
    u.ldot.setAttribute("cx", x2.toFixed(1)); u.ldot.setAttribute("cy", y2.toFixed(1));
    u.leader.style.setProperty("--l", `${Math.max(0, x1 - 6).toFixed(1)}px`);
    u.leader.style.setProperty("--r", `${Math.max(0, u.stage.clientWidth - x2 - 6).toFixed(1)}px`);
    if (animate && motionOn()) { u.leader.dataset.in = "0"; void u.leader.getBoundingClientRect(); u.leader.dataset.in = "1"; }
    else if (u.leader.dataset.in !== "1") instant(() => { u.leader.dataset.in = "1"; });
  }
  let relayout = 0, settle = 0;
  function replace() {                     // the inset and the thread follow a resize, a scroll, or the globe gliding back
    if (S.ev && u.map.dataset.in === "1") placeMap(u, S.ev);
    if (S.played && !S.playing) placeLeader(false);
  }
  const onLayout = () => {                 // at most once a frame, and once more when things have settled
    if (!relayout) relayout = requestAnimationFrame(() => { relayout = 0; replace(); });
    clearTimeout(settle);
    settle = setTimeout(replace, 820);
  };

  /* ---- content (the end state of every part) ---- */
  function renderAll(r) {
    S.r = r;
    u.stage.dataset.pending = "0";
    u.stage.hidden = !r;
    if (!r) return;
    const v = PFx().view(r);
    S.rd = renderRead(u, r, { live: S.live, steps: S.live ? S.liveSteps : null, confirmed: S.confirmed }, act);
    if (S.details && u.details.hidden) showDetails(true);
    u.stage.dataset.stop = v.stop ? "1" : "0";
    if (v.stop) {                           // blocked, clarify, an error: the server's own sentence, no verdict, no chart
      note(v.message || PFx().failureLine(r));
      u.scene.hidden = true; u.verdict.hidden = true; S.ev = null;
      destroyRace();
      return;
    }
    u.scene.hidden = false;
    u.strip.hidden = !(obj(r.tipping_point) && Array.isArray(r.tipping_point.curve) && r.tipping_point.curve.length);
    if (!u.strip.hidden) ensureStrip();
    const bl = u.strip.hidden ? null : R.bandLine(r);
    fill(u.band, bl);
    fill(u.peer, R.peerLine(r));
    const rb = R.robustLine(r);
    u.robust.hidden = !rb; u.robust.textContent = rb || "";
    S.ev = R.worstPrecedent(r);
    renderEpi(u, S.ev, S.rd.mix);
    renderVerdict(u, r, store.get().weightIndex);
    ensureRace(r).then((race) => {
      if (!race || S.r !== r) return;
      if (!S.playing) { race.draw(1); pinShock(); if (!u.leader.hasAttribute("hidden") || (!store.get().globe && (u.map.dataset.in === "1" || card()))) placeLeader(false); }
    });
  }
  function restFrame() {                   // the still: every part shown, the steps folded, the globe left alone
    instant(() => {
      flags(true, [...parts(), u.strip]);
      u.stream.dataset.in = "0";
      u.stream.dataset.gone = "1";
      u.map.dataset.in = useMap() && S.ev ? "1" : card() ? "0" : u.map.dataset.in;
      u.map.dataset.ring = "1";
      if (S.ev && u.map.dataset.in === "1") placeMap(u, S.ev);
    });
    if (S.race) { S.race.draw(1); pinShock(); }
    setTransport(!S.r || !!(PFx().view(S.r) || {}).stop ? null : "replay");
    if (u.stage.dataset.phase === "idle") setPhase("idle", { instant: true });   // the still (lane agentlog shows its folded line)
  }
  function stopLoop() { if (S.raf) cancelAnimationFrame(S.raf); S.raf = 0; S.playing = false; S.paused = false; }
  function endFrame(globeMs = 0) {         // Skip, Esc, a user scroll, reduced motion, the stage reached by scroll: the end frame
    stopLoop();
    restFrame();
    if (S.ev) stageGlobe(globeMs, true);
    setPhase("landed", { instant: true });
    S.played = true;
    if (!globeMs) placeLeader(false);       // after a glide, the thread is drawn once the globe has docked
  }

  /* ---- the one timeline: cues fire once at their time; the race is the one continuous track ---- */
  function run(T, cues) {
    stopLoop();
    S.playing = true; S.paused = false; S.T = T;
    setTransport("pause");
    cues.sort((a, b) => a.at - b.at);
    S.t0 = performance.now();
    const tick = (now) => {
      const t = now - S.t0;
      while (cues.length && cues[0].at <= t) { try { cues.shift().fn(); } catch (e) { console.error("[replay] a beat failed", e); } }
      if (S.race && t >= T.race && t <= T.race + T.raceMs + 64) S.race.draw(R.easeInOut((t - T.race) / T.raceMs));
      if (!cues.length && t >= T.end) { S.raf = 0; finish(); return; }
      S.raf = requestAnimationFrame(tick);
    };
    S.tick = tick;
    S.raf = requestAnimationFrame(tick);
  }
  function setTransport(state) {           // "pause" | "resume" | "replay" | null (hidden)
    u.transport.hidden = !state;
    if (!state) return;
    const label = state === "pause" ? "Pause" : state === "resume" ? "Resume" : "Replay";
    u.transport.dataset.state = state;
    u.transport.setAttribute("aria-label", label); u.transport.title = label;
    u.tIcon.firstChild.setAttribute("href", state === "pause" ? "#i-pause" : "#i-play");
  }
  function pause() {
    if (!S.playing || S.paused) return;
    if (S.raf) cancelAnimationFrame(S.raf);
    S.raf = 0; S.paused = true; S.pausedAt = performance.now() - S.t0;
    setTransport("resume");
  }
  function resume() {
    if (!S.playing || !S.paused || !S.tick) return;
    S.t0 = performance.now() - S.pausedAt; S.paused = false;
    S.raf = requestAnimationFrame(S.tick);
    setTransport("pause");
  }
  function pinShock() {                    // the crosshair opens on the asked shock's week (lane U3's race.pin)
    if (S.race && typeof S.race.pin === "function" && S.ev) { try { S.race.pin(S.ev.date); } catch (e) { console.error("[replay] race.pin failed", e); } }
  }
  function laterCues(T) {                  // EPICENTRE, HANDOFF, THE RACE, VERDICT: the same for saved and live runs
    const c = [], at = (t, fn) => c.push({ at: t, fn });
    at(T.fly, () => { setPhase("flying"); u.stream.dataset.in = "0"; flyGlobe(T.flyMs); });   // R7: the zoom to the epicentre, one ring
    at(T.caption, () => { u.epi.dataset.in = "1"; });
    at(T.handoff, () => { stageGlobe(T.handoffMs, false); u.race.dataset.in = "1"; u.stream.dataset.gone = "1"; });   // the Earth docks
    at(T.by, () => { flags(true, [u.by, u.receipt]); });
    at(T.race, () => setPhase("racing"));
    at(T.leader, () => placeLeader(true));                     // the thread: from the inset Earth to the shock's tick
    at(T.pin, () => pinShock());                               // the crosshair opens on that week, then the verdict lights
    at(T.lamp, () => { flags(true, [u.ask, u.reframe, u.reframePill, u.lamp, u.qual, u.standing, u.pill]); setPhase("landed"); });
    at(T.lines, () => flags(true, [u.answer, u.without, u.fine, u.decide, u.band, u.peer, u.shockLine, u.floorLine, u.proof]));
    at(T.twist, () => { u.twist.dataset.in = "1"; });
    return c;
  }
  function startFrame(live) {
    instant(() => {
      flags(false, [...parts(), u.map, u.leader, u.strip]);
      if (live) flags(true, [u.q, u.who]);
      if (useMap() && S.ev) { placeMap(u, S.ev); flags(true, [u.map, u.epi]); u.map.dataset.ring = "0"; }
      else if (!store.get().globe && card() && S.ev) flags(true, [u.epi]);   // the Earth card is there from the first frame
      u.stream.dataset.gone = "0";
      u.stream.dataset.in = live ? "1" : "0";
      for (const li of u.stream.children) li.dataset.in = live ? "1" : "0";
    });
    u.leader.setAttribute("hidden", "");
    if (S.race) { if (typeof S.race.unpin === "function") { try { S.race.unpin(); } catch (e) { /* older race */ } } S.race.draw(0); }
  }
  function savedCues(T) {                  // READ from a saved run: the trace's steps at a calm pace, the reading, then the rest
    const c = laterCues(T), at = (t, fn) => c.push({ at: t, fn });
    at(T.lift, () => { flags(true, [u.q, u.who]); u.stream.dataset.in = "1"; });   // the steps stream in the empty slot, on black
    [...u.stream.children].forEach((li, i) => at(T.step0 + i * T.stepGap, () => { li.dataset.in = "1"; }));
    [...u.chips.children].forEach((chip, i) => at(T.chips + i * T.chipGap, () => { chip.dataset.in = "1"; }));
    at(T.aside, () => { u.aside.dataset.in = "1"; u.effect.dataset.in = "1"; u.funding.dataset.in = "1"; });
    return c;
  }
  function play() {
    if (!S.r) { S.pending = true; return; }
    S.pending = false;
    S.guardUntil = Math.max(S.guardUntil, performance.now() + 700);
    if (!motionOn() || u.stage.dataset.stop === "1") return endFrame();
    const T = R.schedule({});
    S.T = T;
    startFrame(false);
    setPhase("reading");
    undockGlobe(T.undockMs);               // every replay starts from the Earth's own place, large, beside the stage
    run(T, savedCues(T));
  }
  function seek(t) {                       // capture and review only: the frame at t ms of a saved run's replay, no loop
    stopLoop();
    const T = R.schedule({}), c = savedCues(T).sort((a, b) => a.at - b.at);
    startFrame(false);
    instant(() => { for (const q of c) if (q.at <= t) q.fn(); });
    if (S.race) S.race.draw(t < T.race ? 0 : R.easeInOut((t - T.race) / T.raceMs));
    setPhase(R.phaseAt(t, T));
    return { phase: R.phaseAt(t, T), schedule: T };
  }
  function finish() {
    S.playing = false; S.played = true;
    flags(true, [...parts(), u.strip]);
    setTransport("replay");
    setPhase("landed");
  }
  function skip() {
    if (!S.playing) return;
    endFrame();
  }

  /* ---- a live run (R8): the old answer dims, the lamp says Checking, the five steps stream here, then the rest lands ---- */
  async function dataApi() {
    if (deps.data) return deps.data;
    try { return await import("../data.js"); } catch (e) { return null; }
  }
  async function runLive(question) {
    const data = await dataApi(), PF = PFx(), prev = S.r, st = store.get();
    if (!data || typeof data.runLive !== "function" || !prev) return play();
    stopLoop();
    S.liveRun = { question }; S.live = true; S.liveSteps = R.foldStep(null, null);
    note(null);
    u.q.textContent = `“${question}”`;
    u.stage.dataset.pending = "1";
    u.lamp.dataset.tone = "pending";
    u.lampIcon.replaceChildren(icon("i-spin", "rp-lamp-svg"));
    u.lampWord.textContent = "Checking";
    renderSteps(u, S.liveSteps);
    instant(() => {
      /* the cold first-time user: never the OLD verdict and sentences under "Checking"; they come back with the new answer */
      flags(false, [u.qual, u.standing, u.without, u.answer, u.twist, u.dial, u.subs, u.proof, u.race, u.pill, u.decide]);
      flags(true, [u.q, u.who, u.lamp]); u.receipt.dataset.in = "0"; u.by.dataset.in = "0";
      u.stream.dataset.gone = "0"; u.stream.dataset.in = "1"; for (const li of u.stream.children) li.dataset.in = "1";
    });
    setTransport(null);
    setPhase("reading", { live: true });
    undockGlobe(motionOn() ? ms("dur-story") : 0);         // the steps stream in the empty slot while the run computes
    store.set({ steps: S.liveSteps });
    let r = null;
    try {
      const body = withYou(withHoldings(PF.requestBody({ ...PF.planFrom(prev, st.investor), q: question }, null, false), st.holdings, st.investor), st);
      r = await data.runLive(body, (ev) => { S.liveSteps = R.foldStep(S.liveSteps, ev); renderSteps(u, S.liveSteps); store.set({ steps: S.liveSteps }); });
      if (r && store.get().result !== r) store.set({ result: r, view: PF.view(r), weightIndex: null });
    } catch (e) {
      S.liveRun = null; S.live = false; S.liveSteps = null;
      if (e && e.aborted) { renderAll(store.get().result); restFrame(); setPhase("landed"); return; }   // another investor: draw that one
      renderAll(prev); restFrame(); setPhase("landed");
      note(PF.failureLine(e));
      return;
    }
    S.liveRun = null;
    landLive(r);
  }
  function landLive(r) {
    renderAll(r);
    if (!r || u.stage.dataset.stop === "1" || !motionOn()) return endFrame();
    const T = R.schedule({ live: true });
    startFrame(true);
    const c = laterCues(T), at = (t, fn) => c.push({ at: t, fn });
    [...u.chips.children].forEach((chip, i) => at(T.chips + i * T.chipGap, () => { chip.dataset.in = "1"; }));
    at(T.aside, () => { u.aside.dataset.in = "1"; u.effect.dataset.in = "1"; u.funding.dataset.in = "1"; });
    run(T, c);
  }

  /* ---- a replay request (hero, investors, Play again): to the stage, then the saved run's replay or a live run ---- */
  function toStage(then) {
    const top = el.getBoundingClientRect().top;
    if (Math.abs(top - bar()) < 8) return then();
    const smooth = motionOn() && !byKey();
    window.scrollTo({ top: window.scrollY + top - bar(), behavior: smooth ? "smooth" : "auto" });
    if (!smooth) return then();
    let done = false;
    const go = () => { S.heading = false; if (done) return; done = true; window.removeEventListener("scrollend", go); then(); };
    S.heading = true;                                 // motion QA: mid-scroll the observer must not build an end frame play() resets
    window.addEventListener("scrollend", go, { once: true });
    setTimeout(go, 900);
  }
  function onReplay() {
    const st = store.get(), q = norm(st.question), rq = norm(S.r && S.r.question);
    const current = S.r && (!st.investor || S.r.pilot === st.investor);
    S.guardUntil = performance.now() + 1500;
    const you = youGate(st, S.r);                             // lane profile-ui: "You" waits for the card, else runs live on it
    if (you === "wait") return;
    if (you === "run") return toStage(() => runLive(st.question || ""));
    if (!current) { S.pending = true; return toStage(() => {}); }
    if (st.mode === "live" && q && q !== rq) return toStage(() => runLive(st.question));
    const own = customFor(st.holdings, st.investor);         // edited holdings not yet replayed: a live run on them
    if (st.mode === "live" && own && !ranOn(own, S.r)) return toStage(() => runLive(st.question || (S.r && S.r.question) || ""));
    note(st.mode === "static" && q && q !== rq ? "This page replays saved runs, so it shows the recorded question. Your own words need the live app." : null);
    toStage(play);
  }

  /* ---- any user scroll, Esc or Skip jumps to the end frame; a keyboard action never animates ---- */
  const intent = (e) => {
    if (!S.playing) return;
    if (e.type === "keydown") {
      const t = e.target;
      if (e.key === "Escape") return skip();
      if (!SCROLL_KEYS.has(e.key) || (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(t.tagName)))) return;
    }
    if (performance.now() < S.guardUntil) return;
    skip();
  };
  const markKey = () => { S.lastKey = performance.now(); };
  const markPointer = () => { S.lastKey = 0; };
  u.transport.addEventListener("click", () => {
    if (S.playing && !S.paused) pause();
    else if (S.playing && S.paused) resume();
    else store.set({ replay: Date.now() });
  });
  window.addEventListener("wheel", intent, { passive: true });
  window.addEventListener("touchmove", intent, { passive: true });
  window.addEventListener("resize", onLayout, { passive: true });
  window.addEventListener("scroll", onLayout, { passive: true });
  document.addEventListener("pointerdown", markPointer, { capture: true, passive: true });

  /* the first time the stage is reached by scroll it plays (the hero, lane U1, gives the globe back when the reader scrolls up) */
  const phone = typeof matchMedia === "function" ? matchMedia("(max-width: 900px)") : null;
  const placeStream = () => {             // phones: the Earth sits over the slot while it is large, so the steps get their own row
    const home = (phone && phone.matches) || !store.get().globe ? u.main : u.slot;
    if (u.stream.parentNode !== home) home.append(u.stream);
  };
  placeStream();
  if (phone) phone.addEventListener("change", placeStream);
  const io = typeof IntersectionObserver === "function" ? new IntersectionObserver((entries) => {
    for (const e of entries) {             // half the stage, or half the screen when the stage is taller than the screen (a phone)
      const enough = e.isIntersecting && e.intersectionRect.height >= 0.5 * Math.min(e.boundingClientRect.height, innerHeight);
      S.inView = enough;
      if (enough && !S.played && !S.playing && !S.liveRun && !S.heading && S.r) endFrame(motionOn() ? ms("dur-story") : 0);   // rests on the end frame
    }
  }, { threshold: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6] }) : null;
  if (io) io.observe(el);
  /* lane U1's Earth card can arrive after the first render (no WebGL): the flat map steps aside and the thread starts from it */
  const slotMO = typeof MutationObserver === "function" ? new MutationObserver(() => {
    if (!card()) return;
    if (u.map.dataset.in === "1") instant(() => { u.map.dataset.in = "0"; });
    if (S.played && !S.playing) placeLeader(false);
  }) : null;
  if (slotMO) slotMO.observe(u.slot, { childList: true });

  const offs = [
    store.on("result", (r) => {
      if (S.liveRun) return;               // a live run lands through runLive (its own choreography)
      stopLoop(); S.live = false; S.liveSteps = null;
      renderAll(r);
      const st = store.get();
      if (S.pending && r && (!st.investor || r.pilot === st.investor)) play();
      else if (r && S.inView && S.played) endFrame(motionOn() ? ms("dur-story") : 0);   // another investor on screen: the Earth turns to it
      else { restFrame(); S.played = false; }                                            // reached later: it rests on the end frame then
    }),
    store.on("weightIndex", (wi) => {
      if (!S.r || S.liveRun) return;
      const before = u.lampWord.textContent, lamp = renderVerdict(u, S.r, wi);
      if (lamp && before !== lamp.word && motionOn() && !byKey()) {
        u.lamp.classList.add("is-morph");
        requestAnimationFrame(() => requestAnimationFrame(() => u.lamp.classList.remove("is-morph")));
      }
    }),
    store.on("replay", () => onReplay()),
    store.on("investor", (id) => { if (S.r && S.r.pilot !== id) u.stage.dataset.pending = "1"; }),
    store.on("globe", () => placeStream()),
    store.on("depth", (d) => { placeDetails(); S.details = d === "detailed"; showDetails(S.details); onLayout(); }),
  ];
  renderAll(store.get().result);
  /* lane hold: TODAY vs WITH THE MOVE beside the move chip (its own module; the stage works without it) */
  import("./hold.js").then((m) => m.mountMoveStrip(u.hold, store))
    .catch((e) => { u.hold.hidden = true; console.warn("[replay] the holdings strip is not available:", e && e.message); });
  placeDetails();
  if (store.get().depth === "detailed") { S.details = true; showDetails(true); }
  restFrame();
  if (!motionOn() && store.get().result) S.played = false;
  document.addEventListener("keydown", markKey, { capture: true });
  window.addEventListener("keydown", intent);
  return {
    play, skip, seek,
    destroy() {
      stopLoop(); destroyRace(); if (io) io.disconnect(); if (slotMO) slotMO.disconnect(); offs.forEach((f) => f()); showDetails(false);
      if (phone) phone.removeEventListener("change", placeStream);
      window.removeEventListener("wheel", intent); window.removeEventListener("touchmove", intent); window.removeEventListener("keydown", intent);
      window.removeEventListener("resize", onLayout); window.removeEventListener("scroll", onLayout);
      document.removeEventListener("pointerdown", markPointer, { capture: true }); document.removeEventListener("keydown", markKey, { capture: true });
    },
  };
}
