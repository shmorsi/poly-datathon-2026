// Lane sc-u: the pure helpers of #scenario (web/lib/scenario.js). Values are pinned on the synthetic Result below (the shape of
// lane sc-b's result.scenarios, committed here, ruling R17); the public fixtures are checked for shape only once they carry it.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { load, NAMES } from "./web_fixtures.mjs";
import * as L from "../web/lib/scenario.js";

const PF = createRequire(import.meta.url)("../web/lib.js");
let n = 0;
const t = (name, fn) => { fn(); n += 1; };

const AFTER = { "XIU.TO": 0.27, "XBB.TO": 0.21, GLD: 0.06, "ZST.TO": 0.06, NVDA: 0.4 };
const TODAY = { "XIU.TO": 0.45, "XBB.TO": 0.35, GLD: 0.1, "ZST.TO": 0.1 };
function result(extra) {
  return { run_id: "r1", pilot: "robert", status: "ok", question_type: "change", as_of: "2026-11-12", amount: 600000, portfolio: AFTER, baseline: { portfolio: TODAY },
    limits: { floor: -0.15, capacity_dollars: 90000 }, profile: { capacity: 90000 }, scenario: { families: ["tariffs"] },
    tipping_point: { ticker: "NVDA" },
    scenarios: { kind: "hypothetical", method: "A linear model.",
      factors: [{ id: "canada", label: "Canadian stocks", unit: "pct" }, { id: "tech", label: "Tech stocks", unit: "pct", bounds: [-0.9, 0.9] },
        { id: "energy", label: "Energy stocks", unit: "pct" }, { id: "rates", label: "Canada 10-year rate", unit: "pp" },
        { id: "usdcad", label: "US dollar vs CAD", unit: "pct" }, { id: "gold", label: "Gold", unit: "pct" }],
      presets: [
        { id: "ai", label: "AI and chip slump like 2022", short: "2022 tech fall", source: "QQQ in 2022.", shocks: { tech: -0.286 },
          today: { fall: -0.0129, dollars: -7740, floor_status: "held" }, after: { fall: -0.2079, dollars: -124740, floor_status: "broke" },
          contributions: { NVDA: -0.2002, "XIU.TO": -0.0077, "XBB.TO": 0, GLD: 0, "ZST.TO": 0 } },
        { id: "tariff", label: "Tariff shock like Apr 2025", source: "Liberation Day.",
          shocks: { canada: -0.081, tech: -0.131, energy: -0.152, rates: 0.0016, usdcad: 0.012, gold: 0.031, nope: 0.5 },
          today: { fall: -0.0319, dollars: -19151, floor_status: false }, after: { fall: -0.1555, dollars: -93300, floor_status: true },
          contributions: { after: { NVDA: -0.097, "XIU.TO": -0.0322, GLD: 0.0021 }, today: { "XIU.TO": -0.0536 } } },
        { id: "cad", label: "Canadian dollar slide", source: "USD/CAD.", shocks: { usdcad: 0.074 },
          today: { fall: 0.0067, dollars: 4020, floor_status: "held" }, after: { fall: 0.0292, dollars: 17520, floor_status: "held" }, contributions: {} },
        { id: "empty", label: "Nothing known", shocks: { zzz: 0.1 }, today: { fall: 0 }, after: { fall: 0 } },
      ],
      validation: [{ episode: "The 2022 fall", real_today: -0.118, model_today: -0.104, real_after: -0.345, model_after: -0.312, gap_pp: 3.3 },
        { episode: "Liberation Day", real_today: -0.046, model_today: -0.049, real_after: -0.118, model_after: -0.126, gap_pp: -0.8 }] },
    ...(extra || {}) };
}

