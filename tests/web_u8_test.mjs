// Lane U8 (#deep, "Not just 2022"): the pure model web/lib/deep.js under node, plus static guards on the section's words.
// Run: node tests/web_u8_test.mjs (tests/test_web_lib.py runs every tests/web_*_test.mjs).
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
const require = createRequire(import.meta.url);
const PF = require("../web/lib.js");
const D = await import("../web/lib/deep.js");
const { load } = await import("./web_fixtures.mjs");
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
let n = 0;
const t = (name, fn) => { fn(); n += 1; };

t("depthOf reads both shapes and never a side that was not replayed", () => {
  assert.equal(D.depthOf(-0.1507), -0.1507);
  assert.equal(D.depthOf({ depth: -0.2, replayable: true }), -0.2);
  assert.equal(D.depthOf({ depth: -0.2, replayable: false }), null);
  assert.equal(D.depthOf({ replayable: true, uncovered: [] }), null);
  assert.equal(D.depthOf(null), null);
  assert.equal(D.depthOf(NaN), null);
});

t("classOf: the Result's class wins, then beyond_floor with the one-point band, then the rounded comparison", () => {
  const k = (row, side, d) => (D.classOf(row, side, d, -0.15, PF) || {}).key;
  assert.equal(k({ today: -0.1507 }, "today", -0.1507), "touched");            // past the floor by 0.1 pt
  assert.equal(k({ today: -0.1600 }, "today", -0.16), "touched");              // exactly one point: still touched
  assert.equal(k({ today: -0.1606 }, "today", -0.1606), "broke");              // 1.1 pt (tenths, ROUND_HALF_UP)
  assert.equal(k({ today: -0.1459 }, "today", -0.1459), "held");
  assert.equal(k({ today: -0.15004 }, "today", -0.15004), "held");             // -15.0 % after round_pp: not past (pitfall 5)
  assert.equal(k({ today: { depth: -0.17, beyond_floor: false } }, "today", -0.17), "held");   // the server's own call wins
  assert.equal(k({ today: { depth: -0.152, beyond_floor: true } }, "today", -0.152), "touched");
  assert.equal(k({ today: { depth: -0.30, beyond_floor: true } }, "today", -0.30), "broke");
  assert.equal(k({ today: { depth: -0.30, class: "touched" } }, "today", -0.30), "touched");   // a B3 class is taken as is
  assert.equal(k({ classes: { after: "held" }, after: -0.3 }, "after", -0.3), "held");
  assert.equal(D.classOf({}, "today", null, -0.15, PF), null);
  assert.deepEqual(Object.keys(D.CLASS), ["broke", "touched", "held"]);
});

t("yearsOf writes the span the way the page reads it", () => {
  assert.equal(D.yearsOf("1973-01", "1974-12"), "1973–74");
  assert.equal(D.yearsOf("1987-07", "1987-12"), "1987");
  assert.equal(D.yearsOf("2007-06", "2009-06"), "2007–09");
  assert.equal(D.yearsOf("1999-03", "2001-02"), "1999–2001");
  assert.equal(D.yearsOf("", "1990"), "");
});

t("scaleOf covers the deepest value and the floor, to the next ten points", () => {
  assert.equal(D.scaleOf([-0.812, -0.15, null], -0.15), 0.9);
  assert.equal(D.scaleOf([-0.05], -0.25), 0.3);
  assert.equal(D.scaleOf([-0.3], -0.15), 0.3);
  assert.equal(D.scaleOf([], null), 1);
});

t("worseOf: the Result's flag wins; else more than a point deeper", () => {
  assert.equal(D.worseOf({}, -0.1614, -0.1618, PF), false);                   // 0.04 pt is not worse
  assert.equal(D.worseOf({}, -0.152, -0.296, PF), true);
  assert.equal(D.worseOf({}, -0.0815, -0.0583, PF), false);
  assert.equal(D.worseOf({ move_worse: true }, -0.10, -0.05, PF), true);
  assert.equal(D.worseOf({}, null, -0.2, PF), null);
});

