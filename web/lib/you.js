/* EPICENTRE Replay, lane profile-ui: the 5th investor, "You" (rulings R46, R49; /tmp LIMITS_MODEL). You describe yourself in your
   own words; the AI reader (POST /api/profile/read, lane profile-ai) turns them into a profile that code validates; this module
   turns that answer into the card's plain rows, the limits lane hold's limits card shows (store key limitsIn) and the run's body.
   Pure: no DOM, no network. Every figure on the card is one the reader returned or you chose; the browser computes none.
   readBody(text), withAnswer(text, answer)   the POST /api/profile/read body; a clarifying answer appended to the same words
   readOf(answer)            the answer, normalized (never inventing a key)
   cardModel(you)            the card: rows [{key, label, items: [{text, source "words"|"assumed"|"you", words, edit}]}], clarify
   limitsInOf(you)           what lane hold's limits card shows as "from your words" (its contract), or null
   planOf(you, holdings)     what the run sends: {profile, amount, limits, portfolio}; limits {none: true} = "No limits set" (R49)
   withYou(body, state)      POST /api/run's body for "You" (unchanged for the other four investors)
   youGate(state, r)         what Replay does for "You": "wait" (the card is not ready), "run" (a live run on the card), or null
   exampleOf(json)           data/demo_runs/you_example.json (the static demo's one recorded example), validated, or null
   Tests: tests/web_profile_test.mjs (committed fixtures only, R17). */

export const YOU = "you";
export const PROMPT = "Describe yourself in a sentence or two: age, what the money is for, when you need it, how much you could lose, anything you avoid.";
export const EXAMPLE = "I’m 34, saving $80,000 for a home in about five years. I could live with losing $12,000. No crypto, no oil companies.";
export const READ_LABEL = "Read my words";
export const AGAIN_LABEL = "Read them again";
export const READING = "Reading your words…";
export const STATIC_LINE = "Describing yourself needs the live app.";
export const EXAMPLE_LINE = "A recorded example: describing yourself needs the live app.";
export const PRIVACY = "Your words are read once to fill this card and never stored.";
export const WAIT_LINE = "Describe yourself first, then replay.";
export const ANSWER_LABEL = "Answer";
export const FROM_WORDS = "from your words";
export const ASSUMED = "assumed";
export const YOURS = "set by you";
export const MAX_TEXT = 1500;                      // the reader's own cap (lane profile-ai: over 1,500 characters is a 422)
/* the neutral starting mix for "You": data/personas.json illustration_mixes.moderate (the test pins it to the file). The same for
   everyone, whatever the words say, so it is never a suggestion; lane hold's card labels it "assumed: edit it" */
export const NEUTRAL = Object.freeze({ "XIU.TO": 0.35, "XBB.TO": 0.3, SPY: 0.25, GLD: 0.1 });

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const own = (o, k) => !!o && Object.prototype.hasOwnProperty.call(o, k);
const money = (x) => "$" + Math.round(Math.abs(x)).toLocaleString("en-CA");
const SMALL = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
  "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"];
export const yearsWords = (y) => `In about ${y <= 20 ? SMALL[y] : y} year${y === 1 ? "" : "s"}`;   // words, not figures (R22)

/* ---- the words of each choice, for a reader outside finance (no jargon; never buy / sell / hold, R1) ---- */
export const GOALS = Object.freeze({ growth: "Growing it over the long run", balance: "Growth with some stability",
  preservation: "Keeping it, with a little growth", income: "A steady income from it" });