t("the model reads the engine's factors, presets and validation; unknown factors and empty presets drop", () => {
  const m = L.scenarioModel(result(), PF);
  assert.equal(m.show, true);
  assert.deepEqual(m.presets.map((p) => p.id), ["ai", "tariff", "cad"]);
  assert.equal(m.presets[1].shocks.nope, undefined);
  assert.deepEqual(m.byId.tech.bounds, { lo: -0.9, hi: 0.9, given: true });
  assert.deepEqual(m.byId.usdcad.bounds, { lo: -3 * 0.074, hi: 3 * 0.074, given: false });   // the server's rule over the page's moves
  assert.equal(m.move.name, "NVIDIA");
  assert.equal(m.floor.v, -0.15);
  assert.equal(L.scenarioModel({ ...result(), scenarios: null }, PF).staticOnly, true);
  assert.equal(L.scenarioModel(null, PF).show, false);
  assert.equal(L.scenarioModel({ ...result(), scenarios: { factors: [], presets: [] } }, PF).staticOnly, true);
});

t("one answer sentence with the server's numbers and floor class (status.js vocabulary)", () => {
  const m = L.scenarioModel(result(), PF);
  const o = L.outcomeOf(m.presets[0].answer, m, PF);
  assert.equal(o.sentence.map((x) => x.text).join(""),
    "In this made-up scenario, your mix with the move would fall about −20.8 % (−$124,740): your floor would break.");
  assert.deepEqual(o.sides.map((x) => [x.key, x.fallText, x.cls, x.word, x.tone]), [["after", "−20.8 %", "broke", "Past your floor", "outside"],
    ["today", "−1.3 %", "held", null, "neutral"]]);   // outside the gap: said plainly, no pass word
  assert.equal(o.main.icon, "i-out");
  assert.equal(o.contributions[0].ticker, "NVDA");
  assert.equal(o.contributions[0].isMove, true);
  assert.equal(o.contributions[0].w, 1);
  const tariff = L.outcomeOf(m.presets[1].answer, m, PF);          // a boolean beyond: within 1 point of the floor = touched (R11)
  assert.equal(tariff.main.cls, "too_close");                                     // touched is always inside the gap
  assert.equal(tariff.main.close, "Too close to call: inside the engine\u2019s 3.3\u2011point gap on real episodes.");
  assert.deepEqual(tariff.contributions.map((x) => [x.ticker, x.text]), [["NVDA", "−9.7 %"], ["XIU.TO", "−3.2 %"], ["GLD", "+0.2 %"]]);
  const gain = L.outcomeOf(m.presets[2].answer, m, PF);
  assert.equal(gain.sentence.map((x) => x.text).join(""),
    "In this made-up scenario, your mix with the move would rise about +2.9 % (+$17,520); your floor is a 15\u00a0% fall from a high.");
});

t("too close to call: the engine's margin inside its own gap reads amber with its numbers, never a pass word (controller, 14:00)", () => {
  const m = L.scenarioModel(result(), PF);
  const o = L.outcomeOf({ today: { fall: -0.0319, dollars: -19151, floor_status: "held" },
    after: { fall: -0.145, dollars: -87000, floor_status: "too_close", margin_pp: 0.5, gap_pp: 11.5 } }, m, PF);
  const said = o.sentence.map((x) => x.text).join("");
  assert.equal(said, "In this made-up scenario, your mix with the move would fall about \u221214.5\u00a0% (\u2212$87,000). "
    + "Too close to call: 0.5\u00a0points from your floor, inside the engine\u2019s 11.5\u2011point gap on real episodes.");
  assert.deepEqual([o.main.cls, o.main.word, o.main.tone, o.main.icon], ["too_close", "Too close to call", "caveat", "i-warn"]);
  assert.ok(!/stay above|Held above|inside your|safe/i.test(said + o.main.word));
  const bare = L.outcomeOf({ after: { fall: -0.145, floor_status: "too_close" } }, m, PF);  // no margin or gap sent: no margin figure
  assert.equal(bare.main.close, "Too close to call: inside the engine\u2019s 3.3\u2011point gap on real episodes.");   // the run's widest gap
  const odd = L.outcomeOf({ after: { fall: -0.12, floor_status: "maybe" } }, m, PF);      // a status the page cannot name
  assert.deepEqual([odd.main.cls, odd.main.word, odd.main.tone, odd.main.close], ["unknown", "Too close to call", "caveat", L.UNJUDGED]);
  assert.ok(!/stay above/.test(odd.sentence.map((x) => x.text).join("")));
  const none = L.outcomeOf({ after: { fall: -0.12, floor_status: null } }, m, PF);       // no judgement sent: no floor clause at all
  assert.deepEqual([none.main.cls, none.main.close], [null, null]);
  assert.equal(L.tooCloseLine({ margin_pp: -1, gap_pp: 3.3 }), "Too close to call: 1.0\u00a0point from your floor, inside the engine\u2019s 3.3\u2011point gap on real episodes.");
});

