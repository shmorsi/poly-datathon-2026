/* EPICENTRE Replay, lane picker: "Try another move" (ruling R24). Pure: no DOM, no network; reads globalThis.PF (web/lib.js)
   at call time only for moveOf. Names come from web/lib/funds.js, the page's one ticker map (lane hold); never a second map.
   The question box stays the single source: the picker composes "What if I put N % in <public name>?" (the other holdings
   scale down in proportion) or "What if I move N % of my money from <holding> into <asset>?" (the engine's op move, R34) into
   it (live mode), or loads a saved run whose question it is (static mode), and reads the box back to show what it says.
   Tests: tests/web_picker_test.mjs (committed fixtures only, R17). */
import { fundName, plainLabel, kindOf } from "./funds.js";
import { mixes } from "./hold.js";

export const MIN_PCT = 1, MAX_PCT = 50, DEFAULT_PCT = 20, STEP_PCT = 5;
export const OWN = "own", CUSTOM = "custom";            // the select's two values that are not an asset
export const EQUAL = "equal";                            // "taken from": every other holding in proportion (the engine scales them by one factor)
export const EQUAL_TEXT = "your other holdings, in proportion";   // the engine scales every other holding by one factor (never "evenly": equal amounts would be another move)
export const EQUAL_FACE = "all your other holdings";        // the face reads "from all your other holdings" (fits at 1280); the list and the stage say "in proportion"
export const TITLE = "Try another move";
export const PLACEHOLDER = "Choose a stock, fund or coin";
export const CUSTOM_LABEL = "Your own words";
export const SIZE_LABEL = "Size of the move";
export const SAVED_LABEL = "Saved replays";
export const HONEST = "This move runs on the live app.";
/* the live app's one no-move chip: the mix as it is, replayed against the limits (the reader's "fit" question, agents/scenario.py
   _FIT); it writes the words in the box, the reader presses Replay */
export const NO_MOVE = Object.freeze({ label: "Your mix as it is", question: "Does my portfolio, as it is, stay inside my limits?" });
export const LIVE_LINK = "Open the live app";

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const NB = "\u00a0";

/* ---- the list: the 31 starter assets (assets_universe.csv) in six groups, in the brief's order ---- */
const G = (id, label, tickers) => Object.freeze({ id, label, tickers: Object.freeze(tickers) });
export const GROUPS = Object.freeze([
  G("ca", "Canadian stocks", ["RY.TO", "TD.TO", "MFC.TO", "ENB.TO", "CNQ.TO", "CNR.TO", "FTS.TO", "ATD.TO", "SHOP.TO", "CSU.TO"]),
  G("us", "US stocks", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "JPM", "JNJ", "PG", "XOM"]),
  G("etf", "Stock ETFs", ["XIU.TO", "SPY", "QQQ", "ESGV"]),
  G("bond", "Bond ETFs", ["XBB.TO", "ZST.TO", "AGG", "TLT"]),
  G("gold", "Gold", ["GLD"]),
  G("crypto", "Crypto", ["BTC-USD", "ETH-USD"]),
]);
export const UNIVERSE = Object.freeze(GROUPS.flatMap((g) => g.tickers));
const GROUP = new Map(GROUPS.flatMap((g, i) => g.tickers.map((tk) => [tk, { g, i }])));
const known = (tk) => typeof tk === "string" && GROUP.has(tk);
export const groupOf = (tk) => (known(tk) ? GROUP.get(tk).g.id : null);

/* the public name as a question says it: funds.js's name without a trailing parenthesis ("Alphabet (Class A)" -> "Alphabet") */
export const askName = (tk) => fundName(tk).replace(/\s*\([^)]*\)\s*$/, "").trim();
const byName = (a, b) => a.localeCompare(b, "en", { sensitivity: "base" });
/* a plain label inside a sentence: "gold", "long US Treasury bonds"; proper words stay ("Canadian stocks", "US bonds") */
const inSentence = (label) => (/^(US|Canadian)\b/.test(label) ? label : label.charAt(0).toLowerCase() + label.slice(1));

