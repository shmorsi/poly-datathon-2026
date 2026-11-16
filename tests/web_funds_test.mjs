// Lane funds: the pure helpers of the fund drawer (web/lib/fundpage.js). A synthetic Result in the shapes result_extras.funds and
// result_extras.funds_private write (fictional company names: no licensed row is ever committed, red gate 8). Every number the
// drawer shows is one of these keys; the gate's own rules (scripts/gate_rules.mjs) read every string it can show.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import * as M from "../web/lib/fundpage.js";
import * as SB from "../web/lib/sharebar.js";
import { adviceHits, metaHits } from "../scripts/gate_rules.mjs";

const PF = createRequire(import.meta.url)("../web/lib.js");
let n = 0;
const t = (name, fn) => { try { fn(); } catch (e) { e.message = `${name}: ${e.message}`; throw e; } n += 1; };
const NB = " ";

const fund = (ticker, name, asset_class, extra) => ({ ticker, name, issuer: "Example Issuer", asset_class, holds: "Broad market (Canada)",
  page: `https://issuer.example/${ticker}`, date: "2026-11-12", dates: { positions: "2026-11-12", sectors: "2026-11-12", countries: "2026-11-12" },
  listed: { positions: 0, sectors: 0, countries: 0 }, coverage: null, sectors: [], countries: [], later: null, top10: null, concentrated: false,
  today: null, after: null, ...extra });
function result({ live = false, moved = true } = {}) {
  const r = {
    status: "ok", as_of: "2026-11-12", amount: 600000, profile: { name: "Robert" },
    portfolio: { NVDA: 0.4, "XIU.TO": 0.27, "XBB.TO": 0.21, GLD: 0.12 }, baseline: { portfolio: { "XIU.TO": 0.45, "XBB.TO": 0.35, GLD: 0.2 } },
    checks: [{ rule: "single_stock", status: "fail", tier: "soft", value: 0.4, limit: 0.1, holding: "NVDA" },
      { rule: "sector", status: "fail", tier: "soft", value: 0.425947, limit: 0.35, holding: "NVDA" }],
    baseline_checks: null,
    funds: { as_of: "2026-11-12", mode: "lookthrough", newest: "2026-11-12", funds: [
      fund("XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", { listed: { positions: 26, sectors: 11, countries: 3 }, coverage: 0.7786,
        sectors: [{ name: "Financials", share: 0.4123 }, { name: "Energy", share: 0.1665 }], countries: [{ name: "CAN", share: 0.9769 }, { name: "USA", share: 0.017 }],
        top10: { count: 10, share: 0.4731 }, concentrated: true, today: { share: 0.45, dollars: 270000 }, after: { share: 0.27, dollars: 162000 } }),
      fund("XBB.TO", "iShares Core Canadian Universe Bond Index ETF", "etf_bond", { holds: "Bonds (Canada aggregate)", listed: { positions: 0, sectors: 1, countries: 2 },
        dates: { positions: null, sectors: "2026-11-12", countries: "2026-11-12" },
        sectors: [{ name: "Bonds", share: 1 }], countries: [{ name: "CAN", share: 0.9621 }], today: { share: 0.35, dollars: 210000 }, after: { share: 0.21, dollars: 126000 } }),
      fund("GLD", "SPDR Gold Shares", "etf_commodity", { holds: "Gold", date: null, dates: { positions: null, sectors: null, countries: null }, later: "2026-11-14",
        today: { share: 0.2, dollars: 120000 }, after: { share: 0.12, dollars: 72000 } }),
    ], sides: {
      today: { in_funds: { share: 1, dollars: 600000 }, direct: [], unlisted: { share: 0.0996, dollars: 59778 }, mode: "lookthrough",
        sectors: [{ name: "Financials", share: 0.1855, dollars: 111321 }], countries: [{ name: "CAN", share: 0.8763, dollars: 525805 }, { name: "GLOBAL", share: 0.2, dollars: 120000 }] },
      after: moved ? { in_funds: { share: 0.6, dollars: 360000 }, direct: [{ ticker: "NVDA", name: "NVIDIA", share: 0.4, dollars: 240000, total: { share: 0.4, dollars: 240000 } }],
        unlisted: { share: 0.0598, dollars: 35867 }, mode: "lookthrough", sectors: [{ name: "Information Technology", share: 0.425947, dollars: 255568 }],
        countries: [{ name: "CAN", share: 0.5258, dollars: 315483 }, { name: "USA", share: 0.4106, dollars: 246370 }] } : null } },
  };
  r.baseline.checks = [{ rule: "single_stock", status: "pass", tier: "soft", value: 0.04311, limit: 0.1, holding: null },
    { rule: "sector", status: "pass", tier: "soft", value: 0.1855, limit: 0.35, holding: null }];
  delete r.baseline_checks;
  if (!moved) { r.portfolio = r.baseline.portfolio; r.funds.funds.forEach((f) => { f.after = null; }); }
  if (live) r.funds_private = { as_of: "2026-11-12", top: 10, funds: { "XIU.TO": { date: "2026-11-12", listed: 26, coverage: 0.7786, top: [
    { name: "Northwind Bank", ticker: null, share: 0.0958, today: 25866, after: 15520 }, { name: "Example Rail", ticker: null, share: 0.0694, today: 18738, after: 11243 }] } },
  owning: { today: { top: [{ name: "Northwind Bank", ticker: null, dollars: 25866, direct: 0, share: 0.04311, funds: ["XIU.TO"], inside: [{ fund: "XIU.TO", share: 0.04311, dollars: 25866 }] }],
    rest: { count: 25, share: 0.6, dollars: 360000 }, named: { count: 26, share: 0.65, dollars: 385866 } },
  after: { top: [{ name: "NVIDIA", ticker: "NVDA", dollars: 246000, direct: 240000, share: 0.41, funds: ["XIU.TO"], inside: [{ fund: "XIU.TO", share: 0.01, dollars: 6000 }] },
    { name: "Northwind Bank", ticker: null, dollars: 15520, direct: 0, share: 0.025867, funds: ["XIU.TO"], inside: [{ fund: "XIU.TO", share: 0.025867, dollars: 15520 }] }],
    rest: { count: 24, share: 0.2, dollars: 120000 }, named: { count: 26, share: 0.6, dollars: 360000 } } } };
  return r;
}
function strings(o, out = []) {
  if (typeof o === "string") out.push(o);
  else if (Array.isArray(o)) o.forEach((x) => strings(x, out));
  else if (o && typeof o === "object") Object.values(o).forEach((x) => strings(x, out));
  return out;
}

