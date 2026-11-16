/* Lane agentlog ("Watch the AI work", ruling R42): the pure helpers of web/lib/agentlog.js under node, on committed fixtures only
   (ruling R17): tests/fixtures/agentlog_run.json (a cut of Robert's 13:44 live recording, where the number check caught one defect
   in draft 1 and the AI fixed it) and the four public cuts in tests/fixtures/web/. Run: node tests/web_agentlog_test.mjs */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { load, NAMES } from "./web_fixtures.mjs";

globalThis.PF = createRequire(import.meta.url)("../web/lib.js");
const L = await import("../web/lib/agentlog.js");
const run = () => JSON.parse(readFileSync(new URL("./fixtures/agentlog_run.json", import.meta.url), "utf8"));
const NB = " ";
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL", name); throw e; } };
const ids = (log) => log.rows.map((r) => r.id);
const byId = (log, id) => log.rows.find((r) => r.id === id);
const all = (log) => log.rows.map((r) => [r.text, r.sub, ...(r.quote || []), ...(r.items || []).flatMap((i) => [i.label, i.text])].filter(Boolean).join(" ")).join(" ");
const BANNED = /\b(buy|sell|hold|you should|recommend\w*|safe|allowed|you can)\b/i;

test("time readouts: under 1 ms, whole ms, seconds with one decimal; the tick lands on the exact value", () => {
  assert.equal(L.timeText(0.82), `<1${NB}ms`);
  assert.equal(L.timeText(6), `6${NB}ms`);
  assert.equal(L.timeText(639), `0.6${NB}s`);
  assert.equal(L.timeText(6250), `6.3${NB}s`);
  assert.equal(L.timeText(null), "");
  assert.equal(L.tickText(6250, 1), `6.3${NB}s`);
  assert.equal(L.tickText(6250, 0), `0.1${NB}s`);
  assert.equal(L.tickText(5, 0.2), `5${NB}ms`);
});

test("the timeline from the trace, in the pipeline's order, every row with its actor and its own time", () => {
  const log = L.logOf(run());
  assert.deepEqual(ids(log), ["guard-in", "search", "decide", "plan", "replay", "draft1", "caught", "draft2", "check", "guard-out", "memory-out", "effect"]);
  assert.deepEqual(log.rows.map((r) => r.part), ["read", "read", "read", "read", "compare", "explain", "explain", "explain", "explain", "explain", "explain", "after"]);
  assert.deepEqual(log.rows.map((r) => r.actor), ["guard", "code", "ai", "code", "code", "ai", "code", "ai", "code", "guard", "code", "code"]);
  const g = byId(log, "guard-in");
  assert.equal(g.text, "Guardrails checked your question: passed.");
  assert.equal(g.time, `0.6${NB}s`);                       // trace T3: 639 ms
  assert.equal(byId(log, "decide").time, `2.3${NB}s`);     // navigator.model_turn: 2272 ms
  assert.equal(byId(log, "draft1").time, `6.3${NB}s`);     // explain.draft: 6250 ms
  assert.equal(byId(log, "draft2").time, `5.8${NB}s`);
  assert.equal(log.model, "Claude Sonnet 5.5");
  assert.equal(log.recorded, `Recorded on 15${NB}Nov${NB}2026`);
  assert.ok(log.total > 10000 && log.totalText.endsWith(`${NB}s`));
});

test("the searches: code chose them (tool_calls[].chosen_by), each with its result count", () => {
  const s = byId(L.logOf(run()), "search");
  assert.equal(s.text, "Code searched the shock record 4 times, one kind of shock each, and checked where your money is.");
  assert.deepEqual(s.items, [{ label: "Tariff war", text: "3 found" }, { label: "War & oil", text: "3 found" },
    { label: "Chip war", text: "3 found" }, { label: "Rate shock", text: "3 found" }]);
  assert.equal(s.time, `<1${NB}ms`);
  const r = run();
  r.scenario.tool_calls.forEach((c) => { c.chosen_by = "model"; });
  const one = run();                                        // one search (a named shock): no comma before "and"
  one.scenario.tool_calls = [one.scenario.tool_calls[0], one.scenario.tool_calls[4]];
  assert.equal(byId(L.logOf(one), "search").text, "Code searched the shock record once and checked where your money is.");
  assert.match(L.loopOf(one).text, /code chose and ran both tool calls/);
  const s2 = byId(L.logOf(r), "search");
  assert.equal(s2.actor, "ai");
  assert.match(s2.text, /^The AI reader searched the shock record 4 times/);
});