/* ---- the size: whole points from 1 to 50 %; the buttons step to the next multiple of 5, the keys by 1 ---- */
export function clampPct(x) {
  const v = typeof x === "string" ? (x.trim() ? Number(x.trim()) : NaN) : x;
  if (!isNum(v)) return DEFAULT_PCT;
  return Math.min(MAX_PCT, Math.max(MIN_PCT, Math.round(v)));
}
export function stepPct(v, dir) {
  const p = clampPct(v);
  return clampPct(dir > 0 ? (Math.floor(p / STEP_PCT) + 1) * STEP_PCT : (Math.ceil(p / STEP_PCT) - 1) * STEP_PCT);
}

/* ---- the question: the curated wording (INTERFACES.md, moves.json), composed and read back ---- */
/* the recorded wording (scripts/record_demo.py --scripted, data/demo_scripted.json; the live AI reader read every one of them):
   a fund named "... ETF" or "... Trust" takes "the" ("in the Invesco QQQ Trust", but "in SPDR Gold Shares"); a source holding is
   named as the investor would say it, "my Canadian stocks", "my gold", "my Shopify shares" (the select shows the same words) */
const named = (tk) => `${kindOf(tk) === "fund" && /\b(ETF|Trust)$/.test(askName(tk)) ? "the " : ""}${askName(tk)}`;
const sourceWords = (tk) => (kindOf(tk) === "stock" ? `${askName(tk)} shares` : inSentence(plainLabel(tk)));
/* from: EQUAL (or none) = the other lines scale down in proportion; a holding = N % of the money moves from it (op move, R34) */
export function composeQuestion(tk, pct, from) {
  if (!known(tk)) return null;
  if (from === undefined || from === null || from === EQUAL) return `What if I put ${clampPct(pct)} % in ${named(tk)}?`;
  if (!known(from) || from === tk) return null;
  return `What if I move ${clampPct(pct)} % of my money from my ${sourceWords(from)} into ${named(tk)}?`;
}
const norm = (x) => (typeof x === "string" ? x.replace(/[\u00a0\u202f]/g, " ").replace(/\s+/g, " ").trim() : "");
const ASKED = /^what if i put (\d{1,3}) ?% in (.+?) ?\?$/i;
const MOVED = /^what if i move (\d{1,3}) ?% of my money from (.+?) into (.+?) ?\?$/i;
/* a name as a question says it: the public name (with or without its parenthesis), the ticker or the plain label (unique across
   the 31), after "my" or "the", with or without "shares" */
const tickerOf = (name) => {
  const n = name.trim().toLowerCase(), bare = n.replace(/^(my|the)\s+/, ""), tries = [n, bare, bare.replace(/\s+shares$/, "")];
  return UNIVERSE.find((tk) => [askName(tk), fundName(tk), tk, plainLabel(tk)].some((x) => tries.includes(x.toLowerCase()))) || null;
};
/* {ticker, pct} for "put", {ticker, pct, from} for "move"; null for anything else */
export function parseQuestion(q) {
  const t = norm(q), put = ASKED.exec(t), mv = put ? null : MOVED.exec(t);
  const m = put || mv;
  if (!m) return null;
  const pct = Number(m[1]);
  if (pct < MIN_PCT || pct > MAX_PCT) return null;
  if (put) { const ticker = tickerOf(m[2]); return ticker ? { ticker, pct } : null; }
  const from = tickerOf(m[2]), ticker = tickerOf(m[3]);
  return ticker && from && ticker !== from ? { ticker, pct, from } : null;
}

/* ---- what is inside a fund: funds.js's plain words; "looked" when this run's look-through (lane hold) names the fund ---- */
export function insideHint(tk, result) {
  if (kindOf(tk) !== "fund") return null;
  const lt = obj(obj(result) && result.lookthrough) || {};
  const looked = ["today", "after"].some((k) => {
    const side = obj(lt[k]);
    return !!side && side.mode === "lookthrough" && [side.coverage, side.snapshot].some((m) => !!obj(m) && Object.prototype.hasOwnProperty.call(m, tk));
  });
  return { label: inSentence(plainLabel(tk)), looked };
}
export function hintLine(tk, result) {
  const h = insideHint(tk, result);
  if (!h) return null;
  return `Inside this fund: ${h.label}.${h.looked ? " This run looked inside it, using its published holdings." : ""}`;
}

