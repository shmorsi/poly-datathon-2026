/* Lane U5 (#money, #checklist): the pure models of web/lib/money.js under node, pinned on the committed web fixtures (the
   public cut of the four saved real runs, ruling R17), design doc §2.4, §2.5, rulings R1, R11, R13, R16, R18 and the critique's
   problem 5. Run: node tests/web_u5_test.mjs (tests/test_web_lib.py runs it too). Every number the models print is a Result
   value through PF.fmt; a missing key hides its part. */
import { strict as assert } from "node:assert";
import { createRequire } from "node:module";
import { load } from "./web_fixtures.mjs";
import * as M from "../web/lib/money.js";

const PF = createRequire(import.meta.url)("../web/lib.js");
let failed = 0, passed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n${e && e.stack}`); }
}
const NB = " ", MINUS = "−";
const run = (name, edit) => { const r = PF.withPaths(load(name)); if (edit) edit(r); return [r, PF.view(r)]; };
const money = (name, edit) => { const [r, v] = run(name, edit); return M.moneyModel(r, v, PF); };
const checks = (name, edit) => { const [r, v] = run(name, edit); return M.checksModel(r, v, PF); };

/* ---- the words around the numbers ---- */
test("R1: 'in this 2021–26 replay' comes from the Result's own dates, never typed", () => {
  assert.equal(M.replayPhrase(load("robert")), "in this 2021–26 replay");
  assert.equal(M.replayPhrase({}), "in this replay");
});

test("critique 5: only a hard limit that broke reads Outside with the octagon; soft, preference and warn rows read Caution", () => {
  assert.deepEqual(M.shownStatus("fail", "hard"), { word: "Outside", tone: "outside", icon: "i-out" });
  for (const tier of ["soft", "preference", "warn"]) assert.equal(M.shownStatus("fail", tier).icon, "i-warn", tier);
  assert.equal(M.shownStatus("warn", "soft").word, "Caution");
  assert.equal(M.shownStatus("pass", "hard").word, "Inside");
  assert.equal(M.shownStatus("odd", "hard"), null);
});

test("R13 + R18: persona limits are assumed for this fictional profile, in the second person; edited limits are typed by you", () => {
  const [r, v] = run("robert");
  assert.deepEqual(M.limitsNote(r, v), { text: "Your limits are assumed for this fictional profile.", edit: true });
  const [t, tv] = run("robert", (x) => { x.limits.edited = ["floor"]; });
  assert.deepEqual(M.limitsNote(t, tv), { text: "Your limits, as you typed them.", edit: false });
  const [c, cv] = run("canadian");
  assert.equal(M.whoOf(c, cv).name, null);                                    // "Too Canadian?" is a case's title, not a name
});

test("a number opens its thread only when a facts row has the same value AND names it (never a look-alike)", () => {
  const r = load("robert");
  assert.equal(M.factFor(r, 0.4, ["the move"]), "T27");
  assert.equal(M.factFor(r, 0.35, null), null);                               // words are required
  assert.equal(M.factFor(r, 0.35, ["share of the risk"]), null);              // 0.35 is the one-sector limit
  assert.equal(M.factFor(r, r.risk.after.shares.NVDA, ["share of the risk"]), "T37");
});

/* ---- #checklist ---- */
test("#checklist (Robert): the most serious first, the asked shock's check pinned into the visible three, the deciding row marked", () => {
  const c = checks("robert");
  assert.deepEqual(c.visible.map((x) => x.rule), ["max_drawdown", "single_stock", "scenario_stress"]);
  assert.deepEqual([c.count, c.more], [8, true]);
  assert.deepEqual(c.rows.filter((x) => x.decided).map((x) => x.rule), ["max_drawdown"]);
  assert.equal(c.title, "Your floor decided the verdict.");
  assert.equal(c.sub, "8 checks, the most serious first.");
  assert.deepEqual([c.verdict.word, c.phrase], ["Outside your limits", "in this 2021–26 replay"]);
  const floor = c.rows[0];
  assert.deepEqual([floor.word, floor.icon, floor.tierText], ["Outside", "i-out", "Hard limit"]);
  /* R35 (finance F1): the floor row is the 15 % rule in percent; "$90,000" is the other limit (capacity), never this one's */
  assert.equal(floor.value, `${MINUS}34.5${NB}%`);
  assert.equal(floor.limit, `${MINUS}15${NB}%`);
  const one = c.rows.find((x) => x.rule === "single_stock");
  assert.deepEqual([one.word, one.icon, one.value, one.limit], ["Caution", "i-warn", `NVIDIA 40${NB}%`, `10${NB}%`]);
  assert.equal(c.rows.find((x) => x.rule === "sector").same, "One company");
  assert.equal(c.rows.find((x) => x.rule === "risk_concentration").value, `NVIDIA 89.6${NB}%`);
  assert.equal(c.rows.find((x) => x.rule === "scenario_stress").asked, "Tariff war");
  /* every value and limit opens its own facts row when one names it (never a look-alike: T27 "The move" is not the check's) */
  const facts = Object.fromEntries(c.rows.map((x) => [x.rule, [x.valueFact, x.limitFact]]));
  assert.deepEqual(facts.max_drawdown, ["T29", "T25"]);
  assert.deepEqual(facts.single_stock, ["T42", "T43"]);
  assert.deepEqual(facts.scenario_stress, ["T34", "T35"]);
  assert.deepEqual(facts.recovery, ["T49", null]);                           // the limit's facts row is rounded: no match, plain
});

test("#checklist: a reason prints its dates and shock names in words; the evidence note is lifted out", () => {
  const c = checks("robert");
  assert.match(c.rows[0].reason, /from 29 Nov 2021 to 14 Oct 2022/);
  const s = c.rows.find((x) => x.rule === "scenario_stress");
  assert.equal(s.reason, `In the 6 separate earlier Tariff war episodes the worst clean one cost 9.0${NB}%, beyond half your floor (7.5${NB}%).`);
  /* pre-freeze 5 (lane clarity): the date belongs to the other shock, never read as the asked episode's */
  assert.equal(s.evidence, "indicative, because one of these episodes overlapped another shock: Attack on Saudi Arabia\u2019s East-West pipeline, on 10\u00a0Sep\u00a02026");
  assert.match(c.rows[0].reason, /the mix\u2019s worst drop/);                // R18: typographic apostrophes
  assert.ok(c.rows.every((x) => !/\b\d{4}-\d{2}-\d{2}\b|_20\d\d\b/.test(`${x.reason} ${x.evidence || ""}`)), "no ISO date or event id left");
});

test("R14: each investor's checklist is decided by a different check", () => {
  assert.equal(checks("mateo").title, "Values added the caveat.");          // a preference cannot decide Outside: it added the caveat
  assert.equal(checks("mateo").binding.decidedWord, "Added the caveat");
  assert.equal(checks("mateo").visible[0].tierText, "Preference");
  assert.equal(checks("mateo").visible[0].value, `Canadian Natural 8${NB}%`);
  assert.equal(checks("amira").title, "Crypto share added the caveat.");
  assert.equal(checks("robert").binding.decidedWord, "Decided the verdict");
  assert.deepEqual(checks("amira").visible.map((x) => x.rule), ["crypto", "sector", "scenario_stress"]);   // G4: her own test (not only tech) in view
  const ca = checks("canadian");
  assert.deepEqual([ca.title, ca.binding, ca.verdict.word], ["No limit broke.", null, "Inside your limits"]);
});

test("#checklist: no shock asked, nothing pinned; no checks, no section", () => {
  assert.deepEqual(checks("robert", (r) => { r.scenario.families = []; }).visible.map((x) => x.rule), ["max_drawdown", "single_stock", "sector"]);
  assert.equal(checks("robert", (r) => { r.checks = []; }), null);
});

/* ---- #money ---- */
test("#money (Robert): 40 % of your money in NVIDIA (a weight) and 89.6 % of the risk (a share, with its tenth), each with the limit it was checked against", () => {
  const m = money("robert");
  assert.equal(m.kind, "move");
  assert.equal(m.lede, "With the move, in this 2021–26 replay");
  assert.deepEqual([m.pair.money.text, m.pair.risk.text], [`40${NB}%`, `89.6${NB}%`]);
  assert.deepEqual([m.pair.money.label, m.pair.risk.label], ["of your money was in NVIDIA", "of the risk came from NVIDIA"]);
  assert.deepEqual([m.pair.money.fact, m.pair.risk.fact], ["T27", "T37"]);      // "The move: NVDA set to", not the look-alike T42
  assert.deepEqual([m.pair.moneyTick.text, m.pair.moneyTick.label], [`10${NB}%`, "One-company limit"]);
  assert.deepEqual([m.pair.riskTick.text, m.pair.riskTick.label], [`50${NB}%`, "Warning level"]);
  assert.deepEqual(m.pair.segments.map((s) => s.key), ["NVDA", "XIU.TO", "XBB.TO", "GLD", "ZST.TO"]);   // the move first, then by money
});

test("#money (Robert): the row under it reads today then with the move, from the Result's own keys", () => {
  const by = Object.fromEntries(money("robert").stats.map((s) => [s.id, [s.today && s.today.text, s.after && s.after.text, s.after && s.after.fact]]));
  assert.deepEqual(by.bets, ["2.4", "1.2", "T38"]);
  assert.deepEqual(by["can-money"], [`87.6${NB}%`, `52.6${NB}%`, null]);
  assert.deepEqual(by["can-risk"], [`85.3${NB}%`, `9.5${NB}%`, null]);
});

test("R11: the same 40 % in three bets; the bank juror's ruling: a bet nobody asked about has no verdict and no end value, only its fall against your floor in neutral words", () => {
  const m = money("robert"), L = m.ladder;
  assert.deepEqual([L.weightText, L.countWord], [`40${NB}%`, "three"]);
  assert.deepEqual(L.rows.map((x) => x.name), ["The broad US market", "The Nasdaq-100 fund", "NVIDIA"]);
  assert.deepEqual(L.rows.map((x) => x.ddText), [`${MINUS}14.2${NB}%`, `${MINUS}18.4${NB}%`, `${MINUS}34.5${NB}%`]);
  assert.deepEqual(L.rows.map((x) => x.dollarsText), [`${MINUS}$85,205`, `${MINUS}$110,249`, `${MINUS}$207,146`]);
  assert.deepEqual(L.rows.map((x) => [x.verdict && x.verdict.word, x.endText]), [[null, null], [null, null], ["Outside your limits", "$1,847,077"]]);
  assert.deepEqual(L.rows.map((x) => x.floorWord.word), ["Held above your floor", "Broke your floor", "Broke your floor"]);
  assert.ok(L.rows.every((x) => x.floorWord.tone === "neutral"));
  assert.deepEqual([L.today.name, L.today.ddText, L.today.endText, L.today.verdict.word, L.today.floorWord.word],
    ["Today\u2019s mix", `${MINUS}10.6${NB}%`, "$911,676", "Inside your limits", "Held above your floor"]);
  assert.ok(L.scale > Math.abs(L.rows[2].dd));
  assert.equal(m.notes.floor, `Your floor, a 15${NB}% fall from any high, is assumed for this fictional profile.`);
  assert.equal(m.notes.fiction, "Fictional illustration, not a recommendation.");
  const ca = money("canadian").ladder;                                        // Too Canadian?: SPY is the move, QQQ is not asked
  assert.deepEqual(ca.rows.map((x) => [x.ticker, x.verdict && x.verdict.word, x.endText]), [["SPY", "Inside your limits", "$403,823"], ["QQQ", null, null]]);
});

test("Leave 2022 out (Robert): result.not_2022 in the floor's own terms; the dollars are the Result's (amount × depth)", () => {
  const n = money("robert").not2022;
  assert.deepEqual([n.from, n.fallText, n.dollarsText, n.amountText], ["2023", `16.9${NB}%`, `${MINUS}$101,548`, "$600,000"]);
  assert.deepEqual([n.peak, n.trough, n.back], [`23${NB}Jan${NB}2025`, `8${NB}Apr${NB}2025`, `29${NB}May${NB}2025`]);
  assert.deepEqual([n.status.word, n.floorText], ["Past the floor", `15${NB}%`]);
  assert.deepEqual(n.facts, { depth: "T59", dollars: "T60" });
});

test("Too Canadian?: leads with Canada's share of your money and of the risk, today then with the move", () => {
  const m = money("canadian");
  assert.equal(m.kind, "canada");
  assert.deepEqual([m.pair.money.text, m.pair.money.was.text], [`78.0${NB}%`, `97.5${NB}%`]);
  assert.deepEqual([m.pair.risk.text, m.pair.risk.was.text], [`68.3${NB}%`, `97.5${NB}%`]);
  assert.deepEqual(m.stats.map((s) => [s.id, s.after && s.after.text]), [["bets", "1.4"], ["move-money", `20${NB}%`], ["move-risk", `30.0${NB}%`]]);
  assert.deepEqual([m.ladder.countWord, m.not2022.status.word], ["two", "Inside the floor"]);
});

test("R19(b): the workshop's XSP question shows only when result.hedge_compare is there (lane B3's shape; a shape check)", () => {
  assert.equal(money("canadian").hedge, null);                                // absent in the committed fixture: hidden
  const H = { ticker: "SPY", weight: 0.2, amount: 250000,
    unhedged: { worst_fall: -0.1290208253453493, worst_2022: -0.12604591174609114, end_value: 403823, kind: "fact" },
    hedged_standin: { worst_fall: -0.14199012259379074, worst_2022: -0.14075434929776443, end_value: 393647, kind: "assumption" },
    spy_2022: { usd: -0.181753675572921, cad: -0.1258614751506265, currency_effect_pp: 5.59, kind: "fact" },
    method: "Hedged stand-in (\u25D0 assumption): the same mix." };
  const with_ = (h) => money("canadian", (r) => { r.hedge_compare = h; }).hedge;
  const x = with_(H);
  assert.deepEqual([x.weightText, x.unhedged.ddText, x.unhedged.y2022Text, x.unhedged.endText], [`20${NB}%`, `${MINUS}12.9${NB}%`, `${MINUS}12.6${NB}%`, "$403,823"]);
  assert.deepEqual([x.hedged.kind, x.hedged.ddText, x.hedged.endText], ["assumption", `${MINUS}14.2${NB}%`, "$393,647"]);
  assert.deepEqual([x.sentence.usd, x.sentence.cad, x.sentence.pp, x.sentence.softened], [`${MINUS}18.2${NB}%`, `${MINUS}12.6${NB}%`, "5.6", true]);
  assert.equal(x.method, "Hedged stand-in (assumption): the same mix.");   // R16: no mark glyphs in the prose
  assert.equal(with_({ ...H, hedged_standin: null }), null);                  // half there: hidden
  assert.equal(money("robert", (r) => { r.hedge_compare = H; }).hedge, null);  // only for the Canada question
});

test("no move (Mateo, Amira): the line that carried the most risk, today only, no ladder; a fiction label only with a fictional mix", () => {
  const ma = money("mateo"), am = money("amira");
  assert.deepEqual([ma.kind, ma.lede, ma.pair.ticker, ma.pair.risk.text], ["mix", "In this 2021–26 replay", "XIU.TO", `45.9${NB}%`]);
  assert.equal(ma.pair.money.fact, null);                                    // no facts row names a line's weight
  assert.ok(ma.stats.every((s) => s.after === null));
  assert.deepEqual([ma.ladder, am.notes.fiction], [null, null]);              // Amira: no move, no fictional mix shown
  assert.equal(ma.notes.fiction, "Fictional illustration, not a recommendation.");   // Mateo: the mix without CNQ.TO is fictional
  assert.deepEqual([am.pair.subject, am.pair.money.text, am.pair.risk.text], ["NVIDIA", `15${NB}%`, `27.8${NB}%`]);
});

test("a missing key hides its part, and with nothing to show there is no section", () => {
  assert.equal(money("robert", (r) => { r.ladder = null; }).ladder, null);
  assert.equal(money("robert", (r) => { r.not_2022 = null; }).not2022, null);
  assert.equal(money("robert", (r) => { delete r.risk; }).pair, null);
  assert.equal(money("robert", (r) => { delete r.risk; delete r.diversification; delete r.not_2022; delete r.ladder; }), null);
});

test("the dial moved: both sections say they stay on the size asked", () => {
  const [r, v] = run("robert");
  assert.equal(M.dialNote(r, v, 8, PF), `Shown for the size asked, NVIDIA at 40${NB}%. The dial above is at 8${NB}%.`);
  assert.equal(M.dialNote(r, v, 40, PF), null);
  assert.equal(M.dialNote(r, v, null, PF), null);
});

/* ---- the audit's fixes (11:20): your limits, a recheck with limits you type, the floor's sensitivity, the price of values ---- */
test("your limits: PF.youRows' objective, horizon and capacity, the floor's source (tolerance is not capacity), each limit; static mode says why it cannot edit", () => {
  const [r, v] = run("robert");
  const Y = M.limitsBlock(r, v, "static", PF);
  assert.deepEqual(Y.rows.map((x) => [x.label, x.value]), [["Objective", "Preserve capital, with some growth"], ["When you need the money", "In 4 years"],
    ["What you can afford to lose", "$90,000 of $600,000"], ["Your floor", `No fall of more than 15${NB}% from a high`], ["One company", `Up to 10${NB}%`], ["One sector", `Up to 35${NB}%`], ["Crypto", `Excluded (0${NB}%)`],
    ["Values", "Off"]]);      // LIMITS_MODEL CONFLICTS (binding, 16:55): 0 reads as an exclusion, the values screen On / Off
  assert.equal(Y.floorNote, "Your tolerance, assumed from the profile, not set by you. What you can afford to lose is the other limit, in dollars.");   // R35
  /* compliance (regulation flaw hunter): a persona's limits come from its profile, never typed by the client */
  assert.deepEqual([Y.note, Y.edit.live, Y.edit.why], ["Your limits here are assumed from the profile, not set by you.", false, "Editing your limits needs the live app."]);
  assert.deepEqual([M.limitsBlock(r, v, "live", PF).edit.live, Y.edit.capacity, Y.edit.single], [true, 90000, 10]);
});

test("recheck: the body of POST /api/recheck from what you typed (R35, the controller 17:41: the capacity as itself, never a floor), refused in plain words", () => {
  const r = load("robert");
  assert.deepEqual(M.recheckBody(r, { capacity: "210000", single: "20" }), { body: { run_id: r.run_id, limits: { capacity: 210000, single_stock: 0.2 } } });
  assert.deepEqual(M.recheckBody(r, { capacity: "", single: "" }), { error: "Change a limit first." });
  assert.match(M.recheckBody(r, { capacity: "700000" }).error, /^Enter a loss between \$1 and /);
  assert.equal(M.recheckBody(r, { single: "0" }).error, "Enter a one-company limit between 1 % and 100 %.");
  assert.equal(M.recheckBody({ ...r, run_id: null }, { capacity: "1" }).error, "This run cannot be checked again here.");
});

test("recheck: the server's answer merged into the Result (checks, verdict, the capacity you typed and its line drawn again, marked typed by you)", () => {
  const r = load("robert"), made = M.recheckBody(r, { capacity: "210000" });
  const line = { amount: 600000, capacity: 210000, line: 390000, today: { line: 390000, sessions_below: 0 }, after: { line: 390000, sessions_below: 12 } };
  const rc = { checks: r.checks, verdict: r.verdict, kpis: r.kpis, sensitivity: null, baseline: { checks: r.baseline.checks, verdict: r.baseline.verdict },
    deep_history: null, capacity: line };                                  // pipeline.recheck: the capacity line for the new dollars
  const x = M.mergeRecheck(r, rc, made.body, { capacity: "210000" });
  assert.deepEqual([x.verdict, x.limits.floor, x.profile.capacity, x.limits.edited.includes("capacity"), x.limits.edited.includes("floor"), x.rechecked],
    [r.verdict, r.limits.floor, 210000, true, false, true]);                 // R35: the 15 % rule stays; the capacity is its own limit
  assert.deepEqual([x.series, x.capacity], [r.series, line]);              // the replay's paths stay those of the run
  const v = PF.view(PF.withPaths(x)), Y = M.limitsBlock(x, v, "live", PF), c = M.checksModel(x, v, PF);
  assert.deepEqual(Y.rows.filter((y) => y.typed).map((y) => y.label), ["What you can afford to lose"]);   // R35 names: only the capacity is yours
  assert.equal(Y.rows[2].value, "$210,000 of $600,000: stay above $390,000");
  assert.equal(c.binding.rule, "max_drawdown");                              // the same rule check_order writes
});

test("the floor row says what would change the answer (result.sensitivity.sentence, the deck's 'change a hypothesis')", () => {
  const c = checks("robert"), floor = c.rows.find((x) => x.rule === "max_drawdown");
  assert.equal(floor.change, `Outside your limits until your floor is ${MINUS}34.5${NB}% or lower; at that floor the verdict would be Inside, with caveats because NVDA would still be beyond the single-company limit.`);
  assert.equal(checks("robert", (r) => { r.sensitivity = null; }).rows.find((x) => x.rule === "max_drawdown").change, null);
});

test("Mateo's test: what your values cost in this replay (result.price_of_values), facts beside the assumption, no new number", () => {
  const V = money("mateo").values;
  assert.deepEqual(V.now.rows.map((x) => [x.label, x.text, x.fact]), [["Worst fall", `${MINUS}11.4${NB}%`, "T24"], ["Growth per year", `11.5${NB}%`, "T25"],
    ["Worst War & oil shock", `${MINUS}4.2${NB}%`, "T30"]]);
  assert.deepEqual(V.alt.rows.map((x) => x.text), [`${MINUS}12.9${NB}%`, `9.8${NB}%`, `${MINUS}5.8${NB}%`]);
  assert.deepEqual([V.now.kind, V.alt.kind, V.removed], ["fact", "assumption", ["CNQ.TO"]]);
  assert.equal(V.now.note, `Including CNQ.TO, 8${NB}% of your money, as the checks judged it.`);
  assert.equal(V.sentence, `In this replay, your mix without CNQ.TO grew 9.8${NB}% a year against 11.5${NB}%, and its worst fall was ${MINUS}12.9${NB}% against ${MINUS}11.4${NB}%.`);
  assert.equal(money("mateo").notes.fiction, "Fictional illustration, not a recommendation.");
  assert.equal(money("robert").values, null);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
