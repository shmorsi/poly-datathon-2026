/* Lane U2 (the Replay stage): the pure helpers of web/lib/replay.js under node. Self-contained on web/fake_result.json (in git);
   the saved real runs in /tmp (when this machine has them) add Robert's exact words. Design doc §2 item 2, rulings R1, R3, R13, R15. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
globalThis.PF = createRequire(import.meta.url)("../web/lib.js");
const R = await import("../web/lib/replay.js");
const load = (p) => JSON.parse(readFileSync(p, "utf8"));
const txt = (segs) => (segs || []).map((s) => s[0]).join("");
const NB = " ", M = "−";
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL", name); throw e; } };
const BANNED = /\b(buy|sell|hold|you should|we recommend|recommended|safe|allowed|you can|holds up to|fits)\b/i;

const fake = load(join(here, "..", "web", "fake_result.json"));

test("formatters: durations, model names, the recorded date, the replay's years", () => {
  assert.equal(R.duration(240), `240${NB}ms`);
  assert.equal(R.duration(2522), `2.5${NB}s`);
  assert.equal(R.duration(null), "");
  assert.equal(R.modelName("us.anthropic.claude-sonnet-5-5"), "Claude Sonnet 5.5");
  assert.equal(R.modelName("fake-model"), "fake-model");
  assert.equal(R.recordedOn({ message: "Demo mode: this is the saved run for this exact question, recorded on 15 Nov 2026." }), `15${NB}Nov${NB}2026`);
  assert.equal(R.recordedOn({ message: null }), null);
  assert.equal(R.replayYears(fake), "2021–26");
});

test("the five steps from the trace, folded live progress, one receipt line", () => {
  const rows = R.stepRows(fake);
  assert.deepEqual(rows.map((s) => s.step), R.STEPS);
  assert.ok(rows.every((s) => s.status === "done" && s.service));
  const noModel = { ...fake, trace: fake.trace.filter((t) => t.step !== "EXPLAIN" && t.step !== "VERIFY") };
  assert.deepEqual(R.stepRows(noModel).map((s) => s.status), ["done", "done", "done", "skipped", "skipped"]);
  let live = R.foldStep(null, null);
  assert.ok(live.every((s) => s.status === "waiting"));
  live = R.foldStep(live, { type: "progress", step: "OBSERVE", status: "run", service: "Bedrock Guardrails", ms: null });
  assert.equal(live[0].status, "running");
  live = R.foldStep(live, { type: "progress", step: "OBSERVE", status: "done", service: "Bedrock Guardrails", ms: 1045 });
  live = R.foldStep(live, { type: "progress", step: "UNDERSTAND", status: "detail", detail: "Shocks to replay: Tariff war." });
  assert.equal(live[0].ms, 1045); assert.equal(live[1].detail, "Shocks to replay: Tariff war.");
  const saved = R.receiptOf(rows, fake);
  assert.match(saved.text, /^5 steps in \d+\.\d s, with Amazon Bedrock and Guardrails\.$/);
  assert.match(saved.sub, /^Recorded earlier\./);                                   // R15: a saved run never looks live
  const replay = R.receiptOf(rows, { ...fake, mode: "demo_replay", message: "Demo mode: this is the saved run for this exact question, recorded on 15 Nov 2026." });
  assert.equal(replay.sub, `Recorded on 15${NB}Nov${NB}2026.`);
  assert.equal(R.receiptOf(rows, fake, { live: true }).sub, null);
  assert.match(R.receiptOf(R.stepRows(noModel), noModel).sub, /2 steps not run/);
});

test("the reading as chips: the move, the family, the precedents, who read it, the families set aside", () => {
  const rd = R.readingOf(fake);
  assert.equal(rd.move.value, `NVIDIA → 40${NB}%`);
  assert.equal(rd.move.sub, null);                                       // how it was funded is its own line now (fundingLine)
  assert.equal(R.fundingLine(fake).kind, "assumed");
  assert.equal(rd.family.value, "Tariff war");
  assert.equal(rd.precedents.value, "6 earlier episodes");
  assert.equal(rd.by.kind, "model"); assert.equal(rd.by.service, "Amazon Bedrock");
  assert.ok(rd.aside.labels.length === 3);
  assert.deepEqual(R.editRange(rd.question, rd.move.needles), [rd.question.indexOf("40 %"), rd.question.indexOf("40 %") + 4]);
  /* never claim Bedrock when it did not run: the keyword fallback, or no model row in the trace */
  const rules = { ...fake, scenario: { ...fake.scenario, method: "fallback" } };
  assert.equal(R.readingOf(rules).by.service, "Code rules");
  const noRow = { ...fake, trace: fake.trace.filter((t) => t.service !== "Amazon Bedrock") };
  assert.equal(R.readingOf(noRow).by.service, "Code rules");
  const none = { ...fake, question_type: "shock", scenario: { ...fake.scenario, change: null } };
  assert.equal(R.readingOf(none).move.value, "Your mix, unchanged");
});

