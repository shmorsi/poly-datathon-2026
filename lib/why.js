/* EPICENTRE lane U6, pure helpers for #why, the #thread drawer and the navigator-off switch. ES module, no DOM, no network.
   Every number they hand to the page is a Result key (or the debrief's own verified text); a missing key gives null and the
   page hides that line. They read globalThis.PF (web/lib.js) at call time, never at import time (INTERFACES.md). */

import { shownStatus, bindingWord } from "./status.js";   // the page's one status vocabulary (R20, lane U5)

const pf = () => globalThis.PF || {};
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const NB = " ", MINUS = "−";

export const QUESTIONS = [
  { id: "data", title: "What data?" },
  { id: "why", title: "Why this verdict?" },
  { id: "limits", title: "What limits?" },
  { id: "would_change", title: "What would change the answer?" },
];
export const FAMILIES = { tariffs: "Tariff war", war_oil: "War & oil", chips: "Chip war", rates: "Rate shock" };
const ENTITY_WORDS = { today: "today’s mix", after: "the mix after the move", "your floor": "your floor", "your amount": "your amount",
  "shock check": "the shock check", "one company": "one company", "one sector": "one sector", illustration: "the fictional mix" };
const STOP = new Set(["blocked", "error", "clarify", "limits_missing"]);
const WITHHELD_RX = /withheld/i;

/* ---- the debrief's text as segments: a number right before its [T#] tag becomes a button; the tags themselves are dropped ---- */
const TAG_RX = /\[(T\d+(?:\s*[,;]\s*T\d+)*)\]/g;
const NUM_END = /(\$?\d+(?:,\d{3})*(?:\.\d+)?(?:k|K|M|bn)?(?:[  ]?(?:%|pp|percentage points?|days?|weeks?|months?|years?)(?![A-Za-z]))?)[  ]*$/;
const nbsp = (s) => s.replace(/(\d) (%|pp)/g, "$1" + NB + "$2");

export function segments(text) {
  const t = String(text == null ? "" : text), out = [];
  let last = 0, m;
  TAG_RX.lastIndex = 0;
  const pushText = (s) => { if (s) { const prev = out[out.length - 1]; if (prev && prev.t === "text") prev.text += s; else out.push({ t: "text", text: s }); } };
  while ((m = TAG_RX.exec(t))) {
    const ids = m[1].match(/T\d+/g), before = t.slice(last, m.index);
    const n = NUM_END.exec(before);
    let start = n ? n.index : -1;
    if (n) {
      const ch = before[start - 1] || "";
      if (/[A-Za-z0-9_.,\-]/.test(ch) && ch !== "-") start = -1;          // "G7", "COVID-19": a name, not a number
      else if (ch === MINUS || ch === "-" || ch === "+") {                  // a sign that belongs to the number ("−34.5 %")
        const ch2 = before[start - 2] || "";
        if (!/[A-Za-z0-9_]/.test(ch2)) start -= 1;
      }
    }
    if (start >= 0) {
      pushText(before.slice(0, start));
      out.push({ t: "num", text: nbsp(before.slice(start).trimEnd()), id: ids[0], ids });
      const gap = before.length - before.trimEnd().length;
      if (gap && !/\s$/.test(before.slice(start).trimEnd())) { /* the space before the tag is dropped with the tag */ }
    } else {
      pushText(before.replace(/[  ]+$/, ""));
      out.push({ t: "ref", id: ids[0], ids });
    }
    last = m.index + m[0].length;
  }
  pushText(t.slice(last));
  for (const s of out) if (s.t === "text") s.text = nbsp(s.text);
  return out;
}
export const plain = (segs) => arr(segs).map((s) => (s.t === "ref" ? "" : s.text)).join("").replace(/\s+([.,;:])/g, "$1").trim();

/* the sentences in reading order (the verdict first, then the four questions), each with its index in debrief.sentences */
function ordered(d) {
  const pool = arr(d.sentences), secs = d.sections, out = [];
  if (Array.isArray(secs)) {                               // the prototype's list form [{id, title, text, kind}]
    secs.forEach((s, k) => { if (obj(s) && str(s.text)) out.push({ i: -1 - k, section: s.id === "change" ? "would_change" : s.id, text: s.text, kind: s.kind, refs: arr(s.refs) }); });
    return out;
  }
  const used = new Set();
  for (const q of QUESTIONS) {
    let idx = obj(secs) && Array.isArray(secs[q.id]) ? secs[q.id] : null;
    if (!idx) idx = pool.map((s, i) => (obj(s) && s.section === q.id ? i : -1)).filter((i) => i >= 0);
    for (const i of idx) {
      const s = obj(pool[i]);
      if (!s || !str(s.text) || used.has(i)) continue;
      used.add(i);
      out.push({ i, section: q.id, text: s.text, kind: s.kind, refs: arr(s.refs) });
    }
  }
  return out;
}

const sentenceOf = (s, names) => {
  const P = pf(), kind = str(s.kind) || null;
  return { i: s.i, section: s.section, kind, marker: P.markerOf ? P.markerOf(kind) : { icon: "i-pending", word: "unlabelled" },
    segs: upFirst(named(segments(s.text), names)), refs: s.refs };
};
/* the moved ticker written as the page names it (NVDA -> NVIDIA), text only, whole words; numbers and tags untouched */
function movedName(r) {
  const P = pf(), m = P.moveOf ? P.moveOf(r) : null;
  return m && m.name && m.name !== m.ticker ? [new RegExp(`(?<![A-Za-z0-9.\\-])${m.ticker.replace(/[.\\-]/g, "\\$&")}(?![A-Za-z0-9\\-])`, "g"), m.name] : null;
}
function named(segs, names) {
  const F = pf().fmt;
  for (const g of segs) {
    if (g.t !== "text") continue;
    if (names) g.text = g.text.replace(names[0], names[1]);
    if (F) g.text = g.text.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (m) => F.date(m) || m);
  }
  return segs;
}
function upFirst(segs) {
  const f = segs[0];
  if (f && f.t === "text" && /^[a-z]/.test(f.text)) f.text = f.text.charAt(0).toUpperCase() + f.text.slice(1);
  return segs;
}

/* each fact's Result key, from its own trace row (inputs.path / inputs.key): how the page knows what a cited number is */
export function pathsOf(r) {
  const facts = obj(obj(r) && r.facts) || {}, out = {};
  for (const t of arr(obj(r) && r.trace)) {
    if (obj(t) && Object.prototype.hasOwnProperty.call(facts, t.id) && obj(t.inputs)) out[t.id] = { path: str(t.inputs.path), key: str(t.inputs.key) };
  }
  return out;
}
/* the check that decided the verdict: the first failing rule in code's check_order, else the first caution, else none */
export function decidingRule(r) {
  const order = arr(obj(obj(r) && r.scenario) && r.scenario.check_order), checks = arr(obj(r) && r.checks).map(obj).filter(Boolean);
  const pos = (c) => (order.includes(c.rule) ? order.indexOf(c.rule) : order.length);
  const first = (st) => checks.filter((c) => c.status === st && str(c.rule)).sort((a, b) => pos(a) - pos(b))[0];
  const c = first("fail") || first("warn");
  return c ? c.rule : null;
}
const WORST = /^turbulence\.[a-z_]+\.worst_(after|today)$/;

