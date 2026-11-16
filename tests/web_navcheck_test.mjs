/* Lane navcheck (Sun Nov 15): where the globe flies for real-world future-scenario questions. Pure helpers of web/lib/replay.js,
   web/lib/u1.js and web/lib/race.js on web/fake_result.json (in git), changed the way the live check of 14 questions found them:
   "China invades Taiwan" (war and oil + chips, every pick a chip event) flew to Tehran because families come in config order;
   a relief event could be "the deepest shock"; an abstention still flew to its family's worst event (ruling R29, pipeline._abstains). */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
globalThis.PF = createRequire(import.meta.url)("../web/lib.js");
const R = await import("../web/lib/replay.js");
const U = await import("../web/lib/u1.js");
const RACE = await import("../web/lib/race.js");
const fake = JSON.parse(readFileSync(join(here, "..", "web", "fake_result.json"), "utf8"));
let n = 0;
const test = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL", name); throw e; } };

/* a Result whose navigator named `families` and picked `picked` (event ids); troughs set on both sides */
function withPicks(families, picked, troughs = {}, extra = {}) {
  const events = fake.events.map((e) => {
    const t = troughs[e.event_id];
    const side = t === undefined ? {} : { today: { ...(e.today || {}), trough: t }, after: { ...(e.after || {}), trough: t } };
    return { ...e, ...side, picked: picked.includes(e.event_id) };
  });
  return { ...fake, events, scenario: { ...fake.scenario, families, event_ids: picked, ...extra } };
}
const ids = (fam) => fake.events.filter((e) => e.family === fam).map((e) => e.event_id);

test("the fixture keeps its epicentre: Liberation Day, the deepest tariff shock (the demo's beat)", () => {
  assert.equal(R.worstPrecedent(fake).id, "liberation_day_2025");
  assert.equal(U.askedFamily(fake), "tariffs");
});

test("the asked family is the first family the navigator picked a precedent in, not config order", () => {
  /* question (e) of the live check: "What if China invades Taiwan and chips stop?" -> war_oil + chips, every pick a chip event */
  const r = withPicks(["war_oil", "chips"], ["chip_selloff_2024", "chips_2022"]);
  assert.equal(R.worstPrecedent(r).family, "chips");
  assert.notEqual(R.worstPrecedent(r).id, "iran_2026");
  assert.equal(U.askedFamily(r), "chips");
  const none = withPicks(["war_oil", "chips"], []);                      // nothing picked: the first family, as before
  assert.equal(R.worstPrecedent(none).family, "war_oil");
});

test("a relief event is never the epicentre of a shock, unless the navigator picked relief (R29)", () => {
  const relief = fake.events.find((e) => e.family === "tariffs" && e.sign === "positive");
  assert.ok(relief, "the fixture has a tariff relief event");
  const deep = { [relief.event_id]: -0.5 };                              // the relief event made the deepest trough
  const shock = withPicks(["tariffs"], ["liberation_day_2025"], deep);
  assert.notEqual(R.worstPrecedent(shock).id, relief.event_id);
  assert.equal(R.worstPrecedent(shock).id, "liberation_day_2025");
  const asked = withPicks(["tariffs"], [relief.event_id], deep);       // the words asked for relief: it may be the epicentre
  assert.equal(R.worstPrecedent(asked).id, relief.event_id);
});

test("an abstention (no close precedent, nothing picked) flies nowhere and draws no family's ticks", () => {
  const abstain = withPicks(["rates"], [], {}, { weather: { no_precedent: true, families: ["rates"], regions: [] } });
  assert.equal(R.worstPrecedent(abstain), null);
  assert.equal(U.askedFamily(abstain), null);
  const model = RACE.raceModel(abstain, null);
  assert.ok(model, "the fixture draws a race");
  assert.equal(model.family, null);
  const picked = withPicks(["tariffs"], ["liberation_day_2025"], {}, { weather: { no_precedent: false } });
  assert.equal(R.worstPrecedent(picked).id, "liberation_day_2025");
});

test("the race's cyan ticks follow the same asked family as the globe", () => {
  const model = RACE.raceModel(withPicks(["war_oil", "chips"], ["chip_selloff_2024"]), null);
  assert.ok(model, "the fixture draws a race");
  assert.equal(model.family, "chips");
});

console.log(`web_navcheck_test: ${n} passed`);