t("the drawer: What you own first, then one tab per fund held; the side opens with the move when there is one", () => {
  const d = M.drawerModel(result(), PF, "XIU.TO", null);
  assert.deepEqual(d.tabs.map((x) => x.id), ["owning", "XIU.TO", "XBB.TO", "GLD"]);
  assert.equal(d.tabs[0].label, "What you own");
  assert.equal(d.view, "XIU.TO"); assert.equal(d.side, "after"); assert.equal(d.live, false);
  assert.deepEqual(d.sides.map((s) => s.label), ["Today", "With the move"]);
  assert.equal(M.drawerModel(result(), PF, "SPY", "today").view, "owning");        // a fund not held: the overview
  assert.equal(M.drawerModel(result({ moved: false }), PF, "owning", "after").side, "today");
  assert.deepEqual(M.drawerModel(result({ moved: false }), PF, "owning", null).sides.map((s) => s.id), ["today"]);
  assert.equal(M.drawerModel({ status: "ok" }, PF, "owning", null), null);         // no funds key: the caller's own panel
});

t("a fund: its name, issuer, what it holds, at most six numbers, the date and 'Nothing dated later is used.'", () => {
  const p = M.fundPage(result(), PF, "XIU.TO", "after");
  assert.equal(p.name, "iShares S&P/TSX 60 Index ETF");
  assert.equal(p.about, "Run by Example Issuer. It holds Canadian stocks: broad market (Canada).");
  assert.ok(p.stats.length <= 6);
  assert.deepEqual(p.stats.map((s) => s.k), ["Your money, with the move", "10 largest companies", "Positions listed", "Largest industry", "Largest country", "Holdings dated"]);
  assert.deepEqual(p.stats.map((s) => s.v), ["$162,000", `47.3${NB}%`, "26", `41.2${NB}%`, `97.7${NB}%`, `12${NB}Nov${NB}2026`]);
  assert.equal(p.stats[0].sub, `27${NB}% of $600,000; today $270,000`);
  assert.equal(p.stats[3].sub, "Financials"); assert.equal(p.stats[4].sub, "Canada");
  assert.equal(p.datedLine, `Holdings dated 12${NB}Nov${NB}2026, the replay’s last day. Nothing dated later is used.`);
  assert.equal(p.concentration, `XIU.TO is concentrated: its 10 largest companies are 47.3${NB}% of the fund.`);
  assert.equal(M.concentrationLine(PF, "SPY", { count: 10, share: 0.37 }, false), `SPY’s 10 largest companies are 37.0${NB}% of the fund.`);
  assert.equal(p.stats.find((s) => s.k === "Your money, with the move").v, "$162,000");
  assert.equal(M.fundPage(result(), PF, "XIU.TO", "today").stats[0].sub, `45${NB}% of $600,000; with the move $162,000`);
  const older = result();
  older.funds.funds[0].dates.sectors = "2026-10-31";                       // QQQ and ESGV publish their splits later
  assert.equal(M.fundPage(older, PF, "XIU.TO", "after").datedLine,
    `Holdings dated 12${NB}Nov${NB}2026, the replay’s last day. Its industry split is dated 31${NB}Oct${NB}2026. Nothing dated later is used.`);
  assert.match(M.fundPage(result(), PF, "XBB.TO", "after").datedLine, /^The fund file dated 12/);
});

