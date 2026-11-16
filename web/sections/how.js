/* EPICENTRE Replay, lane U7: #how, "How it works" (design doc §2 item 8; R12, R15, R10). One diagram of THIS run (the Result
   on the store): question, input guardrail, navigator, code computes, checks, explanation, receipt, output guardrail, you;
   each station carries the trace's own ms, tokens, model and request id. Then the AWS services, one job each; the eval card
   (web/eval_results.json, the blind held-out set first, the development set labelled as such); and the reconciliation rows
   (result.reconciliation). The strip is one SVG drawn in percentages, so it needs no measuring; the words under it are HTML.
   A saved run says "Recorded on <date>" (R15). DOM from createElement/textContent (R16). Motion: one reveal of the line,
   behind window.EPI_MOTION and prefers-reduced-motion. */
import * as H from "../lib/how.js";
import { peekRun } from "../data.js";
import { shownStatus } from "../lib/money.js";             // lane U5b's own words for a check: the strip and the checklist agree
import { countFigures, say } from "../lib/meaning.js";
import { head, details, mean, figs, term } from "./clarity.js";

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
const TONE = { inside: "tone-in", caveat: "tone-caution", outside: "tone-out" };
const TONE_ICON = { inside: "i-in", caveat: "i-warn", outside: "i-out" };
const pc = (x) => `${(x * 100).toFixed(3)}%`;

/* one station's glyph, centred on (x %, y px): ring = you, diamond = Bedrock Guardrails, disc = Amazon Bedrock, square = code */
function glyph(kind, x, y) {
  const g = (H.KINDS[kind] || H.KINDS.code).glyph;
  return h("svg:use", { href: `#flow-${g}`, x, y, class: `flow-g flow-g-${g}` });
}
function defs() {
  return h("svg:defs", {},
    h("svg:g", { id: "flow-ring" }, h("svg:circle", { r: "6", fill: "var(--sky)", stroke: "var(--ink-2)", "stroke-width": "1.5" })),
    h("svg:g", { id: "flow-diamond" }, h("svg:path", { d: "M0 -7.5 7.5 0 0 7.5 -7.5 0Z", fill: "var(--sky)", stroke: "var(--starlight)", "stroke-width": "1.5" })),
    h("svg:g", { id: "flow-disc" }, h("svg:circle", { r: "10", fill: "var(--sky)" }), h("svg:circle", { r: "6.5", fill: "var(--starlight)" }),
      h("svg:circle", { r: "10", fill: "none", stroke: "var(--starlight)", "stroke-opacity": ".35", "stroke-width": "1" })),
    h("svg:g", { id: "flow-square" }, h("svg:rect", { x: "-5", y: "-5", width: "10", height: "10", rx: "1.5", fill: "var(--ink-2)" })),
    h("svg:path", { id: "flow-chev", d: "M-2.5 -3.5 1 0 -2.5 3.5", fill: "none", stroke: "var(--edge)", "stroke-width": "1.25",
      "stroke-linecap": "round", "stroke-linejoin": "round" }));
}

/* the strip: the five steps as dimension lines, then the line through the nine stations */
function strip(flow) {
  const n = flow.nodes.length, col = 1 / n, cx = (i) => (i + 0.5) * col, Y = 58;
  const svg = h("svg:svg", { class: "flow-strip", width: "100%", height: "76", "aria-hidden": "true", focusable: "false" });
  for (const s of H.STEPS) {
    const idx = flow.nodes.map((nd, i) => (nd.step === s.id ? i : -1)).filter((i) => i >= 0);
    if (!idx.length) continue;
    const a = idx[0] * col, b = (idx[idx.length - 1] + 1) * col, inset = 0.006, ours = s.ours ? " is-ours" : "";
    svg.append(h("svg:line", { x1: pc(a + inset), x2: pc(b - inset), y1: "22", y2: "22", class: `flow-band${ours}` }),
      h("svg:line", { x1: pc(a + inset), x2: pc(a + inset), y1: "18", y2: "26", class: `flow-band${ours}` }),
      h("svg:line", { x1: pc(b - inset), x2: pc(b - inset), y1: "18", y2: "26", class: `flow-band${ours}` }),
      h("svg:text", { x: pc(a + inset), y: "12", class: `flow-step${ours}`, text: s.label }));
  }
  svg.append(h("svg:line", { x1: pc(cx(0)), x2: pc(cx(n - 1)), y1: String(Y), y2: String(Y), class: "flow-rail" }));
  for (let i = 0; i < n - 1; i += 1) {          // a chevron halfway between two stations: the direction of the run
    svg.append(h("svg:use", { href: "#flow-chev", x: pc(cx(i) + col / 2), y: String(Y), class: "flow-chev" }));
  }
  flow.nodes.forEach((nd, i) => { const g = glyph(nd.kind, pc(cx(i)), String(Y)); if (nd.notRun) g.classList.add("is-off"); svg.append(g); });
  return svg;
}

