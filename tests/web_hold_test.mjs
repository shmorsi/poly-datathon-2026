// Lane hold: the pure helpers of "what each investor holds" (web/lib/funds.js: the one ticker map; web/lib/hold.js: the hero
// list, the stage strip, the look-through panel). Values are pinned on the committed fixtures (R17: tests/fixtures/web/*.json)
// and on small synthetic Results; the browser never computes more than amount x weight.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { load, NAMES } from "./web_fixtures.mjs";
import * as F from "../web/lib/funds.js";
import * as S from "../web/lib/scenario.js";
import * as H from "../web/lib/hold.js";
import * as U from "../web/lib/u1.js";
import { adviceHits, verdictHits, metaHits } from "../scripts/gate_rules.mjs";

const PF = createRequire(import.meta.url)("../web/lib.js");
let n = 0;
const t = (name, fn) => {
  try { fn(); } catch (e) { e.message = `${name}: ${e.message}`; throw e; }
  n += 1;
};
const NB = " ";

/* ---- web/lib/funds.js: the one map ---- */
t("every ticker of the starter universe and XSP.TO has a public name, a plain label and a kind", () => {
  const universe = ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO", "AAPL", "MSFT", "NVDA",
    "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM", "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG", "TLT", "GLD", "BTC-USD", "ETH-USD", "XSP.TO"];
  for (const tk of universe) {
    const f = F.FUNDS[tk];
    assert.ok(f && f.name && f.label && ["fund", "stock", "crypto"].includes(f.kind), tk);
    assert.equal(F.fundName(tk), f.name);
    assert.equal(F.plainLabel(tk), f.label);
    assert.doesNotMatch(f.name + f.label, /\d+\s?%|\$/, `${tk}: a name, never a number`);
  }
  assert.equal(F.fundName("XIU.TO"), "iShares S&P/TSX 60 Index ETF");
  assert.equal(F.fundName("XBB.TO"), "iShares Core Canadian Universe Bond Index ETF");
  assert.equal(F.fundName("GLD"), "SPDR Gold Shares");
  assert.equal(F.fundName("ZST.TO"), "BMO Ultra Short-Term Bond ETF");
  assert.equal(F.fundName("XSP.TO"), "iShares Core S&P 500 Index ETF (CAD-Hedged)");
  assert.equal(F.plainLabel("XIU.TO"), "Canadian stocks");
  assert.equal(F.plainLabel("ZST.TO"), "Short-term bonds");
  assert.equal(F.kindOf("NVDA"), "stock");
  assert.equal(F.kindOf("GLD"), "fund");
  assert.equal(F.kindOf("BTC-USD"), "crypto");
  assert.equal(F.kindOf("ZZZ"), null);
  assert.equal(F.plainLabel("ZZZ"), "ZZZ");
  assert.equal(F.fundName("ZZZ"), "ZZZ");
  assert.equal(F.plainLabel(undefined), "");
});

t("the universe: the 31 starter tickers, each in the map; XSP.TO and META are words only", () => {
  assert.equal(F.UNIVERSE.length, 31);
  assert.equal(new Set(F.UNIVERSE).size, 31);
  for (const tk of F.UNIVERSE) assert.ok(F.FUNDS[tk], tk);
  assert.ok(!F.UNIVERSE.includes("XSP.TO") && !F.UNIVERSE.includes("META"));
  for (const name of NAMES) {
    const r = load(name);
    for (const tk of [...Object.keys(r.portfolio), ...Object.keys((r.baseline && r.baseline.portfolio) || {})]) assert.ok(F.UNIVERSE.includes(tk), `${name}: ${tk}`);
  }
});

