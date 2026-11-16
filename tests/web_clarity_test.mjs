/* Lane clarity (ruling R22, the lead 12:35): every finished section opens with ONE plain question and ONE answer sentence, at most
   about 6 figures on screen while "Show the details" is closed, and every number has a plain-words meaning. Pinned on the
   committed web fixtures (R17). Run: node tests/web_clarity_test.mjs (tests/test_web_lib.py runs it too). */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { load, NAMES } from "./web_fixtures.mjs";
import * as C from "../web/lib/meaning.js";
import * as M from "../web/lib/money.js";
import * as D from "../web/lib/dial.js";
import * as W from "../web/lib/why.js";
import * as H from "../web/lib/how.js";
import * as R from "../web/lib/record.js";

const PF = createRequire(import.meta.url)("../web/lib.js");
globalThis.PF = PF;                                   // the section libraries read PF at call time
let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}
const run = (name) => { const r = PF.withPaths(load(name)); return [r, PF.view(r)]; };
const figures = (strings) => strings.reduce((a, s) => a + C.countFigures(s), 0);
const BUDGET = 6;
const sp = (s) => String(s).replace(/[\u00a0\u202f]/g, " ");      // PF.fmt keeps a figure and its unit together

/* ---- the meaning map and the figure count ---- */
test("countFigures: years and year ranges are dates, the rest are figures", () => {
  assert.equal(C.countFigures("in this 2021–26 replay"), 0);
  assert.equal(C.countFigures("−$207,146 (−34.5 %) vs −$90,000 (−15 %)"), 4);
  assert.equal(C.countFigures("NVIDIA 40 % vs 10 %"), 2);
  assert.equal(C.countFigures("XIU.TO"), 0);
  assert.equal(C.countFigures("Four other checks raised a caution."), 0);
});

test("say(): one sentence that repeats the figure shown and adds no number", () => {
  assert.equal(C.say("worst_fall", "−34.5 %"), "−34.5 %: the biggest drop from a high point, in this replay.");
  assert.equal(C.say("money_share", "40 %", "NVIDIA"), "40 %: the share of your money in NVIDIA.");
  assert.equal(C.say("worst_fall", ""), null);
  for (const [k, words] of Object.entries(C.MEANING)) assert.equal(C.countFigures(words), 0, `${k} carries a number of its own`);
});

test("factMeaning(): the Result's own facts label, never typed", () => {
  const [r] = run("robert");
  const id = Object.keys(r.facts).find((k) => r.facts[k].label === "Worst drop after the move");
  assert.ok(id);
  assert.equal(C.factMeaning(r, id, "−34.5 %"), "−34.5 %: worst drop after the move.");
  assert.equal(C.factMeaning(r, "T-none", "1", "count"), "1: how many there were, in this replay.");
});

/* ---- #money ---- */
test("money: 'Where is the risk?' answered in one sentence with the pair's own figure (R22's example)", () => {
  const [r, v] = run("robert");
  const L = M.moneyLead(r, v, PF);
  assert.equal(L.question, "Where is the risk?");
  assert.equal(sp(L.answer), "With the move, 89.6 % of your risk came from NVIDIA alone.");
  assert.ok(L.notes.includes("This already happened; it is not a forecast."));
  assert.ok(L.notes.includes("Fictional illustration, not a recommendation."));
});

test("money: closed, at most 6 figures on every fixture", () => {
  for (const n of NAMES) {
    const [r, v] = run(n);
    const L = M.moneyLead(r, v, PF);
    assert.ok(L && L.answer, n);
    assert.ok(figures(L.shown) <= BUDGET, `${n}: ${figures(L.shown)} figures`);
  }
});

/* ---- #checklist ---- */
test("checklist: 'Which of your rules broke?' in words, the three rows kept, the floor row by its one name, defined once (R35, 17:20)", () => {
  const [r, v] = run("robert");
  const L = M.checklistLead(r, v, PF);
  assert.equal(L.question, "Which of your rules broke?");
  assert.equal(L.answer, "Your floor broke in this 2021–26 replay. Four other checks raised a caution; two are shown here, the rest in the details.");
  assert.equal(L.rows.length, 3);
  assert.equal(L.rows[0].rule, "max_drawdown");
  assert.equal(sp(L.rows[0].valueShort), "−34.5 %");
  assert.equal(sp(L.rows[0].limitShort), "−15 %");
  assert.equal(sp(L.rows[0].ruleWords), "Tolerance: no fall of more than 15 % from a high");
  assert.match(sp(L.rows.find((x) => x.rule === "scenario_stress").ruleWords), /^Its limit is a rule of thumb: half your 15 % floor$/);
  assert.equal(L.capacity, null, "no capacity key in the fixture: no row");
  assert.equal(L.rest.length, 5);
  assert.ok(L.rows.some((x) => x.rule === "scenario_stress"), "the asked shock's check stays visible");
});