test("the epicentre: the asked family's deepest trough on the evaluated mix", () => {
  const ev = R.worstPrecedent(fake);
  assert.equal(ev.id, "liberation_day_2025");
  assert.equal(ev.dateText, `3${NB}Apr${NB}2025`);
  assert.equal(ev.troughText, `${M}9.0${NB}%`);
  assert.equal(R.worstPrecedent({ ...fake, scenario: { ...fake.scenario, families: [] } }), null);
});

test("the lamp: the server's verdict at the asked size, a what-if anywhere else (never the verdict words, never green)", () => {
  const lamp = R.lampOf(fake, null);
  assert.equal(lamp.word, "Outside your limits"); assert.equal(lamp.tone, "outside");
  assert.equal(lamp.qualifier, "in this 2021\u201326 replay");
  assert.equal(lamp.whatIf, false); assert.equal(lamp.caption, null);
  assert.equal(R.lampOf(fake, R.askedIndex(fake)).whatIf, false);                    // the asked size is the run's own verdict
  const curve = fake.tipping_point.curve, floor = fake.limits.floor;
  const at = (i) => R.lampOf(fake, i), words = new Set(["Inside your limits", "Inside, with caveats", "Outside your limits"]);
  curve.forEach((c, i) => {
    if (i === R.askedIndex(fake)) return;
    const w = at(i);
    assert.equal(w.whatIf, true); assert.ok(!words.has(w.word), w.word); assert.notEqual(w.tone, "inside");
    assert.match(w.caption, /^What-if at \d+\u00a0% NVIDIA instead of the 40\u00a0% you asked\. A replay, not a recommendation\.$/);
    if (c.verdict === "Incompatible") assert.equal(w.word, "Broke your floor");
  });
  /* touched: inside, and the worst fall within 1 point of the floor after rounding to a tenth (pitfall 5) */
  const near = JSON.parse(JSON.stringify(fake));
  near.tipping_point.curve[5] = { ...near.tipping_point.curve[5], verdict: "Compatible", max_drawdown: floor + 0.0099 };
  assert.equal(R.lampOf(near, 5).word, "Touched your floor"); assert.equal(R.lampOf(near, 5).tone, "caveat");
  near.tipping_point.curve[5].max_drawdown = floor + 0.02;
  assert.equal(R.lampOf(near, 5).word, "Held above your floor"); assert.equal(R.lampOf(near, 5).icon, null);
  assert.equal(R.withoutLine(fake).text, "Without the move: inside your limits.");
  assert.equal(R.lampOf({ question: "x" }, null), null);
});

test("sentence 1, the money (R13, R35): the path's own dollars, the 15 % rule never called a dollar limit", () => {
  const s1 = txt(R.moneyLine(fake));
  assert.match(s1, /^With 40\u00a0% in NVIDIA, this mix fell 34\.5\u00a0% at its worst/);
  assert.match(s1, /That broke your floor: no fall of more than 15\u00a0% from any high \(assumed for this fictional profile\)\.$/);
  assert.doesNotMatch(s1, /the same fall on your|set as your limit/);                       // R35: never again
  const deep = [...fake.breaches].sort((x, y) => x.depth - y.depth)[0];
  if (typeof deep.peak_value === "number") assert.ok(s1.includes(globalThis.PF.fmt.money(deep.peak_value)));
  const mine = { ...fake, pilot: null };
  assert.match(txt(R.moneyLine(mine)), /, typed by you\.$/);
});

test("the check that decided the lamp, when neither sentence names it (R14)", () => {
  assert.equal(R.decidingLine(fake), null);                                          // Robert: the floor decided, sentence 1 says so
  const values = { ...fake, verdict: "Tension", checks: [
    { rule: "max_drawdown", tier: "hard", status: "pass", value: -0.11, limit: -0.25, reason: "In this history the mix's worst drop was 11 %." },
    { rule: "esg_direct", tier: "preference", status: "fail", value: 0.08, limit: 0, name: "Values",
      reason: "CNQ.TO is owned directly (8.0 % of the money) and excluded by the values screen you asked for; the limit is 0 %." }] };
  const d = R.decidingLine(values);
  assert.equal(d.name, "your values");
  assert.equal(d.lead, "The check that added the caveat:");                           // never "decided by"
  assert.match(d.text, /^CNQ\.TO is owned directly \(8\.0\u00a0% of the money\)/);
  assert.equal(R.lampOf(values, null).tone, "caveat");                               // drawn in the lamp's tone, not a red row
  assert.equal(R.decidingLine({ ...values, verdict: "Compatible" }), null);          // inside: a caution never reads as the reason
  assert.equal(R.readingOf(fake).whose, "Robert\u2019s question");
  assert.equal(R.readingOf({ ...fake, pilot: "canadian", profile: { ...fake.profile, name: "Too Canadian?" } }).whose, "The \u201cToo Canadian?\u201d question");
});