const ROBERT = { pilot: "robert", question_type: "change", amount: 600000, status: "ok",
  profile: { name: "Robert", age: 59 }, limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000 },
  portfolio: { "XIU.TO": 0.27, "XBB.TO": 0.21, NVDA: 0.4 }, baseline: { portfolio: { "XIU.TO": 0.45, "XBB.TO": 0.35 } }, tipping_point: { ticker: "NVDA" } };
const ep = (id, start, end, today, after, extra = {}) => ({ episode_id: id, title: id.replace(/_/g, " "), start, end, place: "Somewhere",
  source_url: "https://example.org/" + id, today, after, ...extra });
const side = (depth, beyond) => ({ replayable: true, uncovered: [], depth, beyond_floor: beyond, peak: "1974-02", trough: "1974-09", loss_dollars: 91337 });
const withDeep = (dh, more = {}) => ({ ...ROBERT, deep_history: dh, ...more });

t("deepModel: no deep_history, no rows or no PF hide the section", () => {
  assert.equal(D.deepModel(ROBERT, PF).show, false);
  assert.equal(D.deepModel(withDeep({ episodes: [] }), PF).show, false);
  assert.equal(D.deepModel(withDeep({ episodes: [ep("a", "1973-01", "1974-12", -0.1, -0.2)] }), null).show, false);
});

t("deepModel (tools.deep shape): every number is the Result's own, formatted by PF.fmt", () => {
  const dh = { episodes: [ep("oil_embargo", "1973-01", "1974-12", side(-0.1522, true), side(-0.2957, true)),
    ep("bond_rout", "1994-01", "1994-12", side(-0.0815, false), side(-0.0583, false)),
    ep("dotcom", "2000-01", "2002-12", side(-0.1128, false), side(-0.5044, true), { proxy_alone: -0.8118 })],
    robust_claims: ["With the move it broke the floor in the 1970s and 2000s."], source: "Proxy replay (assumption)" };
  const m = D.deepModel(withDeep(dh), PF);
  assert.equal(m.show, true); assert.equal(m.state, "ok"); assert.equal(m.n, 3);
  assert.deepEqual(m.span, { from: "1973", to: "2002" });
  assert.equal(m.who, "Robert"); assert.equal(m.amountText, "$600,000"); assert.equal(m.floor.text, PF.fmt.share(-0.15));
  assert.equal(m.move.name, "NVIDIA"); assert.equal(m.move.weightText, PF.fmt.share(0.4));
  assert.deepEqual(m.rows.map((x) => x.today.text), [-0.1522, -0.0815, -0.1128].map((v) => PF.fmt.pct(v)));
  assert.deepEqual(m.rows.map((x) => x.after.text), [-0.2957, -0.0583, -0.5044].map((v) => PF.fmt.pct(v)));
  assert.deepEqual(m.rows.map((x) => [x.today.cls.key, x.after.cls.key]), [["touched", "broke"], ["held", "held"], ["held", "broke"]]);
  assert.deepEqual(m.rows.map((x) => x.worse), [true, false, true]);
  assert.equal(m.rows[2].alone.text, PF.fmt.pct(-0.8118)); assert.equal(m.rows[0].alone, null);
  assert.equal(m.rows[0].today.dollars, 91337); assert.equal(m.rows[0].years, "1973–74");
  assert.equal(m.scale, 0.9);
  assert.ok(Math.abs(m.rows[2].g.a - 0.5044 / 0.9) < 1e-12 && Math.abs(m.floor.f - 0.15 / 0.9) < 1e-12);
  assert.equal(m.rows[1].g.zone, null);                                         // nothing past the floor: no hatch
  assert.ok(Math.abs(m.rows[0].g.zone - 0.2957 / 0.9) < 1e-12);                 // the hatch runs to the deepest bar past it
  assert.deepEqual(m.claims, ["With the move it broke the floor in the 1970s and 2000s."]);
  assert.deepEqual(m.cols, { after: true, alone: true, worse: true });
  assert.equal(m.source, "Proxy replay (assumption)");
});

