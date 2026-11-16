// Lane U6 pure helpers (web/lib/why.js): node tests/web_u6_test.mjs. The fixture copies the shapes of a real Bedrock run
// (Robert, 40 % NVIDIA, run 1464f3e86a68: debrief, receipt, guardrail, facts, trace) cut to the rows the helpers read.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

globalThis.PF = createRequire(import.meta.url)("../web/lib.js");
const W = await import("../web/lib/why.js");
const NB = " ", MINUS = "−";
const clone = (x) => JSON.parse(JSON.stringify(x));

const R = {
  run_id: "1464f3e86a68", status: "ok", mode: "live", message: null, as_of: "2026-11-12", pilot: "robert", amount: 600000, question_type: "change",
  verdict: "Incompatible", question: "What if I put 40 % in NVIDIA and the tariff war flares up again?",
  profile: { name: "Robert", capacity: 90000 }, limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000 },
  series: { dates: ["2021-11-12", "2026-11-12"], today: [100, 120], after: [100, 180] },
  portfolio: { "XIU.TO": 0.27, "XBB.TO": 0.21, GLD: 0.06, "ZST.TO": 0.06, NVDA: 0.4 },
  baseline: { portfolio: { "XIU.TO": 0.45, "XBB.TO": 0.35, GLD: 0.1, "ZST.TO": 0.1 }, verdict: "Compatible" },
  scenario: { families: ["tariffs"], event_ids: ["canada_35_2025", "liberation_day_2025"], method: "bedrock",
    change: { op: "set", ticker: "NVDA", weight: 0.4, from_ticker: null }, check_order: ["max_drawdown", "scenario_stress"] },
  events: [{ event_id: "canada_35_2025", date: "2025-07-11", title: "A 35% tariff on Canada", family: "tariffs", lat: 45.4, lon: -75.7 },
    { event_id: "liberation_day_2025", date: "2025-04-03", title: "\"Liberation Day\" reciprocal tariffs", family: "tariffs", lat: 38.9, lon: -77.0 }],
  facts: {
    T24: { label: "Fictional amount", value: 600000, unit: "CAD", entity: "your amount", sign: "positive", kind: "fiction" },
    T25: { label: "Your floor, set by your capacity", value: -0.15, unit: "pct", entity: "your floor", sign: "negative", kind: "assumption" },
    T29: { label: "Worst drop after the move", value: -0.3452439040250206, unit: "pct", entity: "after", sign: "negative", kind: "fact" },
    T34: { label: "Worst clean tariff war shock after the move", value: -0.08990116109252089, unit: "pct", entity: "tariffs", sign: "negative", kind: "fact" },
    T35: { label: "Shock limit (half your floor)", value: -0.075, unit: "pct", entity: "shock check", sign: "negative", kind: "assumption" },
    T36: { label: "Clean tariff war shocks known", value: 6, unit: "count", entity: "tariffs", sign: "positive", kind: "fact" },
    T39: { label: "In this history, your floor breaks above 8 %", value: 0.08, unit: "pct", entity: "NVDA", sign: "positive", kind: "fact" },
  },
  trace: [
    { id: "T10", step: "COMPARE", tool: "governance.evaluate", inputs: { which: "after", families: ["tariffs"] }, outputs: {}, ms: 110, service: "Python", model: null, request_id: null },
    { id: "T11", step: "COMPARE", tool: "governance.evaluate", inputs: { which: "today", families: ["tariffs"] }, outputs: {}, ms: 92, service: "Python", model: null, request_id: null },
    { id: "T24", step: "OBSERVE", tool: "flight plan (your input)", inputs: { path: "amount", recipe: "flight_plan" }, outputs: { value: 600000 }, ms: 0, service: "Python", source: "Entered by you (fictional, never stored)" },
    { id: "T29", step: "COMPARE", tool: "governance.evaluate", inputs: { path: "metrics.after.max_drawdown", recipe: "evaluate.after" }, outputs: { value: -0.3452439040250206 },
      ms: 0, service: "Python", model: null, request_id: null, source: "Computed from the portfolio series" },
    { id: "T25", step: "OBSERVE", tool: "governance.load_limits", inputs: { path: "limits.floor", recipe: "limits" }, outputs: { value: -0.15 }, ms: 0, service: "Python" },
    { id: "T34", step: "COMPARE", tool: "governance.evaluate", inputs: { path: "turbulence.tariffs.worst_after", recipe: "evaluate.after" }, outputs: { value: -0.08990116109252089 }, ms: 0, service: "Python" },
    { id: "T55", step: "EXPLAIN", tool: "explain.draft", inputs: { facts: 7 }, outputs: { text: "…" }, ms: 6616, service: "Amazon Bedrock", model: "us.anthropic.claude-sonnet-5-5", request_id: "req-1" },
    { id: "T57", step: "EXPLAIN", tool: "explain.draft", inputs: { facts: 7 }, outputs: { text: "…" }, ms: 6531, service: "Amazon Bedrock", model: "us.anthropic.claude-sonnet-5-5", request_id: "req-2" },
  ],
  debrief: {
    verdict_sentence: "Outside your limits: the check that decided the verdict is your floor, and the tariff war shock you asked about adds to it.",
    sections: { data: [0], why: [1, 2], limits: [3], would_change: [4] },
    sentences: [
      { text: "The replay uses real market history and a fictional amount of $600,000 [T24].", kind: "scenario", refs: ["T24"], section: "data" },
      { text: "The check that decided the verdict is your floor: the portfolio after the move fell up to 34.5 % [T29], beyond your floor of 15.0 % [T25].", kind: "assumption", refs: ["T29", "T25"], section: "why" },
      { text: "On your tariff war question, the worst earlier tariff shock lost 9.0 % [T34], past the shock limit of 7.5 % [T35].", kind: "assumption", refs: ["T34", "T35"], section: "why" },
      { text: "This already happened; it is not a forecast.", kind: "limit", refs: [], section: "limits" },
      { text: "In this history, your floor breaks when NVDA is above 8.0 % [T39] of the portfolio.", kind: "fact", refs: ["T39"], section: "would_change" },
    ],
    flagged: false,
  },
  receipt: { verified: 13, total: 13, defects: [], drafts: 2, first_try: { verified: 15, total: 16, defects: ["Sentence 1 says 40.0 % but cites no [T#]."] } },
  guardrail: { input: { action: "NONE", blocked: false, topic_hit: false, error: null, request_id: "g-in" },
    output: { action: "NONE", blocked: false, topic_hit: false, error: null, request_id: "g-out" } },
  checks: [
    { rule: "max_drawdown", status: "fail", tier: "hard", name: "Your floor", value: -0.3452439040250206, limit: -0.15,
      reason: "In this history the mix's worst drop was −34.5 % ($207,146) from 2021-11-29 to 2022-10-14, beyond the −15.0 % ($90,000) you said you could absorb." },
    { rule: "scenario_stress", status: "warn", tier: "soft", name: "Shock check", value: -0.0899, limit: -0.075, reason: "In the 6 separate earlier Tariff war episodes the worst clean one cost 9.0 %, beyond half your floor (7.5 %)." },
    { rule: "crypto", status: "pass", tier: "preference", name: "Crypto share", value: 0, limit: 0, reason: "No crypto is in the mix, as you asked." },
  ],
};