t("bank juror (17:20): no reassuring line anywhere; inside the gap too close to call, outside it said plainly; a copy of a real episode shows the real replay", () => {
  const m = L.scenarioModel(result(), PF);
  const REASSURE = /stay above|held above|holds? above|survive|safe|inside your limits/i;
  for (const p of m.presets) {
    const o = L.outcomeOf(p.answer, m, PF);
    const said = o.sentence.map((x) => x.text).join("") + o.sides.map((s) => s.word || "").join(" ");
    assert.ok(!REASSURE.test(said), `${p.id}: ${said}`);
  }
  const far = L.outcomeOf({ after: { fall: -0.02, dollars: -12000, floor_status: "held", margin_pp: 13, gap_pp: 2.3 } }, m, PF);
  assert.equal(far.sentence.map((x) => x.text).join(""),
    "In this made-up scenario, your mix with the move would fall about \u22122.0\u00a0% (\u2212$12,000); your floor is a 15\u00a0% fall from a high.");
  assert.deepEqual([far.main.word, far.main.icon, far.main.close], [null, null, null]);
  const near = L.outcomeOf({ after: { fall: -0.113, dollars: -67997, floor_status: "held", margin_pp: 3.7, gap_pp: 11.5 } }, m, PF);
  assert.equal(near.main.close, "Too close to call: 3.7\u00a0points from your floor, inside the engine\u2019s 11.5\u2011point gap on real episodes.");
  assert.equal(near.main.cls, "too_close");
  const deep = L.outcomeOf({ after: { fall: -0.4, dollars: -240000, floor_status: "broke", margin_pp: -25, gap_pp: 11.5 } }, m, PF);
  assert.equal(deep.main.would, "your floor would break");
  const sc = { ...result().scenarios, validation: [{ episode: "tariffs_2025", label: "Liberation Day", real_after: -0.09, model_after: -0.113, gap_pp: -2.3 }],
    presets: [{ id: "tariffs_2025", label: "Tariff shock like Apr 2025", headline: null, window: { start: "2025-04-02", end: "2025-04-08" },
      shocks: { tech: -0.13 }, measured: ["tech"], after: { fall: -0.113, dollars: -67997, floor_status: "held" }, today: { fall: -0.058, floor_status: "held" } }] };
  const r = result({ scenarios: sc, breaches: [{ peak_date: "2021-11-29", trough_date: "2022-10-14", depth: -0.345 },
    { peak_date: "2025-01-23", trough_date: "2025-04-08", depth: -0.1692, loss_dollars: -101548 }] });
  const mr = L.scenarioModel(r, PF);
  assert.deepEqual(mr.presets[0].real && [mr.presets[0].real.lead, mr.presets[0].real.figure, mr.presets[0].real.tail],
    ["The real April 2025 fall with this move: ", "\u221216.9\u00a0%", ", past your floor."]);
  const tdy = L.scenarioModel(result({ scenarios: { ...sc, presets: [{ ...sc.presets[0], headline: "tech" }], validation: [] }, breaches: r.breaches }), PF);
  assert.equal(tdy.presets[0].real, null);                                            // one factor's measured size: not a copy
});

t("no move: the one mix, never 'with the move'", () => {
  const r = result({ question_type: "shock", baseline: null, portfolio: TODAY });
  const m = L.scenarioModel(r, PF);
  assert.equal(m.move, null);
  const o = L.outcomeOf({ today: { fall: -0.05, dollars: -30000, floor_status: "held" }, contributions: { "XIU.TO": -0.05 } }, m, PF);
  assert.equal(o.sides.length, 1);
  assert.equal(o.sentence.map((x) => x.text).join(""), "In this made-up scenario, your mix would fall about −5.0 % (−$30,000); your floor is a 15\u00a0% fall from a high.");
  assert.equal(L.outcomeOf({ fall: -0.2, dollars: -120000, floor_status: "broke" }, m, PF).main.cls, "broke");   // one flat answer
  assert.equal(L.outcomeOf({ today: { fall: "x" } }, m, PF), null);
});