t("deepModel (fixture shape): bare numbers, NaN family, proxies with strength; no claim without robust_claims", () => {
  const dh = { episodes: [{ id: "volcker", title: "The Volcker shock", start: "1979-09", end: "1982-07", family: null,
    source_url: "javascript:alert(1)", today: -0.1541, after: -0.1448, proxy_alone: -0.2139 }] };
  const dw = { proxies: [{ ticker: "NVDA", proxy: "CHIPS", label: "US chip and electronics industry", strength: "weak" }, { ticker: "GLD", label: "Gold" }] };
  const m = D.deepModel(withDeep(dh, { deep_windows: dw }), PF);
  assert.equal(m.rows[0].url, null);                                            // only http(s) sources become links
  assert.equal(m.rows[0].today.cls.key, "touched"); assert.equal(m.rows[0].after.cls.key, "held");
  assert.equal(m.rows[0].worse, false);
  assert.deepEqual(m.standIn, { ticker: "NVDA", label: "US chip and electronics industry", strength: "weak", note: null });
  assert.equal(m.proxies.length, 2); assert.equal(m.proxies[1].strength, null);
  assert.deepEqual(m.claims, []);
});

t("a crisis of the question's own family is marked; no family, no mark", () => {
  const r = { ...withDeep({ episodes: [ep("oil", "1973-01", "1974-12", -0.2, -0.3, { family: "war_oil" }), ep("crash", "1987-07", "1987-12", -0.1, -0.2, { family: null })] }),
    scenario: { families: ["war_oil"] } };
  const m = D.deepModel(r, PF);
  assert.deepEqual(m.rows.map((x) => x.asked), [true, false]); assert.equal(m.askedLabel, PF.view(r).shockFamily);
  assert.equal(D.deepModel({ ...r, scenario: { families: ["tariffs"] } }, PF).askedLabel, null);
});

t("deepModel without a move: one bar, no 'with the move' column, no stand-in alone, no comparison", () => {
  const r = { ...ROBERT, question_type: "shock", portfolio: { "XIU.TO": 0.6 }, baseline: null, tipping_point: null,
    deep_history: { episodes: [ep("gfc", "2007-06", "2009-06", side(-0.2627, true), null, { proxy_alone: -0.4 })] } };
  const m = D.deepModel(r, PF);
  assert.equal(m.move, null); assert.equal(m.rows[0].after, null); assert.equal(m.rows[0].alone, null); assert.equal(m.rows[0].worse, null);
  assert.deepEqual(m.cols, { after: false, alone: false, worse: false });
  assert.equal(m.rows[0].today.cls.key, "broke");
});

t("deepModel: a mix no stand-in covers says can't say and names the line (Amira's crypto)", () => {
  const no = { replayable: false, uncovered: ["BTC-USD"], depth: null };
  const m = D.deepModel(withDeep({ episodes: [ep("a", "1973-01", "1974-12", no, null), ep("b", "1987-07", "1987-12", no, null)] }), PF);
  assert.equal(m.state, "cant_say"); assert.deepEqual(m.missing.tickers, ["BTC-USD"]);
  assert.ok(m.rows.every((x) => x.today === null));
  const w = D.deepModel(withDeep({ episodes: [ep("a", "1973-01", "1974-12", -0.1, -0.2)] }, { deep_windows: { status: "cant_say", reason: "Bitcoin has no price history before Nov 2021." } }), PF);
  assert.equal(w.missing.reason, "Bitcoin has no price history before Nov 2021.");
});