test("segments: a number right before its [T#] becomes a button, the tags leave the text", () => {
  const s = W.segments("fell up to 34.5 % [T29], beyond your floor of 15.0 % [T25].");
  assert.deepEqual(s.map((x) => x.t), ["text", "num", "text", "num", "text"]);
  assert.equal(s[1].text, `34.5${NB}%`);
  assert.equal(s[1].id, "T29");
  assert.equal(W.plain(s), `fell up to 34.5${NB}%, beyond your floor of 15.0${NB}%.`);
  assert.equal(W.segments("an amount of $600,000 [T24].")[1].text, "$600,000");
  assert.equal(W.segments("in the 6 [T36] separate episodes")[1].text, "6");
  assert.equal(W.segments("a fall of −34.5 % [T29] here")[1].text, `${MINUS}34.5${NB}%`);
  assert.equal(W.segments("took 487 days [T50] to recover")[1].text, "487 days");
});
test("segments: a name with a digit, a tag with no number and a group tag", () => {
  assert.equal(W.segments("the G7 [T5] met")[1].t, "ref");
  assert.equal(W.segments("your floor [T25] holds")[1].t, "ref");
  assert.deepEqual(W.segments("lost 9.0 % [T34, T35].")[1].ids, ["T34", "T35"]);
  assert.deepEqual(W.segments("No tags at all."), [{ t: "text", text: "No tags at all." }]);
});