t("a factor's move as the chip prints it; gaps in points", () => {
  assert.equal(L.shockText(0.52, "pct", PF), "+52.0 %");
  assert.equal(L.shockText(-0.286, "pct", PF), "−28.6 %");
  assert.equal(L.shockText(0.0186, "pp", PF), "+1.9\u00a0points");                  // rates as fractions: 0.01 = 1 point (lane sc-b)
  assert.equal(L.shockText(-0.01, "pp", PF), "\u22121.0\u00a0point");
  assert.equal(L.shockText(0.0234, "pp", PF), "+2.3\u00a0points");
  assert.equal(L.shockText(0, "pct", PF), "0.0 %");
  assert.equal(L.shockText(null, "pct", PF), "");
  assert.equal(L.pointsText(-0.8), "0.8 points");
  assert.equal(L.pointsText(1), "1.0 point");
  assert.equal(L.gapWords(1.3), "1.3\u00a0points higher");
  assert.equal(L.gapWords(-11.5), "11.5\u00a0points lower");
  assert.equal(L.gapWords(0.04), "the same");
  assert.equal(L.signedPct(0.213, PF), "+21.3\u00a0%");
  assert.equal(L.signedPct(-0.085, PF), "\u22128.5\u00a0%");
});

t("R22: at most three chips in view, the rest fold; the closed section shows six figures or fewer", () => {
  const m = L.scenarioModel(result(), PF), checked = L.checkedLine(m.validation);
  assert.deepEqual(checked, { lead: "Checked against real episodes: within ", figure: "3.3 points", tail: "." });
  for (const p of m.presets) {
    const chips = L.chipsOf(p.shocks, m, {});
    assert.ok(chips.shown.length <= L.VISIBLE_CHIPS, p.id);
    assert.equal(chips.shown.length + chips.folded.length, Object.values(p.shocks).filter((v) => v !== 0).length, p.id);
    const figs = L.closedFigures(chips, L.outcomeOf(p.answer, m, PF), checked, PF, m);
    assert.ok(figs.length <= 6, `${p.id}: ${figs.join(" | ")}`);
  }
  const tariff = L.chipsOf(m.presets[1].shocks, m, {});
  assert.deepEqual(tariff.shown.map((c) => c.id), ["canada", "energy", "rates"]);    // the most extreme against their bounds, in order
  const withBetas = L.scenarioModel(result({ scenarios: { ...result().scenarios, betas: { NVDA: { tech: 1.75, usdcad: 0.85 }, GLD: { gold: 1 } } } }), PF);
  assert.equal(withBetas.lead, "tech");                                              // the moved holding's largest sensitivity
  assert.deepEqual(L.chipsOf(withBetas.presets[1].shocks, withBetas, {}).shown.map((c) => c.id), ["canada", "tech", "energy"]);
  assert.deepEqual(tariff.idle, []);
  const one = L.chipsOf({ tech: -0.2, gold: 0 }, m, {}, 3, new Set(["gold"]));
  assert.deepEqual(one.shown.map((c) => [c.id, c.value]), [["tech", -0.2], ["gold", 0]]);   // a factor the investor added, at zero
  assert.ok(one.idle.every((f) => f.id !== "tech" && f.id !== "gold"));
});

