// Lane picker: "Try another move" (web/lib/movepicker.js, pure). Committed fixtures only (ruling R17): the four public-cut runs
// (tests/fixtures/web/*.json) and the moves list in the shape of data/demo_runs/moves.json (tests/fixtures/web/moves.json).
// Run: node tests/web_picker_test.mjs   (tests/test_web_lib.py runs every tests/web_*_test.mjs)
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { load, NAMES } from "./web_fixtures.mjs";
import * as M from "../web/lib/movepicker.js";
import { fundName, plainLabel, kindOf } from "../web/lib/funds.js";
import { adviceHits, verdictHits, metaHits } from "../scripts/gate_rules.mjs";

const PF = createRequire(import.meta.url)("../web/lib.js");
globalThis.PF = PF;
const MOVES = JSON.parse(readFileSync(new URL("./fixtures/web/moves.json", import.meta.url), "utf8"));
let n = 0;
const t = (name, fn) => {
  try { fn(); } catch (e) { e.message = `${name}: ${e.message}`; throw e; }
  n += 1;
};
const NB = "\u00a0";

/* the starter universe, as the brief lists it (31 assets: assets_universe.csv) */
const EXPECTED = {
  "Canadian stocks": ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO"],
  "US stocks": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM"],
  "Stock ETFs": ["XIU.TO", "SPY", "QQQ", "ESGV"],
  "Bond ETFs": ["XBB.TO", "ZST.TO", "AGG", "TLT"],
  "Gold": ["GLD"],
  "Crypto": ["BTC-USD", "ETH-USD"],
};
const ALL = Object.values(EXPECTED).flat();

/* ---- the list: six groups in the brief's order, every one of the 31 assets in exactly one ---- */
t("the six groups, in order, hold exactly the 31 starter assets, each once", () => {
  assert.deepEqual(M.GROUPS.map((g) => g.label), Object.keys(EXPECTED));
  assert.equal(ALL.length, 31);
  assert.equal(M.UNIVERSE.length, 31);
  assert.deepEqual([...M.UNIVERSE].sort(), [...ALL].sort());
  assert.equal(new Set(M.UNIVERSE).size, 31);
  for (const [label, tickers] of Object.entries(EXPECTED)) {
    const g = M.GROUPS.find((x) => x.label === label);
    assert.deepEqual([...g.tickers].sort(), [...tickers].sort(), label);
    for (const tk of tickers) assert.equal(M.groupOf(tk), g.id, `${tk} is in ${label}`);
  }
  assert.equal(M.groupOf("META"), null);              // not in the starter universe
  assert.equal(M.groupOf("XSP.TO"), null);            // the workshop's fund, not one of the 31
  assert.equal(M.groupOf(undefined), null);
});

t("every asset takes its public name and kind from web/lib/funds.js (the one map), and the kind matches its group", () => {
  const kinds = { "Canadian stocks": "stock", "US stocks": "stock", "Stock ETFs": "fund", "Bond ETFs": "fund", Gold: "fund", Crypto: "crypto" };
  for (const [label, tickers] of Object.entries(EXPECTED)) {
    for (const tk of tickers) {
      assert.notEqual(fundName(tk), tk, `${tk} has a public name`);
      assert.equal(kindOf(tk), kinds[label], tk);
    }
  }
});