/* 3 to 5 sentences for the first read (design doc §2 item 6), chosen by what each sentence cites, never by its wording: the
   verdict sentence; the one citing the deciding check's own value and the one citing its limit; the one citing the asked shock's
   worst episode; what would change the answer. Kept in reading order; "This already happened" is the page's caption under the
   verdict, and the full text stays one tap away. */
export function pick(list, r) {
  const facts = obj(obj(r) && r.facts) || {}, paths = pathsOf(r), dec = decidingRule(r), P = pf();
  const move = !!(P.moveOf && P.moveOf(r));
  const cites = (s, pred) => arr(s.refs).some((id) => pred(paths[id] || {}, obj(facts[id]) || {}));
  const isValue = (p) => !!dec && ((p.path === "checks.value" && p.key === dec) || (dec === "max_drawdown" && p.path === `metrics.${move ? "after" : "today"}.max_drawdown`)
    || (dec === "scenario_stress" && WORST.test(p.path || "")));   // the shock check's value is checks.value[scenario_stress] or turbulence.<family>.worst_*
  const isLimit = (p) => !!dec && ((p.path === "checks.limit" && p.key === dec) || (dec === "max_drawdown" && p.path === "limits.floor")
    || (dec === "scenario_stress" && p.path === "limits.scenario_stress"));
  const isShock = (p) => WORST.test(p.path || "") || (p.path === "checks.value" && p.key === "scenario_stress") || p.path === "limits.scenario_stress";
  const isFamily = (p, f) => Object.prototype.hasOwnProperty.call(FAMILIES, f.entity);
  const by = (sec) => list.filter((s) => s.section === sec);
  const body = list.filter((s) => s.section !== "data" && !/already happened/i.test(s.text));
  const chosen = [];
  const add = (s) => { if (s && !chosen.includes(s) && chosen.length < 4) chosen.push(s); };
  add(body.find((s) => cites(s, isValue)) || by("why")[0]);
  add(body.find((s) => cites(s, isLimit)));
  add(body.find((s) => cites(s, isShock)) || body.find((s) => cites(s, isFamily)));
  add(by("would_change")[0]);
  for (const s of [...by("why"), ...by("would_change"), ...by("limits"), ...by("data")]) {
    if (chosen.length >= 2) break;
    if (!/already happened/i.test(s.text)) add(s);
  }
  return list.filter((s) => chosen.includes(s));
}

/* who wrote the explanation, from the trace: the EXPLAIN rows Amazon Bedrock answered (the shown draft is the last one) */
export function draftsOf(r) {
  return arr(obj(r) && r.trace).filter((t) => obj(t) && t.step === "EXPLAIN" && t.tool === "explain.draft");
}
const bedrockAnswered = (rows) => rows.some((t) => t.service === "Amazon Bedrock" && !(obj(t.outputs) && t.outputs.error));

/* the code-written reasons of the deciding checks (governance's own sentences), for a run with no explanation shown */
function reasonsOf(r) {
  const P = pf(), v = obj(r && r.__view) || (P.view ? P.view(r) : null);
  const rows = arr(v && v.rows).filter((x) => x && x.reason);
  const deciding = rows.filter((x) => x.status === "fail" || x.status === "warn");
  const names = movedName(r), F = P.fmt;
  const tidy = (t) => { let out = String(t); if (names) out = out.replace(names[0], names[1]);
    return F ? out.replace(/\b(\d{4}-\d{2}-\d{2})\b/g, (m) => F.date(m) || m) : out; };
  const tierOf = new Map(arr(obj(r) && r.checks).map(obj).filter(Boolean).map((c) => [c.rule, c.tier]));
  const dec = decidingRule(r);
  return (deciding.length ? deciding : rows).slice(0, 4).map((x) => {
    const tier = tierOf.get(x.rule), st = shownStatus(x.status, tier) || { word: x.word, tone: x.tone, icon: x.icon };
    return { rule: x.rule, status: x.status, word: st.word, tone: st.tone, icon: st.icon, name: x.name, text: tidy(x.reason),
      binding: x.rule === dec ? bindingWord(x.status, tier) : null };
  });
}

/* the whole #why model. state: "shown" | "flagged" | "withheld" | "off" | "stopped" | "empty" */
export function explanation(r) {
  r = obj(r);
  if (!r) return { state: "empty", lead: null, picked: [], groups: [], count: 0, note: null, reasons: [] };
  const facts = obj(r.facts) || {}, d = obj(r.debrief), status = str(r.status);
  if (status && STOP.has(status)) return { state: "stopped", lead: null, picked: [], groups: [], count: 0, reasons: [],
    note: { tone: "none", icon: "i-pending", word: "No explanation", text: str(r.message) || "This run stopped before the explanation." } };
  const list = d ? ordered(d) : [];
  if (d && (list.length || str(d.verdict_sentence))) {
    const names = movedName(r), sentences = list.map((x) => sentenceOf(x, names));   // names may be null: dates are still tidied
    const groups = QUESTIONS.map((q) => ({ id: q.id, title: q.title, sentences: sentences.filter((s) => s.section === q.id) }))
      .filter((g) => g.sentences.length);
    const keep = new Set(pick(list, r).map((s) => s.i));
    const lead = str(d.verdict_sentence) ? { segs: named(segments(d.verdict_sentence), names) } : null;
    const rc = obj(r.receipt), open = arr(rc && rc.defects).map(str).filter(Boolean);
    const flagged = d.flagged === true;
    const note = flagged ? { tone: "caveat", icon: "i-warn", word: "Flagged", text: open.length
      ? `After ${rc && rc.drafts === 2 ? "one rewrite" : "the first draft"}, the code that checks the explanation still names ${open.length === 1 ? "one open point" : `${open.length} open points`}:`
      : "The code that checks the explanation left it flagged.", items: open } : null;
    const drafts = draftsOf(r), shown = drafts[drafts.length - 1] || null;
    return { state: flagged ? "flagged" : "shown", by: "bedrock", lead, picked: sentences.filter((s) => keep.has(s.i)), groups,
      count: sentences.length + (lead ? 1 : 0), note, reasons: [],
      writer: shown ? { model: str(shown.model), ms: isNum(shown.ms) ? shown.ms : null, requestId: str(shown.request_id),
        drafts: drafts.length, service: str(shown.service) } : null };
  }
  const msg = str(r.message), reasons = reasonsOf(r);
  if (msg && WITHHELD_RX.test(msg))
    return { state: "withheld", by: "code", lead: null, picked: [], groups: [], count: 0, reasons,
      note: { tone: "caveat", icon: "i-warn", word: "Withheld", text: msg } };
  const drafts = draftsOf(r);
  const text = msg && /bedrock/i.test(msg) ? msg
    : drafts.length && bedrockAnswered(drafts) ? "The explanation is not part of this run."
      : "This run was made without Amazon Bedrock, so no explanation was written. The reasons below are the ones code wrote for each deciding check.";
  return { state: "off", by: "code", lead: null, picked: [], groups: [], count: 0, reasons,
    note: { tone: "none", icon: "i-pending", word: "Made without Amazon Bedrock", text } };
}