test("sentence 2, the asked shock, in the past tense (R1)", () => {
  const s2 = R.shockLine(fake);
  assert.equal(txt(s2.segs), `In the 6 tariff war episodes on record, this mix lost up to 9.0${NB}% within a shock\u2019s window, more than the 7.5${NB}% shock limit assumed for this profile.`);
  assert.doesNotMatch(txt(s2.segs), /\bif\b|flares up/i);
  const thin = { ...fake, checks: fake.checks.map((c) => (c.rule === "scenario_stress" ? { ...c, value: null, reason: "There is no close precedent at this date for tariffs shocks, so the shock check cannot conclude." } : c)) };
  assert.match(txt(R.shockLine(thin).segs), /^There is no close precedent/);
});

test("the money twist (R3, R35, one name): ended higher, broke your floor, the capacity from result.capacity, no 'Both are true.'", () => {
  const tw = R.twistLine(fake);
  assert.equal(txt(tw.segs), `Ended higher. Broke your floor twice on the way.`);
  const cap = { ...fake, capacity: { line: 510000, after: { falls_below: 1, first_below: "2022-05-09", last_below: "2022-12-20", status: "broke" },
    today: { falls_below: 0, status: "held" } } };                                                      // lane fin-backend's shape
  assert.equal(txt(R.twistLine(cap).segs), `Ended higher. Broke your floor twice on the way; fell below the $510,000 you can afford once, in${NB}2022.`);
  assert.doesNotMatch(txt(R.twistLine(cap).segs), /Both are true/);
  assert.equal(tw.breaches, 2);
  assert.equal(R.twistLine({ ...fake, breaches: [] }), null);
  const lower = JSON.parse(JSON.stringify(fake));
  lower.tipping_point.curve[R.askedIndex(fake)].end_value = 1;
  assert.equal(R.twistLine(lower), null);                                            // no twist when the move ended lower
});

test("the timeline: one beat after another, the phases of store.phase, the ease of the tokens", () => {
  for (const T of [R.schedule(), R.schedule({ live: true })]) {
    /* the signature moment: the race lands, the thread draws from the inset Earth, the crosshair opens, then the verdict lights */
    const order = ["chips", "aside", "fly", "caption", "handoff", "by", "race", "leader", "pin", "lamp", "lines", "twist", "end"];
    assert.ok(T.leader >= T.race + T.raceMs && T.pin >= T.leader + T.leaderMs && T.leaderMs === 500, "the thread draws after the race (500 ms)");
    assert.ok(T.fly + T.flyMs < T.handoff, "R7: the zoom to the epicentre ends, and holds, before the Earth docks");
    assert.ok(T.live || T.step0 + 5 * T.stepGap <= T.fly, "the five steps have streamed before the zoom");
    order.slice(1).forEach((k, i) => assert.ok(T[k] > T[order[i]], `${order[i]} < ${k}`));
    assert.equal(R.phaseAt(T.fly - 1, T), "reading"); assert.equal(R.phaseAt(T.fly, T), "flying");
    assert.equal(R.phaseAt(T.race + 1, T), "racing"); assert.equal(R.phaseAt(T.end, T), "landed");
    assert.ok(T.raceMs <= 2400 && T.flyMs === 900 && T.lampMs <= 400);
  }
  assert.equal(R.easeInOut(0), 0); assert.equal(R.easeInOut(1), 1);
  let last = -1;
  for (let p = 0; p <= 1.0001; p += 0.05) { const v = R.easeInOut(p); assert.ok(v >= last); last = v; }
});