test("checklist: the answer names the row that decided, and never more than 6 figures closed", () => {
  const want = {
    mateo: "No hard limit broke in this 2021–26 replay; your values added the caveat.",
    amira: "No hard limit broke in this 2021–26 replay; your crypto share added the caveat.",
    canadian: "None of your limits broke in this 2021–26 replay. One check raised a caution.",
  };
  for (const n of NAMES) {
    const [r, v] = run(n);
    const L = M.checklistLead(r, v, PF);
    if (want[n]) assert.equal(L.answer, want[n], n);
    assert.equal(C.countFigures(L.answer), 0, `${n}: the answer is words`);
    assert.ok(figures(L.shown) <= BUDGET, `${n}: ${figures(L.shown)} figures`);
  }
});


/* ---- #dial (standalone), #why, #investors, #how, #record: what each shows closed stays inside the budget ---- */
test("dial: 'At what size does it break?' answered by R2's own sentence and one large figure", () => {
  const r = PF.withPaths(load("robert")), m = D.dialModel(r, PF);
  const sentence = m.sentence.map(([t]) => t).join("");
  assert.equal(sp(sentence), "In this replay, your floor first broke at 9 % NVIDIA.");
  for (const n of NAMES) {
    const x = D.dialModel(PF.withPaths(load(n)), PF);
    if (!x) continue;
    const shown = [x.sentence.map(([t]) => t).join(""), x.notch ? x.notch.text : "", x.notch ? `${x.name}: the first size that broke your floor, ${x.replay}` : "", x.fineprint.join(" ")];
    assert.ok(figures(shown) <= BUDGET, `${n}: ${figures(shown)} figures`);
  }
});

test("why: the lead, the three sentences and the AI's line stay inside the budget on the fixtures", () => {
  for (const n of NAMES) {
    const r = load(n), e = W.explanation(r), txt = (segs) => segs.map((s) => s.text || "").join("");
    const four = W.fourQuestions(e);       // G2: one sentence per workshop question (four at most), so the budget is a sentence's 2-3 each
    const shown = [e.lead ? txt(e.lead.segs) : "", ...four.map((x) => txt(x.s.segs)), W.aiValueLine(r, null) || "",
      "In this 2021–26 replay. This already happened; it is not a forecast."];
    assert.ok(four.length >= 3 && four.length <= 4, n);
    assert.ok(figures(shown) <= 12, `${n}: ${figures(shown)} figures`);
  }
});

test("why: one plain line on the AI's value, only when the navigator's reading differs, words only", () => {
  const can = W.aiValueLine(load("canadian"), null);
  assert.equal(can, "The AI read your question as the tariff war; a plain word search found no shock.");
  const rob = W.aiValueLine(load("robert"), null);
  assert.equal(rob, "The AI read the tariff war, as the keyword rules did, and picked two earlier episodes they missed.");
  for (const n of NAMES) assert.equal(C.countFigures(W.aiValueLine(load(n), null) || ""), 0, n);
  const same = load("robert");
  same.navigator_effect = { ...same.navigator_effect, same: true, diffs: [] };
  assert.equal(W.aiValueLine(same, null), null, "no difference, no line");
});

test("investors: four one-line rows with no figures", () => {
  for (const n of H.INVESTORS) {
    const x = H.ledgerRow(load(n), n);
    const shown = [x.name, x.family || "", x.verdict.word, x.qualifier, x.decided ? x.decided.name : ""];
    assert.equal(figures(shown), 0, `${n}: ${shown.join(" | ")}`);
  }
});

test("how: closed, the five steps say words (a line with a figure waits for the details)", () => {
  for (const n of NAMES) {
    const flow = H.flowOf(load(n), { live: false, shown: M.shownStatus });
    const shown = flow.nodes.flatMap((nd) => [nd.name, nd.model || "", nd.outcome || "", ...nd.lines.filter((l) => !C.countFigures(l))]);
    assert.equal(figures(shown), 0, n);
    assert.ok(flow.nodes.some((nd) => nd.lines.some((l) => C.countFigures(l))), `${n}: the figures exist, one click deep`);
  }
});

test("record: the essentials carry at most 6 figures (who, the move); the annex keeps every number", () => {
  for (const n of NAMES) {
    const rec = R.buildRecord(load(n), {});
    const shown = [rec.investor.age, rec.investor.amount, rec.move && rec.move.weight, rec.move && rec.move.today_weight].filter((x) => typeof x === "number");
    assert.ok(shown.length <= BUDGET, n);
    assert.ok(rec.numbers.length > BUDGET, `${n}: the annex lists every number`);
  }
});