/* the list as the select shows it: names first, the ticker after, each fund with its plain words; alphabetical by name */
export function assetOptions() {
  return GROUPS.map((g) => ({
    id: g.id, label: g.label,
    options: g.tickers.map((tk) => {
      const name = askName(tk), h = insideHint(tk, null), hint = h ? h.label : null;
      return { ticker: tk, name, hint, text: `${name} (${tk})${hint ? `, ${hint}` : ""}` };
    }).sort((a, b) => byName(a.name, b.name)),
  }));
}

/* ---- saved moves (static mode): data/demo_runs/moves.json, published by scripts/publish_pages.py as runs/moves.json with
   <meta name="epicentre-moves">; each move's run is runs/<key>.json (or a Result inside the entry, public cut by the build) ---- */
const KEY = /^[0-9a-f]{16}$/, PILOT = /^[a-z][a-z0-9_-]{0,31}$/;
const wholePct = (w) => (isNum(w) && w > 0 && w <= MAX_PCT / 100 && Math.abs(w * 100 - Math.round(w * 100)) < 1e-6 ? Math.round(w * 100) : null);
const runFile = (key) => `runs/${key}.json`;

/* moves.json, strictly: a run key, a pilot id, the question; a move names one of the 31 assets at a whole size up to 50 %;
   the defaults ("default": true) are the investors' own questions (their move, when they have one, is kept) */
export function normalizeMoves(json) {
  const list = obj(json) && Array.isArray(json.moves) ? json.moves : [];
  const out = [];
  for (const m of list) {
    if (!obj(m) || !PILOT.test(String(m.pilot)) || !KEY.test(String(m.key)) || !str(m.question)) continue;
    const isDefault = m.default === true, pct = wholePct(m.weight), ticker = known(m.ticker) ? m.ticker : null;
    const hasFrom = m.from !== undefined && m.from !== null, from = hasFrom && known(m.from) && m.from !== ticker ? m.from : null;
    if (!isDefault && (!ticker || pct === null)) continue;
    if (hasFrom && !from) continue;                    // a source that is not one of the 31, or the asset itself
    const r = obj(m.result), result = r && r.pilot === m.pilot && r.status !== "error" ? r : null;
    /* a run recorded with the investor's own typed limits (the mini-recording: "with your own limit: technology ≤ 20 %") keeps
       its label and its limits: it is told apart on its chip, and a plain pick never lands on it */
    const label = str(m.label) ? str(m.label).slice(0, 80) : null, limits = obj(m.limits);
    out.push({ pilot: m.pilot, ticker: ticker && pct !== null ? ticker : null, pct: ticker ? pct : null, question: str(m.question),
      from, key: m.key, file: runFile(m.key), default: isDefault, ...(label ? { label } : {}), ...(limits ? { limits } : {}),
      ...(result ? { result } : {}) });
  }
  return out;
}

/* one investor's saved moves, in the list's own order (group, then name, then size): an order, never a ranking */
export function savedFor(moves, investor) {
  const seen = new Set();
  return (Array.isArray(moves) ? moves : [])
    .filter((m) => obj(m) && m.pilot === investor && !m.default && known(m.ticker) && isNum(m.pct))
    .sort((a, b) => GROUP.get(a.ticker).i - GROUP.get(b.ticker).i || byName(askName(a.ticker), askName(b.ticker)) || a.pct - b.pct
      || String(a.from || "").localeCompare(String(b.from || "")))
    .filter((m) => { const k = `${m.ticker}|${m.pct}|${m.from || EQUAL}|${m.label || ""}`; if (seen.has(k)) return false; seen.add(k); return true; });
}
/* the moves a plain pick (asset, size, from) may land on: never one recorded with limits the reader did not set */
const plainFor = (moves, investor) => savedFor(moves, investor).filter((m) => !m.label && !m.limits);
const fromOf = (f) => (known(f) ? f : EQUAL);
export const matchSaved = (moves, investor, tk, pct, from) => plainFor(moves, investor)
  .find((m) => m.ticker === tk && m.pct === clampPct(pct) && fromOf(m.from) === fromOf(from)) || null;
