/* EPICENTRE Replay, lane sc-u: #scenario, "Would it survive a future you imagine?" (rulings R21, R22). mount(el, store).
   The investor describes a future in words (live: the navigator reads them, POST /api/scenario/read) or starts from a move on
   record (result.scenarios.presets, static mode works from these); each factor the reading moves is a chip with a slider
   (range = the engine's bounds, engraved marks at the measured precedents); the answer is ONE sentence with one big number,
   the fall of the mix in this made-up scenario against the investor's floor (live: POST /api/scenario; static: the preset's
   own numbers). Who carries the fall and the engine against real episodes fold behind "Show the details" (R22).
   Every number is a Result or API value through PF.fmt (web/lib/scenario.js); the page never computes one. #m-fiction marks the
   scenario's result, #m-assumption the measured sensitivities. Hidden when the Result has no scenarios block. */
import { scenarioModel, outcomeOf, readingOf, chipsOf, closedFigures, checkedLine, shockText, pointsText, trackOf, snapTo,
  readBody, scenarioBody, sameShocks, cleanShocks, firstPreset, keyStep, moreLine, anchoredMarks, withMarks, withBook, gapWords, signedPct, factOf, EXAMPLES, LINE } from "../lib/scenario.js";

const SVG = "http://www.w3.org/2000/svg";
function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "vars") for (const [p, x] of Object.entries(v)) { if (x !== null && x !== undefined) n.style.setProperty(p, String(x)); }
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}
function s(tag, attrs, ...kids) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
  for (const c of kids) n.append(c);
  return n;
}
const hide = { "aria-hidden": "true", focusable: "false" };
/* the page's sprite symbols (index.html), drawn in place where a harness page has no sprite */
const DRAWN = {
  "m-fiction": () => [s("circle", { cx: 6, cy: 6, r: 4.25, fill: "none", stroke: "currentColor", "stroke-width": 1.5 })],
  "m-assumption": () => [s("circle", { cx: 6, cy: 6, r: 4.25, fill: "none", stroke: "currentColor", "stroke-width": 1.5 }), s("path", { d: "M6 1A5 5 0 0 0 6 11Z", fill: "currentColor" })],
  "m-fact": () => [s("circle", { cx: 6, cy: 6, r: 5, fill: "currentColor" })],
};
const mark = (kind, cls) => s("svg", { class: cls || "sc-mark", viewBox: "0 0 12 12", ...hide },
  ...(document.getElementById(`m-${kind}`) ? [s("use", { href: `#m-${kind}` })] : DRAWN[`m-${kind}`]()));
const icon = (id) => (id && document.getElementById(id) ? s("svg", { class: "icon", viewBox: "0 0 24 24", ...hide }, s("use", { href: `#${id}` })) : null);
const fig = (text, fact, label) => traced(text, fact, label, "fig");
/* a number with a facts row is a button that opens its thread (U6's drawer, store.thread); plain text otherwise */
function traced(text, fact, label, cls) {
  return fact ? h("button", { type: "button", class: `${cls || ""} sc-traced`.trim(), "data-fact": fact, "aria-haspopup": "dialog", "aria-controls": "thread",
    "aria-label": `${label ? `${label}: ` : ""}${text}. Open where this number came from.` }, text) : h("span", { class: cls || null, text });
}
/* the fact path of a number on screen, only for an unchanged move on record */
const pathOf = (ctx, rest) => (ctx.S.source === "preset" && ctx.S.presetId && ctx.m.presets.some((p) => p.id === ctx.S.presetId && p.answer === ctx.S.raw)
  ? factOf(ctx.m, `presets.${ctx.S.presetId}.${rest}`) : null);

/* ---- the two live calls (relative URLs on the page's own server; a plain sentence on failure, never an exception's text) ---- */
const NO_SERVER = "The scenario engine could not be reached. Try again.";
const UNREAD = "The navigator could not read that. Try other words, or start from a move on record.";
async function post(url, body, signal, fallback) {
  let res;
  try { res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal }); }
  catch (e) { if (e && e.name === "AbortError") throw e; throw Object.assign(new Error(NO_SERVER), { plain: true }); }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  const said = data && typeof data.message === "string" && data.message.trim() ? data.message.trim() : null;
  if (!res.ok || !data || data.status === "error") throw Object.assign(new Error(said || fallback), { plain: true });
  return data;
}
const plainOf = (e, fallback) => (e && e.plain && e.message ? e.message : fallback);

