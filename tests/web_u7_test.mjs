// Lane U7 pure helpers (web/lib/how.js) and the vendored QR encoder: node tests/web_u7_test.mjs. The fixture copies the shapes
// of the saved runs of 15 Nov 2026 (Robert 40 % NVIDIA, run fe9c7ecb24be: checks, kpis, guardrail, receipt, trace), cut to the
// rows the helpers read; the eval numbers are read from web/eval_results.json itself, never typed here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
globalThis.PF = require("../web/lib.js");
const H = await import("../web/lib/how.js");
const qrcode = require("../web/vendor/qr/qrcode.js");
const NB = " ";
const clone = (x) => JSON.parse(JSON.stringify(x));
const EVAL = JSON.parse(readFileSync(new URL("../web/eval_results.json", import.meta.url), "utf8"));

const ROBERT = {
  run_id: "fe9c7ecb24be", status: "ok", mode: "demo_replay", as_of: "2026-11-12", pilot: "robert", amount: 600000, question_type: "change",
  message: "Demo mode: this is the saved run for this exact question, recorded on 15 Nov 2026.",
  question: "Everyone is talking about NVIDIA. What if I put 40 % in it and the tariff war flares up again?",
  verdict: "Incompatible", profile: { name: "Robert", age: 59, capacity: 90000 },
  limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000, edited: [] },
  portfolio: { "XIU.TO": 0.27, "XBB.TO": 0.21, GLD: 0.06, "ZST.TO": 0.06, NVDA: 0.4 },
  baseline: { portfolio: { "XIU.TO": 0.45, "XBB.TO": 0.35, GLD: 0.1, "ZST.TO": 0.1 }, verdict: "Compatible", kpis: { max_drawdown: { value: -0.106, loss_dollars: -63639.21 } } },
  scenario: { families: ["tariffs"], method: "bedrock", change: { op: "set", ticker: "NVDA", weight: 0.4 },
    check_order: ["max_drawdown", "single_stock", "sector", "scenario_stress", "risk_concentration", "crypto", "recovery", "short_horizon"] },
  series: { dates: ["2021-11-12", "2026-11-12"], today: [100, 120], after: [100, 180] },
  metrics: { today: { max_drawdown: -0.106, cagr: 0.087, trough_date: "2022-10-14" }, after: { max_drawdown: -0.3452439040250206, cagr: 0.25, trough_date: "2022-10-14" } },
  kpis: { max_drawdown: { value: -0.3452439040250206, limit: -0.15, loss_dollars: -207146.34241501236 } },
  checks: [
    { rule: "max_drawdown", tier: "hard", status: "fail", value: -0.3452439040250206, limit: -0.15, name: "Your floor" },
    { rule: "scenario_stress", tier: "soft", status: "warn", value: -0.0899, limit: -0.075, name: "Shock check" },
    { rule: "single_stock", tier: "soft", status: "fail", value: 0.4, limit: 0.1, holding: "NVDA", name: "One company" },
    { rule: "crypto", tier: "preference", status: "pass", value: 0, limit: 0, name: "Crypto" },
  ],
  guardrail: { input: { action: "NONE", blocked: false, error: null, request_id: "924235ab-0000-4000-8000-000000000001" },
    output: { action: "NONE", topic_hit: false, error: null, grounding: { score: 0.19, threshold: 0.7, detected: true }, request_id: "05afae09-0000-4000-8000-000000000002" } },
  receipt: { verified: 15, total: 15, defects: [] },
  debrief: { sentences: [] },
  diversification: { today: { countries: { CAN: 0.876 }, can_risk_share: 0.853 }, after: { countries: { CAN: 0.526 }, can_risk_share: 0.095 } },
  events: [{ event_id: "liberation_day_2025", date: "2025-04-03", family: "tariffs", lat: 38.9, lon: -77.0 }],
  trace: [
    { id: "T1", step: "OBSERVE", tool: "flight plan (your input)", ms: 0, service: "Python", model: null, usage: null, request_id: null },
    { id: "T3", step: "OBSERVE", tool: "guardrail.apply_guardrail(INPUT)", ms: 601, service: "Bedrock Guardrails", model: null, usage: { topicPolicyUnits: 1 }, request_id: "924235ab-0000-4000-8000-000000000001" },
    { id: "T4", step: "OBSERVE", tool: "governance.evaluate", inputs: { which: "today" }, ms: 537, service: "Python" },
    { id: "T5", step: "UNDERSTAND", tool: "navigator.search_events", ms: 0, service: "Python", detail: "called by the navigator" },
    { id: "T7", step: "UNDERSTAND", tool: "navigator.model_turn", ms: 3053, service: "Amazon Bedrock", model: "us.anthropic.claude-sonnet-5-5",
      usage: { inputTokens: 2151, outputTokens: 324, totalTokens: 3781, cacheReadInputTokens: 1306 }, request_id: "ca96e1d9-0000-4000-8000-000000000003" },
    { id: "T8", step: "UNDERSTAND", tool: "agents.scenario.run_scenario", ms: 3200, service: "Python" },
    { id: "T15", step: "COMPARE", tool: "tools.allocation.tipping_point", ms: 3470, service: "Python" },
    { id: "T18", step: "COMPARE", tool: "tools.allocation.comparison_menu", ms: 5015, service: "Python" },
    { id: "T10", step: "COMPARE", tool: "governance.evaluate", inputs: { which: "after" }, ms: 201, service: "Python" },
    { id: "T53", step: "COMPARE", tool: "ui.charts", ms: 0, service: "Python" },
    { id: "T29", step: "COMPARE", tool: "governance.evaluate", inputs: { path: "metrics.after.max_drawdown", recipe: "evaluate.after" }, ms: 0, service: "Python" },
    { id: "T54", step: "EXPLAIN", tool: "agents.memory.load", inputs: { file: "defect_memory.json" }, ms: 0, service: "Python" },
    { id: "T55", step: "EXPLAIN", tool: "explain.draft", ms: 5868, service: "Amazon Bedrock", model: "us.anthropic.claude-sonnet-5-5",
      usage: { inputTokens: 2069, outputTokens: 690, cacheReadInputTokens: 2727 }, request_id: "a561b17d-0000-4000-8000-000000000004" },
    { id: "T56", step: "VERIFY", tool: "verify.receipt", ms: 6, service: "Python" },
    { id: "T57", step: "VERIFY", tool: "guardrail.output", ms: 743, service: "Bedrock Guardrails", request_id: "05afae09-0000-4000-8000-000000000002" },
  ],
  reconciliation: { rows: [
    { ticker: "XIU.TO", period: "YTD to 2026-11-12, NAV", basis: "NAV", ours: 0.179854, published: 0.1793, gap_pp: 0.06, ours_text: "17.99 %", published_text: "17.93 %", ok: true,
      source_url: "https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf" },
    { ticker: "GLD", period: "1 year to 2026-10-31, market", basis: "market price", ours: -0.033522, published: -0.0335, gap_pp: 0.0, ours_text: "−3.35 %", published_text: "−3.35 %", ok: true,
      source_url: "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld" } ], n: 2, within: 2, tolerance_pp: 0.15, kind: "fact" },
};

