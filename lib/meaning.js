/* EPICENTRE Replay, lane clarity: what a number on screen means, in plain words (ruling R22; the lead 12:35: "not too complicated
   to understand the numbers and what's going on"). Pure: no DOM, no globals, no network. Tests: tests/web_clarity_test.mjs.
   Every number the sections show gets ONE sentence on hover, focus or tap: "<the number>: <what it is>." The words come from
   this one small map, or from the Result's own facts row (result.facts[T#].label) when the number has one. Never a number of
   its own: the sentence repeats the figure the page already shows, it never adds one.
   countFigures(text) counts the numbers a reader sees in a string (the R22 budget: about 6 per screen when closed); a calendar
   year or a year range ("2021–26") is a date, not a figure, and is not counted (like an axis). */

export const MEANING = Object.freeze({
  money_share: "the share of your money in {x}",
  risk_share: "how much of your mix’s ups and downs came from {x}, on daily prices",
  one_company_limit: "the most you set for any one company",
  risk_warning: "the share of the risk at which the check starts to warn",
  bets: "independent bets: how many truly separate sources of risk the mix held (more is more spread out)",
  canada_money: "the share of your money in Canadian lines",
  canada_risk: "the share of your mix’s ups and downs that came from Canadian lines",
  worst_fall: "the biggest drop from a high point, in this replay",
  worst_dollars: "the same drop in dollars on your amount",
  floor: "your floor: the largest drop from a high you said you could take",
  capacity: "the most you said you could lose, in dollars",
  shock_loss: "the worst loss in the earlier episodes of the shock you asked about",
  shock_limit: "the most you set for one shock",
  end_value: "what the money was worth at the end of the replay",
  break_size: "the smallest size of the move that broke your floor, in this replay",
  move_size: "the size of the move you asked about: its share of your money",
  sector: "the share of your money in one industry",
  crypto: "the share of your money in crypto",
  recovery: "the days it took to climb back to the old high",
  growth: "the average growth per year {x}, compounded over the replay, in Canadian dollars with dividends reinvested",
  volatility: "how much the value swung in a year {x} (its daily ups and downs, annualised); one indicator among others: your horizon, your diversification and your preferences matter too",
  horizon: "the years until you need the money",
  value: "the value this check measured, in this replay",
  limit: "the limit you set for this check",
  count: "how many there were, in this replay",
  episodes: "how many earlier episodes of this shock are on record",
  traced: "the numbers in the explanation that the number check matched to the data, out of all of them",
  ms: "how long this step took",
  tokens: "the pieces of text the AI model read and wrote in this step",
  eval_score: "correct readings out of the questions it was tested on",
  wilson: "the range the true rate is likely in, given how many questions were tested",
  reconciled: "our return next to the return the fund’s issuer published for the same period",
  seal: "the record’s fingerprint: change any number and it changes",
});

const lowerFirst = (t) => (/^[A-Z][a-z]/.test(t) && !/^(NVIDIA|Canada|Canadian|S&P|XSP|SPY|QQQ|AWS|Amazon)/.test(t) ? t.charAt(0).toLowerCase() + t.slice(1) : t);
const clean = (t) => String(t == null ? "" : t).replace(/\s+/g, " ").trim();
const stop = (t) => (/[.!?]$/.test(t) ? t : `${t}.`);

/* "<text>: <meaning>." for a kind of the map (or a sentence given as it is); null when either side is missing */
export function say(kind, text, x) {
  const shown = clean(text);
  let words = Object.prototype.hasOwnProperty.call(MEANING, kind) ? MEANING[kind] : clean(kind);
  if (!shown || !words) return null;
  words = words.includes("{x}") ? words.replace("{x}", clean(x) || "it") : x ? `${words}, ${clean(x)}` : words;
  return stop(`${shown}: ${words}`);
}