/* ---- the receipt line: ‘14 of 14 numbers traced to the data, guardrail passed, corrected once’ (+ ‘recorded on’ for a saved run, R15).
   The page sets the separating dots itself, as hidden marks between the parts. ---- */
export function guardrailOf(r) {
  const g = obj(obj(r) && r.guardrail);
  if (!g) return null;
  const inp = obj(g.input), out = obj(g.output);
  const hit = (x) => !!x && (x.blocked === true || x.action === "GUARDRAIL_INTERVENED" || x.topic_hit === true);
  const word = (x) => (!x ? null : x.blocked === true ? "blocked" : hit(x) ? "intervened" : x.error ? "could not run" : "passed");
  const gr = obj(out && out.grounding);
  const score = gr && isNum(gr.score) ? gr.score : isNum(g.grounding) ? g.grounding : null;
  const threshold = gr && isNum(gr.threshold) ? gr.threshold : null;
  const bits = [];
  if (inp) bits.push(`Input guardrail: ${word(inp)}.`);
  if (out && (hit(out) || out.error)) bits.push(`Output guardrail: ${word(out)}.`);
  if (score !== null) bits.push(`Output grounding: ${score.toFixed(2)}${threshold !== null ? ` (threshold ${threshold.toFixed(2)})` : ""}, advisory, not a gate; the number check above is the gate (eval §8).`);
  else if (out && !hit(out) && !out.error) bits.push("Output guardrail: passed.");
  if (!bits.length) return null;
  return { input: word(inp), output: word(out), score, threshold, text: bits.join(" "),
    tone: hit(inp) || hit(out) ? "caveat" : "none", ids: [inp, out].map((x) => x && str(x.request_id)).filter(Boolean) };
}
const RECORDED_RX = /recorded on (\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4})/;
export function recordedOn(r, mode) {
  r = obj(r) || {};
  const P = pf(), iso = [r.recorded_at, r.saved_at, r.recorded_on].map(str).find(Boolean);
  const date = iso && P.fmt ? P.fmt.date(iso) : "";
  const m = !date && RECORDED_RX.exec(String(r.message || ""));
  const saved = r.mode === "demo_replay" || mode === "static";
  return { saved, date: date || (m ? m[1].replace(/\s+/g, NB) : null) };
}
export function receiptLine(r, mode) {
  r = obj(r);
  const rc = obj(r && r.receipt), d = obj(r && r.debrief);
  if (!rc || !d || !isNum(rc.verified) || !isNum(rc.total)) return null;     // no explanation on screen: no receipt for it
  const P = pf(), parts = [];
  const all = rc.verified === rc.total, clean = !arr(rc.defects).length && !(d && d.flagged === true);
  parts.push({ text: `${rc.verified} of ${rc.total} numbers traced to the data`, tone: all ? "inside" : "outside", icon: all ? "i-in" : "i-out", lead: true });
  const g = guardrailOf(r);                                    // its own sentence under the parts (never "passed" below a threshold)
  if (rc.drafts === 2) parts.push({ text: "corrected once" });
  else if (rc.drafts === 1 && !arr(obj(rc.first_try) && rc.first_try.defects).length) parts.push({ text: "clean on the first draft" });
  const rec = recordedOn(r, mode);
  if (rec.saved) parts.push({ text: rec.date ? `recorded on ${rec.date}` : "a saved run", saved: true });
  return { parts, text: parts.map((p) => p.text).join(", "), verified: rc.verified, total: rc.total, drafts: isNum(rc.drafts) ? rc.drafts : null,
    guardrail: g, saved: rec.saved, recorded: rec.date, clean: all && clean, fmt: !!P.fmt };
}

/* ---- the #thread drawer: one fact pulled through the run ---- */
const nameOf = (tk) => { const P = pf(); return P.moveOf ? ({ NVDA: "NVIDIA", TSLA: "Tesla", MSFT: "Microsoft", "SHOP.TO": "Shopify",
  "CNQ.TO": "Canadian Natural", "ENB.TO": "Enbridge", "BTC-USD": "Bitcoin", "ETH-USD": "Ether" })[tk] || tk : tk; };
export function entityText(entity) {
  const e = str(entity);
  if (!e) return null;
  if (Object.prototype.hasOwnProperty.call(FAMILIES, e)) return { tariffs: "the tariff war", war_oil: "war and oil shocks", chips: "the chip war", rates: "rate shocks" }[e];
  if (Object.prototype.hasOwnProperty.call(ENTITY_WORDS, e)) return ENTITY_WORDS[e];
  return /^[A-Z0-9.\-]{2,10}$/.test(e) ? nameOf(e) : e;
}
/* a Result value written with enough digits to show it was computed, not typed (no rounding beyond 10 significant digits) */
export function rawText(v) {
  if (!isNum(v)) return null;
  const s = Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(10)));
  return s.replace(/^-/, MINUS);
}
/* a fact written the way the rest of the page writes it: a weight or a limit as a share ("40 %", "−15 %", PF.fmt.share, as the
   chips, the dial and lib.js compareOf do), a fall or a growth with its tenth ("−34.5 %", fmt.pct), anything else PF.factText */
const SHARE_RULES = new Set(["single_stock", "sector", "crypto", "esg_direct", "esg_indirect", "risk_concentration"]);
export function pageText(r, id) {
  const f = obj(obj(obj(r) && r.facts) && r.facts[id]), P = pf();
  if (!f || !isNum(f.value) || !P.fmt) return f && P.factText ? P.factText(f) || null : null;
  if (f.unit === "pct") {
    const own = traceRow(r, id), inp = obj(own && own.inputs) || {}, path = str(inp.path) || "", recipe = str(inp.recipe);
    const share = recipe === "limits" || path === "scenario.change.weight" || path.startsWith("tipping_point")
      || ((path === "checks.value" || path === "checks.limit") && SHARE_RULES.has(str(inp.key)));
    return share ? P.fmt.share(f.value) : P.fmt.pct(f.value);
  }
  return P.factText ? P.factText(f) || null : null;
}

