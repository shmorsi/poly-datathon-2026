// Lane U4: the dial's pure helpers (web/lib/dial.js) under node. Run: node tests/web_u4_test.mjs
// Pins design doc §2 item 3 and rulings R1/R2: the break is the first size the server judged Incompatible (pitfall 5: the browser
// never compares a fall with the floor), the copy is past tense and never "holds up to", the band replaces the notch when present.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
const PF = createRequire(import.meta.url)("../web/lib.js");
const D = await import("../web/lib/dial.js");
const F = await import("./web_fixtures.mjs");      // R17: the committed public cut of the four saved runs (lane U0)

let passed = 0;
const test = (name, fn) => { try { fn(); passed++; } catch (e) { console.error("FAIL", name); throw e; } };

/* a synthetic Result shaped like a real one: 0..40 % of one ticker, inside to 8 %, outside from 9 % (test numbers only) */
function fixture(over = {}) {
  const curve = Array.from({ length: 41 }, (_, k) => ({
    weight: k / 100, verdict: k <= 8 ? "Compatible" : "Incompatible", fails: k <= 8 ? 0 : k <= 10 ? 1 : 2,
    max_drawdown: -0.1 - k * 0.006, scenario_shock: -0.06, end_value: 900000 + k * 20000 }));
  return { question_type: "change", amount: 600000, verdict: "Incompatible", profile: { name: "Robert" }, limits: { floor: -0.15 },
    portfolio: { A: 0.27, B: 0.33, NVDA: 0.4 }, baseline: { verdict: "Compatible", portfolio: { A: 0.45, B: 0.55 } },
    scenario: { change: { op: "set", ticker: "NVDA", weight: 0.4 } },
    tipping_point: { ticker: "NVDA", max_weight: 0.08, curve, paths: { dates: ["2021-11-12", "2026-11-12"], weights: curve.map((c) => c.weight), values: [] } },
    ...over };
}
const text = (segs) => segs.map((s) => s[0]).join("");
const BANNED = /\b(buy|sell|hold|holds|you should|you can|safe|allowed|fits|recommend(ed)?)\b/i;

test("no curve, no dial", () => {
  assert.equal(D.dialModel(null, PF), null);
  assert.equal(D.dialModel({ tipping_point: null }, PF), null);
  assert.equal(D.dialModel(fixture({ tipping_point: { ticker: "NVDA", curve: [] } }), PF), null);
  assert.equal(D.dialModel(fixture(), null), null);
});

test("the break, the asked size and today come from the Result", () => {
  const m = D.dialModel(fixture(), PF);
  assert.equal(m.name, "NVIDIA");
  assert.equal(m.asked, 40);
  assert.equal(m.today, 0);
  assert.equal(m.breakAt, 9);
  assert.equal(m.notch.text, "9 %");
  assert.ok(Math.abs(m.notch.x - 0.2125) < 1e-9);             // the cut sits halfway between 8 % and 9 %, where the pointer flips the size
  assert.deepEqual(m.runs.map((r) => [r.cls, r.from, r.to]), [["held", 0, 6], ["touched", 7, 8], ["broke", 9, 40]]);   // R20 floor classes
  assert.equal(m.replay, "in this 2021–26 replay");
  assert.equal(m.label, "NVIDIA share of your $600,000");       // R18: one voice in the instrument
});

test("R2 copy: past tense, the first failing size, no advice words", () => {
  const m = D.dialModel(fixture(), PF);
  assert.equal(text(m.sentence), "In this replay, your floor first broke at 9 % NVIDIA.");
  for (const s of [text(m.sentence), m.hint, m.summary, ...m.fineprint, D.readout(m, 8).valuetext]) assert.doesNotMatch(s, BANNED, s);
  assert.deepEqual(m.fineprint, ["Fictional illustration, not a recommendation.", "This already happened; it is not a forecast."]);
});

test("the browser never judges: a verdict the server wrote wins over any number", () => {
  const r = fixture();
  r.tipping_point.curve[8].max_drawdown = -0.1500004;          // pitfall 5: a raw comparison would call 8 % a breach
  r.tipping_point.curve[20].verdict = "Compatible";             // a curve that comes back inside is drawn as the server said
  const m = D.dialModel(r, PF);
  assert.equal(m.breakAt, 9);
  assert.equal(D.readout(m, 8).floor.cls, "touched");          // held by the server's verdict, at the floor after rounding: never "broke"
  assert.equal(D.readout(m, 20).floor.cls, "touched");         // a size the server passed is never turned into a break
  assert.deepEqual(m.runs.map((x) => [x.cls, x.from, x.to]), [["held", 0, 6], ["touched", 7, 8], ["broke", 9, 19], ["touched", 20, 20], ["broke", 21, 40]]);
});