/* the words under one station: name, who ran it, what happened, then the trace's own numbers */
function station(nd, i, all) {
  const k = H.KINDS[nd.kind] || H.KINDS.code;
  const step = H.STEPS.find((x) => x.id === nd.step);
  const stepStart = step && (i === 0 || all[i - 1].step !== nd.step) ? step : null;         // phones: the step names the group
  const read = nd.id === "navigator" && nd.lines.length;
  const link = H.STATION_LINKS[nd.id], target = link && typeof document !== "undefined" ? document.getElementById(link[0]) : null;
  const linked = target && !["missing", "failed"].includes(target.dataset.mount) && !nd.notRun;
  const lines = [
    linked ? h("p", { class: "stn-name" }, h("a", { class: "stn-link", href: `#${link[0]}`, title: `Go to ${link[1]}`, text: nd.name }))
      : h("p", { class: "stn-name", text: nd.name }),
    nd.kind !== "you" ? h("p", { class: "stn-kind", text: k.label }) : null,
    nd.model ? h("p", { class: "stn-model", text: nd.model }) : null,
    nd.outcome ? h("p", { class: `stn-out ${TONE[nd.tone] || ""}` }, nd.tone ? icon(nd.icon || TONE_ICON[nd.tone], "icon stn-icon") : null, h("span", { text: nd.outcome })) : null,
    ...(read ? nd.lines.map((t, j) => h("p", { class: `${j === 0 ? "stn-read stn-shock" : "stn-read stn-move"}${countFigures(t) ? " stn-more" : ""}`, text: t }))
      : nd.lines.map((t) => h("p", { class: `stn-line${countFigures(t) ? " stn-more" : ""}`, text: t }))),
  ];
  const nums = [
    H.msText(nd.ms) ? h("p", { class: "stn-num" }, mean(h("span", { class: "inst", text: H.msText(nd.ms) }), say("ms", H.msText(nd.ms), `in this run: ${nd.name}`))) : null,
    nd.tokens ? h("p", { class: "stn-num" },
      mean(h("span", { class: "inst", text: H.count(nd.tokens.total) }), say("tokens", `${H.count(nd.tokens.total)} tokens`,
        nd.tokens.cached ? `${H.count(nd.tokens.input)} in, ${H.count(nd.tokens.output)} out, ${H.count(nd.tokens.cached)} from the prompt cache` : null)), " tokens") : null,
    nd.requestId ? h("p", { class: "stn-req", title: `AWS request id ${nd.requestId}` }, "Request ", h("span", { class: "inst", text: H.shortId(nd.requestId) })) : null,
    nd.grounding ? h("p", { class: "stn-ground" }, "Output grounding ", h("span", { class: "inst", text: nd.grounding.score.toFixed(2) }),
      nd.grounding.threshold !== null ? [" (threshold ", h("span", { class: "inst", text: nd.grounding.threshold.toFixed(2) }), ")"] : null,
      h("span", { class: "stn-adv" }, h("span", { class: "stn-adv-sep", text: ": " }), "advisory, not a gate; the number check is the gate.")) : null,
  ].filter(Boolean);
  return h("li", { class: `stn stn-${nd.kind}${nd.notRun ? " is-off" : ""}`, "data-node": nd.id, style: `--i:${i}` },
    h("svg:svg", { class: "stn-glyph", viewBox: "-11 -11 22 22", "aria-hidden": "true", focusable: "false" }, h("svg:use", { href: `#flow-${k.glyph}` })),
    h("div", { class: "stn-words" }, stepStart ? h("p", { class: `stn-step${stepStart.ours ? " is-ours" : ""}`, text: stepStart.label }) : null, lines, nums.length ? h("div", { class: "stn-nums" }, nums) : null));
}