t("the list: names first, ticker after, alphabetical within each group, ETFs carry what is inside them", () => {
  const groups = M.assetOptions(null);
  assert.deepEqual(groups.map((g) => g.label), Object.keys(EXPECTED));
  for (const g of groups) {
    const names = g.options.map((o) => o.name);
    assert.deepEqual(names, [...names].sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" })), `${g.label} alphabetical`);
    for (const o of g.options) {
      assert.equal(o.name, M.askName(o.ticker));
      assert.ok(o.text.startsWith(`${o.name} (${o.ticker})`), o.text);
      if (kindOf(o.ticker) === "fund") assert.ok(o.hint && o.text.endsWith(o.hint), `${o.ticker} carries its hint: ${o.text}`);
      else assert.equal(o.hint, null, o.ticker);
    }
  }
  const ca = groups[0].options.map((o) => o.ticker);
  assert.deepEqual(ca, ["ATD.TO", "CNR.TO", "CNQ.TO", "CSU.TO", "ENB.TO", "FTS.TO", "MFC.TO", "RY.TO", "SHOP.TO", "TD.TO"]);
  const etf = groups[2].options;
  assert.equal(etf.find((o) => o.ticker === "QQQ").text, "Invesco QQQ Trust (QQQ), US tech stocks");
  assert.equal(etf.find((o) => o.ticker === "XIU.TO").text, "iShares S&P/TSX 60 Index ETF (XIU.TO), Canadian stocks");
  assert.equal(groups[3].options.find((o) => o.ticker === "TLT").text, "iShares 20+ Year Treasury Bond ETF (TLT), long US Treasury bonds");
  assert.equal(groups[4].options[0].text, "SPDR Gold Shares (GLD), gold");
  assert.equal(groups[5].options.map((o) => o.text).join("|"), "Bitcoin (BTC-USD)|Ether (ETH-USD)");
});

t("the asked name is the public name without a trailing parenthesis", () => {
  assert.equal(M.askName("GOOGL"), "Alphabet");
  assert.equal(M.askName("QQQ"), "Invesco QQQ Trust");
  assert.equal(M.askName("SHOP.TO"), "Shopify");
  assert.equal(M.askName("RY.TO"), "Royal Bank of Canada");
  assert.equal(M.askName("TLT"), "iShares 20+ Year Treasury Bond ETF");
  for (const tk of ALL) assert.doesNotMatch(M.askName(tk), /[()]/, tk);
});

/* ---- the question: "What if I put N % in <public name>?" (INTERFACES.md, moves.json) ---- */
t("the question is composed in the curated wording, for every asset, and read back", () => {
  assert.equal(M.composeQuestion("SHOP.TO", 20), "What if I put 20 % in Shopify?");
  assert.equal(M.composeQuestion("BTC-USD", 5), "What if I put 5 % in Bitcoin?");
  assert.equal(M.composeQuestion("GOOGL", 15), "What if I put 15 % in Alphabet?");
  for (const m of MOVES.moves.filter((x) => !x.default)) {
    assert.equal(M.composeQuestion(m.ticker, Math.round(m.weight * 100), m.from), m.question, m.ticker);
  }
  for (const tk of ALL) for (const pct of [1, 5, 20, 37, 50]) {
    assert.deepEqual(M.parseQuestion(M.composeQuestion(tk, pct)), { ticker: tk, pct }, `${tk} ${pct}`);
  }
  assert.equal(M.composeQuestion("META", 20), null);
  assert.equal(M.composeQuestion("SHOP.TO", 0), "What if I put 1 % in Shopify?");     // sizes are kept in 1..50
  assert.equal(M.composeQuestion("SHOP.TO", 80), "What if I put 50 % in Shopify?");
});

t("the recorded wording reads back too (scripts/record_demo.py --scripted, data/demo_scripted.json): 'the' before a fund, 'my' and a plain label for the source", () => {
  assert.deepEqual(M.parseQuestion("What if I put 20 % in the Invesco QQQ Trust?"), { ticker: "QQQ", pct: 20 });
  assert.deepEqual(M.parseQuestion("What if I put 20 % in the iShares 20+ Year Treasury Bond ETF?"), { ticker: "TLT", pct: 20 });
  assert.deepEqual(M.parseQuestion("What if I put 10 % in SPDR Gold Shares?"), { ticker: "GLD", pct: 10 });
  assert.deepEqual(M.parseQuestion("What if I move 40 % of my money from my Canadian stocks into NVIDIA?"), { ticker: "NVDA", pct: 40, from: "XIU.TO" });
  assert.deepEqual(M.parseQuestion("What if I move 30 % of my money from my Canadian bonds into NVIDIA?"), { ticker: "NVDA", pct: 30, from: "XBB.TO" });
  assert.deepEqual(M.parseQuestion("What if I move 10 % of my money from my Shopify shares into Bitcoin?"), { ticker: "BTC-USD", pct: 10, from: "SHOP.TO" });
  /* a plain label names one asset only, so it can be read back */
  const labels = ALL.map((tk) => plainLabel(tk).toLowerCase());
  assert.equal(new Set(labels).size, 31, "plain labels are unique across the 31");
  /* a fund named "... ETF" or "... Trust" takes "the" when asked about (the recorded wording); others do not */
  assert.equal(M.composeQuestion("QQQ", 20), "What if I put 20 % in the Invesco QQQ Trust?");
  assert.equal(M.composeQuestion("TLT", 20), "What if I put 20 % in the iShares 20+ Year Treasury Bond ETF?");
  assert.equal(M.composeQuestion("GLD", 10), "What if I put 10 % in SPDR Gold Shares?");
  assert.equal(M.composeQuestion("SHOP.TO", 20, "XIU.TO"), "What if I move 20 % of my money from my Canadian stocks into Shopify?");
  assert.equal(M.composeQuestion("BTC-USD", 10, "SHOP.TO"), "What if I move 10 % of my money from my Shopify shares into Bitcoin?");
});

t("reading a question back: the box's no-break space, spacing and the full public name are accepted; anything else is not a picked move", () => {
  assert.deepEqual(M.parseQuestion(`What if I put 20${NB}% in Shopify?`), { ticker: "SHOP.TO", pct: 20 });
  assert.deepEqual(M.parseQuestion("  what if I put 20% in  shopify ? "), { ticker: "SHOP.TO", pct: 20 });
  assert.deepEqual(M.parseQuestion("What if I put 20 % in Invesco QQQ Trust (Nasdaq-100)?"), { ticker: "QQQ", pct: 20 });
  assert.deepEqual(M.parseQuestion("What if I put 10 % in Alphabet (Class A)?"), { ticker: "GOOGL", pct: 10 });
  assert.deepEqual(M.parseQuestion("What if I put 30 % in RY.TO?"), { ticker: "RY.TO", pct: 30 });
  for (const q of [load("robert").question, load("canadian").question, "What if I put 0 % in Shopify?", "What if I put 51 % in Shopify?",
    "What if I put 20 % in Meta Platforms?", "What if I put 20 % in my cousin's startup?", "", null, 42]) {
    assert.equal(M.parseQuestion(q), null, String(q));
  }
});

t("the size: 1 to 50 %, default 20 %, steps of 5 on the buttons", () => {
  assert.equal(M.DEFAULT_PCT, 20);
  assert.equal(M.clampPct(20), 20);
  assert.equal(M.clampPct(0), 1);
  assert.equal(M.clampPct(-4), 1);
  assert.equal(M.clampPct(77), 50);
  assert.equal(M.clampPct(12.6), 13);
  assert.equal(M.clampPct("15"), 15);
  assert.equal(M.clampPct("abc"), 20);
  assert.equal(M.clampPct(undefined), 20);
  assert.equal(M.stepPct(20, 1), 25);
  assert.equal(M.stepPct(20, -1), 15);
  assert.equal(M.stepPct(3, 1), 5);
  assert.equal(M.stepPct(3, -1), 1);
  assert.equal(M.stepPct(5, -1), 1);
  assert.equal(M.stepPct(1, -1), 1);
  assert.equal(M.stepPct(1, 1), 5);
  assert.equal(M.stepPct(48, 1), 50);
  assert.equal(M.stepPct(50, 1), 50);
});

/* ---- saved moves (static mode): data/demo_runs/moves.json, published as runs/moves.json (lane U0's build hook) ---- */
t("moves.json is read strictly: the four defaults, the 16 curated moves and two taken-from moves; a malformed entry is dropped, never guessed", () => {
  const all = M.normalizeMoves(MOVES);
  assert.equal(all.length, 22);
  assert.equal(all.filter((m) => m.default).length, 4);
  const shop = all.find((m) => m.pilot === "robert" && m.ticker === "SHOP.TO");
  assert.deepEqual(shop, { pilot: "robert", ticker: "SHOP.TO", pct: 20, question: "What if I put 20 % in Shopify?", from: null,
    key: "a000000000000001", file: "runs/a000000000000001.json", default: false });
  const bad = { version: 1, moves: [
    { pilot: "robert", ticker: "META", weight: 0.2, question: "What if I put 20 % in Meta?", key: "b000000000000001" },   // not one of the 31
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.7, question: "q", key: "b000000000000002" },                      // over 50 %
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.2, question: "q", key: "../../etc/passwd" },                      // not a run key
    { pilot: "Robert!", ticker: "SHOP.TO", weight: 0.2, question: "q", key: "b000000000000003" },                     // not a pilot id
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.2, key: "b000000000000004" },                                     // no question
    null, 7, "x",
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.25, question: "What if I put 25 % in Shopify?", key: "b000000000000005" },
  ] };
  assert.deepEqual(M.normalizeMoves(bad).map((m) => m.key), ["b000000000000005"]);
  for (const x of [null, undefined, {}, { moves: "no" }, [], "moves"]) assert.deepEqual(M.normalizeMoves(x), []);
});