test("explanation: a clean debrief, the verdict sentence first and 3 to 5 sentences in reading order", () => {
  const e = W.explanation(R);
  assert.equal(e.state, "shown");
  assert.equal(e.by, "bedrock");
  assert.ok(W.plain(e.lead.segs).startsWith("Outside your limits:"));
  const n = e.picked.length + 1;
  assert.ok(n >= 3 && n <= 5, `picked ${n}`);
  assert.deepEqual(e.picked.map((s) => s.i), [1, 2, 4]);          // the deciding value and its limit, the asked shock, what would change
  assert.deepEqual(e.groups.map((g) => g.title), ["What data?", "Why this verdict?", "What limits?", "What would change the answer?"]);
  assert.equal(e.picked[0].marker.word, "assumption");
  assert.equal(e.groups[0].sentences[0].marker.word, "scenario");
  assert.equal(e.writer.requestId, "req-2");
  assert.equal(e.writer.drafts, 2);
});
test("explanation: flagged keeps the text and names the open point; withheld and no-Bedrock never pretend", () => {
  const f = clone(R);
  f.debrief.flagged = true;
  f.receipt.defects = ["The debrief must say “in the 6 separate earlier tariff war episodes”."];
  const ef = W.explanation(f);
  assert.equal(ef.state, "flagged");
  assert.equal(ef.note.word, "Flagged");
  assert.deepEqual(ef.note.items, f.receipt.defects);
  const w = clone(R);
  w.debrief = null;
  w.message = "The explanation is withheld: it still gave advice after one rewrite. The checklist and the charts are computed the same way.";
  const ew = W.explanation(w);
  assert.equal(ew.state, "withheld");
  assert.equal(ew.note.text, w.message);
  assert.deepEqual(ew.reasons.map((x) => x.rule), ["max_drawdown", "scenario_stress"]);
  assert.deepEqual(ew.reasons.map((x) => x.word), ["Outside", "Caution"], "web/lib/status.js: the page's one status vocabulary");
  assert.equal(ew.reasons[0].binding, "Decided the verdict");
  assert.equal(ew.reasons[1].binding, null);
  const soft = clone(w);
  soft.checks.unshift({ rule: "single_stock", status: "fail", tier: "soft", name: "One company", value: 0.4, limit: 0.1, reason: "NVDA is 40.0 % of the money." });
  const es = W.explanation(soft).reasons.find((x) => x.rule === "single_stock");
  assert.equal(es.word, "Caution", "a broken soft limit only adds a caveat");
  assert.match(ew.reasons[0].text, /from 29\u00a0Nov\u00a02021 to 14\u00a0Oct\u00a02022/);   // the page's own date and U+00A0 before %
  assert.match(ew.reasons[0].text, /−34\.5\u00a0%/);
  assert.equal(W.receiptLine(w, "live"), null, "no receipt line for an explanation that is not shown");
  const o = clone(R);
  o.debrief = null; o.receipt = null; o.trace = o.trace.filter((t) => t.step !== "EXPLAIN");
  const eo = W.explanation(o);
  assert.equal(eo.state, "off");
  assert.match(eo.note.text, /without Amazon Bedrock/);
  assert.equal(W.receiptLine(o, "static"), null);
  const st = W.explanation({ ...clone(R), status: "blocked", message: "The question was blocked." });
  assert.equal(st.state, "stopped");
});

test("receiptLine: counts from the receipt; the guardrail in its own words, grounding with its real score and threshold (R20)", () => {
  const l = W.receiptLine(R, "live");
  assert.deepEqual(l.parts.map((p) => p.text), ["13 of 13 numbers traced to the data", "corrected once"]);
  assert.equal(l.guardrail.text, "Input guardrail: passed. Output guardrail: passed.");
  const s = { ...clone(R), mode: "demo_replay", message: "Demo mode: this is the saved run for this exact question, recorded on 15 Nov 2026." };
  assert.equal(W.receiptLine(s, "live").parts[2].text, `recorded on 15${NB}Nov${NB}2026`);
  const low = clone(R);
  low.guardrail.output.grounding = { score: 0.13, threshold: 0.7, detected: true };
  const gl = W.receiptLine(low, "live").guardrail.text;
  assert.equal(gl, "Input guardrail: passed. Output grounding: 0.13 (threshold 0.70), advisory, not a gate; the number check above is the gate (eval §8).");
  assert.doesNotMatch(gl, /grounding[^.]*passed/i, "never 'passed' below its threshold");
  const high = clone(low);
  high.guardrail.output.grounding.score = 0.82;
  assert.match(W.receiptLine(high, "live").guardrail.text, /Output grounding: 0\.82 \(threshold 0\.70\), advisory/, "the copy reads the real values");
  const g = clone(R);
  g.guardrail.output.action = "GUARDRAIL_INTERVENED";
  assert.match(W.receiptLine(g, "live").guardrail.text, /Output guardrail: intervened\./);
  assert.equal(W.receiptLine(g, "live").guardrail.tone, "caveat");
  const one = clone(R);
  one.receipt = { verified: 12, total: 13, defects: ["x"], drafts: 1, first_try: { defects: ["x"] } };
  const l1 = W.receiptLine(one, "live");
  assert.equal(l1.parts[0].tone, "outside");
  assert.ok(!/corrected|first draft/.test(l1.text));
});