function legend() {
  return h("ul", { class: "flow-legend", "aria-label": "Who does each step" },
    ...["model", "guard", "code", "you"].map((kind) => h("li", {},
      h("svg:svg", { class: "lg-glyph", viewBox: "-11 -11 22 22", "aria-hidden": "true", focusable: "false" }, h("svg:use", { href: `#flow-${H.KINDS[kind].glyph}` })),
      h("span", { text: kind === "you" ? "The investor" : H.KINDS[kind].label }))));
}

function flowFigure(flow) {
  const list = h("ol", { class: "flow-stations", style: `--n:${flow.nodes.length}` }, flow.nodes.map((nd, i, all) => station(nd, i, all)));
  const fig = h("figure", { class: "how-flow", "aria-labelledby": "how-flow-cap" },
    h("p", { class: "flow-method", text: H.METHOD }),
    h("svg:svg", { class: "flow-defs", width: "0", height: "0", "aria-hidden": "true", focusable: "false" }, defs()),
    h("div", { class: "flow-body" }, strip(flow), list),
    h("figcaption", { class: "flow-cap", id: "how-flow-cap" },
      h("div", { class: "flow-claim" },
        h("p", { class: "flow-fine", text: "The investor and the move are a fictional illustration, not a recommendation." })),
      legend()));
  return fig;
}

function services(flow) {
  const all = H.servicesOf(flow);
  const item = (s) => h("li", { class: "aws", "data-service": s.id },
    h("p", { class: "aws-name", text: s.name }), h("p", { class: "aws-job", text: s.job }), s.run ? h("p", { class: "aws-run stn-more", text: s.run }) : null);
  return h("section", { class: "how-aws", "aria-labelledby": "how-aws-t" },
    h("h3", { class: "how-h3", id: "how-aws-t", text: "Amazon Web Services, one job each" }),
    h("div", { class: "aws-groups" }, H.SERVICE_GROUPS.map((g) => h("div", { class: `aws-group aws-group-${g.id}` },
      h("p", { class: "aws-glabel", text: g.label }),
      h("ul", { class: "aws-list", style: `--n:${all.filter((s) => s.group === g.id).length}` }, all.filter((s) => s.group === g.id).map(item))))));
}