t("static filtering: only the investor's own question and that investor's saved moves are offered, in the list's order (no ranking)", () => {
  const all = M.normalizeMoves(MOVES);
  const robert = M.savedFor(all, "robert");
  assert.deepEqual(robert.map((m) => `${m.pct} ${m.ticker}${m.from ? ` from ${m.from}` : ""}`),
    ["20 RY.TO", "20 SHOP.TO", "30 NVDA from XBB.TO", "40 NVDA from XIU.TO", "20 TLT", "5 BTC-USD"]);
  assert.ok(robert.every((m) => m.pilot === "robert" && !m.default));
  assert.deepEqual(M.savedFor(all, "mateo").map((m) => m.ticker), ["XOM", "TSLA", "QQQ", "ESGV"]);
  assert.deepEqual(M.savedFor(all, "amira").map((m) => m.ticker), ["NVDA", "QQQ", "BTC-USD", "ETH-USD"]);
  assert.deepEqual(M.savedFor(all, "canadian").map((m) => m.ticker), ["QQQ", "ESGV", "AGG", "GLD"]);
  assert.deepEqual(M.savedFor([], "robert"), []);                         // no moves.json yet: the own question only
  assert.deepEqual(M.savedFor(null, "robert"), []);
  const chips = M.chips(all, "robert", "Robert");
  assert.deepEqual(chips.map((c) => c.label), ["Robert’s question", `20${NB}% Royal Bank`, `20${NB}% Shopify`,
    `30${NB}% NVIDIA from Canadian bonds`, `40${NB}% NVIDIA from Canadian stocks`, `20${NB}% Long US Treasury bonds`, `5${NB}% Bitcoin`]);
  assert.equal(chips[0].own, true);
  assert.deepEqual(M.chips([], "mateo", "Mateo").map((c) => c.label), ["Mateo’s question"]);
  assert.deepEqual(M.chips(all, "canadian", "Too Canadian?").map((c) => c.label)[0], "The original question");
  assert.equal(M.chips(all, "canadian", "Too Canadian?")[1].ticker, "QQQ");
});