test("wilson reproduces the intervals docs/eval_results.json carries (scripts/eval.py, z = 1.96)", () => {
  for (const a of EVAL.arms) {
    const w = H.wilson(a.k, a.n);
    assert.ok(Math.abs(w.lo - a.lo) < 1e-12 && Math.abs(w.hi - a.hi) < 1e-12, `${a.arm} ${a.k}/${a.n}`);
  }
  assert.equal(H.wilson(0, 0), null);
  assert.equal(H.wilson(5, 4), null);
  assert.equal(H.intervalText(0.7783231187385907, 0.9546789490988218), `77.8–95.5${NB}%`);
});

test("provenance (R15): a saved run says when it was recorded, never live; live only when the caller knows it just landed live", () => {
  assert.deepEqual(H.provenance(ROBERT), { saved: true, date: `15${NB}Nov${NB}2026`, time: null, text: `Recorded on 15${NB}Nov${NB}2026` });
  const stamped = { ...ROBERT, recorded_at: "2026-11-15T15:02:11-05:00", message: null };
  assert.deepEqual(H.provenance(stamped), { saved: true, date: `15${NB}Nov${NB}2026`, time: "15:02 Eastern time", text: `Recorded on 15${NB}Nov${NB}2026` });
  assert.equal(H.provenance({ ...ROBERT, message: "Demo mode: this is the saved run for this exact question, recorded on 05 Nov 2026." }).text, `Recorded on 5${NB}Nov${NB}2026`);
  assert.equal(H.provenance({ ...ROBERT, message: null }), null);                          // no date: the line is hidden
  const raw = { ...ROBERT, mode: "live", message: null };
  assert.equal(H.provenance(raw), null);                                                    // a raw saved file never reads as live
  assert.equal(H.provenance(raw, { live: true }).text, "Run live in this session");
  assert.equal(H.provenance(ROBERT, { live: true }).text, `Recorded on 15${NB}Nov${NB}2026`); // a demo replay is never live
  assert.equal(H.flowOf(raw, { live: true }).provenance.text, "Run live in this session");
  assert.equal(H.provenance({ mode: "something" }), null);
  assert.equal(H.provenance(null), null);
  assert.equal(H.qualifier(ROBERT), "in this 2021–26 replay");
  assert.equal(H.qualifier({}), "in this replay");
  assert.equal(H.dataTo(ROBERT), `Data to 12${NB}Nov${NB}2026`);
  assert.equal(H.dataTo({}), null);
  assert.equal(H.dataToShort(ROBERT), `To 12${NB}Nov${NB}2026`);
});

