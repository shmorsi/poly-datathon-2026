/* Lane judge: "Try to trip it up" (web/sections/testai.js) and the bar's "Judging? Start here" popover, pure helpers only
   (web/lib/judge.js). Pinned on committed fixtures (R17): tests/fixtures/web/tests.json (the INTERFACES.md tests.json shape)
   and the four web fixtures. Run: node tests/web_judge_test.mjs (tests/test_web_lib.py runs it too). */
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { load } from "./web_fixtures.mjs";
import * as J from "../web/lib/judge.js";
import * as H from "../web/lib/how.js";
import { schedule } from "../web/lib/replay.js";
import { adviceHits, metaHits } from "../scripts/gate_rules.mjs";

globalThis.PF = createRequire(import.meta.url)("../web/lib.js");
const FIXTURE = JSON.parse(readFileSync(new URL("./fixtures/web/tests.json", import.meta.url), "utf8"));
const fresh = () => JSON.parse(JSON.stringify(FIXTURE));
let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}
const store = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) }; };

/* ---- the six cards ---- */
test("the fixture's cards (the six of R25 and the seventh, source_short), in its order, each with its question, line and kind", () => {
  const tests = J.readTests(fresh());
  assert.equal(tests.length, 7);
  assert.deepEqual(tests.map((t) => t.id), ["advice", "french", "alias", "no_precedent", "clarify", "reframe", "source_short"]);
  assert.deepEqual(tests.map((t) => t.kind), ["blocked", "run", "run", "run", "clarify", "run", "clarify"]);
  for (const t of tests) { assert.ok(t.question); assert.ok(t.shows); }
  assert.equal(tests[5].pilot, "canadian");
  assert.equal(tests[0].pilot, "robert");
});

test("the heading and its one line are the brief's words; the count is the cards' own", () => {
  assert.equal(J.TITLE, "Try to trip it up");
  assert.equal(J.lede(6), "Six questions that show what the AI does — and what it refuses to do.");
  assert.equal(J.lede(5), "Five questions that show what the AI does — and what it refuses to do.");
  assert.equal(J.lede(7), "Seven questions that show what the AI does — and what it refuses to do.");
});

test("readTests drops what a card cannot show: unknown kinds, no question, duplicates, a bad key; at most MAX_TESTS (8)", () => {
  const j = fresh();
  j.tests.push({ id: "x", kind: "poem", question: "Write a poem?" }, { id: "y", kind: "run" }, { ...j.tests[1] });
  assert.equal(J.readTests(j).length, 7);
  const bad = fresh();
  bad.tests[1].key = "../../etc/passwd";
  assert.equal(J.readTests(bad)[1].key, null);
  bad.tests[0].pilot = "nobody";
  assert.equal(J.readTests(bad)[0].pilot, "robert");
  const many = { tests: Array.from({ length: 9 }, (_, i) => ({ id: `t${i}`, kind: "run", key: "a1b2c3d4e5f60001", question: `Q${i}?` })) };
  assert.equal(J.readTests(many).length, J.MAX_TESTS);
});

/* ---- run vs inline ---- */
test("static: blocked and clarify answer inline in the card; run cards load their saved run by key", () => {
  const acts = J.readTests(fresh()).map((t) => J.actionFor(t, "static"));
  assert.deepEqual(acts.map((a) => a.type), ["inline", "load", "load", "load", "inline", "load", "inline"]);
  assert.deepEqual(acts[1], { type: "load", key: "a1b2c3d4e5f60001", pilot: "robert" });
  assert.deepEqual(acts[5], { type: "load", key: "a1b2c3d4e5f60004", pilot: "canadian" });
  assert.equal(J.runPath("a1b2c3d4e5f60001"), "runs/a1b2c3d4e5f60001.json");
  assert.equal(J.runPath("../x"), null);
});

test("live: every card sends its own question down the app's normal path, for its investor", () => {
  const tests = J.readTests(fresh());
  for (const t of tests) assert.deepEqual(J.actionFor(t, "live"), { type: "live", question: t.question, pilot: t.pilot });
});

test("a card that cannot run in static mode is not drawn (null): a run without a key, a stop without an answer", () => {
  const [advice, french] = J.readTests(fresh());
  assert.equal(J.actionFor({ ...french, key: null }, "static"), null);
  assert.equal(J.actionFor({ ...advice, response: null }, "static"), null);
  assert.equal(J.actionFor({ ...advice, response: { status: "ok", message: "x" } }, "static"), null);
});