t("validationOf reads deep_validation first, else the tools.deep proxy check; gentleOf needs both numbers", () => {
  const dv = { today_real: -0.106, today_proxy: -0.087, after_real: -0.345, after_proxy: -0.159, gap_pp: 18.6, method_notes: ["Month-end FX."], window: { start: "2021-11", end: "2025-12" } };
  assert.deepEqual(D.validationOf({ deep_validation: dv }, {}), { today: { real: -0.106, proxy: -0.087, gap: null, within: null },
    after: { real: -0.345, proxy: -0.159, gap: null, within: null }, window: { start: "2021-11", end: "2025-12" }, weak: null, notes: "Month-end FX." });
  const proxy = { today: { drawdown_real: -0.0936, drawdown_proxy: -0.0871, window: { start: "2021-12", end: "2025-12" }, strength: "strong" },
    after: { drawdown_real: -0.319, drawdown_proxy: -0.159, strength: "weak", direction: "gentler" } };
  const v = D.validationOf({}, { proxy });
  assert.deepEqual(v.after, { real: -0.319, proxy: -0.159, gap: null, within: null }); assert.equal(v.weak, "gentler"); assert.deepEqual(v.window, { start: "2021-12", end: "2025-12" });
  assert.equal(D.validationOf({}, {}), null);
  assert.equal(D.gentleOf({}, {}), null);
  assert.equal(D.gentleOf({ deep_validation: { gentle_case: { company: -0.602 } } }, {}), null);
  assert.deepEqual(D.gentleOf({ deep_validation: { gentle_case: { company: -0.602, industry: -0.27, year: 2022 } } }, {}),
    { company: -0.602, industry: -0.27, gentler: null, label: null, window: null, year: "2022" });
});

t("leadOf reads B3's counts only: both sides with a move, today alone without one, null without counts", () => {
  const c = { n: 11, today_broke: 0, today_touched: 3, today_replayable: 11, after_broke: 4, after_touched: 4, after_replayable: 11 };
  const none = { past: 0, lo: null, hi: null };                                      // no robust rows: nothing counted as just past
  assert.deepEqual(D.leadOf({ counts: c }), { after: { broke: 4, touched: 4, of: 11, all: 11, ...none }, today: { broke: 0, touched: 3, of: 11, all: 11, ...none } });
  assert.deepEqual(D.leadOf({ counts: { ...c, after_broke: null, after_touched: null, after_replayable: null } }).after, null);
  assert.equal(D.leadOf({ counts: { n: 11, today_broke: 0, today_replayable: 0 } }), null);       // nothing replayed: no lead
  assert.equal(D.leadOf({}), null);
});

t("G6: the deep source never says 'not recorded'; a real date when the Result has one, else the run's as_of, labelled", () => {
  const r = load("robert"), m = D.deepModel(r, PF);
  assert.ok(!/not recorded/i.test(m.source || "")); assert.ok(m.source.length > 20);
  assert.equal(m.provenance, `The panel as this run used it, run as of ${PF.fmt.date(r.deep_history.as_of || r.as_of)}.`);
  assert.equal(D.provenanceOf(r, { ...r.deep_history, panel_built: "2026-11-14T23:28:13Z" }, PF), `Panel built on ${PF.fmt.date("2026-11-14")}.`);
  assert.equal(D.provenanceOf(r, { ...r.deep_history, retrieved_at: "2026-11-14T22:01:00Z", panel_built: "2026-11-14" }, PF), `Sources retrieved on ${PF.fmt.date("2026-11-14")}.`);
  assert.equal(D.provenanceOf(r, { ...r.deep_history, retrieved_at: "not recorded" }, PF).startsWith("The panel as this run used it"), true);
  assert.equal(D.sourceText("Proxy replay. Data retrieved: not recorded. This already happened."), "Proxy replay. This already happened.");
});

t("one rule for broke (R39): a touched row past the floor reads as 'went just past your rule', with B3's own margins", () => {
  const dh = { counts: { n: 11, today_broke: 0, today_touched: 3, today_replayable: 11 },
    episodes: [{ id: "a", today_class: "touched" }, { id: "b", today_class: "touched" }, { id: "c", today_class: "touched" }, { id: "d", today_class: "held" }],
    robust_claims: { rows: [{ id: "a", today: { margin_pp: 0.2 } }, { id: "b", today: { margin_pp: 2.0 } }, { id: "c", today: { margin_pp: -5.2 } }, { id: "d", today: { margin_pp: 1.0 } }] } };
  assert.deepEqual(D.leadOf(dh).today, { broke: 0, touched: 3, of: 11, all: 11, past: 2, lo: 0.2, hi: 2.0 });   // c stopped short, d held
  const m = { show: true, state: "ok", move: null, floor: { v: -0.15, text: PF.fmt.share(-0.15) }, lead: D.leadOf(dh), missing: { tickers: [] } };
  const v = D.closedView(m, null);
  assert.equal(v.figs[0].n, 2);
  assert.equal(v.figs[0].caption, "earlier crises broke your 15\u00a0% rule; 2 more went just past it (by 0.2 to 2.0 points): too close to call with monthly similar indexes."
    .replace("earlier crises broke your 15\u00a0% rule; 2 more went just past it", "went just past your 15\u00a0% rule"));
  assert.equal(v.answer, "2 of the 11 earlier crises went just past your 15\u00a0% rule (by 0.2 to 2.0 points): too close to call with monthly similar indexes.");
  const src = readFileSync(join(ROOT, "web/sections/deep.js"), "utf8") + readFileSync(join(ROOT, "web/lib/deep.js"), "utf8");
  assert.ok(!/\blower bound\b/i.test(src));                                          // R36: never "a lower bound"
});