t("static: no company list, one honest line and the issuer's page; bonds and gold say why they have none", () => {
  const p = M.fundPage(result(), PF, "XIU.TO", "after");
  assert.equal(p.top, null);
  assert.deepEqual(p.licence, { line: "The issuer’s licence does not let us republish its holdings list.", link: "See them on the issuer’s page →",
    href: "https://issuer.example/XIU.TO" });
  const b = M.fundPage(result(), PF, "XBB.TO", "after");
  assert.equal(b.licence, null); assert.match(b.note, /^A bond fund/); assert.deepEqual(b.sectors, []);
  assert.equal(b.countries[0].name, "Canada");
  const g = M.fundPage(result(), PF, "GLD", "today");
  assert.match(g.note, /gold bullion/); assert.equal(g.dateText, null);
  assert.equal(g.datedLine, `The issuer’s file here is dated 14${NB}Nov${NB}2026, after the replay’s last day (12${NB}Nov${NB}2026), so it is not used. Nothing dated later is used.`);
});

t("live: the top holdings, and the investor's dollars in each on the chosen side", () => {
  const p = M.fundPage(result({ live: true }), PF, "XIU.TO", "after");
  assert.equal(p.licence, null);
  assert.deepEqual(p.top.map((x) => [x.rank, x.name, x.shareText, x.yoursText]), [[1, "Northwind Bank", `9.6${NB}%`, `≈${NB}$15,520`], [2, "Example Rail", `6.9${NB}%`, `≈${NB}$11,243`]]);
  assert.equal(M.fundPage(result({ live: true }), PF, "XIU.TO", "today").top[0].yoursText, `≈${NB}$25,866`);
  assert.match(p.topNote, /^Your dollars = \$600,000 × this fund’s share of your money × the company’s weight in the fund/);
});

t("what you own: the biggest company and industry against the limits, in the page's status words", () => {
  const o = M.owningModel(result(), PF, "after");
  assert.equal(o.title, "What Robert ends up owning");
  assert.deepEqual(o.limits.map((l) => [l.status.word, l.name, l.line]), [
    ["Caution", "NVIDIA", `40.0${NB}% of the money, against a 10${NB}% limit for one company.`],
    ["Caution", "Information Technology", `42.6${NB}% of the money, against a 35${NB}% limit for one industry.`]]);
  const today = M.owningModel(result(), PF, "today");
  assert.equal(today.title, "What Robert owns today");
  assert.deepEqual(today.limits.map((l) => [l.status.word, l.name]), [["Inside", "A company inside your funds"], ["Inside", "Financials"]]);
  assert.equal(M.owningModel(result({ live: true }), PF, "today").limits[0].name, "Northwind Bank");   // the same share, named live
});