t("a choice becomes one action: live writes the question; static loads a saved run or says, once, that the move runs on the live app", () => {
  const all = M.normalizeMoves(MOVES);
  assert.deepEqual(M.decide({ mode: "live", investor: "robert", choice: { value: "SHOP.TO", pct: 20 }, moves: all }),
    { kind: "write", question: "What if I put 20 % in Shopify?" });
  assert.deepEqual(M.decide({ mode: "live", investor: "robert", choice: { value: "AAPL", pct: 33 }, moves: [] }),
    { kind: "write", question: "What if I put 33 % in Apple?" });
  const saved = M.decide({ mode: "static", investor: "robert", choice: { value: "SHOP.TO", pct: 20 }, moves: all });
  assert.equal(saved.kind, "load");
  assert.equal(saved.move.key, "a000000000000001");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "SHOP.TO", pct: 25 }, moves: all }).kind, "honest");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "AAPL", pct: 20 }, moves: all }).kind, "honest");
  assert.equal(M.decide({ mode: "static", investor: "mateo", choice: { value: "SHOP.TO", pct: 20 }, moves: all }).kind, "honest");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "SHOP.TO", pct: 20 }, moves: [] }).kind, "honest");
  assert.deepEqual(M.decide({ mode: "static", investor: "robert", choice: { value: M.OWN }, moves: all }), { kind: "own" });
  assert.deepEqual(M.decide({ mode: "live", investor: "robert", choice: { value: M.OWN }, moves: all }), { kind: "own" });
  assert.deepEqual(M.decide({ mode: "live", investor: "robert", choice: { value: "META", pct: 20 }, moves: all }), { kind: "none" });
  /* a saved asset picked at another size snaps to the saved size (static), so the list never strands the reader */
  assert.equal(M.snapPct(all, "robert", "BTC-USD", 20), 5);
  assert.equal(M.snapPct(all, "robert", "SHOP.TO", 20), 20);
  assert.equal(M.snapPct(all, "robert", "AAPL", 20), 20);
});

t("the honest line, with the live app's link only when the page knows a safe https address", () => {
  assert.equal(M.HONEST, "This move runs on the live app.");
  assert.deepEqual(M.honestLine(null), { text: "This move runs on the live app.", link: null });
  assert.deepEqual(M.honestLine("https://d111.cloudfront.net/"),
    { text: "This move runs on the live app.", link: { href: "https://d111.cloudfront.net/", text: "Open the live app" } });
  for (const bad of ["http://d111.cloudfront.net/", "javascript:alert(1)", "https://user:pw@d111.cloudfront.net/", " https://x y/", "", 7]) {
    assert.equal(M.safeLiveUrl(bad), null, String(bad));
    assert.equal(M.honestLine(bad).link, null);
  }
});

t("where the saved moves come from: only a moves.json the static build announced on this site; otherwise none (no failed request)", () => {
  assert.deepEqual(M.movesSource({ mode: "static", announced: "runs/moves.json" }), { url: "runs/moves.json", kind: "moves" });
  assert.equal(M.movesSource({ mode: "static", announced: null }), null);               // no moves.json yet: the own question only
  assert.equal(M.movesSource({ mode: "live", announced: "runs/moves.json" }), null);    // live runs any move through the API
  assert.equal(M.movesSource({ mode: null }), null);
  for (const bad of ["https://elsewhere.example/moves.json", "//elsewhere.example/moves.json", "../moves.json", "javascript:x.json", "runs/moves.txt"]) {
    assert.equal(M.movesSource({ mode: "static", announced: bad }), null, bad);
  }
  /* a Result inside an entry (the build gives it the public cut) is used as is; another investor's is ignored */
  const r = { pilot: "robert", verdict: "outside", series: {}, question: "What if I put 20 % in Shopify?" };
  const withRun = M.normalizeMoves({ moves: [{ pilot: "robert", ticker: "SHOP.TO", weight: 0.2, question: r.question, key: "d000000000000001", result: r },
    { pilot: "mateo", ticker: "XOM", weight: 0.1, question: "What if I put 10 % in Exxon Mobil?", key: "d000000000000002", result: r }] });
  assert.equal(withRun[0].result, r);
  assert.equal("result" in withRun[1], false);
});

/* ---- each ETF's "what's inside" hint: the plain words of funds.js, and whether this run looked inside it (lane hold's
   look-through: lookthrough.today / .after coverage and snapshot, mode "lookthrough"); no new numbers ---- */