t("the navigator's reading: known factors only, inside the bounds, unmapped words said plainly", () => {
  const m = L.scenarioModel(result(), PF);
  const r = L.readingOf({ shocks: { tech: -2, energy: 0.52, mars: 0.1 }, why: { tech: "2022.", mars: "no" }, unmapped: ["elections"], clarify: null }, m);
  assert.deepEqual(r.shocks, { tech: -2, energy: 0.52 });                            // never clamped by the page (the engine says no)
  assert.ok(L.trackOf(m.byId.energy, 0.52).hi >= 0.52);                               // a page-derived track widens to the value
  assert.deepEqual(r.why, { tech: "2022." });
  assert.deepEqual(r.dropped, ["mars"]);
  assert.equal(r.unmapped, "No factor matches ‘elections’; say which channel you mean.");
  assert.equal(L.unmappedLine(["a", "b", "c"]), "No factor matches ‘a’, ‘b’ or ‘c’; say which channel you mean.");
  const none = L.readingOf({ shocks: {}, unmapped: ["aliens"], clarify: "Which channel do you mean?" }, m);
  assert.equal(none.empty, true);
  assert.equal(none.clarify, "Which channel do you mean?");
  assert.equal(L.readingOf(null, m).empty, true);
  const blocked = L.readingOf({ status: "blocked", message: "Describe a future, not an order.", shocks: { tech: -0.2 } }, m);
  assert.deepEqual([blocked.blocked, blocked.empty, blocked.shocks, blocked.message], [true, true, {}, "Describe a future, not an order."]);
  assert.equal(L.readingOf({ status: "ok", method: "bedrock", shocks: { tech: -0.2 } }, m).by.startsWith("Read by the navigator on Amazon Bedrock"), true);
  assert.equal(L.readingOf({ status: "ok", method: "keyword", message: "Amazon Bedrock is off.", shocks: { tech: -0.2 } }, m).by, "Amazon Bedrock is off.");
  const named = L.scenarioModel(result({ scenarios: { ...result().scenarios, factors: [{ id: "tech", label: "Tech stocks (QQQ)", unit: "return" }] } }), PF);
  assert.deepEqual([named.byId.tech.label, named.byId.tech.full, named.byId.tech.unit], ["Tech stocks", "Tech stocks (QQQ)", "pct"]);
});

t("tracks: geometry from the bounds, marks at the precedents, a snap lands on the precedent itself", () => {
  const m = L.scenarioModel(result(), PF), f = m.byId.tech;
  const tr = L.trackOf(f, -0.286);
  assert.equal(tr.zero, 0.5);
  assert.ok(Math.abs(tr.x - (0.9 - 0.286) / 1.8) < 1e-12);
  assert.deepEqual(tr.marks.map((x) => x.label), ["2022 tech fall", "Tariff shock like Apr 2025"]);
  assert.equal(L.snapTo(f, -0.28), -0.286);
  assert.equal(L.snapTo(f, -0.5), -0.5);
  assert.equal(L.snapTo(f, 0.004), 0);
  assert.equal(L.trackOf({ bounds: null, marks: [] }, 0), null);
  assert.ok(Math.abs(L.keyStep(f, -0.2, "ArrowRight", 0.005) - -0.195) < 1e-12);
  assert.equal(L.keyStep(f, -0.2, "PageDown", 0.005), -0.286);                        // the next engraved precedent
  assert.equal(L.keyStep(f, -0.286, "PageDown", 0.005), -0.9);                         // then the bound
  assert.equal(L.keyStep(f, -0.286, "PageUp", 0.005), -0.131);
  assert.equal(L.keyStep(f, 0.89, "ArrowUp", 0.05), 0.9);                              // never past the bound
  assert.equal(L.keyStep(f, -0.3, "Home", 0.005), 0);
  assert.equal(L.keyStep(f, -0.3, "a", 0.005), null);
});