test("names and readouts: model, tokens, durations, request ids", () => {
  assert.equal(H.modelName("us.anthropic.claude-sonnet-5-5"), "Claude Sonnet 5.5");
  assert.equal(H.modelName("claude"), "Claude");
  assert.equal(H.modelName(null), null);
  assert.deepEqual(H.tokensOf({ inputTokens: 2151, outputTokens: 324, cacheReadInputTokens: 1306 }), { input: 2151, output: 324, total: 2475, cached: 1306 });
  assert.equal(H.tokensOf({ topicPolicyUnits: 1 }), null);
  assert.deepEqual([H.msText(601), H.msText(3053), H.msText(11996), H.msText(null)], [`601${NB}ms`, `3.1${NB}s`, `12${NB}s`, null]);
  assert.equal(H.shortId("924235ab-0000-4000-8000-000000000001"), "924235ab");
});

test("the ledger row: the answer, its qualifier, and the check that decided it (R1, R13, R14, R15)", () => {
  const x = H.ledgerRow(ROBERT, "robert");
  assert.equal(x.name, "Robert");
  assert.equal(x.meta, "59, with $600,000");
  assert.deepEqual(x.verdict, { word: "Outside your limits", tone: "outside", icon: "i-out" });
  assert.equal(x.qualifier, "in this 2021–26 replay");
  assert.equal(x.without, "Without the move: inside your limits.");
  assert.equal(x.family, "Tariff war");
  assert.equal(x.move, `NVIDIA to 40${NB}%`);
  assert.equal(x.decided.rule, "max_drawdown");
  assert.equal(x.decided.name, "your floor");
  assert.equal(x.decidedLabel, "Decided by");
  assert.equal(x.decided.sentence, `At its worst the mix fell 34.5${NB}% from a high, past your 15${NB}% rule.`);   // R35 (17:41): no dollars on the % rule
  assert.equal(x.assumed, true);
  assert.equal(x.recorded.text, `Recorded on 15${NB}Nov${NB}2026`);
  assert.equal(H.ledgerRow({ status: "error" }, "robert"), null);
  assert.equal(H.ledgerRow(null, "robert"), null);
});