export const RISKS = Object.freeze({ low: "Small ones only", moderate: "Some, not too big", high: "Big ones are fine" });
export const REACTIONS = Object.freeze({ sold: "Got out", held: "Stayed in", bought: "Put more in" });
export const CRYPTO = Object.freeze({ no: "No crypto", yes: "Crypto is fine" });
export const ESG = Object.freeze({ yes: "Values screen: on", no: "Values screen: off" });   // LIMITS_MODEL: the values screen reads On / Off
const PROFILE_KEYS = ["goal", "horizon_years", "esg", "crypto", "risk", "capacity", "reaction_2022"];
/* the reader's neutral defaults (lane profile-ai): when your words differ, the card says what they replaced (LIMITS_MODEL CONFLICTS) */
export const DEFAULTS = Object.freeze({ goal: "balance", horizon_years: 10, risk: "moderate", esg: false, crypto: false });
export const NO_CAPACITY = "Not set (no capacity line)";
export const SKIP_LABEL = "Replay without it";
/* profile-ai's limits_hint IS RunBody.limits (16:55, agreed with lane sector-limits): floor, single_stock, scenario_stress, crypto,
   sector, sector_caps {GICS industry: share, 0 = excluded}, from_words (a LIST of keys, never the words: the words stay in the
   browser, in read_from under the same keys), or {none: true} when the words want no limits; {} when they are silent (the engine
   applies the profile's assumed limits). capacity, esg and horizon_years stay in the profile. */
const LIMIT_KEYS = ["floor", "single_stock", "scenario_stress", "crypto", "sector"];
const ASSUMABLE = ["capacity", "esg", "crypto", "horizon_years"];   // the answers the engine can tag "assumed" (limits.assumed)

/* ---- the request ---- */
export function readBody(text) {
  const t = typeof text === "string" ? text.replace(/\s+/g, " ").trim() : "";
  return t ? { text: t.slice(0, MAX_TEXT) } : null;
}
export function withAnswer(text, answer) {
  const a = str(answer), t = str(text) || "";
  if (!a) return t;
  return `${t}${t && !/[.!?]$/.test(t) ? "." : ""} ${a}`.trim();
}

/* ---- the answer (lane profile-ai's shape; a 503 still carries the keyword reading: show it, with its note) ---- */
export function readOf(answer) {
  const a = obj(answer) || {};
  const status = ["ok", "clarify", "blocked", "error"].includes(a.status) ? a.status : "error";
  const p = obj(a.profile) || {}, profile = {};
  for (const k of PROFILE_KEYS) if (own(p, k) && p[k] !== null && p[k] !== undefined) profile[k] = p[k];
  const from = {};
  for (const [k, v] of Object.entries(obj(a.read_from) || {})) if (str(v)) from[k] = str(v);
  const hint = obj(a.limits_hint) || {};
  return { status, canRun: a.can_run === true, profile, hint,
    amount: isNum(a.amount) && a.amount > 0 ? a.amount : null,
    age: isNum(a.age) && a.age >= 16 && a.age <= 110 ? Math.round(a.age) : null,
    assumed: arr(a.assumed).filter((k) => typeof k === "string"), from,
    clarify: status === "clarify" ? str(a.clarify) : null,
    move: str(obj(a.move) && a.move.words) || from.move || null, message: str(a.message),
    rejected: arr(a.rejected).map((x) => str(obj(x) && x.reason)).filter(Boolean),
    keyword: a.method === "keyword" || a.ai === "off" || a.ai === "down" };
}
export const usable = (r) => !!r && (r.status === "ok" || r.status === "clarify") && Object.keys(r.profile).length > 0;

/* a field's value (your edit on the card wins) and where it came from (R46: your words with the exact words, or an assumption) */
export function valueOf(you, key) {
  const y = obj(you) || {}, e = obj(y.edits) || {}, r = y.read || {};
  if (own(e, key)) return e[key];
  if (key === "amount") return r.amount;
  if (key === "age") return r.age;
  return own(r.profile || {}, key) ? r.profile[key] : null;
}
function defaultWords(key) {
  const d = DEFAULTS[key];
  if (key === "goal") return GOALS[d].toLowerCase();
  if (key === "horizon_years") return `${SMALL[d]} years`;
  if (key === "risk") return RISKS[d].toLowerCase();
  if (key === "esg") return "off";
  if (key === "crypto") return "no crypto";
  return null;
}
export function sourceOf(you, key, wordsKey) {
  const y = obj(you) || {}, r = y.read || {};
  if (arr(y.edited).includes(key)) return { source: "you", words: null };
  const words = r.from ? r.from[wordsKey || key] || null : null;
  if (arr(r.assumed).includes(key) || !words) return { source: "assumed", words: null };
  const v = own(r.profile || {}, key) ? r.profile[key] : null;
  const beat = own(DEFAULTS, key) && v !== null && v !== DEFAULTS[key] ? `default: ${defaultWords(key)}` : null;   // words beat the default
  return { source: "words", words, beat };
}