test("every size inside, or every size outside", () => {
  const inside = fixture();
  for (const c of inside.tipping_point.curve) c.verdict = "Compatible";
  const mi = D.dialModel(inside, PF);
  assert.equal(mi.breakAt, null);
  assert.equal(mi.notch, null);
  assert.equal(text(mi.sentence), "In this replay, your floor did not break at any size up to 40 % NVIDIA.");
  const outside = fixture();
  for (const c of outside.tipping_point.curve) c.verdict = "Incompatible";
  const mo = D.dialModel(outside, PF);
  assert.equal(mo.breakAt, 0);
  assert.equal(mo.notch, null);
  assert.equal(text(mo.sentence), "In this replay, your floor broke at every size, even with no NVIDIA.");
});

test("R20: a size with caveats on other limits still reads only as a fall against the floor", () => {
  const r = fixture();
  for (const k of [5, 6, 7, 8]) r.tipping_point.curve[k].verdict = "Tension";
  const m = D.dialModel(r, PF);
  assert.equal(m.breakAt, 9);
  assert.deepEqual(m.runs.map((x) => x.cls), ["held", "touched", "broke"]);
  assert.equal(D.readout(m, 6).word, "Held above your floor");
});

test("the start-month band (B3 tipping_band) adds its own sentence; R2's sentence stays the replay's", () => {
  const starts = [["2021-11", 0.07], ["2022-06", 0.12], ["2023-11", 0.1]].map(([start, first_break]) => ({ start, first_break }));
  const m = D.dialModel(fixture({ tipping_band: { lo: 0.07, hi: 0.12, starts, holds: [], n_starts: 3 } }), PF);
  assert.equal(text(m.sentence), "In this replay, your floor first broke at 9\u00a0% NVIDIA.");
  assert.equal(text(m.bandLine), "Depending on the start month, from Nov\u00a02021 to Nov\u00a02023, it first broke between 7\u00a0% and 12\u00a0%.");
  assert.deepEqual([m.band.iLo, m.band.iHi, m.band.firstAt, m.band.lastAt], [7, 12, "7\u00a0%", "10\u00a0%"]);
  assert.ok(m.notch && m.notch.i === 9);                       // the cut still marks where this replay broke
  const one = D.dialModel(fixture({ tipping_band: { lo: 0.09, hi: 0.09, starts: ["2021-11", "2023-11"] } }), PF);
  assert.equal(text(one.bandLine), "Started in any month from Nov\u00a02021 to Nov\u00a02023, it first broke at the same 9\u00a0%.");
  const some = D.dialModel(fixture({ tipping_band: { lo: 0.09, hi: 0.2, starts, holds: ["2023-11"], n_starts: 4 } }), PF);
  assert.match(text(some.bandLine), /From 1 of the 4 start months it did not break at all\.$/);
  assert.equal(D.dialModel(fixture({ tipping_band: { lo: 0.12, hi: 0.07 } }), PF).band, null);       // a malformed band is ignored
  assert.equal(D.dialModel(fixture({ tipping_band: { lo: null, hi: 0.1 } }), PF).band, null);
  assert.equal(D.dialModel(fixture({ tipping_band: { lo: 0.07, hi: 0.12 } }), PF).bandLine.length, 5);   // no starts: no month span
});

test("every start month held: no band, one more sentence", () => {
  const r = fixture({ tipping_band: { lo: null, hi: null, holds: ["2021-11", "2023-11"], n_starts: 2, starts: [{ start: "2021-11", first_break: null }, { start: "2023-11", first_break: null }] } });
  for (const c of r.tipping_point.curve) c.verdict = "Compatible";
  const m = D.dialModel(r, PF);
  assert.equal(m.band, null);
  assert.equal(m.everyStart, true);
  assert.equal(text(m.bandLine), "Started in any month from Nov\u00a02021 to Nov\u00a02023, it did not break either.");
});

test("R18 one voice: the label is second person; the floor in dollars only when the capacity set it", () => {
  assert.equal(D.dialModel(fixture({ profile: { name: "Too Canadian?" } }), PF).label, "NVIDIA share of your $600,000");
  assert.equal(D.dialModel(fixture({ amount: null }), PF).label, "NVIDIA share of your mix");
  const capped = fixture({ limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000, edited: [] } });
  assert.deepEqual([D.dialModel(capped, PF).capText, D.dialModel(capped, PF).capWord], ["\u2212$90,000", "Assumed limit"]);
  const typed = fixture({ limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000, edited: ["floor"] } });
  assert.equal(D.dialModel(typed, PF).capText, null);           // an edited floor is a percent, never re-priced in dollars
  assert.equal(D.dialModel(fixture({ limits: { floor: -0.25, floor_source: "band" } }), PF).capText, null);
});

