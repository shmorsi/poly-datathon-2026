/* #dial, "Where it breaks" (design doc §2 item 3, rulings R1, R2, R5, R13; lane U4). A ruler over tipping_point.curve: the thumb
   starts at the asked size; a drag follows the pointer size by size with no easing, a click jumps, the keys step (no animation).
   Every size change: store.set({weightIndex}) (the lamp follows), store.get().race?.setWeight(i) (the chart's magenta path morphs).
   Words and numbers come from web/lib/dial.js (Result keys only); the browser never judges a size, it reads curve[i].verdict. */
import { dialModel, readout, rollTexts, figuresOf, nearestIndex, keyStep, crossed, easeOut, WHAT_IF } from "../lib/dial.js";
import { say } from "../lib/meaning.js";
import { head, details, mean } from "./clarity.js";

const SVG = "http://www.w3.org/2000/svg";
const ICONS = {   // the page's status symbols (index.html i-in / i-warn / i-out), drawn inline so the dial stands alone
  "i-in": [["circle", { cx: 12, cy: 12, r: 9.5, fill: "none", stroke: "currentColor", "stroke-width": 2 }],
    ["path", { d: "M7.5 12.3l3 3 6-6.3", fill: "none", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" }]],
  "i-warn": [["path", { d: "M12 3l9.5 17h-19z", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linejoin": "round" }],
    ["path", { d: "M12 9.5v5", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 17.4, r: 1.25, fill: "currentColor" }]],
  "i-out": [["path", { d: "M8.2 2.5h7.6l5.7 5.7v7.6l-5.7 5.7H8.2l-5.7-5.7V8.2z", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linejoin": "round" }],
    ["path", { d: "M12 7v6.2", stroke: "currentColor", "stroke-width": 2.2, "stroke-linecap": "round" }], ["circle", { cx: 12, cy: 16.8, r: 1.35, fill: "currentColor" }]],
  "i-pending": [["circle", { cx: 12, cy: 12, r: 8.5, fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-dasharray": "3 4" }]],
};

/* tiny DOM builders: text only through textContent, never markup */
function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v === true ? "" : String(v));
  }
  n.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return n;
}
function s(tag, attrs, ...kids) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) n.setAttribute(k, String(v));
  n.append(...kids.flat().filter(Boolean));
  return n;
}
function icon(name) {
  const svg = s("svg", { class: "dial-icon", viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" });
  for (const [tag, attrs] of ICONS[name] || ICONS["i-pending"]) svg.append(s(tag, attrs));
  return svg;
}
/* sentence segments [[text, "n"?]]: numbers inline in Archivo tabular figures */
const segs = (list) => list.map(([t, k]) => (k === "n" ? h("span", { class: "dial-n", text: t }) : document.createTextNode(t)));

/* motion: the page's tokens, the pause switch (window.EPI_MOTION = false) and the reader's setting, all read at call time */
const reduce = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
const moving = () => globalThis.EPI_MOTION !== false && !reduce.matches;
const coarse = () => typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches;   // a finger taps, a mouse clicks
const ms = (name) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--" + name)) || 0;

/* one rAF loop for every dial tween (the readouts' roll) */
const tweens = new Set();
let frame = 0;
function loop(now) {
  for (const t of tweens) {
    const k = Math.min(1, (now - t.t0) / t.dur);
    t.step(easeOut(k), k >= 1);
    if (k >= 1) tweens.delete(t);
  }
  frame = tweens.size ? requestAnimationFrame(loop) : 0;
}
function tween(dur, step) {
  const t = { t0: performance.now(), dur: Math.max(1, dur), step };
  tweens.add(t);
  if (!frame) frame = requestAnimationFrame(loop);
  return () => tweens.delete(t);
}

/* the stylesheet travels with the module: linked once, the section draws after it applies (no unstyled frame) */
function styles() {
  if (document.querySelector('link[rel="stylesheet"][href$="css/dial.css"]')) return Promise.resolve();
  const link = h("link", { rel: "stylesheet", href: new URL("../css/dial.css", import.meta.url).href });
  document.head.append(link);
  return new Promise((done) => { link.onload = link.onerror = done; });
}

/* ---- the engraved scale (SVG in CSS pixels, redrawn on resize so every hairline lands on a pixel). Top to bottom: the comb (one
   bar per size, hanging as deep as that size's worst fall, in the tone the server gave the size), the gold floor line across it,
   the ruler (the stretches hatched by status, the ticks), the axis. The gold notch drops through all of it where the floor first
   broke, so the cut and the floor line cross where the bars break through. ---- */
/* the scale sits inside the track by PAD on each side (= --dial-pad in dial.css): the knob, its ring and its focus outline stay inside
   the ruler at 0 % and at the last size, and the track clips the thumb's wide hit area, so nothing ever overflows the page */
const PAD = 16;
const span = (W) => Math.max(1, W - 1 - 2 * PAD);
const xAt = (x, W) => PAD + Math.round(x * span(W));             // a size's centre in px (bars are 2 px, centred on a pixel edge)
function geo(H) {
  const top = 8, body = 16, foot = 24, P = Math.max(32, H - top - 10 - body - foot);
  return { H, top, P, bodyTop: top + P + 10, body, bot: top + P + 10 + body, label: top + P + 10 + body + 17 };
}
const depthOf = (m, dd, P) => (typeof dd === "number" ? Math.min(P, (Math.abs(dd) / m.scale) * P) : 0);

function drawScale(svg, m, W, G, uid) {
  const { H, top, P, bodyTop, body, bot } = G, X = (x) => xAt(x, W), parts = [];
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W);
  svg.setAttribute("height", H);
  const hatch = (tone, angle, gap) => s("pattern", { id: `${uid}-hatch-${tone}`, patternUnits: "userSpaceOnUse", width: gap, height: gap, patternTransform: `rotate(${angle})` },
    s("line", { x1: 0.5, y1: 0, x2: 0.5, y2: gap, class: `dial-hatch-line dial-hatch-${tone}` }));
  parts.push(s("defs", {}, hatch("outside", 45, 6), hatch("caveat", -45, 8)));
  parts.push(s("line", { x1: 0, x2: W, y1: top + 0.5, y2: top + 0.5, class: "dial-zero" }));
  for (const p of m.points) {      // the comb: the worst fall of every size, never compared here (its tone is the server's verdict)
    const d = Math.round(depthOf(m, p.dd, P));
    if (d > 0) parts.push(s("rect", { x: X(p.x) - 1, y: top + 1, width: 2, height: d, class: `dial-bar dial-bar-${p.floorCls || "none"}`, "data-i": p.i }));
  }
  if (m.floorV !== null) {         // the floor as a depth: the same −15 % for every size; it brightens once when the thumb crosses the cut
    const y = Math.round(top + depthOf(m, m.floorV, P)) + 0.5;
    parts.push(s("line", { x1: 0, x2: W, y1: y, y2: y, class: "dial-floor-line" }), s("line", { x1: 0, x2: W, y1: y, y2: y, class: "dial-floor-line dial-floor-flash" }));
    parts.push(s("text", { x: 4, y: y - 6, class: "dial-floor-t" }, document.createTextNode("Your floor")));   // its value is the gold readout
  }
  for (const run of m.runs) {      // the ruler: the server's status per size, as stretches (hatched red outside, amber with caveats)
    if (run.tone !== "outside" && run.tone !== "caveat") continue;
    const x0 = xAt(run.x0, W), x1 = xAt(run.x1, W) + 1;
    parts.push(s("rect", { x: x0, y: bodyTop, width: Math.max(1, x1 - x0), height: body, class: `dial-wash dial-wash-${run.tone}` }),
      s("rect", { x: x0, y: bodyTop, width: Math.max(1, x1 - x0), height: body, fill: `url(#${uid}-hatch-${run.tone})` }));
  }
  for (const mk of m.marks) {
    const x = X(mk.x) + 0.5, len = [4, 6, 9][mk.level];
    parts.push(s("line", { x1: x, x2: x, y1: bot, y2: bot - len, class: `dial-tick dial-tick-${mk.level}` }));
    if (mk.label) parts.push(s("text", { x, y: G.label, "text-anchor": "middle", class: "dial-axis" }, document.createTextNode(mk.label)));
  }
  parts.push(s("line", { x1: 0, x2: W, y1: bot + 0.5, y2: bot + 0.5, class: "dial-base" }));
  if (m.notch) {                   // the engraved cut where the floor first broke in this replay: a gold line and a V, and its bright twin
    const x = xAt(m.notch.x, W) + 0.5;
    const cut = (cls) => s("g", { class: cls }, s("line", { x1: x, x2: x, y1: top - 2, y2: bot + 6 }), s("path", { d: `M${x - 4.5} ${top - 7.5}H${x + 4.5}L${x} ${top - 1.5}Z` }));
    parts.push(cut("dial-notch"), cut("dial-notch dial-notch-flash"));
  }
  svg.replaceChildren(...parts);
}

/* ---- the section's skeleton for one model; refs are the nodes the readouts and the thumb update ---- */
function build(m, kind, uid, store, onOpen) {
  const R = {}, id = (k) => `${uid}-${k}`;
  const cell = (label, value, sub, extra) => h("div", { class: "dial-cell" + (extra ? " " + extra : "") },
    h("dt", { class: "dial-k", text: label }), value, sub);
  R.sentence = h("p", { class: "dial-sentence", id: id("sentence") }, segs(m.sentence));
  R.size = h(kind === "strip" ? "span" : "dd", { class: kind === "strip" ? "dial-num dial-move-size" : "dial-v dial-move-size" });
  R.statusIcon = h("span", { class: "dial-status-icon" });
  R.statusWord = h("span", { class: "dial-status-word" });
  R.status = h(kind === "strip" ? "span" : "dd", { class: "dial-status" }, R.statusIcon, R.statusWord);
  R.caption = h("p", { class: "dial-whatif", text: WHAT_IF });              // R20: under any size the investor did not ask
  R.dd = h("dd", { class: "dial-v" });
  R.dollars = h("dd", { class: "dial-v" });
  R.end = h("dd", { class: "dial-v" });
  if (kind === "full") {           // lane clarity (R22): what each readout is, in plain words (the figure itself is beside it)
    mean(R.dd, "The worst fall: the biggest drop from a high point at this size, in this replay.");
    mean(R.dollars, "The same drop in dollars on your amount, at this size.");
    mean(R.end, "What the money was worth at the end of the replay, at this size.");
  }
  R.todayEnd = h("span", { class: "dial-num" });
  R.todaySub = h("dd", { class: "dial-sub" }, "Today’s mix ", R.todayEnd);
  R.back = h("button", { type: "button", class: "dial-back", text: `Back to the ${m.points[m.asked].weightText} asked` });
  R.stem = h("span", { class: "dial-move-stem" });
  R.line = h("span", { class: "dial-move-line" });
  R.knob = h("span", { class: "dial-move-knob" });
  R.tip = h("span", { class: "dial-move-tip", "aria-hidden": "true" });     // the current bar's own worst fall, at its tip
  R.thumb = h("div", { class: "dial-move", role: "slider", tabindex: 0, "aria-labelledby": id("label"),
    "aria-describedby": kind === "strip" ? id("summary") : `${id("sentence")} ${id("summary")}`, "aria-orientation": "horizontal", "aria-valuemin": 0,
    "aria-valuemax": m.last }, R.line, R.stem, R.tip, R.knob);
  R.svg = s("svg", { class: "dial-scale", "aria-hidden": "true", focusable: "false" });
  R.track = h("div", { class: "dial-track" }, R.svg, R.thumb);
  const at = (i) => ({ style: `--x:${m.points[i].x}`, "data-align": "middle" });
  const edgeAt = (i) => { const x = m.points[i].x; return { style: `--x:${x}`, "data-align": x < 0.25 ? "start" : x > 0.75 ? "end" : "middle" }; };
  R.asked = h("span", { class: "dial-mark dial-mark-move", ...at(m.asked), text: "asked" });
  R.backSlot = h("span", { class: "dial-mark dial-mark-back", ...edgeAt(m.asked) }, R.back);
  const marks = h("div", { class: "dial-marks" }, m.today !== null && m.today !== m.asked ? h("span", { class: "dial-mark", ...at(m.today), text: "today" }) : null,
    R.asked, R.backSlot);
  if (m.notch) {
    const x = m.notch.x;
    R.notchLabel = h("p", { class: "dial-notch-label", "data-align": x < 0.12 ? "start" : x > 0.88 ? "end" : "middle", style: `--x:${x}` },
      h("span", { class: "dial-notch-k", text: "Your floor first broke at" }), " ", h("span", { class: "dial-num", text: m.notch.text }));   // R1: past tense
  }
  if (m.band) {                    // the start-month band: from the earliest to the latest first break, a tick per start's own break
    const b = m.band, right = b.x0 > 0.6;
    R.bandRow = h("div", { class: "dial-band-row", style: `--x0:${b.x0};--x1:${b.x1}` },
      h("p", { class: "dial-band-label", "data-align": right ? "end" : "start" }, "By start month: ",
        h("span", { class: "dial-num", text: b.iLo === b.iHi ? b.loText : `${b.loText} to ${b.hiText}` })),
      h("span", { class: "dial-band-bracket" }));
  }
  const fall = [cell("Worst fall", R.dd, m.floorText ? h("dd", { class: "dial-sub dial-floor" }, "Your floor ", h("span", { class: "dial-num", text: m.floorText })) : null)];
  if (m.hasDollars && m.amountText) fall.push(R.dollarsCell = cell(`The same fall on your ${m.amountText}`, R.dollars,
    m.capText ? h("dd", { class: "dial-sub dial-floor" }, `${m.capWord} `, h("span", { class: "dial-num", text: m.capText })) : null));
  R.endCell = cell("Ended at", R.end, m.today !== null ? R.todaySub : null);
  const summary = h("p", { class: "sr", id: id("summary"), text: m.summary });
  if (kind === "strip") {          // the compact ruler for the stage, under the race chart: the lamp there says the verdict
    R.root = h("div", { class: "dial dial-strip" },
      h("div", { class: "dial-ruler-head" },
        h("div", {}, h("p", { class: "dial-label", id: id("label") }, `Drag to replay another ${m.name} size: `, R.size, " ", R.status), R.caption),
        h("p", { class: "dial-key", "aria-hidden": "true" }, h("span", { class: "dial-key-bar" }), "Each bar: the worst fall at that size")),
      h("div", { class: "dial-ruler-body" }, h("div", { class: "dial-notch-row" }, R.notchLabel || null), R.track, marks), summary);
    return R;
  }
  /* R22: the standalone section is its question and its answer (the drag lives under the race, in the stage); the ruler, the
     readouts and the start-month band fold into "Show the details" */
  const answer = segs(m.sentence).map((n) => (n.nodeType === 1 && n.classList.contains("dial-n")
    ? mean(n, m.notch && n.textContent === m.notch.text ? say("break_size", n.textContent) : say("move_size", n.textContent)) : n));
  const big = m.notch ? h("p", { class: "dial-big" },
    mean(h("span", { class: "dial-big-n", text: m.notch.text }), say("break_size", m.notch.text)),
    h("span", { class: "dial-big-l", text: `${m.name}: the first size that broke your floor, ${m.replay}` })) : null;
  R.root = h("div", { class: "dial frame" },
    head(id("title"), "At what size does it break?", answer),
    big,
    h("p", { class: "dial-fine cl-quiet", text: m.fineprint.join(" ") }),
    details("dial", store, [
      m.bandLine ? h("p", { class: "dial-band-line" }, segs(m.bandLine)) : null,
    h("div", { class: "dial-read" },
      h("dl", { class: "dial-now" },
        cell(m.name, R.size, null, "dial-cell-size"),
        h("div", { class: "dial-cell dial-cell-status" }, h("dt", { class: "sr", text: "At this size" }), R.status,
          h("dd", { class: "dial-qual", text: m.replay }))),
      h("dl", { class: "dial-measures" }, ...fall, R.endCell), R.caption),
    h("div", { class: "dial-ruler" },
      h("div", { class: "dial-ruler-head" }, h("div", {}, h("p", { class: "dial-label", id: id("label"), text: m.label }), h("p", { class: "dial-hint", text: coarse() ? m.hint.replace("click", "tap") : m.hint })),
        h("p", { class: "dial-key", "aria-hidden": "true" }, h("span", { class: "dial-key-bar" }), "Each bar: the worst fall at that size")),
      h("div", { class: "dial-ruler-body" }, R.bandRow || null, h("div", { class: "dial-notch-row" }, R.notchLabel || null), R.track, marks),
      summary)], { label: "Where it breaks: the ruler and the details", onToggle: onOpen }));
  return R;
}

/* ---- mount(el, store): INTERFACES.md "Sections"; re-renders on result, follows weightIndex, resets on replay.
   mountStrip(el, store): the same ruler without the readouts, for a slot under the race chart in the #replay stage (lane U2 may
   host it), so the chart's morph is in view while the thumb moves. Both follow the store, so any number of rulers stay in step. ---- */
export function mount(el, store) { return attach(el, store, "full"); }
export function mountStrip(el, store) { return attach(el, store, "strip"); }
let instances = 0;

async function attach(el, store, kind) {
  await styles();
  const uid = kind === "full" && !document.getElementById("dial-label") ? "dial" : `dial-${kind}-${++instances}`;
  let m = null, R = null, index = null, shown = null, stopRoll = null, drag = null, ro = null, W = 0, G = null, warned = false;
  const clamp = (i) => Math.max(0, Math.min(m.last, i));
  const lerp = (a, b, k) => (typeof a === "number" && typeof b === "number" ? a + (b - a) * k : b);

  function morph(race, i) {        // the chart follows the dial; a chart error never stops the dial
    if (!race || typeof race.setWeight !== "function") return;
    try { race.setWeight(i); } catch (err) { if (!warned) { warned = true; console.warn("dial: race.setWeight failed", err); } }
  }
  function place() {
    if (!R) return;
    const w = Math.round(R.track.clientWidth), hgt = Math.round(R.track.clientHeight);
    if (w && hgt && (w !== W || !G || G.H !== hgt)) {
      W = w; G = geo(hgt);
      drawScale(R.svg, m, W, G, uid);
      R.thumb.style.height = `${G.H}px`;
      R.line.style.cssText = `top:${G.top}px;height:${G.bodyTop - G.top}px`;
      R.stem.style.cssText = `top:${G.top + 1}px;height:${G.P}px`;
      R.knob.style.top = `${G.bodyTop + G.body / 2 - 9}px`;
      fit(R.notchLabel);
    }
    if (!W) return;
    const p = m.points[index], d = depthOf(m, p.dd, G.P);
    R.thumb.style.transform = `translateX(${xAt(p.x, W)}px)`;
    R.stem.style.transform = `scaleY(${(d / G.P).toFixed(4)})`;          // the current size's own bar, in magenta
    R.tip.style.transform = `translateY(${Math.round(G.top + d - 8)}px)`;  // its value rides at the bar's tip
    R.tip.classList.toggle("is-left", p.x > 0.85);
    const floorT = R.svg.querySelector(".dial-floor-t");         // the floor's label moves to the far end while the thumb sits over it
    if (floorT) { const near = xAt(p.x, W) < 112; floorT.setAttribute("x", near ? W - 4 : 4); floorT.setAttribute("text-anchor", near ? "end" : "start"); }
  }
  function fit(label) {             // a floating label stays inside the ruler: centred on its mark unless that would cross an edge
    if (!label) return;
    const x = parseFloat(label.style.getPropertyValue("--x")) || 0, w = label.offsetWidth, room = R.track.clientWidth, c = xAt(x, room);
    label.dataset.align = c - w / 2 < 0 ? "start" : c + w / 2 > room ? "end" : "middle";
  }
  function texts(t) { R.dd.textContent = t.ddText || ""; R.dollars.textContent = t.dollarsText || ""; R.end.textContent = t.endText || ""; }
  function flash(from, to) {       // the floor line brightens once (200 ms) when the thumb crosses it; nothing else celebrates
    el.dispatchEvent(new CustomEvent("dial:cross", { bubbles: true, detail: { from, to } }));   // the chart may brighten its own floor
    for (const f of R.svg.querySelectorAll(".dial-notch-flash, .dial-floor-flash")) {
      f.classList.remove("is-flash");
      f.getBoundingClientRect();
      f.classList.add("is-flash");
    }
  }
  /* draw size i; how: "init" | "store" (no echo) | "drag" | "key" (exact, no motion) | "jump" | "reset" (the figures roll) */
  function show(i, how) {
    const prev = index, out = readout(m, i), target = figuresOf(m, i);
    index = i;
    R.thumb.setAttribute("aria-valuenow", String(i));
    R.thumb.setAttribute("aria-valuetext", out.valuetext);
    R.size.textContent = out.weightText;
    R.tip.textContent = out.ddText || "";
    R.status.dataset.tone = out.tone;
    R.statusIcon.replaceChildren(...(out.icon ? [icon(out.icon)] : []));     // "held above" carries no mark at all (R20)
    R.statusWord.textContent = out.word || "";
    R.root.classList.toggle("is-whatif", !out.isAsked);                    // any other size: the floor's words, no end value
    if (R.dollarsCell) R.dollarsCell.hidden = !out.isAsked;
    R.endCell.hidden = !out.isAsked;
    R.caption.hidden = out.isAsked;
    R.todayEnd.textContent = out.todayEndText || "";
    R.todaySub.classList.toggle("is-quiet", !out.todayEndText);
    R.root.classList.toggle("is-away", !out.isAsked);           // away from the asked size: "asked" becomes the way back
    R.back.tabIndex = out.isAsked ? -1 : 0;
    R.root.dataset.tone = out.tone;
    place();
    if (stopRoll) { stopRoll(); stopRoll = null; }
    if (kind === "full" && (how === "jump" || how === "reset") && prev !== null && prev !== i && moving()) {
      const from = shown || figuresOf(m, prev);
      stopRoll = tween(ms("dur-lamp"), (k, done) => {
        texts(rollTexts(m, from, i, done ? 1 : k));
        shown = done ? target : { dd: lerp(from.dd, target.dd, k), dollars: lerp(from.dollars, target.dollars, k), end: lerp(from.end, target.end, k) };
        if (done) stopRoll = null;
      });
    } else {
      texts(rollTexts(m, null, i, 1));
      shown = target;
    }
    if (prev !== null && (how === "drag" || how === "jump" || how === "reset") && crossed(m, prev, i) && moving()) flash(prev, i);   // never on keys
  }
  function set(i, how) {           // a change the investor made: the store and the chart follow
    i = clamp(i);
    if (i === index) return;
    show(i, how);
    store.set({ weightIndex: how === "reset" ? null : i });
    morph(store.get().race, i);
  }
  function indexAt(clientX) {
    const r = R.track.getBoundingClientRect();
    return nearestIndex(m, (clientX - r.left - PAD) / span(r.width));
  }
  function wire() {
    const t = R.track;
    t.addEventListener("pointerdown", (e) => {
      if (drag || (e.pointerType === "mouse" && e.button !== 0)) return;      // one pointer at a time; the main button only
      drag = { id: e.pointerId, x: e.clientX, live: e.pointerType !== "touch" };   // a touch waits: a vertical swipe still scrolls
      R.root.classList.add("is-pointer");                                           // the focus ring is for keys, not for a hand
      try { t.setPointerCapture(e.pointerId); } catch { /* the pointer is already gone */ }
      R.thumb.focus({ preventScroll: true });
      if (drag.live) {
        R.root.classList.add("is-dragging");
        set(indexAt(e.clientX), e.target.closest(".dial-move") ? "drag" : "jump");
        e.preventDefault();
      }
    });
    t.addEventListener("pointermove", (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (!drag.live) {
        if (Math.abs(e.clientX - drag.x) < 4) return;
        drag.live = true;
        R.root.classList.add("is-dragging");
      }
      set(indexAt(e.clientX), "drag");
    });
    const end = (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (e.type === "pointerup" && !drag.live) set(indexAt(e.clientX), "jump");   // a tap on a touch screen jumps
      drag = null;
      R.root.classList.remove("is-dragging");
    };
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) t.addEventListener(type, end);
    R.thumb.addEventListener("keydown", (e) => {
      R.root.classList.remove("is-pointer");
      const to = keyStep(index, e.key, m.last);
      if (to === null) return;
      e.preventDefault();
      set(to, "key");
    });
    R.back.addEventListener("click", () => set(m.asked, "reset"));
    ro = new ResizeObserver(() => place());
    ro.observe(t);
  }
  function render(result) {
    if (ro) { ro.disconnect(); ro = null; }
    if (stopRoll) { stopRoll(); stopRoll = null; }
    drag = null; W = 0; G = null; shown = null; index = null;
    m = dialModel(result, globalThis.PF);
    el.hidden = !m;                // no size curve (no move, or a stopped run): no dial
    if (!m) { R = null; el.replaceChildren(); return; }
    R = build(m, kind, uid, store, () => requestAnimationFrame(() => place()));
    if (kind === "full") el.setAttribute("aria-labelledby", `${uid}-title`);
    el.replaceChildren(R.root);
    wire();
    show(m.asked, "init");         // a new run starts at the size the investor asked about
    if (store.get().weightIndex !== null && store.get().weightIndex !== undefined) store.set({ weightIndex: null });
  }

  store.on("result", (r) => render(r));
  store.on("weightIndex", (w) => {  // someone else moved the size (the stage's reset): follow without echo or motion
    if (!m) return;
    const i = Number.isInteger(w) ? clamp(w) : m.asked;
    if (i !== index) show(i, "store");
  });
  store.on("replay", () => {        // a replay redraws the chart at the asked size: the dial goes back there too
    if (!m) return;
    if (index !== m.asked) show(m.asked, "store");
    if (store.get().weightIndex !== null && store.get().weightIndex !== undefined) store.set({ weightIndex: null });
  });
  store.on("race", (race) => { if (m && index !== null && index !== m.asked) morph(race, index); });
  render(store.get().result);
}