t("what you own, static: direct lines only and the licence line; live: the funds' companies too, NVIDIA counted twice", () => {
  const s = M.owningModel(result(), PF, "after");
  assert.deepEqual(s.companies.map((c) => [c.name, c.how, c.dollarsText]), [["NVIDIA", "You own it directly", "$240,000"]]);
  assert.equal(s.licence, M.STATIC_OWNING); assert.equal(s.live, false); assert.equal(s.unlisted.dollarsText, "$35,867");
  assert.deepEqual(s.funds.map((f) => [f.ticker, f.dollarsText]), [["XIU.TO", "$162,000"], ["XBB.TO", "$126,000"], ["GLD", "$72,000"]]);
  assert.deepEqual(s.sectors.map((x) => [x.name, x.dollarsText]), [["Information Technology", "$255,568"]]);
  assert.deepEqual(s.countries.map((x) => x.name), ["Canada", "United States"]);
  const l = M.owningModel(result({ live: true }), PF, "after");
  assert.equal(l.live, true); assert.equal(l.licence, null);
  assert.deepEqual(l.companies[0], { name: "NVIDIA", ticker: "NVDA", how: `40${NB}% directly, plus 1${NB}% inside XIU.TO`, dollars: 246000,
    dollarsText: "$246,000", share: 0.41, shareText: `41${NB}%` });
  assert.equal(l.companies[1].how, "Inside XIU.TO");
  assert.deepEqual([l.rest.count, l.rest.dollarsText], [24, "$120,000"]);
  const twice = result();
  twice.funds.sides.after.direct[0].total = { share: 0.412, dollars: 247200 };
  assert.equal(M.owningModel(twice, PF, "after").companies[0].how, `40${NB}% directly, 41.2${NB}% counting your funds`);
});

t("no advice word, no meta dots and no licensed name in anything the drawer can show", () => {
  const all = [];
  for (const live of [false, true]) for (const side of ["today", "after"]) for (const what of ["owning", "XIU.TO", "XBB.TO", "GLD"])
    all.push(...strings(M.drawerModel(result({ live }), PF, what, side)));
  for (const s of new Set(all)) {
    assert.deepEqual(adviceHits(s), [], s);
    assert.deepEqual(metaHits(s), [], s);
  }
  assert.ok(all.includes("Fictional illustration, not a recommendation."));
});

t("the share bar: largest first, widths exactly the shares, five named and the rest one Other (n), one order for both rows", () => {
  const items = (xs) => xs.map(([key, share, dollars]) => ({ key, name: key, share, dollars }));
  const m = SB.sharebarModel([{ id: "today", label: "Today", items: items([["A", 0.1, 60], ["B", 0.3, 180], ["C", 0.05, 30], ["D", 0.02, 12], ["E", 0.01, 6], ["F", 0.04, 24], ["G", 0.005, 3]]) },
    { id: "after", label: "With the move", items: [...items([["A", 0.06, 36], ["B", 0.18, 108]]), { key: "NV", name: "NVIDIA", share: 0.4, dollars: 240, move: true }] }]);
  assert.deepEqual(m.keys, ["NV", "B", "A", "C", "F"]);                 // by the largest share on any row
  const today = m.rows[0];
  assert.deepEqual(today.segs.map((g) => [g.key, Number(g.share.toFixed(6))]), [["B", 0.3], ["A", 0.1], ["C", 0.05], ["F", 0.04], [SB.OTHER, 0.035]]);
  assert.equal(today.segs[4].name, "Other (3)"); assert.equal(today.segs[4].dollars, 21);
  assert.deepEqual(today.segs.map((g) => Number(g.x0.toFixed(3))), [0, 0.3, 0.4, 0.45, 0.49]);       // each starts where the last ends
  const after = m.rows[1];
  assert.deepEqual(after.segs.map((g) => [g.key, g.move]), [["NV", true], ["B", false], ["A", false]]);
  assert.equal(after.segs[0].tone, 0); assert.equal(today.segs[0].tone, 1);           // B keeps its tone on both rows
  assert.equal(m.legend.length, 6); assert.equal(m.legend[5].name, "Other (3)");
  assert.deepEqual(m.legend[0].values, [null, { share: 0.4, dollars: 240 }]);
  assert.equal(SB.segWords(after.segs[0], PF.fmt), `NVIDIA: 40.0${NB}% of your money, $240`);
  assert.equal(SB.segWords({ name: "Financials", share: 0.4123, dollars: null }, PF.fmt, "of the fund"), `Financials: 41.2${NB}% of the fund`);
});