test("readouts: exact Result values, dollars only when every size carries them", () => {
  const m = D.dialModel(fixture(), PF);
  const r40 = D.readout(m, 40);
  assert.deepEqual([r40.weightText, r40.word, r40.ddText, r40.endText, r40.todayEndText, r40.dollarsText, r40.isAsked],
    ["40 %", "Outside your limits", "−34.0 %", "$1,700,000", "$900,000", null, true]);
  assert.equal(r40.valuetext, "40 % NVIDIA, the size you asked: outside your limits in this 2021–26 replay. Worst fall −34.0 %. Ended at $1,700,000.");
  assert.equal(D.readout(m, 0).todayEndText, null);             // at today's size there is nothing to compare
  const r = fixture();
  for (const c of r.tipping_point.curve) c.loss_dollars = Math.round(600000 * c.max_drawdown);
  const md = D.dialModel(r, PF);
  assert.equal(md.hasDollars, true);
  assert.equal(D.readout(md, 40).dollarsText, "−$204,000");
  assert.match(D.readout(md, 40).valuetext, /the same fall as −\$204,000 on your \$600,000/);
  delete r.tipping_point.curve[3].loss_dollars;
  assert.equal(D.dialModel(r, PF).hasDollars, false);
});

test("the roll lands on the exact value", () => {
  const m = D.dialModel(fixture(), PF);
  const from = D.figuresOf(m, 40);
  assert.deepEqual(D.rollTexts(m, from, 8, 1, PF), { ddText: "−14.8 %", dollarsText: null, endText: "$1,060,000" });
  assert.deepEqual(D.rollTexts(m, from, 8, 0, PF), { ddText: "−34.0 %", dollarsText: null, endText: "$1,700,000" });
  assert.equal(D.rollTexts(m, from, 8, 0.5, PF).endText, "$1,380,000");
  assert.equal(D.easeOut(0), 0);
  assert.equal(D.easeOut(1), 1);
  assert.ok(D.easeOut(0.5) > 0.9 && D.easeOut(0.1) > 0.3);     // a strong ease-out: most of the way early
});

