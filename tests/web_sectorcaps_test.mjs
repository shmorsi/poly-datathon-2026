/* Lane sector-limits (Sun Nov 15; LIMITS_MODEL 16:40 and its CONFLICTS 16:55): the industry limits on the page, under node.
   web/lib/sectorcaps.js (names, sources, the editor's rows -> limits.sector_caps), web/lib/money.js (the limits block, the
   recheck body and its merge) and PF's checklist rows (web/lib.js) for governance's rows "sector_cap:<sector>", on the committed
   web fixtures (R17) with one row added the way governance writes it. Run: node tests/web_sectorcaps_test.mjs (tests/test_web_lib.py
   runs it too). The page never judges a cap: every status, value and limit below is the Result's. */
import { strict as assert } from "node:assert";
import { createRequire } from "node:module";
import { load } from "./web_fixtures.mjs";
import * as M from "../web/lib/money.js";
import * as S from "../web/lib/sectorcaps.js";

const PF = createRequire(import.meta.url)("../web/lib.js");
let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}
const NB = " ";
const TECH = { rule: "sector_cap:Information Technology", tier: "soft", status: "fail", value: 0.425947, limit: 0.2, holding: "NVDA",
  reason: `In this replay the mix held 42.6${NB}% in Information Technology, past the 20${NB}% you set.`,
  name: "Your Information Technology limit", same_cause_as: "single_stock", source: "you" };
const ENERGY = { rule: "sector_cap:Energy", tier: "hard", status: "pass", value: 0, limit: 0, holding: null,
  reason: `In this replay the mix held nothing in Energy, an industry you excluded (0${NB}%).`, name: "Your Energy limit",
  same_cause_as: null, source: "words" };
const capped = (edit) => {
  const r = load("robert");
  r.checks = [...r.checks, TECH, ENERGY];
  r.limits = { ...r.limits, sector_caps: { Energy: 0, "Information Technology": 0.2 }, edited: [...(r.limits.edited || []), "sector_caps"],
    from_words: ["sector_caps.Energy"] };
  if (edit) edit(r);
  return r;
};

test("the eleven GICS names are governance's, in its order; the rule id names its industry", () => {
  assert.equal(S.GICS_SECTORS.length, 11);
  assert.equal(S.GICS_SECTORS[7], "Information Technology");
  assert.equal(S.capSector("sector_cap:Energy"), "Energy");
  assert.equal(S.capSector("sector"), null);
  assert.equal(S.capName("sector_cap:Health Care"), "Your Health Care limit");
  assert.deepEqual(S.capFacts("sector_cap:Energy"), [["energy share"], ["your energy limit"]]);
});

test("one rule for where a limit came from: your words > set by you > assumed", () => {
  const L = { edited: ["floor", "sector_caps"], from_words: ["sector_caps.Energy"] };
  assert.equal(S.sourceOf(L, "sector_caps.Energy"), "words");
  assert.equal(S.sourceOf(L, "sector_caps.Utilities"), "you");
  assert.equal(S.sourceOf(L, "floor"), "you");
  assert.equal(S.sourceOf(L, "single_stock"), "assumed");
  assert.equal(S.sourceOf({ from_words: { crypto: "no crypto" } }, "crypto"), "words");     // a {key: words} map gives its keys
  assert.equal(S.sourceWords("assumed"), "assumed from the profile, not set by you");
});

test("the editor's rows become limits.sector_caps in GICS order, or one plain sentence", () => {
  assert.deepEqual(S.capsFromRows([{ sector: "Information Technology", pct: "20" }, { sector: "Energy", pct: "0" }, { sector: "", pct: "" }]),
    { caps: { Energy: 0, "Information Technology": 0.2 } });
  assert.deepEqual(S.capsFromRows([{ sector: "Utilities", pct: "12.5 %" }]), { caps: { Utilities: 0.125 } });
  assert.match(S.capsFromRows([{ sector: "", pct: "20" }]).error, /Pick an industry/);
  assert.match(S.capsFromRows([{ sector: "Energy", pct: "" }]).error, /Enter the largest share for Energy/);
  assert.match(S.capsFromRows([{ sector: "Energy", pct: "120" }]).error, /between 0 % \(none of it\) and 100 %/);
  assert.match(S.capsFromRows([{ sector: "Energy", pct: "1" }, { sector: "Energy", pct: "2" }]).error, /two limits/);
  assert.deepEqual(S.capsFromRows([]), { caps: {} });
});

