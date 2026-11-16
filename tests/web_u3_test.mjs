// Lane U3: the race chart's pure model (web/lib/race.js) under node. Synthetic Results pin the rules; the committed FAKE
// Result and, when present, the real saved runs (/tmp/epi_runs_v1, /tmp/epi_video/runs) pin the shapes on real numbers.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(import.meta.url);
globalThis.PF = require("../web/lib.js");
const { raceModel, raceModelFromSeries, ribbonOf, episodesOf, hatchOf, weeklyIndices, tenths, pastFloor, timeOf, typo } = await import("../web/lib/race.js");
const PF = globalThis.PF, M = "−";

// rounding like governance.round_pp (pitfall 5): -15.00004 % is inside a -15 % floor, -15.06 % is past it
assert.equal(tenths(-0.1500004), -150);
assert.equal(pastFloor(-0.1500004, -0.15), false);
assert.equal(pastFloor(-0.1506, -0.15), true);
for (const x of [-0.1494, -0.14951, -0.1495, -0.15049, -0.1505, -0.151, -0.149, -0.3, 0.02, -0.1521, -0.1479])   // the fast path agrees with round_pp
  assert.equal(pastFloor(x, -0.15), tenths(x) < tenths(-0.15), String(x));
assert.equal(timeOf("1973-01"), Date.UTC(1973, 0, 1));
assert.equal(timeOf("2022-10-14"), Date.UTC(2022, 9, 14));
assert.ok(Number.isNaN(timeOf("2022-13-01")) && Number.isNaN(timeOf(null)));

// typographic quotes (R18)
assert.equal(typo('"Liberation Day" reciprocal tariffs'), "\u201cLiberation Day\u201d reciprocal tariffs");
assert.equal(typo("Trump's Taiwan remarks ('again')"), "Trump\u2019s Taiwan remarks (\u2018again\u2019)");
// the ribbon follows every new high; one episode per high, its stretches past the floor, closed by the next high
const line = [100, 90, 80, 86, 79, 100, 120, 95, 130];
assert.deepEqual(ribbonOf(line, -0.15).map((x) => Math.round(x * 100) / 100), [85, 85, 85, 85, 85, 85, 102, 102, 110.5]);
const eps = episodesOf(line, -0.15);
assert.equal(eps.length, 2);
assert.deepEqual([eps[0].peak, eps[0].trough, eps[0].recover, eps[0].stretches], [0, 4, 5, [[2, 2], [4, 4]]]);
assert.equal(Math.round(eps[0].depth * 1000) / 1000, -0.21);
assert.deepEqual([eps[1].peak, eps[1].trough, eps[1].recover, eps[1].stretches], [6, 7, 8, [[7, 7]]]);
assert.deepEqual(episodesOf([100, 85, 100], -0.15), []);                       // exactly on the floor is not past it
assert.deepEqual(episodesOf([100, null, 80, 70, null, 100], -0.15)[0].stretches, [[2, 3]]);   // a skipped day joins a stretch
// the hatch starts and ends where the line crosses the floor level
const ts = line.map((_, k) => k * 10), rib = ribbonOf(line, -0.15);
const h = hatchOf(ts, line, rib, eps[0].stretches[0]);
assert.deepEqual(h[0], [15, 85]);                                            // 90 -> 80 crosses 85 halfway
assert.deepEqual(h[1], [20, 80]);
assert.ok(Math.abs(h[2][0] - (20 + 10 * (5 / 6))) < 1e-9);                     // 80 -> 86 crosses 85 at 5/6
// weekly cadence keeps the days the Result names
assert.deepEqual(weeklyIndices(["a", "b", "c", "d", "e", "f", "g", "h"].map((x, i) => `2022-01-0${i + 1}`), ["2022-01-03"]), [0, 2, 5, 7]);