test("each investor is decided by a different check: values, crypto, Canada's share", () => {
  const mateo = clone(ROBERT);
  Object.assign(mateo, { pilot: "mateo", question_type: "shock", verdict: "Tension", profile: { name: "Mateo", age: 41 }, amount: 250000, tipping_point: null, baseline: null,
    checks: [{ rule: "esg_direct", status: "fail", tier: "preference", value: 0.08, limit: 0, holding: "CNQ.TO" }, { rule: "max_drawdown", status: "pass", value: -0.11, limit: -0.25 }] });
  mateo.scenario.check_order = ["esg_direct", "max_drawdown"];
  const m = H.ledgerRow(mateo, "mateo");
  assert.equal(m.decided.name, "your values");
  assert.equal(m.decidedLabel, "The check that added the caveat:");      // a caveat is never "decided"
  assert.equal(m.decided.sentence, `A company your values screen excludes is held directly: 8${NB}% of the money, against your limit of 0${NB}%.`);
  assert.equal(m.without, null);
  assert.ok(!/CNQ/.test(m.decided.sentence));                        // the company is never named on the card
  const amira = clone(mateo);
  Object.assign(amira, { pilot: "amira", profile: { name: "Amira", age: 26 }, checks: [{ rule: "crypto", status: "fail", tier: "soft", value: 0.15, limit: 0.1 }] });
  amira.scenario.check_order = ["crypto"];
  assert.equal(H.ledgerRow(amira, "amira").decided.sentence, `Crypto is 15${NB}% of the money, against your limit of 10${NB}%.`);
  const can = clone(ROBERT);
  Object.assign(can, { pilot: "canadian", verdict: "Compatible", profile: { name: "Too Canadian?", age: null }, amount: 250000,
    portfolio: { "XIU.TO": 0.48, "XBB.TO": 0.24, "ZST.TO": 0.08, SPY: 0.2 }, baseline: { portfolio: { "XIU.TO": 0.6, "XBB.TO": 0.3, "ZST.TO": 0.1 }, verdict: "Compatible" },
    checks: [{ rule: "risk_concentration", status: "warn", tier: "warn", value: 0.639, limit: 0.5 }],
    diversification: { today: { countries: { CAN: 0.975 }, can_risk_share: 0.975 }, after: { countries: { CAN: 0.78 }, can_risk_share: 0.683 } } });
  can.scenario.change = { op: "add", ticker: "SPY", weight: 0.2 };
  const c = H.ledgerRow(can, "canadian");
  assert.equal(c.decided.name, "Canada’s share");
  assert.equal(c.decidedLabel, "The check that answers it:");
  assert.equal(c.decided.sentence, `With SPY at 20${NB}%, Canada’s share of the money goes from 97.5${NB}% to 78.0${NB}%, and in this replay it carried 68.3${NB}% of the risk instead of 97.5${NB}%.`);
  assert.equal(c.meta, "$250,000");
  assert.equal(c.assumed, false);
  assert.deepEqual(H.flowOf(can).nodes[0].lines, ["As the workshop asked it"]);
  assert.deepEqual(H.flowOf(ROBERT).nodes[0].lines, ["In Robert\u2019s words"]);
  assert.equal(c.kicker, "The workshop\u2019s question");
  assert.equal(H.ledgerRow(ROBERT, "robert").kicker, null);
});

test("R19 (a): the steps are the workshop's method plus the one we added, said in one line", () => {
  assert.deepEqual(H.STEPS.map((s) => s.label), ["Observe", "Understand", "Compare", "Explain", "Verify"]);
  assert.deepEqual(H.STEPS.filter((s) => s.ours).map((s) => s.id), ["VERIFY"]);
  assert.equal(H.METHOD, "Observe, Understand, Compare, Explain: the method National Bank\u2019s workshop taught. We added one step: Verify.");
});