test("the AI's decision: the move, the shock with the words it was read from, the precedents it picked", () => {
  const d = byId(L.logOf(run()), "decide");
  assert.equal(d.text, "The AI reader read your words and decided:");
  assert.deepEqual(d.items, [{ label: "The move", text: `NVIDIA → 40${NB}%` },
    { label: "The shock", text: "tariff war, from your words “Washington slaps new levies on Canadian goods”" },
    { label: "Precedents", text: "the 3 closest on record" }]);
  assert.equal(d.sub, "Claude Sonnet 5.5 on Amazon Bedrock, request daa1cb54");
  const r = run();
  r.scenario.read_from = "words that are not in the question";
  assert.equal(byId(L.logOf(r), "decide").items[1].text, "tariff war");   // never words the question does not hold
});

test("code checked the plan: what it kept, the kinds of shock it set aside and why", () => {
  const p = byId(L.logOf(run()), "plan");
  assert.equal(p.actor, "code");
  assert.equal(p.text, "Code checked every field of the plan against your words and its own searches: kept the move, the tariff war and 3 precedents; set aside three kinds of shock.");
  assert.deepEqual(p.items, [{ label: "Set aside", text: "War & oil, Chip war, Rate shock: no words in your question point to them" }]);
  const r = run();
  r.scenario.rejected = { war_oil: "War & oil: no words in your question point to it; best score 0.20.", rates: "Rate shock: no known shock at this date." };
  assert.deepEqual(byId(L.logOf(r), "plan").items, [{ label: "Set aside", text: "War & oil: no words in your question point to it" }, { label: "", text: "Rate shock: no known shock at this date" }]);
  const f = run();                                          // the plan refused: block and tell (workshop level 6)
  Object.assign(f.scenario, { method: "fallback", fallback_reason: "The navigator's answer was not used (the plan invented a move the investor did not ask for); the keyword rules answered." });
  const fl = L.logOf(f);
  assert.equal(byId(fl, "plan").status, "refused");
  assert.deepEqual(byId(fl, "plan").quote, ["the plan invented a move the investor did not ask for"]);
  assert.equal(byId(fl, "decide").text, "The AI reader answered.");
});

test("the self-correction: the defect named in draft 1, the re-ask, 15 of 15 on draft 2", () => {
  const log = L.logOf(run());
  const c = byId(log, "caught");
  assert.equal(c.status, "caught");
  assert.equal(c.text, "The number check caught one defect in draft 1 (14 of 15 numbers traced). Code told the AI exactly what was wrong:");
  assert.deepEqual(c.quote, ["Sentence 5 cites T32 for 34.5 % but does not name after. Name it or remove the number."]);
  assert.equal(byId(log, "draft2").text, "The AI rewrote the explanation with that one message (draft 2).");
  assert.equal(byId(log, "check").text, "The number check passed draft 2: 15 of 15 numbers traced to the data.");
  assert.equal(byId(log, "memory-out").text, "Code saved this run’s mistake for the next run’s prompt: a number that did not say what it measures.");
  assert.equal(log.fold, "One AI decision, checked by code; a defect caught and fixed.");
  const g = byId(log, "guard-out");
  assert.equal(g.text, "Guardrails checked the explanation against the facts: grounding 0.93, above the 0.70 bar.");
  assert.equal(g.time, `0.6${NB}s`);
});

test("a structure defect (word budget) is named as code's checks, not the number check", () => {
  const r = run();
  const d2 = r.trace.filter((t) => t.tool === "explain.draft")[1];
  d2.inputs.retry_numbers = ["The debrief has 194 words; keep it under 180: cut at least 24 words, the least needed sentence first."];
  r.receipt.first_try = { verified: 15, total: 15, defects: [] };
  const c = byId(L.logOf(r), "caught");
  assert.equal(c.text, "Code’s checks caught one defect in draft 1. Code told the AI exactly what was wrong:");
});

test("absent keys hide their rows; a first draft that passes shows no self-correction", () => {
  const r = run();
  delete r.guardrail; r.trace = r.trace.filter((t) => !/^guardrail\./.test(t.tool));
  delete r.receipt; delete r.navigator_effect;
  r.trace = r.trace.filter((t) => !(t.tool === "explain.draft" && t.inputs && t.inputs.retry_numbers) && t.tool !== "agents.memory.record");
  const log = L.logOf(r);
  for (const id of ["guard-in", "guard-out", "caught", "draft2", "check", "memory-out", "effect"]) assert.ok(!ids(log).includes(id), id);
  assert.equal(byId(log, "draft1").text, "The AI wrote the explanation from 84 computed facts.");
  assert.equal(L.logOf({ trace: [] }), null);
  assert.equal(L.logOf(null), null);
  for (const name of NAMES) {                               // the public cuts: first drafts that passed
    const lg = L.logOf(load(name));
    assert.ok(lg && !ids(lg).includes("caught") && !ids(lg).includes("draft2"), name);
    assert.match(byId(lg, "check").text, /on the first draft\.$/, name);
  }
});