t("the reading's anchored precedent is engraved once; the engine's implied co-moves fold under 'what moves with it'", () => {
  const m = L.scenarioModel(result(), PF);
  const ans = { anchors: { energy: "oil_2022", tech: "nope" }, marks: { energy: [{ id: "oil_2022", label: "2022 oil spike", value: 0.6517 }], tech: [] } };
  const extra = L.anchoredMarks(ans);
  assert.deepEqual(extra, { energy: { value: 0.6517, label: "2022 oil spike", id: "oil_2022" } });
  const m2 = L.withMarks(m, extra);
  assert.deepEqual(m2.byId.energy.marks.map((x) => x.label), ["Tariff shock like Apr 2025", "2022 oil spike"]);
  assert.ok(m2.byId.energy.bounds.hi >= 3 * 0.6517 - 1e-12);                          // a page-derived track re-measured
  assert.equal(L.withMarks(m, {}), m);
  const o = L.outcomeOf({ shocks: { tech: -0.3, energy: 0.4, gold: -0.016 }, measured: ["tech", "energy"], implied: ["gold"],
    today: { fall: -0.01, dollars: -6182, floor_status: "held", uncovered: ["BTC-USD"] }, after: { fall: -0.204, dollars: -122379, floor_status: "broke" },
    contributions: { NVDA: -0.2 }, contributions_mix: "after" }, m, PF);
  assert.deepEqual(o.implied, { gold: -0.016 });
  assert.deepEqual(o.uncovered, ["BTC-USD"]);
  const chips = L.chipsOf({ tech: -0.3, energy: 0.4 }, m, {}, 3, null, o.implied);
  assert.deepEqual(chips.implied.map((c) => [c.id, c.implied]), [["gold", true]]);
  assert.equal(L.moreLine(chips), "One more factor moves with it, as they did week to week; it is in the details.");
  assert.equal(L.moreLine({ folded: [1, 2], implied: [3] }), "Three more factors move; they are in the details.");
  assert.equal(L.moreLine({ folded: [], implied: [] }), null);
  const v = L.scenarioModel(result({ scenarios: { ...result().scenarios, validation: [{ episode: "drawdown_2022", label: "The 2022 drawdown",
    real_today: -0.085, model_today: -0.085, real_after: -0.26, model_after: -0.247, gap_pp_today: 0, gap_pp_after: 1.3, gap_pp: 1.3 }] } }), PF).validation;
  assert.deepEqual([v.rows[0].episode, v.rows[0].gap, v.worstGap], ["The 2022 drawdown", { today: 0, after: 1.3 }, 1.3]);
});

t("live, a Result without a scenarios block still shows the section; the reading brings its factors, bounds and marks", () => {
  const r = result({ scenarios: null });
  const st = L.scenarioModel(r, PF);                                                    // static: the question and one honest line
  assert.deepEqual([st.show, st.staticOnly, st.presets.length], [true, true, 0]);
  assert.ok(!/\d/.test(L.LINE.staticOnly) && /live app/.test(L.LINE.staticOnly));
  const m = L.scenarioModel(r, PF, { live: true });
  assert.deepEqual([m.show, m.liveOnly, m.factors.length, m.presets.length, m.move.name], [true, true, 0, 0, "NVIDIA"]);
  assert.equal(L.firstPreset(r, m), null);
  const read = { status: "ok", shocks: { energy: 0.6517 }, why: { energy: "Oil." }, anchors: { energy: "oil_2022" },
    factors: [{ id: "energy", label: "Energy stocks (XOM, CNQ.TO, ENB.TO)", unit: "return" }, { id: "rates", label: "Canada 10-year yield", unit: "pp" }],
    bounds: { energy: [-1, 1.97], rates: [-0.068, 0.068] }, marks: { energy: [{ id: "oil_2022", label: "2022 oil spike", value: 0.6517 }] } };
  const mb = L.withBook(m, read);
  assert.deepEqual(mb.factors.map((f) => [f.id, f.label, f.unit]), [["energy", "Energy stocks", "pct"], ["rates", "Canada 10-year yield", "pp"]]);
  assert.deepEqual(mb.byId.energy.bounds, { lo: -1, hi: 1.97, given: true });
  assert.deepEqual(mb.byId.energy.marks, [{ value: 0.6517, label: "2022 oil spike", id: "oil_2022" }]);
  assert.deepEqual(L.readingOf(read, mb).shocks, { energy: 0.6517 });
  assert.equal(L.withBook(L.scenarioModel(result(), PF), read).liveOnly, undefined);   // a Result's own block always wins
  assert.equal(L.withBook(m, null), m);
});