// ---- a synthetic Result with a move: three sizes, nine weekly points, one breach the server measured on daily data ----
const D = ["2021-11-12", "2021-11-19", "2021-11-26", "2021-12-03", "2021-12-10", "2021-12-17", "2021-12-24", "2021-12-31", "2022-01-07"];
const syn = () => ({
  amount: 1000, question_type: "change", portfolio: { AAA: 0.6, NVDA: 0.4 }, baseline: { portfolio: { AAA: 1 } }, verdict: "Incompatible",
  profile: { name: "Robert" }, pilot: "robert", limits: { floor: -0.15 }, scenario: { families: ["tariffs"], change: { ticker: "NVDA", weight: 0.4 } },
  kpis: { max_drawdown: { value: -0.25, loss_dollars: -250 } }, metrics: { today: { cagr: 0.05 }, after: { cagr: 0.2, peak_date: "2021-11-22", trough_date: "2021-12-08" } },
  tipping_point: { ticker: "NVDA", curve: [
    { weight: 0, verdict: "Compatible", max_drawdown: -0.05, end_value: 1050 },
    { weight: 0.2, verdict: "Compatible", max_drawdown: -0.149, end_value: 1100, loss_dollars: -149 },
    { weight: 0.4, verdict: "Incompatible", max_drawdown: -0.25, end_value: 1300 }],
    paths: { weights: [0, 0.2, 0.4], dates: D, values: [
      [1000, 1010, 1000, 990, 980, 1000, 1020, 1030, 1050],
      [1000, 1050, 1000, 960, 910, 990, 1040, 1070, 1100],
      [1000, 1100, 1000, 900, 860, 980, 1150, 1200, 1300]] } },
  breaches: [{ peak_date: "2021-11-22", trough_date: "2021-12-08", recovery_date: "2021-12-24", depth: -0.25, peak_value: 1120, trough_value: 840, loss_dollars: -250 }],
  events: [{ event_id: "e1", date: "2021-12-01", title: "Tariff day", family: "tariffs", lat: 1, lon: 2, place: "Ottawa", today: { trough: -0.01 }, after: { trough: -0.04 } },
    { event_id: "e2", date: "2021-12-30", title: "Later tariffs", family: "tariffs", lat: 1, lon: 2, after: { trough: -0.01 } },
    { event_id: "w1", date: "2021-12-02", title: "War", family: "war_oil", lat: 1, lon: 2, after: { trough: -0.09 } }],
  backdrops: [{ label: "Rates rising", start: "2021-11-01", end: "2022-06-01" }],
});
const r = syn(), m = raceModel(r);
assert.equal(m.kind, "paths");
assert.equal(m.askedIndex, 2);
assert.deepEqual([m.weight, m.weightIndex, m.asked], [0.4, 2, true]);
assert.deepEqual(m.dates.filter((d) => !D.includes(d)), ["2021-11-22", "2021-12-08"]);   // the server's own high and trough
assert.equal(m.after[m.dates.indexOf("2021-12-08")], 840);
assert.equal(m.today[m.dates.indexOf("2021-12-08")], null);                   // no invented value for today's line on that day
assert.deepEqual([m.ends.today, m.ends.after, m.ends.afterText], [1050, 1300, "$1,300"]);
assert.equal(m.breaches.length, 1);
const b0 = m.breaches[0];
assert.deepEqual([b0.result, b0.peakDate, b0.troughDate, b0.depth, b0.dollars, b0.label, b0.labelKind, b0.eventId],
  [true, "2021-11-22", "2021-12-08", -0.25, -280, "Tariff day", "event", "e1"]);   // R35: the path’s own dollars, 1,120 to 840
assert.deepEqual([b0.depthText, b0.dollarsText, b0.moneyText, m.worst.moneyText], [`${M}25.0\u00a0%`, `${M}$280`, `${M}$280 ($1,120 \u2192 $840)`, `${M}$280 ($1,120 \u2192 $840)`]);
assert.deepEqual([m.worst.depth, m.worst.dollars, m.worst.breach, m.worst.past, m.worst.value], [-0.25, -280, 0, true, 840]);
assert.deepEqual([m.worst.cls, m.worst.word, m.worst.tone, m.whatIf, m.labels.whatIf], ["broke", "Broke your floor", "outside", false, null]);
// a backdrop is a band over its own dates (never a fall's name: correlation, never cause)
assert.deepEqual(m.bands.map((x) => [x.label, x.start, x.end, x.t0 === m.domain.t0]), [["Rates rising", "2021-11-01", "2022-06-01", true]]);
assert.equal(m.bands[0].text, "Rates rising, Nov\u00a02021 \u2013 Jun\u00a02022");
assert.deepEqual(m.shocks.map((s) => [s.id, s.worst]), [["e1", true], ["e2", false]]);   // the asked family only; the worst precedent
assert.deepEqual([m.labels.after, m.labels.today, m.labels.shocks, m.labels.ribbon, m.labels.rule, m.labels.below],
  ["With 40\u00a0% NVIDIA", "Today\u2019s mix", "Tariff war shocks", "Your floor follows every new high", "Your floor (15\u00a0% from a high)", "Below your floor"]);