test("the flow of this run: nine stations in order, each with the trace's own numbers; recipe rows are not calls", () => {
  const f = H.flowOf(ROBERT);
  assert.deepEqual(f.nodes.map((n) => n.id), ["question", "guard_in", "navigator", "compute", "checks", "explain", "receipt", "guard_out", "you"]);
  assert.deepEqual(f.nodes.map((n) => n.kind), ["you", "guard", "model", "code", "code", "model", "code", "guard", "you"]);
  const by = Object.fromEntries(f.nodes.map((n) => [n.id, n]));
  assert.equal(by.guard_in.ms, 601);
  assert.equal(by.guard_in.outcome, "Not blocked");
  assert.equal(by.guard_in.requestId, "924235ab-0000-4000-8000-000000000001");
  assert.equal(by.navigator.ms, 3053);
  assert.equal(by.navigator.tokens.total, 2475);
  assert.equal(by.navigator.model, "Claude Sonnet 5.5");
  assert.deepEqual(by.navigator.lines, ["Tariff war", `NVIDIA to 40${NB}%`]);
  assert.equal(by.compute.ms, 3470 + 5015);
  assert.deepEqual(by.compute.lines, ["2 tool calls"]);
  assert.equal(by.checks.ms, 537 + 201);                               // the recipe row T29 (ms 0) is a fact's provenance, not a call
  assert.deepEqual(by.checks.lines, ["4 on your limits", "1 outside, 2 caution, 1 inside"]);   // the checklist's words: a soft break is caution
  assert.equal(by.checks.outcome, "Outside your limits");
  assert.equal(by.explain.tokens.total, 2759);
  assert.equal(by.receipt.lines[0], "15 of 15 numbers traced");
  assert.equal(by.receipt.outcome, "Clean");
  assert.equal(by.guard_out.outcome, "No advice found");
  assert.deepEqual(by.guard_out.grounding, { score: 0.19, threshold: 0.7 });
  assert.equal(f.bedrock, 2);
  assert.equal(f.guards, 2);
  const noModel = clone(ROBERT);
  noModel.trace = noModel.trace.filter((t) => t.service !== "Amazon Bedrock");
  noModel.debrief = null;
  const g = Object.fromEntries(H.flowOf(noModel).nodes.map((n) => [n.id, n]));
  assert.equal(g.navigator.kind, "code");
  assert.equal(g.navigator.outcome, "Keyword rules, no model");
  assert.equal(g.explain.outcome, "Off in this run");
  assert.equal(H.flowOf({ ...ROBERT, trace: [] }), null);
  /* a blocked question: the input guardrail says so, and no later station claims a state it never reached */
  const blocked = clone(ROBERT);
  blocked.status = "blocked";
  blocked.guardrail.input.blocked = true;
  blocked.trace = blocked.trace.filter((t) => t.step === "OBSERVE");
  const b = Object.fromEntries(H.flowOf(blocked).nodes.map((n) => [n.id, n]));
  assert.equal(b.guard_in.outcome, "Blocked");
  assert.deepEqual(["navigator", "compute", "checks", "explain", "receipt", "guard_out"].map((id) => [b[id].notRun, b[id].outcome, b[id].ms]),
    Array(6).fill([true, "Not run", null]));
  assert.equal(b.you.notRun, undefined);
});

