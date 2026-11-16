/* EPICENTRE Replay, lane U7: pure helpers for #bar, #investors, #how and #footer. No DOM, no network. Reads globalThis.PF
   (web/lib.js: PF.view, PF.fmt) at call time, never at import time. Every number these return is a Result key, a key of
   docs/eval_results.json, or a count of a Result's own rows; a missing key gives null and the section hides that line.
   Copy rules: past tense for history, "in this <years> replay" under every verdict (R1), persona limits are assumptions
   (R13), saved runs say "Recorded on <date>" (R15), no "A · B · C" strings (R16), never buy / sell / hold. */

const NB = " ", MINUS = "−", DASH = "–", RSQ = "’";
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const pf = () => globalThis.PF;
const fmt = () => (pf() && pf().fmt) || null;
const plain = (s) => (typeof s === "string" ? s.replace(MINUS, "") : s);      // "−34.5 %" -> "34.5 %" (a fall said in words)
const lower1 = (s) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);

export const INVESTORS = ["robert", "mateo", "amira", "canadian"];
export const PERSONAS = new Set(["robert", "mateo", "amira"]);       // fictional investors whose limits are assumptions (R13)
export const PUBLIC_URL = "https://shmorsi.github.io/poly-datathon-2026/";
export const REPO_URL = "https://github.com/shmorsi/poly-datathon-2026";

/* ---- provenance (R15) ---- */
/* the years this replay covers, from the Result's own series dates: "2021–26" */
export function replayYears(r) {
  r = obj(r) || {};
  const s = obj(r.series), tp = obj(r.tipping_point), paths = tp && obj(tp.paths);
  const d = arr(s && s.dates).length ? s.dates : arr(paths && paths.dates);
  const a = str(d[0]), z = str(d[d.length - 1]);
  if (!a || !z || !/^\d{4}/.test(a) || !/^\d{4}/.test(z)) return null;
  return a.slice(0, 4) === z.slice(0, 4) ? a.slice(0, 4) : `${a.slice(0, 4)}${DASH}${z.slice(2, 4)}`;
}
export const qualifier = (r) => (replayYears(r) ? `in this ${replayYears(r)} replay` : "in this replay");

/* where a Result came from (R15). A saved run says when it was recorded: result.recorded_at (ISO 8601, Eastern time, stamped by
   scripts/record_demo.py), else the "recorded on 15 Nov 2026" that pipeline._as_replay writes into its message; with neither,
   null (the line is hidden). It reads as live only when the caller knows it just landed live (opts.live) and the Result says
   so: a saved run never reads as live, whatever its mode. */
export function provenance(r, opts) {
  r = obj(r);
  if (!r) return null;
  if (obj(opts) && opts.live === true && r.mode === "live") return { saved: false, date: null, time: null, text: "Run live in this session" };
  const F = fmt(), at = str(r.recorded_at);
  let date = at && F ? F.date(at) || null : null;
  const hm = at && /T(\d{2}):(\d{2})/.exec(at), zone = at && /(?:-0[45]:00)$/.test(at) ? " Eastern time" : "";
  const time = date && hm ? `${+hm[1]}:${hm[2]}${zone}` : null;
  if (!date) {
    const m = /recorded on (\d{1,2}[\s\u00a0][A-Z][a-z]{2}[\s\u00a0]\d{4})/.exec(String(r.message || ""));
    date = m ? m[1].replace(/^0/, "").replace(/\s/g, NB) : null;          // pipeline._as_replay writes %d: "05 Nov" reads "5 Nov"
  }
  return date ? { saved: true, date, time, text: `Recorded on ${date}` } : null;
}

/* "us.anthropic.claude-sonnet-5-5" -> "Claude Sonnet 5.5"; another Claude id -> "Claude"; anything else as given */
export function modelName(id) {
  const s = str(id);
  if (!s) return null;
  const m = /claude-([a-z]+)-(\d+)(?:-(\d+))?/i.exec(s);
  if (m) return `Claude ${m[1].charAt(0).toUpperCase()}${m[1].slice(1).toLowerCase()} ${m[2]}${m[3] ? "." + m[3] : ""}`;
  return /claude/i.test(s) ? "Claude" : s;
}

/* one model call's tokens: Converse names or the short ones; cached = read from the prompt cache */
export function tokensOf(usage) {
  const u = obj(usage);
  if (!u) return null;
  const n = (...keys) => { for (const k of keys) if (isNum(u[k])) return u[k]; return null; };
  const input = n("inputTokens", "input"), output = n("outputTokens", "output");
  if (input === null && output === null) return null;
  return { input: input || 0, output: output || 0, total: (input || 0) + (output || 0), cached: n("cacheReadInputTokens", "cache_read") || 0 };
}

export const shortId = (id) => (str(id) ? str(id).replace(/[^0-9a-z]/gi, "").slice(0, 8).toLowerCase() : null);
export const count = (n) => (isNum(n) ? Math.round(n).toLocaleString("en-CA") : "");

