/* EPICENTRE Replay, lane hold: the page's ONE map of what each ticker is (the lead, 14:10: "it doesn't say what each of their
   portfolios holds"). Pure: no DOM, no globals, no network. Tests: tests/web_hold_test.mjs.
   For every ticker of the starter universe (the 31 lines of assets_universe.csv) and XSP.TO (the CAD-hedged S&P 500 fund the
   workshop names): its PUBLIC name (the issuer's or the company's own name, a public fact, never a number) and a plain label a
   reader understands at once ("Canadian stocks", "Gold"). web/lib/scenario.js reads its holding names from here.
   The licensed files (data/starter, data/etf_holdings.csv) are never read or copied by the page: only these public names.
   Country codes (the look-through's ISO 3166 alpha-3 keys, plus the engine's GLOBAL, CRYPTO and OTHER) get plain names too. */

const F = (name, label, kind) => Object.freeze({ name, label, kind });

/* kind: "fund" (an exchange-traded fund: it has insides), "stock" (one company), "crypto" (a coin) */
export const FUNDS = Object.freeze({
  "XIU.TO": F("iShares S&P/TSX 60 Index ETF", "Canadian stocks", "fund"),
  "XBB.TO": F("iShares Core Canadian Universe Bond Index ETF", "Canadian bonds", "fund"),
  "ZST.TO": F("BMO Ultra Short-Term Bond ETF", "Short-term bonds", "fund"),
  "XSP.TO": F("iShares Core S&P 500 Index ETF (CAD-Hedged)", "US stocks, hedged to CAD", "fund"),
  SPY: F("SPDR S&P 500 ETF Trust", "US stocks", "fund"),
  QQQ: F("Invesco QQQ Trust (Nasdaq-100)", "US tech stocks", "fund"),
  ESGV: F("Vanguard ESG U.S. Stock ETF", "US stocks, ESG screened", "fund"),
  AGG: F("iShares Core U.S. Aggregate Bond ETF", "US bonds", "fund"),
  TLT: F("iShares 20+ Year Treasury Bond ETF", "Long US Treasury bonds", "fund"),
  GLD: F("SPDR Gold Shares", "Gold", "fund"),
  "RY.TO": F("Royal Bank of Canada", "Royal Bank", "stock"),
  "TD.TO": F("Toronto-Dominion Bank", "TD Bank", "stock"),
  "MFC.TO": F("Manulife Financial", "Manulife", "stock"),
  "ENB.TO": F("Enbridge", "Enbridge", "stock"),
  "CNQ.TO": F("Canadian Natural Resources", "Canadian Natural", "stock"),
  "CNR.TO": F("Canadian National Railway", "CN Rail", "stock"),
  "FTS.TO": F("Fortis", "Fortis", "stock"),
  "ATD.TO": F("Alimentation Couche-Tard", "Couche-Tard", "stock"),
  "SHOP.TO": F("Shopify", "Shopify", "stock"),
  "CSU.TO": F("Constellation Software", "Constellation Software", "stock"),
  AAPL: F("Apple", "Apple", "stock"),
  MSFT: F("Microsoft", "Microsoft", "stock"),
  NVDA: F("NVIDIA", "NVIDIA", "stock"),
  GOOGL: F("Alphabet (Class A)", "Alphabet", "stock"),
  AMZN: F("Amazon", "Amazon", "stock"),
  TSLA: F("Tesla", "Tesla", "stock"),
  META: F("Meta Platforms", "Meta", "stock"),
  JPM: F("JPMorgan Chase", "JPMorgan Chase", "stock"),
  JNJ: F("Johnson & Johnson", "Johnson & Johnson", "stock"),
  PG: F("Procter & Gamble", "Procter & Gamble", "stock"),
  XOM: F("Exxon Mobil", "Exxon Mobil", "stock"),
  "BTC-USD": F("Bitcoin", "Bitcoin", "crypto"),
  "ETH-USD": F("Ether", "Ether", "crypto"),
});

/* the 31 tickers of the starter universe (assets_universe.csv, in its order): the only ones a run can hold (the engine rejects
   any other); XSP.TO and META are named above for the page's words but are not in the dataset */
export const UNIVERSE = Object.freeze(["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO",
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM", "XIU.TO", "SPY", "QQQ", "ESGV", "XBB.TO", "ZST.TO", "AGG",
  "TLT", "GLD", "BTC-USD", "ETH-USD"]);

const own = (o, k) => typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const str = (x) => String(x == null ? "" : x);

/* the whitelist as a reader looks for it: Canadian stocks, US stocks, funds, crypto (UNIVERSE order inside each group); the
   tickers in `held` are left out (the editor's "Add a holding" list) */
export function universeGroups(held = []) {
  const skip = new Set(Array.isArray(held) ? held : []);
  const kind = (tk) => (FUNDS[tk] ? FUNDS[tk].kind : null);
  const groups = [
    ["Canadian stocks", (tk) => kind(tk) === "stock" && tk.endsWith(".TO")],
    ["US stocks", (tk) => kind(tk) === "stock" && !tk.endsWith(".TO")],
    ["Funds (ETFs)", (tk) => kind(tk) === "fund"],
    ["Crypto", (tk) => kind(tk) === "crypto"],
  ];
  return groups.map(([label, fits]) => ({ label, tickers: UNIVERSE.filter((tk) => fits(tk) && !skip.has(tk)) }));
}

/* the plain label ("Canadian stocks"); the ticker itself when the page has none */
export const plainLabel = (tk) => (own(FUNDS, tk) ? FUNDS[tk].label : str(tk));
/* the public name ("iShares S&P/TSX 60 Index ETF"); the ticker when the page has none */
export const fundName = (tk) => (own(FUNDS, tk) ? FUNDS[tk].name : str(tk));
/* "fund" | "stock" | "crypto" | null (a ticker the page does not know) */
export const kindOf = (tk) => (own(FUNDS, tk) ? FUNDS[tk].kind : null);
/* the name web/lib/scenario.js has always shown for a holding (its old NAMES map, now this one) */
export const holdingName = plainLabel;

/* the look-through's country keys (tools/lookthrough.py: listing or fund country rows, gold in GLOBAL, coins in CRYPTO, an
   unexplained remainder in OTHER) as a reader says them */
export const COUNTRIES = Object.freeze({
  CAN: "Canada", USA: "United States", BMU: "Bermuda", NLD: "Netherlands", BRA: "Brazil", CHN: "China", GBR: "United Kingdom",
  IRL: "Ireland", CHE: "Switzerland", JPN: "Japan", DEU: "Germany", FRA: "France", TWN: "Taiwan", KOR: "South Korea",
  ISR: "Israel", AUS: "Australia", MEX: "Mexico", URY: "Uruguay", ARG: "Argentina", SGP: "Singapore", HKG: "Hong Kong",
  IND: "India", CYM: "Cayman Islands", LUX: "Luxembourg", NOR: "Norway", SWE: "Sweden", DNK: "Denmark", ESP: "Spain", ITA: "Italy",
  GLOBAL: "No single country (gold)", CRYPTO: "No country (crypto)", OTHER: "Other countries",
});
/* a key that is not a place: never "the money is in" it */
export const NOT_A_COUNTRY = Object.freeze(new Set(["GLOBAL", "CRYPTO", "OTHER"]));
export const countryName = (code) => (own(COUNTRIES, code) ? COUNTRIES[code] : str(code));