test("PF's checklist rows read an industry row in its own words: share against your limit, Excluded (0 %) for an exclusion", () => {
  const v = PF.view(PF.withPaths(capped()));
  const tech = v.rows.find((x) => x.rule === TECH.rule), energy = v.rows.find((x) => x.rule === ENERGY.rule);
  assert.equal(tech.name, "Your Information Technology limit");
  assert.equal(tech.compare, `42.6${NB}% against your limit 20.0${NB}%`.replace("20.0", PF.fmt.share(0.2).replace(/ %$/, "")));
  assert.equal(tech.word, "Outside");          // PF's status word; the checklist shows a soft one as Caution (status.js)
  assert.equal(tech.tier, "Soft limit");
  assert.equal(energy.tier, "Hard limit");
  assert.equal(energy.compare, `${PF.fmt.share(0)} against your limit Excluded (0${NB}%)`);
  const bare = capped((r) => { r.checks = r.checks.map((c) => (c.rule === TECH.rule ? { ...c, name: undefined } : c)); });
  assert.equal(PF.view(PF.withPaths(bare)).rows.find((x) => x.rule === TECH.rule).name, "Your Information Technology limit");
});

test("the checklist model keeps every industry row, a soft one as Caution, the exclusion as a hard limit", () => {
  const r = PF.withPaths(capped()), m = M.checksModel(r, PF.view(r), PF);
  const tech = m.rows.find((x) => x.rule === TECH.rule), energy = m.rows.find((x) => x.rule === ENERGY.rule);
  assert.equal(tech.word, "Caution");
  assert.equal(energy.word, "Inside");
  assert.equal(energy.hard, true);
  assert.equal(tech.same, "One company");
  assert.deepEqual([tech.src, tech.srcText, energy.srcText], ["you", "set by you", "from your words"]);   // the engine's own tag
  const old = PF.withPaths(load("robert")), mo = M.checksModel(old, PF.view(old), PF);
  assert.ok(mo.rows.every((x) => x.srcText === null || ["set by you", "from your words", "assumed"].includes(x.srcText)));
});

test("your limits block lists each industry with its source, and the editor starts from the run's caps", () => {
  const r = PF.withPaths(capped()), Y = M.limitsBlock(r, PF.view(r), "live", PF);
  const rows = Y.rows.filter((x) => String(x.key).startsWith("sector_caps."));
  assert.deepEqual(rows.map((x) => [x.label, x.value, x.typed, x.tag]), [["Energy", `Excluded (0${NB}%)`, false, "from your words"],
    ["Information Technology", `Up to ${PF.fmt.share(0.2)}`, true, null]]);
  assert.deepEqual(Y.edit.caps, [{ sector: "Energy", pct: 0, source: "words" }, { sector: "Information Technology", pct: 20, source: "you" }]);
  assert.equal(M.limitsBlock(PF.withPaths(load("robert")), PF.view(PF.withPaths(load("robert"))), "live", PF).edit.caps.length, 0);
});

test("the recheck body carries the caps as typed, the run's own caps when untouched, and the words that still stand", () => {
  const r = capped();
  const same = M.recheckBody(r, { caps: [{ sector: "Energy", pct: "0" }, { sector: "Information Technology", pct: "20" }] });
  assert.equal(same.error, "Change a limit first.");
  const moved = M.recheckBody(r, { caps: [{ sector: "Energy", pct: "0" }, { sector: "Information Technology", pct: "25" }] });
  assert.deepEqual(moved.body.limits, { sector_caps: { Energy: 0, "Information Technology": 0.25 }, from_words: ["sector_caps.Energy"] });
  const words = M.recheckBody(r, { caps: [{ sector: "Energy", pct: "5" }] });
  assert.deepEqual(words.body.limits, { sector_caps: { Energy: 0.05 } });     // edited: no longer from your words
  const other = M.recheckBody(r, { single: "20" });
  assert.deepEqual(other.body.limits.sector_caps, { Energy: 0, "Information Technology": 0.2 });   // kept: a recheck judges what it is sent
  const cleared = M.recheckBody(r, { caps: [] });
  assert.equal(cleared.body.limits.sector_caps, undefined);
  assert.match(M.recheckBody(r, { caps: [{ sector: "Energy", pct: "abc" }] }).error, /between 0 %/);
});