/* ---- the eval card: k / N with its Wilson 95 % interval on one 0-100 % scale; the blind set leads ---- */
function armRow(a, lead) {
  return h("li", { class: `ev-arm${lead ? " is-lead" : ""}`, "data-arm": a.id },
    h("p", { class: "ev-who" }, h("span", { class: "ev-name", text: a.label }), h("span", { class: "ev-engine", text: a.engine })),
    h("div", { class: "ev-track", role: "img", "aria-label": `${a.label}: ${a.k} of ${a.n} right, Wilson 95 % interval ${a.interval}` },
      h("svg:svg", { class: "ev-svg", width: "100%", height: "20", "aria-hidden": "true", focusable: "false" },
        h("svg:line", { x1: "0%", x2: "100%", y1: "10", y2: "10", class: "ev-base" }),
        h("svg:line", { x1: pc(a.lo), x2: pc(a.hi), y1: "10", y2: "10", class: "ev-ci" }),
        h("svg:line", { x1: pc(a.lo), x2: pc(a.lo), y1: "5", y2: "15", class: "ev-ci-end" }),
        h("svg:line", { x1: pc(a.hi), x2: pc(a.hi), y1: "5", y2: "15", class: "ev-ci-end" }),
        h("svg:circle", { cx: pc(a.rate), cy: "10", r: "5", class: "ev-dot" }))),
    h("p", { class: "ev-score" }, mean(h("span", { class: "ev-k", text: `${a.k} / ${a.n}` }), say("eval_score", `${a.k} / ${a.n}`), { focus: false }),
      mean(h("span", { class: "ev-ci-text", text: a.interval }), say("wilson", a.interval), { focus: false })));
}
function evalCard(ev) {
  const ho = ev.heldout, dev = ev.development, F = globalThis.PF && globalThis.PF.fmt;
  const when = ho && ho.date && F ? F.date(ho.date) : null;
  const group = (label, arms) => (arms && arms.length ? [h("p", { class: "ev-group", text: label }), h("ul", { class: "ev-arms" }, arms.map((x, i) => armRow(x, i === 0)))] : []);
  return h("section", { class: "how-eval", "aria-labelledby": "how-eval-t" },
    h("h3", { class: "how-h3", id: "how-eval-t", text: "How often the AI reader reads the right shock" }),
    ho ? h("p", { class: "ev-lede", text: `${ho.n} questions written blind and never used for tuning, measured${when ? ` on ${when}` : ""}${ho.firstPass ? " in two passes with no tuning between them" : ""}.` }) : null,
    ...(ho ? group("The shock read right", ho.arms) : []),
    ...(ho ? group("The whole reading right: the shock, its precedents, the move and the kind of question", ho.whole) : []),
    ho ? h("div", { class: "ev-axis", "aria-hidden": "true" }, h("div", { class: "ev-axis-in" }, h("span", { text: "0 %" }), h("span", { text: "50 %" }), h("span", { text: "100 %" }))) : null,
    ho && ho.categories.length ? h("table", { class: "ev-cats" },
      h("caption", { class: "sr", text: "Where the two readers differ most" }),
      h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Kind of question" }), h("th", { scope: "col", text: "AI reader" }), h("th", { scope: "col", text: "Keyword rules" }))),
      h("tbody", {}, ho.categories.map((c) => h("tr", {}, h("th", { scope: "row", text: `${c.label} (${c.n})` }),
        h("td", { text: `${c.navigator} / ${c.n}` }), h("td", { text: `${c.keyword} / ${c.n}` }))))) : null,
    ho && ho.firstPass ? h("p", { class: "ev-dev", text: `The first pass read the shock right in ${ho.firstPass.navigator} / ${ho.n}${ho.firstPass.keyword !== null ? `, the keyword rules in ${ho.firstPass.keyword} / ${ho.n}` : ""}.` }) : null,
    dev && dev.navigator && dev.keyword ? h("p", { class: "ev-dev",
      text: `On the ${dev.n} development questions (not blind: the team wrote them and tuned on them), the AI reader read ${dev.navigator.k} / ${dev.n} right and the keyword rules ${dev.keyword.k} / ${dev.n}.` }) : null,
    h("p", { class: "ev-meta", text: `Each interval is a Wilson 95 % interval.${ev.modelId ? ` Model: ${ev.modelId}.` : ""}` }));
}