t("one map: scenario.js names a holding from funds.js, and lib.js's move names agree with it", () => {
  for (const tk of Object.keys(F.FUNDS)) assert.equal(S.holdingName(tk), F.plainLabel(tk), tk);
  assert.equal(S.holdingName("XBB.TO"), "Canadian bonds");
  assert.equal(S.holdingName("ZZZ"), "ZZZ");
  /* lib.js is a classic script with its own move names (the move chip): each one is the same words as the map's label */
  for (const tk of ["NVDA", "TSLA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "SHOP.TO", "CNQ.TO", "ENB.TO", "BTC-USD", "ETH-USD"]) {
    const r = { question_type: "change", portfolio: { [tk]: 0.4, "XIU.TO": 0.6 }, baseline: { portfolio: { "XIU.TO": 1 } }, tipping_point: { ticker: tk } };
    assert.equal(PF.moveOf(r).name, F.plainLabel(tk), tk);
  }
  /* the page's map is typed from public names only: no licensed file is read by the page */
  const src = readFileSync(new URL("../web/lib/funds.js", import.meta.url), "utf8");
  assert.doesNotMatch(src, /etf_holdings\.csv['"`]|data\/starter\/|fetch\(|import\(/);
});

t("countries: plain names for the look-through's keys; GLOBAL, CRYPTO and OTHER are not places", () => {
  assert.equal(F.countryName("CAN"), "Canada");
  assert.equal(F.countryName("USA"), "United States");
  assert.equal(F.countryName("GLOBAL"), "No single country (gold)");
  assert.equal(F.countryName("CRYPTO"), "No country (crypto)");
  assert.equal(F.countryName("OTHER"), "Other countries");
  assert.equal(F.countryName("XYZ"), "XYZ");
  for (const k of ["GLOBAL", "CRYPTO", "OTHER"]) assert.ok(F.NOT_A_COUNTRY.has(k), k);
  for (const name of NAMES) {
    const lt = load(name).lookthrough;
    for (const side of ["today", "after"]) for (const code of Object.keys((lt[side] && lt[side].countries) || {})) {
      assert.ok(Object.prototype.hasOwnProperty.call(F.COUNTRIES, code), `${name} ${side}: ${code} has a plain name`);
    }
  }
});

/* ---- web/lib/hold.js ---- */
const strip = (x) => String(x).replace(/ /g, " ");
t("the hero list: today's rows come from baseline.portfolio, largest first, with dollars = amount x weight", () => {
  const r = load("robert"), m = H.holdModel(r, PF);
  assert.equal(m.title, "What Robert holds now");
  assert.equal(m.fiction, "(fictional)");
  assert.equal(m.amountText, "$600,000");
  assert.deepEqual(m.rows.map((x) => x.ticker), ["XIU.TO", "XBB.TO", "GLD", "ZST.TO"]);
  assert.deepEqual(m.rows.map((x) => x.label), ["Canadian stocks", "Canadian bonds", "Gold", "Short-term bonds"]);
  assert.deepEqual(m.rows.map((x) => strip(x.weightText)), ["45 %", "35 %", "10 %", "10 %"]);
  assert.deepEqual(m.rows.map((x) => x.dollarsText), ["$270,000", "$210,000", "$60,000", "$60,000"]);
  for (const x of m.rows) assert.equal(x.weight, r.baseline.portfolio[x.ticker], `${x.ticker}: the Result's own weight`);
  assert.deepEqual(m.rows.map((x) => x.tone), [0, 1, 2, 3]);
  assert.equal(m.rows[0].name, "iShares S&P/TSX 60 Index ETF");
  assert.equal(m.more, null);
  assert.equal(m.moved, true);
  assert.equal(m.move, "NVDA");
  assert.equal(m.noMove, null);
  assert.ok(Math.abs(m.bar.reduce((a, s) => a + s.weight, 0) - 1) < 1e-9, "the bar adds up to the whole");
});

t("the look-through line: the largest share in one place, never gold's GLOBAL", () => {
  const r = load("robert"), L = H.holdModel(r, PF).look;
  assert.equal(L.kind, "country");
  assert.equal(L.code, "CAN");
  assert.equal(L.share, r.lookthrough.today.countries.CAN);
  assert.equal(strip(L.text), "Looking inside the funds: 87.6 % of the money is in Canada.");
  const g = load("robert");
  g.lookthrough.today.countries = { GLOBAL: 0.6, USA: 0.3, CAN: 0.1 };
  assert.equal(strip(H.lookLine(g, PF).text), "Looking inside the funds: 30.0 % of the money is in United States.");
  for (const [name, code] of [["mateo", "CAN"], ["amira", "CAN"], ["canadian", "CAN"]]) assert.equal(H.holdModel(load(name), PF).look.code, code, name);
});

t("mode direct: one honest line, no panel", () => {
  const r = load("robert");
  r.lookthrough.today = { mode: "direct", countries: { CAN: 0.9 }, sectors: {}, coverage: {}, snapshot: {}, gaps: [] };
  const L = H.holdModel(r, PF).look;
  assert.equal(L.kind, "direct");
  assert.equal(L.text, "Fund contents unavailable here; each fund is counted as one holding.");
  assert.deepEqual(H.lookModel(r, PF), { mode: "direct", direct: H.DIRECT_LINE, moved: true });
  const none = load("robert"); delete none.lookthrough;
  assert.equal(H.holdModel(none, PF).look, null);
  assert.equal(H.lookModel(none, PF), null);
});

t("no move in the question (Mateo, Amira): today is the one mix, no strip, said in words", () => {
  for (const name of ["mateo", "amira"]) {
    const r = load(name), m = H.holdModel(r, PF);
    assert.equal(m.moved, false, name);
    assert.equal(m.noMove, "No move in the question", name);
    assert.equal(H.stripModel(r, PF), null, name);
    const lm = H.lookModel(r, PF);
    assert.equal(lm.moved, false);
    assert.equal(lm.noMove, "No move in the question");
    assert.ok(lm.countries.every((c) => c.after === null && c.afterText === null), name);
  }
  assert.equal(H.holdModel(load("mateo"), PF).title, "What Mateo holds now");
  assert.deepEqual(H.holdModel(load("mateo"), PF).rows.map((x) => x.ticker), ["XBB.TO", "XIU.TO", "GLD", "MSFT", "CNQ.TO"]);
  /* the same weights in baseline and portfolio are no move either */
  const same = load("robert"); same.portfolio = { ...same.baseline.portfolio };
  assert.equal(H.mixes(same, PF).after, null);
  assert.equal(H.stripModel(same, PF), null);
});

t("at most five rows: Amira's sixth holding folds into the fifth row, named, its weight and dollars summed", () => {
  const r = load("amira"), m = H.holdModel(r, PF);
  assert.equal(m.rows.length + (m.more ? 1 : 0), 5);
  assert.deepEqual(m.rows.map((x) => x.ticker), ["XIU.TO", "BTC-USD", "NVDA", "QQQ"]);
  assert.deepEqual(m.more.tickers, ["XBB.TO", "SHOP.TO"]);
  assert.equal(m.more.label, "Canadian bonds and Shopify");
  assert.equal(strip(m.more.weightText), "25 %");
  assert.equal(m.more.dollarsText, "$20,000");
  assert.equal(m.bar.length, 6, "the bar keeps every holding");
  assert.ok(m.rows.every((x) => x.ticker !== "NVDA" || x.tone !== "move"), "a holding the question did not move is never magenta");
});

t("the stage strip: today from baseline.portfolio, with the move from portfolio, the move last and magenta", () => {
  const r = load("robert"), st = H.stripModel(r, PF);
  assert.deepEqual(st.today.map((x) => [x.ticker, x.tone]), [["XIU.TO", 0], ["XBB.TO", 1], ["GLD", 2], ["ZST.TO", 3]]);
  assert.deepEqual(st.after.map((x) => [x.ticker, x.tone]), [["XIU.TO", 0], ["XBB.TO", 1], ["GLD", 2], ["ZST.TO", 3], ["NVDA", "move"]]);
  for (const x of st.after) assert.equal(x.weight, r.portfolio[x.ticker]);
  assert.equal(strip(st.move.weightText), "40 %");
  assert.ok(Math.abs(st.after[st.after.length - 1].x1 - 1) < 1e-9);
  assert.equal(strip(st.summary), "Today: Canadian stocks 45 %, Canadian bonds 35 %, Gold 10 %, Short-term bonds 10 %. With the move: Canadian stocks 27 %, Canadian bonds 21 %, Gold 6 %, Short-term bonds 6 %, NVIDIA 40 %.");
  const c = H.stripModel(load("canadian"), PF);
  assert.deepEqual(c.after.map((x) => [x.ticker, x.tone, strip(x.weightText)]), [["XIU.TO", 0, "48 %"], ["XBB.TO", 1, "24 %"], ["ZST.TO", 2, "8 %"], ["SPY", "move", "20 %"]]);
  assert.equal(H.holdModel(load("canadian"), PF).title, "What this portfolio holds now");
  /* a move on a holding already held (Amira's NVIDIA at 20 %): neutral today, magenta with the move, last */
  const a = load("amira"); a.question_type = "change"; a.baseline = { portfolio: { ...a.portfolio } };
  a.portfolio = { NVDA: 0.2, QQQ: 0.1412, "SHOP.TO": 0.0941, "BTC-USD": 0.1412, "XIU.TO": 0.2823, "XBB.TO": 0.1412 }; a.tipping_point = { ticker: "NVDA" };
  const sa = H.stripModel(a, PF);
  assert.notEqual(sa.today.find((x) => x.ticker === "NVDA").tone, "move");
  assert.equal(sa.after[sa.after.length - 1].ticker, "NVDA");
  assert.equal(sa.after[sa.after.length - 1].tone, "move");
});

t("what's inside the funds: top five countries and industries, today vs with the move, the date and coverage", () => {
  const r = load("robert"), lm = H.lookModel(r, PF);
  assert.equal(lm.moved, true);
  assert.deepEqual(lm.countries.map((c) => c.key), ["CAN", "USA", "GLOBAL", "OTHER", "BMU"]);
  const can = lm.countries[0], usa = lm.countries[1];
  assert.equal(can.today, r.lookthrough.today.countries.CAN);
  assert.equal(can.after, r.lookthrough.after.countries.CAN);
  assert.deepEqual([strip(can.todayText), strip(can.afterText), strip(usa.todayText), strip(usa.afterText)], ["87.6 %", "52.6 %", "1.8 %", "41.1 %"]);
  assert.equal(usa.name, "United States");
  assert.deepEqual(lm.sectors.map((c) => c.key), ["Information Technology", "Financials", "Energy", "Materials", "Industrials"]);
  assert.deepEqual(lm.funds.map((f) => f.ticker), ["XIU.TO", "XBB.TO", "GLD", "ZST.TO"]);
  assert.equal(strip(lm.notes[0]), "Fund holdings as published on 12 Nov 2026, the last day of the data. Nothing dated later is used.");
  assert.equal(strip(lm.notes[1]), "The holdings those files name cover 77.9 % of XIU.TO; the country and industry splits cover each whole fund.");
  const older = load("robert"); older.lookthrough.today.snapshot = { "XIU.TO": "2026-10-31" };
  assert.match(strip(H.lookModel(older, PF).notes[0]), /^Fund holdings as published on or before 12 Nov 2026, the last day of the data\./);
  const gap = load("robert"); gap.lookthrough.today.gaps = [{ etf: "XIU.TO", missing: "holdings", coverage: 0 }];
  assert.ok(H.lookModel(gap, PF).notes.some((x) => /No holdings list for XIU\.TO: what is inside it is unknown here, not zero\./.test(x)));
  assert.equal(lm.notes[lm.notes.length - 1], "Each fund’s own fees are already in its price (adjusted close, dividends reinvested).");
  const tc = H.lookModel(load("canadian"), PF);
  assert.match(strip(tc.notes[1]), /77\.9 % of XIU\.TO and 51\.8 % of SPY/);
  assert.equal(strip(tc.countries[1].afterText), "21.5 %");
});

t("G3: the hero persona line gains the objective and horizon from result.profile, in words, within R22's six figures", () => {
  const want = { robert: "Objective: preserve capital with some growth, over about four years.", mateo: "Objective: balance growth and stability, over about ten years.",
    amira: "Objective: grow capital, over about fifteen years.", canadian: "Objective: balance growth and stability, over about ten years." };
  for (const name of NAMES) {
    const r = load(name), c = U.heroCopy(r, PF.view(r));
    assert.equal(c.aim, want[name], name);
    assert.ok(c.strings.includes(c.aim), `${name}: counted with the hero's strings`);
    assert.ok(c.strings.reduce((k, x) => k + U.numbersIn(x), 0) <= 8, name);     // R22's six + R35's two
    /* R35: the two limits apart, never one "loss limit" */
    const who = [...c.persona.who, ...c.persona.limits].map((x) => x[0]).join("").replace(/\u00a0/g, " ");
    const L = r.limits, above = PF.fmt.money(r.amount - L.capacity_dollars), fl = strip(PF.fmt.share(-L.floor));
    assert.ok(who.includes(`stay above ${above}`), `${name}: ${who}`);
    assert.ok(who.includes(`no fall of more than ${fl} from a high`), `${name}: ${who}`);
    assert.doesNotMatch(who, /loss limit/, name);
    assert.deepEqual(metaHits(who), [], name);
    assert.deepEqual(adviceHits(who, []), [], name);
    assert.deepEqual(adviceHits(c.aim, []), [], name);
  }
  assert.equal(U.aimLine({ profile: { goal: "growth", horizon_years: 30 } }), "Objective: grow capital, over about 30 years.");
  assert.equal(U.aimLine({ profile: { goal: "growth" } }), "Objective: grow capital.");
  assert.equal(U.aimLine({ profile: { goal: "yolo", horizon_years: 3 } }), null);
  assert.equal(U.aimLine(null), null);
});

t("the holdings editor: seeded with the investor's own mix only, a live total that must reach 100 %", () => {
  const r = load("robert"), rows = H.seedRows(r);
  assert.deepEqual(rows, [{ ticker: "XIU.TO", pct: 45 }, { ticker: "XBB.TO", pct: 35 }, { ticker: "GLD", pct: 10 }, { ticker: "ZST.TO", pct: 10 }]);
  assert.deepEqual(H.seedRows(load("mateo")).map((x) => x.pct), [35, 35, 12, 10, 8]);
  assert.equal(H.totalOf(rows), 100);
  assert.ok(H.totalOk(H.totalOf(rows)));
  assert.deepEqual(H.editProblems(rows, 600000), []);
  const less = rows.map((x) => (x.ticker === "GLD" ? { ...x, pct: 5 } : x));
  assert.equal(H.totalOf(less), 95);
  assert.deepEqual(H.editProblems(less, 600000).map(strip), ["The weights add up to 95 %; they must reach 100 %."]);
  assert.equal(H.customFrom(less, 600000, "robert"), null);
  const blank = [...rows.slice(0, 3), { ticker: "ZST.TO", pct: "" }];
  assert.equal(H.totalOf(blank), 90);
  assert.ok(H.editProblems(blank, 600000).some((x) => /Give Short-term bonds a weight above 0/.test(x)));
  assert.deepEqual(H.editProblems([], 600000), ["Add at least one holding."]);
  assert.ok(H.editProblems(rows, "").includes("Type an amount above $0."));
  assert.equal(H.totalOf([{ ticker: "SPY", pct: "33.3" }, { ticker: "QQQ", pct: "33.3" }, { ticker: "GLD", pct: "33.4" }]), 100);
  for (const w of H.editProblems(less, 0).concat(H.editProblems(blank, 1))) assert.deepEqual(adviceHits(w, []), [], w);
});

t("use these holdings, reset, the static line", () => {
  const r = load("robert");
  const rows = [{ ticker: "XIU.TO", pct: 40 }, { ticker: "XBB.TO", pct: 30 }, { ticker: "SPY", pct: 20 }, { ticker: "GLD", pct: 10 }];
  const c = H.customFrom(rows, "500000", "robert");
  assert.deepEqual(c, { pilot: "robert", portfolio: { "XIU.TO": 0.4, "XBB.TO": 0.3, SPY: 0.2, GLD: 0.1 }, amount: 500000 });
  const m = H.customModel(r, c, PF);
  assert.equal(m.title, "Your holdings (edited)");
  assert.equal(m.look.kind, "pending");
  assert.equal(m.look.text, "Replay to see these holdings through 2021–26 and what is inside their funds.");
  assert.deepEqual(adviceHits(m.look.text, []), []);
  assert.deepEqual(m.rows.map((x) => [x.ticker, x.dollarsText]), [["XIU.TO", "$200,000"], ["XBB.TO", "$150,000"], ["SPY", "$100,000"], ["GLD", "$50,000"]]);
  assert.equal(H.customModel(load("mateo"), c, PF), null, "another investor's edit never shows");
  assert.equal(H.customFor(c, "robert"), c);
  assert.equal(H.customFor(c, "amira"), null);
  assert.equal(H.customFor(null, "robert"), null);
  assert.equal(H.resetLabel(r), "Back to Robert’s holdings");
  assert.equal(H.resetLabel(load("canadian")), "Back to this portfolio’s holdings");
  assert.equal(H.staticEditLine(r), "Editing holdings needs the live app; these are Robert’s fictional holdings.");
  assert.equal(H.staticEditLine(load("canadian")), "Editing holdings needs the live app; these are this portfolio’s fictional holdings.");
  assert.equal(H.ranOn(c, r), false);
  assert.equal(H.ranOn({ pilot: "robert", portfolio: { ...r.baseline.portfolio }, amount: 600000 }, r), true);
  for (const w of [H.EDITED_TITLE, H.resetLabel(r), H.staticEditLine(r)]) { assert.deepEqual(adviceHits(w, []), [], w); assert.deepEqual(metaHits(w), [], w); }
});

t("Replay sends the edited holdings: POST /api/run's body carries the portfolio and the amount", () => {
  const r = load("robert"), c = { pilot: "robert", portfolio: { "XIU.TO": 0.5, SPY: 0.5 }, amount: 400000 };
  const body = PF.requestBody({ ...PF.planFrom(r, "robert"), q: r.question }, null, false);
  assert.deepEqual(body.portfolio, r.baseline.portfolio, "without an edit: the investor's own mix");
  const sent = H.withHoldings(body, c, "robert");
  assert.deepEqual(sent.portfolio, { "XIU.TO": 0.5, SPY: 0.5 });
  assert.equal(sent.amount, 400000);
  assert.equal(sent.question, body.question);
  assert.deepEqual(sent.profile, body.profile);
  assert.deepEqual(body.portfolio, r.baseline.portfolio, "the original body is untouched");
  assert.equal(H.withHoldings(body, c, "mateo"), body, "another investor: unchanged");
  assert.equal(H.withHoldings(body, null, "robert"), body);
  /* replay.js sends it that way (one call on the body it already builds) */
  const src = readFileSync(new URL("../web/sections/replay.js", import.meta.url), "utf8");
  assert.match(src, /withHoldings\(PF\.requestBody\(/);
});

t("'You' (R46, lane profile-ui): the card shows the assumed example mix until the first You run lands, never another investor's", () => {
  const robert = load("robert"), mix = { "XIU.TO": 0.35, "XBB.TO": 0.3, SPY: 0.25, GLD: 0.1 };
  const holdings = { pilot: "you", portfolio: mix, amount: 100000, assumed: true };
  const seed = H.youSeed({ investor: "you", result: robert, holdings });
  assert.deepEqual(seed, { status: "ok", pilot: "you", amount: 100000, portfolio: mix, profile: null });
  assert.equal(H.youSeed({ investor: "robert", result: robert, holdings }), null);
  assert.equal(H.youSeed({ investor: "you", result: { ...robert, pilot: "you" }, holdings }), null, "the You run has landed");
  assert.equal(H.youSeed({ investor: "you", result: robert, holdings: null }), null);
  const m = H.holdModel(seed, PF);
  assert.equal(m.title, "Your holdings now");
  assert.deepEqual(m.rows.map((x) => [x.ticker, x.dollarsText]), [["XIU.TO", "$35,000"], ["XBB.TO", "$30,000"], ["SPY", "$25,000"], ["GLD", "$10,000"]]);
  assert.equal(m.look, null);
  assert.equal(H.lookModel(seed, PF), null);
  assert.equal(H.ranOn(holdings, seed), true);
  assert.equal(H.resetLabel(seed), null);
  assert.equal(H.staticEditLine(seed), "Editing holdings needs the live app; this mix is an assumed example.");
  assert.deepEqual(H.customFrom(H.seedRows(seed), 100000, seed.pilot), { pilot: "you", portfolio: mix, amount: 100000 }, "the submit drops 'assumed'");
  for (const w of [H.YOU_TITLE, H.YOU_ASSUMED, H.staticEditLine(seed)]) assert.deepEqual(adviceHits(w, []), [], w);
  assert.ok(adviceHits("What you hold", []).length > 0, "why the title is not 'What you hold'");
});

t("the limits card (LIMITS_MODEL.md): every limit with its value and source; set by you > from your words > assumed", () => {
  const r = load("robert"), c = H.limitsCard(r, PF, null);
  assert.equal(c.summary, "8 limits, all assumed from the profile, none set by you.");
  assert.deepEqual(c.rows.map((x) => [x.key, strip(x.value), x.tag]), [
    ["floor", "No more than 15 % from any high", "assumed"], ["capacity", "$90,000, staying above $510,000", "assumed"],
    ["scenario_stress", "No more than 7.5 %", "assumed"], ["single_stock", "Up to 10 %", "assumed"], ["sector", "Up to 35 %", "assumed"],
    ["crypto", "Excluded (0 %)", "assumed"], ["values", "Off", "assumed"], ["horizon", "4 years", "assumed"]]);
  assert.equal(c.precedence, "Set by you wins over your words, and your words win over what the profile assumed.");
  assert.deepEqual(c.conflicts, []);
  assert.ok(H.limitsCard(load("mateo"), PF, null).rows.some((x) => x.key === "values" && x.value === "On"));
  /* from your words (lane profile-ui's store.limitsIn), the exact words kept for the hover */
  const inn = { pilot: "robert", limits: { sector_caps: { Energy: 0 }, crypto: 0 }, capacity: 40000,
    source: { capacity: "words", "sector_caps.Energy": "words", crypto: "words" }, words: { capacity: "losing $40,000 at most" } };
  const w = H.limitsCard(r, PF, inn);
  const cap = w.rows.find((x) => x.key === "capacity");
  assert.deepEqual([strip(cap.value), cap.tag, cap.words], ["$40,000, staying above $560,000", "from your words", "losing $40,000 at most"]);
  assert.equal(strip(w.rows.find((x) => x.key === "sector_caps.Energy").value), "Excluded (0 %)");
  assert.equal(w.summary, "9 limits: 3 from your words and 6 assumed from the profile.");
  assert.equal(cap.assumed, "the profile assumed $90,000", "words vs assumed: the words win, and the screen says what was assumed");
  assert.equal(H.limitsCard(r, PF, { ...inn, pilot: "mateo" }).rows.length, 8, "another investor's words never apply");
  /* the values screen: your words turn it on over the profile's off */
  const ew = H.limitsCard(r, PF, { pilot: "robert", limits: { esg: true }, words: { esg: "I care about ESG" } }).rows.find((x) => x.key === "values");
  assert.deepEqual([ew.value, ew.tag, ew.assumed], ["On", "from your words", "the profile assumed off"]);
  /* set by you wins over your words */
  const e = load("robert"); e.limits = { ...e.limits, crypto: 0.05, edited: ["crypto"] };
  const lc = H.limitsCard(e, PF, { ...inn, words: { ...inn.words, crypto: "no crypto" } }), ce = lc.rows.find((x) => x.key === "crypto");
  assert.deepEqual([strip(ce.value), ce.tag], ["Up to 5 %", "set by you"]);
  /* words vs set by you: the typed value wins and one line says so (amber on screen) */
  assert.deepEqual(lc.conflicts.map((x) => strip(x.text)), ["You said “no crypto”; you set crypto to up to 5 %. The replay uses your value."]);
  /* a limit the run does not carry reads "No limit", with no source tag */
  const nl = load("robert"); delete nl.limits.single_stock;
  const one = H.limitsCard(nl, PF, null).rows.find((x) => x.key === "single_stock");
  assert.deepEqual([one.value, one.tag], ["No limit", null]);
  /* the run's own facts (lane sector-limits): from_words wins over edited (words reach the engine as overrides), caps one key */
  const run = load("robert");
  run.limits = { ...run.limits, sector_caps: { Energy: 0, "Information Technology": 0.2 }, edited: ["sector_caps", "crypto"], crypto: 0,
    from_words: ["sector_caps.Energy"] };
  const cr = H.limitsCard(run, PF, { pilot: "robert", words: { "sector_caps.Energy": "no oil companies" } }).rows;
  assert.deepEqual(cr.filter((x) => x.key.startsWith("sector_caps")).map((x) => [x.label, strip(x.value), x.tag, x.words]),
    [["Energy", "Excluded (0 %)", "from your words", "no oil companies"], ["Information Technology", "Up to 20 %", "set by you", null]]);
  assert.equal(cr.find((x) => x.key === "crypto").tag, "set by you");
  const none = load("robert"); none.limits = null; none.verdict = null;
  assert.deepEqual(H.limitsCard(none, PF, null), { rows: [], none: true, summary: "No limits set" });
  /* the engine's own tag per check wins (governance.limit_source, the checks' `source`) */
  const tagged = load("mateo");
  tagged.checks = tagged.checks.map((c) => (c.rule === "esg_direct" ? { ...c, source: "you" } : c.rule === "single_stock" ? { ...c, source: "words" } : c));
  const tr = H.limitsCard(tagged, PF, null).rows;
  assert.equal(tr.find((x) => x.key === "values").tag, "set by you");
  assert.equal(tr.find((x) => x.key === "single_stock").tag, "from your words");
  /* limits-QA (17:10): a floor the words' capacity set reads from your words, with its link on hover; a horizon from the words too */
  const q = load("robert");
  q.limits = { ...q.limits, floor: -0.2, floor_source: "capacity", capacity_dollars: 40000, from_words: ["capacity", "horizon_years", "esg"] };
  q.amount = 200000; q.profile = { ...q.profile, capacity: 40000, horizon_years: 10, esg: true };
  const qr = H.limitsCard(q, PF, null).rows, qf = qr.find((x) => x.key === "floor");
  assert.equal(qf.tag, "from your words");
  assert.match(strip(qf.say), /^20 % = the \$40,000 you could lose, of \$200,000\./);
  assert.equal(qr.find((x) => x.key === "horizon").tag, "from your words");
  assert.deepEqual([qr.find((x) => x.key === "values").value, qr.find((x) => x.key === "values").tag], ["On", "from your words"]);
  assert.equal(qr.find((x) => x.key === "capacity").tag, "from your words");
  /* limits-QA (17:20), You: a re-read before the replay is the card's (limitsIn + the holdings' amount), never the old run's */
  const youRun = load("robert"); youRun.pilot = "you"; youRun.amount = 200000;
  youRun.limits = { ...youRun.limits, capacity_dollars: 40000, crypto: 0, from_words: ["capacity", "crypto"] };
  const plan = { pilot: "you", limits: {}, capacity: 50000, esg: true, source: { capacity: "words", esg: "words" }, words: { capacity: "could lose $50,000", esg: "I care about ESG" } };
  const yc = H.limitsCard(youRun, PF, plan, { pilot: "you", portfolio: { SPY: 1 }, amount: 250000, assumed: true });
  assert.equal(yc.plan, true);
  assert.equal(strip(yc.rows.find((x) => x.key === "capacity").value), "$50,000, staying above $200,000");
  assert.deepEqual([yc.rows.find((x) => x.key === "crypto").value, yc.rows.find((x) => x.key === "crypto").tag], ["Assumed from the profile", "assumed"]);
  assert.deepEqual([yc.rows.find((x) => x.key === "values").value, yc.rows.find((x) => x.key === "values").tag, yc.rows.find((x) => x.key === "values").words], ["On", "from your words", "I care about ESG"]);
  assert.ok(yc.rows.every((x) => x.value !== "No limit"), "before the You replay, unstated limits are assumed, never 'No limit'");
  /* before the first You run, with nothing read yet: every limit assumed */
  const seedRun = { status: "ok", pilot: "you", amount: 100000, portfolio: { SPY: 1 }, profile: null };
  assert.ok(H.limitsCard(seedRun, PF, null, null).rows.every((x) => x.tag === "assumed"));
  /* a capacity typed in #checklist (only "floor" in edited): set by you, and the line recomputed, never the run's old one */
  const typed = load("robert"); typed.limits = { ...typed.limits, capacity_dollars: 60000, floor: -0.1, edited: ["floor"] };
  typed.capacity = { capacity: 90000, line: 510000, today: { line: 510000 } };
  const tc2 = H.limitsCard(typed, PF, null).rows.find((x) => x.key === "capacity");
  assert.deepEqual([strip(tc2.value), tc2.tag], ["$60,000, staying above $540,000", "set by you"]);
  /* limits-QA final pass (17:55): You's floor set by the words' capacity takes the capacity's tag, one floor one source */
  const yf = load("robert"); yf.pilot = "you"; yf.amount = 200000;
  yf.limits = { ...yf.limits, floor: -0.2, floor_source: "capacity", capacity_dollars: 40000, from_words: ["capacity"] };
  yf.profile = { ...yf.profile, capacity: 40000, horizon_years: 10 };
  const yIn = { pilot: "you", limits: {}, capacity: 40000, source: { capacity: "words", horizon: "words" }, words: { capacity: "could lose $40,000 at most" } };
  const yh = { pilot: "you", portfolio: { SPY: 1 }, amount: 200000 };
  const yr = H.limitsCard(yf, PF, yIn, yh).rows;
  const yfl = yr.find((x) => x.key === "floor");
  assert.deepEqual([yfl.tag, yfl.words], ["from your words", "could lose $40,000 at most"]);
  assert.doesNotMatch(yfl.say, /Assumed from the profile/, "the hover never contradicts the tag");
  assert.equal(yr.find((x) => x.key === "horizon").tag, "from your words", "the horizon under either name");
  /* a stale run during a clarify question: the run read capacity and Energy from earlier words; the new words lack both */
  const st = load("robert"); st.pilot = "you"; st.amount = 200000;
  st.limits = { ...st.limits, capacity_dollars: 40000, sector_caps: { Energy: 0 }, from_words: ["capacity", "sector_caps.Energy", "crypto"], crypto: 0 };
  const sp = H.limitsCard(st, PF, { pilot: "you", limits: { crypto: 0 }, source: { crypto: "words" }, words: { crypto: "No crypto" } }, yh);
  assert.equal(sp.plan, true);
  assert.ok(!sp.rows.some((x) => x.key === "sector_caps.Energy"), "the old run's Energy cap never leaks in");
  assert.equal(sp.rows.find((x) => x.key === "capacity").value, "Assumed from the profile");
  /* the static demo's recorded You run (limits-QA 18:14): its words set esg and the horizon too; a plan without those keys but
     with the same limits is the same plan: the run's own values show, never "Assumed from the profile" */
  const rec = load("robert"); rec.pilot = "you"; rec.amount = 200000;
  rec.limits = { ...rec.limits, floor: -0.2, floor_source: "capacity", capacity_dollars: 40000, crypto: 0, sector_caps: { Energy: 0 },
    from_words: ["crypto", "sector_caps.Energy", "capacity", "esg", "horizon_years"] };
  rec.profile = { ...rec.profile, capacity: 40000, horizon_years: 8, esg: true };
  const hint = { pilot: "you", limits: { crypto: 0, sector_caps: { Energy: 0 } }, capacity: 40000, esg: null,
    source: { crypto: "words", "sector_caps.Energy": "words", capacity: "words" }, words: { capacity: "could lose $40,000" } };
  const rc = H.limitsCard(rec, PF, hint, { pilot: "you", portfolio: { SPY: 1 }, amount: 200000, assumed: true });
  assert.notEqual(rc.plan, true, "the recorded run's card");
  assert.equal(strip(rc.rows.find((x) => x.key === "floor").value), "No more than 20 % from any high");
  assert.ok(rc.rows.some((x) => x.key === "horizon"), "the horizon row shows");
  assert.ok(rc.rows.every((x) => x.value !== "Assumed from the profile"));
  /* no limits is valid */
  assert.deepEqual(H.limitsCard(r, PF, { pilot: "robert", none: true }), { rows: [], none: true, summary: "No limits set" });
  for (const x of [...c.rows, ...w.rows]) for (const t of [x.label, x.value, x.tag, x.say]) {
    assert.deepEqual(adviceHits(t, []), [], t); assert.deepEqual(metaHits(t), [], t); assert.deepEqual(verdictHits(t), [], t);
  }
});

t("limit words in a persona's question (limits-QA 5): one line says where they work; the recorded questions never trigger it", () => {
  for (const name of NAMES) assert.equal(H.limitWordsLine(load(name)), null, name);
  for (const q of ["What if I put 20 % in Shopify?", "What if I put 5 % in Bitcoin?", "What if the US–China chip war heats up again?"]) {
    const r = load("robert"); r.question = q; assert.equal(H.limitWordsLine(r), null, q);
  }
  const r = load("robert"); r.question = "What if I put 40 % in NVIDIA? I don't care about ESG and I could lose $50,000.";
  const lw = H.limitWordsLine(r);
  assert.equal(lw.text, "Limits in your own words work under You. Robert’s limits are the profile’s, in the line above.");
  assert.deepEqual(adviceHits(lw.text, []), []);
  const y = load("robert"); y.pilot = "you"; y.question = r.question;
  assert.equal(H.limitWordsLine(y), null, "under You the words are read");
  const m = load("mateo"); m.question = "No crypto, and at most 10 % in one company: what if oil spikes?";
  assert.match(H.limitWordsLine(m).text, /Mateo’s limits are the profile’s/);
});

t("words: no advice, no verdict, no meta dots, nothing undefined, on every fixture", () => {
  for (const name of NAMES) {
    const r = load(name), m = H.holdModel(r, PF), st = H.stripModel(r, PF), lm = H.lookModel(r, PF);
    const words = [m.title, ...m.rows.flatMap((x) => [x.label, x.ticker, x.name, x.weightText, x.dollarsText]), m.more && m.more.label, m.look && m.look.text,
      m.noMove, st && st.summary, ...(lm.notes || []), lm.sectorNote, lm.noMove, ...lm.countries.map((c) => c.name), ...lm.funds.map((f) => f.name),
      H.WHY.question, H.WHY.answer, H.WHY.link, H.DIRECT_LINE, H.FEES, m.fiction].filter(Boolean);
    for (const w of words) {
      assert.deepEqual(adviceHits(w, [r.question]), [], `${name}: ${w}`);
      assert.deepEqual(verdictHits(w), [], `${name}: ${w}`);
      assert.deepEqual(metaHits(w), [], `${name}: ${w}`);
      assert.doesNotMatch(w, /undefined|NaN|null/, `${name}: ${w}`);
    }
  }
});

t("a stopped run, or no mix, shows nothing; a run without an amount shows weights only", () => {
  const b = load("robert"); b.status = "blocked";
  assert.equal(H.holdModel(b, PF), null);
  assert.equal(H.holdModel({ status: "ok", portfolio: {} }, PF), null);
  assert.equal(H.holdModel(null, PF), null);
  const na = load("robert"); delete na.amount;
  const m = H.holdModel(na, PF);
  assert.ok(m.rows.every((x) => x.dollars === null && x.dollarsText === null));
});

t("lane funds' drawer: wired only once the page links css/fundpage.css; a fund's name and 'What's inside the funds' open it", () => {
  const src = readFileSync(new URL("../web/sections/hold.js", import.meta.url), "utf8");
  assert.match(src, /const hasDrawer = \(\) => [^\n]*css\/fundpage\.css/);
  assert.equal((src.match(/import\("\.\/fundpage\.js"\)/g) || []).length, 1, "one lazy import");
  assert.match(src, /openFunds\(store, "owning", btn\)/);
  assert.match(src, /x\.kind === "fund" && hasDrawer\(\) \? fundButton\(x\)/);
  assert.match(src, /"aria-haspopup": "dialog"/);
});

t("phones: the list keeps label, weight and dollars on one line, the ticker under the label", () => {
  const css = readFileSync(new URL("../web/css/hold.css", import.meta.url), "utf8");
  const phone = css.slice(css.indexOf("@media (max-width: 760px)"));
  assert.match(phone, /\.hd-row \{[^}]*grid-template-areas: "key label w d" "\. tk \. \."/);
  assert.match(phone, /\.hd-tk \{[^}]*grid-area: tk/);
  const html = readFileSync(new URL("../web/index.html", import.meta.url), "utf8");
  assert.match(html, /href="css\/hold\.css"/);
});

t("universeGroups: the 31 assets a run can hold, each once, grouped as a reader looks for them", () => {
  const g = F.universeGroups();
  assert.deepEqual(g.map((x) => x.label), ["Canadian stocks", "US stocks", "Funds (ETFs)", "Crypto"]);
  const all = g.flatMap((x) => x.tickers);
  assert.equal(all.length, 31);
  assert.deepEqual([...all].sort(), [...F.UNIVERSE].sort());
  assert.ok(g[0].tickers.every((tk) => tk.endsWith(".TO") && F.kindOf(tk) === "stock"));
  assert.ok(g[1].tickers.every((tk) => !tk.endsWith(".TO") && F.kindOf(tk) === "stock"));
  assert.ok(g[2].tickers.every((tk) => F.kindOf(tk) === "fund"));
  assert.deepEqual(g[3].tickers, ["BTC-USD", "ETH-USD"]);
  assert.ok(!all.includes("XSP.TO") && !all.includes("META"), "named for words only, not in the dataset");
  assert.deepEqual(F.universeGroups(["NVDA", "XIU.TO"])[1].tickers.includes("NVDA"), false, "held ones are left out");
});

console.log(`web_hold_test: ${n} groups passed`);