test("a value typed now is set by you, no longer from your words; the run's other edits go back as they were", () => {
  const r = capped((x) => { x.limits = { ...x.limits, single_stock: 0.15, crypto: 0, edited: ["single_stock", "crypto", "sector_caps"],
    from_words: ["single_stock", "crypto", "sector_caps.Energy"] }; });
  const b = M.recheckBody(r, { single: "20" }).body.limits;
  assert.equal(b.single_stock, 0.2);
  assert.equal(b.crypto, 0);                                   // from your words, kept: a recheck judges what it is sent
  assert.deepEqual(b.from_words, ["crypto", "sector_caps.Energy"]);
  const merged = M.mergeRecheck(r, { checks: [], verdict: "Compatible", kpis: r.kpis }, { run_id: r.run_id, limits: b }, { single: "20" });
  assert.deepEqual(merged.limits.from_words, ["crypto", "sector_caps.Energy"]);
  assert.ok(merged.limits.edited.includes("single_stock"));
  assert.equal(S.sourceOf(merged.limits, "single_stock"), "you");
  const floored = capped((x) => { x.limits = { ...x.limits, floor: -0.2, edited: ["floor", "sector_caps"], from_words: ["floor"] }; });
  const kept = M.recheckBody(floored, { single: "20" }).body.limits;
  assert.equal(kept.floor, -0.2);                                // your words' 20 % rule goes back as it was
  const m2 = M.mergeRecheck(floored, { checks: [], verdict: "Compatible", kpis: floored.kpis }, { run_id: floored.run_id, limits: kept }, { capacity: "", single: "20" });
  assert.equal(m2.profile.capacity, floored.profile.capacity);   // never "$0 you could lose" from a floor sent back unchanged
  assert.deepEqual(m2.limits.from_words, ["floor"]);
});

test("the merged recheck keeps the caps and words it sent, and drops them when cleared", () => {
  const r = capped(), rc = { checks: [TECH], verdict: "Incompatible", kpis: r.kpis };
  const body = { run_id: r.run_id, limits: { sector_caps: { "Information Technology": 0.25 } } };
  const merged = M.mergeRecheck(r, rc, body, {});
  assert.deepEqual(merged.limits.sector_caps, { "Information Technology": 0.25 });
  assert.ok(merged.limits.edited.includes("sector_caps") && merged.limits.from_words === undefined);
  const gone = M.mergeRecheck(r, rc, { run_id: r.run_id, limits: { single_stock: 0.2 } }, {});
  assert.equal(gone.limits.sector_caps, undefined);
  assert.ok(!gone.limits.edited.includes("sector_caps"));
});

test("the limits line names the industry limits, set by you or from your words", () => {
  const typed = capped((r) => { r.limits.from_words = []; });
  assert.equal(M.limitsLine(typed, PF.view(typed)).text,
    "Your industry limits are set by you; every other limit here is assumed from the profile, not set by you.");
  const said = capped((r) => { r.limits.from_words = ["sector_caps.Energy", "sector_caps.Information Technology"]; });
  assert.equal(M.limitsLine(said, PF.view(said)).text,
    "Your industry limits are from your words; every other limit here is assumed from the profile, not set by you.");
  const mixed = capped();                                    // Energy from your words, Information Technology typed
  assert.equal(M.limitsLine(mixed, PF.view(mixed)).text, "Your Energy limit is from your words; your Information Technology limit is set "
    + "by you; every other limit here is assumed from the profile, not set by you.");
});

test("no limits set: a live run with no checks still offers the editor; a run with checks, a static one or no band never", () => {
  const none = (edit) => { const r = PF.withPaths(load("robert")); r.checks = []; r.verdict = null; r.limits = null; if (edit) edit(r); return r; };
  const r = none(), got = M.noLimitsBlock(r, PF.view(r), "live", PF);
  assert.equal(got.answer, "No limits set. The replay above shows everything; add a limit to check the move against it.");
  assert.equal(got.Y.edit.live, true);
  assert.equal(M.noLimitsBlock(r, PF.view(r), "static", PF), null);
  const banded = none((x) => { x.profile = { ...x.profile, risk: null, reaction_2022: null }; });
  assert.equal(M.noLimitsBlock(banded, PF.view(banded), "live", PF), null);
  const judged = PF.withPaths(load("robert"));
  assert.equal(M.noLimitsBlock(judged, PF.view(judged), "live", PF), null);
});