t("a move on record's numbers carry their fact ids (result.scenarios.facts), only where result.facts has the row", () => {
  const sc = { ...result().scenarios, facts: { "presets.ai.after.fall": "T40", "presets.ai.after.dollars": "T41", "presets.ai.today.fall": "T99" } };
  const m = L.scenarioModel(result({ scenarios: sc, facts: { T40: { value: -0.2079 }, T41: { value: -124740 } } }), PF);
  assert.equal(L.factOf(m, "presets.ai.after.fall"), "T40");
  assert.equal(L.factOf(m, "presets.ai.after.dollars"), "T41");
  assert.equal(L.factOf(m, "presets.ai.today.fall"), null);                          // no facts row: plain text
  assert.equal(L.factOf(null, "x"), null);
});

t("the two requests carry the run's own mixes, limits and amount; the opening move matches the asked family", () => {
  const r = result();
  assert.deepEqual(L.readBody(r, "  oil up  "), { text: "oil up", portfolio: AFTER, as_of: "2026-11-12" });   // server.py ScenarioReadBody
  assert.equal(L.readBody({ ...r, as_of: "2023-06-30" }, "x").as_of, "2023-06-30");   // red gate 3: the run's own decision date
  assert.equal(L.scenarioBody({ ...r, as_of: "2023-06-30" }, {}).as_of, "2023-06-30");
  assert.equal(L.readBody({ ...r, as_of: undefined }, "x").as_of, null);
  const b = L.scenarioBody(r, { tech: -0.2, x: "bad" });
  assert.deepEqual(Object.keys(b).sort(), ["amount", "as_of", "baseline", "fill", "limits", "portfolio", "shocks"]);   // server.py ScenarioBody
  assert.equal(b.as_of, "2026-11-12");
  assert.deepEqual(b.shocks, { tech: -0.2 });
  assert.deepEqual(b.limits, { floor: -0.15 });
  assert.equal(b.amount, 600000);
  assert.equal(b.limits.floor, -0.15);
  assert.equal(L.sameShocks({ tech: -0.2, gold: 0 }, { tech: -0.2 }), true);
  assert.equal(L.sameShocks({ tech: -0.2 }, { tech: -0.21 }), false);
  const m = L.scenarioModel(r, PF);
  assert.equal(L.firstPreset(r, m).id, "tariff");
  assert.equal(L.firstPreset({ ...r, scenario: { families: ["chips"] } }, m).id, "ai");
  assert.equal(L.firstPreset({ ...r, scenario: { families: [] } }, m).id, "ai");
});

t("closed, the section is one line with no number (controller ruling, 12:40)", () => {
  assert.deepEqual([L.LINE.question, L.LINE.open, L.LINE.close], ["Would it survive a future you imagine?", "Try your own scenario", "Close your scenario"]);
  for (const s of Object.values(L.LINE)) assert.ok(!/\d/.test(s) && !s.trim().endsWith("\u2192"), s);
});

t("the words: no advice word, typographic quotes, examples in the investor's kind of words", () => {
  const ADVICE = /\b(buy|sell|hold|you should|we recommend|recommended)\b/i;
  for (const e of L.EXAMPLES) assert.ok(!ADVICE.test(e), e);
  assert.ok(L.EXAMPLES.some((e) => /^Et si/.test(e)));                               // a French one (R19c)
  assert.equal(L.holdingName("XBB.TO"), "Canadian bonds");
  assert.equal(L.holdingName("ZZZ"), "ZZZ");
});

t("the public fixtures, once they carry result.scenarios, read without error and keep the closed budget", () => {
  for (const name of NAMES) {
    const r = load(name);
    const m = L.scenarioModel(r, PF);
    if (!r.scenarios) { assert.equal(m.staticOnly, true); continue; }
    if (!m.show) continue;
    const checked = L.checkedLine(m.validation);
    for (const p of m.presets) {
      const o = L.outcomeOf(p.answer, m, PF);
      if (!o) continue;
      assert.ok(L.closedFigures(L.chipsOf(p.shocks, m, {}), o, checked, PF, m).length <= 6, `${name} ${p.id}`);
    }
  }
});

console.log(`web_scenario_test: ${n} groups passed`);