test("one voice and typographic quotes (R18): no his/her in the instrument, curly quotes and apostrophes", () => {
  assert.equal(R.smart('"Liberation Day" reciprocal tariffs'), "\u201cLiberation Day\u201d reciprocal tariffs");
  assert.equal(R.smart("Trump's Taiwan remarks"), "Trump\u2019s Taiwan remarks");
  const ev = R.worstPrecedent({ ...fake, events: fake.events.map((e) => (e.event_id === "liberation_day_2025" ? { ...e, title: '"Liberation Day" reciprocal tariffs' } : e)) });
  assert.equal(ev.title, "\u201cLiberation Day\u201d reciprocal tariffs");
  const all = [txt(R.moneyLine(fake)), txt(R.shockLine(fake).segs), txt(R.twistLine(fake).segs), R.readingOf(fake).move.value];
  for (const w of all) { assert.doesNotMatch(w, /\b(his|her|him)\b/i, w); assert.ok(!/["']/.test(w), w); }
});

/* R17: values are pinned only on committed fixtures (web/fake_result.json above, tests/fixtures/web/*.json when present); the saved
   runs under /tmp, when this machine has them, get shape checks only (no advice word, no middle-dot meta string, the reading never
   claims a model the trace does not show), and skip when absent */
const FIXTURES = join(here, "fixtures", "web");
const RUNS = [FIXTURES, "/tmp/epi_runs_v1", "/tmp/epi_video/runs"];
const real = (id) => RUNS.map((d) => join(d, `${id}.json`)).find(existsSync);
test("every investor's words: no advice word, no middle-dot meta string, the reader named truthfully (shape checks)", () => {
  for (const id of ["robert", "mateo", "amira", "canadian"]) {
    const p = real(id);
    if (!p) continue;
    const r = load(p), rd = R.readingOf(r);
    const words = [txt(R.moneyLine(r)), txt((R.shockLine(r) || {}).segs), txt((R.twistLine(r) || {}).segs), rd.move.value, rd.move.sub || "",
      rd.family.value, (rd.precedents || {}).value || "", rd.by.service, rd.by.model || "", (R.lampOf(r, null) || {}).qualifier || "",
      (R.receiptOf(R.stepRows(r), r) || {}).text || ""];
    for (const w of words) { assert.doesNotMatch(w, BANNED, `${id}: ${w}`); assert.ok(!w.includes(" \u00b7 "), `${id}: ${w}`); }
    const modelRow = (r.trace || []).some((t) => t && t.step === "UNDERSTAND" && t.service === "Amazon Bedrock" && t.model);
    if (!modelRow || (r.scenario && r.scenario.method === "fallback")) assert.equal(rd.by.service, "Code rules", id);
    assert.ok(R.lampOf(r, null) === null || /^in this (\d{4}\u2013\d{2} )?replay$/.test(R.lampOf(r, null).qualifier), id);
  }
});

/* ---- lane u2b: R20 on the committed fixtures, R22's one question and one answer, the reframe, the AI's words ---- */
const FIX = ["robert", "mateo", "amira", "canadian"].map((id) => [id, load(join(here, "fixtures", "web", `${id}.json`))]);
const robert = FIX[0][1];
const shockAns = (r) => { const c = r.checks.find((x) => x.rule === "scenario_stress"), P = globalThis.PF.fmt;
  return `${c.status === "pass" ? "No: the shock stayed inside" : "Yes: the shock went past"} your limit (${P.pct(c.value)} against ${P.share(c.limit).replace("\u2212", "")}).`; };

const otherAns = (r, x) => { const c = r.checks.find((y) => y.rule === "scenario_stress");   // cold user 3: one breath when the shock passed
  return c.status === "pass" ? shockAns(r).replace(/\)\.$/, `), but your mix is outside for another reason: ${x}.`) : `${shockAns(r)} Your mix is outside for another reason: ${x}.`; };
const { dialModel } = await import("../web/lib/dial.js");
test("R20 on the fixture: 9 % broke, 8 % and 7 % touched, 6 % and 5 % held (the server's floor_margin_pp), never green", () => {
  const at = (i) => R.lampOf(robert, i), w = (i) => robert.tipping_point.curve[i].weight;
  assert.equal(w(9), 0.09); assert.equal(at(9).word, "Broke your floor"); assert.equal(at(9).tone, "outside");
  for (const i of [8, 7]) { assert.equal(at(i).word, "Touched your floor"); assert.equal(at(i).tone, "caveat"); assert.equal(at(i).icon, "i-warn"); }
  for (const i of [6, 5]) { assert.equal(at(i).word, "Held above your floor"); assert.equal(at(i).icon, null); assert.notEqual(at(i).tone, "inside"); }
  assert.equal(at(8).caption, `What-if at 8${NB}% NVIDIA instead of the 40${NB}% you asked. A replay, not a recommendation.`);
  /* the lamp and lane U4's ruler beside it name every size the same way, and agree with the server's own margin */
  for (const [id, r] of FIX) {
    const m = dialModel(r, globalThis.PF), asked = R.askedIndex(r);
    if (!m) continue;
    r.tipping_point.curve.forEach((c, i) => {
      if (i === asked) return;
      const l = R.lampOf(r, i), cls = { "Broke your floor": "broke", "Touched your floor": "touched", "Held above your floor": "held" }[l.word];
      assert.equal(cls, m.points[i].floorCls, `${id} ${i}`);
      if (typeof c.floor_margin_pp === "number") assert.equal(cls, c.verdict === "Incompatible" ? "broke" : c.floor_margin_pp <= 1 ? "touched" : "held", `${id} ${i}`);
    });
  }
});

test("R22: one plain question and one past-tense answer, its years from the Result's floor breaches", () => {
  assert.equal(R.askLine(robert), "Would this move have broken your limit?");
  assert.equal(txt(R.answerLine(robert).segs), `Yes: your floor (your limit on the biggest drop: 15${NB}% from a high) broke in${NB}2022 and again in${NB}2025.`);
  assert.equal(R.answerLine(robert).segs.filter((x) => x[1] === "num").length, 2);
  const one = { ...robert, breaches: robert.breaches.slice(0, 1) };
  assert.equal(txt(R.answerLine(one).segs), `Yes: your floor (your limit on the biggest drop: 15${NB}% from a high) broke in${NB}2022.`);
  assert.equal(txt(R.answerLine(FIX[1][1]).segs), shockAns(FIX[1][1]));                  // R39: a shock question is answered for the shock
  assert.equal(R.askLine(FIX[2][1]), "Would this shock have broken your limit?");           // Amira asks about a shock, no move
  assert.equal(txt(R.answerLine(FIX[3][1]).segs), "No: it stayed inside your limits.");
  assert.equal(R.answerLine({ ...robert, verdict: null }), null);
  for (const [id, r] of FIX) assert.doesNotMatch(txt((R.answerLine(r) || {}).segs), BANNED, id);
});

test("R22: the closed end frame shows at most 6 figures besides the chart's, the ruler's and its labels (fixtures)", () => {
  for (const [id, r] of [...FIX, ["fake", fake]]) {
    const c = R.closedTexts(r), count = c.figures.reduce((a, t) => a + R.figuresIn(t), 0);
    assert.ok(count <= 6, `${id}: ${count} figures: ${c.figures.filter((t) => R.figuresIn(t)).join(" | ")}`);
    for (const t of c.figures) assert.doesNotMatch(t, BANNED, id);
  }
  assert.equal(R.figuresIn(`fell ${M}34.5${NB}% from a high: $207,000 on $600,000`), 3);
  assert.equal(R.receiptOf(R.stepRows(fake), fake).short, "Five steps, with Amazon Bedrock and Guardrails.");
  /* the epicentre's caption counts trading days on a daily series only (the public cut is weekly: it counts weeks) */
  const ep = R.epiLines(R.worstPrecedent(robert), "this mix");
  assert.equal(ep.fig + ep.win, `${M}9.0${NB}% in the 4 weeks after it`);
  const days = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2025, 3, 1 + i)).toISOString().slice(0, 10));
  const daily = { ...robert, series: { ...robert.series, dates: days } };
  assert.match(R.epiLines(R.worstPrecedent(daily), "this mix").win, /^ in the shock’s \d+ trading days$/);
});