test("limits your words set read 'from your words' in the limits block and the line, never 'set by you' (limits-QA 17:12)", () => {
  const r = PF.withPaths(load("robert"));
  r.pilot = "you";
  r.limits = { ...r.limits, crypto: 0, sector_caps: { Energy: 0 }, edited: ["crypto", "sector_caps"], from_words: ["crypto", "sector_caps.Energy", "capacity"] };
  r.checks = r.checks.map((c) => ({ ...c, source: c.rule === "crypto" ? "words" : c.rule === "max_drawdown" ? "words" : "assumed" }));
  const Y = M.limitsBlock(r, PF.view(r), "live", PF), by = (k) => Y.rows.find((x) => x.key === k);
  assert.deepEqual([by("crypto").typed, by("crypto").tag], [false, "from your words"]);
  assert.deepEqual([by("sector_caps.Energy").typed, by("sector_caps.Energy").tag], [false, "from your words"]);
  assert.equal(by("floor").tag, "from your words");
  assert.equal(Y.floorNote, "From your words; this check uses it.");
  assert.equal(M.limitsLine(r, PF.view(r)).text, "Your crypto limit, your industry limits and what you can afford to lose are from "
    + "your words; every other limit here is assumed from the profile, not set by you.");   // You: the rest is the reader's assumption
});

test("limits-QA 17:25: You runs never read 'set by you' for nothing typed; no limits says so; a typed capacity drops the stale line", () => {
  const you = PF.withPaths(load("robert"));
  you.pilot = "you";
  assert.equal(M.limitsLine(you, PF.view(you)).text, "Your limits here are assumed from the profile, not set by you.");
  const none = { ...you, limits: null, checks: [], verdict: null };
  assert.equal(M.limitsLine(none, PF.view(none)).text, "No limits set.");
  const rob = PF.withPaths(load("robert"));
  rob.capacity = { today: { line: 510000 } };
  const body = M.recheckBody(rob, { capacity: "60000" }).body;
  assert.equal(body.limits.capacity, 60000);                  // the coordinator, 17:41: a capacity edit sets capacity ...
  assert.equal(body.limits.floor, undefined);                 // ... and leaves the 15 % rule alone
  const fresh = { today: { line: 540000, sessions_below: 218 } };
  const merged = M.mergeRecheck(rob, { checks: rob.checks, verdict: rob.verdict, kpis: rob.kpis, capacity: fresh }, body, { capacity: "60000" });
  assert.deepEqual(merged.capacity, fresh);                   // the line the server drew again for $60,000
  assert.equal(merged.limits.floor, rob.limits.floor);
  assert.ok(merged.limits.edited.includes("capacity") && merged.profile.capacity === 60000 && merged.limits.capacity_dollars === 60000);
  const blank = M.mergeRecheck(rob, { checks: rob.checks, verdict: rob.verdict, kpis: rob.kpis }, body, { capacity: "60000" });
  assert.equal(blank.capacity, null);                         // no line drawn again: never the old $510,000 beside $60,000
  const kept = M.mergeRecheck(rob, { checks: rob.checks, verdict: rob.verdict, kpis: rob.kpis }, { run_id: rob.run_id, limits: { single_stock: 0.2 } }, { single: "20" });
  assert.deepEqual(kept.capacity, { today: { line: 510000 } });
});

test("a row saved before the engine wrote its source reads by the one rule: Robert's limits are assumed, a typed one is yours", () => {
  const r = PF.withPaths(load("robert"));
  const m = M.checksModel(r, PF.view(r), PF);
  assert.ok(m.rows.filter((x) => x.rule !== "missing_data").every((x) => x.srcText === "assumed"));
  const typed = PF.withPaths(load("robert"));
  typed.limits = { ...typed.limits, edited: ["single_stock"] };
  assert.equal(M.checksModel(typed, PF.view(typed), PF).rows.find((x) => x.rule === "single_stock").srcText, "set by you");
});

test("limits-QA 17:52: the limits line names the capacity, from your words or typed", () => {
  const said = PF.withPaths(load("robert"));
  said.pilot = "you";
  said.limits = { ...said.limits, crypto: 0, edited: ["crypto"], from_words: ["crypto", "capacity"] };
  assert.equal(M.limitsLine(said, PF.view(said)).text, "Your crypto limit and what you can afford to lose are from your words; every other "
    + "limit here is assumed from the profile, not set by you.");
  const typed = PF.withPaths(load("robert"));
  typed.limits = { ...typed.limits, edited: ["capacity"] };
  assert.equal(M.limitsLine(typed, PF.view(typed)).text, "What you can afford to lose is set by you; every other limit here is assumed from "
    + "the profile, not set by you.");
});

console.log(`${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