t("claimsOf takes a string, strings or {text} rows, and nothing else", () => {
  assert.deepEqual(D.claimsOf({ robust_claims: "One." }), ["One."]);
  assert.deepEqual(D.claimsOf({ robust_claims: ["One.", { text: "Two." }, 3, null, " "] }), ["One.", "Two."]);
  assert.deepEqual(D.claimsOf({}), []);
});

t("the section's words: no advice words, no glyph markers, no innerHTML, no middle-dot strings, no typed numbers", () => {
  const src = readFileSync(join(ROOT, "web/sections/deep.js"), "utf8") + readFileSync(join(ROOT, "web/lib/deep.js"), "utf8");
  const lits = [...src.matchAll(/(["'`])((?:\\.|(?!\1).)*)\1/g)].map((x) => x[2]).filter((s) => s.includes(" "));
  const bad = /\b(buy|sell|hold|you should|we recommend|recommended|safe|you can|allowed|fits)\b/i;
  assert.deepEqual(lits.filter((s) => bad.test(s)), []);
  assert.deepEqual(lits.filter((s) => /\b(will|next shock|is likely|chance of)\b/i.test(s)), []);   // past tense, never a forecast or odds
  assert.deepEqual(lits.filter((s) => s.includes(" · ") || s.trimEnd().endsWith("→")), []);
  assert.ok(!/[●◐○]/.test(src)); assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML/.test(src));
  for (const must of ["This already happened; it is not a forecast.", "Fictional illustration, not a recommendation.", "It never changes the verdict."])
    assert.ok(src.includes(must), must);                                                 // the copy rules the section owes (COMMON_UI, R5)
  assert.deepEqual(lits.filter((s) => /\d+(\.\d+)?\s?%|\$\d/.test(s)), []);     // no percent or dollar typed into a sentence
  const css = readFileSync(join(ROOT, "web/css/deep.css"), "utf8");
  const caps = [...css.matchAll(/([^{}]+)\{[^{}]*text-transform\s*:\s*uppercase/g)].map((x) => x[1].trim());
  assert.ok(caps.every((s) => /^\.(display|lamp-word)$/.test(s)), caps.join());     // the page's rule: capitals on .display only
  assert.ok(!/cubic-bezier\(/.test(css) && !/transition\s*:\s*all\b/.test(css) && !/\bease-in\b(?!-out)/.test(css));
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*var\(--(?:magenta|series-after)\)[^{}]*)\}/g)) assert.ok(/move|after/.test(m[1]), m[1]);
});

t("B3's shapes: row classes and details, robust directions, the claim object, gentle_case, gap_pp by side", () => {
  const row = (id, today, after, extra = {}) => ({ id, title: id, start: "1979-09", end: "1982-07", place: "Washington", source_url: "https://example.org/" + id,
    source_title: "A source", today, after, proxy_alone: -0.2, alone_trough: "1980-03", today_class: "touched", after_class: "broke", move_worse: true,
    today_detail: { replayable: true, peak: "1979-09", trough: "1980-03", loss_dollars: 96866, recovery_months: 5 },
    after_detail: { replayable: true, peak: "1979-09", trough: "1980-03", loss_dollars: 97093, recovery_months: 6 }, ...extra });
  const dh = { episodes: [row("volcker_1979", -0.1614, -0.1618), row("bond_rout_1994", -0.0815, -0.0583, { move_worse: false }), row("taper_2013", -0.0445, -0.0155)],
    moved: { ticker: "NVDA", weight: 0.4, proxy: "CHIPS", label: "the US chip industry" },
    robust_claims: { sentence: "By proxy, in the 3 earlier crises: it fell no further than today's mix in the rate shock (1994).",
      claims: [{ id: "no_further", episodes: ["bond_rout_1994"] }], test: "Each statement held in every run.",
      rows: [{ id: "volcker_1979", direction: "further" }, { id: "bond_rout_1994", direction: "no_further" }, { id: "taper_2013", direction: null }] },
    gentle_case: { ticker: "NVDA", label: "the US chip industry", window: { start: "2021-11", end: "2025-12" }, real: -0.6016, stand_in: -0.2699, gentler: true } };
  const dv = { window: { start: "2021-11", end: "2025-12" }, gap_pp: { today: 1.9, after: 18.6 }, within_2pp: { today: true, after: false },
    today_real: -0.1061, today_real_window: -0.1061, today_proxy: -0.0871, after_real: -0.3452, after_proxy: -0.159,
    method_notes: ["Monthly month-end returns in CAD.", "Gold: monthly averages."],
    canada: { currency: "CAD", splice: { to: "1976-12", source: "Statistics Canada 10-10-0125-01" }, splice_check: { months: 477, start: "1977-01", end: "2016-09", corr: 0.9863 } } };
  const m = D.deepModel(withDeep(dh, { deep_validation: dv }), PF);
  assert.deepEqual(m.rows.map((x) => [x.today.cls.key, x.after.cls.key]), [["touched", "broke"], ["touched", "broke"], ["touched", "broke"]]);
  assert.deepEqual(m.rows.map((x) => x.worse), [true, false, "close"]);            // the robust direction wins over move_worse
  assert.deepEqual([m.rows[0].today.dollars, m.rows[0].after.months, m.rows[0].today.trough, m.rows[0].alone.trough], [96866, 6, "1980-03", "1980-03"]);
  assert.equal(m.rows[0].sourceTitle, "A source");
  assert.deepEqual(m.claims, [D.typo(dh.robust_claims.sentence)]); assert.deepEqual(m.claimTest, { test: "Each statement held in every run.", none: null });
  assert.ok(m.claims[0].includes("today\u2019s mix"));                              // R18: the Result's words, typographic apostrophes
  assert.equal(m.standIn.label, "the US chip industry");
  assert.deepEqual(m.validation.today, { real: -0.1061, proxy: -0.0871, gap: 1.9, within: true });
  assert.deepEqual(m.validation.after, { real: -0.3452, proxy: -0.159, gap: 18.6, within: false });
  assert.deepEqual(m.gentle, { company: -0.6016, industry: -0.2699, gentler: true, label: "the US chip industry", window: { start: "2021-11", end: "2025-12" }, year: null });
  assert.equal(m.methods.notes.length, 2); assert.equal(m.methods.canada.check.months, 477);
  const none = D.deepModel(withDeep({ ...dh, robust_claims: { sentence: "By proxy, no direction held in every sensitivity run.", claims: [], rows: [] } }), PF);
  assert.deepEqual(none.claims, []); assert.equal(none.claimTest.none, "By proxy, no direction held in every sensitivity run.");
  assert.deepEqual(none.rows.map((x) => x.worse), [true, false, true]);            // no robust rows: the Result's own move_worse
});

t("one voice (R18): your amount, typographic apostrophes; can't say names the line and its share", () => {
  const dh = { episodes: [ep("a", "1973-01", "1974-12", -0.1, -0.2)] };
  assert.equal(D.deepModel(withDeep(dh), PF).on, "your $600,000");                          // ruling R18: second person, never the name
  assert.equal(D.deepModel({ ...withDeep(dh), profile: { name: "Too Canadian?" }, amount: 250000 }, PF).on, "your $250,000");
  assert.equal(D.typo("Today's mix held in 8; the \"gentle\" case, 'quoted'"), "Today\u2019s mix held in 8; the \u201cgentle\u201d case, \u2018quoted\u2019");
  const no = { replayable: false, uncovered: ["BTC-USD"] };
  const m = D.deepModel({ ...withDeep({ episodes: [ep("a", "1973-01", "1974-12", null, null, { today_detail: no })] }), portfolio: { "BTC-USD": 0.15, "XIU.TO": 0.85 },
    question_type: "shock", baseline: null, tipping_point: null }, PF);
  assert.equal(m.state, "cant_say"); assert.deepEqual(m.missing.items, [{ ticker: "BTC-USD", share: PF.fmt.share(0.15) }]);
});

t("stripesOf (P1, flag off by default): one class per start month, runs merged, decade ticks, never a share", () => {
  const starts = ["1979-11", "1979-12", "1980-01", "1980-02"];
  const r = { ...ROBERT, deep_windows: { floor: -0.15, horizon_months: 48, stripes: { starts, today: [-0.10, -0.152, -0.20, -0.21], after: [-0.3, -0.3, -0.31, -0.1] },
    today: { breach_share: 0.5 }, after: { breach_share: 0.75 } } };
  const sx = D.stripesOf(r, PF);
  assert.equal(sx.n, 4); assert.equal(sx.years, 4); assert.deepEqual(sx.decades, [{ i: 2, label: "1980" }]);
  assert.deepEqual(sx.rows[0].cls, ["held", "touched", "broke", "broke"]);
  assert.deepEqual(sx.rows[0].runs, [{ cls: "held", i: 0, n: 1 }, { cls: "touched", i: 1, n: 1 }, { cls: "broke", i: 2, n: 2 }]);
  assert.ok(!JSON.stringify(sx).includes("share"));                                    // R5: no share of stretches reaches the page
  assert.equal(D.stripesOf({ ...r, deep_windows: { status: "cant_say", reason: "x" } }, PF), null);
  assert.equal(D.stripesOf({ ...r, deep_windows: { ...r.deep_windows, stripes: { starts, today: [-0.1] } } }, PF), null);
});

t("kindsOf on the committed fixtures (R17): the deep record only, one row per kind the earlier crises contain", () => {
  const r = load("robert"), k = D.kindsOf(r, PF);
  assert.deepEqual(k.rows.map((x) => x.id), ["war_oil", "rates", "crash"]);           // no tariff war or chip slump among them
  assert.equal(k.move, true); assert.equal(k.floorText, PF.fmt.share(r.limits.floor));
  assert.ok(k.rows.every((x) => !("recent" in x) && x.earlier.kind === "assumption"));   // the 2021-26 shocks are the stage's
  const war = k.rows.find((x) => x.id === "war_oil"), mine = r.deep_history.episodes.filter((e) => e.family === "war_oil");
  assert.equal(war.earlier.n, mine.length);
  assert.equal(war.earlier.today.v, Math.min(...mine.map((e) => e.today)));          // the worst of the group: a Result number
  assert.equal(war.earlier.after.cls, mine.reduce((a, b) => (b.after < a.after ? b : a)).after_class);   // with B3's own class
  const crash = k.rows.find((x) => x.id === "crash");
  assert.equal(crash.earlier.n, r.deep_history.episodes.filter((e) => !["war_oil", "rates", "chips", "tariffs"].includes(e.family)).length);
  for (const x of k.rows) for (const c of [x.earlier.today, x.earlier.after]) if (c) assert.ok(["Broke your floor", "Touched your floor", "Held above your floor"].includes(c.word), c.word);
  const mateo = D.kindsOf(load("mateo"), PF);
  assert.equal(mateo.move, false); assert.ok(mateo.rows.every((x) => x.earlier.after === null));
  const amira = D.kindsOf(load("amira"), PF);
  assert.ok(amira.rows.every((x) => x.earlier.cant === true));                       // her stand-ins are missing: can't say
  assert.equal(D.kindsOf({ limits: {} }, PF), null);
});

t("#deep never reads the 2021-26 turbulence (pre-freeze judge, defect 1): changing it changes nothing here", () => {
  const a = D.kindsOf(load("robert"), PF), r = load("robert");
  for (const f of Object.values(r.turbulence)) { f.worst_today = -0.9; f.worst_after = -0.9; f.today_class = "broke"; f.after_class = "broke"; }
  assert.deepEqual(D.kindsOf(r, PF), a);
  const v = D.closedView(D.deepModel(r, PF), D.kindsOf(r, PF));
  assert.ok(!JSON.stringify(v).includes("Recent episodes")); assert.ok(v.legend.includes("similar indexes") && v.legend.includes("probably milder than the real thing"));   // plain words (cold-user test, 14:25)
  const e = a.rows.find((x) => x.id === "war_oil").earlier;
  assert.equal(e.today.by, "result");                                                 // the earlier crises carry B3's class
});

t("Simple #deep (R22 + the fintech-UX pass): the question, one answer sentence from B3's counts, the lower-bound line; at most three numbers", () => {
  for (const id of ["robert", "mateo", "amira", "canadian"]) {
    const r = load(id), m = D.deepModel(r, PF), k = D.kindsOf(r, PF), v = D.closedView(m, k), nums = D.numbersIn(v);
    assert.ok(nums.length <= 6, `${id}: ${nums.join(", ")}`);                    // Simple: question, one answer, the milder line (R22: ~6)
    const simple = D.simpleText(v).join(" ");
    assert.ok(simple.includes("This already happened; it is not a forecast.") && simple.includes("probably milder than the real thing"), id);   // release gate (d)
    assert.equal(D.simpleText(v).length, 2 + (v.answer ? 1 : 0) + (v.readout ? 1 : 0), id);   // question, answer, the big readout, the line
    if (v.readout) { assert.equal(v.marks.length, r.deep_history.episodes.length, id); assert.ok(v.marks.every((x) => /^\d{4}$/.test(x.year)), id); }
    assert.equal(v.question, "Is it just 2022?"); assert.ok(v.honesty.includes("This already happened; it is not a forecast."));
    assert.ok(v.kinds.every((x) => x.lines.every((l) => [l.today, l.after].every((c) => !c || !/\d/.test(c.word)))), id);   // words only
    if (m.lead && m.lead.after && m.move) assert.equal(v.figs[0].n, r.deep_history.counts.after_broke);   // B3's count, as it is
  }
  const r = load("robert"), v = D.closedView(D.deepModel(r, PF), D.kindsOf(r, PF));
  assert.equal(v.no, r.deep_history.counts.after_broke > 0);
  const rule = `your ${PF.fmt.share(-r.limits.floor)} rule`;
  if (r.deep_history.counts.after_broke > 0)
    assert.equal(v.answer, `No: with the move, ${r.deep_history.counts.after_broke} of ${r.deep_history.counts.after_replayable} earlier crises broke ${rule}.`);
  const amira = D.closedView(D.deepModel(load("amira"), PF), D.kindsOf(load("amira"), PF));
  assert.deepEqual(amira.figs, []); assert.ok(/^Can\u2019t say/.test(amira.cant));
});

/* R17: saved runs under /tmp only for an optional shape check that skips when they are absent (no value pinned on them) */
let real = 0;
for (const id of ["robert", "mateo", "amira", "canadian"]) {
  const path = `/tmp/epi_runs_v1/${id}.json`;
  if (!existsSync(path)) continue;
  const r = JSON.parse(readFileSync(path, "utf8"));
  if (!r.deep_history) continue;
  const m = D.deepModel(r, PF);
  assert.equal(m.show, true, id);
  for (const [x, e] of m.rows.map((x, i) => [x, r.deep_history.episodes[i]])) {
    for (const side of ["today", "after"]) {
      const d = D.depthOf(e[side]);
      if (x[side]) { assert.equal(x[side].text, PF.fmt.pct(d), `${id} ${x.id} ${side}`); if (e[`${side}_class`]) assert.equal(x[side].cls.key, e[`${side}_class`]); }
    }
    assert.ok([x.today, x.after, x.alone].every((s) => !s || !/NaN|undefined/.test(s.text)), id);
  }
  real += 1;
}
console.log(`web_u8_test: ${n} groups passed${real ? `, ${real} saved runs shape-checked` : ""}`);