test("the eval card reads the file: the blind held-out set leads, the development set is labelled, intervals are Wilson", () => {
  const ev = H.evalOf(EVAL);
  const h = EVAL.holdout_v2;
  assert.equal(ev.heldout.n, h.n);
  assert.deepEqual(ev.heldout.arms.map((a) => [a.id, a.k, a.n]), [["navigator", h.navigator_k, h.n], ["keyword", h.keyword_k, h.n]]);
  for (const a of ev.heldout.arms) {
    const w = H.wilson(a.k, a.n);
    assert.ok(Math.abs(a.lo - w.lo) < 1e-12 && Math.abs(a.hi - w.hi) < 1e-12);
    assert.equal(a.interval, H.intervalText(w.lo, w.hi));
  }
  const dn = EVAL.arms.find((a) => a.arm === "navigator"), dk = EVAL.arms.find((a) => a.arm === "keyword_fallback");
  assert.deepEqual([ev.development.n, ev.development.navigator.k, ev.development.keyword.k], [EVAL.n, dn.k, dk.k]);
  assert.equal(ev.heldout.model, "Claude Sonnet 5.5");
  /* lane ev's second pass: the file's own intervals, the whole reading, the first pass and the categories, all read as written */
  if (Array.isArray(h.navigator_families_wilson)) assert.deepEqual([ev.heldout.arms[0].lo, ev.heldout.arms[0].hi], h.navigator_families_wilson);
  if (Number.isFinite(h.navigator_whole_k)) assert.deepEqual(ev.heldout.whole.map((a) => a.k), [h.navigator_whole_k, h.keyword_whole_k]);
  if (h.first_pass) assert.deepEqual(ev.heldout.firstPass, { navigator: h.first_pass.navigator_k, keyword: h.first_pass.keyword_k });
  if (h.by_category && h.by_category.french) assert.deepEqual(ev.heldout.categories.find((c) => c.id === "french"),
    { id: "french", label: "In French", n: h.by_category.french.n, navigator: h.by_category.french.navigator.k, keyword: h.by_category.french.keyword.k });
  /* when the file carries the held-out intervals and the categories (B5's results shape), those are used as they are */
  const richer = clone(EVAL);
  delete richer.holdout_v2.navigator_families_wilson;
  delete richer.holdout_v2.keyword_families_wilson;
  richer.holdout_v2.summary = { navigator: { k: h.navigator_k, wilson_low: 0.5, wilson_high: 0.9 }, keyword: { k: h.keyword_k, wilson_low: 0.4, wilson_high: 0.8 } };
  richer.holdout_v2.by_category = { french: { n: 6, navigator: { k: 6 }, keyword: { k: 0 } }, paraphrase: { n: 10, navigator: { k: 10 }, keyword: { k: 5 } }, slang: { n: 5, navigator: { k: 5 }, keyword: { k: 5 } } };
  const r = H.evalOf(richer);
  assert.deepEqual([r.heldout.arms[0].lo, r.heldout.arms[0].hi], [0.5, 0.9]);
  assert.deepEqual(r.heldout.categories.map((c) => [c.id, c.n, c.navigator, c.keyword]), [["french", 6, 6, 0], ["paraphrase", 10, 10, 5]]);
  assert.equal(H.evalOf(null), null);
  assert.equal(H.evalOf({}), null);
});

test("reconciliation rows (R12): B3's object shape and a plain list both read; dates read as dates", () => {
  const rc = H.reconciliationOf(ROBERT);
  assert.deepEqual([rc.n, rc.funds, rc.within, rc.tolerance], [2, 2, 2, 0.15]);
  assert.deepEqual(rc.rows[0], { ticker: "XIU.TO", period: `YTD to 12${NB}Nov${NB}2026, NAV`, basis: "NAV", ours: `17.99${NB}%`, published: `17.93${NB}%`, gap: "+0.06",
    ok: true, url: "https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf", host: "blackrock.com" });
  assert.equal(rc.rows[1].gap, "0.00");
  const list = H.reconciliationOf({ reconciliation: [{ ticker: "SPY", period: "1 year", ours: 0.12, published: 0.1197, source_url: "http://insecure.example" }] });
  assert.deepEqual([list.rows[0].ours, list.rows[0].published, list.rows[0].url, list.within], [`12.00${NB}%`, `11.97${NB}%`, null, null]);
  assert.equal(H.reconciliationOf({}), null);
});

