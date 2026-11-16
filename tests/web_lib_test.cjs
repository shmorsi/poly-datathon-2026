const assert = require("node:assert/strict"), PF = require("../web/lib.js");
const plan = { pilot: "robert", amount: 600000, capacity: 90000, in_2022: "held", goal: "preservation", horizon: 4, esg: false, crypto: false,
  holdings: { "XIU.TO": 45, "XBB.TO": 35, GLD: 10, "ZST.TO": 10 }, q: "What if I put 40 % in NVIDIA?", hl: "New US tariffs on Canada" };
const body = PF.requestBody(plan, null, false);
assert.deepEqual(body.portfolio, { "XIU.TO": 0.45, "XBB.TO": 0.35, GLD: 0.1, "ZST.TO": 0.1 });
assert.equal(body.question, "What if I put 40 % in NVIDIA? Headline: New US tariffs on Canada");
assert.deepEqual(body.profile, { goal: "preservation", horizon_years: 4, risk: "moderate", esg: false, crypto: false, capacity: 90000, reaction_2022: "held" });
assert.equal("headline" in body, false);
const d = { verdict_sentence: "V", sections: { data: [0], why: [1], limits: [2], would_change: [3] },
  sentences: ["a", "b", "c", "d"].map((t) => ({ text: t, kind: "fact", refs: [] })) };
assert.deepEqual(PF.debriefSections(d).map((s) => s.title), ["What data?", "Why this verdict?", "What limits?", "What would change the answer?"]);
assert.deepEqual(PF.blockOrder({ scenario: { check_order: ["single_stock", "max_drawdown"] } }), ["risk", "floor", "diversification", "turbulence", "values", "size"]);
assert.equal(PF.tokensOf({ inputTokens: 1200, outputTokens: 300 }), 1500);
assert.deepEqual(["fact", "assumption", "limit", "scenario", "fiction"].map((k) => PF.markerOf(k).icon), ["m-fact", "m-assumption", "m-assumption", "m-fiction", "m-fiction"]);
assert.equal(PF.markerOf("fact").word, "fact");
assert.deepEqual([PF.markerOf(undefined).icon, PF.markerOf("constructor").word], ["i-pending", "unlabelled"]);   // W1a review minor

// C1: a question without a portfolio change comes from the pipeline with series.after, baseline and tipping_point null.
// The page draws the evaluated mix as the one path: after is a copy of today, never null.
const fs = require("node:fs");
const noChange = (r) => ({ ...r, question_type: "shock", baseline: null, tipping_point: null, scenario: { change: null, check_order: [] },
  series: { dates: ["2021-11-12", "2022-10-14", "2026-11-12"], today: [100, 89.4, 150.6], after: null, aligned: null } });
const given = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2], "utf8")) : noChange({});   // argv[2]: a Result written by the real pipeline
const drawn = PF.withPaths(given);
assert.ok(Array.isArray(drawn.series.after) && drawn.series.after.length === drawn.series.today.length);
assert.deepEqual(drawn.series.after, drawn.series.today);
assert.notEqual(drawn.series.after, drawn.series.today);   // a copy: nothing that edits one path can move the other
assert.equal(drawn.baseline, given.baseline);               // baseline and tipping_point stay null: the page hides those lines
const withMove = { series: { dates: ["a", "b"], today: [100, 90], after: [100, 70] } };
assert.deepEqual(PF.withPaths(withMove).series.after, [100, 70]);   // a real "after" is never replaced
assert.equal(PF.withPaths(null), null);
// nothing changes, so the move's hit is the mix's own hit: events and shock families get their "after" from "today"
const hit = PF.withPaths({ series: { today: [1, 2], after: null }, events: [{ today: { trough: -0.05 }, after: { trough: null } }, { today: { trough: null } }],
  turbulence: { tariffs: { worst_today: -0.06, worst_after: null }, rates: { worst_today: null, worst_after: null } } });
assert.equal(hit.events[0].after.trough, -0.05);
assert.equal(hit.turbulence.tariffs.worst_after, -0.06);
assert.equal(hit.turbulence.rates.worst_after, null);
const kept = PF.withPaths({ series: { today: [1, 2], after: [1, 1] }, events: [{ today: { trough: -0.05 }, after: { trough: null } }], turbulence: {} });
assert.equal(kept.events[0].after.trough, null);   // a question with a move keeps its own numbers, null or not
assert.doesNotThrow(() => PF.withPaths({}));