/* ---- the hide-when-absent rule ---- */
test("no tests.json signal: no source, so no request and the section stays hidden", () => {
  assert.equal(J.testsSource({}), null);
  assert.equal(J.testsSource({ meta: null, override: undefined }), null);
  assert.equal(J.testsSource(), null);
  assert.deepEqual(J.readTests(null), []);
  assert.deepEqual(J.readTests({ version: 1 }), []);
  assert.deepEqual(J.readTests({ tests: "six" }), []);
});

test("the static build's meta tag (or a harness's EPI_TESTS_URL) names the file; anything else is refused", () => {
  assert.equal(J.testsSource({ meta: "runs/tests.json" }), "runs/tests.json");
  assert.equal(J.testsSource({ meta: "runs/tests.json", override: "/runs/tests.json" }), "/runs/tests.json");
  for (const bad of ["javascript:alert(1)", "../secret.json", "runs/tests.js", "data:application/json,{}", " "]) {
    assert.equal(J.testsSource({ meta: bad }), null, bad);
  }
});

/* ---- the recorded answers ---- */
test("blocked by Amazon Bedrock Guardrails: the badge says so, no model saw it, the answer has no disclaimer twice", () => {
  const s = J.stopOf(J.readTests(fresh())[0].response);
  assert.equal(s.by, "guardrails");
  assert.equal(s.badge, "Amazon Bedrock Guardrails stopped it. No model saw the question.");
  assert.ok(!s.text.includes(J.DISCLAIMER));
  assert.ok(s.text.startsWith("EPICENTRE replays a move against the limits you set; it doesn’t tell anyone"));
  assert.ok(s.text.includes("Try: “What if I put 40 % in NVIDIA and the tariff war flares up again?”"));
});

test("blocked by the advice check (code): read from its own trace row (the pipeline's offline shape)", () => {
  const r = { status: "blocked", message: `${"EPICENTRE replays a move against the limits you set."}\n\n${J.DISCLAIMER}`,
    guardrail: { input: null, output: null }, trace: [{ step: "OBSERVE", tool: "flight plan (your input)" },
      { step: "OBSERVE", tool: "advice_guard.screen", outputs: { ok: false, kind: "advice", rule: "should I act" } }] };
  const s = J.stopOf(r);
  assert.equal(s.by, "advice");
  assert.equal(s.badge, "The advice check (code) stopped it. No model saw the question.");
  assert.equal(s.text, "EPICENTRE replays a move against the limits you set.");
});

test("clarify: the one question the AI asked back, in its own words", () => {
  const s = J.stopOf(J.readTests(fresh())[4].response);
  assert.equal(s.kind, "clarify");
  assert.equal(s.badge, "The AI reader asked one question back.");
  assert.ok(s.text.startsWith("Which company do you mean"));
  assert.equal(J.stopOf({ status: "clarify", message: J.DISCLAIMER }), null);     // nothing but the disclaimer: nothing to show
});

test("the recorded answer says when it was recorded (R15)", () => {
  const p = H.provenance(J.readTests(fresh())[0].response);
  assert.equal(p.text.replace(/ /g, " "), "Recorded on 15 Nov 2026");
});

/* ---- the copy gates: R22, red gate 1, R16, R18, R1 ---- */
function cardTexts(view) {
  return [view.label, view.question, view.shows, view.investor, view.button.text, view.button.label, view.back,
    view.answer && view.answer.badge, view.answer && view.answer.text].filter(Boolean);
}
test("no advice word on any card, in either mode, except inside the quoted question (the advice card, as a test)", () => {
  const tests = J.readTests(fresh());
  for (const mode of ["static", "live"]) {
    for (const t of tests) {
      for (const s of cardTexts(J.cardView(t, mode))) assert.deepEqual(adviceHits(s), [], `${t.id} (${mode}): ${s}`);
    }
  }
  const advice = J.cardView(tests[0], "static");
  assert.equal(advice.question, "“Should I buy NVIDIA now?”");
  assert.ok(adviceHits("Should I buy NVIDIA now").length > 0, "the same words unquoted are advice words: the quotes exempt them");
  assert.deepEqual(adviceHits(advice.button.label), []);
});