test("the reframe: advice_guard.REFRAME_LINE word for word, only when the Result carries reframe, and then no yes or no", () => {
  const py = readFileSync(join(here, "..", "advice_guard.py"), "utf8");
  const m = /REFRAME_LINE = \(([\s\S]*?)\)\n/.exec(py);
  const line = m[1].match(/"([^"]*)"/g).map((q) => q.slice(1, -1)).join("");
  assert.equal(R.REFRAME_LINE, line);
  assert.equal(R.reframeLine(robert), null);
  const asked = { ...robert, reframe: { reason: "asks whether a move or a size is right for you" } };
  assert.equal(R.reframeLine(asked), R.smart(line));
  assert.ok(R.reframeLine(asked).includes("can’t"));
  assert.equal(txt(R.answerLine(asked).segs), `Your floor (your limit on the biggest drop: 15${NB}% from a high) broke in${NB}2022 and again in${NB}2025.`);
  assert.equal(txt(R.answerLine({ ...FIX[3][1], reframe: { reason: "x" } }).segs), "It stayed inside your limits.");
});

test("the AI's translation: the family chip names the words it was read from only when the Result carries them, as written", () => {
  const q = "Everyone is talking about NVIDIA. What if I put 40 % in it and Washington slaps new levies on Canadian goods?";
  const base = { ...fake, question: q };
  assert.equal(R.readingOf(base).family.from, null);
  const said = { ...base, scenario: { ...base.scenario, read_from: "new levies on Canadian goods" } };
  assert.equal(R.readingOf(said).family.value, "Tariff war");
  assert.equal(R.readingOf(said).family.from, "read from: new levies on Canadian goods");
  assert.deepEqual(R.editRange(q, R.readingOf(said).family.needles), [q.indexOf("new levies"), q.indexOf("new levies") + "new levies on Canadian goods".length]);
  assert.equal(R.readingOf({ ...said, scenario: { ...said.scenario, read_from: "tariffs on steel" } }).family.from, null);   // not in the question
  assert.ok(R.editRange(q, R.readingOf(base).family.needles));                                 // Edit still finds "new levies"
});