// the browser's tenth-of-a-point rounding is the server's (governance.round_pp: ties away from zero, pitfall 5)
assert.equal(PF.tenths(-0.1505), -151);
assert.equal(PF.tenths(-0.15), -150);
assert.equal(PF.tenths(-0.15004), -150);
assert.equal(PF.tenths(0.08), 80);
assert.equal(PF.tenths(0.0805), 81);

// I5: the drawer's ticker select. Changing XIU.TO to SPY and then to QQQ sends QQQ (the second change reads the key the first wrote).
let drawer = { "XIU.TO": 45, "XBB.TO": 35, GLD: 10, "ZST.TO": 10 };
drawer = PF.renameLine(drawer, "XIU.TO", "SPY");
drawer = PF.renameLine(drawer, "SPY", "QQQ");
assert.deepEqual(Object.keys(drawer), ["QQQ", "XBB.TO", "GLD", "ZST.TO"]);   // the row keeps its place
assert.deepEqual(PF.requestBody({ ...plan, holdings: drawer }, null, false).portfolio, { QQQ: 0.45, "XBB.TO": 0.35, GLD: 0.1, "ZST.TO": 0.1 });
assert.equal(PF.renameLine(drawer, "QQQ", "GLD"), null);                     // a line already holds that ticker: no silent merge
assert.equal(PF.renameLine(drawer, "QQQ", "QQQ"), drawer);                   // no change
assert.equal(PF.renameLine(drawer, "NOPE", "AGG"), drawer);                  // the row is gone: nothing to rename

// I3, I4: what the user reads when a run fails. A plain sentence from the server (or ours) is shown; an exception's own text never is.
const plainErr = Object.assign(new Error("Keep the question under 2,000 characters."), { plain: true });
const droppedErr = Object.assign(new Error("The connection dropped before the answer arrived. Run the check again."), { dropped: true });
assert.equal(PF.failureLine(plainErr), "Keep the question under 2,000 characters.");
assert.equal(PF.failureLine(droppedErr), "The connection dropped before the answer arrived. Run the check again.");
assert.equal(PF.failureLine(new TypeError("Cannot read properties of null (reading 'x')")), PF.UNSHOWN);
assert.equal(PF.failureLine(new Error("r.series.after is not iterable")), PF.UNSHOWN);
assert.equal(PF.failureLine(undefined), PF.UNSHOWN);
assert.equal(PF.failureLine({ status: "error", message: "Something went wrong in the compare step. The page keeps the last result." }), "Something went wrong in the compare step. The page keeps the last result.");
assert.equal(PF.failureLine({ status: "error" }), "The check could not run. Run it again.");
assert.ok(!/undefined|null|TypeError/.test(PF.UNSHOWN));

// ---- W-S1: the formatter, the move, the investor card and PF.view (the page's one map from a §12 Result) ----
const NB = "\u00a0", M = "\u2212";
assert.equal(PF.fmt.money(-207146.4), M + "$207,146"); assert.equal(PF.fmt.money(-0), "$0"); assert.equal(PF.fmt.money(-0.4), "$0");
assert.equal(PF.fmt.money(1200000), "$1,200,000"); assert.equal(PF.fmt.money(null), ""); assert.equal(PF.fmt.money("x"), "");
assert.equal(PF.fmt.pct(-0.345), M + "34.5" + NB + "%"); assert.equal(PF.fmt.pct(0.0004), "0.0" + NB + "%"); assert.equal(PF.fmt.pct(-0.0004), "0.0" + NB + "%");
assert.equal(PF.fmt.pct(null), ""); assert.equal(PF.fmt.pct(undefined), ""); assert.equal(PF.fmt.pct(-0.15, 0), M + "15" + NB + "%");
assert.equal(PF.fmt.pct(-0.1505), M + "15.1" + NB + "%");                  // governance.round_pp: ties away from zero (pitfall 5)
assert.equal(PF.fmt.share(0.4), "40" + NB + "%"); assert.equal(PF.fmt.share(0.424), "42.4" + NB + "%"); assert.equal(PF.fmt.share(0.075), "7.5" + NB + "%");
assert.equal(PF.fmt.date("2022-10-14"), "14" + NB + "Oct" + NB + "2022"); assert.equal(PF.fmt.month("2022-10-14"), "Oct" + NB + "2022");
assert.equal(PF.fmt.date("nope"), ""); assert.equal(PF.fmt.date(null), "");
assert.equal(PF.fmt.days(486.6), "487 days"); assert.equal(PF.fmt.days(1), "1 day"); assert.equal(PF.fmt.days(null), "");
assert.equal(PF.fmt.years(4), "4 years"); assert.equal(PF.fmt.years(1), "1 year");
assert.equal(PF.tidyReason("The 34.5 % drop; your horizon allows 486.6 days."), "The 34.5" + NB + "% drop; your horizon allows 487 days.");