/* ---- the card: who you are, in plain words; the limits go to lane hold's limits card (limitsInOf) ---- */
export function cardModel(you) {
  const y = obj(you) || {}, r = y.read;
  if (!usable(r)) return null;
  const rows = [];
  const row = (key, label, text, extra) => rows.push({ key, label, items: [{ key, text, ...sourceOf(y, key), ...(extra || {}) }] });
  const age = valueOf(y, "age"), amount = valueOf(y, "amount"), goal = valueOf(y, "goal"), years = valueOf(y, "horizon_years");
  if (isNum(age)) row("age", "Age", String(age), { num: true });
  if (isNum(amount)) row("amount", "Money", money(amount), { num: true });
  if (own(GOALS, goal)) row("goal", "What it is for", GOALS[goal], { edit: { options: GOALS, value: goal } });
  if (isNum(years) && years >= 1 && years <= 40) row("horizon_years", "When you need it", yearsWords(Math.round(years)), { edit: { years: true, value: Math.round(years) } });
  const risk = valueOf(y, "risk"), react = valueOf(y, "reaction_2022");
  if (own(RISKS, risk)) row("risk", "Ups and downs you accept", RISKS[risk], { edit: { options: RISKS, value: risk } });
  if (own(REACTIONS, react)) row("reaction_2022", "In a fall like 2022, you", REACTIONS[react], { edit: { options: REACTIONS, value: react } });
  const values = valuesItems(y);
  if (values.length) rows.push({ key: "values", label: "Your values", items: values });
  if (y.skip && !(isNum(valueOf(y, "capacity")) && valueOf(y, "capacity") > 0))      // you chose to replay without a capacity
    rows.push({ key: "capacity", label: "You could lose", items: [{ key: "capacity", text: NO_CAPACITY, source: "you", words: null }] });
  const notes = [...(r.keyword && r.message ? [r.message] : []), ...r.rejected];     // the keyword reading's note; what code refused
  return { rows, clarify: r.status === "clarify" && !y.skip ? r.clarify : null, canRun: r.canRun, keyword: notes.length ? notes.join(" ") : null,
    conflicts: conflicts(y) };
}
/* "Your values: no crypto, no Energy companies": crypto, the ESG screen and every industry the words exclude (sector cap 0) */
function valuesItems(y) {
  const out = [], crypto = valueOf(y, "crypto"), esg = valueOf(y, "esg"), caps = obj((y.read || {}).hint.sector_caps) || {};
  if (typeof crypto === "boolean") out.push({ key: "crypto", text: crypto ? CRYPTO.yes : CRYPTO.no, ...sourceOf(y, "crypto"),
    edit: { options: CRYPTO, value: crypto ? "yes" : "no" } });
  for (const s of Object.keys(caps).filter((k) => caps[k] === 0).sort())
    out.push({ key: `sector_caps.${s}`, text: `No ${s} companies`, ...sourceOf(y, `sector_caps.${s}`) });
  if (esg === true || arr(y.edited).includes("esg") || ((y.read || {}).from || {}).esg)
    out.push({ key: "esg", text: esg ? ESG.yes : ESG.no, ...sourceOf(y, "esg"), edit: { options: ESG, value: esg ? "yes" : "no" } });
  return out;
}
/* LIMITS_MODEL "CONFLICTS" (binding, 16:55): a value you set beats your words, and one amber line says so, with "Use my words
   instead"; nothing is overridden silently */