t("the drawer's share bars: today vs with the move per breakdown; static companies are the direct lines only", () => {
  const o = M.owningModel(result(), PF, "after");
  assert.deepEqual(o.breakdown.sectors.map((r) => r.label), ["Today", "With the move"]);
  assert.deepEqual(o.breakdown.companies.map((r) => r.items.map((x) => x.key)), [[], ["NVDA"]]);
  assert.equal(o.breakdown.companies[1].items[0].move, true);                        // the move in magenta
  assert.deepEqual(o.breakdown.funds[0].items.map((x) => [x.name, x.share]), [["XIU.TO (Canadian stocks)", 0.45], ["XBB.TO (Canadian bonds)", 0.35], ["GLD (Gold)", 0.2]]);
  const l = M.owningModel(result({ live: true }), PF, "after");
  assert.deepEqual(l.breakdown.companies[1].items.map((x) => x.name), ["NVIDIA", "Northwind Bank", "24 more companies"]);
  const grouped = SB.sharebarModel(l.breakdown.companies);              // the rest is never ranked as one company
  assert.deepEqual(grouped.keys, ["NVDA", "Northwind Bank"]);
  assert.equal(grouped.rows[1].segs.at(-1).name, "Other (24)"); assert.equal(grouped.legend.at(-1).name, "Other (25)");
  const p = M.fundPage(result(), PF, "XIU.TO", "after");
  assert.deepEqual(p.split.sectors[0].items.map((x) => x.key), ["Financials", "Energy"]);
  assert.deepEqual(p.split.countries[0].items.map((x) => x.name), ["Canada", "United States"]);
});

t("a run saved without the funds key still opens the drawer from its own keys (weights, amount x weight, the look-through)", () => {
  const r = result(); delete r.funds;
  r.lookthrough = { today: { mode: "lookthrough", sectors: { Financials: 0.1855 }, countries: { CAN: 0.8763, GLOBAL: 0.2 }, coverage: { "XIU.TO": 0.7786 }, snapshot: { "XIU.TO": "2026-11-12" } },
    after: { mode: "lookthrough", sectors: { "Information Technology": 0.425947 }, countries: { CAN: 0.5258 }, stocks: { NVDA: { direct: 0.4, total: 0.4 } } } };
  const d = M.drawerModel(r, PF, "XIU.TO", null);
  assert.deepEqual(d.tabs.map((x) => x.id), ["owning", "XIU.TO", "XBB.TO", "GLD"]);
  assert.equal(d.page.name, "iShares S&P/TSX 60 Index ETF"); assert.equal(d.page.stats[0].v, "$162,000");
  assert.match(d.page.note, /not its own industry and country split/); assert.equal(d.page.licence, null);
  const o = M.owningModel(r, PF, "after");
  assert.deepEqual(o.companies.map((c) => [c.name, c.dollarsText]), [["NVIDIA", "$240,000"]]);
  assert.deepEqual(o.sectors.map((x) => [x.name, x.dollarsText]), [["Information Technology", "$255,568"]]);
  assert.equal(o.limits[0].name, "NVIDIA");
});

console.log(`web_funds_test: ${n} groups passed`);