// R35: the capacity line comes from result.capacity only (lane fin-backend): its fill under the line, its one label
const rc = syn(); rc.capacity = { amount: 1000, capacity: 90, line: 900,   // lane fin-backend's shape (result_extras.capacity)
  today: { line: 900, sessions_below: 0, episodes: [] },
  after: { line: 900, sessions_below: 3, first_below: "2021-12-01", last_below: "2021-12-10", episodes: [{ first_date: "2021-12-01", last_date: "2021-12-10", sessions: 3 }] } };
const mc = raceModel(rc);
assert.deepEqual([mc.capacity.line, mc.capacity.label, mc.capacity.note, mc.capacity.under.length > 0, mc.domain.y0 <= 900],
  [900, "What you can afford to lose: $90", "below it for 3 sessions in Dec\u00a02021", true, true]);
rc.capacity.after.episodes = [{ first_date: "2022-04-22", last_date: "2022-06-01" }, { first_date: "2022-08-01", last_date: "2023-01-19" }];
assert.equal(raceModel({ ...rc }).capacity.note, "below it for 3 sessions, Apr\u00a02022 to Jan\u00a02023");   // the first start to the last end
assert.equal(raceModel({ ...rc, capacity: { capacity: 90, line: 900, after: { line: 900, sessions_below: 0, episodes: [] } } }).capacity.note, "never below it");
assert.equal(raceModel({ ...rc, breaches: [{ ...rc.breaches[0], fall_dollars: -279 }] }).worst.dollars, -279);   // fin-backend's own fall_dollars first
assert.equal(raceModel(rc, 1).capacity.note, null);          // the count is the asked size’s: another size keeps the line, never the count
assert.equal(m.capacity, null);                              // no key (an old run, a fresh clone): no capacity line at all
assert.ok(m.domain.y0 <= 840 && m.domain.y1 >= 1300 && m.domain.t0 === timeOf(D[0]));