test("keepRanges: a year range never breaks across lines", () => {
  assert.equal(C.keepRanges("in this 2021–26 replay"), "in this 2021–\u206026 replay");
  assert.equal(C.countFigures(C.keepRanges("in this 2021–26 replay")), 0);
});

/* ---- pre-freeze (13:05): the workshop's XSP line, the blind measure in #how, the evidence date ---- */
test("money, Too Canadian?: one line from the run's keys (more spread, not softer; hedged like XSP by a similar index)", () => {
  const [r0, v0] = run("canadian");
  assert.equal(M.moneyLead(r0, v0, PF).hedge, null, "no key, no line");
  const r = PF.withPaths(load("canadian"));
  r.hedge_compare = { ticker: "SPY", weight: 0.2, unhedged: { worst_fall: -0.1290208253453493, kind: "fact" },
    hedged_standin: { worst_fall: -0.14199012259379074, kind: "assumption" } };
  const L = M.moneyLead(r, PF.view(r), PF);
  assert.equal(sp(L.hedge.text), `More spread, not softer: worst fall ${sp(PF.fmt.pct(r.metrics.today.max_drawdown))} → −12.9 % (−14.2 % hedged like XSP, by a similar index).`);
  assert.equal(L.hedge.hedgedKind, "assumption");
  assert.ok(figures(L.shown) <= 8, `${figures(L.shown)} figures`);
});

test("how: the AI's measured value in one sentence, read from the blind held-out measure (never typed)", () => {
  const ev = JSON.parse(readFileSync(new URL("../web/eval_results.json", import.meta.url), "utf8"));
  const b = H.blindLine(ev), h = ev.holdout_v2;
  assert.equal(b.text, `On ${h.n} blind questions the AI reader read the right shock ${h.navigator_k} times, the keyword rules ${h.keyword_k}.`);
  assert.equal(H.blindLine({}), null);
  assert.equal(H.blindLine({ holdout_v2: { n: 48 } }), null);
});

test("checklist: the evidence note's date belongs to the other shock (it never reads as the asked episode's)", () => {
  const [r, v] = run("robert");
  const s = M.checksModel(r, v, PF).rows.find((x) => x.rule === "scenario_stress");
  assert.match(sp(s.evidence), /^indicative, because one of these episodes overlapped another shock: .+, on 10 Sep 2026$/);
});

test("plain words: the page's vocabulary for the jargon, the exact term kept in the tooltip", () => {
  assert.equal(C.plain("Your question, read by the navigator"), "Your question, read by the AI reader");
  assert.equal(C.plain("Check of the stand-ins (2021-11 to 2025-12)"), "Check of the similar indexes (2021-11 to 2025-12)");
  assert.equal(C.plain("replayed by stand-in."), "replayed by similar indexes.");
  assert.equal(C.plain("Receipt: 13 of 13"), "Number check: 13 of 13");
  assert.equal(C.plain("sit inside each family's shock windows"), "sit inside each kind of shock’s windows");
  for (const k of ["AI reader", "number check", "tamper-proof record", "similar indexes", "kinds of shock"]) {
    assert.ok(C.TERMS[k] && C.countFigures(C.TERMS[k].replace("SHA-256", "")) === 0, k);
  }
  assert.match(C.TERMS["AI reader"], /^The navigator: /);
  assert.match(C.TERMS["tamper-proof record"], /^The seal: /);
});

/* ---- the official-requirements round (traceability G1, G2, G4, G5) ---- */
test("G1: growth per year and volatility over the replay's own dates, today then with the move (no after side without a move)", () => {
  const [r, v] = run("robert"), c = M.compareOf(r, v, PF);
  assert.equal(sp(c.period), "From 12 Nov 2021 to 12 Nov 2026, in Canadian dollars, dividends reinvested");
  assert.deepEqual([c.today.cagr, c.after.cagr, c.today.vol, c.after.vol].map(sp), ["8.7 %", "25.2 %", "7.4 %", "22.2 %"]);
  const [m, mv] = run("mateo");
  assert.equal(M.compareOf(m, mv, PF).after, null);
  assert.match(C.MEANING.volatility, /one indicator among others/);
});

test("G2: Simple #why speaks by the workshop's four questions, one sentence each", () => {
  const four = W.fourQuestions(W.explanation(load("robert")));
  assert.deepEqual(four.map((x) => x.q), ["What data?", "Why this answer?", "What limits?", "What would change it?"]);
});