test("factCard and traceOf: the fact's row, where code recorded it and the step that computed it", () => {
  const c = W.factCard(R, "T29");
  assert.equal(c.valueText, `${MINUS}34.5${NB}%`);
  assert.equal(c.marker.word, "fact");
  assert.equal(c.entityText, "the mix after the move");
  assert.equal(c.raw, `${MINUS}0.345243904`);
  assert.equal(W.factCard(R, "T99"), null);
  assert.equal(W.entityText("tariffs"), "the tariff war");
  assert.equal(W.moveText({ op: "add", ticker: "SPY", weight: 0.2 }), `Add 20${NB}% SPY`);
  assert.equal(W.moveText(null), "No move");
  assert.equal(W.entityText("NVDA"), "NVIDIA");
  const t = W.traceOf(R, "T29");
  assert.equal(t.recorded.tool, "governance.evaluate");
  assert.deepEqual(t.recorded.inputs, [["path", "metrics.after.max_drawdown"], ["recipe", "evaluate.after"]]);
  assert.equal(t.computed.id, "T10");
  assert.equal(t.computed.ms, 110);
  assert.equal(W.traceOf(R, "T24").computed, null);
  assert.equal(W.recipeOf(R, "T24").title, "Read from your inputs");
  const mv = clone(R);
  mv.facts.T27 = { label: "The move: NVDA set to", value: 0.4, unit: "pct", entity: "NVDA", sign: "positive", kind: "fiction" };
  mv.trace.push({ id: "T27", step: "UNDERSTAND", tool: "agents.scenario.run_scenario", inputs: { path: "scenario.change.weight", recipe: "flight_plan" }, outputs: { value: 0.4 } });
  assert.equal(W.factCard(mv, "T27").label, "The move: NVIDIA set to");
  assert.equal(W.recipeOf(mv, "T27").title, "Read from your question by the AI reader");   // plain words (cold-user test, 14:25)
  assert.match(W.recipeOf(R, "T29").how, /governance\.evaluate on the mix after the move, on the data up to 12\u00a0Nov\u00a02026/);
  const dated = clone(R);
  dated.debrief.sentences[0].text = "The replay runs from 2021-11-12 to 2026-11-12 on a fictional amount of $600,000 [T24].";
  assert.match(W.plain(W.explanation(dated).groups[0].sentences[0].segs), /from 12\u00a0Nov\u00a02021 to 12\u00a0Nov\u00a02026/);
});

test("setBy (R4, R13): a persona's limits are assumed, your own are typed by you, a fictional amount says so", () => {
  const r = clone(R);
  assert.equal(W.setBy(r, "T24"), "Fictional illustration, not a recommendation.");
  assert.equal(W.setBy(r, "T25"), "Assumed from the profile, not set by you.");   // compliance: never "typed" for a persona
  r.limits.edited = ["floor"];
  assert.equal(W.setBy(r, "T25"), "Set by you, never read from an account.");
  assert.equal(W.setBy({ ...clone(R), pilot: null }, "T25"), "Set by you, never read from an account.");
  assert.equal(W.setBy(R, "T29"), null);
});

test("evidenceOf: hidden without the key; rows when present; an honest line when empty", () => {
  assert.equal(W.evidenceOf(R, "T29"), null);
  const e = { ...clone(R), evidence: { T29: [{ file: "computed: portfolio_series (base 100, CAD)", date: "2021-11-29", ticker: "portfolio (after)", value: 103.89968271352237 },
    { file: "computed: portfolio_series (base 100, CAD)", date: "2022-10-14", ticker: "portfolio (after)", value: 68.02895062654495 }], T24: [], T34: [] } };
  const ev = W.evidenceOf(e, "T29");
  assert.deepEqual(ev.rows.map((x) => [x.date, x.value]), [[`29${NB}Nov${NB}2021`, "103.90"], [`14${NB}Oct${NB}2022`, "68.03"]]);
  assert.match(W.evidenceOf(e, "T24").note, /input or a limit/);
  assert.match(W.evidenceOf(e, "T34").note, /licensed/);
});

test("reconciliationFor (R12): B3's {rows} with fractions and texts; the fact's ticker or the funds of its mix", () => {
  const rows = [{ ticker: "XIU.TO", period: "YTD to 2026-11-12, NAV", ours: 0.17991, published: 0.1793, gap_pp: 0.06, ours_text: "17.99 %", published_text: "17.93 %",
    ok: true, source_url: "https://www.blackrock.com/ca/investors/en/products/239832", read_on: "2026-11-14" },
    { ticker: "SPY", period: "1 year to 2026-10-31, market", ours: 0.12, published: 0.1197, gap_pp: 0.03, source_url: "https://www.ssga.com/y" }];
  const r = { ...clone(R), reconciliation: { rows, n: 5, within: 5, tolerance_pp: 0.15, kind: "fact" } };
  const got = W.reconciliationFor(r, "T29");
  assert.deepEqual(got.map((x) => [x.ticker, x.ours, x.published, x.gap, x.host, x.readOn]),
    [["XIU.TO", `17.99${NB}%`, `17.93${NB}%`, `+0.06${NB}pp`, "blackrock.com", `14${NB}Nov${NB}2026`]]);
  assert.deepEqual(W.reconciliationFor(r, "T25"), []);
  assert.deepEqual(W.reconciliationFor(R, "T29"), []);
  assert.deepEqual([W.reconciliationOf(r).n, W.reconciliationOf(r).within, W.reconciliationOf(r).tolerance], [5, 5, 0.15]);
  const bare = { ...clone(R), reconciliation: [{ ticker: "XIU.TO", period: "YTD", ours: 0.1799, published: 0.1793 }] };
  assert.equal(W.reconciliationFor(bare, "T29")[0].ours, `17.99${NB}%`);
});