/* a duration as the trace measured it: "869 ms", "2.7 s", "12 s" */
export function msText(ms) {
  if (!isNum(ms) || ms < 0) return null;
  if (ms < 1000) return `${Math.round(ms)}${NB}ms`;
  const s = ms / 1000;
  return `${s < 10 ? s.toFixed(1) : Math.round(s).toLocaleString("en-CA")}${NB}s`;
}

/* ---- the Wilson score interval, the formula of scripts/eval.py (z = 1.96) ---- */
export function wilson(k, n, z = 1.96) {
  if (!isNum(k) || !isNum(n) || n <= 0 || k < 0 || k > n) return null;
  const p = k / n, z2 = z * z;
  const centre = (p + z2 / (2 * n)) / (1 + z2 / n);
  const half = (z * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / (1 + z2 / n);
  return { lo: Math.max(0, centre - half), hi: Math.min(1, centre + half) };
}
const pct1 = (x) => (isNum(x) ? (Math.round(x * 1000) / 10).toFixed(1) : null);
export const intervalText = (lo, hi) => (isNum(lo) && isNum(hi) ? `${pct1(lo)}${DASH}${pct1(hi)}${NB}%` : null);

/* ---- #investors: one ledger row per saved run (R14: each answer names the check that decided it) ---- */
/* the fall against the % rule (R35, the controller 17:41): "At its worst the mix fell 34.5 % from a high, past your 15 % rule."
   The floor is the % rule; it is never priced in the capacity's dollars, and no fall is "the same fall on your $600,000" */
function floorSentence(v) {
  const F = fmt(), fall = (v.move ? v.fall.after : v.fall.today) || null, his = "your";      // R18: the instrument says "your"
  if (!F || !fall || !fall.ddText) return null;
  const rule = v.floor && v.floor.text ? plain(v.floor.text).replace(/\.0(?=\u00a0%)/, "") : null;
  const past = rule && isNum(fall.dd) && isNum(v.floor.v) ? (fall.dd < v.floor.v ? "past" : "inside") : null;
  return `At its worst the mix fell ${plain(fall.ddText)} from a high${rule && past ? `, ${past} ${his} ${rule} rule` : ""}.`;
}
function shareSentence(c, what, his) {
  const F = fmt();
  if (!F || !isNum(c.value)) return null;
  const lim = isNum(c.limit) ? `, against ${his} limit of ${F.share(c.limit)}` : "";
  return `${what} ${F.share(c.value)} of the money${lim}.`;
}
/* Canada's share of the money (look-through, today's holdings) and of the risk (2021-26 daily returns), before and after */
export function canadaShare(r) {
  const d = obj(obj(r) && r.diversification), t = d && obj(d.today), a = d && obj(d.after);
  const money = (s) => (s && obj(s.countries) && isNum(s.countries.CAN) ? s.countries.CAN : null);
  const risk = (s) => (s && isNum(s.can_risk_share) ? s.can_risk_share : null);
  if (!t || !a || money(t) === null || money(a) === null) return null;
  return { money: [money(t), money(a)], risk: risk(t) !== null && risk(a) !== null ? [risk(t), risk(a)] : null };
}
export function decidedBy(r, v) {
  const F = fmt();
  if (!F || !v) return null;
  const his = "your", rows = arr(v.rows), first = rows[0] || null;                         // R18: one voice, second person
  const check = (rule) => arr(obj(r) && r.checks).find((c) => obj(c) && c.rule === rule) || null;
  if (first && first.status === "fail") {
    const c = check(first.rule) || {};
    switch (first.rule) {
      case "max_drawdown": return { rule: first.rule, name: `${his} floor`, sentence: floorSentence(v) };
      case "esg_direct": return { rule: first.rule, name: `${his} values`, sentence: shareSentence(c, `A company ${his} values screen excludes is held directly:`, his) };
      case "esg_indirect": return { rule: first.rule, name: `${his} values`, sentence: shareSentence(c, `Companies ${his} values screen excludes are, inside ${his} funds,`, his) };
      case "crypto": return { rule: first.rule, name: "the crypto share", sentence: shareSentence(c, "Crypto is", his) };
      case "single_stock": return { rule: first.rule, name: "one company" + RSQ + "s share", sentence: shareSentence(c, "One company is", his) };
      case "sector": return { rule: first.rule, name: "one sector" + RSQ + "s share", sentence: shareSentence(c, "One sector is", his) };
      default: return { rule: first.rule, name: lower1(first.name), sentence: first.compare ? `${first.compare}.` : null };
    }
  }
  const ca = canadaShare(r);
  if (ca && v.move) {
    const risk = ca.risk ? `, and in this replay it carried ${F.pct(ca.risk[1])} of the risk instead of ${F.pct(ca.risk[0])}` : "";   // R1: the risk share is history
    return { rule: "canada", name: "Canada" + RSQ + "s share", canada: ca,
      sentence: `With ${v.move.name} at ${v.move.weightText}, Canada${RSQ}s share of the money goes from ${F.pct(ca.money[0])} to ${F.pct(ca.money[1])}${risk}.` };
  }
  if (first) return { rule: first.rule, name: lower1(first.name), sentence: first.compare ? `${first.compare}.` : null };
  return null;
}

/* the row: who, their words, the asked shock and move, the answer with its qualifier, the deciding check, the provenance */
export function ledgerRow(r, id) {
  const P = pf();
  if (!P || !obj(r) || typeof P.view !== "function") return null;
  const v = P.view(r);
  if (!v || v.stop || !v.verdict) return null;
  const pid = str(id) || str(r.pilot) || null, persona = PERSONAS.has(pid);
  const age = isNum(v.who.age) ? v.who.age : null;
  const limits = obj(r.limits) || {};
  return {
    id: pid, name: v.who.name || null, persona, kicker: persona ? null : "The workshop" + RSQ + "s question",   // under the name
    meta: age !== null && v.amountText ? `${age}, with ${v.amountText}` : v.amountText,
    question: v.question, family: v.shockFamily, move: v.move ? v.move.readAs : null,
    verdict: { word: v.verdict.word, tone: v.verdict.tone, icon: v.verdict.icon },
    qualifier: qualifier(r),
    without: v.move && v.today ? `Without the move: ${lower1(v.today.word)}.` : null,
    decided: decidedBy(r, v),
    decidedLabel: v.verdict.tone === "outside" ? "Decided by" : v.verdict.tone === "caveat" ? "The check that added the caveat:" : "The check that answers it:",
    assumed: persona && !arr(limits.edited).includes("floor"),
    recorded: provenance(r),
  };
}

/* ---- #how: this run as nine nodes, each with the trace's own numbers ---- */
/* R19 (a): the first four steps are National Bank's workshop method (Appendix C, slides 13-14); Verify is the one we added */
export const STEPS = [
  { id: "OBSERVE", label: "Observe" }, { id: "UNDERSTAND", label: "Understand" }, { id: "COMPARE", label: "Compare" },
  { id: "EXPLAIN", label: "Explain" }, { id: "VERIFY", label: "Verify", ours: true },
];
export const METHOD = "Observe, Understand, Compare, Explain: the method National Bank" + RSQ + "s workshop taught. We added one step: Verify.";
export const KINDS = {
  you: { label: "You", glyph: "ring" },
  guard: { label: "Bedrock Guardrails", glyph: "diamond" },
  model: { label: "Amazon Bedrock", glyph: "disc" },
  code: { label: "Python code", glyph: "square" },
};
/* where each station's output is shown on the page (the diagram doubles as a map into the evidence); links only to sections present */
export const STATION_LINKS = { question: ["hero", "the question"], navigator: ["replay", "the reading on the replay"], checks: ["checklist", "the checks"],
  explain: ["why", "the explanation"], receipt: ["why", "the number check under the explanation"], you: ["record", "the decision record"] };
/* the checklist's own words for a check (lane U5b, web/lib/money.js shownStatus): only a hard limit that broke reads "Outside";
   a soft limit or a preference that broke, and any warning, read "Caution"; a pass reads "Inside". #how passes U5b's function
   itself (flowOf opts.shown); this exact mirror is the fallback, and a node test pins the two to agree on the four fixtures */
export function shownMirror(status, tier) {
  if (status === "fail") return tier === "hard" ? { word: "Outside", tone: "outside", icon: "i-out" } : { word: "Caution", tone: "caveat", icon: "i-warn" };
  if (status === "warn") return { word: "Caution", tone: "caveat", icon: "i-warn" };
  if (status === "pass") return { word: "Inside", tone: "inside", icon: "i-in" };
  return null;
}
const isRecipe = (t) => !!(obj(t.inputs) && Object.prototype.hasOwnProperty.call(t.inputs, "recipe"));
const sumMs = (list) => (list.length && list.some((t) => isNum(t.ms)) ? list.reduce((s, t) => s + (isNum(t.ms) ? t.ms : 0), 0) : null);
const sumTokens = (list) => {
  const all = list.map((t) => tokensOf(t.usage)).filter(Boolean);
  return all.length ? all.reduce((s, u) => ({ input: s.input + u.input, output: s.output + u.output, total: s.total + u.total,
    cached: s.cached + u.cached }), { input: 0, output: 0, total: 0, cached: 0 }) : null;
};
const firstId = (list, g) => str((list.find((t) => str(t.request_id)) || {}).request_id) || str(obj(g) && g.request_id);

export function flowOf(r, opts) {
  r = obj(r);
  const P = pf();
  if (!r || !P) return null;
  const v = P.view(r), his = "your";                                                        // R18
  const calls = arr(r.trace).map(obj).filter((t) => t && !isRecipe(t) && str(t.tool));
  if (!calls.length) return null;
  const tool = (re) => calls.filter((t) => re.test(t.tool));
  const gIn = obj(obj(r.guardrail) && r.guardrail.input), gOut = obj(obj(r.guardrail) && r.guardrail.output);
  const scen = obj(r.scenario) || {}, rc = obj(r.receipt), checks = arr(r.checks).map(obj).filter(Boolean);
  const ran = new Set(arr(r.trace).map(obj).filter(Boolean).map((t) => t.step));
  const nodes = [];
  /* a station whose step never ran (a blocked question, a run that stopped) says so, never a state it did not reach */
  const add = (n) => nodes.push(n.step && !ran.has(n.step) && n.kind !== "you"
    ? { ms: null, tokens: null, requestId: null, model: null, tone: null, lines: [], ...n, notRun: true, outcome: "Not run", ms: null, tokens: null, requestId: null, grounding: null }
    : { ms: null, tokens: null, requestId: null, model: null, outcome: null, tone: null, lines: [], ...n });

  const asked = PERSONAS.has(str(r.pilot)) && v && v.who.name ? `In ${v.who.name}${RSQ}s words`
    : str(r.pilot) === "canadian" ? "As the workshop asked it" : "In the investor" + RSQ + "s words";
  add({ id: "question", kind: "you", step: "OBSERVE", name: "The question", lines: [asked] });

  const gi = tool(/apply_guardrail\(INPUT\)|^guardrail\.input/);
  const inOutcome = !gi.length && !gIn ? null : gIn && gIn.error ? ["Could not run", "caveat"] : gIn && gIn.blocked ? ["Blocked", "outside"] : ["Not blocked", "inside"];
  add({ id: "guard_in", kind: "guard", step: "OBSERVE", name: "Input guardrail", ms: sumMs(gi), requestId: firstId(gi, gIn),
    outcome: inOutcome && inOutcome[0], tone: inOutcome && inOutcome[1], absent: !gi.length && !gIn });

  const turns = tool(/^navigator\.model_turn$/), navTools = calls.filter((t) => /^navigator\./.test(t.tool) && t.tool !== "navigator.model_turn");
  const read = [v && v.shockFamily, v && v.move ? v.move.readAs : null].filter(Boolean);
  add({ id: "navigator", kind: turns.length ? "model" : "code", step: "UNDERSTAND", name: "AI reader", ms: sumMs(turns), tokens: sumTokens(turns),
    requestId: firstId(turns), model: modelName((turns.find((t) => str(t.model)) || {}).model),
    outcome: turns.length ? null : "Keyword rules, no model", lines: read, tools: navTools.length, turns: turns.length });

  const compute = calls.filter((t) => t.step === "COMPARE" && t.service === "Python" && t.tool !== "governance.evaluate" && !/^ui\./.test(t.tool));
  add({ id: "compute", kind: "code", step: "COMPARE", name: "Code computes", ms: sumMs(compute),
    lines: compute.length ? [`${count(compute.length)} tool calls`] : [] });

  const evals = tool(/^governance\.evaluate$/);
  const shown = obj(opts) && typeof opts.shown === "function" ? opts.shown : shownMirror;   // the checklist's words, so both pages agree
  const tally = (w) => checks.filter((c) => (shown(c.status, c.tier) || {}).word === w).length;
  const outN = tally("Outside"), cauN = tally("Caution"), inN = tally("Inside");
  add({ id: "checks", kind: "code", step: "COMPARE", name: "Checks", ms: sumMs(evals),
    lines: checks.length ? [`${count(checks.length)} on ${his} limits`,
      [outN ? `${count(outN)} outside` : null, cauN ? `${count(cauN)} caution` : null, inN ? `${count(inN)} inside` : null].filter(Boolean).join(", ")] : [],
    outcome: v && v.verdict ? v.verdict.word : null, tone: v && v.verdict ? v.verdict.tone : null, icon: v && v.verdict ? v.verdict.icon : null });

  const drafts = tool(/^explain\.draft$/), withheld = r.debrief === null && !!drafts.length;
  add({ id: "explain", kind: drafts.length ? "model" : "code", step: "EXPLAIN", name: "Explanation", ms: sumMs(drafts), tokens: sumTokens(drafts),
    requestId: firstId(drafts), model: modelName((drafts.find((t) => str(t.model)) || {}).model),
    outcome: !drafts.length ? "Off in this run" : withheld ? "Withheld" : null, tone: withheld ? "caveat" : null,
    lines: drafts.length > 1 ? [`${count(drafts.length)} drafts`] : drafts.length ? ["One draft"] : [] });

  const ver = tool(/^verify\.receipt$/);
  const traced = rc && isNum(rc.verified) && isNum(rc.total) ? `${count(rc.verified)} of ${count(rc.total)} numbers traced` : null;
  add({ id: "receipt", kind: "code", step: "VERIFY", name: "Number check", ms: sumMs(ver), lines: traced ? [traced] : [],
    outcome: rc ? (arr(rc.defects).length ? "Defects left" : "Clean") : null, tone: rc ? (arr(rc.defects).length ? "caveat" : "inside") : null });

  const go = tool(/^guardrail\.output$/), gr = gOut && obj(gOut.grounding);
  const outOutcome = !go.length && !gOut ? null : gOut && gOut.error ? ["Could not run", "caveat"] : gOut && gOut.topic_hit ? ["Advice found", "outside"] : ["No advice found", "inside"];
  add({ id: "guard_out", kind: "guard", step: "VERIFY", name: "Output guardrail", ms: sumMs(go), requestId: firstId(go, gOut),
    outcome: outOutcome && outOutcome[0], tone: outOutcome && outOutcome[1], absent: !go.length && !gOut,
    grounding: gr && isNum(gr.score) ? { score: gr.score, threshold: isNum(gr.threshold) ? gr.threshold : null } : null });

  add({ id: "you", kind: "you", step: null, name: "You", lines: ["The answer, with every number" + RSQ + "s trace"] });

  const bedrock = turns.length + drafts.length, guards = gi.length + go.length;
  return { nodes, bedrock, guards, method: str(scen.method), provenance: provenance(r, opts), question: str(r.question), who: v ? v.who : null };
}

/* ---- the AWS services, one plain job each (docs/aws.md, "Each service's one job"): the two this run called, with the run's
   own counts, then the five around the live app ---- */
export function servicesOf(flow) {
  const f = obj(flow) || {};
  const n = (k, one, many) => (isNum(f[k]) && f[k] > 0 ? (f[k] === 1 ? one : `${count(f[k])} ${many}`) : null);
  return [
    { id: "bedrock", group: "run", name: "Amazon Bedrock", job: "Runs Claude for the two language jobs: reading the question and writing the explanation. It never computes a number.",
      run: n("bedrock", "One call in this run", "calls in this run") },
    { id: "guardrails", group: "run", name: "Amazon Bedrock Guardrails", job: "Screens the question before any model sees it, and scores the explanation on its way out.",
      run: n("guards", "One check in this run", "checks in this run") },
    { id: "ec2", group: "app", name: "Amazon EC2", job: "Runs the app" + RSQ + "s Python code, which computes every number." },
    { id: "cloudfront", group: "app", name: "Amazon CloudFront", job: "Serves the live app over HTTPS." },
    { id: "iam", group: "app", name: "AWS IAM", job: "Keeps the app" + RSQ + "s role to those calls and to writing a tamper-proof record." },
    { id: "s3", group: "app", name: "Amazon S3", job: "The record vault: keeps a tamper-proof record (SHA-256) only when you ask it to, private, versioned and locked." },
    { id: "cloudwatch", group: "app", name: "Amazon CloudWatch", job: "The dashboard: the calls as counts and latencies, never their content." },
  ];
}
export const SERVICE_GROUPS = [{ id: "run", label: "Called by this run" }, { id: "app", label: "Around the live app" }];

/* ---- the eval card: docs/eval_results.json (published as web/eval_results.json). The blind held-out set leads; the
   development set is labelled as such. Intervals are the file's own when it has them, else Wilson from its k and N. ---- */
function armOf(id, label, engine, k, n, lo, hi) {
  if (!isNum(k) || !isNum(n) || n <= 0) return null;
  const w = isNum(lo) && isNum(hi) ? { lo, hi } : wilson(k, n);
  return { id, label, engine, k, n, rate: k / n, lo: w ? w.lo : null, hi: w ? w.hi : null, interval: w ? intervalText(w.lo, w.hi) : null };
}
const CATEGORY = { french: "In French", paraphrase: "Paraphrases" };
const pair = (x) => (Array.isArray(x) && x.length === 2 && isNum(x[0]) && isNum(x[1]) ? x : [null, null]);
export function evalOf(j) {
  j = obj(j);
  if (!j) return null;
  const model = modelName(j.model);
  const h = obj(j.holdout_v2), sum = h && obj(h.summary);
  const nav = sum && obj(sum.navigator), kw = sum && obj(sum.keyword);
  const engine = h && (modelName(h.model) || model);
  let heldout = null;
  if (h && isNum(h.n)) {
    const nf = pair(h.navigator_families_wilson), kf = pair(h.keyword_families_wilson);
    const nw = pair(h.navigator_whole_wilson), kw2 = pair(h.keyword_whole_wilson);
    const first = obj(h.first_pass);
    heldout = {
      n: h.n, date: str(h.date), sha: str(h.sha256), model: engine,
      arms: [   /* the shock read right (families): the file's own interval when it has one */
        armOf("navigator", "The AI reader", engine, isNum(h.navigator_k) ? h.navigator_k : nav && nav.k, h.n, nf[0] ?? (nav && nav.wilson_low), nf[1] ?? (nav && nav.wilson_high)),
        armOf("keyword", "Keyword rules", "no model", isNum(h.keyword_k) ? h.keyword_k : kw && kw.k, h.n, kf[0] ?? (kw && kw.wilson_low), kf[1] ?? (kw && kw.wilson_high)),
      ].filter(Boolean),
      whole: isNum(h.navigator_whole_k) && isNum(h.keyword_whole_k) ? [   /* the whole reading: shock, precedents, move, question type */
        armOf("navigator", "The AI reader", engine, h.navigator_whole_k, h.n, nw[0], nw[1]),
        armOf("keyword", "Keyword rules", "no model", h.keyword_whole_k, h.n, kw2[0], kw2[1]),
      ].filter(Boolean) : [],
      firstPass: first && isNum(first.navigator_k) ? { navigator: first.navigator_k, keyword: isNum(first.keyword_k) ? first.keyword_k : null } : null,
      categories: Object.keys(CATEGORY).map((id) => {
        const c = obj(obj(h.by_category) && h.by_category[id]), cn = c && obj(c.navigator), ck = c && obj(c.keyword);
        return c && isNum(c.n) && cn && ck && isNum(cn.k) && isNum(ck.k) ? { id, label: CATEGORY[id], n: c.n, navigator: cn.k, keyword: ck.k } : null;
      }).filter(Boolean),
    };
  }
  const dev = arr(j.arms).map(obj).filter(Boolean);
  const devArm = (name) => dev.find((x) => x.arm === name && isNum(x.k) && isNum(x.n));
  const dn = devArm("navigator"), dk = devArm("keyword_fallback");
  const development = dn && dk ? { n: dn.n, date: str(j.date), navigator: armOf("navigator", "The AI reader", model, dn.k, dn.n, dn.lo, dn.hi),
    keyword: armOf("keyword", "Keyword rules", "no model", dk.k, dk.n, dk.lo, dk.hi) } : null;
  if (!heldout && !development) return null;
  return { heldout: heldout && heldout.arms.length ? heldout : null, development, model, modelId: str(j.model) };
}

/* ---- R12, checked against the outside world: result.reconciliation ({rows, n, within, tolerance_pp} from B3, or a plain
   list of rows); ours and published are fractions with their own texts. ISO dates in the period read as dates. ---- */
export function reconciliationOf(r) {
  const rec = obj(r) ? r.reconciliation : null, F = fmt();
  const box = obj(rec), rows = arr(box ? box.rows : rec).map(obj).filter(Boolean);
  if (!rows.length || !F) return null;
  const pp = (x) => (isNum(x) ? `${x < 0 ? MINUS : ""}${Math.abs(x * 100).toFixed(2)}${NB}%` : null);
  const day = (s) => String(s || "").replace(/\d{4}-\d{2}-\d{2}/g, (d) => F.date(d) || d);
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch (e) { return null; } };
  const out = rows.map((x) => {
    const url = str(x.source_url) || str(x.url);
    const ours = str(x.ours_text) ? x.ours_text.replace(/ %/g, NB + "%") : pp(x.ours), pub = str(x.published_text) ? x.published_text.replace(/ %/g, NB + "%") : pp(x.published);
    const gap = isNum(x.gap_pp) ? `${x.gap_pp < 0 ? MINUS : x.gap_pp > 0 ? "+" : ""}${Math.abs(x.gap_pp).toFixed(2)}` : null;
    return { ticker: str(x.ticker) || str(x.etf), period: day(str(x.period) || str(x.window)), basis: str(x.basis), ours, published: pub, gap,
      ok: typeof x.ok === "boolean" ? x.ok : null, url: url && /^https:\/\//.test(url) ? url : null, host: url ? host(url) : null };
  }).filter((x) => x.ticker && x.ours && x.published);
  if (!out.length) return null;
  const n = box && isNum(box.n) ? box.n : out.length;
  const within = box && isNum(box.within) ? box.within : null, tol = box && isNum(box.tolerance_pp) ? box.tolerance_pp : null;
  return { rows: out, n, funds: new Set(out.map((x) => x.ticker)).size, within, tolerance: tol, source: box ? str(box.source) : null };
}

/* ---- after first paint: fn runs once, when the browser is idle or `el` comes within a viewport or two, whichever is first
   (the hero's textures and the first run go first; a capture that never scrolls still gets it on idle) ---- */
export function whenNear(el, fn, timeout = 2500) {
  let done = false, io = null;
  const go = () => { if (done) return; done = true; if (io) io.disconnect(); fn(); };
  const g = globalThis;
  if (typeof g.requestIdleCallback === "function") g.requestIdleCallback(go, { timeout });
  else setTimeout(go, Math.min(timeout, 1200));
  if (el && typeof g.IntersectionObserver === "function") {
    io = new g.IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) go(); }, { rootMargin: "150% 0px 150% 0px" });
    io.observe(el);
  }
  return go;
}