const FAKE = JSON.parse(fs.readFileSync(require("node:path").join(__dirname, "..", "web", "fake_result.json"), "utf8"));
const INV = FAKE._investors, rob = JSON.parse(JSON.stringify(FAKE));
delete rob._investors;
const strings = (o, out = []) => { if (typeof o === "string") out.push(o); else if (o && typeof o === "object") for (const v of Object.values(o)) strings(v, out); return out; };
const clean = (v, who) => { for (const s of strings(v)) assert.ok(!/undefined|NaN|\bnull\b|\[object/.test(s), `${who}: "${s}"`); };
const text = (segs) => (segs || []).map((s) => s[0]).join("");

assert.deepEqual(PF.moveOf(rob), { ticker: "NVDA", name: "NVIDIA", weight: 0.4 });
assert.equal(PF.moveOf(INV.mateo), null);
assert.equal(PF.moveOf(INV.canadian).ticker, "SPY");

// Robert (the default run): a move, today vs after, the lamp, the dollars, the story lines, the shocks for the hero
const vr = PF.view(rob);
clean(vr, "robert");
assert.equal(vr.ok, true); assert.equal(vr.who.name, "Robert"); assert.equal(vr.who.his, "his");
assert.deepEqual([vr.verdict.word, vr.verdict.tone, vr.verdict.icon], ["Outside your limits", "outside", "i-out"]);
assert.deepEqual([vr.today.word, vr.today.tone], ["Inside your limits", "inside"]);
assert.equal(vr.move.name, "NVIDIA"); assert.equal(vr.move.weightText, "40" + NB + "%");
assert.equal(vr.fall.after.dollarsText, M + "$207,000"); assert.equal(vr.fall.after.ddText, M + "34.5" + NB + "%");
assert.equal(vr.fall.today.dollarsText, M + "$63,600"); assert.equal(vr.floor.dollarsText, M + "$90,000"); assert.equal(vr.floor.text, M + "15" + NB + "%");
assert.equal(vr.amountText, "$600,000"); assert.equal(vr.capacityText, "$90,000");
assert.equal(vr.paths.dates.length, rob.series.dates.length); assert.equal(vr.paths.after.length, rob.series.dates.length);
assert.equal(vr.paths.after[vr.paths.trough], vr.fall.after.dd);   // series / running high − 1 (ledger §14): the line meets the quoted fall at its date
assert.equal(vr.paths.floor, -0.15);                               // a fraction: the page draws the floor where the rule measures it
assert.equal(text(vr.lines.hero), "Robert’s move, replayed on real history: outside his limits.");
assert.match(text(vr.lines.thesis), /^With 40 % in NVIDIA, Robert’s money would have grown 25\.2 % a year, against 8\.7 %, and fallen below his floor\.$/);   // a counterfactual: he never held the move (Minor 12)
assert.match(text(vr.lines.dollar), /would have been −\$207,000/);
assert.ok(vr.lines.dollar.some((s) => s[1] === "num"));
assert.equal(vr.shocks.n, rob.events.length); assert.equal(vr.shocks.span, "Feb" + NB + "2022 to Sep" + NB + "2026");
assert.deepEqual(vr.shocks.events.map((e) => e.date), [...vr.shocks.events.map((e) => e.date)].sort());
assert.equal(vr.shocks.events.find((e) => e.id === "jackson_hole_2022").trough, -0.141);   // the move's trough on the default run
assert.deepEqual(vr.rows.slice(0, 3).map((x) => [x.rule, x.word]), [["max_drawdown", "Outside"], ["single_stock", "Outside"], ["sector", "Outside"]]);
assert.equal(vr.rows.find((x) => x.rule === "scenario_stress").word, "Caution");   // the soft shock check: "Caution", never "Fail" (board res. 9)
assert.equal(vr.rows[0].tier, "Hard limit"); assert.equal(vr.rows.find((x) => x.rule === "risk_concentration").word, "Caution");
assert.equal(vr.breaches.length, 2); assert.equal(vr.breaches[1].dollarsText, M + "$101,400");
assert.equal(vr.saved, false);
assert.equal(PF.view({ ...rob, mode: "demo_replay" }).saved, true);

// Mateo: a question without a move (one path, "fell", never "would have been"); Amira: the amber lamp; Too Canadian?: green
const vm = PF.view(INV.mateo), va = PF.view(INV.amira), vc = PF.view(INV.canadian);
clean(vm, "mateo"); clean(va, "amira"); clean(vc, "canadian");
assert.equal(vm.move, null); assert.equal(vm.today, null); assert.equal(vm.paths.after, null); assert.equal(vm.fall.after, null);
assert.equal(vm.verdict.word, "Outside your limits"); assert.equal(vm.rows[0].rule, "esg_direct");
assert.ok(!/would have been/.test(text(vm.lines.dollar)) && /fell/.test(text(vm.lines.dollar)));
assert.deepEqual([va.verdict.word, va.verdict.tone, va.verdict.icon], ["Inside, with caveats", "caveat", "i-warn"]);
assert.equal(va.who.his, "her"); assert.equal(va.rows[0].word, "Caution");
assert.deepEqual([vc.verdict.word, vc.verdict.tone], ["Inside your limits", "inside"]); assert.equal(vc.move.ticker, "SPY");
assert.equal(vc.who.age, null);

// a via-less exposed list (saved and static runs, ledger §30): grouped by channel, an ETF named only when `via` exists
const ex = PF.view(INV.canadian).shocks.events.find((e) => e.exposure.length);
assert.ok(ex.exposure.every((g) => g.channel && Array.isArray(g.tickers) && g.via === null));
const exVia = PF.view(rob).shocks.events.find((e) => e.id === "ukraine_2022");
assert.equal(exVia.exposure[0].via, "Energy names inside (ENB, CNQ)");
clean(PF.view(INV.canadian).shocks, "via-less");

// a stripped Result (an older saved run, the public cut): every missing key hides its line, nothing prints undefined or NaN
const bare = { status: "ok", series: { dates: rob.series.dates, today: rob.series.today } };
const vb = PF.view(bare);
clean(vb, "bare");
assert.equal(vb.ok, true); assert.equal(vb.verdict, null); assert.equal(vb.move, null); assert.equal(vb.floor, null);
assert.equal(vb.paths, null);                                 // no amount: no dollars, so no fall view (never a constant)
assert.equal(vb.lines.hero, null); assert.equal(vb.lines.thesis, null); assert.equal(vb.lines.dollar, null);
assert.deepEqual(vb.rows, []); assert.equal(vb.shocks, null);
const vn = PF.view({ status: "ok", verdict: null, amount: 1000, series: { dates: ["2022-01-03", "2022-01-04"], today: [100, 90], after: null } });
assert.equal(vn.verdict.word, "No limits set"); assert.equal(vn.verdict.tone, "none");
for (const r of [null, undefined, 7, "x", {}, { status: "error", message: "The price data is missing." }]) assert.doesNotThrow(() => clean(PF.view(r), "odd"));
assert.equal(PF.view({ status: "blocked", message: "M" }).stop, true); assert.equal(PF.view(rob).stop, false);
const noFig = JSON.parse(JSON.stringify(rob)); delete noFig.figures;  // the public demo has no figures key at all
assert.equal(PF.view(noFig).paths.after.length, rob.series.dates.length);

// the investor card: the rows mock 03 shows, from the Result (or an investor from /api/pilots), never from a constant
assert.deepEqual(PF.youRows(rob).map((r) => [r.label, r.value]), [["Objective", "Preserve capital, with some growth"], ["When you need the money", "In 4 years"],
  ["The most you could lose", "$90,000 of $600,000"], ["Your floor", M + "15" + NB + "%"], ["Limits", "One company up to 10" + NB + "%; no crypto"], ["Values", "No values screen"]]);
assert.equal(PF.youRows(rob)[3].note, "Set by the loss you could absorb. Your reaction to the 2022 fall alone pointed to " + M + "25" + NB + "%, a deeper fall than this floor.");   // release gate (a): past tense, no permission verb
assert.equal(PF.youRows(INV.amira).find((r) => r.label === "Limits").value, "One company up to 20" + NB + "%; crypto up to 10" + NB + "%");
assert.equal(PF.youRows(INV.mateo).find((r) => r.label === "Values").value, "Screen out companies with major controversies");
assert.deepEqual(PF.youRows({ amount: 600000 }), []);
const persona = { name: "Robert", age: 59, amount: 600000, profile: { goal: "preservation", horizon_years: 4, risk: "moderate", esg: false, crypto: false, capacity: 90000, reaction_2022: "held" } };
assert.deepEqual(PF.youRows(persona).map((r) => r.label), ["Objective", "When you need the money", "The most you could lose", "Values"]);  // no run yet: no floor, no limits
for (const r of PF.youRows(INV.canadian)) clean(r, "canadian rows");

// the five questions: one typed profile, one plain sentence per wrong field
assert.deepEqual(PF.profileFromAnswers({ goal: "balance", horizon: "10", loss: "25", unit: "%", in_2022: "bought more", esg: true, crypto: false }, 250000),
  { profile: { goal: "balance", horizon_years: 10, risk: "high", esg: true, crypto: false, capacity: 62500, reaction_2022: "bought" } });
assert.equal(PF.profileFromAnswers({ goal: "balance", horizon: "0", loss: "1", unit: "$", in_2022: "held" }, 1000).error, "Choose a number of years between 1 and 40.");
assert.equal(PF.profileFromAnswers({ goal: "balance", horizon: "5", loss: "-3", unit: "$", in_2022: "held" }, 1000).error, "Enter the loss as a positive amount.");

// the plan the run sends, from an investor or a Result (one shape for PF.requestBody), and the static demo's run for a tab
const planR = PF.planFrom(rob);
assert.deepEqual(PF.requestBody(planR, null, false).portfolio, rob.baseline.portfolio);
assert.equal(PF.requestBody(planR, null, false).question, rob.question);
assert.deepEqual(PF.requestBody(PF.planFrom({ ...persona, portfolio: { "XIU.TO": 0.45, "XBB.TO": 0.55 }, question: "Q?" }, "robert"), null, false).profile,
  { goal: "preservation", horizon_years: 4, risk: "moderate", esg: false, crypto: false, capacity: 90000, reaction_2022: "held" });
const idx = [{ key: "a1", pilot: "robert", question: "Q1", as_of: "2026-11-12", file: "runs/a1.json", commit: "0123456789abcdef0123456789abcdef01234567" },
  { key: "b2", pilot: "robert", question: "Q2", as_of: "2026-11-12", file: "runs/b2.json", commit: "c" }, { key: "c3", pilot: "mateo", question: "Q3", file: "runs/c3.json" }];
assert.equal(PF.staticRun(idx, "robert").key, "a1"); assert.equal(PF.staticRun(idx, "mateo").key, "c3"); assert.equal(PF.staticRun(idx, "amira"), null);
assert.equal(PF.staticRun(null, "robert"), null); assert.equal(PF.shortCommit(idx[0].commit), "0123456"); assert.equal(PF.shortCommit(undefined), null);
// the D Task 5 port must preserve (re-review r1): (1) a no-change Result draws one path and never says "with the move";
// (2) one judge: a row's word follows the server's status, never its value; (5) the shock label comes from the Result
const nc = PF.view(PF.withPaths(JSON.parse(JSON.stringify(given))));
clean(nc, "no-change");
assert.equal(nc.move, null); assert.equal(nc.today, null);
if (nc.paths) assert.equal(nc.paths.after, null);
assert.ok(!strings(nc).some((s) => /with the move|would have been/i.test(s)));
const judged = JSON.parse(JSON.stringify(rob));
judged.checks[0].value = -0.01;                                      // a value inside the floor, status still "fail"
assert.equal(PF.view(judged).rows[0].word, "Outside");
judged.checks[0].status = "pass";
assert.equal(PF.view(judged).rows.find((x) => x.rule === "max_drawdown").word, "Inside");
judged.verdict = "Compatible";                                       // the lamp is the server's verdict, whatever the rows say
assert.equal(PF.view(judged).verdict.word, "Inside your limits");
assert.equal(PF.view(rob).shockFamily, "Tariff war"); assert.equal(PF.view(INV.amira).shockFamily, "Chip war");
assert.equal(PF.view({ ...rob, scenario: { ...rob.scenario, families: [] } }).shockFamily, null);
console.log("web_lib_test: W-S1 assertions passed");

// the hero holds at most 35 words (spec §22 density budget, ledger §28): the bar and the hero section of index.html (hidden and
// script-filled slots left out) plus the words the page writes into the slots from the default run
const html = fs.readFileSync(require("node:path").join(__dirname, "..", "web", "index.html"), "utf8");
const heroHtml = html.slice(html.indexOf('<header class="bar"'), html.indexOf('<section class="act thesis"'));
const visible = heroHtml.replace(/<svg[\s\S]*?<\/svg>/g, " ").replace(/<(\w+)[^>]*\b(hidden|data-slot)\b[^>]*>[\s\S]*?<\/\1>/g, " ")
  .replace(/<p class="sr"[\s\S]*?<\/p>/g, " ").replace(/<[^>]+>/g, " ");
const words = (s) => (String(s).match(/[\p{L}\p{N}][\p{L}\p{N}’'.,:%$−-]*/gu) || []).length;
const hc = PF.heroCopy(vr);
assert.equal(hc.button, "Replay Robert’s move");
assert.deepEqual(hc.readout, [`${rob.events.length} shocks on record`, "Feb" + NB + "2022 to Sep" + NB + "2026"]);
const heroWords = words(visible) + words(hc.line) + words(hc.button) + hc.readout.reduce((n, s) => n + words(s), 0);
assert.ok(heroWords <= 35, `the hero holds ${heroWords} words`);
console.log(`web_lib_test: hero ${heroWords} words`);

// the no-WebGL rings sit where web/globe.js draws the shocks: the disc centre is (tilt, lon0), the limb is at radius 1
const c0 = PF.globeProject(26, -18, { tilt: 26, lon0: -18, D: 6 });
assert.ok(Math.abs(c0.x) < 1e-9 && Math.abs(c0.y) < 1e-9 && c0.visible);
const limb = PF.globeProject(26 - 90 + Math.asin(1 / 6) * 180 / Math.PI, -18, { tilt: 26, lon0: -18, D: 6 });   // the horizon point below the centre
assert.ok(Math.abs(Math.hypot(limb.x, limb.y) - 1) < 1e-6);
assert.equal(PF.globeProject(-26, 162, { tilt: 26, lon0: -18 }).visible, false);                           // the far side
console.log("web_lib_test: globe projection passed");

// addendum 3 (ledger §30): facts rows in years or days are words, never percents; an unknown exposure is never "no exposure"
assert.equal(PF.factText({ value: 4, unit: "years" }), "4 years"); assert.equal(PF.factText({ value: 486.6, unit: "days" }), "487 days");
assert.equal(PF.factText({ value: -0.345, unit: "pct" }), M + "34.5" + NB + "%"); assert.equal(PF.factText({ value: -207146, unit: "CAD" }), M + "$207,146");
assert.equal(PF.factText({ value: 1.3, unit: "count" }), "1.3"); assert.equal(PF.factText({ value: 4, unit: "parsecs" }), ""); assert.equal(PF.factText(null), "");
const hz = PF.view({ ...rob, facts: { T1: { label: "Horizon", value: 4, unit: "years", kind: "assumption" }, T2: { label: "x", value: null, unit: "pct" } } });
assert.deepEqual(hz.facts.map((f) => [f.id, f.text, f.marker.icon]), [["T1", "4 years", "m-assumption"]]);
const unknown = JSON.parse(JSON.stringify(rob));
unknown.events[0].exposed = null; unknown.events[1].exposed = []; unknown.events[1].exposed_mode = "direct"; unknown.events[2].exposed = [];
const ue = PF.view(unknown).shocks.events, byId = (id) => ue.find((e) => e.id === id);
assert.equal(byId(unknown.events[0].event_id).exposure, null); assert.equal(byId(unknown.events[0].event_id).exposureNote, "Not known from holdings");
assert.equal(byId(unknown.events[1].event_id).exposureNote, "Not known from holdings"); assert.deepEqual(byId(unknown.events[1].event_id).exposure, []);
assert.equal(byId(unknown.events[2].event_id).exposureNote, null);
console.log("web_lib_test: facts units and unknown exposure passed");

// a rule whose value has no known unit (missing_data counts the funds that could not be looked through) shows its reason
const md = PF.view({ ...rob, checks: [{ rule: "missing_data", tier: "warn", status: "warn", value: 2, limit: 0, reason: "XIU.TO could not be looked through." }] });
assert.equal(md.rows[0].compare, null); assert.equal(md.rows[0].reason, "XIU.TO could not be looked through.");
console.log("web_lib_test: rule units passed");

// W-S1 fix round 1, C1: the limit clause names the floor that decided the check (governance.load_limits keeps the stricter
// of the capacity floor and the 2022 band; ruling R18): capacity -> "the $X you said you could absorb"; band -> the floor itself
{
  const P0 = "With 40" + NB + "% in NVIDIA, this mix fell 34.5" + NB + "% at its worst in this history. The same fall on your $600,000 would have been " + M + "$207,000";
  assert.equal(text(PF.view(rob).lines.dollar), P0 + ", past the $90,000 you said you could absorb.");
  const band = JSON.parse(JSON.stringify(rob));
  Object.assign(band.limits, { floor_source: "band", capacity_dollars: 300000 }); band.profile.capacity = 300000;
  const vb2 = PF.view(band); clean(vb2, "band floor");
  assert.equal(text(vb2.lines.dollar), P0 + ", past your floor of " + M + "15" + NB + "%.");
  assert.ok(!strings(vb2).some((s) => /you said you could absorb/.test(s)));
  assert.equal(vb2.floor.dollarsText, null); assert.equal(vb2.floor.label, M + "15" + NB + "%");
  assert.match(vb2.rows[0].compare, new RegExp("against your limit " + M + "15" + NB + "%$"));
  const edited = JSON.parse(JSON.stringify(rob)); edited.limits.edited = ["floor"];           // an edited floor is the investor's own
  assert.match(text(PF.view(edited).lines.dollar), new RegExp("past your floor of " + M + "15" + NB + "%\\.$"));
  const inside = JSON.parse(JSON.stringify(INV.mateo)); Object.assign(inside.limits, { floor_source: "band" });
  assert.match(text(PF.view(inside).lines.dollar), new RegExp("inside your floor of " + M + "25" + NB + "%\\.$"));
  assert.match(text(PF.view(INV.mateo).lines.dollar), /inside the \$62,500 you said you could absorb\.$/);
}
console.log("web_lib_test: fix round 1 C1 passed");

// W-S1 fix round 1, I1 (ruling R18, §24 res. 9 one value per fact): every dollar shown is a Result key (kpis.*.loss_dollars,
// breaches[].loss_dollars, limits.capacity_dollars), never amount × percent; a missing key hides the dollars; the hatch is
// the Result's below_floor (pitfall 5: the server's round_pp decides a breach), never a raw value < floor
{
  const v = PF.view(rob);
  assert.equal(v.fall.after.dollars, rob.kpis.max_drawdown.loss_dollars);
  assert.equal(v.fall.today.dollars, rob.baseline.kpis.max_drawdown.loss_dollars);
  assert.deepEqual(v.breaches.map((b) => b.dollars), [...rob.breaches].sort((a, b) => a.depth - b.depth).map((b) => b.loss_dollars));
  const sh = JSON.parse(JSON.stringify(rob));
  sh.kpis.max_drawdown.loss_dollars = -123456; sh.baseline.kpis.max_drawdown.loss_dollars = -11111; sh.breaches[1].loss_dollars = -55555;
  const vs = PF.view(sh);
  assert.match(text(vs.lines.dollar), /would have been −\$123,456,/); assert.match(text(vs.lines.note), /\(−\$11,111\)/);
  assert.equal(vs.breaches[1].dollarsText, M + "$55,555"); assert.ok(vs.rows[0].compare.startsWith(M + "$123,456 (" + M + "34.5" + NB + "%)"));
  const odd = JSON.parse(JSON.stringify(rob)); odd.kpis.max_drawdown.value = -0.2;               // dollars of another number: not this fact
  assert.equal(PF.view(odd).fall.after.dollars, null);
  const nod = JSON.parse(JSON.stringify(rob));
  delete nod.kpis.max_drawdown.loss_dollars; delete nod.baseline.kpis.max_drawdown.loss_dollars; nod.breaches.forEach((b) => delete b.loss_dollars);
  const vn2 = PF.view(nod); clean(vn2, "no dollar keys");
  assert.equal(vn2.fall.after.dollars, null); assert.equal(vn2.lines.dollar, null); assert.ok(!text(vn2.lines.note).includes("$"));
  assert.ok(vn2.breaches.every((b) => b.dollars === null)); assert.ok(!vn2.rows[0].compare.split(" against")[0].includes("$"));
  // the chart: drawdown fractions (no dollar path); the drawn trough is the quoted number at the Result's own trough date
  const P = v.paths;
  assert.equal(P.dates[P.trough], rob.metrics.after.trough_date); assert.equal(P.after[P.trough], rob.metrics.after.max_drawdown);
  assert.ok(P.after.every((x) => x === null || (x <= 0 && x >= rob.metrics.after.max_drawdown - 1e-3)));
  assert.equal(P.floor, rob.limits.floor);
  const at = (d) => P.dates.findIndex((x) => x >= d);
  assert.deepEqual(P.hatch, rob.breaches.flatMap((b) => b.below_floor).map(([a, b]) => [at(a), at(b)]).sort((a, b) => a[0] - b[0]));
  const nb = JSON.parse(JSON.stringify(rob)); nb.breaches = [];          // the line still dips under the floor; the Result names no breach
  assert.deepEqual(PF.view(nb).paths.hatch, []);
  for (const pid of ["mateo", "amira", "canadian"]) {                   // the FAKE investors quote their own kpis
    const vi = PF.view(INV[pid]), side = vi.move ? vi.fall.after : vi.fall.today;
    assert.equal(side.dollars, INV[pid].kpis.max_drawdown.loss_dollars, pid);
  }
}
console.log("web_lib_test: fix round 1 I1 passed");

// W-S1 fix round 1, I2: a failed run puts back the last good Result of the same investor, never another's (review I2)
{
  const last = { robert: rob };
  assert.equal(PF.lastGood(last, "robert"), rob); assert.equal(PF.lastGood(last, "mateo"), null);
  assert.equal(PF.lastGood({}, "robert"), null); assert.equal(PF.lastGood(null, "robert"), null);
  assert.equal(PF.lastGood({ robert: "x" }, "robert"), null); assert.equal(PF.lastGood(Object.create({ mateo: rob }), "mateo"), null);
  assert.equal(PF.lastGood({ robert: { ...rob, status: "blocked" } }, "robert"), null);   // a stopped answer is never "the last good"
}
console.log("web_lib_test: fix round 1 I2 passed");

// W-S1 fix round 1, minors: "pp" facts round like round_pp with U+2212 (Minor 7); one format per limit (Minor 9)
{
  assert.equal(PF.factText({ value: -0.0125, unit: "pp" }), M + "1.3" + NB + "pp"); assert.equal(PF.factText({ value: 0.004, unit: "pp" }), "0.4" + NB + "pp");
  const one = PF.view({ ...rob, checks: [{ rule: "scenario_stress", tier: "soft", status: "warn", value: -0.09, limit: -0.15, reason: "R." }] });
  assert.equal(one.rows[0].compare, M + "9.0" + NB + "% against your limit " + M + "15" + NB + "%");   // as the floor's "−15 %"
}
console.log("web_lib_test: fix round 1 minors passed");