test("seriesRows: with the public cut, the mix's own value on the fact's dates, from the Result's series (proofs._fact_dates)", () => {
  const r = clone(R);
  r.metrics = { after: { peak_date: "2021-11-29", trough_date: "2022-10-14" } };
  r.series = { dates: ["2021-11-12", "2021-11-29", "2022-10-14", "2026-11-12"], today: [100, 101, 90, 120], after: [100, 103.89968, 68.02895, 180] };
  r.evidence = { T29: [], T24: [] };
  const ev = W.evidenceOf(r, "T29");
  assert.equal(ev.from, "series");
  assert.deepEqual(ev.rows.map((x) => [x.date, x.value, x.ticker]), [[`29${NB}Nov${NB}2021`, "103.90", "The mix after the move"], [`14${NB}Oct${NB}2022`, "68.03", "The mix after the move"]]);
  assert.deepEqual(W.seriesRows(r, "T24"), []);
  r.as_of = "2022-01-01";
  assert.deepEqual(W.seriesRows(r, "T29").map((x) => x.value), ["103.90"], "a date after as_of is never shown (red gate 3)");
});

test("the moved ticker reads as the page names it, in text only (NVDA -> NVIDIA); numbers and ids untouched", () => {
  const e = W.explanation(R);
  const all = e.groups.flatMap((g) => g.sentences).map((s) => W.plain(s.segs)).join(" ");
  assert.match(all, /when NVIDIA is above 8\.0/);
  assert.doesNotMatch(all, /\bNVDA\b/);
  assert.equal(e.groups.flatMap((g) => g.sentences).flatMap((s) => s.segs).filter((g) => g.t === "num").length, 6);
});

test("recomputeLine: reproduced with the server's delta, mismatch, the static build check, the mock label", () => {
  const m = W.recomputeLine({ fact_id: "T29", value: -0.345, match: true, delta: 0 });
  assert.equal(m.word, "Reproduced");
  assert.equal(m.detail, `Δ${NB}0.0000`);
  assert.equal(W.recomputeLine({ same: true, value: 1, stored: 1 }).word, "Reproduced");
  assert.equal(W.recomputeLine({ same: true, value: 1, stored: 1 }).detail, null);
  const x = W.recomputeLine({ match: false, value: -0.3, stored: -0.345 });
  assert.equal(x.word, "Mismatch");
  assert.match(x.detail, /stored .*recomputed/);
  assert.equal(W.recomputeLine({ match: null }).word, "Not recomputed here");
  assert.match(W.recomputeLine({ match: true, delta: 0, mock: true }).label, /mock/i);
  assert.match(W.recomputeLine({ match: true, build: true }, { recorded: "15 Nov 2026" }).label, /recorded on 15 Nov 2026/);
  assert.equal(W.recomputeLine({ error: "Number T9 has no recorded recipe." }).detail, "Number T9 has no recorded recipe.");
  assert.equal(W.recomputeLine(undefined), null);
});

const NE = { same: false, diffs: [{ what: "precedents", navigator: ["canada_35_2025", "liberation_day_2025"], fallback: ["canada_35_2025"] }],
  verdict: "Incompatible", verdict_without: "Incompatible", binding_rule: "max_drawdown", binding_without: "max_drawdown", checks_without: [],
  fallback: { type: "change", change: { op: "set", ticker: "NVDA", weight: 0.4, from_ticker: null }, families: ["tariffs"], event_ids: ["canada_35_2025"], clarify_reason: null } };
const EVAL = { date: "2026-11-15", examples: { ai_off_cases: [
  { id: "hv2_fr01", category: "french", text: "Et si les États-Unis imposent encore des droits de douane?", expected_families: ["tariffs"], keyword_got: [], navigator_got: ["tariffs"] },
  { id: "hv2_para01", category: "paraphrase", text: "If Ottawa slaps new duties on US steel, what happens to me?", expected_families: ["tariffs"], keyword_got: ["war_oil"], navigator_got: ["tariffs"] },
  { id: "x", text: "A case where the navigator is wrong", expected_families: ["rates"], navigator_got: ["chips"], keyword_got: ["rates"] }] } };