// another size (ruling R20): the line is tipping_point.paths.values[i] only (no server days); it reads only as its worst fall
// against your floor (curve[i]'s), never with dollars or an end value; the floor check rounds like the server (−14.9 % at 20 %
// never hatches, and touched it: within 1 point)
const m1 = raceModel(r, 1);
assert.deepEqual([m1.weight, m1.weightIndex, m1.asked, m1.whatIf, m1.ends.after, m1.ends.afterText], [0.2, 1, false, true, null, null]);
assert.deepEqual([m1.labels.after, m1.labels.whatIf], ["At 20\u00a0%: what-if", "A replay at another size, not a recommendation."]);
assert.equal(m1.after[m1.dates.indexOf("2021-12-08")], null);
assert.deepEqual(m1.breaches, []);
assert.deepEqual([m1.worst.depth, m1.worst.dollars, m1.worst.dollarsText, m1.worst.cls, m1.worst.word], [-0.149, null, null, "touched", "Touched your floor"]);
assert.deepEqual([raceModel(r, 0).worst.cls, raceModel(r, 0).worst.tone], ["held", "neutral"]);   // −5 % against −15 %: held above
assert.equal(raceModel(r, 0).worst.dollars, null);                           // curve[0] has no loss_dollars: percent only
assert.equal(raceModel(r, 99).weightIndex, 2);                               // clamped to the curve
assert.equal(m.at(1).weightIndex, 1);
assert.equal(raceModel(r, 1).dates, m.dates);                                // one date axis for every size: the dial never re-flows it
// the ticker already held today (20 %): today's line is the curve's 20 % size, its end value curve[1]'s, never the 0 % mix
const hd = syn(); hd.baseline.portfolio = { AAA: 0.8, NVDA: 0.2 };
const hm = raceModel(hd);
assert.deepEqual([hm.today[0], hm.today[m.dates.indexOf("2021-12-10")], hm.ends.today, hm.todayPriced], [1000, 910, 1100, true]);
// today's weight is no size of the curve (10 %): today's line is the Result's own series, unpriced (no dollar readout, no end value)
const hs = syn(); hs.baseline.portfolio = { AAA: 0.9, NVDA: 0.1 };
hs.series = { dates: D, today: [100, 103, 100, 95, 92, 99, 104, 107, 110], after: [100, 110, 100, 90, 86, 98, 115, 120, 130] };
const hsm = raceModel(hs);
assert.deepEqual([hsm.today[1], hsm.ends.today, hsm.todayPriced, hsm.kind], [1030, null, false, "paths"]);
// an asked size the curve does not carry (30 %): the asked view is the server's own daily series of that mix; the dial's
// sizes stay the curve's paths, never matched to the server's breaches
const oc = syn(); oc.portfolio = { AAA: 0.7, NVDA: 0.3 }; oc.scenario.change.weight = 0.3;
oc.series = { dates: D, today: [100, 101, 100, 99, 98, 100, 102, 103, 105], after: [100, 105, 100, 92, 84, 99, 110, 114, 120] };
const om = raceModel(oc);
assert.deepEqual([om.kind, om.exact, om.weightIndex, om.labels.after, om.ends.after, om.ends.today], ["series", false, null, "With 30\u00a0% NVIDIA", null, 1050]);
assert.equal(raceModel({ ...oc, end_values: { today: 1050, after: 1200 } }).ends.after, 1200);   // the asked mix's own end value
assert.deepEqual([om.at(2).kind, om.at(2).asked, om.at(2).breaches.every((x) => !x.result), om.at(2).dates.length], ["paths", false, true, D.length]);

// no move (Mateo's oil question): one line from series.today in dollars, weekly, keeping the server's days; no ends in dollars
const nm = syn();
Object.assign(nm, { question_type: "shock", tipping_point: null, portfolio: { AAA: 1 }, baseline: null, scenario: { families: ["war_oil"], change: null },
  kpis: { max_drawdown: { value: -0.12, loss_dollars: -120 } }, breaches: [],
  events: [{ event_id: "w1", date: "2021-11-23", title: "Strikes", family: "war_oil", lat: 1, lon: 2, today: { trough: -0.05 } },
    { event_id: "w2", date: "2021-12-02", title: "Out of the window", family: "war_oil", lat: 1, lon: 2, today: { trough: -0.09 } }],
  metrics: { today: { cagr: 0.05, peak_date: "2021-11-15", trough_date: "2021-11-24" }, after: null },
  series: { dates: ["2021-11-12", "2021-11-15", "2021-11-16", "2021-11-17", "2021-11-18", "2021-11-19", "2021-11-22", "2021-11-23", "2021-11-24", "2021-11-25", "2021-11-26", "2021-11-29"],
    today: [100, 101, 99, 98, 97, 96, 95, 92, 88.88, 90, 94, 99], after: null } });
const n = raceModel(nm);
assert.equal(n.kind, "series");
assert.equal(n.after, null);
assert.deepEqual(n.dates, ["2021-11-12", "2021-11-15", "2021-11-19", "2021-11-24", "2021-11-26", "2021-11-29"]);   // every 5th + the server's days + the last
assert.equal(n.today[3], 888.8);
assert.deepEqual([n.ends.today, n.ends.after, n.weightIndex, n.at], [null, null, null, null]);   // no end_values: no dollar end
assert.deepEqual(raceModel({ ...nm, end_values: { today: 990, after: null } }).ends, { today: 990, after: null, todayText: "$990", afterText: null });
assert.deepEqual([n.worst.depth, n.worst.dollars, n.worst.troughDate, n.worst.past], [-0.12, null, "2021-11-24", false]);   // no path high/trough: % only
assert.deepEqual(n.shocks.map((s) => [s.id, s.worst]), [["w1", true]]);          // inside the drawn window only
assert.equal(n.labels.today, "Your mix");                                     // R18: second person, no persona name in the chart
assert.equal(raceModel({ ...nm, amount: null }), null);
assert.equal(raceModel(null), null);
// a move without paths still draws (series.after), never inventing sizes
const np = syn(); np.tipping_point = null;
np.series = { dates: D, today: [100, 101, 100, 99, 98, 100, 102, 103, 105], after: [100, 110, 100, 90, 86, 98, 115, 120, 130] };
const pm = raceModel(np);
assert.deepEqual([pm.kind, pm.weights, pm.after.length === pm.today.length, pm.labels.after], ["series", null, true, "With 40 % NVIDIA"]);
// a monthly window (lane U8): "YYYY-MM" dates, unnumbered breaches, the worst figure only from the caller's Result keys
const wm = raceModelFromSeries({ dates: ["1973-01", "1973-02", "1973-03", "1973-04", "1973-05"], today: [100, 95, 90, 96, 101],
  after: [100, 80, 70, 85, 102], amount: 600000, floor: -0.15, worst: { date: "1973-03", depth: -0.3011, dollars: -180660, label: "Oil embargo" } });
