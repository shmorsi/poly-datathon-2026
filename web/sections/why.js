/* EPICENTRE lane U6: #why (the explanation, every number a button), the #thread drawer (pull one number's thread through the
   run) and the navigator-off switch. mount(el, store) per INTERFACES.md; every number is a Result key or the debrief's own
   verified text (web/lib/why.js builds the models; this file only draws them). */
import * as W from "../lib/why.js";
import { factMeaning, plain } from "../lib/meaning.js";
import { head as clHead, details, mean, marks } from "./clarity.js";

const SVG = "http://www.w3.org/2000/svg";
/* a motion duration read from the night tokens (web/styles.css), so the script paces nothing on its own */
const ms = (name) => { const v = getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim(), n = parseFloat(v);
  return Number.isFinite(n) ? (v.endsWith("ms") ? n : n * 1000) : 0; };
const motionOn = () => globalThis.EPI_MOTION !== false && !(globalThis.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)
  && !/\b(motion-off|motion-paused)\b/.test(document.documentElement.className) && !(document.body && /\b(motion-paused|is-paused|no-motion)\b/.test(document.body.className));

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
  return el;
}
function icon(id, cls) {
  const s = document.createElementNS(SVG, "svg"), u = document.createElementNS(SVG, "use");
  s.setAttribute("class", cls || "icon"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  u.setAttribute("href", "#" + id); s.append(u);
  return s;
}
function ensureCss() {
  if (document.querySelector('link[href$="css/why.css"]')) return;
  const base = new URL("../css/why.css", import.meta.url).href;
  document.head.append(h("link", { rel: "stylesheet", href: base, "data-u6": "" }));
}

/* the sentence, its numbers as buttons that open the thread. A whole percent prints as the stage prints it ("40 %", not "40.0 %",
   design director item 7): the same value, one format on the page */
const whole = (t) => String(t).replace(/(\d)\.0(?=[\s\u00a0\u202f]?%)/g, "$1");
function sentenceNode(segs, ctx, at) {
  const frag = document.createDocumentFragment();
  for (const s0 of segs) {
    const s = s0.text ? { ...s0, text: whole(s0.text) } : s0;
    if (s.t === "text") { frag.append(s.text); continue; }
    const card = W.factCard(ctx.result, s.id);
    if (!card) { if (s.t === "num") frag.append(s.text); continue; }
    const label = s.t === "num" ? `${s.text}: ${card.label || s.id}. Open where this number came from.` : `${card.label || s.id}. Open where this number came from.`;
    const b = h("button", { type: "button", class: s.t === "num" ? "why-num" : "why-ref", "data-fact": s.id, "data-at": at === undefined ? null : String(at), "aria-label": label,
      "aria-haspopup": "dialog", "aria-controls": "thread" }, s.t === "num" ? s.text : s.id);
    if (s.t === "num") mean(b, factMeaning(ctx.result, s.id, s.text));
    frag.append(s.t === "ref" ? " " : "", b);
  }
  return frag;
}
function sentenceRow(s, ctx, q) {
  return h("li", { class: "why-s", "data-kind": s.kind || "none" },
    h("span", { class: "why-mark", title: s.marker.word }, icon(s.marker.icon, "kind"), h("span", { class: "sr", text: s.marker.word + ": " })),
    h("p", { class: "why-p" }, q ? h("strong", { class: "why-qlabel", text: `${q} ` }) : null, sentenceNode(s.segs, ctx, s.i)));
}
function legend() {
  const item = (id, word) => h("li", {}, icon(id, "kind"), word);
  return h("ul", { class: "why-legend", "aria-label": "What the marks mean" },
    item("m-fact", "fact"), item("m-assumption", "assumption or limit"), item("m-fiction", "scenario or fiction"));
}
function noteNode(note) {
  if (!note) return null;
  return h("div", { class: "why-note", "data-tone": note.tone, role: note.tone === "caveat" ? "note" : null },
    h("p", { class: "why-note-head" }, icon(note.icon), h("strong", { text: note.word }), h("span", { text: note.text })),
    note.items && note.items.length ? h("ul", { class: "why-note-items" }, note.items.map((t) => h("li", { text: t }))) : null);
}
/* the receipt: one line of separate parts divided by hairlines (R16), the guardrail sentence, then "Show every number": each traced
   fact once, written as the page writes it, with its id, a button to its thread */
const cap = (t) => t.charAt(0).toUpperCase() + t.slice(1);
function receiptNode(rc, ctx, ui) {
  if (!rc) return null;
  ui = ui || {};
  const parts = rc.parts.map((p) => h("li", { class: "rc-part" + (p.lead ? " rc-lead" : ""), "data-tone": p.tone || null },
    p.lead ? icon(p.icon) : null,
    p.lead ? h("span", {}, h("span", { class: "rc-n", "data-count": rc.verified, text: String(rc.verified) }), ` of ${rc.total} numbers traced to the data`) : cap(p.text)));
  const box = h("div", { class: "why-rc" }, h("ul", { class: "why-receipt", "aria-label": "The number check" }, parts),
    rc.guardrail && typeof rc.verified === "number" && typeof rc.total === "number"      // the grounding score shows once, in #how
      ? h("p", { class: "why-guard", text: `Every number was checked by code (${rc.verified} of ${rc.total}).` }) : null);
  const list = W.receiptFacts(ctx.result);
  if (!list.length) return box;
  const ol = h("ol", { class: "rc-list", id: "rc-list", hidden: true, "aria-label": "Every number in the explanation, as this page writes it" },
    list.map((x) => h("li", { class: "rc-row", "data-traced": String(x.traced) }, x.id
      ? h("button", { type: "button", class: "rc-num", "data-fact": x.id, "data-at": x.at === null || x.at === undefined ? null : String(x.at),
        "aria-haspopup": "dialog", "aria-controls": "thread", "aria-label": `${x.valueText}, ${x.label || x.id}, ${x.id}. Open where it came from.` },
        mean(h("span", { class: "rc-v tab", text: x.valueText }), x.label ? `${x.valueText}: ${x.label}.` : null, { focus: false }), h("span", { class: "rc-l", text: x.label || "" }), h("span", { class: "rc-id", text: x.id }))
      : h("span", { class: "rc-num" }, h("span", { class: "rc-v tab", text: x.valueText }), h("span", { class: "rc-l", text: "Not traced to a fact" })))));
  const more = h("button", { type: "button", class: "linkbtn rc-more", "aria-expanded": "false", "aria-controls": "rc-list" }, "Show every number");
  const toggle = (open) => {
    ol.hidden = !open;
    more.setAttribute("aria-expanded", String(open));
    more.textContent = open ? "Hide the numbers" : "Show every number";
    if (ui.onNums) ui.onNums(open);
  };
  more.addEventListener("click", () => toggle(ol.hidden));
  box.append(more, ol);
  if (ui.nums) toggle(true);
  return box;
}
function reasonsNode(reasons) {
  if (!reasons.length) return null;
  return h("div", { class: "why-reasons" },
    h("p", { class: "why-by", text: "Written by code from the checks behind the verdict:" }),
    h("ul", { class: "why-list" }, reasons.map((x) => h("li", { class: "why-s why-reason", "data-tone": x.tone },
      h("span", { class: "why-mark" }, icon(x.icon)),
      h("p", { class: "why-p" }, h("span", { class: "why-status", text: x.word }), " ", h("strong", { class: "why-rule", text: `${x.name}. ` }), x.text,
        x.binding ? h("span", { class: "why-binding", text: ` ${x.binding}.` }) : null)))));
}

const BYLINE = {
  bedrock: "Amazon Bedrock wrote this from the run’s facts; code then checked every number against them. Select a number to see where it came from: the step that computed it, the data behind it, and a recompute.",
  code: "No written explanation is shown for this run. Every number on this page still comes from code.",
};

/* R22: "Why this answer?" answered by the explanation's own lead sentence; its three short sentences and, when the run shows
   it, one line on what the AI changed stay in view; the rest (the byline, the marks, the full text, the receipt, the
   navigator switch) folds into "Show the details" */
function renderWhy(root, ctx, ui) {
  ui = ui || {};
  const e = W.explanation(ctx.result), rc = W.receiptLine(ctx.result, ctx.mode);
  root.replaceChildren();
  root.dataset.state = e.state;
  if (e.state === "empty") return { e, rc };                 // no Result yet: nothing to explain, nothing claimed
  const lead = e.lead ? sentenceNode(e.lead.segs, ctx, "v") : null;
  const span = W.replaySpan(ctx.result);
  const body = h("div", { class: "why-body" });
  body.append(h("p", { class: "why-span cl-quiet", text: `${span ? `In this ${span} replay. ` : ""}This already happened; it is not a forecast.` }));
  body.append(h("p", { class: "why-dial", hidden: !ctx.dialNote, text: ctx.dialNote || "" }));
  /* G2: by the workshop's four questions, one sentence each (else the three picked sentences) */
  const four = W.fourQuestions(e, ctx.result);
  const short = four.length ? h("ol", { class: "why-list why-short why-four", "aria-label": "The explanation, by the workshop’s four questions" },
    four.map((x) => sentenceRow(x.s, ctx, x.q)))
    : e.picked.length ? h("ol", { class: "why-list why-short", "aria-label": "The explanation, in short" }, e.picked.map((s) => sentenceRow(s, ctx))) : null;
  if (short) body.append(short, marks());              // red gate 4: the marks' legend, always beside them
  if (ctx.aiLine) body.append(h("p", { class: "why-ai" }, h("span", { class: "why-ai-k" }, "What the AI changed"), h("span", { text: ctx.aiLine }),
    h("a", { class: "linkbtn why-agentlog", href: "#agentlog", "data-agentlog-open": "", text: "Watch the AI work" })));
  const coded = e.by !== "bedrock";                         // no written explanation: the code's own reasons and the note stay in view
  if (coded) body.append(...[noteNode(e.note), reasonsNode(e.reasons)].filter(Boolean));
  const more = [h("p", { class: "why-lede", text: e.by === "bedrock" ? BYLINE.bedrock : BYLINE.code }), e.by === "bedrock" ? legend() : null];
  if (e.groups.length && e.count > e.picked.length + (e.lead ? 1 : 0)) {
    more.push(h("div", { class: "why-all", id: "why-all" }, h("h3", { class: "why-all-t", text: "The full explanation, by its four questions" }),
      e.groups.map((g) => h("section", { class: "why-q", "aria-label": g.title },
        h("h3", { class: "why-q-title", text: g.title }), h("ol", { class: "why-list" }, g.sentences.map((s) => sentenceRow(s, ctx)))))));
  }
  more.push(coded ? null : noteNode(e.note), coded ? null : reasonsNode(e.reasons), receiptNode(rc, ctx, ui), ctx.nav || null,
    h("p", { class: "why-code" }, icon("m-fact", "kind"), "Every number comes from code."));
  const P = globalThis.PF, vw = P && P.VERDICT && ctx.result ? P.VERDICT[ctx.result.verdict] : null;
  const question = vw && vw.word ? `Why ${vw.word.charAt(0).toLowerCase()}${vw.word.slice(1)}?` : "Why this answer?";
  const proof = rc && typeof rc.verified === "number" && typeof rc.total === "number" ? h("aside", { class: "why-proof", "aria-label": "The number check" },
    h("p", { class: "why-big" }, mean(h("span", { class: "why-big-n" }, `${rc.verified} of ${rc.total}`), `${rc.verified} of ${rc.total}: the numbers in the explanation that code matched to the data, out of all of them.`)),
    h("p", { class: "why-big-cap" }, "numbers checked by code"),
    h("p", { class: "why-big-by" }, [e.by === "bedrock" ? "Read by Claude on Amazon Bedrock" : "Written by code", rc.guardrail ? ", Guardrails on." : "."].join(""))) : null;
  root.append(...[clHead("why-title", question, lead ? h("span", { class: "why-lead" }, lead) : (coded ? BYLINE.code : null)), body, proof,
    details("why", ctx.store, more.filter(Boolean), { label: "Why this answer: the details" })].filter(Boolean));   // append(null) writes "null"
  return { e, rc };
}

/* the receipt counter: 0 → n in ≤ 600 ms, landing on the exact value (motion only; the still state is the end state) */
function countUp(root) {
  const n = root.querySelector(".rc-n");
  if (!n || !motionOn()) return;
  const end = Number(n.dataset.count), t0 = performance.now(), dur = ms("dur-lamp") * 1.5;   // ≤ 600 ms, landing on the exact value
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  const step = (now) => {
    const t = Math.min(1, (now - t0) / dur);
    n.textContent = String(t >= 1 ? end : Math.round(end * ease(t)));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ---- the #thread drawer ---- */
const periodText = (p) => String(p || "").replace(/^YTD\b/, "Year to date").replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (d) => globalThis.PF.fmt.date(d) || d);
function recNote(r, rows) {
  const m = W.reconciliationOf(r), read = rows.find((x) => x.readOn);
  const bits = [read ? `The issuers’ pages were read on ${read.readOn}.` : null,
    m.n !== null && m.within !== null && m.tolerance !== null ? `${m.within} of ${m.n} published figures in this check are within ${m.tolerance.toFixed(2)}\u00a0pp of ours.` : null].filter(Boolean);
  return bits.length ? h("p", { class: "th-small", text: bits.join(" ") }) : null;
}
const dl = (pairs) => h("dl", { class: "th-dl" }, pairs.filter(([, v]) => v !== null && v !== undefined && v !== "")
  .map(([k, v, cls]) => h("div", {}, h("dt", { text: k }), h("dd", { class: cls || null }, v))));
const MIX_WORD = { after: "After the move", today: "Today’s mix", illustration: "The fictional mix" };
const INPUT_LABEL = { path: "Result key", key: "Key", recipe: "Recipe", formula: "Formula", which: "Mix", ticker: "Ticker", families: "Kinds of shock", draft: "Draft" };
const STEP_WORD = { OBSERVE: "Observe", UNDERSTAND: "Understand", COMPARE: "Compare", EXPLAIN: "Explain", VERIFY: "Verify" };
const plainStep = (s) => (s ? STEP_WORD[s] || s : null);
/* R15: a saved run's request ids are labelled with when it was recorded, never shown as if live */
const savedWhen = (ctx) => { const s = W.recordedOn(ctx.result, ctx.mode); return s.saved ? (s.date ? `On ${s.date}, in this saved run` : "In this saved run") : null; };
const msText = (ms) => (ms === null ? null : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);

/* data.recompute (U0): live POST /api/recompute, or in static mode the build-time check the Result carries ({match: null} without one) */
async function recomputeVia(ctx, id) {
  let data = null;
  try { data = await import("../data.js"); } catch { return { match: null, static: true }; }
  try { return await data.recompute(ctx.investor, ctx.result, id); }
  catch (e) { return { error: (e && e.message) || "The server could not recompute this number. Try again." }; }
}

function threadBody(ctx, id, onRecompute, at) {
  const r = ctx.result, card = W.factCard(r, id);
  if (!card) return null;
  const cited = W.citedIn(r, id, at), tr = W.traceOf(r, id), ev = W.evidenceOf(r, id), rec = W.reconciliationFor(r, id);
  const e = W.explanation(r), wr = e.writer;
  const node = (title, ...kids) => h("li", { class: "th-node" }, h("h3", { class: "th-h", text: title }), ...kids);
  const chain = h("ol", { class: "th-chain" });
  if (cited) chain.append(node("In the explanation",
    h("blockquote", { class: "th-quote" }, cited.segs.map((s) => (s.t === "text" ? s.text : s.t === "num"
      ? h("mark", { class: s.ids.includes(id) ? "th-hit" : null, text: s.text }) : ""))),
    wr ? dl([["Written by", wr.service || "Amazon Bedrock"], ["Model", wr.model, "th-id"], ["Draft", wr.drafts > 1 ? `${wr.drafts} of ${wr.drafts} (rewritten once)` : "1 of 1"],
      ["Time", msText(wr.ms)], ["Request ID", wr.requestId, "th-id"], ["Recorded", savedWhen(ctx)]]) : null,
    h("p", { class: "th-small", text: "The model chose the words; code checked that this number equals the fact it cites." })));
  if (tr) {
    const c = tr.computed, rec = tr.recorded, rc = W.recipeOf(r, id);
    const extra = (c ? c.inputs : []).filter(([k]) => k === "which" || k === "ticker").map(([k, v]) => [INPUT_LABEL[k] || k, k === "which" ? MIX_WORD[v] || v : v, k === "which" ? null : "th-code"]);
    chain.append(node(rc.title,
      dl([["Tool", (c || rec).tool, "th-code"], ...extra, ["Step", plainStep((c || rec).step)], ["Service", (c || rec).service], ["Model", c && c.model, "th-id"],
        ["Time", c && c.ms ? msText(c.ms) : null], ["Request ID", c && c.requestId, "th-id"], ["Recorded", c && c.requestId ? savedWhen(ctx) : null],
        ...rec.inputs.filter(([k]) => k !== "which" && k !== "recipe").map(([k, v]) => [INPUT_LABEL[k] || k, v, "th-code"]), ["Raw value", rec.value, "num"]]),
      rc.how ? h("p", { class: "th-small", text: rc.how }) : null,
      (c && c.source) || rec.source ? h("p", { class: "th-small th-source", text: (c && c.source) || rec.source }) : null));
  }
  if (ev) chain.append(node("The data behind it", ev.rows.length
    ? h("table", { class: "th-rows" }, h("thead", {}, h("tr", {}, ["Date", "Series", "Value"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, ev.rows.map((x) => h("tr", {}, h("td", { class: "tab", text: x.date || "" }), h("td", {}, h("span", { class: "th-ser", text: x.ticker || x.file || "" }), x.ticker && x.file ? h("span", { class: "th-file", text: x.file }) : null), h("td", { class: "tab", text: x.value || "" })))))
    : h("p", { class: "th-small", text: ev.note }),
    ev.rows.length ? h("p", { class: "th-small", text: ev.from === "series"
      ? "The mix’s value on the days this number is about, read from this run’s own replay (base 100). The licensed price rows are left out of the public demo. This already happened; it is not a forecast."
      : "Read from the run’s own series and files, dated on or before the decision date. This already happened; it is not a forecast." }) : null));
  if (rec.length) chain.append(node("Checked against the outside world",
    h("table", { class: "th-rows th-recs" },
      h("thead", {}, h("tr", {}, ["Fund and window", "Ours", "Published", "Gap"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, rec.map((x) => h("tr", {},
        h("td", {}, h("span", { class: "th-rec-name", text: x.name }), h("span", { class: "th-rec-win", text: periodText(x.period) }),
          x.url ? h("a", { class: "th-rec-src", href: x.url, target: "_blank", rel: "noopener noreferrer", text: x.host || "Source" }) : null),
        h("td", { class: "tab", text: x.ours }), h("td", { class: "tab", text: x.published }), h("td", { class: "tab th-gap", text: x.gap || "" }))))),
    recNote(ctx.result, rec),
    h("p", { class: "th-small", text: "Our total return for each fund in this mix against the figure its issuer publishes, over the issuer’s own window." })));
  const out = h("p", { class: "th-out", role: "status", "aria-live": "polite" });
  const btn = h("button", { type: "button", class: "btn btn-quiet th-btn" }, icon("i-spin", "icon th-spin"), h("span", { text: "Recompute this number" }));
  btn.addEventListener("click", () => onRecompute(btn, out));
  chain.append(h("li", { class: "th-node th-act" }, h("h3", { class: "th-h", text: "Run it again" }), btn, out));
  return h("div", { class: "th-body" },
    h("p", { class: "th-kind" }, icon(card.marker.icon, "kind"), h("span", { text: card.marker.word }), h("span", { class: "th-fid num", text: card.id })),
    h("h2", { class: "th-label", id: "thread-title", text: card.label || card.id }),
    h("p", { class: "th-value num", text: card.valueText || card.raw || "" }),
    card.entityText ? h("p", { class: "th-entity", text: `About ${card.entityText}` }) : null,
    W.setBy(r, id) ? h("p", { class: "th-setby", text: W.setBy(r, id) }) : null,
    chain);
}

function createThread(store, getCtx, scope) {
  let root = document.getElementById("thread");
  if (!root) { root = h("div", { id: "thread" }); document.body.append(root); }
  root.classList.add("thread-root");
  root.hidden = true;
  const scrim = h("div", { class: "th-scrim", "aria-hidden": "true" });
  const close = h("button", { type: "button", class: "th-x", "aria-label": "Close" }, h("span", { "aria-hidden": "true", text: "×" }));
  const scroll = h("div", { class: "th-scroll" });
  const panel = h("div", { class: "th-panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "thread-title", tabindex: "-1" },
    h("div", { class: "th-top" }, h("p", { class: "th-top-t", text: "Where this number came from" }), close), scroll);
  /* the tether: the pulled number stays lit above the scrim, joined to the panel by one hairline (desktop drawer only) */
  const link = document.createElementNS(SVG, "svg"), path = document.createElementNS(SVG, "path"), knot = document.createElementNS(SVG, "circle");
  link.setAttribute("class", "th-link"); link.setAttribute("aria-hidden", "true"); link.setAttribute("focusable", "false");
  knot.setAttribute("r", "2.5");
  link.append(path, knot);
  const ghost = h("span", { class: "th-ghost", "aria-hidden": "true" });
  root.replaceChildren(scrim, link, ghost, panel);
  let trigger = null, shownId = null, hideT = 0;
  const untether = () => { link.style.display = "none"; ghost.style.display = "none"; };
  function tether(btn) {
    const r = btn && btn.isConnected && btn.closest("#why") ? btn.getBoundingClientRect() : null;
    const value = scroll.querySelector(".th-value");
    if (!r || !r.width || !value || matchMedia("(max-width: 760px)").matches) { untether(); return; }
    const x1 = r.right + 5, y1 = r.top + r.height / 2, x2 = innerWidth - panel.offsetWidth - 1;
    const v = value.getBoundingClientRect(), y2 = v.top + v.height / 2;
    if (x2 - x1 < 40) { untether(); return; }
    const top = Math.min(y1, y2) - 4, w = x2 - x1, hgt = Math.abs(y2 - y1) + 8, a1 = y1 - top, a2 = y2 - top;
    Object.assign(link.style, { display: "block", left: `${x1}px`, top: `${top}px`, width: `${w}px`, height: `${hgt}px` });
    link.setAttribute("viewBox", `0 0 ${w} ${hgt}`);
    path.setAttribute("d", `M 0 ${a1} C ${w * 0.55} ${a1}, ${w * 0.45} ${a2}, ${w} ${a2}`);
    knot.setAttribute("cx", "0"); knot.setAttribute("cy", String(a1));
    const cs = getComputedStyle(btn), copy = btn.cloneNode(true);
    copy.removeAttribute("data-fact"); copy.removeAttribute("aria-label"); copy.setAttribute("tabindex", "-1"); copy.classList.add("is-on");
    ghost.replaceChildren(copy);
    Object.assign(ghost.style, { display: "block", left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`,
      font: cs.font, letterSpacing: cs.letterSpacing });
  }
  addEventListener("resize", () => { if (shownId !== null) tether(trigger); });
  const shut = () => store.set({ thread: null });
  close.addEventListener("click", shut);
  scrim.addEventListener("click", shut);
  scrim.addEventListener("wheel", (ev) => ev.preventDefault(), { passive: false });
  root.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { ev.preventDefault(); shut(); return; }
    if (ev.key !== "Tab") return;
    const f = [...panel.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && (document.activeElement === first || document.activeElement === panel)) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });
  const onRecompute = async (btn, out) => {
    const ctx = getCtx(), id = shownId;
    const show = (ans) => {
      const l = W.recomputeLine(ans, { recorded: W.recordedOn(ctx.result, ctx.mode).date });
      out.replaceChildren();
      if (!l) return;
      out.dataset.tone = l.tone;
      out.append(h("span", { class: "th-out-word" }, l.state === "pending" ? null : icon(l.icon), l.word + (l.state === "match" ? " ✓" : "")),
        l.detail ? h("span", { class: "th-out-d num", text: l.detail }) : null, l.label ? h("span", { class: "th-out-l", text: l.label }) : null);
    };
    btn.disabled = true; btn.classList.add("is-busy"); show("pending");
    const ans = await recomputeVia(ctx, id);
    if (shownId !== id) return;
    btn.disabled = false; btn.classList.remove("is-busy"); show(ans);
  };
  function open(id) {
    const body = threadBody(getCtx(), id, onRecompute, getCtx().at);
    if (!body) { shut(); return; }
    clearTimeout(hideT);
    if (shownId === null && !trigger) trigger = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
    shownId = id;
    scroll.replaceChildren(body);
    scroll.scrollTop = 0;
    root.dataset.motion = motionOn() ? "on" : "off";
    root.hidden = false;
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add("is-open")));
    panel.focus({ preventScroll: true });
    scope.querySelectorAll("[data-fact].is-on").forEach((b) => b.classList.remove("is-on"));
    scope.querySelectorAll(`[data-fact="${CSS.escape(id)}"]`).forEach((b) => b.classList.add("is-on"));
    tether(trigger && trigger.dataset && trigger.dataset.fact === id ? trigger : null);
  }
  function hide() {
    if (shownId === null) return;
    shownId = null;
    root.classList.remove("is-open");
    scope.querySelectorAll("[data-fact].is-on").forEach((b) => b.classList.remove("is-on"));
    const done = () => { if (shownId === null) { root.hidden = true; scroll.replaceChildren(); untether(); } };
    if (root.dataset.motion === "on") hideT = setTimeout(done, ms("dur-panel-exit") + 20); else done();
    if (trigger && trigger.isConnected) trigger.focus({ preventScroll: true });
    trigger = null;
  }
  /* from(btn): the number the reader pulled (a click does not focus a button in every browser, so the trigger is handed over) */
  return { sync: (id) => (id ? open(id) : hide()), from: (btn) => { trigger = btn || null; }, get id() { return shownId; } };
}

/* ---- the navigator-off switch ---- */
function cellText(row, side, cls) {
  const v = row[side];
  const l = side === "navigator" ? "The AI reader" : "Keyword rules only";
  if (row.what !== "precedents") return h("td", { class: cls || null, "data-l": l, text: v });
  const only = side === "navigator" ? row.onlyNavigator : row.onlyKeywords;
  if (!v.length) return h("td", { class: cls || null, "data-l": l, text: "None named" });
  return h("td", { class: cls || null, "data-l": l }, h("ul", { class: "nav-eps" }, v.map((x) => h("li", { class: only.some((o) => o.id === x.id) ? "is-only" : null },
    h("span", { text: x.title }), x.date ? h("span", { class: "nav-ep-d tab", text: ` ${x.date}` }) : null))));
}
function navNode(p, ui, off) {
  if (!p) return null;
  ui = ui || {};
  const sw = h("button", { type: "button", class: "nav-switch", role: "switch", "aria-checked": "true", "aria-controls": "nav-cmp", "aria-label": "The AI reader" },
    h("span", { class: "nav-track", "aria-hidden": "true" }, h("span", { class: "nav-thumb" })),
    h("span", { class: "nav-sw-l", "aria-hidden": "true" }, "The AI reader is ", h("strong", { class: "nav-sw-s", text: "on" })));
  const table = h("table", { class: "nav-cmp", id: "nav-cmp" },
    h("caption", { class: "sr", text: "The AI reader’s reading of your question next to the keyword rules’ reading" }),
    h("thead", {}, h("tr", {}, h("th", { scope: "col", class: "sr-col" }, h("span", { class: "sr", text: "What was read" })),
      h("th", { scope: "col", text: "The AI reader (Claude on Amazon Bedrock)" }), h("th", { scope: "col", class: "nav-kw", text: "Keyword rules only (no AI)" }),
      h("th", { scope: "col", class: "nav-kw nav-st-h" }, h("span", { class: "sr", text: "Changed?" })))),
    h("tbody", {}, p.rows.map((r) => h("tr", { "data-same": String(r.same === null ? "unknown" : r.same) }, h("th", { scope: "row", text: r.label }), cellText(r, "navigator"),
      cellText(r, "keywords", "nav-kw"),
      h("td", { class: "nav-kw nav-st" }, h("span", { class: "nav-st-in" }, icon(r.same === null ? "i-pending" : r.same ? "i-in" : "i-warn"),
        r.same === null ? "Not known" : r.same ? "Same" : "Changed"))))));
  const sum = off || p.summary ? h("p", { class: "nav-sum nav-kw-b", text: off ? `${off} ${plain(p.summary || "")}`.trim() : plain(p.summary) }) : null;
  const x = p.example;
  const ex = x ? h("div", { class: "nav-ex nav-kw-b" },
    h("p", { class: "nav-ex-h" }, h("strong", { text: "Where the keyword rules read the wrong shock" }),
      h("span", { text: ` A question from ${x.source}${x.lang === "fr" ? ", asked in French" : ""}, not this run.` })),
    h("blockquote", { class: "nav-ex-q", lang: x.lang === "fr" ? "fr" : null, text: `“${x.question}”` }),
    x.english ? h("p", { class: "nav-ex-en", text: `In English: “${x.english}”` }) : null,
    h("p", { class: "nav-ex-r" }, h("span", {}, "The keyword rules read ", h("strong", { text: x.keywordsPhrase || "no shock" }), "."),
      h("span", {}, " The AI reader read ", h("strong", { text: x.navigatorPhrase }), x.expected && x.expected === x.navigator ? ", the labelled answer." : "."))) : null;
  const box = h("section", { class: "nav-off", "data-off": "false", "aria-labelledby": "nav-off-t" },
    h("div", { class: "nav-head" }, h("h3", { class: "nav-t", id: "nav-off-t", text: "What the AI reader changed in this run" }),
      h("p", { class: "nav-d", text: "The AI reader (Claude on Amazon Bedrock) reads your question. This run also recorded what fixed keyword rules read from the same words. Switch the AI reader off to see them side by side." }), sw),
    h("div", { class: "nav-main" }, table, p.countLine ? h("p", { class: "nav-count", text: p.countLine }) : null,
      h("p", { class: "nav-hint", text: "Switch the AI reader off to see the keyword rules’ reading beside it." }), sum, ex));
  const set = (off) => {
    box.dataset.off = String(off);
    sw.setAttribute("aria-checked", String(!off));
    sw.querySelector(".nav-sw-s").textContent = off ? "off" : "on";
  };
  sw.addEventListener("click", () => { const off = box.dataset.off !== "true"; set(off); if (ui.onToggle) ui.onToggle(off); });
  if (ui.off) set(true);
  return box;
}

/* the held-out evaluation's examples (R8/R10): docs/eval_results.json as the page can reach it; none found = no example */
let evalDoc;
async function loadEval() {
  if (evalDoc !== undefined) return evalDoc;
  evalDoc = null;
  try {                                   // U0 publishes web/eval_results.json (a copy of docs/eval_results.json; the static build too)
    const res = await fetch(new URL("../eval_results.json", import.meta.url), { cache: "force-cache" });
    if (res.ok) { const j = await res.json(); if (j && j.examples) evalDoc = j; }
  } catch { /* no eval file on this host: no example */ }
  return evalDoc;
}

/* the dial moved off the asked size: say which size the explanation describes (it is about the asked one) */
function dialNote(st) {
  const r = st.result, i = st.weightIndex, tp = r && r.tipping_point, P = globalThis.PF;
  const curve = tp && Array.isArray(tp.curve) ? tp.curve : null;
  if (i === null || i === undefined || !curve || !curve[i] || !P || !P.moveOf) return null;
  const mv = P.moveOf(r);
  if (!mv || Math.abs(curve[i].weight - mv.weight) < 1e-9) return null;
  return `This explanation is about the size asked, ${mv.name} at ${P.fmt.share(mv.weight)}. The dial now shows ${P.fmt.share(curve[i].weight)}.`;
}

export function mount(el, store) {
  ensureCss();
  el.classList.add("why");
  if (!el.getAttribute("aria-labelledby")) el.setAttribute("aria-labelledby", "why-title");
  const frame = h("div", { class: "frame why-grid" });
  const textRoot = h("div", { class: "why-text" });
  frame.append(textRoot);
  el.replaceChildren(frame);
  let at = null;                       // the sentence the reader pulled the number from (the drawer quotes that one)
  const ctxOf = () => { const st = store.get() || {}; return { result: st.result || null, mode: st.mode || "static", investor: st.investor || (st.result && st.result.pilot) || null, at }; };
  const thread = createThread(store, ctxOf, el);
  let lastResult = null, seen = false;
  const ui = { off: false, more: false, nums: false, onToggle: (off) => { ui.off = off; }, onMore: (open) => { ui.more = open; },
    onNums: (open) => { ui.nums = open; } };
  const draw = () => {
    const st = store.get() || {}, base = ctxOf();
    const p = W.navigatorPanel(base.result, evalDoc);
    const off = W.aiOffLine(base.result);                      // R37: the honest value first, else what the reading changed
    const ctx = { ...base, dialNote: dialNote(st), store, nav: navNode(p, ui, off), aiLine: off || W.aiValueLine(base.result, evalDoc) };
    el.hidden = false;
    el.dataset.motion = motionOn() ? "on" : "off";
    renderWhy(textRoot, ctx, ui);
    if (seen) countUp(textRoot);
  };
  textRoot.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-fact]");
    if (!b) return;
    at = b.dataset.at === undefined ? null : b.dataset.at;
    thread.from(b);
    if (store.get().thread === b.dataset.fact) thread.sync(b.dataset.fact);
    store.set({ thread: b.dataset.fact });
  });
  store.on("result", (r) => {
    if (r === lastResult) return;
    lastResult = r;
    ui.off = false; ui.more = false; ui.nums = false;   // a new run starts with the navigator on, the short text, the numbers folded
    if (store.get().thread) store.set({ thread: null });
    draw();
  });
  store.on("mode", draw);
  store.on("weightIndex", () => {
    const slot = textRoot.querySelector(".why-dial"), note = dialNote(store.get() || {});
    if (slot) { slot.textContent = note || ""; slot.hidden = !note; }
  });
  store.on("thread", (id) => { thread.sync(id || null); if (!id) at = null; });
  lastResult = (store.get() || {}).result || null;
  draw();
  if ((store.get() || {}).thread) thread.sync(store.get().thread);
  loadEval().then((doc) => { if (doc) draw(); });
  if ("IntersectionObserver" in globalThis) {
    const io = new IntersectionObserver((es) => { if (es.some((x) => x.isIntersecting) && !seen) { seen = true; countUp(textRoot); io.disconnect(); } }, { threshold: 0.35 });
    io.observe(el);
  } else seen = true;
}
