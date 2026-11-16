/* EPICENTRE Replay, lane funds: each fund as a fund page shows it (the lead: "put each ETF like TradingView: break it down, its
   holdings based on today, to see exactly what stocks or stuff the person would end up with"). Pure: no DOM, no network; P is the
   page's PF (web/lib.js: fmt), passed in. Every number is a Result key: result.funds (public, fund-level aggregates only) and,
   in the live app only, result.funds_private (the companies inside each fund with the investor's dollars in each, computed by
   result_extras.funds_private; red gate 8: never in a saved run or the static build).
   drawerModel(r, P, what, side)  the drawer: its tabs (What you own, then one per fund), the side (today | after) and the view
   fundPage(r, P, ticker, side)   one fund: name, ticker, issuer, what it holds, the holdings date ("Nothing dated later is
                                  used."), its sectors and countries, your money in it, its top positions (live) or one line
   owningModel(r, P, side)        what the investor ends up owning: by company (direct lines, plus the funds' companies live),
                                  by fund, by industry and by country, in dollars
   Tests: tests/web_funds_test.mjs. */
import { plainLabel, fundName, kindOf, countryName } from "./funds.js";
import { shownStatus } from "./status.js";
import { mixes } from "./hold.js";

export const STATIC_LINE = "The issuer’s licence does not let us republish its holdings list.";
export const STATIC_LINK = "See them on the issuer’s page →";
export const STATIC_OWNING = "The issuers’ licences do not let us republish their holdings lists. Open a fund to see its industries, its countries and its issuer’s page.";
export const DATED = "Nothing dated later is used.";
export const EXPOSURE = "Exposure only: the fund’s contents as of that date. Never a return or a forecast.";
export const SECTOR_NOTE = "Industries count only the money in company shares; bonds, gold and cash have none.";
export const OWNING_TAB = "What you own";
export const TOP_TITLE = "Top holdings, and your money in each";
export const FICTION = "Fictional illustration, not a recommendation.";
const BARS = 8;                                   // the largest industries and countries drawn; the rest stay in the issuer's file

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const fmt = (P, k, x) => (P && P.fmt && typeof P.fmt[k] === "function" ? P.fmt[k](x) : "");
const https = (u) => (typeof u === "string" && /^https:\/\/[^\s"'<>]+$/.test(u) ? u : null);

/* "Robert"; a profile whose name is not a person's ("Too Canadian?") reads "this portfolio" (lane hold's rule) */
export function whoOf(r) {
  const name = str(obj(obj(r) && r.profile) && r.profile.name);
  return name && /^[A-Z][a-z]+$/.test(name) ? name : null;
}
/* the run's funds key; a run saved before it existed (or a dev preview's old run) gets the same shape from its own keys:
   the weights, amount x weight, the look-through's sectors, countries, coverage and holdings dates; no per-fund split */
const ISSUERS = { "XIU.TO": "BlackRock Canada (iShares)", "XBB.TO": "BlackRock Canada (iShares)", AGG: "BlackRock (iShares)", TLT: "BlackRock (iShares)",
  SPY: "State Street Global Advisors (SPDR)", GLD: "State Street Global Advisors (SPDR)", QQQ: "Invesco", ESGV: "Vanguard",
  "ZST.TO": "BMO Global Asset Management" };
const ASSET = { "XBB.TO": "etf_bond", "ZST.TO": "etf_bond", AGG: "etf_bond", TLT: "etf_bond", GLD: "etf_commodity" };
const built = new WeakMap();
function fromKeys(r) {
  const m = mixes(r, null);
  if (!m) return null;
  const amount = isNum(r.amount) ? r.amount : null, lt = obj(r.lookthrough) || {};
  const pay = (w) => (isNum(w) && w > 0 ? { share: w, dollars: amount === null ? null : Math.round(amount * w) } : null);
  const held = [...new Set([...Object.keys(m.today), ...Object.keys(m.after || {})])].filter((tk) => kindOf(tk) === "fund")
    .sort((a, b) => ((m.today[b] || 0) - (m.today[a] || 0)) || (((m.after || {})[b] || 0) - ((m.after || {})[a] || 0)) || (a < b ? -1 : 1));
  const snap = (tk) => str((obj(obj(lt.today) && lt.today.snapshot) || {})[tk]) || str((obj(obj(lt.after) && lt.after.snapshot) || {})[tk]);
  const cov = (tk) => { const c = (obj(obj(lt.today) && lt.today.coverage) || {})[tk]; return isNum(c) ? c : null; };
  const funds = held.map((tk) => ({ ticker: tk, name: fundName(tk), issuer: ISSUERS[tk] || null, asset_class: ASSET[tk] || "etf_equity",
    holds: null, page: null, date: snap(tk), dates: { positions: snap(tk), sectors: null, countries: null }, listed: { positions: 0, sectors: 0, countries: 0 },
    coverage: cov(tk), sectors: [], countries: [], later: null, top10: null, concentrated: false, today: pay(m.today[tk]), after: m.after ? pay(m.after[tk]) : null,
    fromKeys: true }));
  const side = (w, look) => w && {
    in_funds: pay(Object.entries(w).filter(([tk]) => kindOf(tk) === "fund").reduce((a, [, v]) => a + v, 0)),
    direct: Object.entries(w).filter(([tk, v]) => kindOf(tk) !== "fund" && isNum(v) && v > 0).sort((a, b) => b[1] - a[1])
      .map(([tk, v]) => ({ ticker: tk, name: fundName(tk), ...pay(v), total: pay(isNum(((obj(obj(look) && look.stocks) || {})[tk] || {}).total) ? look.stocks[tk].total : v) })),
    sectors: Object.entries(obj(obj(look) && look.sectors) || {}).filter(([, v]) => isNum(v) && v > 0).sort((a, b) => b[1] - a[1]).map(([name, v]) => ({ name, ...pay(v) })),
    countries: Object.entries(obj(obj(look) && look.countries) || {}).filter(([, v]) => isNum(v) && v > 0).sort((a, b) => b[1] - a[1]).map(([name, v]) => ({ name, ...pay(v) })),
    unlisted: null, mode: str(obj(look) && look.mode) };
  return { as_of: str(r.as_of), mode: str(obj(lt.today) && lt.today.mode) || "direct", funds,
    sides: { today: side(m.today, lt.today), after: m.after ? side(m.after, lt.after) : null }, fromKeys: true };
}
export const fundsOf = (r) => {
  const own = obj(obj(r) && r.funds);
  if (own || !obj(r)) return own;
  if (!built.has(r)) built.set(r, fromKeys(r));
  return built.get(r);
};
export const privateOf = (r) => obj(obj(r) && r.funds_private);
const moved = (f) => !!obj(obj(f && f.sides) && f.sides.after);
export const sidesOf = (r) => { const f = fundsOf(r); return f && moved(f) ? ["today", "after"] : ["today"]; };
export const SIDE_WORDS = Object.freeze({ today: "Today", after: "With the move" });
/* the side a view opens on: "with the move" when there is one (what the person would end up with), else today */
export const defaultSide = (r) => (sidesOf(r).includes("after") ? "after" : "today");
const sideOk = (r, side) => (sidesOf(r).includes(side) ? side : defaultSide(r));

const money = (P, m) => (obj(m) && isNum(m.dollars) ? { dollars: m.dollars, dollarsText: fmt(P, "money", m.dollars),
  share: isNum(m.share) ? m.share : null, shareText: isNum(m.share) ? fmt(P, "share", m.share) : "" } : null);
const bars = (P, items, name) => arr(items).map(obj).filter((x) => x && str(x.name) && isNum(x.share) && x.share > 0)
  .slice(0, BARS).map((x) => ({ key: x.name, name: name(x.name), share: x.share, shareText: fmt(P, "pct", x.share),
    ...(isNum(x.dollars) ? { dollars: x.dollars, dollarsText: fmt(P, "money", x.dollars) } : {}) }));
const country = (code) => countryName(code);
const coin = (tk) => kindOf(tk) === "crypto";
/* one share-bar row (web/lib/sharebar.js) from a list of {name, share, dollars?}: every item, the bar keeps the five largest */
const barRow = (id, label, items, name, move) => ({ id, label, items: arr(items).map(obj).filter((x) => x && str(x.name) && isNum(x.share))
  .map((x) => ({ key: x.name, name: name(x.name), share: x.share, dollars: isNum(x.dollars) ? x.dollars : null, move: !!move && x.name === move,
    ...(x.other ? { other: true, count: x.count } : {}) })) });
/* a label inside a sentence: "short-term bonds", "gold"; a proper name or an acronym first stays ("Canadian stocks", "US bonds") */
const lc = (t) => (/^(Canadian|US|U\.S\.|ESG)\b/.test(String(t)) ? String(t) : String(t).charAt(0).toLowerCase() + String(t).slice(1));
const KIND = { etf_equity: "stocks", etf_bond: "bonds", etf_commodity: "gold" };

/* the holdings date as a sentence: on the replay's last day, before it, or a file dated after it that is not used */
function datedLines(P, f, asOf) {
  const end = fmt(P, "date", asOf);
  if (str(f.date)) {
    const d = fmt(P, "date", f.date), what = obj(f.dates) && str(f.dates.positions) ? "Holdings" : "The fund file";
    const sec = obj(f.dates) && str(f.dates.sectors) && f.dates.sectors !== f.date ? ` Its industry split is dated ${fmt(P, "date", f.dates.sectors)}.` : "";
    return { dateText: d, line: `${what} dated ${d}${f.date === asOf ? ", the replay’s last day." : `, before the replay’s last day (${end}).`}${sec} ${DATED}` };
  }
  if (str(f.later)) return { dateText: null, line: `The issuer’s file here is dated ${fmt(P, "date", f.later)}, after the replay’s last day (${end}), so it is not used. ${DATED}` };
  return { dateText: null, line: `No issuer file dated on or before ${end} for this fund. ${DATED}` };
}

/* ---- one fund: one screen, at most six big numbers; the industries and countries behind one button ---- */
export function concentrationLine(P, ticker, top10, concentrated) {
  if (!obj(top10) || !isNum(top10.share) || !isNum(top10.count) || top10.count < 1) return null;
  const n = top10.count === 1 ? "largest company is" : `${top10.count} largest companies are`;
  return concentrated ? `${ticker} is concentrated: its ${n} ${fmt(P, "pct", top10.share)} of the fund.`
    : `${ticker}’s ${n} ${fmt(P, "pct", top10.share)} of the fund.`;
}
export function fundPage(r, P, ticker, side) {
  const F = fundsOf(r), f = F && arr(F.funds).map(obj).find((x) => x && x.ticker === ticker);
  if (!f) return null;
  side = sideOk(r, side);
  const asOf = str(F.as_of) || str(r.as_of), amountText = isNum(r.amount) ? fmt(P, "money", r.amount) : "";
  const kind = KIND[f.asset_class] || "stocks", listed = obj(f.listed) || {}, positions = isNum(listed.positions) ? listed.positions : 0;
  const d = datedLines(P, f, asOf), mine = { today: money(P, f.today), after: money(P, f.after) };
  const sectors = kind === "stocks" ? bars(P, f.sectors, (n) => n) : [], countries = bars(P, f.countries, country);
  const other = sidesOf(r).find((s) => s !== side), o = other && mine[other];
  const stats = [
    { k: side === "after" ? "Your money, with the move" : "Your money today", v: mine[side] ? mine[side].dollarsText : fmt(P, "money", 0),
      sub: mine[side] ? `${mine[side].shareText} of ${amountText}${o ? `; ${other === "today" ? "today" : "with the move"} ${o.dollarsText}` : ""}` : "Not in this mix", side: true },
    obj(f.top10) && isNum(f.top10.share) ? { k: `${f.top10.count === 1 ? "Largest company" : `${f.top10.count} largest companies`}`, v: fmt(P, "pct", f.top10.share), sub: "of the fund" } : null,
    positions ? { k: "Positions listed", v: String(positions), sub: isNum(f.coverage) ? `${fmt(P, "pct", f.coverage)} of the fund` : null } : null,
    sectors.length ? { k: "Largest industry", v: sectors[0].shareText, sub: sectors[0].name } : null,
    countries.length ? { k: "Largest country", v: countries[0].shareText, sub: countries[0].name } : null,
    { k: "Holdings dated", v: d.dateText || "Not used", sub: DATED, date: true },
  ].filter(Boolean).slice(0, 6);
  const priv = privateOf(r), mineP = obj(obj(priv && priv.funds) && priv.funds[ticker]);
  const top = mineP ? arr(mineP.top).map(obj).filter((x) => x && str(x.name) && isNum(x.share)).map((x, i) => ({
    rank: i + 1, name: x.name, ticker: str(x.ticker), share: x.share, shareText: fmt(P, "pct", x.share),
    yours: isNum(x[side]) ? x[side] : null, yoursText: isNum(x[side]) ? `≈ ${fmt(P, "money", x[side])}` : "–" })) : null;
  const url = https(f.page);
  const note = kind === "bonds" ? "A bond fund: it lends to governments and companies, so it has no company shares to list."
    : kind === "gold" ? "One asset: gold bullion held by the fund. There are no companies inside it."
    : f.fromKeys ? "This saved run carries the fund’s weight and dates, not its own industry and country split." : null;
  return {
    ticker, name: str(f.name) || ticker, label: plainLabel(ticker), issuer: str(f.issuer), holds: str(f.holds), kind, url, side,
    sideWord: SIDE_WORDS[side], dateText: d.dateText, datedLine: d.line, stats, note, positions, mine, inMix: !!mine[side],
    datedNote: !d.dateText || /industry split/.test(d.line) ? d.line : null,     // the readout says the rest
    about: [str(f.issuer) ? `Run by ${f.issuer}.` : null,
      `It holds ${lc(plainLabel(ticker))}${str(f.holds) && lc(f.holds) !== lc(plainLabel(ticker)) ? `: ${lc(f.holds)}` : ""}.`].filter(Boolean).join(" "),
    concentration: concentrationLine(P, ticker, f.top10, !!f.concentrated), concentrated: !!f.concentrated,
    sectors, countries, top: top && top.length ? top : null, topTitle: TOP_TITLE,
    topNote: top && top.length ? `Your dollars = ${amountText} × this fund’s share of your money × the company’s weight in the fund (${SIDE_WORDS[side].toLowerCase()}).` : null,
    licence: !(top && top.length) && kind === "stocks" && positions ? { line: STATIC_LINE, link: STATIC_LINK, href: url } : null,
    exposure: EXPOSURE, more: sectors.length || countries.length ? "Show the breakdown" : null,
    split: { sectors: kind === "stocks" && arr(f.sectors).length ? [barRow("fund", "", f.sectors, (n) => n)] : [],
      countries: arr(f.countries).length ? [barRow("fund", "", f.countries, country)] : [] },
  };
}

/* ---- what the investor ends up owning: the biggest company and industry against the limits, then the companies ---- */
const checksFor = (r, side) => arr(side === "today" && sidesOf(r).includes("after") ? obj(r.baseline) && r.baseline.checks : r.checks).map(obj).filter(Boolean);
function limitRow(P, check, name, what) {
  if (!check || !isNum(check.value) || !isNum(check.limit)) return null;
  const st = shownStatus(check.status, check.tier);
  return { name, valueText: fmt(P, "pct", check.value), limitText: fmt(P, "share", check.limit), what, status: st,
    line: `${fmt(P, "pct", check.value)} of the money, against a ${fmt(P, "share", check.limit)} limit for one ${what}.` };
}
export function owningModel(r, P, side) {
  const F = fundsOf(r);
  if (!F) return null;
  side = sideOk(r, side);
  const S = obj(obj(F.sides) && F.sides[side]);
  if (!S) return null;
  const who = whoOf(r), amountText = isNum(r.amount) ? fmt(P, "money", r.amount) : "";
  const priv = privateOf(r), own = obj(obj(priv && priv.owning) && priv.owning[side]);
  const how = (x) => {
    const inside = arr(x.inside).map(obj).filter((v) => v && str(v.fund) && isNum(v.share));
    const direct = isNum(x.direct) && x.direct > 0;
    if (direct && inside.length) return `${fmt(P, "share", x.direct / r.amount)} directly, plus ${inside.map((v) => `${fmt(P, "share", v.share)} inside ${v.fund}`).join(" and ")}`;
    if (inside.length) return `Inside ${inside.map((v) => v.fund).join(" and ")}`;
    return coin(x.ticker) ? "A coin, owned directly" : "You own it directly";
  };
  const companies = own ? arr(own.top).map(obj).filter((x) => x && str(x.name) && isNum(x.dollars)).map((x) => ({
    name: x.name, ticker: str(x.ticker), how: how(x), ...money(P, x) }))
    : arr(S.direct).map(obj).filter((x) => x && str(x.ticker) && isNum(x.dollars)).map((x) => {
      const t = money(P, x.total), twice = t && isNum(x.share) && t.share > x.share + 1e-9;
      return { name: str(x.name) || x.ticker, ticker: x.ticker, ...(twice ? t : money(P, x)),
        how: twice ? `${fmt(P, "share", x.share)} directly, ${t.shareText} counting your funds` : coin(x.ticker) ? "A coin, owned directly" : "You own it directly" };
    });
  const checks = checksFor(r, side), one = checks.find((c) => c.rule === "single_stock"), sec = checks.find((c) => c.rule === "sector");
  const firstCo = own && arr(own.top).map(obj).find((x) => x && str(x.name));
  const coName = one && str(one.holding) ? fundName(one.holding)
    : firstCo && isNum(one && one.value) && Math.abs(firstCo.share - one.value) < 0.0006 ? firstCo.name : "A company inside your funds";
  const secs = bars(P, S.sectors, (n) => n), ctys = bars(P, S.countries, country);
  const limits = [limitRow(P, one, coName, "company"), limitRow(P, sec, secs.length ? secs[0].name : "The largest industry", "industry")].filter(Boolean);
  const rest = own && obj(own.rest) && own.rest.count > 0 ? { count: own.rest.count, ...money(P, own.rest) } : null;
  const funds = arr(F.funds).map(obj).filter((f) => f && obj(f[side]) && isNum(f[side].dollars)).map((f) => ({
    ticker: f.ticker, label: plainLabel(f.ticker), name: str(f.name) || f.ticker, ...money(P, f[side]) }));
  const unlisted = money(P, S.unlisted);
  const both = sidesOf(r), mv = mixes(r, P), move = mv && mv.move;
  const sideBars = (pick, name, moveKey) => both.map((sd) => barRow(sd, SIDE_WORDS[sd], pick(sd), name, moveKey));
  const coRows = (sd) => {
    const o2 = obj(obj(priv && priv.owning) && priv.owning[sd]), S2 = obj(F.sides[sd]) || {};
    const list = o2 ? arr(o2.top).map(obj).filter(Boolean).map((x) => ({ name: x.ticker || x.name, label: x.name, share: x.share, dollars: x.dollars }))
      : arr(S2.direct).map(obj).filter(Boolean).map((x) => { const t2 = obj(x.total); return { name: x.ticker, label: x.name,
        share: t2 && isNum(t2.share) ? t2.share : x.share, dollars: t2 && isNum(t2.dollars) ? t2.dollars : x.dollars }; });
    if (o2 && obj(o2.rest) && o2.rest.count > 0) list.push({ name: "__rest__", label: `${o2.rest.count} more companies`, share: o2.rest.share, dollars: o2.rest.dollars, other: true, count: o2.rest.count });
    return list;
  };
  const labels = new Map();
  for (const sd of both) for (const x of coRows(sd)) labels.set(x.name, x.label);
  const breakdown = {
    companies: sideBars(coRows, (k) => labels.get(k) || k, move),
    sectors: sideBars((sd) => (obj(F.sides[sd]) || {}).sectors, (n) => n, null),
    countries: sideBars((sd) => (obj(F.sides[sd]) || {}).countries, country, null),
    funds: sideBars((sd) => arr(F.funds).map(obj).filter((f) => f && obj(f[sd])).map((f) => ({ name: f.ticker, share: f[sd].share, dollars: f[sd].dollars })),
      (k) => `${k} (${plainLabel(k)})`, move),
  };
  return {
    side, sideWord: SIDE_WORDS[side], live: !!own, amountText, limits, companies, rest, funds, inFunds: money(P, S.in_funds), breakdown,
    companiesTitle: companies.some((c) => coin(c.ticker)) ? "By company and coin" : "By company",
    title: side === "after" ? `What ${who || "this portfolio"} ends up owning` : `What ${who || "this portfolio"} owns today`,
    country: ctys.length ? ctys.find((c) => !/^No /.test(c.name)) || null : null,
    unlisted: unlisted && unlisted.dollars > 0 ? unlisted : null,
    licence: own ? null : STATIC_OWNING, direct: S.mode === "direct" || F.mode === "direct",
    sectors: secs, countries: ctys, sectorNote: SECTOR_NOTE, fiction: FICTION, more: "Show the full breakdown",
    companiesNote: own ? `Each fund’s largest positions in the issuer’s file dated on or before ${fmt(P, "date", str(F.as_of) || r.as_of)}, plus what you own directly.` : null,
  };
}

/* ---- the drawer: tabs, side and the view ---- */
export function drawerModel(r, P, what, side) {
  const F = fundsOf(r);
  if (!F || (!arr(F.funds).length && !obj(F.sides))) return null;
  side = sideOk(r, side);
  const held = arr(F.funds).map(obj).filter((f) => f && str(f.ticker) && (obj(f.today) || obj(f.after)));
  const tabs = [{ id: "owning", label: OWNING_TAB }, ...held.map((f) => ({ id: f.ticker, label: f.ticker, sub: plainLabel(f.ticker) }))];
  const view = tabs.some((t) => t.id === what) ? what : "owning";
  return { tabs, view, side, sides: sidesOf(r).map((s) => ({ id: s, label: SIDE_WORDS[s] })), live: !!privateOf(r),
    page: view === "owning" ? null : fundPage(r, P, view, side), owning: view === "owning" ? owningModel(r, P, side) : null };
}