assert.equal(wm.kind, "window");
assert.deepEqual(wm.breaches.map((x) => [x.peak, x.trough, x.recover, x.depth]), [[0, 2, 4, null]]);
assert.deepEqual([wm.worst.k, wm.worst.depthText, wm.worst.dollarsText, wm.worst.label, wm.worst.breach, wm.worst.moneyText], [2, `${M}30.1\u00a0%`, `${M}$180,660`, "Oil embargo", 0, `${M}$180,660`]);
assert.equal(raceModelFromSeries({ dates: ["1973-01"], today: [1] }), null);

// the committed FAKE Result: every figure on the chart is one of its keys
const fake = JSON.parse(fs.readFileSync(new URL("../web/fake_result.json", import.meta.url), "utf8"));
const fm = raceModel(fake), keys = new Set(fake.breaches.map((x) => Math.round(x.trough_value) - Math.round(x.peak_value)));   // the path’s own
assert.equal(fm.kind, "paths");
assert.deepEqual([fm.ends.today, fm.ends.after], [fake.tipping_point.curve[0].end_value, fake.tipping_point.curve[fm.weightIndex].end_value]);
for (const x of [...fm.breaches, fm.worst]) if (x.dollars !== null) assert.ok(keys.has(x.dollars), x.dollars);

// the committed real Results (tests/fixtures/web, ruling R17): Robert's two breaches named by the asked shock and the 2022
// backdrop, his end values, the 8 / 9 % flip; Mateo's one line; the Canadian SPY size curve
const { load } = await import("./web_fixtures.mjs");
const R = load("robert"), rm = raceModel(R);
assert.deepEqual(rm.breaches.map((x) => [x.label, x.labelKind, x.depthText, x.dollarsText]), [
  [null, null, `${M}34.5\u00a0%`, `${M}$215,224`],
  ["\u201cLiberation Day\u201d reciprocal tariffs", "event", `${M}16.9\u00a0%`, `${M}$249,413`]]);