t("ETF hints: plain words always; 'looked inside in this run' only when the run's look-through names the fund", () => {
  const robert = load("robert"), amira = load("amira");
  assert.deepEqual(M.insideHint("XIU.TO", robert), { label: "Canadian stocks", looked: true });
  assert.deepEqual(M.insideHint("QQQ", robert), { label: "US tech stocks", looked: false });
  assert.deepEqual(M.insideHint("QQQ", amira), { label: "US tech stocks", looked: true });
  assert.deepEqual(M.insideHint("GLD", null), { label: "gold", looked: false });
  assert.equal(M.insideHint("SHOP.TO", robert), null);
  assert.equal(M.insideHint("BTC-USD", amira), null);
  const direct = { lookthrough: { today: { mode: "direct", coverage: { "XIU.TO": 0.78 }, snapshot: { "XIU.TO": "2026-11-12" } } } };
  assert.deepEqual(M.insideHint("XIU.TO", direct), { label: "Canadian stocks", looked: false });
  assert.equal(M.hintLine("XIU.TO", robert), "Inside this fund: Canadian stocks. This run looked inside it, using its published holdings.");
  assert.equal(M.hintLine("QQQ", robert), "Inside this fund: US tech stocks.");
  assert.equal(M.hintLine("SHOP.TO", robert), null);
  for (const tk of ALL) {
    const line = M.hintLine(tk, robert) || "";
    assert.doesNotMatch(line, /\d/, `${tk}: no new numbers`);
  }
  const groups = M.assetOptions(amira);
  assert.equal(groups[2].options.find((o) => o.ticker === "QQQ").text, "Invesco QQQ Trust (QQQ), US tech stocks");
});

/* ---- the hero's one button says what it does (coordinator, 14:30): investor, then move, then replay ---- */
t("the Replay button names the investor and whether the question names a move", () => {
  assert.equal(M.goLabel("Robert", true), "Replay Robert’s move");
  assert.equal(M.goLabel("Mateo", false), "Replay Mateo’s question");
  assert.equal(M.goLabel("Too Canadian?", true), "Replay this move");
  assert.equal(M.goLabel("Too Canadian?", false), "Replay this question");
  assert.equal(M.goLabel(null, true), "Replay this move");
  assert.equal(M.possessive("Amira"), "Amira’s");
  /* R46 (lane profile-ui): a fifth investor, "You": second person everywhere, "have" not "hold" (the gate reads "You hold" as advice) */
  assert.equal(M.possessive("You"), "your");
  assert.equal(M.goLabel("You", true), "Replay your move");
  assert.equal(M.goLabel("You", false), "Replay your question");
  assert.equal(M.askLabel("You", true), "The move, in your words");
  assert.equal(M.ownLabel("You"), "Your own question");
  assert.equal(M.wantsLabel("You"), "What you want to do");
  assert.equal(M.chips([], "you", "You")[0].label, "Your question");
  assert.equal(M.overLine({ pilot: "you", portfolio: { "XBB.TO": 0.3, "XIU.TO": 0.7 } }, "You", "XBB.TO", 40), `You have 30${NB}% in Canadian bonds.`);
  assert.deepEqual(adviceHits(M.overLine({ pilot: "you", portfolio: { "XBB.TO": 0.3, "XIU.TO": 0.7 } }, "You", "XBB.TO", 40)), []);
  assert.equal(M.wantsLabel("Robert"), "What Robert wants to do");                // R24: ② on the question box
  assert.equal(M.wantsLabel("Too Canadian?"), "What this investor wants to do");
  assert.equal(M.replayWords(load("robert")), "Replay it through 2021\u201326");   // R24: ③, the run's own years
  assert.equal(M.replayWords({ as_of: "2026-11-12", series: { dates: ["2026-01-05"] } }), "Replay it through 2026");
  assert.equal(M.replayWords(null), "Replay it on real market history");
  /* the design director (15:55): ② "The move, in Robert’s words" over the box; ③ a circle, the pill, then the years */
  assert.equal(M.askLabel("Robert", true), "The move, in Robert’s words");
  assert.equal(M.askLabel("Mateo", false), "The question, in Mateo’s words");
  assert.equal(M.askLabel("Too Canadian?", true), "The move, in this investor’s words");
  assert.equal(M.throughWords(load("robert")), "through 2021\u201326");
  assert.equal(M.throughWords(null), "on real market history");
  assert.equal(M.possessive("Too Canadian?"), null);
  const robert = load("robert"), mateo = load("mateo"), canadian = load("canadian");
  assert.equal(M.namesMove(robert.question, robert), true);          // the run's own words: its own move (40 % NVIDIA)
  assert.equal(M.namesMove(mateo.question, mateo), false);          // a shock question: no move
  assert.equal(M.namesMove(canadian.question, canadian), true);     // +20 % SPY
  assert.equal(M.namesMove("What if I put 20 % in Shopify?", mateo), true);   // a picked move in the box
  assert.equal(M.namesMove("Is my portfolio too risky?", robert), false);      // the investor's own words (live)
});

t("the picker shows what the box says: the investor's own question, a picked move, or the investor's own words", () => {
  const robert = load("robert"), mateo = load("mateo");
  assert.deepEqual(M.stateOf({ text: robert.question, own: robert }), { value: M.OWN, pct: 40, sized: true, from: M.EQUAL });
  assert.deepEqual(M.stateOf({ text: robert.question.replace(/(\d) %/g, `$1${NB}%`), own: robert }), { value: M.OWN, pct: 40, sized: true, from: M.EQUAL });
  assert.deepEqual(M.stateOf({ text: mateo.question, own: mateo }), { value: M.OWN, pct: 20, sized: false, from: M.EQUAL });
  assert.deepEqual(M.stateOf({ text: "What if I put 5 % in Bitcoin?", own: robert }), { value: "BTC-USD", pct: 5, sized: true, from: M.EQUAL });
  assert.deepEqual(M.stateOf({ text: "Is my portfolio too risky?", own: robert, pct: 35 }), { value: M.CUSTOM, pct: 35, sized: false, from: M.EQUAL });
  assert.deepEqual(M.stateOf({ text: "", own: null }), { value: M.OWN, pct: 20, sized: false, from: M.EQUAL });
  /* the own move resized: the same ticker at the new size, in the curated wording */
  assert.deepEqual(M.ownMove(robert), { ticker: "NVDA", pct: 40 });
  assert.equal(M.ownMove(mateo), null);
  assert.deepEqual(M.ownMove(load("canadian")), { ticker: "SPY", pct: 20 });
});