export const USE_WORDS = "Use my words instead";
const SAID = { esg: { on: "You said you care about ESG; you switched the values screen off. The replay uses your switch.",
  off: "You said ESG does not matter to you; you switched the values screen on. The replay uses your switch." },
  crypto: { on: "You said no crypto; you allowed crypto. The replay uses your choice.",
    off: "You said crypto is fine; you switched crypto off. The replay uses your choice." } };
export function conflicts(you) {
  const y = obj(you) || {}, r = y.read || {}, from = r.from || {}, out = [];
  for (const key of arr(y.edited)) {
    const words = from[key], was = own(r.profile || {}, key) ? r.profile[key] : null, now = valueOf(y, key);
    if (!words || arr(r.assumed).includes(key) || was === null || now === was) continue;
    let line;
    if (key === "esg") line = was ? SAID.esg.on : SAID.esg.off;
    else if (key === "crypto") line = was ? SAID.crypto.off : SAID.crypto.on;
    else {
      const text = (key === "horizon_years" ? yearsWords(now) : ({ goal: GOALS, risk: RISKS, reaction_2022: REACTIONS }[key] || {})[now]) || String(now);
      line = `You said \u201c${words}\u201d; you chose \u201c${text}\u201d. The replay uses your choice.`;
    }
    out.push({ key, line, words });
  }
  return out;
}
/* an edit made on the card, in the profile's own types */
export function editValue(key, raw) {
  if (key === "horizon_years") { const n = Math.round(Number(raw)); return n >= 1 && n <= 40 ? n : null; }
  if (key === "crypto" || key === "esg") return raw === "yes";
  const opts = { goal: GOALS, risk: RISKS, reaction_2022: REACTIONS }[key];
  return opts && own(opts, raw) ? raw : null;
}

/* ---- lane hold's limits card (its contract, 16:50): {pilot, limits, capacity, source, words, none} ---- */
export function limitsInOf(you) {
  const y = obj(you) || {}, r = y.read;
  if (!usable(r)) return null;
  const listed = new Set(arr(r.hint.from_words).filter((k) => typeof k === "string" && !arr(y.edited).includes(k)));
  const limits = {}, source = {}, words = {};
  const tagged = (key) => { if (listed.has(key)) { source[key] = "words"; if (r.from[key]) words[key] = r.from[key]; } };
  for (const k of LIMIT_KEYS) if (isNum(r.hint[k]) && !(k === "crypto" && arr(y.edited).includes("crypto"))) { limits[k] = r.hint[k]; tagged(k); }
  const caps = obj(r.hint.sector_caps);
  if (caps) for (const [s0, v] of Object.entries(caps)) if (str(s0) && isNum(v) && v >= 0 && v <= 1) {
    (limits.sector_caps = limits.sector_caps || {})[s0] = v; tagged(`sector_caps.${s0}`);
  }
  const cap = valueOf(y, "capacity"), capacity = isNum(cap) && cap > 0 ? cap : null;
  if (capacity !== null) tagged("capacity");
  const none = r.hint.none === true;
  if (none && r.from.limits) words.none = r.from.limits;
  /* the values screen (limits-QA): its current value and where it came from, so the limits card can mirror it before a run */
  const esg = valueOf(y, "esg"), es = sourceOf(y, "esg");
  if (typeof esg === "boolean") { source.esg = es.source; if (es.words) words.esg = es.words; }
  return { pilot: YOU, limits, capacity, source, words, none, esg: typeof esg === "boolean" ? esg : null };
}