export function factCard(r, id) {
  const f = obj(obj(obj(r) && r.facts) && r.facts[id]);
  if (!f) return null;
  const P = pf(), kind = str(f.kind), names = movedName(r), label = str(f.label);
  return { id, label: label ? nbsp(names ? label.replace(names[0], names[1]) : label) : label, valueText: pageText(r, id), raw: rawText(f.value), unit: str(f.unit), kind,
    marker: P.markerOf ? P.markerOf(kind) : { icon: "i-pending", word: "unlabelled" }, entity: str(f.entity), entityText: entityText(f.entity) };
}

const traceRow = (r, id) => arr(obj(r) && r.trace).find((t) => obj(t) && t.id === id) || null;
const factIds = (r) => new Set(Object.keys(obj(obj(r) && r.facts) || {}));
const inputsOf = (row) => {
  const i = obj(row && row.inputs) || {}, out = [];
  for (const k of ["path", "key", "recipe", "formula", "which", "ticker", "families", "draft"]) {
    const v = i[k];
    if (v == null || v === "") continue;
    out.push([k, Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v)]);
  }
  return out;
};
const stepOf = (row) => row && { id: row.id, step: str(row.step), tool: str(row.tool), inputs: inputsOf(row), service: str(row.service),
  model: str(row.model), ms: isNum(row.ms) ? row.ms : null, requestId: str(row.request_id), source: str(row.source) };

/* how code produced a number, by its recipe (the words of pipeline._RECIPE_WORDS, which the live recompute answers with) */
const RECIPE = {
  flight_plan: { title: "Read from your inputs", how: "Read back from your inputs: no tool computes this number." },
  limits: { title: "Set by your limits", how: "Set by governance.load_limits from your answers and the limits table." },
  "evaluate.today": { title: "Computed by code", how: "Computed by governance.evaluate on today’s mix, on the data up to {as_of}." },
  "evaluate.after": { title: "Computed by code", how: "Computed by governance.evaluate on the mix after the move, on the data up to {as_of}." },
  tipping_point: { title: "Computed by code", how: "Computed by tools.allocation.tipping_point (governance.evaluate at each size), on the data up to {as_of}." },
  attribution: { title: "Computed by code", how: "Computed by tools.events.drawdown_attribution on the mix’s path and the shocks known at {as_of}." },
};
export function recipeOf(r, id) {
  const own = traceRow(r, id), k = str(obj(own && own.inputs) && own.inputs.recipe), P = pf();
  const d = RECIPE[k];
  if (!d) return { title: "Computed by code", how: null, input: false };
  if (k === "flight_plan" && /^agents\.scenario\./.test(str(own.tool) || "")) return { title: "Read from your question by the AI reader", how: null, input: true };
  const asOf = str(obj(r) && r.as_of), day = asOf && P.fmt ? P.fmt.date(asOf) || asOf : asOf;
  return { title: d.title, how: d.how.replace("{as_of}", day || "the decision date"), input: k === "flight_plan" || k === "limits" };
}

/* who set a number (R4, R13): a persona's limits are assumed for the fictional profile, your own are typed by you; a fictional
   amount or size carries the fiction label. null for a computed fact (its source line says enough). */
const LIMIT_OF_RULE = { max_drawdown: "floor", single_stock: "single_stock", sector: "sector", crypto: "crypto" };
export function setBy(r, id) {
  r = obj(r);
  const f = obj(obj(r && r.facts) && r.facts[id]);
  if (!f) return null;
  if (f.kind === "fiction") return "Fictional illustration, not a recommendation.";
  const own = traceRow(r, id), inp = obj(own && own.inputs) || {}, recipe = str(inp.recipe);
  if (recipe !== "limits" && recipe !== "flight_plan") return null;
  const path = str(inp.path) || "", key = path.startsWith("limits.") ? path.slice(7) : path === "checks.limit" ? LIMIT_OF_RULE[str(inp.key)] || str(inp.key) : null;
  const edited = arr(obj(r.limits) && r.limits.edited);
  if (key && edited.includes(key)) return "Set by you, never read from an account.";
  return str(r.pilot) ? "Assumed from the profile, not set by you." : "Set by you, never read from an account.";
}

/* the fact's own trace row (where the number was recorded), and the step that computed it: the run's row of the same tool, in
   the same step, for the same mix ("evaluate.after" -> governance.evaluate with which "after"); a recipe with no such row
   (an input, a limit) has only its own row */
export function traceOf(r, id) {
  const own = traceRow(r, id);
  if (!own) return null;
  const facts = factIds(r), recipe = str(obj(own.inputs) && own.inputs.recipe) || "";
  const which = recipe.startsWith("evaluate.") ? recipe.slice(9) : null;
  if (recipe === "flight_plan" || recipe === "limits") return { recorded: { ...stepOf(own), value: rawText(obj(own.outputs) && own.outputs.value) }, computed: null };
  const rows = arr(r.trace).filter((t) => obj(t) && !facts.has(t.id) && t.tool === own.tool);
  const by = (t) => (which ? obj(t.inputs) && t.inputs.which === which : true);
  const comp = rows.find((t) => t.step === own.step && by(t)) || rows.find(by) || null;
  const v = obj(own.outputs) && own.outputs.value;
  return { recorded: { ...stepOf(own), value: rawText(v) }, computed: comp ? stepOf(comp) : null };
}

/* result.evidence[fact_id] (B3, proofs.evidence_rows public cut). null = the Result has no evidence key: the page hides the block */
export function evidenceOf(r, id) {
  const ev = obj(obj(r) && r.evidence);
  if (!ev) return null;
  const P = pf(), rows = arr(ev[id]).map(obj).filter(Boolean).map((x) => ({ file: str(x.file), date: P.fmt ? P.fmt.date(x.date) || str(x.date) : str(x.date),
    ticker: str(x.ticker), value: isNum(x.value) ? (Math.abs(x.value) < 10 ? x.value.toFixed(4) : x.value.toFixed(2)).replace(/^-/, MINUS) : null }));
  if (rows.length) return { rows, note: null, from: "evidence" };
  const mine = seriesRows(r, id);
  if (mine.length) return { rows: mine, note: null, from: "series" };
  const own = traceRow(r, id), recipe = str(obj(own && own.inputs) && own.inputs.recipe);
  const input = recipe === "flight_plan" || recipe === "limits";
  return { rows: [], note: input ? "An input or a limit: no market data sits behind it."
    : "No data rows are published with this run: the starter prices are licensed, so the public demo leaves them out." };
}