/* ---- #bar ---- */
export const NAV = [
  { id: "replay", label: "Replay" }, { id: "deep", label: "Not just 2022" }, { id: "investors", label: "Investors" },
  { id: "how", label: "How it works" }, { id: "record", label: "Record" },
];
export const dataTo = (r) => { const F = fmt(), d = obj(r) && str(r.as_of); return F && d && F.date(d) ? `Data to ${F.date(d)}` : null; };
export const dataToShort = (r) => { const F = fmt(), d = obj(r) && str(r.as_of); return F && d && F.date(d) ? `To ${F.date(d)}` : null; };   // phones

/* ---- #footer ---- */
/* the dark modules of a QR matrix as one SVG path, a run of dark cells per row ("M x y h n v 1 h -n z"), offset by the quiet zone */
export function qrPath(isDark, size, quiet = 0) {
  if (typeof isDark !== "function" || !isNum(size) || size <= 0) return "";
  let d = "";
  for (let y = 0; y < size; y += 1) {
    let x = 0;
    while (x < size) {
      if (!isDark(y, x)) { x += 1; continue; }
      let e = x;
      while (e < size && isDark(y, e)) e += 1;
      d += `M${x + quiet} ${y + quiet}h${e - x}v1h${x - e}z`;
      x = e;
    }
  }
  return d;
}
/* the URL a scan opens: one constant, window.EPI_PUBLIC_URL, else the public static demo (R8: never a live endpoint) */
export function publicUrl(given) {
  const u = str(given);
  return u && /^https:\/\/[^\s"'<>]+$/.test(u) ? u : PUBLIC_URL;
}
export const bareUrl = (u) => String(u || "").replace(/^https?:\/\//, "").replace(/\/$/, "");

/* the limits of the replay, dated from the Result where a date is involved; `kind` names the marker beside a line */
export function limitsOf(r) {
  const F = fmt(), s = obj(obj(r) && r.series), d = arr(s && s.dates), asOf = obj(r) && str(r.as_of);
  const from = F && d.length ? F.date(d[0]) : null, to = F && asOf ? F.date(asOf) : null;
  const out = [{ text: "This already happened; it is not a forecast.", kind: "fact", lead: true }];
  if (from && to) out.push({ text: `Daily prices from ${from} to ${to}, on assets chosen in ${asOf.slice(0, 4)}: the replay already knows which companies survived.`, kind: "fact" });
  if (obj(r) && obj(r.deep_history) && d.length) out.push({ text: `Crises before ${String(d[0]).slice(0, 4)} are replayed month by month with similar indexes in place of today${RSQ}s funds: an assumption, never part of a verdict.`, kind: "assumption" });
  out.push({ text: "Nominal Canadian dollars, with no adjustment for inflation.", kind: "fact" });
  out.push({ text: "No taxes, no fees, and no other accounts are counted.", kind: "fact" });
  out.push({ text: "The investors and their amounts are fictional; their limits are assumptions set for these profiles.", kind: "fiction" });
  out.push({ text: "These profiles’ limits are assumed from each profile; on the live app you can type your own.", kind: "fact",
    link: { href: "#checklist", text: "Edit your limits in the checklist (live app)." } });
  return out;
}
/* ---- the record of sources (audit item 7): every shock on record and every earlier crisis, each with its own source link ---- */
/* R18 on display: the catalog's straight quotes and apostrophes read as typographic ones ("Liberation Day" -> “Liberation Day”) */
export const typo = (t) => (typeof t === "string" ? t.replace(/(^|[\s(\[])"/g, "$1\u201c").replace(/"/g, "\u201d").replace(/'/g, RSQ) : t);
const linkOf = (u) => {
  const url = str(u);
  if (!url || !/^https?:\/\/[^\s"'<>]+$/.test(url)) return null;
  let host = null;
  try { host = new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return null; }
  return { url, host };
};
export function shocksRecord(r) {
  const P = pf(), F = fmt();
  if (!obj(r) || !P || !F) return null;
  const v = P.view(r), label = new Map(arr(v && v.shocks && v.shocks.events).map((e) => [e.id, e.familyLabel]));
  const rows = arr(r.events).map(obj).filter((e) => e && str(e.date) && /^\d{4}-\d{2}-\d{2}/.test(e.date) && str(e.title))
    .map((e) => { const id = str(e.event_id) || e.date, l = linkOf(e.source_url);
      return { id, date: e.date.slice(0, 10), dateText: F.date(e.date), title: typo(str(e.title)), place: typo(str(e.place)), family: label.get(id) || null,
        url: l && l.url, host: l && l.host }; })
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  return rows.length ? rows : null;
}
export function crisesRecord(r) {
  const dh = obj(obj(r) && r.deep_history);
  const rows = arr(dh && dh.episodes).map(obj).filter((e) => e && str(e.title)).map((e) => {
    const a = (str(e.start) || "").slice(0, 4), z = (str(e.end) || "").slice(0, 4), l = linkOf(e.source_url);
    return { id: str(e.id) || e.title, title: typo(str(e.title)), years: a && z ? (a === z ? a : `${a}${DASH}${z}`) : a || z || null,
      place: typo(str(e.place)), url: l && l.url, host: l && l.host, sourceTitle: typo(str(e.source_title)) };
  });
  return rows.length ? rows : null;
}

/* the values screen's sources, as data/esg_flags.csv cites them (docs/finance_methods.md section 6): Vanguard's published ESGV
   methodology for the exclusion categories, and each company's own annual filing for a controversy, read on its investor site */
export const VALUES_SOURCES = [
  { label: "ESGV methodology", url: "https://investor.vanguard.com/investment-products/etfs/profile/esgv" },
  { label: "CNR.TO annual report", url: "https://www.cn.ca/-/media/files/investors/investor-annual-report/2025-cn-annual-report.pdf" },
  { label: "ENB.TO Form 10-K", url: "https://www.enbridge.com/~/media/43387962F0B04032A6B64E005CCA59D9.ashx" },
  { label: "JNJ Form 10-K", url: "https://d18rn0p25nwr6d.cloudfront.net/CIK-0000200406/e09b8882-48b1-4fea-a818-66acddf84c4f.pdf" },
  { label: "PG Form 10-K", url: "https://d18rn0p25nwr6d.cloudfront.net/CIK-0000080424/274693a2-3e60-4e9f-a89b-2db88249cbad.pdf" },
  { label: "XOM Form 10-K", url: "https://investor.exxonmobil.com/sec-filings/all-sec-filings/content/0000034088-26-000045/xom-20251231.htm" },
];

export function sourcesOf(r) {
  const n = arr(obj(r) && r.events).length;
  return [
    { name: "Yahoo Finance", via: "through the organizers" + RSQ + " starter set", use: "Daily prices and dividends.", licence: "Used under Yahoo" + RSQ + "s terms and never redistributed." },
    { name: "Bank of Canada", use: "The US dollar exchange rate and the policy rate.", licence: "Under the Bank of Canada" + RSQ + "s terms." },
    { name: "FRED", via: "Federal Reserve Bank of St. Louis", use: "The US dollar rate for the earlier crises.", licence: "Public domain, citation requested." },
    { name: "Kenneth French Data Library", use: "US market and industry returns for the earlier crises.", licence: "No licence stated, so the raw files stay local." },
    { name: "Statistics Canada", via: "tables 10-10-0122-01 and 10-10-0125-01", use: "Canadian series for the earlier crises.", licence: "Statistics Canada Open Licence." },
    { name: "World Bank", via: "Pink Sheet", use: "The gold price for the earlier crises.", licence: "CC BY 4.0." },
    { name: "ETF issuers", via: "their own pages and files", use: "What each fund holds.", licence: "Their terms forbid redistribution, so the holdings stay local." },
    { name: "The values screen", via: "Vanguard" + RSQ + "s published ESGV methodology and the companies" + RSQ + " own annual filings",
      use: "The exclusion categories, and each controversy in the filing that discloses it, read on the company" + RSQ + "s investor site.",
      licence: "Cited, with one short quotation per controversy.", links: VALUES_SOURCES },
    { name: "NASA Earth Observatory", via: "Black Marble 2016, from the VIIRS sensor of the Suomi NPP satellite", use: "The night Earth on the globe, its city lights.",
      licence: "Public domain imagery, credited; NASA does not endorse this project." },
    { name: "The shocks", use: n ? `${count(n)} team-written summaries of public announcements, one source link each.` : "Team-written summaries of public announcements, one source link each.", licence: "Our own work." },
  ];
}

/* ---- lane clarity (pre-freeze 2): the AI's measured value in one sentence, from the same blind held-out measure the stage's
   AI line reads (web/eval_results.json holdout_v2, lane B5); null without it, never a typed number ---- */
export function blindLine(ev) {
  const h = ev && typeof ev === "object" && ev.holdout_v2 && typeof ev.holdout_v2 === "object" ? ev.holdout_v2 : null;
  const ok = (x) => typeof x === "number" && Number.isFinite(x);
  if (!h || !ok(h.n) || !ok(h.navigator_k) || !ok(h.keyword_k)) return null;
  return { n: String(h.n), navigator: String(h.navigator_k), keyword: String(h.keyword_k),
    text: `On ${h.n} blind questions the AI reader read the right shock ${h.navigator_k} times, the keyword rules ${h.keyword_k}.` };
}


/* ---- R37: the blind result as paired, when the measure carries it (holdout_v2.paired {navigator_only, keyword_only, p_exact}
   or holdout_v2.mcnemar {b, c, p}, lane B5); null without it (the page then says only the two scores) ---- */
export function pairedLine(ev) {
  const h = ev && typeof ev === "object" && ev.holdout_v2 && typeof ev.holdout_v2 === "object" ? ev.holdout_v2 : null;
  const ok = (x) => typeof x === "number" && Number.isFinite(x);
  const p = h && (h.paired || h.mcnemar);
  if (!p || typeof p !== "object") return null;
  /* eval-stab writes only_navigator / only_keyword / mcnemar_exact_p (749418f); the earlier names still read */
  const a = [p.navigator_only, p.only_navigator, p.b].find(ok), b = [p.keyword_only, p.only_keyword, p.c].find(ok), pv = [p.p_exact, p.mcnemar_exact_p, p.p].find(ok);
  if (!ok(a) || !ok(b)) return null;
  return { a: String(a), b: String(b),
    text: `${a} ${a === 1 ? "question" : "questions"} only the AI reader got right, ${b} the other way${ok(pv) ? ` (exact McNemar p = ${pv < 0.001 ? pv.toFixed(4) : pv.toFixed(3)})` : ""}.` };
}