/* ---- the run ---- */
export function planOf(you, holdings) {
  const y = obj(you) || {}, r = y.read;
  if (!usable(r)) return null;
  const amount = [obj(holdings) && holdings.pilot === YOU ? holdings.amount : null, valueOf(y, "amount")].find((x) => isNum(x) && x > 0) ?? null;
  const portfolio = obj(holdings) && holdings.pilot === YOU && obj(holdings.portfolio) ? { ...holdings.portfolio } : { ...NEUTRAL };
  const profile = {};
  for (const k of PROFILE_KEYS) { const v = valueOf(y, k); if (v !== null && v !== undefined) profile[k] = v; }
  const none = r.hint.none === true;          // R49: no limits keeps the profile; the engine runs no checks, the replay plays in full
  const limits = JSON.parse(JSON.stringify(r.hint));
  if (arr(y.edited).includes("crypto")) delete limits.crypto;     // your crypto choice on the card replaces the words' crypto cap
  if (Array.isArray(limits.from_words)) {     // a field you changed on the card is no longer "from your words"
    limits.from_words = limits.from_words.filter((k) => typeof k === "string" && !arr(y.edited).includes(k));
    if (!limits.from_words.length) delete limits.from_words;
  }
  /* lane sector-limits (17:40): limits.assumed = the answers the reader ASSUMED, so the engine tags their rows "assumed", not
     "set by you"; never one your words gave or one you changed with the pen (then it is yours) */
  const said = new Set(arr(limits.from_words));
  const assumed = none ? [] : ASSUMABLE.filter((k) => arr(r.assumed).includes(k) && !said.has(k) && !arr(y.edited).includes(k) &&
    valueOf(y, k) !== null && valueOf(y, k) !== undefined);
  if (assumed.length) limits.assumed = assumed; else delete limits.assumed;
  return { profile, amount, limits: Object.keys(limits).length ? limits : null, portfolio, none };
}
export function withYou(body, state) {
  const st = obj(state);
  if (!st || st.investor !== YOU || !obj(body)) return body;
  const plan = planOf(st.you, st.holdings);
  if (!plan) return body;
  return { ...body, pilot: YOU, profile: plan.profile, limits: plan.limits, portfolio: plan.portfolio,
    amount: isNum(plan.amount) ? plan.amount : body.amount };
}
/* the run on screen already answers the card's plan (a You run with the same profile, amount and limits from the words) */
export function ranPlan(plan, r) {
  const res = obj(r);
  if (!plan || !res || res.pilot !== YOU) return false;
  if (isNum(plan.amount) && plan.amount !== res.amount) return false;
  const p = obj(res.profile) || {}, lim = obj(res.limits);
  if (PROFILE_KEYS.some((k) => (plan.profile[k] ?? null) !== (p[k] ?? null))) return false;
  if (plan.none) return !lim || lim.none === true;
  if (!lim) return false;
  return Object.entries(plan.limits || {}).every(([k, v]) => !isNum(v) || (isNum(lim[k]) && Math.abs(lim[k] - v) < 1e-9));
}
export function youGate(state, r) {
  const st = obj(state);
  if (!st || st.investor !== YOU) return null;
  const res = obj(r);
  if (st.mode !== "live") return res && res.pilot === YOU ? null : "wait";   // static: the recorded example plays, else nothing to run
  const y = obj(st.you) || {};
  if (!usable(y.read) || !y.read.canRun) return "wait";
  if (y.read.status === "clarify" && !y.skip) return "wait";       // the one question is answered first, or skipped with a visible "not set"
  return ranPlan(planOf(y, st.holdings), res) ? null : "run";
}

/* ---- the static demo's one recorded example (<meta name="epicentre-you" content="runs/you_example.json">) ---- */
const KEY = /^[0-9a-f]{16}$/;
export function exampleOf(json) {
  const j = obj(json);
  if (!j) return null;
  const text = str(j.text) || str(j.words);
  const raw = obj(j.read) || obj(j.response) || obj(j.profile_read) || obj(j.answer);
  if (!text || !raw) return null;
  const read = readOf(raw);
  if (!usable(read)) return null;
  const k = str(j.key) || str(j.run_key), key = k && KEY.test(k) ? k : null;
  const result = obj(j.result) && j.result.pilot === YOU ? j.result : null;     // a run inside the file (the build's public cut)
  return { text, read, key, file: key ? `runs/${key}.json` : null, result, question: str(j.question) };
}