test("navigatorPanel: hidden without navigator_effect; the two readings row by row; what only the navigator named", () => {
  assert.equal(W.navigatorPanel(R, EVAL), null);
  const p = W.navigatorPanel({ ...clone(R), navigator_effect: NE }, null);
  assert.deepEqual(p.rows.map((x) => [x.what, x.same]), [["change", true], ["families", true], ["precedents", false], ["verdict", true]]);
  assert.equal(p.rows[0].navigator, `NVIDIA to 40${NB}%`);
  assert.equal(p.rows[1].keywords, "Tariff war");
  assert.deepEqual(p.rows[2].onlyNavigator.map((x) => x.id), ["liberation_day_2025"]);
  assert.equal(p.rows[2].onlyNavigator[0].title, "\u201cLiberation Day\u201d reciprocal tariffs", "R18: typographic quotes");
  assert.equal(p.rows[3].navigator, "Outside your limits");
  assert.equal(p.example, null);
});
test("navigatorPanel (R8, R10): the same shock read by both brings the held-out case where the keyword rules misread it", () => {
  const p = W.navigatorPanel({ ...clone(R), navigator_effect: NE }, EVAL);
  assert.equal(p.familiesSame, true);
  assert.equal(p.example.question, EVAL.examples.ai_off_cases[1].text);
  assert.equal(p.example.keywords, "War & oil");
  assert.equal(p.example.navigator, "Tariff war");
  assert.match(p.example.source, /held-out evaluation/);
  assert.equal(p.example.navigatorPhrase, "the tariff war");
  assert.equal(p.example.keywordsPhrase, "a war and oil shock");
  const dated = W.evalExample({ date: "2026-11-14", holdout_v2: { date: "2026-11-15" }, examples: { ai_off_cases: [EVAL.examples.ai_off_cases[0]] } });
  assert.match(dated.source, /15\u00a0Nov\u00a02026/, "a held-out v2 case is dated by its own run, not the development set's");
  const wrongOnly = { examples: [EVAL.examples.ai_off_cases[2]] };
  const fr = W.evalExample({ examples: { ai_off_cases: [EVAL.examples.ai_off_cases[0]] } }, "tariffs");
  assert.equal(fr.lang, "fr");
  assert.match(fr.english, /^What if the United States/, "red gate 9: a French question is quoted only beside its English rendering");
  assert.equal(W.evalExample({ examples: { ai_off_cases: [{ ...EVAL.examples.ai_off_cases[0], id: "hv2_fr99" }] } }), null);
  assert.equal(W.evalExample({ examples: { ai_off_cases: [{ ...EVAL.examples.ai_off_cases[0], id: "hv2_fr99", text_en: "What if tariffs return?" }] } }).english, "What if tariffs return?");
  assert.equal(W.navigatorPanel({ ...clone(R), navigator_effect: NE }, wrongOnly).example, null);
  const famDiff = clone(NE);
  famDiff.diffs.push({ what: "families", navigator: ["tariffs"], fallback: ["war_oil"] });
  const q = W.navigatorPanel({ ...clone(R), navigator_effect: famDiff }, EVAL);
  assert.equal(q.familiesSame, false);
  assert.equal(q.example, null);
  assert.equal(q.rows[1].keywords, "War & oil");
});

test("citedIn and replaySpan: the sentence behind a number; the replay's own years (R1)", () => {
  const c = W.citedIn(R, "T34");
  assert.match(W.plain(c.segs), /worst earlier tariff shock/);
  assert.equal(c.title, "Why this verdict?");
  assert.equal(W.citedIn(R, "T35").section, "why");
  const twice = clone(R);
  twice.debrief.sentences[4].text = "In this history, your floor breaks when NVDA is above 8.0 % [T39]; the fall was 34.5 % [T29].";
  twice.debrief.sentences[4].refs = ["T39", "T29"];
  assert.equal(W.citedIn(twice, "T29").i, 1);
  assert.equal(W.citedIn(twice, "T29", 4).i, 4, "the sentence the reader clicked is the one quoted");
  assert.equal(W.citedIn({ ...clone(R), debrief: null }, "T29"), null);
  assert.equal(W.replaySpan(R), "2021–26");
  assert.equal(W.replaySpan({}), null);
});