test("the decisions the agent made: the code held the loop", () => {
  const lp = L.loopOf(run());
  assert.equal(lp.engine, "converse");
  assert.equal(lp.decisions, 1);
  assert.equal(lp.text, "The code held the loop: one AI decision, in one call; code chose and ran all 5 tool calls and checked the answer.");
  const r = run();
  Object.assign(r.scenario, { engine: "loop", decisions: 3 });
  r.scenario.tool_calls.forEach((c) => { c.chosen_by = "model"; });
  const l2 = L.loopOf(r);
  assert.equal(l2.cap, L.LOOP_CAP);
  assert.equal(l2.text, `The code held the loop: 3 of ${L.LOOP_CAP} AI decisions used; code ran each of the 5 tool calls the AI asked for.`);
  assert.equal(L.loopOf({ scenario: {} }), null);
});

test("what the AI changed (R37): the question answered, never the verdict", () => {
  const e = byId(L.logOf(run()), "effect");
  assert.equal(e.text, "Without the AI reader, the keyword rules read no shock in your words, so the shock check would have replayed every kind of shock instead of the tariff war you asked about. The verdict would have been the same: the AI changed the question answered, not the answer.");
  const r = run();                                          // the pipeline's own sentence (pipeline.ai_off_sentence) wins when present
  r.navigator_effect.sentence = "Switching the AI off changes no verdict here: Outside your limits either way. It changes the question answered: without it, the shock check replays all 26 episodes (worst −13.6 %) instead of the 6 tariff war episodes you asked about (worst −9.0 %).";
  assert.equal(byId(L.logOf(r), "effect").text, r.navigator_effect.sentence);
  r.navigator_effect.sentence = "Switching the AI off changes no verdict here: Outside your limits either way. It changes the question answered: without it, the shock check replays the None  episodes (worst −13.6 %) instead of the 6 tariff war episodes you asked about (worst −9.0 %).";
  assert.equal(byId(L.logOf(r), "effect").text, e.text);   // a sentence built on a missing key is not shown: the log's own words
});

test("the run screen's compressed clock fits the stage's schedule; live rows follow the server's steps", () => {
  const log = L.logOf(run());
  const T = { fly: 2200, lamp: 6720 };
  const s = L.scheduleOf(log.rows, T);
  const read = log.rows.filter((r) => r.part === "read").map((r) => s.at[r.id]);
  assert.ok(read.every((t, i) => t < T.fly && (i === 0 || t > read[i - 1])), String(read));
  assert.ok(s.at.replay > T.fly && s.at.replay < T.lamp);
  const exp = log.rows.filter((r) => r.part === "explain").map((r) => s.at[r.id]);
  assert.ok(exp.every((t, i) => t > T.lamp && (i === 0 || t > exp[i - 1])));
  assert.ok(s.end > exp[exp.length - 1] && s.end < 12000, String(s.end));
  assert.equal(s.at.effect, undefined);                     // the drawer's closing row is not on the run screen
  const live = L.liveRows([{ step: "OBSERVE", status: "done", ms: 812 }, { step: "UNDERSTAND", status: "running" }, { step: "COMPARE", status: "waiting" }]);
  assert.deepEqual(live.map((r) => [r.id, r.status, r.time]), [["live-OBSERVE", "done", `0.8${NB}s`], ["live-UNDERSTAND", "running", ""]]);
  assert.equal(live[1].text, "The AI reader is reading your words…");
});

test("plain words: no advice words, no internal names on screen, typographic quotes", () => {
  for (const r of [run(), ...NAMES.map(load)]) {
    const log = L.logOf(r), text = all(log) + " " + (L.loopOf(r) || {}).text + " " + log.fold;
    assert.ok(!BANNED.test(text.replace(/the AI wrote the explanation/gi, "")), text.match(BANNED));
    assert.ok(!/navigator|debrief|receipt|search_events|get_exposure|\bstorm\b/i.test(log.rows.filter((x) => x.id !== "caught" && x.id !== "plan").map((x) => [x.text, x.sub, ...(x.items || []).map((i) => i.text)].join(" ")).join(" ")), "internal names");
    assert.ok(!/["']/.test(log.rows.map((x) => x.text).join(" ")), "straight quotes");
  }
});

console.log(`web_agentlog_test: ${n} groups passed`);
