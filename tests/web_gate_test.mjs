/* scripts/gate_rules.mjs, the release gate's rules (scripts/release_gate.mjs): the advice and forecast words of the red gates (README, Limits) red
   gate 1 and ruling R1 (EN and FR), their exemptions (quoted investor questions, the disclaimers), the verdict words of R20, the
   " · " meta strings of R16, and the pass-mark green. Run: node tests/web_gate_test.mjs (test_web_lib.py runs it). */
import { strict as assert } from "node:assert";
import { adviceHits, verdictHits, metaHits, exempt, isGreen, parseColor, ranges, REQUIRED, norm } from "../scripts/gate_rules.mjs";

let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}
const ids = (text, qs) => adviceHits(text, qs).map((h) => h.id);

test("advice words are caught in plain copy, in English and in French", () => {
  assert.deepEqual(ids("Buy 8 % NVIDIA now."), ["buy"]);
  assert.deepEqual(ids("You could sell some of it."), ["sell"]);
  assert.deepEqual(ids("You should trim it."), ["you-should"]);
  assert.deepEqual(ids("We recommend a smaller size."), ["recommend"]);
  assert.deepEqual(ids("This size is not recommended."), ["recommend"]);       // negative advice is still advice
  assert.deepEqual(ids("A safe size for you."), ["safe"]);
  assert.deepEqual(ids("The most you are allowed is 8 %."), ["allowed"]);
  assert.deepEqual(ids("Your 2022 reaction alone would allow −25 %."), ["allowed"]);   // the same permission, another tense
  assert.deepEqual(ids("In this history, your floor holds up to 8 % NVIDIA."), ["hold-phrase"]);
  assert.deepEqual(ids("This mix fits your profile."), ["fits-you"]);
  assert.deepEqual(ids("NVIDIA will fall in the next tariff war."), ["forecast"]);
  assert.deepEqual(ids("Markets are going to rise."), ["forecast"]);
  assert.deepEqual(ids("A guaranteed floor."), ["guaranteed"]);
  assert.deepEqual(ids("The expected return is 7 %."), ["expected-return"]);
  assert.deepEqual(ids("Vous devriez acheter NVIDIA, c’est sécuritaire."), ["fr-acheter", "fr-devriez", "fr-securitaire"]);
  assert.deepEqual(ids("Il faut vendre. Taille recommandée : 8 %."), ["fr-vendre", "fr-recommande"]);
});

test("hold is caught as a verb or an order, never in holdings, thresholds or the R20 floor words", () => {
  assert.deepEqual(ids("Hold NVIDIA through the storm."), ["hold-imperative"]);
  assert.deepEqual(ids("You hold 40 % in one stock."), ["hold-verb"]);
  assert.deepEqual(ids("Better hold on."), ["hold-verb", "hold-phrase"]);
  assert.deepEqual(ids("Held above your floor"), []);
  assert.deepEqual(ids("Your holdings, by fund. The threshold you typed. Each holding’s share."), []);
});

test("market words that only sound like advice pass: a sell-off, buybacks, the negated honesty lines", () => {
  assert.deepEqual(ids("What if a big AI sell-off hits? Three sell-offs on record."), []);
  assert.deepEqual(ids("Share buybacks are not modelled."), []);
  assert.deepEqual(ids("Fictional illustration, not a recommendation."), []);
  assert.deepEqual(ids("A replay at another size, not a recommendation."), []);
  assert.deepEqual(ids("Client-run simulation, not a recommendation or a suitability assessment."), []);
  assert.deepEqual(ids("Past performance does not guarantee future results; nothing here is guaranteed."), []);
  assert.deepEqual(ids("Educational simulation. This is not financial advice."), []);
  assert.deepEqual(ids("Ce n’est pas une recommandation."), []);
});

test("an investor's question is exempt when it is shown whole or quoted; the page's own words around it are not", () => {
  const q = "Should I buy NVIDIA and hold it through the tariff war?";
  assert.deepEqual(ids(q, [q]), []);
  assert.deepEqual(ids(`Robert asked: “${q}” You should not.`, [q]), ["you-should"]);
  assert.deepEqual(ids("“Should I sell everything before the election?” was refused as advice."), []);   // a quoted question
  assert.deepEqual(ids("Should I sell everything now?"), []);                  // the investor's own first-person words
  assert.deepEqual(ids("Should you sell everything now?"), ["sell"]);          // the page speaking: not exempt
  assert.deepEqual(ids("“buy the dip” is not a reading we use."), ["buy"]);    // a quoted phrase that is no question
  assert.deepEqual(ids("“Buy now…” said nobody here."), ["buy"]);              // an ellipsis alone exempts nothing
  assert.deepEqual(ids(`The navigator read “${q.slice(0, 20)}…” as a tariff question.`, [q]), []);   // a quoted part of the question
  const { cut } = exempt(`“${q}”`, [q]);
  assert.equal(cut[0].why, "investor question");
});

test("verdict words (R20) are found in any case and voice; floor words are not verdicts", () => {
  assert.equal(verdictHits("OUTSIDE YOUR LIMITS").length, 1);
  assert.equal(verdictHits("Inside, with caveats").length, 1);
  assert.equal(verdictHits("Without the move: inside your limits.").length, 1);
  assert.equal(verdictHits("Robert’s mix was outside Robert’s limits").length, 1);
  assert.equal(verdictHits("Broke your floor. Touched your floor. Held above your floor.").length, 0);
  assert.equal(verdictHits("Inside").length, 0);
});

test("meta strings (R16): an A · B · C line is caught, a lone dot or a decimal is not", () => {
  assert.equal(metaHits("Robert, 59 · $600,000 · can absorb $90,000").length, 2);
  assert.equal(metaHits("Robert, 59 · $600,000").length, 1);
  assert.equal(metaHits("2.4 → 1.2 bets").length, 0);
  assert.equal(metaHits("Robert, 59, has $600,000.").length, 0);
});

test("the pass-mark green: the page's tokens and any clear green hue, never cyan, amber, red, magenta or grey", () => {
  const tokens = ["#43D18B"];
  assert.ok(isGreen("rgb(67, 209, 139)", tokens));
  assert.ok(isGreen("rgba(67, 209, 139, 0.9)", tokens));
  assert.ok(isGreen("color(srgb 0.2627 0.8196 0.5451)", tokens));
  assert.ok(isGreen("rgb(40, 180, 60)", []));
  assert.ok(!isGreen("rgba(67, 209, 139, 0.05)", tokens));                    // a faint wash is no status mark
  for (const c of ["rgb(159, 230, 255)", "rgb(244, 190, 79)", "rgb(255, 106, 92)", "rgb(255, 95, 200)", "rgb(169, 178, 191)", "rgb(51, 165, 149)"]) {
    assert.ok(!isGreen(c, tokens), c);
  }
  assert.deepEqual(parseColor("#43d18b"), { r: 67, g: 209, b: 139, a: 1 });
});

test("the report's helpers: size ranges, the two required lines, one spelling for spaces and apostrophes", () => {
  assert.equal(ranges([0, 1, 2, 5, 7, 8, 40]), "0-2, 5, 7-8, 40");
  assert.equal(ranges([]), "");
  assert.deepEqual(REQUIRED, ["Educational simulation. This is not financial advice.", "This already happened; it is not a forecast."]);
  assert.equal(norm("It’s a  test"), "It's a test");
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