assert.deepEqual([rm.ends.todayText, rm.ends.afterText, rm.amountText, rm.labels.after], ["$911,676", "$1,847,077", "$600,000", "With 40\u00a0% NVIDIA"]);
// R35: every fall’s dollars are the path’s own, its high to its trough (never the percent times the amount)
assert.deepEqual([rm.worst.moneyText, ...rm.breaches.map((x) => x.moneyText)], [`${M}$215,224 ($623,398 \u2192 $408,174)`, `${M}$215,224 ($623,398 \u2192 $408,174)`, `${M}$249,413 ($1,473,670 \u2192 $1,224,257)`]);
assert.deepEqual([rm.worst.depthText, rm.worst.dollarsText, rm.worst.troughDate, rm.worst.past, rm.worst.word], [`${M}34.5\u00a0%`, `${M}$215,224`, "2022-10-14", true, "Broke your floor"]);
assert.deepEqual(rm.bands.map((x) => x.text), ["Bank of Canada raising rates, Mar\u00a02022 \u2013 Jul\u00a02023"]);
assert.equal(rm.shocks.find((x) => x.worst).id, "liberation_day_2025");
const r8 = raceModel(R, 8), r9 = raceModel(R, 9);   // the dial's flip, named as the dial names it (R20)
assert.deepEqual([r8.breaches.length, r8.worst.depthText, r8.worst.cls, r8.worst.dollars, r8.worst.moneyText, r8.ends.after, r8.labels.after], [0, `${M}15.0 %`, "touched", null, null, null, "At 8 %: what-if"]);
assert.deepEqual([r9.breaches.length, r9.worst.depthText, r9.worst.cls, r9.worst.word], [1, `${M}15.6\u00a0%`, "broke", "Broke your floor"]);
assert.equal(raceModel(R, 0).worst.cls, "held");
const mm = raceModel(load("mateo"));
assert.deepEqual([mm.kind, mm.after, mm.breaches.length, mm.worst.depthText, mm.worst.dollarsText, mm.labels.today], ["series", null, 0, `${M}11.4\u00a0%`, null, "Your mix"]);
assert.deepEqual([mm.ends.today, mm.ends.todayText, mm.ends.after], [431156, "$431,156", null]);   // the one line ends on dollars: end_values (lane b3)
assert.deepEqual([rm.ends.today, rm.ends.after], [R.tipping_point.curve[0].end_value, R.tipping_point.curve[40].end_value]);   // a curve's own come first
const cm = raceModel(load("canadian"));
assert.deepEqual([cm.kind, cm.ticker, cm.weightIndex, cm.labels.after, cm.ends.afterText], ["paths", "SPY", 20, "With 20\u00a0% SPY", "$403,823"]);

// optional shape checks on the real saved runs (ruling R17: they skip when absent and pin no value): at every size every printed
// dollar is one of the Result's own keys, every breach the server measured is drawn, and no stretch is hatched unless
// the server's own worst fall at that size is past the floor
const real = (n) => ["/tmp/epi_runs_v1", "/tmp/epi_video/runs"].map((d) => `${d}/${n}.json`).find((p) => fs.existsSync(p));
for (const id of ["robert", "mateo", "amira", "canadian"]) {
  const f = real(id);
  if (!f) continue;
  const R = JSON.parse(fs.readFileSync(f, "utf8")), m0 = raceModel(R), curve = (R.tipping_point && R.tipping_point.curve) || [];
  assert.ok(m0 && ["paths", "series"].includes(m0.kind), id);
  const drop = (x) => (x && Number.isFinite(x.peak_value) && Number.isFinite(x.trough_value) ? Math.round(x.trough_value) - Math.round(x.peak_value) : null);
  const keys = new Set([...(R.breaches || []).map(drop), drop(R.kpis && R.kpis.max_drawdown),
    ...curve.flatMap((c) => [c.end_value, c.loss_dollars]), ...(R.end_values ? [R.end_values.today, R.end_values.after] : [])].filter(Number.isFinite));
  for (const x of R.breaches || []) assert.ok(m0.breaches.some((y) => y.result && y.troughDate === x.trough_date), `${id} ${x.trough_date}`);
  for (const y of m0.breaches) assert.ok(y.labelKind === null || y.labelKind === "event", `${id}: a fall is named only by a shock on record`);
  for (let i = 0; i < (m0.weights ? m0.weights.length : 1); i++) {
    const mi = m0.weights ? raceModel(R, i) : m0;
    for (const x of [...mi.breaches, mi.worst].filter(Boolean)) if (x.dollars !== null) assert.ok(keys.has(x.dollars), `${id} ${i} ${x.dollars}`);
    for (const e of [mi.ends.today, mi.ends.after]) if (e !== null) assert.ok(keys.has(e), `${id} ${i} ${e}`);
    if (mi.breaches.length) assert.ok(mi.worst && pastFloor(mi.worst.depth, mi.floor), `${id} ${i}`);
    if (m0.weights && mi.worst && !mi.asked) assert.equal(mi.worst.depth, curve[i].max_drawdown);
    if (mi.whatIf) assert.ok(mi.ends.after === null && (!mi.worst || mi.worst.dollars === null), `${id} ${i}: R20, no dollars at another size`);
  }
  if (m0.shocks.length) assert.equal(m0.shocks.filter((x) => x.worst).length, 1);
}
console.log("web_u3_test: all passed");