/* ---- the live path is the existing run: the box's words go to POST /api/run through PF.requestBody, on today's mix ---- */
t("live: the composed question is what the existing run path sends, on the investor's own mix and limits", () => {
  const robert = load("robert");
  const q = M.composeQuestion("SHOP.TO", 20);
  const body = PF.requestBody({ ...PF.planFrom(robert, "robert"), q }, null, false);   // exactly sections/replay.js's call
  assert.equal(body.question, "What if I put 20 % in Shopify?");
  assert.equal(body.pilot, "robert");
  assert.deepEqual(body.portfolio, robert.baseline.portfolio);
  assert.equal(body.amount, robert.amount);
});

/* ---- the red gates on every string the picker can show ---- */
t("no advice, verdict or meta words in anything the picker shows; one fiction label stays the hero's", () => {
  const all = M.normalizeMoves(MOVES);
  const texts = [M.TITLE, M.PLACEHOLDER, M.CUSTOM_LABEL, M.HONEST, M.LIVE_LINK, M.SIZE_LABEL, M.SAVED_LABEL,
    ...M.GROUPS.map((g) => g.label), ...M.assetOptions(load("robert")).flatMap((g) => g.options.map((o) => o.text)),
    ...NAMES.flatMap((id) => M.chips(all, id, id === "canadian" ? "Too Canadian?" : id[0].toUpperCase() + id.slice(1)).map((c) => c.label)),
    ...["Robert", "Too Canadian?"].flatMap((nm) => [M.goLabel(nm, true), M.goLabel(nm, false), M.ownLabel(nm), M.wantsLabel(nm)]),
    M.replayWords(load("robert")), M.replayWords(null), M.throughWords(load("robert")),
    ...["Robert", "Too Canadian?"].flatMap((nm) => [M.askLabel(nm, true), M.askLabel(nm, false)]),
    ...NAMES.flatMap((id) => M.fromOptions(load(id), "SHOP.TO").map((o) => o.text)),
    M.overLine(load("robert"), "Robert", "XBB.TO", 40), M.overLine(load("canadian"), "Too Canadian?", "ZST.TO", 20),
    M.composeQuestion("SHOP.TO", 20, "XBB.TO"), M.composeQuestion("NVDA", 40, "XIU.TO"),
    ...ALL.map((tk) => M.hintLine(tk, load("amira"))).filter(Boolean)];
  for (const s of texts) {
    assert.equal(typeof s, "string");
    assert.deepEqual(adviceHits(s), [], s);
    assert.deepEqual(verdictHits(s), [], s);
    assert.deepEqual(metaHits(s), [], s);
    assert.doesNotMatch(s, /recommend|best|top pick|safest|winner|\brank/i, s);
    assert.doesNotMatch(s, /Fictional illustration/, s);       // the hero's note says it once
    assert.doesNotMatch(s, /'/, `${s}: typographic apostrophes only`);
  }
});



/* ---- "taken from" (coordinator, 15:05): every other holding in proportion (the engine scales them by one factor), or one
   holding that gives N % of the money (the engine's op move, added by the ai lane at 16:15; the AI reader's from_ticker) ---- */
t("taken from: your other holdings, in proportion (the default: the engine scales them by one factor), or one of today's holdings, largest first, never the asset", () => {
  const robert = load("robert");
  const opts = M.fromOptions(robert, "SHOP.TO");
  assert.deepEqual(opts.map((o) => [o.value, o.text, o.pct]), [[M.EQUAL, "your other holdings, in proportion", null],
    ["XIU.TO", "Canadian stocks (XIU.TO)", 45], ["XBB.TO", "Canadian bonds (XBB.TO)", 35], ["GLD", "Gold (GLD)", 10], ["ZST.TO", "Short-term bonds (ZST.TO)", 10]]);
  assert.deepEqual(M.fromOptions(robert, "XBB.TO").map((o) => o.value), [M.EQUAL, "XIU.TO", "GLD", "ZST.TO"]);
  assert.deepEqual(M.fromOptions(load("amira"), "NVDA").map((o) => o.value), [M.EQUAL, "XIU.TO", "BTC-USD", "QQQ", "XBB.TO", "SHOP.TO"]);
  assert.deepEqual(M.fromOptions(null, "SHOP.TO").map((o) => o.value), [M.EQUAL]);
  /* holdings the reader edited (lane hold's store key holdings, live): "from" offers what they hold */
  const edited = { pilot: "robert", portfolio: { "XIU.TO": 0.4, "SHOP.TO": 0.6 } };
  assert.deepEqual(M.fromOptions(edited, "NVDA").map((o) => [o.value, o.pct]), [[M.EQUAL, null], ["SHOP.TO", 60], ["XIU.TO", 40]]);
  assert.equal(M.overLine(edited, null, "XIU.TO", 45), `This portfolio holds 40${NB}% in Canadian stocks.`);
  assert.equal(M.overLine(edited, null, "XIU.TO", 40), null);
  assert.equal(M.fromWeight(robert, "XBB.TO"), 35);
  assert.equal(M.fromWeight(robert, "AAPL"), null);
});

t("taken from one holding: N % of the money moves from it into the asset (the engine's op move), and reads back", () => {
  const XBB = "iShares Core Canadian Universe Bond Index ETF";
  assert.equal(M.composeQuestion("SHOP.TO", 20, "XBB.TO"), "What if I move 20 % of my money from my Canadian bonds into Shopify?");
  assert.equal(M.composeQuestion("NVDA", 40, "XIU.TO"), "What if I move 40 % of my money from my Canadian stocks into NVIDIA?");
  assert.equal(M.composeQuestion("SHOP.TO", 20, M.EQUAL), "What if I put 20 % in Shopify?");
  assert.equal(M.composeQuestion("SHOP.TO", 20, null), "What if I put 20 % in Shopify?");
  assert.equal(M.composeQuestion("SHOP.TO", 20, "SHOP.TO"), null);
  assert.equal(M.composeQuestion("SHOP.TO", 20, "META"), null);
  assert.deepEqual(M.parseQuestion(`What if I move 20 % of my money from ${XBB} into Shopify?`), { ticker: "SHOP.TO", pct: 20, from: "XBB.TO" });
  assert.deepEqual(M.parseQuestion("what if I move 30\u00a0% of my money from  iShares Core Canadian Universe Bond Index ETF into nvidia ?"),
    { ticker: "NVDA", pct: 30, from: "XBB.TO" });
  assert.equal(M.parseQuestion("What if I move 20 % of my money from Shopify into Shopify?"), null);
  assert.equal(M.parseQuestion("What if I move 60 % of my money from SPDR Gold Shares into Bitcoin?"), null);
  for (const tk of ALL) for (const from of ["XIU.TO", "GLD", "BTC-USD"]) {
    if (tk === from) continue;
    assert.deepEqual(M.parseQuestion(M.composeQuestion(tk, 7, from)), { ticker: tk, pct: 7, from }, `${tk} from ${from}`);
  }
  const robert = load("robert");
  assert.deepEqual(M.stateOf({ text: `What if I move 20 % of my money from ${XBB} into Shopify?`, own: robert }),
    { value: "SHOP.TO", pct: 20, sized: true, from: "XBB.TO" });
  assert.deepEqual(M.stateOf({ text: "What if I put 5 % in Bitcoin?", own: robert }), { value: "BTC-USD", pct: 5, sized: true, from: M.EQUAL });
  assert.equal(M.stateOf({ text: robert.question, own: robert }).from, M.EQUAL);
  assert.equal(M.namesMove(`What if I move 20 % of my money from ${XBB} into Shopify?`, robert), true);
});

t("a size above what the source holds is allowed, with one quiet line of what it holds (the run's own clarifying question answers)", () => {
  const robert = load("robert"), canadian = load("canadian");
  assert.equal(M.overLine(robert, "Robert", "XBB.TO", 40), `Robert holds 35${NB}% in Canadian bonds.`);
  assert.equal(M.overLine(robert, "Robert", "XBB.TO", 35), null);
  assert.equal(M.overLine(robert, "Robert", M.EQUAL, 50), null);
  assert.equal(M.overLine(canadian, "Too Canadian?", "ZST.TO", 20), `This portfolio holds 10${NB}% in short-term bonds.`);
  assert.equal(M.overLine(robert, "Robert", "AAPL", 20), null);
});

t("taken from in a decision: live writes the move question; static offers it only for a saved move with that 'from'", () => {
  const moves = M.normalizeMoves({ moves: [
    { pilot: "robert", ticker: "NVDA", from: "XIU.TO", weight: 0.4, question: "What if I move 40 % of my money from iShares S&P/TSX 60 Index ETF into NVIDIA?", key: "e000000000000001" },
    { pilot: "robert", ticker: "NVDA", from: "XBB.TO", weight: 0.3, question: "What if I move 30 % of my money from iShares Core Canadian Universe Bond Index ETF into NVIDIA?", key: "e000000000000002" },
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.2, question: "What if I put 20 % in Shopify?", key: "e000000000000003" },
    { pilot: "robert", ticker: "SHOP.TO", from: "SHOP.TO", weight: 0.2, question: "x", key: "e000000000000004" },     // from itself: dropped
    { pilot: "robert", ticker: "SHOP.TO", from: "META", weight: 0.2, question: "x", key: "e000000000000005" },        // not an asset: dropped
  ] });
  assert.deepEqual(moves.map((m) => [m.key, m.from, m.pct]), [["e000000000000001", "XIU.TO", 40], ["e000000000000002", "XBB.TO", 30], ["e000000000000003", null, 20]]);
  assert.deepEqual(M.decide({ mode: "live", investor: "robert", choice: { value: "SHOP.TO", pct: 20, from: "XBB.TO" }, moves: [] }),
    { kind: "write", question: "What if I move 20 % of my money from my Canadian bonds into Shopify?" });
  const saved = M.decide({ mode: "static", investor: "robert", choice: { value: "NVDA", pct: 30, from: "XBB.TO" }, moves });
  assert.equal(saved.kind, "load");
  assert.equal(saved.move.key, "e000000000000002");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "NVDA", pct: 30, from: "XIU.TO" }, moves }).kind, "honest");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "NVDA", pct: 40, from: M.EQUAL }, moves }).kind, "honest");
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "SHOP.TO", pct: 20, from: M.EQUAL }, moves }).move.key, "e000000000000003");
  assert.deepEqual(M.chips(moves, "robert", "Robert").map((c) => c.label),
    ["Robert’s question", `20${NB}% Shopify`, `30${NB}% NVIDIA from Canadian bonds`, `40${NB}% NVIDIA from Canadian stocks`]);
  assert.equal(M.snapFrom(moves, "robert", "NVDA", M.EQUAL), "XBB.TO");      // static: the first saved source of a saved asset
  assert.equal(M.snapFrom(moves, "robert", "NVDA", "XIU.TO"), "XIU.TO");      // a saved source is kept
  assert.equal(M.snapFrom(moves, "robert", "SHOP.TO", M.EQUAL), M.EQUAL);
});