/* the rows proofs.evidence_rows would print first (its _fact_dates and _portfolio_rows, mirrored): the mix's value, base 100, on
   the dates the fact is about, read from the Result's own series (a lookup, never a computation; the public cut drops them) */
const SIDE_WORD = { today: "Today’s mix", after: "The mix after the move" };
export function seriesRows(r, id) {
  r = obj(r);
  const own = traceRow(r, id), path = str(obj(own && own.inputs) && own.inputs.path) || "", parts = path.split(".");
  if (parts.length < 3 || !(parts[1] in SIDE_WORD)) return [];
  const [head, side] = parts, tail = parts.slice(2).join(".");
  let dates = [];
  if ((head === "metrics" && tail === "max_drawdown") || (head === "worst_rolling" && tail === "value"))
    dates = [obj(obj(r[head]) && r[head][side]) || {}].map((m) => [m.peak_date, m.trough_date])[0];
  else if (head === "metrics" && tail === "cagr") { const d = arr(obj(r.series) && r.series.dates); dates = d.length ? [d[0], d[d.length - 1]] : []; }
  else return [];
  const asOf = str(r.as_of), span = arr(obj(r.series) && r.series.dates), vals = arr(obj(r.series) && r.series[side]), P = pf();
  if (!asOf || span.length !== vals.length) return [];
  const at = new Map(span.map((d, i) => [d, vals[i]])), out = [], seen = new Set();
  for (const d of dates) {
    if (!str(d) || d > asOf || seen.has(d)) continue;
    seen.add(d);
    const v = at.get(d);
    if (isNum(v)) out.push({ file: "this run’s replay series (base 100, CAD)", date: P.fmt ? P.fmt.date(d) || d : d, ticker: SIDE_WORD[side], value: v.toFixed(2) });
  }
  return out;
}