/* a duration token of styles.css in ms (the page's motion reads its tokens, never a literal) */
function tokenMs(name, fallback) {
  const v = String(getComputedStyle(document.documentElement).getPropertyValue(name) || "").trim();
  const n = parseFloat(v);
  return Number.isFinite(n) ? (v.endsWith("ms") ? n : v.endsWith("s") ? n * 1000 : n) : fallback;
}
/* motion: R9's switch and the reader's preference, read at call time */
const still = () => globalThis.EPI_MOTION === false || !globalThis.matchMedia || globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* the stylesheet, when the page did not link it (index.html's data-css does; a harness page may not) */
function ensureCss() {
  if (document.querySelector('link[href$="css/scenario.css"]')) return;
  const l = document.createElement("link");
  l.rel = "stylesheet"; l.href = new URL("../css/scenario.css", import.meta.url).href;
  document.head.append(l);
}

/* ---- the pieces ---- */
/* closed (the default): ONE line, the question and the way in; no number (controller, 12:40) */
function head(ctx) {
  const open = ctx.S.built;
  const arrow = s("svg", { class: "sc-arrow", viewBox: "0 0 24 24", ...hide },
    s("path", { d: "M4.5 12h14M13 6.5l5.5 5.5-5.5 5.5", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }));
  ctx.opener = h("button", { type: "button", class: "btn btn-quiet sc-open", "aria-expanded": String(open), "aria-controls": "sc-builder",
    onclick: () => ctx.setBuilt(!ctx.S.built) }, h("span", { text: open ? LINE.close : LINE.open }), arrow);
  return h("header", { class: "sc-line" }, h("h2", { class: "sc-title", id: "sc-title", text: LINE.question }), ctx.opener);
}

function askForm(ctx) {
  const live = ctx.live;
  const q = h("textarea", { class: "sc-q", id: "sc-q", rows: 1, maxlength: 280, spellcheck: "true", autocomplete: "off",
    placeholder: EXAMPLES[ctx.S.example % EXAMPLES.length], readonly: live ? null : true, "aria-describedby": "sc-hint" });
  q.value = ctx.S.text || "";
  const go = h("button", { type: "submit", class: "btn btn-primary sc-go", "aria-disabled": ctx.S.reading ? "true" : null },
    ctx.S.reading ? [icon("i-spin"), h("span", { text: "Reading" })] : h("span", { text: "Test it" }));
  const hint = h("p", { class: "sc-hint", id: "sc-hint", role: "status",
    text: ctx.S.askNote || (live ? "Press Enter to read it. Then move any factor yourself." : "This saved page cannot read new words; start from a move on record below. The live app reads your own.") });
  const form = h("form", { class: "sc-ask", "aria-label": "Describe a future to test", novalidate: true },
    h("label", { class: "sr", for: "sc-q", text: "Describe a future you want to test" }),
    h("div", { class: "sc-field" }, q, go), hint);
  form.addEventListener("submit", (e) => { e.preventDefault(); ctx.ask(q.value || q.placeholder); });
  q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
  q.addEventListener("input", () => { ctx.S.text = q.value; });
  return form;
}

function presetRow(ctx) {
  const m = ctx.m;
  if (!m.presets.length) return null;
  return h("div", { class: "sc-presets", role: "group", "aria-labelledby": "sc-presets-lbl" },
    h("span", { class: "sc-presets-lbl", id: "sc-presets-lbl", text: ctx.live ? "Or start from a move on record:" : "Start from a move on record:" }),
    h("div", { class: "sc-presets-list" }, m.presets.map((p) => h("button", { type: "button", class: "chip sc-preset",
      "aria-pressed": String(ctx.S.source === "preset" && ctx.S.presetId === p.id), "data-id": p.id, title: p.source || null,
      onclick: () => ctx.pickPreset(p.id) }, h("span", { text: p.label })))));
}

/* one factor: its name and move, the track with the precedents engraved under it, the reason in one line */
function chip(ctx, c) {
  const f = ctx.m.byId[c.id], t = trackOf(f, c.value);
  const val = h("output", { class: "sc-chip-val", for: `sc-r-${c.id}`, text: shockText(c.value, c.unit, ctx.PF) });
  const fill = h("span", { class: "sc-fill", "aria-hidden": "true" });
  const place = (v) => { const p = trackOf(f, v); fill.style.setProperty("--a", String(Math.min(p.x, p.zero))); fill.style.setProperty("--b", String(Math.max(p.x, p.zero))); };
  const range = t ? h("input", { type: "range", class: "sc-range", id: `sc-r-${c.id}`, min: t.lo, max: t.hi, step: "any", value: c.value,
    disabled: ctx.live ? null : true, "aria-label": `${f.full || c.label}: its move in this scenario`, "aria-valuetext": shockText(c.value, c.unit, ctx.PF),
    "aria-describedby": c.why ? `sc-why-${c.id}` : null }) : null;
  if (range) {
    range.addEventListener("input", () => {
      const v = snapTo(f, Number(range.value));
      if (v !== Number(range.value)) range.value = String(v);
      const text = shockText(v, c.unit, ctx.PF);
      val.textContent = text; range.setAttribute("aria-valuetext", text); place(v);
      ctx.moveFactor(c.id, v, false);
    });
    range.addEventListener("change", () => ctx.moveFactor(c.id, snapTo(f, Number(range.value)), true));
    /* the instrument's keys (no animation: a keyboard action lands at once) */
    let now = c.value;
    range.addEventListener("input", () => { now = snapTo(f, Number(range.value)); });
    range.addEventListener("keydown", (e) => {
      const v = keyStep(f, now, e.key, t.step);
      if (v === null) return;
      e.preventDefault();
      now = Number(v.toFixed(6));
      range.value = String(now);
      const text = shockText(now, c.unit, ctx.PF);
      val.textContent = text; range.setAttribute("aria-valuetext", text); place(now);
      ctx.moveFactor(c.id, now, false);
    });
  }
  const li = h("li", { class: "sc-chip", "data-id": c.id },
    h("div", { class: "sc-chip-top" }, h("label", { class: "sc-chip-name", for: range ? `sc-r-${c.id}` : null, title: f.source || null, text: c.label }), val),
    t ? h("div", { class: "sc-track", vars: { "--z": t.zero } },
      h("span", { class: "sc-rail", "aria-hidden": "true" }), fill, h("span", { class: "sc-zero", "aria-hidden": "true" }),
      t.marks.map((mk) => h("span", { class: "sc-notch", "data-on": on(ctx, c, mk) ? "yes" : null, "aria-hidden": "true", vars: { "--m": mk.x } })), range) : null,
    t && t.marks.length ? h("div", { class: "sc-marks", "aria-hidden": "true" }, t.marks.filter((mk) => mk.lane >= 0).map((mk) =>
      h("span", { class: "sc-mark-lbl", "data-on": on(ctx, c, mk) ? "yes" : null, "data-lane": mk.lane, "data-side": mk.x > 0.72 ? "end" : mk.x < 0.28 ? "start" : "mid", vars: { "--m": mk.x }, text: mk.label }))) : null,
    c.why ? h("p", { class: "sc-why", id: `sc-why-${c.id}`, text: c.why }) : null);
  if (t) place(c.value);
  return li;
}

/* the precedent the chip sits on: the preset's own, or the one the navigator anchored to, when the value is still its size */
const on = (ctx, c, mk) => Math.abs(mk.value - c.value) < 1e-9 && ((ctx.S.source === "preset" && mk.preset === ctx.S.presetId) ||
  (ctx.S.source === "read" && ctx.S.anchors && ctx.S.anchors[c.id] === mk.id) || ctx.S.source === "custom");

/* a factor the reading left at zero, offered in the details (live only): one tap adds it at zero */
function idleChip(ctx, f) {
  return h("button", { type: "button", class: "chip sc-add", "aria-label": `Add ${f.label} to the scenario`, onclick: () => ctx.addFactor(f.id) },
    h("span", { class: "sc-plus", "aria-hidden": "true" }), h("span", { text: f.label }));
}

/* the gauge: falls grow right from zero, the floor one gold rule, the move magenta, today's mix grey under it (no figure: the
   sentence says the number; the gauge only shows where it lands against the floor) */
function gauge(ctx, out) {
  const m = ctx.m, sides = out.sides, floor = m.floor;
  const reach = Math.max(floor ? Math.abs(floor.v) : 0, ...sides.map((x) => Math.max(0, -x.fall)));
  const gain = Math.max(0, ...sides.map((x) => x.fall));
  const z = gain > 0 ? 0.2 : 0, dom = reach > 0 ? reach * 1.18 : 1;
  const xOf = (v) => (v <= 0 ? z + (-v / dom) * (1 - z) : z - (gain > 0 ? (v / gain) * z * 0.9 : 0));
  const bar = (x) => { const a = xOf(0), b = xOf(x.fall); return h("span", { class: `sc-g-bar is-${x.key === "after" ? "move" : "today"}`,
    "data-dir": x.fall > 0 ? "gain" : "fall", vars: { "--l": Math.min(a, b), "--w": Math.abs(b - a) } }); };
  const fx = floor ? xOf(floor.v) : null, mainX = xOf(out.main.fall);
  return h("div", { class: "sc-gauge", "aria-hidden": "true", vars: { "--f": fx, "--z": z } },
    h("span", { class: "sc-g-zero" }),
    sides.slice().reverse().map(bar),
    fx !== null && mainX > fx ? h("span", { class: "sc-g-past", vars: { "--a": fx, "--b": mainX } }) : null,
    fx !== null ? h("span", { class: "sc-g-floor" }) : null,
    fx !== null ? h("span", { class: "sc-g-floor-lbl", "data-side": fx > 0.7 ? "end" : "start" }, h("span", { text: "Your floor" }), h("b", { class: "inst", text: floor.text })) : null,
    sides.length > 1 ? h("span", { class: "sc-g-key" }, sides.map((x) => h("span", { class: `sc-g-k is-${x.key === "after" ? "move" : "today"}`, text: x.key === "after" ? "With the move" : x.label }))) : null);
}

function answerBlock(ctx) {
  const S = ctx.S, out = S.outcome;
  if (S.error) return h("div", { class: "sc-answer is-error" }, h("p", { class: "sc-error", text: S.error }));
  if (!out && S.pending) return h("div", { class: "sc-answer is-empty", "aria-busy": "true" }, h("p", { class: "sc-empty", text: "The engine is working it out." }));
  if (!out) return h("div", { class: "sc-answer is-empty" },
    h("p", { class: "sc-empty", text: S.source === "none" ? "Describe a future above, then press Test it: the answer lands here."
      : S.clarify ? "Nothing to test yet: say which market would move." : "Nothing to test yet: the words named no market move." }));
  const main = out.main;
  return h("div", { class: `sc-answer${S.fresh ? " is-fresh" : ""}`, "data-tone": main.tone, "data-key": main.key, "aria-busy": S.pending ? "true" : null },
    h("p", { class: "sc-ans-kind" }, mark("fiction"), h("span", { text: main.key === "after" ? `${main.label}, in this made-up scenario` : "Your mix, in this made-up scenario" })),
    h("p", { class: `sc-big is-${main.key === "after" ? "move" : "today"}` }, h("span", { class: "sr", text: main.fall > 0 ? "Rise: " : "Fall: " }),
      traced(main.fallText, pathOf(ctx, `${main.key}.fall`), main.label)),
    gauge(ctx, out),
    h("p", { class: "sc-sentence" }, out.sentence.map((p) => (p.fig ? fig(p.text, p.text === main.dollarsText ? pathOf(ctx, `${main.key}.dollars`) : null, main.label)
      : p.close ? h("span", { class: "sc-close", "data-tone": main.tone, text: p.text }) : p.text)),
      main.icon ? h("span", { class: "sc-ans-status", "data-tone": main.tone }, icon(main.icon), h("span", { class: "sr", text: main.word })) : null),
    realLine(ctx),
    ctx.checked && !main.close ? h("p", { class: "sc-checked" }, mark("assumption"), h("span", {}, ctx.checked.lead, fig(ctx.checked.figure), ctx.checked.tail)) : null,
    out.uncovered.length ? h("p", { class: "sc-fiction", text: `No measured sensitivity for ${out.uncovered.join(", ")}: ${out.uncovered.length === 1 ? "it adds" : "they add"} nothing to this answer.` }) : null,
    h("p", { class: "sc-fiction", text: "Fictional illustration, not a recommendation. No odds: a scenario has no probability here." }));
}

/* the real replay of the episode a move on record copies (only while the investor has not changed it): a fact, marked so */
function realLine(ctx) {
  const S = ctx.S, p = S.source === "preset" ? ctx.m.presets.find((x) => x.id === S.presetId && x.answer === S.raw) : null;
  if (!p || !p.real) return null;
  return h("p", { class: "sc-real", "data-cls": p.real.cls }, mark("fact"), h("span", {}, p.real.lead, fig(p.real.figure), p.real.tail,
    " This already happened; it is not a forecast."));
}

/* ---- the details (R22: one quiet disclosure) ---- */
function sidesBlock(ctx, out) {
  return h("div", { class: "sc-sides", role: "group", "aria-label": "Both mixes in this scenario" }, out.sides.map((x) => h("div", { class: `sc-side is-${x.key === "after" ? "move" : "today"}` },
    h("p", { class: "sc-side-lbl", text: x.label }),
    h("p", { class: "sc-side-n" }, traced(x.fallText, pathOf(ctx, `${x.key}.fall`), x.label, "inst"),
      x.dollarsText && ctx.m.amountText ? h("span", { class: "sc-side-d" }, fig(x.dollarsText, pathOf(ctx, `${x.key}.dollars`), x.label), ` on your ${ctx.m.amountText}`) : null),
    x.word ? h("p", { class: "sc-side-w", "data-tone": x.tone }, icon(x.icon), h("span", { text: x.word })) : null)));
}

function contribBlock(ctx, out) {
  if (!out.contributions.length) return null;
  const rise = out.main.fall > 0;
  return h("div", { class: `sc-block${ctx.S.fresh ? " is-fresh" : ""}`, role: "group", "aria-labelledby": "sc-who" },
    h("h3", { class: "sc-h3", id: "sc-who" }, mark("assumption"), h("span", { text: rise ? "Who carries the move" : "Who carries the fall" })),
    h("p", { class: "sc-sub", text: "Each holding’s share of the move, in points of your mix, from its measured sensitivities." }),
    h("ul", { class: "sc-bars" }, out.contributions.map((x) => h("li", { class: `sc-bar-row${x.isMove ? " is-move" : ""}` },
      h("span", { class: "sc-bar-name", text: x.name }),
      h("span", { class: "sc-bar-track", "aria-hidden": "true" }, h("span", { class: `sc-bar${x.isMove ? " is-move" : ""}`, "data-dir": x.value > 0 ? "gain" : "fall", vars: { "--w": x.w } })),
      traced(x.text, pathOf(ctx, `contributions.${x.ticker}`), x.name, "sc-bar-val inst")))));
}

/* the engine against what really happened: each real episode's factor moves fed to the engine, its fall next to the real one */
function validationBlock(ctx) {
  const v = ctx.m.validation, PF = ctx.PF, mv = ctx.m.move;
  if (!v) return null;
  const pct = (x) => (x === null ? "" : signedPct(x, PF));
  const col = (label, cls) => h("span", { role: "columnheader", class: `sc-v-c ${cls}`, text: label });
  const two = mv && v.rows.some((x) => x.realAfter !== null);
  const cell = (x, kind, path, label) => h("span", { role: "cell", class: `sc-v-c c-${kind === "fact" ? "real" : "model"}` },
    x !== null ? [mark(kind), traced(pct(x), factOf(ctx.m, path), label, "inst")] : null);
  const sub = (x, side) => {
    const g = x.gap ? (x.gap.one !== undefined ? (side === (two ? "after" : "today") ? x.gap.one : null) : x.gap[side]) : null;
    const real = side === "after" ? x.realAfter : x.realToday, model = side === "after" ? x.modelAfter : x.modelToday;
    if (real === null && model === null) return null;
    return h("div", { role: "row", class: `sc-v-row is-${side === "after" ? "move" : "today"}` },
      h("span", { role: "rowheader", class: "sc-v-c c-ep" }, h("span", { class: "sc-v-ep", text: x.episode }), h("span", { class: "sc-v-mix", text: side === "after" ? "With the move" : "Today\u2019s mix" })),
      cell(real, "fact", `validation.${x.id}.real_${side}`, `${x.episode}, really`), cell(model, "assumption", `validation.${x.id}.model_${side}`, `${x.episode}, the engine`),
      h("span", { role: "cell", class: "sc-v-c c-gap", text: g === null ? "" : gapWords(g) }));
  };
  return h("div", { class: "sc-block", role: "group", "aria-labelledby": "sc-val" },
    h("h3", { class: "sc-h3", id: "sc-val", text: "The engine against what really happened" }),
    h("p", { class: "sc-sub", text: "The engine was fed each real episode’s factor moves; next to its fall, the fall that really happened. This already happened; it is not a forecast." }),
    h("div", { class: "sc-vtable", role: "table", "aria-labelledby": "sc-val" },
      h("div", { role: "row", class: "sc-v-row sc-v-head" }, col("Episode", "c-ep"), col("Really", "c-real"), col("The engine", "c-model"), col("The engine was", "c-gap")),
      v.rows.map((x) => h("div", { role: "rowgroup", class: "sc-v-group" }, two ? sub(x, "after") : null, sub(x, "today")))));
}

function methodBlock(ctx) {
  const m = ctx.m;
  return h("div", { class: "sc-block sc-method" },
    h("h3", { class: "sc-h3", id: "sc-how" }, mark("assumption"), h("span", { text: "How the engine works" })),
    m.method ? h("p", { class: "sc-sub", text: m.method }) : null,
    h("p", { class: "sc-sub", text: "It cannot see a crisis change how markets move together. The sensitivities are measured; the scenario is yours." }));
}

function detailsBody(ctx) {
  const out = ctx.S.outcome, folded = ctx.chips.folded, idle = ctx.live ? ctx.chips.idle : [];
  return [
    out ? sidesBlock(ctx, out) : null,
    folded.length ? h("div", { class: "sc-block", role: "group", "aria-labelledby": "sc-more-h" },
      h("h3", { class: "sc-h3", id: "sc-more-h", text: "The smaller moves in this scenario" }),
      h("ul", { class: "sc-chips is-folded" }, folded.map((c) => chip(ctx, c)))) : null,
    ctx.chips.implied.length ? h("div", { class: "sc-block", role: "group", "aria-labelledby": "sc-with-h" },
      h("h3", { class: "sc-h3", id: "sc-with-h" }, mark("assumption"), h("span", { text: "What moves with it" })),
      h("p", { class: "sc-sub", text: `The engine moves the factors you did not name with the ones you did, as they moved together week to week since 2021.` }),
      h("ul", { class: "sc-co" }, ctx.chips.implied.map((c) => h("li", { class: "sc-co-row" },
        h("span", { class: "sc-co-name", title: (ctx.m.byId[c.id] && ctx.m.byId[c.id].source) || null, text: c.label }),
        h("span", { class: "sc-co-val inst", text: shockText(c.value, c.unit, ctx.PF) }),
        ctx.live ? h("button", { type: "button", class: "linkbtn sc-co-set", "aria-label": `Set ${c.label} yourself`, onclick: () => ctx.promote(c.id, c.value) }, "Set it yourself") : null)))) : null,
    idle.length ? h("div", { class: "sc-block sc-idle", role: "group", "aria-labelledby": "sc-idle-h" },
      h("h3", { class: "sc-h3", id: "sc-idle-h", text: "Move another factor" }),
      h("div", { class: "sc-adds" }, idle.map((f) => idleChip(ctx, f)))) : null,
    out ? contribBlock(ctx, out) : null,
    validationBlock(ctx),
    methodBlock(ctx),
  ];
}

/* ---- the whole section ---- */
function readingHead(ctx) {
  const S = ctx.S, p = S.source === "preset" ? ctx.m.presets.find((x) => x.id === S.presetId) : null;
  const title = S.source === "read" ? "Your words, as the navigator read them" : p ? `${p.label}, as measured` : S.source === "none" ? "Your scenario, as the navigator will read it" : "Your scenario";
  return [h("h3", { class: "sc-h3", id: "sc-read-h" }, mark("fiction"), h("span", { text: title })),
    p && p.source ? h("p", { class: "sc-src", text: p.source }) : null,
    S.source === "read" && S.by ? h("p", { class: "sc-src sc-by", text: S.by }) : null];
}

function build(ctx) {
  const S = ctx.S, c = ctx.chips;
  if (ctx.m.staticOnly) return h("div", { class: "sc frame", "data-built": "no" }, h("header", { class: "sc-line" },
    h("h2", { class: "sc-title", id: "sc-title", text: LINE.question }), h("p", { class: "sc-static", text: LINE.staticOnly })));
  const line = moreLine(c), more = line ? h("p", { class: "sc-more", text: line }) : null;
  const reading = h("div", { class: "sc-reading", role: "group", "aria-labelledby": "sc-read-h" }, readingHead(ctx),
    c.shown.length ? h("ul", { class: "sc-chips" }, c.shown.map((x) => chip(ctx, x))) : null, more,
    S.unmapped ? h("p", { class: "sc-unmapped", text: S.unmapped }) : null,
    S.clarify ? h("p", { class: "sc-clarify" }, h("b", { text: "The navigator asks: " }), S.clarify) : null,
    !ctx.live ? h("p", { class: "sc-note", text: "Moving a factor needs the live app; this saved page shows the moves on record." }) : null);
  ctx.answerSlot = h("div", { class: "sc-slot-answer" }, answerBlock(ctx));
  ctx.say = h("p", { class: "sr", role: "status", "aria-live": "polite" });
  ctx.detailsSlot = h("div", { class: "sc-details", id: "sc-details", hidden: !S.open }, detailsBody(ctx));
  const btn = h("button", { type: "button", class: "linkbtn sc-toggle", "aria-expanded": String(S.open), "aria-controls": "sc-details",
    text: S.open ? "Hide the details" : "Show the details", onclick: () => ctx.setOpen(!S.open, true) });
  ctx.toggle = btn;
  ctx.builder = h("div", { class: "sc-builder", id: "sc-builder", hidden: !S.built, role: "region", "aria-labelledby": "sc-title" },
    h("p", { class: "sc-lede", id: "sc-lede", text: "Describe a future you want to test. It is a scenario you build, not a forecast." }),
    askForm(ctx), presetRow(ctx), h("div", { class: "sc-desk" }, reading, ctx.answerSlot), ctx.say, h("div", { class: "sc-more-row" }, btn), ctx.detailsSlot);
  return h("div", { class: "sc frame", "data-live": ctx.live ? "yes" : "no", "data-built": S.built ? "yes" : "no" }, head(ctx), ctx.builder);
}

export function mount(el, store) {
  ensureCss();
  el.setAttribute("aria-labelledby", "sc-title");
  el.classList.add("sc-section");
  const S = { source: "preset", presetId: null, shocks: {}, why: {}, extra: new Set(), unmapped: null, clarify: null, text: "", raw: null,
    outcome: null, pending: false, reading: false, error: null, askNote: null, open: store.get().depth === "detailed",
    built: store.get().depth === "detailed", example: 0, forResult: null };
  let ctx = null, ctl = null, timer = 0, asked = 0;          // asked: the latest reading; an older one that lands late is dropped
  const live = () => store.get().mode === "live";

  function reset(m, result) {
    const p = firstPreset(result, m);
    Object.assign(S, { source: p ? "preset" : "none", presetId: p ? p.id : null, shocks: p ? { ...p.shocks } : {}, why: {}, extra: new Set(),
      unmapped: null, clarify: null, raw: p ? p.answer : null, pending: false, reading: false, error: null, askNote: null, fresh: true,
      readMarks: null, anchors: {} });
  }
  function render() {
    const st = store.get(), PF = globalThis.PF;
    const base0 = PF && PF.fmt ? scenarioModel(st.result, PF, { live: live() }) : { show: false };
    const base = base0.liveOnly ? withBook(base0, S.book) : base0;
    const m = S.source === "read" && !base.liveOnly ? withMarks(base, S.readMarks) : base;
    el.hidden = !m.show;
    if (!m.show) { el.replaceChildren(); ctx = null; return; }
    if (m.staticOnly) { ctx = null; el.replaceChildren(build({ S, m, chips: null })); return; }
    if (S.forResult !== st.result) { reset(m, st.result); S.forResult = st.result; }
    const focus = document.activeElement && el.contains(document.activeElement) ? keyOf(document.activeElement) : null;
    S.outcome = S.raw ? outcomeOf(S.raw, m, PF) : null;
    ctx = { S, m, PF, live: live(), chips: chipsOf(S.shocks, m, S.why, undefined, S.extra, S.outcome && S.outcome.implied), checked: checkedLine(m.validation), ...actions };
    el.replaceChildren(build(ctx));
    relane();
    if (!S.pending && S.fresh) { announce(); countUp(); }
    if (focus) { const n = el.querySelector(focus); if (n) n.focus({ preventScroll: true }); }
  }
  /* an answer landed (or is on its way): only the answer and the details move, the sliders keep the pointer */
  /* the sentence, once, for a screen reader (never each compute of a drag: only a settled answer) */
  function announce() {
    if (!ctx || !ctx.say) return;
    const n = el.querySelector(".sc-sentence"), e = el.querySelector(".sc-error, .sc-empty");
    ctx.say.textContent = n ? n.textContent : e ? e.textContent : "";
  }
  /* the big figure counts to its value for a fresh scenario (one rAF loop, --dur-lamp + 100 ms, ease-out, landing on
     the exact Result value); a slider's answer, reduced motion or the motion switch: the value at once */
  let count = 0;
  function countUp() {
    cancelAnimationFrame(count);
    const big = el.querySelector(".sc-answer.is-fresh .sc-big"), out = S.outcome;
    if (!big || !out || still() || !S.built) return;
    const end = out.main.fall, text = out.main.fallText, PF = globalThis.PF, ms = tokenMs("--dur-lamp", 400) + 100, t0 = performance.now();
    const ease = (x) => 1 - Math.pow(1 - x, 3);
    const frame = (now) => {
      const p = Math.min(1, (now - t0) / ms);
      big.lastChild.textContent = p < 1 ? (end > 0 ? "+" : "") + PF.fmt.pct(end * ease(p)) : text;
      if (p < 1) count = requestAnimationFrame(frame);
    };
    count = requestAnimationFrame(frame);
  }
  function renderAnswer() {
    if (!ctx) return;
    S.outcome = S.raw ? outcomeOf(S.raw, ctx.m, ctx.PF) : null;
    ctx.chips = chipsOf(S.shocks, ctx.m, S.why, undefined, S.extra, S.outcome && S.outcome.implied);
    ctx.answerSlot.replaceChildren(answerBlock(ctx));
    const held = document.activeElement && ctx.detailsSlot.contains(document.activeElement) ? document.activeElement.closest(".sc-block") : null;
    const body = detailsBody(ctx).filter(Boolean);
    if (held) { const i = body.findIndex((b) => b.getAttribute("aria-labelledby") === held.getAttribute("aria-labelledby")); if (i >= 0) body[i] = held; }
    ctx.detailsSlot.replaceChildren(...body);
    const line = moreLine(ctx.chips);
    let more = el.querySelector(".sc-more");
    if (!more && line) { const list = el.querySelector(".sc-reading > .sc-chips"); if (list) { more = h("p", { class: "sc-more" }); list.after(more); } }
    if (more) { if (line) more.textContent = line; else more.remove(); }
    if (!S.pending) { announce(); countUp(); }
    relane();
    el.querySelectorAll(".sc-preset").forEach((b) => b.setAttribute("aria-pressed", String(S.source === "preset" && S.presetId === b.dataset.id)));
  }

  function compute(now) {
    clearTimeout(timer);
    const preset = ctx && ctx.m.presets.find((p) => sameShocks(p.shocks, S.shocks));
    if (preset) { if (ctl) ctl.abort(); S.raw = preset.answer; S.error = null; S.pending = false; renderAnswer(); return; }
    if (!live()) return;
    const go = async () => {
      if (ctl) ctl.abort();
      const mine = (ctl = new AbortController());
      S.pending = true; if (ctx) ctx.answerSlot.firstChild && ctx.answerSlot.firstChild.setAttribute("aria-busy", "true");
      try {
        const data = await post("/api/scenario", scenarioBody(store.get().result, S.shocks), mine.signal, NO_SERVER);
        if (mine !== ctl) return;
        S.raw = data; S.error = null;
      } catch (e) {
        if (e && e.name === "AbortError") return;
        S.error = plainOf(e, NO_SERVER);
      }
      S.pending = false; renderAnswer();
    };
    if (now) go(); else timer = setTimeout(go, 220);
  }

  const actions = {
    pickPreset(id) {
      const p = ctx && ctx.m.presets.find((x) => x.id === id);
      if (!p) return;
      asked += 1; S.reading = false;
      if (ctl) ctl.abort();
      Object.assign(S, { source: "preset", presetId: id, shocks: { ...p.shocks }, why: {}, extra: new Set(), unmapped: null, clarify: null,
        raw: p.answer, pending: false, error: null, askNote: null, fresh: true });
      render();
    },
    async ask(text) {
      const words = String(text || "").trim();
      if (!words || S.reading) return;
      if (!live()) { S.askNote = "This saved page cannot read new words; the moves on record below work here. The live app reads your own."; const n = el.querySelector("#sc-hint"); if (n) n.textContent = S.askNote; return; }
      S.reading = true; S.text = words; S.askNote = null; render();
      const mine = (asked += 1), forResult = store.get().result;
      try {
        const raw = await post("/api/scenario/read", readBody(forResult, words), undefined, UNREAD);
        if (mine !== asked || store.get().result !== forResult || !ctx) return;      // a move on record or another run since
        const got = readingOf(raw, ctx.m.liveOnly ? withBook(ctx.m, raw) : ctx.m);
        if (got.blocked) { S.reading = false; S.askNote = got.message || UNREAD; render(); return; }      // the scenario on screen stays
        Object.assign(S, { source: "read", presetId: null, shocks: got.shocks, why: got.why, extra: new Set(), unmapped: got.unmapped, clarify: got.clarify,
          by: got.by, readMarks: anchoredMarks(raw), anchors: (raw && raw.anchors) || {}, book: raw, error: null });
        S.raw = null; S.pending = !got.empty; S.fresh = true;  // never the last scenario's numbers under a new reading
        S.reading = false; render();
        if (!got.empty) compute(true);
      } catch (e) {
        if (mine !== asked) return;
        S.reading = false; S.askNote = plainOf(e, UNREAD); render();
      }
    },
    moveFactor(id, v, final) {
      S.shocks = { ...S.shocks, [id]: v };
      S.fresh = false;
      if (S.source === "preset") { S.source = "custom"; el.querySelectorAll(".sc-preset").forEach((b) => b.setAttribute("aria-pressed", "false")); }
      if (S.source === "custom") { const t = el.querySelector("#sc-read-h span"); if (t) t.textContent = "Your scenario"; const src = el.querySelector(".sc-src"); if (src) src.remove(); }
      compute(final);
    },
    promote(id, value) {                                   // an implied co-move becomes the investor's own slider, at its size
      S.shocks = { ...S.shocks, [id]: value };
      if (S.source === "preset") S.source = "custom";
      render();
      const n = el.querySelector(`#sc-r-${CSS.escape(id)}`);
      if (n) n.focus({ preventScroll: false });
      compute(true);
    },
    addFactor(id) {
      S.extra = new Set([...S.extra, id]);
      S.shocks = { ...S.shocks, [id]: 0 };
      if (S.source === "preset") S.source = "custom";
      render();
      const n = el.querySelector(`#sc-r-${CSS.escape(id)}`);
      if (n) n.focus({ preventScroll: false });
    },
    setBuilt(open) {
      S.built = !!open;
      if (!ctx) return;
      ctx.builder.hidden = !S.built;
      ctx.opener.setAttribute("aria-expanded", String(S.built));
      ctx.opener.firstChild.textContent = S.built ? LINE.close : LINE.open;
      el.querySelector(".sc").dataset.built = S.built ? "yes" : "no";
      if (S.built) { relane(); if (!still()) ctx.builder.classList.add("is-opening"); if (S.fresh) countUp(); }
    },
    setOpen(open, byUser) {
      S.open = !!open;
      if (!ctx) return;
      ctx.detailsSlot.hidden = !S.open;
      if (S.open) relane();
      ctx.toggle.setAttribute("aria-expanded", String(S.open));
      ctx.toggle.textContent = S.open ? "Hide the details" : "Show the details";
      if (byUser && S.open && !still()) ctx.detailsSlot.classList.add("is-opening");
    },
  };

  /* the engraved labels: measured after layout, so two never overlap at any width (a second line, else only the notch) */
  function relane() {
    el.querySelectorAll(".sc-marks").forEach((box) => {
      const labels = [...box.children].sort((a, b) => Number(a.style.getPropertyValue("--m")) - Number(b.style.getPropertyValue("--m")));
      labels.forEach((n) => { n.dataset.lane = "0"; });
      const right = [-Infinity, -Infinity];
      let lanes = labels.length ? 1 : 0;
      for (const n of labels) {
        const r = n.getBoundingClientRect();
        const lane = r.left >= right[0] + 12 ? 0 : r.left >= right[1] + 12 ? 1 : -1;
        n.dataset.lane = String(lane);
        if (lane >= 0) { right[lane] = r.right; lanes = Math.max(lanes, lane + 1); }
      }
      box.dataset.lanes = String(lanes);
    });
  }
  let sized = 0;
  if (typeof ResizeObserver === "function") new ResizeObserver(() => { cancelAnimationFrame(sized); sized = requestAnimationFrame(relane); }).observe(el);

  /* the focused control again after a redraw: its id, else its preset id */
  function keyOf(n) {
    if (n.id) return `#${CSS.escape(n.id)}`;
    if (n.dataset && n.dataset.id && n.classList.contains("sc-preset")) return `.sc-preset[data-id="${CSS.escape(n.dataset.id)}"]`;
    if (n.classList && n.classList.contains("sc-toggle")) return ".sc-toggle";
    if (n.classList && n.classList.contains("sc-open")) return ".sc-open";
    return null;
  }

  /* the examples turn over in the empty box while the section is in view (no motion: only the words change; off when motion is) */
  let inView = false;
  if (typeof IntersectionObserver === "function") new IntersectionObserver((e) => { inView = e.some((x) => x.isIntersecting); }).observe(el);
  setInterval(() => {
    const q = el.querySelector("#sc-q");
    if (!q || !S.built || still() || !inView || q.value || document.activeElement === q) return;
    S.example = (S.example + 1) % EXAMPLES.length;
    q.placeholder = EXAMPLES[S.example];
  }, 4800);

  el.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-fact]");
    if (b && el.contains(b)) store.set({ thread: b.dataset.fact });
  });
  store.on("result", render);
  store.on("mode", render);
  store.on("depth", (d) => { actions.setBuilt(d === "detailed"); actions.setOpen(d === "detailed", false); });
  render();
  return { render, state: S };
}