/* the facts row's own words for a traced number: "<text>: <label>." (the Result's label, never typed); falls back to a kind */
export function factMeaning(result, factId, text, kind) {
  const f = result && result.facts && factId ? result.facts[factId] : null;
  const label = f && typeof f.label === "string" ? clean(f.label) : "";
  if (label) return stop(`${clean(text)}: ${lowerFirst(label)}`);
  return kind ? say(kind, text) : null;
}

/* the figures a reader sees in a string: calendar years and year ranges are dates (not counted), the rest are numbers */
export function countFigures(text) {
  const t = clean(text).replace(/\b(19|20)\d{2}(\s?[–-]\u2060?\s?\d{2,4})?\b/g, " ")
    .replace(/\b(Claude|Sonnet|Haiku|Opus)\s+\d+(\.\d+)?\b/g, " ")           // a model's name, not a figure
    .replace(/S&P\s500|Nasdaq-100/g, " ")                                         // an index's name, not a figure
    .replace(/\b[A-Za-z]+\d+[A-Za-z\d]*\b/g, " ");                           // EC2, S3, T29: names, not figures
  const m = t.match(/\d[\d,]*(?:\.\d+)?/g);
  return m ? m.length : 0;
}

/* a year range never breaks across two lines ("2021–" / "26"): a word joiner after the dash between two figures */
export const keepRanges = (text) => String(text == null ? "" : text).replace(/(\d)–(?=\d)/g, "$1–\u2060");

/* ---- plain words (the cold first-time-user test, 14:25): the page says what a thing is, and the exact term lives in the
   tooltip. TERMS: the plain phrase -> the exact term, explained (no figure). plain(text): data-written words (facts labels,
   method notes, source texts) in the page's plain vocabulary; the Result keeps its own words. ---- */
export const TERMS = Object.freeze({
  "AI reader": "The navigator: Claude on Amazon Bedrock reads your question and picks the kind of shock and its earlier episodes. It never computes a number.",
  "number check": "The receipt: code matches every number in the explanation to a fact computed from the data, before the explanation is shown.",
  "tamper-proof record": "The seal: a SHA-256 fingerprint of the whole record. Change any number and the fingerprint no longer matches.",
  "similar indexes": "Stand-ins: public indexes that already existed in each earlier crisis, replayed in place of today’s funds.",
  "similar index": "A stand-in: a public index that already existed then, replayed in place of today’s fund.",
  "kinds of shock": "Shock families: tariffs, war and oil, chips, and rates.",
});

const PLAIN = [
  [/\bthe navigator’s\b/g, "the AI reader’s"], [/\bThe navigator’s\b/g, "The AI reader’s"],
  [/\bthe navigator\b/g, "the AI reader"], [/\bThe navigator\b/g, "The AI reader"],
  [/\bNavigator\b/g, "AI reader"], [/\bnavigator\b/g, "AI reader"],
  [/\bby stand-ins?\b/g, "by similar indexes"], [/\ba stand-in\b/g, "a similar index"], [/\bA stand-in\b/g, "A similar index"],
  [/\bstand-ins\b/g, "similar indexes"], [/\bStand-ins\b/g, "Similar indexes"],
  [/\bstand-in\b/g, "similar index"], [/\bStand-in\b/g, "Similar index"],
  [/\bthe receipt’s\b/g, "the number check’s"], [/\breceipt\b/g, "number check"], [/\bReceipt\b/g, "Number check"],
  [/\bdebrief\b/g, "explanation"], [/\bDebrief\b/g, "Explanation"],
  [/\bthe same fall on the amount\b/g, "the amount times the fall (not the path’s own dollars)"],
  [/\b(each|every) family[’']s shock windows\b/g, "$1 kind of shock’s windows"], [/\b(each|every) family[’']s\b/g, "$1 kind of shock’s"], [/\bshock families\b/gi, "kinds of shock"], [/\bfamilies\b/g, "kinds of shock"],
];
export function plain(text) {
  let t = String(text == null ? "" : text);
  for (const [rx, to] of PLAIN) t = t.replace(rx, to);
  return t;
}
