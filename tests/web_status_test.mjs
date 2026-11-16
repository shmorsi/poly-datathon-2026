/* web/lib/status.js, the page's one status vocabulary (lane U5; #checklist, #record and #how import it): the critique's
   problem 5 (only a broken hard limit reads Outside with the octagon), ruling R11 (a break within 1 point is "touched"), and the
   bank juror's ruling (a what-if row never carries a pass mark). Run: node tests/web_status_test.mjs (test_web_lib.py runs it). */
import { strict as assert } from "node:assert";
import { SHOWN, shownStatus, STATUS_LEGEND, FLOOR_WORDS, floorClass, floorWord, bindingWord } from "../web/lib/status.js";

let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}

test("a check's status: only a broken hard limit is Outside with the octagon; soft, preference and warn rows read Caution", () => {
  assert.deepEqual(shownStatus("fail", "hard"), { word: "Outside", tone: "outside", icon: "i-out" });
  for (const tier of ["soft", "preference", "warn", undefined]) assert.deepEqual(shownStatus("fail", tier), SHOWN.caution, String(tier));
  for (const tier of ["hard", "soft", "warn"]) assert.equal(shownStatus("warn", tier).word, "Caution");
  for (const tier of ["hard", "soft", "preference", "warn"]) assert.deepEqual(shownStatus("pass", tier), { word: "Inside", tone: "inside", icon: "i-in" });
  assert.equal(shownStatus("unknown", "hard"), null);
  assert.ok(Object.isFrozen(SHOWN) && Object.isFrozen(SHOWN.outside));
  assert.match(STATUS_LEGEND, /^A hard limit decides the verdict on its own/);
});

test("the row that set the verdict: only a broken hard limit decided it; a soft limit, a preference or a warning added the caveat", () => {
  assert.equal(bindingWord("fail", "hard"), "Decided the verdict");
  for (const tier of ["soft", "preference", "warn"]) assert.equal(bindingWord("fail", tier), "Added the caveat", tier);
  assert.equal(bindingWord("warn", "soft"), "Added the caveat");
  assert.equal(bindingWord("pass", "hard"), null);
});

test("what a fall did to the floor: the server's beyond_floor decides; a break of 1 point or less is touched (R11)", () => {
  assert.equal(floorClass(-0.142, -0.15, false), "held");
  assert.equal(floorClass(-0.1837, -0.15, true), "broke");
  assert.equal(floorClass(-0.158, -0.15, true), "touched");
  assert.equal(floorClass(-0.16, -0.15, true), "touched");                       // exactly 1.0 point
  assert.equal(floorClass(-0.1601, -0.15, true), "touched");                     // 1.01 raw, 1.0 in tenths: the tenths decide (round_pp)
  assert.equal(floorClass(-0.161, -0.15, true), "broke");
  assert.equal(floorClass(-0.2, -0.15, null), null);                            // the server did not say: no word
  assert.equal(floorClass(-0.2, -0.15, "touched"), "touched");                  // a server class is taken as it is
});

test("the floor words are neutral: no pass mark on a what-if row", () => {
  assert.deepEqual(Object.values(FLOOR_WORDS), ["Broke your floor", "Touched your floor", "Held above your floor"]);
  assert.deepEqual(floorWord("held"), { cls: "held", word: "Held above your floor", tone: "neutral" });
  assert.ok(["broke", "touched", "held"].every((c) => floorWord(c).tone === "neutral" && !("icon" in floorWord(c))));
  assert.equal(floorWord("inside"), null);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