/* ---- R12: our returns next to the issuers' published ones ---- */
function reconCard(rc) {
  const what = rc.funds === rc.n ? `${H.count(rc.n)} funds` : `${H.count(rc.funds)} funds over ${H.count(rc.n)} periods`;
  const lede = rc.within !== null && rc.tolerance !== null
    ? `Our returns for ${what}, beside the figures the issuers publish: ${rc.within === rc.n ? `all ${H.count(rc.n)}` : `${H.count(rc.within)} of ${H.count(rc.n)}`} within ${rc.tolerance.toFixed(2)} points.`
    : `Our returns for ${what}, beside the figures the issuers publish.`;
  return h("section", { class: "how-recon", "aria-labelledby": "how-recon-t" },
    h("h3", { class: "how-h3", id: "how-recon-t", text: "Checked against the outside world" }),
    h("p", { class: "recon-lede", text: lede }),
    h("table", { class: "recon-table" },
      h("caption", { class: "sr", text: "Our computed returns beside the issuers\u2019 published returns" }),
      h("thead", {}, h("tr", {}, ...["Fund", "Period", "Ours", "Published", "Gap, points", "Source"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, rc.rows.map((x) => h("tr", { "data-ok": x.ok === null ? null : String(x.ok) },
        h("th", { scope: "row", class: "recon-tk", text: x.ticker }), h("td", { class: "recon-period", text: x.period }),
        mean(h("td", { class: "recon-n", "data-label": "Ours", text: x.ours }), say("reconciled", `${x.ours} ours, ${x.published} published`), { focus: false }),
        mean(h("td", { class: "recon-n", "data-label": "Published", text: x.published }), say("reconciled", `${x.ours} ours, ${x.published} published`), { focus: false }),
        h("td", { class: "recon-n recon-gap", "data-label": "Gap", text: x.gap || "" }),
        h("td", { class: "recon-src" }, x.url ? h("a", { href: x.url, rel: "noopener noreferrer", target: "_blank", text: x.host || "Issuer page" }) : (x.host || "")))))));
}

/* an order ticket, sketched from the run's own keys (the move's name and ticker, its size, the amount, how it is funded): no typed
   figure and no dollar the page computes; "Crash-test this order" starts the replay (the same action as Replay); "Submit order"
   is disabled: a simulation never sends an order. Hidden when the run has no move */
function ticket(r, store) {
  const P = globalThis.PF, v = P && r ? P.view(r) : null, mv = v && v.move, f = P && P.fmt;
  if (!mv || !f || typeof mv.weight !== "number" || typeof r.amount !== "number") return null;
  const ch = r.scenario && r.scenario.change ? r.scenario.change : {};
  const funded = ch.op === "replace" && ch.from_ticker ? ch.from_ticker : "your other holdings, in proportion";
  const row = (k, val) => h("div", { class: "how-ticket-row" }, h("dt", { text: k }), h("dd", {}, val));
  const go = h("button", { type: "button", class: "btn btn-primary how-ticket-go", text: "Crash-test this order" });
  go.addEventListener("click", () => {
    store.set({ replay: Date.now() });
    requestAnimationFrame(() => {                       // the stage scrolls itself; without it, go where the replay starts
      const stage = document.getElementById("replay");
      if (stage) stage.scrollIntoView({ block: "start" });
    });
  });
  return h("figure", { class: "how-ticket", "aria-labelledby": "how-ticket-cap" },
    h("figcaption", { class: "how-ticket-cap", id: "how-ticket-cap", text: "An order ticket, sketched" }),
    h("dl", { class: "how-ticket-dl" },
      row("Security", `${mv.name}${mv.ticker && mv.ticker !== mv.name ? ` (${mv.ticker})` : ""}`),
      row("Action", "Add to your mix"),
      row("Amount", `${f.share(mv.weight)} of your ${f.money(r.amount)}`),
      row("Funded from", funded)),
    h("div", { class: "how-ticket-acts" }, go,
      h("button", { type: "button", class: "btn btn-quiet how-ticket-submit", disabled: true, "aria-describedby": "how-ticket-note", text: "Submit order" })),
    h("p", { class: "how-ticket-note", id: "how-ticket-note", text: "Simulation only: no order is ever sent." }),
    h("p", { class: "how-ticket-r38", text: "Shown on every order, at the client’s click, never triggered by the order; it makes no recommendation." }));
}

/* ---- mount: the head once; the diagram, services and reconciliation follow the Result; the eval is read once ---- */
let evalPromise = null;
function loadEval() {
  if (!evalPromise) {
    evalPromise = fetch(new URL("../eval_results.json", import.meta.url), { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null)).then((j) => ({ ev: H.evalOf(j), blind: H.blindLine(j), paired: H.pairedLine(j) }))
      .catch(() => ({ ev: null, blind: null, paired: null }));
  }
  return evalPromise;
}

export function mount(el, store) {
  el.classList.add("how");
  const prov = h("p", { class: "how-prov", hidden: true });
  const flowSlot = h("div", { class: "how-flow-slot" }), awsSlot = h("div", { class: "how-aws-slot" });
  const evalSlot = h("div", { class: "how-eval-slot" }), reconSlot = h("div", { class: "how-recon-slot" });
  /* R22: the question, one plain answer, the five steps and the AWS row in words; the trace's own numbers (ms, tokens, request
     ids, grounding), the eval and the reconciliation show with "Show the details" (in place on the diagram, and in the panel) */
  const frame = h("div", { class: "frame how-frame" });
  const fold = details("how", store, [prov, h("div", { class: "how-proof" }, evalSlot, reconSlot)],
    { label: "How it works: the numbers behind each step", onToggle: (on) => { frame.dataset.details = on ? "open" : ""; } });
  const blindSlot = h("p", { class: "how-blind", hidden: true });          // the AI's measured value, in Simple too (pre-freeze 2)
  const bigSlot = h("div", { class: "how-big", hidden: true });           // item 7: the two scores as big readouts
  /* plain words: the AI reader named once in full, the number check, each with its exact term in the tooltip */
  const answer = ["The ", term("AI reader"), " (Claude on Amazon Bedrock) read your question; code computed every number; the ",
    term("number check"), " traced each one back to the data."];
  /* the lead (pitch): "understandable by everybody: what it does, the agentic work, and how it fits": one calm panel, three short
     columns, plain words, no figures (the replay's years come from the run); R38's order-ticket wording exact */
  const spanSlot = h("span", { text: "recent" });
  const col = (title, body, extra) => h("div", { class: "how-minute-col" }, h("h4", { class: "how-minute-h", text: title }), h("p", { class: "how-minute-p" }, ...body), extra || null);
  const ticketSlot = h("div", { class: "how-ticket-slot" });     // the lead 18:23: where EPICENTRE sits at an order-execution-only broker
  const minute = h("section", { class: "how-minute", "aria-labelledby": "how-minute-t" },
    h("h3", { class: "how-minute-t", id: "how-minute-t", text: "In one minute" }),
    h("div", { class: "how-minute-cols" },
      col("What it does", ["You show what you own and say what you want to do. EPICENTRE replays that move through real ", spanSlot,
        " markets and shocks and shows, in dollars, whether it stayed inside your limits. It never tells you what to do."]),
      col("The agentic work", ["Claude on Amazon Bedrock reads your words (the move, the shock, your limits) and writes the explanation. Code computes every number, checks every word the AI wrote, and holds the loop. Guardrails block advice. ",
        h("a", { class: "linkbtn how-agentlog", href: "#agentlog", "data-agentlog-open": "", text: "Watch the AI work" })]),
      col("Where it fits", ["At the order ticket of an order-execution-only broker, such as National Bank Direct Brokerage: one click before the client submits, shown on every order, never triggered by the order, and it makes no recommendation. The tamper-proof record keeps what the client saw."], ticketSlot)));
  frame.append(head("how-title", "How does it work?", answer), minute, h("div", { class: "how-proofline" }, bigSlot, blindSlot),
    flowSlot, awsSlot, fold);
  frame.dataset.details = fold.querySelector(".cl-more").getAttribute("aria-expanded") === "true" ? "open" : "";
  el.setAttribute("aria-labelledby", "how-title");
  el.replaceChildren(frame);

  let revealed = false;
  /* live only when this page is live, the Result says live, and it is not the investor's saved run (it landed from a live run) */
  const liveNow = (r) => { const st = store.get(); return st.mode === "live" && !!r && r.mode === "live" && r !== peekRun(st.investor); };
  const draw = (r) => {
    const d0 = r && r.series && Array.isArray(r.series.dates) ? String(r.series.dates[0] || "") : "", d1 = r && typeof r.as_of === "string" ? r.as_of : "";
    if (/^\d{4}/.test(d0) && /^\d{4}/.test(d1)) spanSlot.textContent = `${d0.slice(0, 4)}–${d1.slice(2, 4)}`;   // the replay's own years
    ticketSlot.replaceChildren(...[ticket(r, store)].filter(Boolean));
    const flow = H.flowOf(r, { live: liveNow(r), shown: shownStatus });
    const p = flow && flow.provenance;
    prov.hidden = !p;
    prov.replaceChildren(...(p ? [h("strong", { text: `${p.text}${p.time ? ` at ${p.time}` : ""}.` }),
      h("span", { text: p.saved ? " A saved run: its request ids and guardrail results are the ones AWS returned then." : " Its request ids and guardrail results are the ones AWS just returned." })] : []));
    flowSlot.replaceChildren(...(flow ? [flowFigure(flow)] : []));
    awsSlot.replaceChildren(services(flow));
    const rc = H.reconciliationOf(r);
    reconSlot.replaceChildren(...(rc ? [reconCard(rc)] : []));
    arm(flowSlot.firstChild);
  };
  /* the one reveal: hidden only once the reader is within a viewport of the diagram (a page captured without scrolling, or
     printed, shows it whole), drawn when a fifth of it is in view; the pause glyph or reduced motion shows it at once */
  const motionOK = () => window.EPI_MOTION !== false && !!window.matchMedia && window.matchMedia("(prefers-reduced-motion: no-preference)").matches;
  let ioNear = null, ioIn = null;
  function arm(fig) {
    if (ioNear) ioNear.disconnect();
    if (ioIn) ioIn.disconnect();
    if (!fig || revealed || !motionOK() || typeof IntersectionObserver !== "function") return;
    const show = () => { revealed = true; ioNear.disconnect(); ioIn.disconnect(); fig.getBoundingClientRect();
      requestAnimationFrame(() => { fig.dataset.reveal = motionOK() ? "done" : ""; }); };
    ioNear = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting) && !revealed && !fig.dataset.reveal) fig.dataset.reveal = "pending";
    }, { rootMargin: "0px 0px 100% 0px" });
    ioIn = new IntersectionObserver((es) => {
      if (!es.some((e) => e.isIntersecting) || revealed) return;
      if (!fig.dataset.reveal) fig.dataset.reveal = "pending";
      show();
    }, { rootMargin: "0px 0px -20% 0px" });
    ioNear.observe(fig);
    ioIn.observe(fig);
  }
  window.addEventListener("epi:motion", (e) => {
    const fig = flowSlot.firstChild;
    if (fig && e.detail && e.detail.on === false && fig.dataset.reveal === "pending") { revealed = true; fig.dataset.reveal = ""; }
  });
  store.on("result", draw);
  draw(store.get().result);
  loadEval().then(({ ev, blind, paired }) => {
    evalSlot.replaceChildren(...(ev ? [evalCard(ev)] : []));
    if (!blind) return;
    const big = (k, who, cls) => h("div", { class: `how-big-one ${cls}` }, mean(h("p", { class: "how-big-n" }, `${k}/${blind.n}`),
      `${k}/${blind.n}: the blind questions where ${who} read the right shock.`), h("p", { class: "how-big-who" }, who));
    bigSlot.replaceChildren(big(blind.navigator, "the AI reader", "is-ai"), big(blind.keyword, "keyword rules alone", "is-kw"),
      h("p", { class: "how-big-cap" }, "blind questions, right shock read"));
    bigSlot.hidden = false;
    blindSlot.replaceChildren(...figs(blind.text, [{ text: blind.n, meaning: `${blind.n}: questions written blind and never used for tuning.` },
      { text: blind.navigator, meaning: `${blind.navigator}: the times the AI reader read the right shock, out of ${blind.n}.` },
      { text: blind.keyword, meaning: `${blind.keyword}: the times the keyword rules alone read the right shock, out of ${blind.n}.` }]),
      ...(paired ? [" ", ...figs(paired.text, [{ text: paired.a, meaning: `${paired.a}: questions the AI reader read right and the keyword rules did not.` },
        { text: paired.b, meaning: `${paired.b}: questions the keyword rules read right and the AI reader did not.` }])] : []));
    blindSlot.hidden = false;
  });
}