test("the vendored encoder (qrcode-generator 1.4.4) encodes the public URL into a matrix of the right size", () => {
  const q = qrcode(0, "M");
  q.addData(H.PUBLIC_URL);
  q.make();
  const n = q.getModuleCount();
  assert.equal((n - 17) % 4, 0);                                       // a QR matrix is 17 + 4 x version modules a side
  assert.ok(n >= 21 && n <= 177);
  const finder = (r0, c0) => [0, 6].every((d) => [0, 1, 2, 3, 4, 5, 6].every((i) => q.isDark(r0 + d, c0 + i) && q.isDark(r0 + i, c0 + d)))
    && !q.isDark(r0 + 1, c0 + 1) && q.isDark(r0 + 3, c0 + 3);
  assert.ok(finder(0, 0) && finder(0, n - 7) && finder(n - 7, 0));     // the three finder patterns
  const again = qrcode(0, "M"); again.addData("https://example.org/"); again.make();
  assert.notDeepEqual(Array.from({ length: n }, (_, r) => q.isDark(r, 10)), Array.from({ length: again.getModuleCount() }, (_, r) => again.isDark(r, 10)));
  /* the SVG path covers exactly the dark modules, one run per row segment, offset by the quiet zone */
  const d = H.qrPath((r, c) => q.isDark(r, c), n, 4);
  let cells = 0;
  for (const m of d.matchAll(/M(\d+) (\d+)h(\d+)v1h-(\d+)z/g)) {
    const [x, y, w] = [+m[1] - 4, +m[2] - 4, +m[3]];
    for (let i = 0; i < w; i += 1) { assert.ok(q.isDark(y, x + i)); cells += 1; }
  }
  let dark = 0;
  for (let r = 0; r < n; r += 1) for (let c = 0; c < n; c += 1) dark += q.isDark(r, c) ? 1 : 0;
  assert.equal(cells, dark);
  assert.equal(H.publicUrl(undefined), H.PUBLIC_URL);
  assert.equal(H.publicUrl("http://not-https.example/"), H.PUBLIC_URL);
  assert.equal(H.publicUrl("https://ok.example/demo/"), "https://ok.example/demo/");
  assert.equal(H.publicUrl("https://bad.example/\"onload"), H.PUBLIC_URL);
  assert.equal(H.bareUrl(H.PUBLIC_URL), "shmorsi.github.io/poly-datathon-2026");
});

test("the strip counts the checks in the checklist's own words (lane U5b's shownStatus), on the four committed fixtures", async () => {
  const M = await import("../web/lib/money.js");
  const { load, NAMES } = await import("./web_fixtures.mjs");
  for (const status of ["fail", "warn", "pass", "error", undefined]) for (const tier of ["hard", "soft", "preference", "warn", undefined])
    assert.deepEqual(H.shownMirror(status, tier), M.shownStatus(status, tier), `${status}/${tier}`);
  const expected = { robert: "1 outside, 4 caution, 3 inside", mateo: "2 caution, 8 inside", amira: "1 caution, 7 inside", canadian: "1 caution, 7 inside" };
  for (const name of NAMES) {
    const r = load(name);
    for (const c of r.checks) assert.deepEqual(H.shownMirror(c.status, c.tier), M.shownStatus(c.status, c.tier), `${name} ${c.rule}`);
    const own = H.flowOf(r, { shown: M.shownStatus }).nodes.find((n) => n.id === "checks"), mirror = H.flowOf(r).nodes.find((n) => n.id === "checks");
    assert.deepEqual(own.lines, mirror.lines, name);
    assert.equal(own.lines[1], expected[name], name);
    const rows = M.checksModel(r, globalThis.PF.view(r), globalThis.PF).rows;      // the checklist's rows say the same
    const words = (w) => rows.filter((x) => x.word === w).length;
    assert.equal(own.lines[1], [["outside", words("Outside")], ["caution", words("Caution")], ["inside", words("Inside")]].filter(([, n]) => n).map(([w, n]) => `${n} ${w}`).join(", "), name);
  }
});