test("red gate 1: no advice word in anything the helpers write", () => {
  const w = clone(R); w.debrief = null; w.message = null; w.trace = w.trace.filter((t) => t.step !== "EXPLAIN");
  const r2 = { ...clone(R), navigator_effect: NE, evidence: { T29: [], T24: [] } };
  const text = JSON.stringify([W.explanation(R), W.explanation(w), W.receiptLine(R, "static"), W.navigatorPanel(r2, EVAL), W.evidenceOf(r2, "T29"),
    W.evidenceOf(r2, "T24"), W.recomputeLine({ match: null }), W.recomputeLine({ match: true, build: true })]);
  const own = text.replace(/"question":"[^"]*"/g, "");      // an eval question is quoted as the investor wrote it
  assert.doesNotMatch(own, /\b(buy|buying|sell|selling|should|recommend\w*|safe|suitable|you can)\b/i);
  assert.doesNotMatch(own, /\bhold\b/i);
});

test("pick reads what a sentence cites, never its wording or its position (the real 09:27 Robert debrief's shape)", () => {
  const r = clone(R);
  r.debrief.sections = { data: [0], why: [1, 2, 3], limits: [4, 5], would_change: [6] };
  r.debrief.sentences = [
    { text: "The replay uses real market history and a fictional amount of $600,000 [T24].", kind: "scenario", refs: ["T24"], section: "data" },
    { text: "Failed rules: Your floor, One company, One sector. Your floor of 15.0 % [T25] is what you said you could absorb.", kind: "assumption", refs: ["T25"], section: "why" },
    { text: "The portfolio after the move fell up to 34.5 % [T29] at its worst.", kind: "fact", refs: ["T29"], section: "why" },
    { text: "Some other why sentence with no number.", kind: "assumption", refs: [], section: "why" },
    { text: "This already happened; it is not a forecast.", kind: "limit", refs: [], section: "limits" },
    { text: "in the 6 [T36] separate earlier tariff war episodes, this mix lost up to 9.0 % [T34] (Indicative)", kind: "limit", refs: ["T36", "T34"], section: "limits" },
    { text: "In this history, the floor breaks when NVDA is above 8.0 % [T39] of the portfolio.", kind: "fact", refs: ["T39"], section: "would_change" },
  ];
  const e = W.explanation(r);
  assert.deepEqual(e.picked.map((s) => s.i), [1, 2, 5, 6]);
  assert.equal(e.picked.length + 1, 5);
  assert.ok(W.plain(e.picked[2].segs).startsWith("In the 6 separate"), "a sentence starts with a capital on screen");
  assert.equal(W.decidingRule(r), "max_drawdown");
  const shockOnly = clone(r);
  shockOnly.checks = [{ rule: "esg_direct", status: "fail", reason: "x" }, { rule: "scenario_stress", status: "pass", reason: "y" }];
  assert.equal(W.decidingRule(shockOnly), "esg_direct");
  assert.equal(W.decidingRule({ checks: [{ rule: "crypto", status: "pass" }] }), null);
});

test("receiptTape: every number the receipt matched, mapped back to the fact its sentence cites", () => {
  const r = clone(R);
  r.receipt.matches = [{ sentence: 2, number: "$600,000", refs: ["T24"] }, { sentence: 3, number: "34.5 %", refs: ["T29", "T25"] },
    { sentence: 3, number: "15.0 %", refs: ["T29", "T25"] }, { sentence: 6, number: "8.0 %", refs: ["T39"] }];
  const t = W.receiptTape(r);
  assert.deepEqual(t.map((x) => [x.number, x.id, x.traced]), [["$600,000", "T24", true], [`34.5${NB}%`, "T29", true], [`15.0${NB}%`, "T25", true], [`8.0${NB}%`, "T39", true]]);
  assert.deepEqual(W.receiptTape({ ...clone(R), receipt: null }), []);
});

test("navigator summary: what changed first (the shock), then what both read alike; never a dotted list", () => {
  const ne = clone(NE);
  ne.diffs.push({ what: "families", navigator: ["tariffs"], fallback: [] });
  ne.verdict_without = null;
  const p = W.navigatorPanel({ ...clone(R), navigator_effect: ne }, null);
  const v = p.rows.find((x) => x.what === "verdict");
  assert.equal(v.same, null);
  assert.equal(v.keywords, "Not computed for this reading");
  assert.match(p.summary, /^The keyword rules named no shock; the navigator read the tariff war\./);
  assert.match(p.summary, /not computed for the keyword rules’ reading/);
  assert.match(p.summary, /Both read the move the same way\.$/);
  assert.doesNotMatch(p.summary, / · /);
  const same = W.navigatorPanel({ ...clone(R), navigator_effect: { ...clone(NE), diffs: [], same: true } }, null);
  assert.equal(same.summary, "Both read the move, the shock and the verdict the same way.");
});