/* static mode: a saved asset picked from the list goes to a saved source and size, so the list never strands the reader */
export function snapFrom(moves, investor, tk, from) {
  const mine = plainFor(moves, investor).filter((m) => m.ticker === tk);
  return !mine.length || mine.some((m) => fromOf(m.from) === fromOf(from)) ? fromOf(from) : fromOf(mine[0].from);
}
export function snapPct(moves, investor, tk, pct, from) {
  const mine = plainFor(moves, investor).filter((m) => m.ticker === tk && fromOf(m.from) === fromOf(from)), p = clampPct(pct);
  return !mine.length || mine.some((m) => m.pct === p) ? p : mine[0].pct;
}

/* ---- names: "Robert’s"; "You" (R46, lane profile-ui) is the reader, in the second person; a case title ("Too Canadian?") is
   not a person (lib/money.js whoOf, record.js personOf) ---- */
const YOU = "You";
const cap = (x) => x.charAt(0).toUpperCase() + x.slice(1);
export const possessive = (label) => (label === YOU ? "your" : typeof label === "string" && /^[A-Z][A-Za-z’'-]*$/.test(label) ? `${label}’s` : null);
export const ownLabel = (label) => (possessive(label) ? `${cap(possessive(label))} own question` : "The original question");
export const goLabel = (label, moved) => `Replay ${possessive(label) || "this"} ${moved ? "move" : "question"}`;
export const wantsLabel = (label) => (label === YOU ? "What you want to do" : `What ${possessive(label) ? label : "this investor"} wants to do`);
/* the replay's own years (series.dates[0] to as_of, Result keys): "through 2021–26"; ③ reads "Replay it through 2021–26" */
export function throughWords(result) {
  const r = obj(result) || {}, d = obj(r.series) && Array.isArray(r.series.dates) ? r.series.dates : [];
  const year = (x) => (typeof x === "string" && /^\d{4}-/.test(x) ? x.slice(0, 4) : null);
  const y0 = year(d[0]), y1 = year(str(r.as_of)) || year(d[d.length - 1]);
  if (!y0 || !y1) return "on real market history";
  if (y0 === y1) return `through ${y0}`;
  return `through ${y0}\u2013${y1.slice(0, 2) === y0.slice(0, 2) ? y1.slice(2) : y1}`;
}
export const replayWords = (result) => `Replay it ${throughWords(result)}`;
/* ② over the box (the design director, 15:55): the move, or the question, in the investor's own words */
export const askLabel = (label, moved) => `The ${moved ? "move" : "question"}, in ${possessive(label) || "this investor\u2019s"} words`;

/* the static chips: the investor's own question first, then the saved moves ("20 % Shopify": the size, then the plain label) */
export function chips(moves, investor, label) {
  const own = { own: true, label: possessive(label) ? `${cap(possessive(label))} question` : "The original question", ticker: null, pct: null, move: null };
  return [own, ...savedFor(moves, investor).map((m) => ({ own: false, ticker: m.ticker, pct: m.pct, from: fromOf(m.from), move: m,
    label: `${m.pct}${NB}% ${plainLabel(m.ticker)}${m.from ? ` from ${inSentence(plainLabel(m.from))}` : ""}${m.label ? `, ${m.label.replace(/(\d) %/g, `$1${NB}%`)}` : ""}` }))];
}
/* which chip shows pressed: the run on screen (the static build's run_id is its key's first 12 hex), so two saved runs with the
   same words (the own question, and the same question with your own limits) are told apart; without a run id, by the words */
export function pressedOf(list, result, box) {
  const id = obj(result) && typeof result.run_id === "string" && result.run_id.length >= 8 ? result.run_id : null;
  const runOf = (c) => !c.own && !!c.move && !!id && c.move.key.startsWith(id);
  const saved = (Array.isArray(list) ? list : []).some(runOf);
  return (Array.isArray(list) ? list : []).map((c) => {
    if (c.own) return !saved && !!box && box.value === OWN;
    if (saved) return runOf(c);
    return !c.move.label && !c.move.limits && !!box && box.value === c.ticker && box.pct === c.pct && box.from === c.from;
  });
}

/* ---- one choice, one action: live writes the question into the box; static loads the saved run or says it needs live ---- */
export function decide({ mode, investor, choice, moves } = {}) {
  const c = obj(choice);
  if (!c) return { kind: "none" };
  if (c.value === OWN) return { kind: "own" };
  if (!known(c.value)) return { kind: "none" };
  const q = composeQuestion(c.value, c.pct, fromOf(c.from));
  if (!q) return { kind: "none" };
  if (mode === "live") return { kind: "write", question: q };
  const move = matchSaved(moves, investor, c.value, c.pct, c.from);
  return move ? { kind: "load", move } : { kind: "honest" };
}

/* ---- the honest line; the live app's link only for a plain https address (never credentials, never a script) ---- */
export function safeLiveUrl(x) {
  if (typeof x !== "string" || !/^https:\/\/[^\s"'<>\\]+$/.test(x)) return null;
  try {
    const u = new URL(x);
    return u.protocol === "https:" && u.hostname && !u.username && !u.password ? u.href : null;
  } catch (e) { return null; }
}
export function honestLine(url) {
  const href = safeLiveUrl(url);
  return { text: HONEST, link: href ? { href, text: LIVE_LINK } : null };
}

/* where the saved moves come from (lane U0, 9469ff9): the static build announces runs/moves.json with <meta name="epicentre-moves">
   only when it published one, so a build without it never asks (no failed request); live mode reads none */
const SAME_SITE = /^(?!\/\/)(?![a-z][a-z0-9+.-]*:)(?!.*\.\.)[\w./-]+\.json$/i;
export function movesSource({ mode, announced } = {}) {
  return mode === "static" && typeof announced === "string" && SAME_SITE.test(announced) ? { url: announced, kind: "moves" } : null;
}

/* ---- the picker shows what the box says ---- */
export function ownMove(result) {
  const P = globalThis.PF, mv = P && typeof P.moveOf === "function" ? P.moveOf(result) : null;
  return mv && known(mv.ticker) && isNum(mv.weight) && wholePct(mv.weight) !== null ? { ticker: mv.ticker, pct: wholePct(mv.weight) } : null;
}
/* does the box name a move: the run's own words name its own move; other words only when they are a picked move */
export function namesMove(text, result) {
  const r = obj(result);
  return r && norm(text) === norm(r.question) ? !!ownMove(r) : !!parseQuestion(text);
}
/* {value: OWN | <ticker> | CUSTOM, pct, sized}: sized = the size control applies (an asset, or the own question's move) */
export function stateOf({ text, own, pct } = {}) {
  const t = norm(text), ownQ = norm(obj(own) && own.question), om = ownMove(own);
  if (!t || (ownQ && t === ownQ)) return { value: OWN, pct: om ? om.pct : clampPct(pct), sized: !!om, from: EQUAL };
  const p = parseQuestion(t);
  if (p) return { value: p.ticker, pct: p.pct, sized: true, from: fromOf(p.from) };
  return { value: CUSTOM, pct: clampPct(pct), sized: false, from: EQUAL };
}

/* ---- "taken from": today's holdings (lane hold's mixes: baseline.portfolio, else the one mix), largest first ---- */
function todayMix(result) {
  const m = obj(result) ? mixes(result, globalThis.PF) : null;
  return Object.entries((m && m.today) || {}).filter(([tk, w]) => typeof tk === "string" && isNum(w) && w > 1e-9)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
}
export function fromOptions(result, tk) {
  return [{ value: EQUAL, text: EQUAL_TEXT, pct: null },
    ...todayMix(result).filter(([k]) => k !== tk).map(([k, w]) => ({ value: k, text: `${plainLabel(k)} (${k})`, pct: Math.round(w * 100) }))];
}
export function fromWeight(result, tk) {
  const hit = todayMix(result).find(([k]) => k === tk);
  return hit ? Math.round(hit[1] * 100) : null;
}
/* the size above what the source holds: allowed (the run's own clarifying question answers), with one quiet line of fact */
export function overLine(result, label, from, pct) {
  const hit = known(from) ? todayMix(result).find(([k]) => k === from) : null;
  if (!hit || !(clampPct(pct) > hit[1] * 100 + 1e-9)) return null;
  const P = globalThis.PF, share = P && P.fmt ? P.fmt.share(hit[1]) : `${Math.round(hit[1] * 100)}${NB}%`;
  const who = label === YOU ? "You have" : `${possessive(label) ? label : "This portfolio"} holds`;   // "You hold" reads as advice to the gate
  return `${who} ${share} in ${inSentence(plainLabel(from))}.`;
}