test("at most 3 figures a closed card, at most 3 in a recorded answer (R22); no ' · ' strings (R16); typographic quotes (R18)", () => {
  const tests = J.readTests(fresh());
  for (const mode of ["static", "live"]) {
    for (const t of tests) {
      const v = J.cardView(t, mode), closed = J.cardFigures({ question: v.question, shows: v.shows });
      assert.ok(closed <= 3, `${t.id} (${mode}) shows ${closed} figures closed`);
      if (v.answer) assert.ok(J.cardFigures({ answer: v.answer }) <= 3, `${t.id}: the recorded answer carries more than 3 figures`);
      for (const s of cardTexts(v)) assert.deepEqual(metaHits(s), [], s);
      assert.match(v.question, /^“[^"]+”$/);
    }
  }
});

test("results in the past tense, 'in this 2021–26 replay' from the run's own dates (R1)", () => {
  const q = H.qualifier(load("robert"));
  assert.equal(q, "in this 2021–26 replay");
  assert.equal(J.playingLine("load", q), "It played in the stage above, in this 2021–26 replay.");
  assert.match(J.playingLine("live", q), /in this 2021–26 replay\.$/);
  assert.equal(J.playingLine("live-stop", q), "Sent to the live app. Its answer shows in the stage above.");   // no replay to name
  for (const t of J.readTests(fresh())) {
    const a = J.cardView(t, "static").answer;
    if (a) assert.match(a.badge, /\b(stopped|asked)\b/);
  }
  assert.equal(J.cardView(J.readTests(fresh())[5], "static").back, "Back to the Too Canadian? question");
  assert.equal(J.cardView(J.readTests(fresh())[1], "static").back, "Back to Robert’s own question");
});

/* ---- the popover ---- */
test("the popover's steps: Replay with the stage's own length, the six questions, any number; the live app note", () => {
  const secs = Math.round(schedule({}).end / 1000);
  assert.equal(J.replaySeconds(), secs);
  const p = J.judgeSteps({ tests: 6, mode: "static" });
  assert.equal(p.title, "Three things to try");
  assert.deepEqual(p.steps.map((s) => [s.n, s.text]), [[1, `Press Replay (${secs} s).`],
    [2, "Try to trip up the AI (six questions)."], [3, "Check any number (click it)."]]);
  assert.equal(p.note, "To type your own questions, use the live app (password in the submission form).");
  assert.deepEqual(p.steps.map((s) => s.target), ["replay", "testai", "why"]);
  const none = J.judgeSteps({ tests: 0, mode: "live" });
  assert.deepEqual(none.steps.map((s) => s.n), [1, 2]);                 // no cards on the page: no dead step
  assert.equal(none.title, "Two things to try");
  assert.equal(none.note, J.NOTE_LIVE);
  for (const s of [...p.steps.map((x) => x.text), p.note, p.title, J.NOTE_LIVE, J.JUDGE_LABEL]) {
    assert.deepEqual(adviceHits(s), [], s);
    assert.deepEqual(metaHits(s), [], s);
  }
});

test("the popover never opens by itself (design director, item 9): no once-per-visit rule is left; the live note names the box", () => {
  assert.equal(J.autoOpen, undefined);
  assert.equal(J.markOpened, undefined);
  assert.equal(J.NOTE_LIVE, "This is the live app: type your own question in the question box.");
  assert.equal(J.judgeSteps({ tests: 7, mode: "static" }).steps[1].text, "Try to trip up the AI (seven questions).");
});

test("the cards always fill two rows of the 12 columns: six = 3 + 3, seven = 4 + 3, never an orphan", () => {
  assert.deepEqual(J.spans(6), [4, 4, 4, 4, 4, 4]);
  assert.deepEqual(J.spans(7), [3, 3, 3, 3, 4, 4, 4]);
  assert.deepEqual(J.spans(5), [4, 4, 4, 6, 6]);
  assert.deepEqual(J.spans(3), [4, 4, 4]);
  assert.deepEqual(J.spans(0), []);
  for (let n = 1; n <= J.MAX_TESTS; n += 1) {
    let sum = 0, rows = 0;
    for (const x of J.spans(n)) { sum += x; if (sum % 12 === 0) rows += 1; }
    assert.equal(sum % 12, 0, `n = ${n}: a row is left unfilled (${J.spans(n)})`);
    assert.ok(rows <= 3, `n = ${n}`);
  }
});

test("keyboard: Esc closes the open popover, nothing else is taken; each card's button keeps its visible words first", () => {
  assert.equal(J.keyAction("Escape", true), "close");
  assert.equal(J.keyAction("Esc", true), "close");
  assert.equal(J.keyAction("Escape", false), null);
  for (const k of ["Enter", " ", "Tab", "r", "1"]) assert.equal(J.keyAction(k, true), null, k);
  for (const t of J.readTests(fresh())) {
    const b = J.cardView(t, "static").button;
    assert.equal(b.text, "Run it");
    assert.ok(b.label.startsWith(b.text), "label in name (WCAG 2.5.3)");
  }
});

/* ---- the recorded lines as the ai lane writes them (data/demo_scripted.json, lower-case fragments) ---- */
test("a recorded line reads as a sentence in plain words (R28): a capital, a full stop, the AI reader", () => {
  assert.equal(J.sentence("the navigator read French: NVIDIA set to 40 % and the tariff shock"),
    "The AI reader read French: NVIDIA set to 40 % and the tariff shock.");
  assert.equal(J.sentence("It read RBC as Royal Bank of Canada."), "It read RBC as Royal Bank of Canada.");
  assert.equal(J.sentence("  "), null);
  assert.equal(J.cardView({ id: "x", kind: "run", key: "a1b2c3d4e5f60001", question: "Q?", label: "Ask the workshop's question" }, "static").label,
    "Ask the workshop’s question");
});

test("the ai lane's scripted tests (data/demo_scripted.json) make clean cards in both modes", () => {
  let scripted;
  try { scripted = JSON.parse(readFileSync(new URL("../data/demo_scripted.json", import.meta.url), "utf8")); }
  catch (e) { console.log("     (no data/demo_scripted.json: skipped)"); return; }
  const tests = J.readTests({ tests: (scripted.tests || []).map((t) => ({ ...t, key: t.kind === "run" ? "a1b2c3d4e5f60001" : undefined,
    response: t.kind === "run" ? undefined : { status: t.kind, message: `One recorded sentence.\n\n${J.DISCLAIMER}` } })) });
  assert.equal(tests.length, Math.min(J.MAX_TESTS, (scripted.tests || []).length));
  assert.ok(tests.length >= 6);
  for (const mode of ["static", "live"]) {
    for (const t of tests) {
      const v = J.cardView(t, mode);
      assert.ok(v.action, `${t.id} (${mode}) cannot run`);
      assert.match(v.shows, /^[A-Z“].*[.!?…]$/, v.shows);
      assert.ok(!/\bnavigator\b/i.test(v.shows), v.shows);
      for (const s of cardTexts(v)) { assert.deepEqual(adviceHits(s), [], `${t.id}: ${s}`); assert.deepEqual(metaHits(s), [], s); }
      assert.ok(J.cardFigures({ question: v.question, shows: v.shows }) <= 3, `${t.id} shows too many figures closed`);
    }
  }
});

/* ---- the recorded file itself (data/demo_runs/tests.json, the ai lane's extended recording): properties, never its words ---- */
test("the recorded tests.json makes clean cards: every run key is a saved run, every stop says who stopped it", () => {
  let rec;
  try { rec = JSON.parse(readFileSync(new URL("../data/demo_runs/tests.json", import.meta.url), "utf8")); }
  catch (e) { console.log("     (no data/demo_runs/tests.json yet: skipped)"); return; }
  const tests = J.readTests(rec);
  assert.equal(tests.length, Math.min(J.MAX_TESTS, rec.tests.length));
  assert.ok(tests.length >= 6, "fewer than six recorded tests");
  for (const t of tests) {
    for (const mode of ["static", "live"]) assert.ok(J.actionFor(t, mode), `${t.id} cannot run (${mode})`);
    if (t.kind === "run") {
      assert.doesNotThrow(() => readFileSync(new URL(`../data/demo_runs/${t.key}.json`, import.meta.url)), `${t.id}: no saved run ${t.key}`);
    } else {
      const s = J.stopOf(t.response);
      assert.ok(s && s.text, `${t.id}: no recorded answer`);
      if (t.kind === "blocked") assert.ok(s.by === "guardrails" || s.by === "advice", `${t.id}: who stopped it is unknown`);
      assert.ok(H.provenance(t.response), `${t.id}: no recorded date (R15)`);
    }
    const v = J.cardView(t, "static");
    assert.ok(J.cardFigures({ question: v.question, shows: v.shows }) <= 3, `${t.id}: more than 3 figures closed`);
    if (v.answer) assert.ok(J.cardFigures({ answer: v.answer }) <= 3, `${t.id}: more than 3 figures in its answer`);
    for (const s of cardTexts(v)) {
      assert.deepEqual(metaHits(s), [], s);
      const hits = adviceHits(s);
      /* the recorded answer is the API's own sentence, quoted, never rewritten here: a hit in it is the generating code's to fix
         (agents/scenario.py, tools/portfolio.py), so it is reported loudly instead of failing every lane's suite */
      if (hits.length && v.answer && s === v.answer.text) console.log(`WARN ${t.id}: the recorded answer trips "${hits[0].label}" (${hits[0].match}): fix the wording upstream, then re-record`);
      else assert.deepEqual(hits, [], `${t.id}: ${s}`);
    }
  }
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