test("R20: a keyword reading of another move gets no verdict word; the episode count comes from one key", () => {
  const ne = clone(NE);
  ne.diffs.unshift({ what: "change", navigator: { op: "set", ticker: "NVDA", weight: 0.4 }, fallback: { op: "set", ticker: "NVDA", weight: 0.1 } });
  ne.verdict_without = "Compatible";
  const r = { ...clone(R), navigator_effect: ne, turbulence: { tariffs: { n: 6 } } };
  const p = W.navigatorPanel(r, null);
  const v = p.rows.find((x) => x.what === "verdict");
  assert.equal(v.keywords, "Not shown: the keyword rules read another move");
  assert.doesNotMatch(JSON.stringify(p.rows), /Inside your limits/, "never a pass mark for an alternative");
  assert.equal(p.rows.find((x) => x.what === "precedents").label, "Precedents picked");
  assert.equal(p.countLine, "The shock check counts all 6 clean tariff war episodes on record. The lists above are the precedents each reading picked to tell the story; they never reach the checks.");
  assert.match(p.summary, /^The keyword rules read the move as nVIDIA|^The keyword rules read the move as/);
});

// R17: values pinned only on the committed fixtures (the public cut of the four saved real runs, frozen by U0)
const FIX = await import("./web_fixtures.mjs");
const EVAL_DOC = JSON.parse((await import("node:fs")).readFileSync(new URL("../web/eval_results.json", import.meta.url), "utf8"));
test("the four saved real runs: 3 to 5 sentences each, the receipt and its tape agree, every cited number opens a fact", () => {
  for (const name of FIX.NAMES) {
    const r = FIX.load(name), e = W.explanation(r), rc = W.receiptLine(r, "static");
    assert.equal(e.state, "shown", name);
    const n = e.picked.length + (e.lead ? 1 : 0);
    assert.ok(n >= 3 && n <= 5, `${name}: ${n} sentences`);
    assert.ok(e.picked.some((s) => s.section === "would_change"), `${name}: what would change the answer`);
    assert.equal(rc.verified, r.receipt.verified, name);
    assert.equal(W.receiptTape(r).filter((x) => x.traced).length, r.receipt.verified, `${name}: one tape mark per traced number`);
    const nums = e.groups.flatMap((g) => g.sentences).flatMap((s) => s.segs).filter((g) => g.t === "num");
    assert.ok(nums.length > 0 && nums.every((g) => W.factCard(r, g.id)), `${name}: every number button has its fact`);
    assert.doesNotMatch(JSON.stringify(e.groups), /\bNVDA\b/, `${name}: the moved ticker by name`);
  }
  assert.equal(W.receiptLine(FIX.load("robert"), "static").parts[0].text, "15 of 15 numbers traced to the data");
});
test("the four saved real runs: the AI-off beat always shows a real difference, in the run or from the blind eval", () => {
  const want = { robert: "tariffs", mateo: "war_oil", amira: "chips" };
  // lane ev's audit: the eval lists only cases that reproduced in both passes, and no war-and-oil case did (hv2_fr02 is
  // dropped), so a run whose asked shock has no case gets an English case of another shock ("not this run")
  const has = (fam) => (Array.isArray(EVAL_DOC.examples) ? EVAL_DOC.examples : []).some((e) => (e.expected_families || []).includes(fam));
  for (const name of FIX.NAMES) {
    const p = W.navigatorPanel(FIX.load(name), EVAL_DOC);
    assert.ok(p, name);
    const inRun = p.rows.some((x) => x.same === false);
    assert.ok(inRun || p.example, `${name}: a difference`);
    if (p.familiesSame && p.example && has(want[name])) assert.equal(p.example.family, want[name], `${name}: the example is about the asked shock`);
    else if (p.familiesSame && p.example) assert.equal(p.example.lang, "en", `${name}: no case of the asked shock, so an English one`);
    if (p.example) assert.notEqual(p.example.id, "hv2_fr02", `${name}: a case that did not reproduce is never shown`);
  }
  assert.equal(W.navigatorPanel(FIX.load("canadian"), EVAL_DOC).familiesSame, false);
});

test("receiptFacts: every traced number once, written as the page writes it (shares as shares, falls with their tenth), with its id", () => {
  const r = FIX.load("robert"), list = W.receiptFacts(r), ids = list.map((x) => x.id);
  assert.equal(new Set(ids).size, ids.length, "deduplicated");
  assert.ok(list.length < W.receiptTape(r).length, "the repeated numbers fold into one row each");
  const by = Object.fromEntries(list.map((x) => [x.id, x.valueText]));
  assert.equal(by.T29, `${MINUS}34.5${NB}%`);
  assert.equal(by.T27, `40${NB}%`, "the move as the chips and the dial write it");
  assert.equal(by.T25, `${MINUS}15${NB}%`, "a limit as lib.js compareOf writes it");
  assert.equal(by.T24, "$600,000");
  for (const x of list) assert.equal(x.valueText, W.pageText(r, x.id));
});