test("the deciding line uses the page's status words (web/lib/status.js bindingWord)", () => {
  const m = R.decidingLine(FIX[1][1]);
  assert.equal(m.lead, "The check that added the caveat:"); assert.equal(m.name, "your values");
  assert.equal(R.decidingLine(robert), null);                                                   // the floor: the answer names it
});

test("the AI's value in one line: navigator_effect's family row only, the blind measure from eval_results.json", () => {
  assert.equal(R.effectLine(robert), null);                            // the saved run differs on precedents only: no line
  const q = "Everyone is talking about NVIDIA. What if I put 40 % in it and Washington slaps new levies on Canadian goods?";
  const fx = { ...robert, question: q, navigator_effect: { same: false, diffs: [{ what: "families", navigator: ["tariffs"], fallback: [] }] } };
  assert.equal(R.effectLine(fx).text, "The AI reader read your words as the tariff war; a plain word search found no shock.");
  const said = { ...fx, scenario: { ...fx.scenario, read_from: "new levies on Canadian goods" } };
  assert.equal(R.effectLine(said).text, "The AI reader read “new levies on Canadian goods” as the tariff war; a plain word search found no shock.");
  const other = { ...fx, navigator_effect: { diffs: [{ what: "families", navigator: ["tariffs"], fallback: ["rates"] }] } };
  assert.equal(R.effectLine(other).text, "The AI reader read your words as the tariff war; a plain word search read them as a rate shock.");
  const ev = load(join(here, "..", "web", "eval_results.json"));
  const h = ev.holdout_v2;
  assert.equal(R.evalLine(ev), `On ${h.n} blind questions the AI reader read the shock right ${h.navigator_k} times, a plain word search ${h.keyword_k}.`);
  assert.equal(R.evalLine({}), null);
  /* R22: no dollar figure in the closed stage (each dollar amount appears once, in the race's own callouts) */
  for (const [id, r] of [...FIX, ["fx", said]]) for (const t of R.closedTexts(r).figures) assert.doesNotMatch(t, /\$/, id);
  assert.ok(R.closedTexts(said).figures.reduce((a, t) => a + R.figuresIn(t), 0) <= 6);
});

test("pre-freeze: the start-month line from lane U4's band, the callout's named high, each step's parts as the trace times them", () => {
  const m = dialModel(robert, globalThis.PF);
  /* F6: the band says why it is wide, from its own starts (the falls named only when each start carries its break's date) */
  assert.equal(txt(R.bandLine(robert)), `Depending on the start month, your floor first broke at 9\u201310${NB}% (starts to Apr${NB}2022) or at ${m.band.hiText} (starts after Aug${NB}2022).`);
  const dated = JSON.parse(JSON.stringify(robert));
  dated.tipping_band.starts.forEach((x) => { x.break_date = x.first_break >= 0.35 ? "2025-03-10" : "2022-05-09"; });
  assert.equal(txt(R.bandLine(dated)), `Two falls decide it: 2022 breaks it from 9\u201310${NB}%; for starts after Aug${NB}2022 only early 2025 does, from 35${NB}%.`);
  assert.equal(R.bandLine({ ...robert, tipping_band: undefined }), null);
  const { raceModel } = { raceModel: (r) => ({ breaches: [{ labelKind: null, label: null, peakDate: "2021-11-29", depthText: "x" },
    { labelKind: "event", label: "old", eventId: "liberation_day_2025", peakDate: "2025-01-23", depthText: `${M}16.9${NB}%` }] }) };
  const out = R.relabelFalls(raceModel(robert), robert);
  assert.equal(out.breaches[1].label, `From the ${globalThis.PF.fmt.month("2025-01-23")} high, through \u201cLiberation Day\u201d`);
  assert.equal(out.breaches[1].depthText, `${M}16.9${NB}%`); assert.equal(out.breaches[0].label, null);
  const same = R.relabelFalls({ breaches: [{ labelKind: "event", label: "kept", eventId: "liberation_day_2025", peakDate: "2025-04-01" }] }, robert);
  assert.equal(same.breaches[0].label, "kept");                                       // a high in the shock's own month: as it was
  /* Observe = every row the trace files under it; the guardrail's part is its own rows' ms (#how's "Input guardrail" station) */
  const obs = R.stepRows(robert)[0], rows = robert.trace.filter((t) => t.step === "OBSERVE");
  const guard = rows.filter((t) => /apply_guardrail\(INPUT\)/.test(t.tool)).reduce((a, t) => a + t.ms, 0);
  assert.equal(obs.ms, rows.reduce((a, t) => a + (t.ms || 0), 0));
  assert.equal(obs.parts.find((p) => p.service === "Bedrock Guardrails").ms, guard);
  assert.equal(obs.parts.reduce((a, p) => a + p.ms, 0), obs.ms);
});