/* a saved run with the investor's own typed limits (data/demo_runs/moves.json 9135784ce30415c6: Robert's own question, "with your
   own limit: technology ≤ 20 %"): its words are the own question's, so the run on screen decides which chip is pressed */
t("a saved move with typed limits: its label on the chip, never reached by a plain pick, pressed by the run on screen", () => {
  const robertQ = load("robert").question;
  const list = M.normalizeMoves({ moves: [
    { pilot: "robert", default: true, ticker: "NVDA", weight: 0.4, question: robertQ, key: "4f31fbfe427a6d7e" },
    { pilot: "robert", ticker: "NVDA", weight: 0.4, question: robertQ, key: "9135784ce30415c6",
      label: "with your own limit: technology ≤ 20 %", limits: { sector_caps: { "Information Technology": 0.2 } } },
    { pilot: "robert", ticker: "SHOP.TO", weight: 0.2, question: "What if I put 20 % in Shopify?", key: "1a61782cadb4203b" },
  ] });
  const lim = list.find((m) => m.key === "9135784ce30415c6");
  assert.equal(lim.label, "with your own limit: technology ≤ 20 %");
  assert.deepEqual(lim.limits, { sector_caps: { "Information Technology": 0.2 } });
  const cs = M.chips(list, "robert", "Robert");
  assert.deepEqual(cs.map((c) => c.label), ["Robert’s question", `20${NB}% Shopify`, `40${NB}% NVIDIA, with your own limit: technology ≤ 20${NB}%`]);
  /* a plain pick never lands on a run with limits the reader did not set */
  assert.equal(M.matchSaved(list, "robert", "NVDA", 40, M.EQUAL), null);
  assert.equal(M.decide({ mode: "static", investor: "robert", choice: { value: "NVDA", pct: 40, from: M.EQUAL }, moves: list }).kind, "honest");
  assert.equal(M.snapPct(list, "robert", "NVDA", 25, M.EQUAL), 25);
  /* pressed: the run on screen (the static build's run_id is the key's first 12 hex), else the words */
  const own = { run_id: "4f31fbfe427a", question: robertQ };
  const box = M.stateOf({ text: robertQ, own: load("robert") });
  assert.deepEqual(M.pressedOf(cs, { run_id: "9135784ce304", question: robertQ }, box), [false, false, true]);
  assert.deepEqual(M.pressedOf(cs, own, box), [true, false, false]);
  assert.deepEqual(M.pressedOf(cs, { run_id: "1a61782cadb4" }, M.stateOf({ text: "What if I put 20 % in Shopify?", own: load("robert") })), [false, true, false]);
  assert.deepEqual(M.pressedOf(cs, { question: "What if I put 20 % in Shopify?" }, M.stateOf({ text: "What if I put 20 % in Shopify?", own: load("robert") })), [false, true, false]);
  for (const c of cs) assert.deepEqual(adviceHits(c.label), [], c.label);
});

t("NO_MOVE: the live app's one chip that replays the mix as it is (the lead 19:15: 'run a test with the portfolio alone')", () => {
  assert.equal(M.NO_MOVE.label, "Your mix as it is");
  assert.match(M.NO_MOVE.question, /inside my limits/, "the reader's fit words (agents/scenario.py _FIT)");
  assert.equal(M.parseQuestion(M.NO_MOVE.question), null, "names no move");
  assert.doesNotMatch(M.NO_MOVE.question, /\d/, "no figure the page did not compute");
  assert.deepEqual(adviceHits(M.NO_MOVE.label + " " + M.NO_MOVE.question, []), []);
});

console.log(`web_picker_test: ${n} groups passed`);