test("G4: Amira's own test (not only tech) is in view: her one-sector row, with its words", () => {
  const [r, v] = run("amira"), L = M.checklistLead(r, v, PF);
  const own = L.rows.find((x) => x.rule === "sector");
  assert.ok(own && own.own === "Your own test: not only tech");
  assert.equal(L.rows.length, 3);
  assert.ok(L.rows.some((x) => x.decided) && L.rows.some((x) => x.rule === "scenario_stress"), "the deciding row and the asked shock stay");
  assert.equal(sp(M.sectorLine(r, PF).text), "Technology: 37.5 % of the money, inside your 40 % sector limit.");
  const [rb, vb] = run("robert");
  assert.ok(!M.checklistLead(rb, vb, PF).rows.some((x) => x.own), "no other investor's rows change");
});

test("G5: the checklist says what it does not measure, in one line, with no advice word", () => {
  const [r, v] = run("robert"), m = M.checksModel(r, v, PF);
  assert.equal(m.unmeasured, "Not measured here: credit risk inside the bond funds and how easily each holding could be sold; every holding trades daily on an exchange, crypto around the clock.");
  assert.doesNotMatch(m.unmeasured, /\b(buy|sell|hold|you should|recommend)\b/i);
});

test("compliance: one muted line says who set the limits, from the run's own flags only", () => {
  const [r, v] = run("robert");
  assert.equal(M.limitsLine(r, v).text, "Your limits here are assumed from the profile, not set by you.");
  const typed = { ...r, limits: { ...r.limits, edited: ["floor"] }, rechecked: true };
  assert.equal(M.limitsLine(typed, v).text, "Your floor is set by you; every other limit here is assumed from the profile, not set by you.");
  const two = { ...r, limits: { ...r.limits, edited: ["floor", "single_stock"] } };
  assert.equal(M.limitsLine(two, v).text, "Your floor and your one-company limit are set by you; every other limit here is assumed from the profile, not set by you.");
  assert.equal(M.limitsLine({ ...r, pilot: null }, v).text, "Your limits here are set by you.");
});

test("R35: the capacity fact row comes from result.capacity only (the path's own dollars)", () => {
  const [r0, v] = run("robert");
  const r = { ...r0, capacity: { today: { amount: 600000, capacity: 90000, line: 510000, low_value: 545000, sessions_below: 0, status: "held" },
    after: { amount: 600000, capacity: 90000, line: 510000, low_value: 408174, low_date: "2022-10-14", sessions_below: 188,
      first_below: "2022-05-09", last_below: "2022-12-28", status: "broke" } } };
  const c = M.capacityRow(r, v, PF);
  assert.equal(sp(c.meta), "Capacity: stay above $510,000 ($90,000 of $600,000)");
  assert.equal(sp(c.value), "$408,174 at its lowest");
  assert.equal(c.word, "Fell below");
  assert.equal(c.when, "Below it for 188 sessions, in 2022.");
  assert.doesNotMatch(JSON.stringify(c), /same fall on your/);
});

test("R37: the AI-off line is the Result's own sentence when navigator_effect carries one, else code's, from its own counts", () => {
  const r = load("robert");
  r.navigator_effect = { ...r.navigator_effect, sentence: "Switching the AI off changes no verdict here." };
  assert.equal(W.aiOffLine(r), "Switching the AI off changes no verdict here.");
  const s = load("robert");
  delete s.navigator_effect.sentence;
  const line = W.aiOffLine(s);
  assert.ok(line === null || /^Switching it off changes/.test(line));
});

test("R37: a malformed AI-off sentence (a missing count printed as None) never reaches the page", () => {
  const r = load("robert");
  r.navigator_effect = { ...r.navigator_effect, sentence: "Switching the AI off changes no verdict here: Outside your limits either way. It changes the question answered: without it, the shock check replays the None  episodes (worst −12.0 %) instead of the 7 chip war episodes you asked about (worst −8.6 %)." };
  const line = W.aiOffLine(r);
  assert.ok(line && line.startsWith("Switching the AI off changes no verdict here: Outside your limits either way."), line);
  assert.doesNotMatch(line, /None|\s{2}/);
});

test("design juror: 'What data?' and 'What limits?' are written by code from the run's keys, never by the AI", () => {
  const r = load("robert"), c = W.codeAnswers(r);
  assert.equal(sp(c.data), "Real daily prices from 12 Nov 2021 to 12 Nov 2026, in Canadian dollars, dividends reinvested (the organizers’ starter set: Yahoo Finance, Bank of Canada, FRED); 37 sourced shocks; the funds’ published holdings dated 12 Nov 2026.");
  assert.equal(c.limits, "One five-year market regime; assets picked in 2026, so survivors only; no taxes or trading costs; it replays the past and is not a forecast.");
  const four = W.fourQuestions(W.explanation(r), r);
  assert.equal(four.find((x) => x.id === "data").s.by, "code");
  assert.equal(four.find((x) => x.id === "limits").s.by, "code");
  assert.notEqual(four.find((x) => x.id === "why").s.by, "code", "the other two stay the explanation's own sentences");
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