test("R20 on the phone pill and the line about today's mix: at a what-if size no verdict word and no pass mark", () => {
  const VERDICTS = /Inside your limits|Outside your limits|Inside, with caveats/;
  for (const [id, r] of FIX) {
    const curve = (r.tipping_point || {}).curve || [], asked = R.askedIndex(r);
    curve.forEach((c, i) => {
      if (i === asked) return;
      const p = R.pillOf(r, i);
      assert.doesNotMatch(p.word, VERDICTS, `${id} ${i}`); assert.notEqual(p.tone, "inside", `${id} ${i}`); assert.notEqual(p.icon, "i-in");
      assert.match(p.rest, /^, what-if at \d+ % \S/, `${id} ${i}`);
      for (const t of R.closedTexts(r, i).figures) assert.doesNotMatch(t, VERDICTS, `${id} ${i}: ${t}`);
    });
    if (asked !== null && curve.length) assert.equal(R.pillOf(r, asked).rest, `, ${R.lampOf(r, null).qualifier}`);
  }
  assert.equal(R.pillOf(robert, 8).word, "Touched your floor");
  assert.equal(R.pillOf(robert, 8).rest, `, what-if at 8${NB}% NVIDIA`);
  assert.equal(R.pillOf(robert, null).word, "Outside your limits");
});

/* ---- the usability round: the answer names the check that DECIDED the verdict (never a hard-coded floor sentence) ---- */
const hard = (r, rule) => ({ ...r, verdict: "Incompatible", checks: r.checks.map((c) => (c.rule === rule ? { ...c, tier: "hard", status: "fail" } : c)) });
test("the answer per investor: Robert's floor, Mateo's values screen when it decides, inside verdicts as they were", () => {
  assert.equal(txt(R.answerLine(robert).segs), `Yes: your floor (your limit on the biggest drop: 15${NB}% from a high) broke in${NB}2022 and again in${NB}2025.`);
  const mateo = FIX[1][1], amira = FIX[2][1], canadian = FIX[3][1];
  assert.equal(txt(R.answerLine(mateo).segs), shockAns(mateo));                                          // R39: his question is a shock
  const mateoOut = hard(mateo, "esg_direct");                                                              // the re-recorded run's tier
  assert.equal(R.decidingCheck(mateoOut).rule, "esg_direct");
  assert.equal(txt(R.answerLine(mateoOut).segs), otherAns(mateoOut, "the companies you avoid (you own CNQ.TO directly)"));
  const moveOut = hard({ ...robert, checks: robert.checks.map((c) => (c.rule === "max_drawdown" ? { ...c, status: "pass" } : c)).concat([{ rule: "esg_direct", status: "fail", tier: "hard", holding: "CNQ.TO", name: "Values", reason: "x" }]) }, "esg_direct");
  assert.equal(txt(R.answerLine(moveOut).segs), "Yes: you own CNQ.TO directly, one of the companies you avoid.");   // a move question
  assert.doesNotMatch(txt(R.answerLine(mateoOut).segs), /floor/);
  assert.equal(R.decidingLine(mateoOut), null);                          // said once: the answer names it, no second line under the chart
  assert.equal(txt(R.answerLine(amira).segs), shockAns(amira));
  assert.equal(txt(R.answerLine(hard(amira, "crypto")).segs), otherAns(amira, "your crypto limit"));
  assert.equal(txt(R.answerLine(canadian).segs), "No: it stayed inside your limits.");
  assert.equal(R.decidingCheck(robert).rule, "max_drawdown");
  const real = "/tmp/epi_runs_v1/mateo.json";                                                              // shape only (R17)
  if (existsSync(real)) { const r = load(real); if (r.verdict === "Incompatible" && R.decidingCheck(r) && R.decidingCheck(r).rule !== "max_drawdown") assert.doesNotMatch(txt(R.answerLine(r).segs), /floor broke/); }
});