test("audit item 7: every shock and every earlier crisis with its own source; the values screen cited as the data cites it", () => {
  const r = clone(ROBERT);
  r.events = [{ event_id: "liberation_day_2025", date: "2025-04-03", title: "\"Liberation Day\" reciprocal tariffs", family: "tariffs", place: "Washington, DC",
    lat: 38.9, lon: -77.0, source_url: "https://www.whitehouse.gov/fact-sheets/2025/04/" },
    { event_id: "ukraine_2022", date: "2022-02-24", title: "Russian invasion of Ukraine", family: "war_oil", place: "Kyiv, Ukraine", lat: 50.4, lon: 30.5,
      source_url: "javascript:alert(1)" }];
  const rows = H.shocksRecord(r);
  assert.deepEqual(rows.map((x) => [x.date, x.family, x.host]), [["2022-02-24", "War & oil", null], ["2025-04-03", "Tariff war", "whitehouse.gov"]]);
  assert.equal(rows[0].url, null);                                       // only http(s) links are ever drawn
  assert.equal(rows[1].dateText, `3${NB}Apr${NB}2025`);
  assert.equal(rows[1].title, "\u201cLiberation Day\u201d reciprocal tariffs");             // R18: typographic quotes on display
  assert.equal(H.typo("Powell's Jackson Hole speech"), "Powell\u2019s Jackson Hole speech");
  assert.equal(H.shocksRecord({}), null);
  r.deep_history = { episodes: [{ id: "oil_embargo_1973", title: "Oil embargo and the 1973\u201374 bear market", start: "1973-01", end: "1974-12", place: "Kuwait City",
    source_url: "https://www.federalreservehistory.org/essays/oil-shock-of-1973-74", source_title: "Federal Reserve History: Oil Shock of 1973-74" }] };
  assert.deepEqual(H.crisesRecord(r), [{ id: "oil_embargo_1973", title: "Oil embargo and the 1973\u201374 bear market", years: "1973\u20131974", place: "Kuwait City",
    url: "https://www.federalreservehistory.org/essays/oil-shock-of-1973-74", host: "federalreservehistory.org", sourceTitle: "Federal Reserve History: Oil Shock of 1973-74" }]);
  assert.equal(H.crisesRecord(ROBERT), null);
  const csv = readFileSync(new URL("../data/esg_flags.csv", import.meta.url), "utf8");
  for (const l of H.VALUES_SOURCES) assert.ok(csv.includes(l.url), l.label);   // every values link is a link the data itself cites
  const values = H.sourcesOf(ROBERT).find((x) => x.name === "The values screen");
  assert.equal(values.links, H.VALUES_SOURCES);
  assert.ok(!/EDGAR|SEDAR/.test(JSON.stringify(values)));               // read on each company's investor site, never there (finance_methods §6)
});

test("footer limits and sources: the history line first, dates from the Result, every line plain", () => {
  const lim = H.limitsOf(ROBERT);
  assert.equal(lim[0].text, "This already happened; it is not a forecast.");
  assert.deepEqual(lim.find((x) => x.link).link, { href: "#checklist", text: "Edit your limits in the checklist (live app)." });
  assert.ok(lim.some((x) => x.text.startsWith(`Daily prices from 12${NB}Nov${NB}2021 to 12${NB}Nov${NB}2026`)));
  assert.ok(!lim.some((x) => /stand-ins/.test(x.text)));                // no deep history in this Result: no line about it
  assert.ok(H.limitsOf({ ...ROBERT, deep_history: { kind: "assumption" } }).some((x) => x.kind === "assumption" && /Crises before 2021/.test(x.text)));
  const src = H.sourcesOf(ROBERT);
  assert.ok(src.find((s) => s.name === "The shocks").use.startsWith("1 team-written"));
  const sv = H.servicesOf(H.flowOf(ROBERT));
  assert.deepEqual(sv.map((s) => s.run || null), ["2 calls in this run", "2 checks in this run", null, null, null, null, null]);
  assert.deepEqual(sv.filter((s) => s.group === "run").map((s) => s.id), ["bedrock", "guardrails"]);
  assert.deepEqual(sv.filter((s) => s.group === "app").map((s) => s.id), ["ec2", "cloudfront", "iam", "s3", "cloudwatch"]);
});

test("nothing these helpers write reads as advice, as an 'A · B · C' string or in the third person (red gate 1, R16, R18)", () => {
  const out = JSON.stringify([H.ledgerRow(ROBERT, "robert"), H.flowOf(ROBERT), H.evalOf(EVAL), H.reconciliationOf(ROBERT), H.limitsOf(ROBERT),
    H.sourcesOf(ROBERT), H.servicesOf(H.flowOf(ROBERT)), H.NAV]);
  assert.ok(!/\b(buy|sell|hold|you should|we recommend|recommended)\b/i.test(out));
  assert.ok(!out.includes(" · "));
  assert.ok(!/[●◐○]/.test(out));
});