/* R12: ‘ours x %, published y %, source’ for the fact's ticker, or for the lines of the mix a portfolio number was computed on */
const pctText = (row, v, text) => {
  if (str(text)) return nbsp(str(text));
  if (!isNum(v)) return null;
  const pts = row.unit === "pp" ? v : v * 100;                  // B3 rows are fractions (0.17991); "pp" marks a row in points
  return (pts < 0 ? MINUS : "") + Math.abs(pts).toFixed(2) + NB + "%";
};
export function reconciliationOf(r) {
  const rc = obj(r) && r.reconciliation;
  const rows = (Array.isArray(rc) ? rc : arr(obj(rc) && rc.rows)).map(obj).filter(Boolean);
  const meta = obj(rc) || {};
  return { rows, n: isNum(meta.n) ? meta.n : null, within: isNum(meta.within) ? meta.within : null,
    tolerance: isNum(meta.tolerance_pp) ? meta.tolerance_pp : null, source: str(meta.source) };
}
export function reconciliationFor(r, id) {
  r = obj(r);
  const { rows } = reconciliationOf(r);
  const f = obj(obj(r && r.facts) && r.facts[id]);
  if (!rows.length || !f) return [];
  const tk = (x) => str(x.ticker) || str(x.etf);
  let held = [];
  if (rows.some((x) => tk(x) === f.entity)) held = [f.entity];
  else if (f.entity === "today" || f.entity === "after") {
    const own = traceRow(r, id), recipe = str(obj(own && own.inputs) && own.inputs.recipe) || "";
    if (recipe.startsWith("evaluate.")) {
      const mix = obj(f.entity === "today" ? (obj(r.baseline) && r.baseline.portfolio) || r.portfolio : r.portfolio) || {};
      held = Object.keys(mix).filter((k) => isNum(mix[k]) && mix[k] > 0);
    }
  }
  const P = pf();
  return rows.filter((x) => held.includes(tk(x))).slice(0, 3).map((x) => {
    const url = str(x.source_url) || str(x.url) || str(x.source);
    let host = null;
    try { host = url ? new URL(url).hostname.replace(/^www\./, "") : null; } catch { host = null; }
    const gap = isNum(x.gap_pp) ? `${x.gap_pp < 0 ? MINUS : "+"}${Math.abs(x.gap_pp).toFixed(2)}${NB}pp` : null;
    return { ticker: tk(x), name: nameOf(tk(x)), period: str(x.period) || str(x.window), ours: pctText(x, x.ours, x.ours_text),
      published: pctText(x, isNum(x.published) ? x.published : x.issuer, x.published_text), gap, ok: typeof x.ok === "boolean" ? x.ok : null,
      readOn: str(x.read_on) && P.fmt ? P.fmt.date(x.read_on) || null : null, url: url && /^https?:\/\//.test(url) ? url : null, host };
  }).filter((x) => x.ours && x.published);
}

/* the answer of data.recompute (INTERFACES: {fact_id, value, match, delta, mock?}; the live route's {same, value, stored, text}) */
export function recomputeLine(ans, ctx) {
  ctx = obj(ctx) || {};
  if (ans === undefined) return null;
  if (ans === "pending") return { state: "pending", tone: "none", icon: "i-spin", word: "Recomputing", detail: null };
  const a = obj(ans) || {};
  if (str(a.error)) return { state: "error", tone: "none", icon: "i-pending", word: "Not recomputed", detail: str(a.error) };
  const match = a.match !== undefined ? a.match : a.same;
  const build = a.build === true || a.static === true || a.saved === true;
  const delta = isNum(a.delta) ? `Δ${NB}${(a.delta < 0 ? MINUS : "") + Math.abs(a.delta).toFixed(4)}` : null;
  const label = a.mock === true ? "A mock answer from the offline dev server"
    : build && typeof match === "boolean" ? `The check run when this saved run was built${ctx.recorded ? ` (recorded on ${ctx.recorded})` : ""}` : null;
  if (match === true) return { state: "match", tone: "inside", icon: "i-in", word: "Reproduced", detail: delta, label: label || str(a.how),
    text: str(a.text) || null };
  if (match === false) return { state: "mismatch", tone: "outside", icon: "i-out", word: "Mismatch", label,
    detail: [isNum(a.stored) ? `stored ${rawText(a.stored)}` : null, isNum(a.value) ? `recomputed ${rawText(a.value)}` : null, delta].filter(Boolean).join(", ") || null };
  return { state: "static", tone: "none", icon: "i-pending", word: "Not recomputed here", label,
    detail: "Recomputing runs the code again on the live server. This page is a saved run, so it shows the numbers as recorded." };
}

/* the sentence that cites a fact (the drawer's first node): null when the explanation does not cite it */
export function citedIn(r, id, at) {
  const e = explanation(r);
  const all = [...(e.lead ? [{ ...e.lead, i: "v", section: "verdict", title: "The verdict" }] : []), ...e.groups.flatMap((g) => g.sentences.map((s) => ({ ...s, title: g.title })))];
  const has = (s) => arr(s.segs).some((g) => (g.t === "num" || g.t === "ref") && arr(g.ids).includes(id));
  return all.find((s) => at !== undefined && at !== null && String(s.i) === String(at) && has(s)) || all.find(has) || null;
}

/* ---- "What the navigator changed in this run": the navigator's reading next to the keyword rules' (result.navigator_effect,
   proofs.navigator_effect). Null without it: the page hides the switch. ---- */
export function moveText(c) {
  c = obj(c);
  if (!c || !str(c.ticker)) return "No move";
  const P = pf(), w = isNum(c.weight) && P.fmt ? P.fmt.share(c.weight) : null, nm = nameOf(c.ticker);
  const from = str(c.from_ticker) ? ` from ${nameOf(c.from_ticker)}` : "";
  if (c.op === "add") return w ? `Add ${w} ${nm}${from}` : `Add ${nm}${from}`;
  return w ? `${nm} to ${w}${from}` : `${nm}${from}`;
}
export const familiesText = (fams) => { const f = arr(fams).filter((x) => FAMILIES[x]); return f.length ? f.map((x) => FAMILIES[x]).join(" and ") : "No shock named"; };
const verdictWord = (k) => { const P = pf(), V = P.VERDICT || {}; return k === null || k === undefined ? null : (V[k] && V[k].word) || null; };
function precedentList(r, ids) {
  const P = pf(), ev = new Map(arr(r.events).map(obj).filter(Boolean).map((e) => [e.event_id, e]));
  const curly = (t) => (t ? t.replace(/"([^"]*)"/g, "\u201c$1\u201d").replace(/'/g, "\u2019") : t);   // R18: typographic quotes on screen
  return arr(ids).map((id) => { const e = ev.get(id); return { id, title: e ? curly(str(e.title)) : null, date: e && P.fmt ? P.fmt.date(e.date) : null }; })
    .filter((x) => x.title);
}
export function navigatorPanel(r, evalDoc) {
  r = obj(r);
  const ne = obj(r && r.navigator_effect);
  if (!ne) return null;
  const sc = obj(r.scenario) || {}, fb = obj(ne.fallback) || {}, diffs = arr(ne.diffs).map(obj).filter(Boolean);
  const diff = (w) => diffs.find((d) => d.what === w) || null;
  const val = (w, navDefault, fbDefault) => { const d = diff(w); return d ? [d.navigator, d.fallback] : [navDefault, fbDefault]; };
  const rows = [];
  const [cn, cf] = val("change", sc.change, fb.change);
  rows.push({ what: "change", label: "The move", navigator: moveText(cn), keywords: moveText(cf), same: !diff("change") });
  const [fn, ff] = val("families", sc.families, fb.families);
  rows.push({ what: "families", label: "The shock", navigator: familiesText(fn), keywords: familiesText(ff), same: !diff("families") });
  const [pn, pk] = val("precedents", sc.event_ids, fb.event_ids);
  const ln = precedentList(r, pn), lk = precedentList(r, pk);
  const onlyN = ln.filter((x) => !arr(pk).includes(x.id)), onlyK = lk.filter((x) => !arr(pn).includes(x.id));
  rows.push({ what: "precedents", label: "Precedents picked", navigator: ln, keywords: lk, onlyNavigator: onlyN, onlyKeywords: onlyK, same: !diff("precedents") });
  if (diff("clarify")) {
    const c = diff("clarify");
    rows.push({ what: "clarify", label: "Asked back", navigator: c.navigator ? "Asked a question back" : "Read the question as asked",
      keywords: c.fallback ? "Asked a question back" : "Read the question as asked", same: false });
  }
  const vn = verdictWord(ne.verdict), otherMove = !!diff("change"), vk = otherMove ? null : verdictWord(ne.verdict_without);
  rows.push({ what: "verdict", label: "The verdict", navigator: vn || "Not known",
    keywords: otherMove ? "Not shown: the keyword rules read another move" : vk || "Not computed for this reading",
    same: vk ? !diff("verdict") : null, known: !!vk });
  const famSame = !diff("families");
  const tb = obj(r.turbulence) || {};
  const ADJ = { tariffs: "tariff war", war_oil: "war and oil", chips: "chip war", rates: "rate shock" };
  const counted = arr(fn).filter((f) => obj(tb[f]) && isNum(tb[f].n)).map((f) => ({ family: f, n: tb[f].n, adj: ADJ[f] || f }));
  const countLine = counted.length ? `The shock check counts all ${counted.map((c) => `${c.n} clean ${c.adj} episodes`).join(" and all ")} on record. `
    + "The lists above are the precedents each reading picked to tell the story; they never reach the checks." : null;
  return { same: ne.same === true || !diffs.length, rows, familiesSame: famSame, verdictSame: !diff("verdict"), counted, countLine,
    summary: summaryOf(rows), example: famSame ? evalExample(evalDoc, arr(sc.families)[0] || null) : null };
}

/* R8 / R10: when this run's question is read the same by both, one held-out evaluation case where the keyword rules read the
   wrong shock and the navigator the right one, labelled as the evaluation's (B5 writes docs/eval_results.json "examples") */
const famOf = (x) => { if (!x) return []; if (Array.isArray(x)) return x; const o = obj(x); return o ? arr(o.families || o.family && [o.family]) : typeof x === "string" ? [x] : []; };
/* the page's English rendering of the evaluation's French questions (red gate 9: what the page shows is in English; the French is
   quoted beside it, marked as French). Used only when the eval file carries no English text of its own (text_en). */
const EN = {
  hv2_fr01: "What if the United States puts tariffs again on everything that comes from Canada?",
  hv2_fr02: "What would happen if the Strait of Hormuz were blocked for several weeks?",
  hv2_fr03: "What if Washington bans chip exports to China completely?",
};
export function evalExample(doc, family) {
  const raw = obj(doc) && doc.examples;
  const ex = (Array.isArray(raw) ? raw : arr(obj(raw) && raw.ai_off_cases)).map(obj).filter(Boolean);
  const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
  const cands = [];
  for (const e of ex) {
    const q = str(e.question) || str(e.prompt) || str(e.text);
    const french = /french|fran[cç]ais/i.test(String(e.category || "")) || e.lang === "fr";
    const english = french ? str(e.text_en) || str(e.translation) || str(e.english) || EN[e.id] || null : q;
    const want = famOf(e.expected_families || (obj(e.expected) && e.expected.families) || e.expected);
    const nav = famOf(e.navigator_families || e.navigator_got || e.navigator || e.nav);
    const kw = famOf(e.keyword_families || e.keyword_got || e.fallback_families || e.keyword || e.keywords || e.fallback);
    if (!q || !english || !nav.length || same(nav, kw) || (want.length && !same(nav, want))) continue;
    cands.push({ question: q, lang: french ? "fr" : "en", english: french ? english : null, family: want[0] || nav[0],
      navigator: familiesText(nav), keywords: kw.length ? familiesText(kw) : "No shock named", expected: want.length ? familiesText(want) : null,
      category: str(e.category), id: str(e.id) });
  }
  const rank = (c) => (family && c.family === family ? 0 : 2) + (c.lang === "en" ? 0 : 1);   // the asked shock first, then English
  const best = cands.sort((a, b) => rank(a) - rank(b))[0];
  if (!best) return null;
  const P = pf(), v2 = obj(obj(doc).holdout_v2), day = (best.id && /^hv2_/.test(best.id) && v2 && str(v2.date)) || str(obj(doc).date);
  return { ...best, navigatorPhrase: famPhrase(best.navigator) || best.navigator, keywordsPhrase: famPhrase(best.keywords) || null,
    source: day ? `the blind held-out evaluation of ${P.fmt ? P.fmt.date(day) || day : day}` : "the blind held-out evaluation" };
}

/* "2021–26": the replay's own span, from the Result's first series date and its as_of (R1: "in this 2021–26 replay") */
export function replaySpan(r) {
  r = obj(r);
  const d0 = str(arr(obj(r && r.series) && r.series.dates)[0]), d1 = str(r && r.as_of);
  if (!d0 || !d1 || !/^\d{4}/.test(d0) || !/^\d{4}/.test(d1)) return null;
  return d0.slice(0, 4) === d1.slice(0, 4) ? d0.slice(0, 4) : `${d0.slice(0, 4)}\u2013${d1.slice(2, 4)}`;
}

/* the receipt's tape: every number the explanation uses, as verify.py matched it ({sentence, number, refs}; sentence 1 is the
   verdict, then the four questions in order, the receipt's own numbering), each mapped back to the fact its text cites */
const norm = (t) => String(t == null ? "" : t).replace(/[\s ]+/g, " ").trim();
export function receiptTape(r) {
  r = obj(r);
  const rc = obj(r && r.receipt), d = obj(r && r.debrief);
  if (!rc || !d) return [];
  const list = [str(d.verdict_sentence) ? { text: d.verdict_sentence } : null, ...ordered(d)];
  if (!list[0]) list.shift();
  const off = str(d.verdict_sentence) ? 1 : 0;
  const idOf = (k, number) => {
    const s = list[k - 1 + (off ? 0 : 0)];
    if (!s) return null;
    const hit = segments(s.text).find((g) => g.t === "num" && norm(g.text) === norm(number));
    return hit ? hit.id : null;
  };
  const at = (k) => { const s = list[k - 1]; return !s ? null : s.i === undefined ? "v" : s.i; };
  const row = (m, traced) => ({ number: nbsp(norm(m.number)), sentence: isNum(m.sentence) ? m.sentence : null,
    id: isNum(m.sentence) ? idOf(m.sentence, m.number) : null, at: isNum(m.sentence) ? at(m.sentence) : null, traced });
  return [...arr(rc.matches).map(obj).filter((m) => m && str(m.number)).map((m) => row(m, true)),
    ...arr(rc.unverified).map(obj).filter((m) => m && str(m.number)).map((m) => row(m, false))];
}

/* the panel's one code-written paragraph (no list joined by dots, R16): what both read alike, then what changed */
const FAM_PHRASE = { tariffs: "the tariff war", war_oil: "a war and oil shock", chips: "the chip war", rates: "a rate shock" };
const famPhrase = (label) => { const k = Object.keys(FAMILIES).find((x) => FAMILIES[x] === label); return k ? FAM_PHRASE[k] : null; };
export function summaryOf(rows) {
  const r = (w) => rows.find((x) => x.what === w), bits = [];
  const fam = r("families");
  if (fam && fam.same === false) {
    const n = famPhrase(fam.navigator), k = famPhrase(fam.keywords);
    bits.push(k ? `The keyword rules read ${k}; the navigator read ${n || fam.navigator.toLowerCase()}.`
      : `The keyword rules named no shock; the navigator read ${n || fam.navigator.toLowerCase()}.`);
  }
  const mv = r("change");
  if (mv && mv.same === false) bits.push(`The keyword rules read the move as ${mv.keywords.charAt(0).toLowerCase() + mv.keywords.slice(1)}; the navigator read ${mv.navigator.charAt(0).toLowerCase() + mv.navigator.slice(1)}.`);
  const vd = r("verdict");
  if (vd && vd.known && vd.same === false) bits.push(`Without the navigator, the verdict would have been “${vd.keywords}”.`);
  else if (vd && !vd.known && rows.some((x) => x.same === false && x.what !== "precedents")) bits.push("The verdict was not computed for the keyword rules’ reading, so the page does not guess it.");
  const pr = r("precedents");
  if (pr && pr.same === false) {
    if (pr.onlyNavigator.length) bits.push(`The navigator also picked the precedents marked here, which the keyword rules missed${pr.onlyKeywords.length ? "; the keyword rules picked others the navigator left out" : ""}.`);
    else if (pr.onlyKeywords.length) bits.push("The keyword rules picked precedents the navigator left out (marked here).");
  }
  const same = rows.filter((x) => x.same === true && x.what !== "precedents").map((x) => x.label.replace(/^The /, "the "));
  if (same.length) bits.push(`Both read ${same.length > 1 ? same.slice(0, -1).join(", ") + " and " + same[same.length - 1] : same[0]} the same way.`);
  return bits.join(" ");
}

/* the receipt's numbers for its disclosure: each traced fact once, in the order the explanation first uses it, written the way the
   page writes that fact (PF.factText), with its id; a number the receipt could not trace stays as written, marked */
export function receiptFacts(r) {
  const seen = new Set(), out = [];
  for (const x of receiptTape(r)) {
    if (x.traced && x.id) {
      if (seen.has(x.id)) continue;
      seen.add(x.id);
      const c = factCard(r, x.id);
      if (c && (c.valueText || c.raw)) out.push({ id: x.id, valueText: c.valueText || c.raw, label: c.label, marker: c.marker, at: x.at, traced: true });
    } else if (!x.traced) out.push({ id: null, valueText: x.number, label: null, marker: null, traced: false });
  }
  return out;
}

/* ---- lane clarity (ruling R22): ONE plain line on the AI's value, shown under the three sentences only when this run's
   navigator_effect shows a difference (the shock read, else the earlier episodes picked); words only, no figure ---- */
const COUNT_WORD = { 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six" };
export function aiValueLine(result, evalDoc) {
  const p = navigatorPanel(result, evalDoc);
  if (!p || !Array.isArray(p.rows)) return null;
  const shock = p.rows.find((r) => r.what === "families"), prec = p.rows.find((r) => r.what === "precedents");
  const named = (s) => typeof s === "string" && s.trim() && !/^no shock/i.test(s);
  const as = (s) => { const l = s.charAt(0).toLowerCase() + s.slice(1); return /(war|shock|crisis)$/.test(l) ? `the ${l}` : `the ${l} shock`; };
  if (shock && shock.same === false && named(shock.navigator)) {
    return named(shock.keywords)
      ? `The AI read your question as ${as(shock.navigator)}; keyword rules alone read ${as(shock.keywords)}.`
      : `The AI read your question as ${as(shock.navigator)}; a plain word search found no shock.`;
  }
  const only = prec && prec.same === false && Array.isArray(prec.onlyNavigator) ? prec.onlyNavigator.length : 0;
  if (only && shock && named(shock.navigator)) {
    return `The AI read ${as(shock.navigator)}, as the keyword rules did, and picked ${COUNT_WORD[only] || only} earlier ${only === 1 ? "episode" : "episodes"} they missed.`;
  }
  return null;
}

/* ---- G2 (traceability W24): Simple shows the explanation by the National Bank workshop's four questions, one sentence each
   (each group's first sentence, the debrief's own words), labelled as the workshop asks them ---- */
export const FOUR = Object.freeze({ data: "What data?", why: "Why this answer?", limits: "What limits?", would_change: "What would change it?" });
export function fourQuestions(e, result) {
  const code = codeAnswers(result);
  const own = (id, text, kind) => ({ i: `code-${id}`, section: id, kind, segs: [{ t: "text", text }],
    marker: kind === "fact" ? { icon: "m-fact", word: "fact" } : { icon: "m-assumption", word: "limit" }, by: "code" });
  return arr(e && e.groups).map((g) => {
    if (!g || !FOUR[g.id]) return null;
    if (g.id === "data" && code && code.data) return { id: g.id, q: FOUR[g.id], s: own("data", code.data, "fact") };        // written by code
    if (g.id === "limits" && code && code.limits) return { id: g.id, q: FOUR[g.id], s: own("limits", code.limits, "limit") };
    return arr(g.sentences).length ? { id: g.id, q: FOUR[g.id], s: g.sentences[0] } : null;
  }).filter(Boolean);
}

/* the design juror (81/100): "What data?" and "What limits?" get real answers, written by CODE from the run's own keys (the
   replay's first and last dates, the shocks on record, the funds' holdings snapshot) and the starter set's documented sources;
   never by the AI */
const SPAN_WORD = { 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten" };
export function codeAnswers(result) {
  const r = obj(result), P = globalThis.PF, f = P && P.fmt;
  if (!r || !f) return null;
  const dates = arr(obj(r.series) && r.series.dates), d0 = str(dates[0]), d1 = str(r.as_of) || str(dates[dates.length - 1]);
  const from = d0 ? f.date(d0) : null, to = d1 ? f.date(d1) : null, shocks = arr(r.events).length;
  const lt = obj(obj(r.lookthrough) && r.lookthrough.today);
  const snap = lt && lt.mode === "lookthrough" ? Object.values(obj(lt.snapshot) || {}).map(str).filter(Boolean).sort().pop() || null : null;
  const data = from && to ? `${[`Real daily prices from ${from} to ${to}, in Canadian dollars, dividends reinvested (the organizers’ starter set: Yahoo Finance, Bank of Canada, FRED)`,
    shocks ? `${shocks} sourced shocks` : null, snap ? `the funds’ published holdings dated ${f.date(snap)}` : null].filter(Boolean).join("; ")}.` : null;
  const y0 = d0 ? Number(d0.slice(0, 4)) : null, y1 = d1 ? Number(d1.slice(0, 4)) : null, span = y0 && y1 && y1 > y0 ? y1 - y0 : null;
  const limits = `${span ? `One ${SPAN_WORD[span] || span}-year market regime` : "One market regime"}; assets picked in ${y1 || "the year of the replay"}, so survivors only; no taxes or trading costs; it replays the past and is not a forecast.`;
  return { data, limits };
}

/* ---- R37 (agentic flaw hunter): the AI's honest value. Switching it off changes no verdict in these runs; it changes the question
   answered: the shock check without the AI replays every episode the keyword rules found (navigator_effect.checks_without) instead
   of the episodes of the shock you asked about. Every figure is the Result's own (the counts are the checks' own episode counts,
   or the number their code-written reason states); null when the two readings replay the same episodes ---- */
export function aiOffLine(result) {
  const r = obj(result), ne = obj(r && r.navigator_effect), P = globalThis.PF, f = P && P.fmt;
  if (!ne) return null;
  /* the ai lane's own sentence first (pipeline.ai_off_sentence); a sentence built on a missing count ("replays the None
     episodes", a double space) keeps only its first sentence, then code's own clause from the checks' counts when it has them */
  const said = str(ne.sentence), broken = said && /\bNone\b|\bnull\b|undefined|NaN|\s{2}/.test(said);
  const tail = f ? questionClause(r, ne, f) : null;
  if (said && !broken) return said;
  if (said && broken) {
    const first = (/^(.+?[.!?])(?=\s|$)/.exec(said) || [])[1];
    const ok = first && !/\bNone\b|\bnull\b|undefined|NaN|\s{2}/.test(first) ? first : null;
    return ok ? (tail ? `${ok} It changes the question answered: ${tail}` : ok) : null;
  }
  if (!tail) return null;
  const same = str(ne.verdict) && ne.verdict === ne.verdict_without;
  return `${same ? "Switching it off changes no verdict here; it changes the question answered" : "Switching it off changes the verdict here, and the question answered"}: ${tail}`;
}
/* "without it, the shock check replays all 26 episodes (worst −13.6 %) instead of the 6 tariff war episodes you asked about
   (worst −9.0 %)": the checks' own episode counts (n_episodes, else the number their code-written reason states); null when a
   count is missing or the two readings replay the same episodes */
function questionClause(r, ne, f) {
  const pick = (list) => arr(list).map(obj).find((c) => c && c.rule === "scenario_stress") || null;
  const withC = pick(r.checks), off = pick(ne.checks_without);
  if (!withC || !off || !isNum(withC.value) || !isNum(off.value)) return null;
  const n = (c) => (isNum(c.n_episodes) ? c.n_episodes : Number(((/\bIn the (\d+) separate\b/.exec(str(c.reason) || "")) || [])[1]) || null);
  const nOff = n(off), nOn = n(withC);
  if (!nOff || !nOn || nOff === nOn) return null;
  const fam = str(withC.family) ? withC.family.charAt(0).toLowerCase() + withC.family.slice(1) : "asked";
  return `without it, the shock check replays all ${nOff} episodes (worst ${f.pct(off.value)}) instead of the ${nOn} ${fam} episodes you asked about (worst ${f.pct(withC.value)}).`;
}