test("under the verdict: the shock asked about and what broke the floor, then one proof line (every number a Result key)", () => {
  const c = robert.checks.find((x) => x.rule === "scenario_stress");
  const ev = R.worstPrecedent(robert);
  const when = ev.windowDays ? ` in ${ev.windowDays} trading days` : ` in the ${ev.windowWeeks} weeks after it`;
  assert.equal(txt(R.shockAskedLine(robert)), `The tariff shock you asked about: ${globalThis.PF.fmt.pct(c.value)}${when}, past your 7.5${NB}% shock limit (a rule of thumb: half your 15${NB}% floor).`);
  assert.equal(globalThis.PF.fmt.pct(c.value), ev.troughText);              // the check's fall is the epicentre's: one number, said once
  const deep = [...robert.breaches].sort((a, b) => a.depth - b.depth)[0];
  assert.equal(txt(R.floorBrokeLine(robert)), `What broke your floor: the 2022 fall, ${globalThis.PF.fmt.pct(deep.depth)}.`);
  assert.equal(R.floorBrokeLine(FIX[1][1]), null);                         // the floor held: no such line
  const rc = robert.receipt;
  assert.equal(R.proofLine(robert), `Every number checked by code: ${rc.verified} of ${rc.total}. Read by Claude on Amazon Bedrock, with Guardrails on.`);
  assert.equal(R.proofLine({ ...robert, guardrail: null }), `Every number checked by code: ${rc.verified} of ${rc.total}. Read by Claude on Amazon Bedrock.`);
  for (const [id, r] of FIX) for (const t of R.closedTexts(r).notes) { assert.doesNotMatch(t, BANNED, id); assert.doesNotMatch(t, / · /, id); }
});

test("where the money comes from: the words' from_ticker, else the replay's assumption, marked as one (flag missing information)", () => {
  assert.equal(R.fundingLine(robert).text, `Your words didn’t say where the 40${NB}% comes from, so the replay took it from every other holding in proportion (assumed).`);
  assert.equal(R.fundingLine(robert).kind, "assumed");
  const named = { ...robert, scenario: { ...robert.scenario, change: { op: "replace", ticker: "NVDA", weight: 0.4, from_ticker: "XBB.TO" } } };
  assert.equal(R.fundingLine(named).text, "Taken from your Canadian bonds (XBB.TO), as your words said.");
  assert.equal(R.fundingLine(named).kind, "said");
  assert.equal(R.fundingLine(FIX[1][1]), null);                             // no move: nothing was funded
  const tc = robert.scenario.tool_calls.find((t) => t.tool === "propose_change");
  if (tc && tc.output_summary && typeof tc.output_summary.others_scaled_by === "number") assert.ok(tc.output_summary.others_scaled_by < 1);   // "in proportion": one factor for all
});

test("R36 robustness facts from lane fin-backend's keys (hidden while a key is absent), R38 inside never green", () => {
  assert.equal(R.peerLine(robert), null); assert.equal(R.robustLine(robert), null);            // the committed fixture has no such keys yet
  const x = { ...robert, peer_check: { n: 20, higher: 19, broke: 12, weight: 0.4 },
    funding_check: { n: 3, mildest: -0.338, deepest: -0.356, same_verdict: true, ways: [{ max_drawdown: -0.338, verdict: "Incompatible" }, { max_drawdown: -0.356, verdict: "Incompatible" }, { max_drawdown: -0.345, verdict: "Incompatible" }] },
    never_rebalanced: { end_weight: 0.75, breaks: 5 } };
  assert.equal(txt(R.peerLine(x)), `In this window 19 of the pack’s 20 stocks, at the same 40${NB}%, would also have ended higher (today’s survivors); 12 broke your floor.`);
  assert.equal(R.robustLine(x), `Funded three ways: worst fall ${M}33.8${NB}% to ${M}35.6${NB}%; the answer holds. Never rebalanced: NVIDIA grows to 75${NB}%; your floor breaks five times.`);
  const css = readFileSync(join(here, "..", "web", "css", "replay.css"), "utf8");
  assert.doesNotMatch(css, /data-tone="inside"\][^{]*\{[^}]*var\(--clear\)/);                 // R38: Inside in a neutral tone
});

console.log(`web_u2_test: ${n} tests passed`);