test("pointer, keys and the crossing", () => {
  const m = D.dialModel(fixture(), PF);
  assert.deepEqual([D.nearestIndex(m, 0), D.nearestIndex(m, 1), D.nearestIndex(m, 0.2124), D.nearestIndex(m, 0.2126), D.nearestIndex(m, -3), D.nearestIndex(m, 9)], [0, 40, 8, 9, 0, 40]);
  assert.deepEqual(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"].map((k) => D.keyStep(10, k, 40)), [9, 11, 11, 9, 15, 5, 0, 40]);
  assert.equal(D.keyStep(0, "ArrowLeft", 40), 0);
  assert.equal(D.keyStep(40, "PageUp", 40), 40);
  assert.equal(D.keyStep(10, "a", 40), null);
  assert.deepEqual([D.crossed(m, 9, 8), D.crossed(m, 8, 9), D.crossed(m, 40, 9), D.crossed(m, 3, 7), D.crossed(m, 40, 0)], [true, true, false, false, true]);
});

test("a move the investor already holds: today sits on the ruler", () => {
  const r = fixture({ baseline: { verdict: "Compatible", portfolio: { A: 0.5, B: 0.35, NVDA: 0.15 } } });
  const m = D.dialModel(r, PF);
  assert.equal(m.today, 15);
  assert.equal(D.readout(m, 15).isToday, true);
});

/* R17: real values are pinned on the committed fixtures (tests/fixtures/web), never on /tmp runs */
test("fixture robert: the floor first broke at 9 %, 9 % to 35 % by start month, dollars beside the assumed limit", () => {
  const m = D.dialModel(F.load("robert"), PF);
  assert.deepEqual([m.name, m.breakAt, m.asked, m.today, m.last, m.hasDollars, m.capText, m.capWord], ["NVIDIA", 9, 40, 0, 40, true, "\u2212$90,000", "Assumed limit"]);
  assert.equal(text(m.sentence), "In this replay, your floor first broke at 9\u00a0% NVIDIA.");
  assert.equal(text(m.bandLine), "Depending on the start month, from Nov\u00a02021 to Nov\u00a02023, it first broke between 9\u00a0% and 35\u00a0%.");
  assert.equal(m.label, "NVIDIA share of your $600,000");
  assert.equal(D.readout(m, 8).valuetext, "8 % NVIDIA, a replay at another size in this 2021–26 replay. Touched your floor. Worst fall −15.0 %, against your floor of −15 %. A replay at another size, not a recommendation.");
  assert.deepEqual([D.readout(m, 9).word, D.readout(m, 9).ddText, D.readout(m, 9).dollarsText, D.readout(m, 9).endText], ["Broke your floor", "−15.6 %", null, null]);
  assert.deepEqual([8, 9, 5].map((i) => D.readout(m, i).floor.cls), ["touched", "broke", "held"]);   // the controller's 8 %, 9 %, 5 %
  assert.deepEqual([D.readout(m, 40).ddText, D.readout(m, 40).dollarsText, D.readout(m, 40).endText, D.readout(m, 40).todayEndText],
    ["\u221234.5\u00a0%", "\u2212$207,146", "$1,847,077", "$911,676"]);
});

test("fixture canadian: SPY 0 to 20 %, the floor never broke from any start month", () => {
  const m = D.dialModel(F.load("canadian"), PF);
  assert.deepEqual([m.name, m.breakAt, m.notch, m.band, m.everyStart, m.asked, m.today], ["SPY", null, null, null, true, 20, 0]);
  assert.equal(text(m.sentence), "In this replay, your floor did not break at any size up to 20\u00a0% SPY.");
  assert.equal(text(m.bandLine), "Started in any month from Nov\u00a02021 to Nov\u00a02023, it did not break either.");
  assert.equal(m.label, "SPY share of your $250,000");
  assert.deepEqual([D.readout(m, 20).ddText, D.readout(m, 20).dollarsText, D.readout(m, 20).endText], ["\u221212.9\u00a0%", "\u2212$32,255", "$403,823"]);
});

test("fixtures mateo and amira: no size curve, no dial", () => {
  assert.equal(D.dialModel(F.load("mateo"), PF), null);
  assert.equal(D.dialModel(F.load("amira"), PF), null);
});

test("R20: no size but the asked one carries a verdict word, a pass mark or an end value", () => {
  for (const name of F.NAMES) {
    const m = D.dialModel(F.load(name), PF);
    if (!m) continue;
    assert.doesNotMatch(m.summary, /inside your limits|with caveats|outside your limits/i);
    for (let i = 0; i <= m.last; i++) {
      const r = D.readout(m, i);
      if (i === m.asked) { assert.equal(r.caption, null); continue; }
      assert.ok(["Broke your floor", "Touched your floor", "Held above your floor"].includes(r.word), r.word);
      assert.notEqual(r.icon, "i-in");
      assert.notEqual(r.tone, "inside");
      assert.equal(r.endText, null);
      assert.equal(r.dollarsText, null);
      assert.equal(r.caption, "A replay at another size, not a recommendation.");
      assert.doesNotMatch(r.valuetext, /inside your limits|ended at|\$/i);
    }
  }
});

/* A saved real run (never in git; re-recorded during the day) gets shape and
   invariant checks only, and the case skips when the file is absent. */
const REAL = ["/tmp/epi_runs_v1/robert.json", "/tmp/epi_video/runs/robert.json"].find((p) => existsSync(p));
if (REAL) test("a saved real run: shape and invariants only", () => {
  const r = JSON.parse(readFileSync(REAL, "utf8"));
  const m = D.dialModel(r, PF);
  if (!r.tipping_point) { assert.equal(m, null); return; }
  const curve = r.tipping_point.curve;
  assert.equal(m.points.length, curve.length);
  assert.equal(m.breakAt, curve.findIndex((c) => c.verdict === "Incompatible") < 0 ? null : curve.findIndex((c) => c.verdict === "Incompatible"));
  assert.match(text(m.sentence), /^In this replay, your floor (first broke at \S+\u00a0% |did not break at any size up to |broke at every size)/);
  assert.equal(D.readout(m, m.asked).endText, PF.fmt.money(curve[m.asked].end_value));
  assert.equal(D.readout(m, m.asked).word, PF.VERDICT[curve[m.asked].verdict].word);
  for (let i = 0; i <= m.last; i++) if (i !== m.asked) assert.equal(D.readout(m, i).floor.cls === "broke", curve[i].verdict === "Incompatible");
  for (const s of [text(m.sentence), m.bandLine ? text(m.bandLine) : "", m.summary]) assert.doesNotMatch(s, BANNED, s);
});

console.log(`web_u4_test: ${passed} passed${REAL ? "" : " (the saved real run is absent: its case is skipped)"}`);
