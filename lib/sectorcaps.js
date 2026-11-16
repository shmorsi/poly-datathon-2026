/* EPICENTRE Replay, lane sector-limits (Sun Nov 15; LIMITS_MODEL 16:40; the NBDB workshop: "Constraints set the boundaries.
   Preferences guide choices within those boundaries", preferred or excluded sectors). Pure helpers for the investor's limits by
   industry: result.limits.sector_caps {GICS sector: the largest share}, 0 = the industry is excluded (a hard limit, governance).
   The page never judges a cap: governance.check_profile writes one row per capped industry (rule "sector_cap:<sector>"); these
   helpers only name, show and type them. No DOM. */

/* governance.GICS_SECTORS, the look-through's own sector names, in its order */
export const GICS_SECTORS = Object.freeze(["Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
  "Financials", "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities"]);
export const CAP_RULE = "sector_cap:";                       // governance.SECTOR_CAP
const SOURCE_WORDS = Object.freeze({ you: "set by you", words: "from your words", assumed: "assumed from the profile, not set by you" });

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);

/* "sector_cap:Energy" -> "Energy"; any other rule -> null */
export function capSector(rule) {
  const s = typeof rule === "string" && rule.startsWith(CAP_RULE) ? rule.slice(CAP_RULE.length).trim() : "";
  return s || null;
}
export const isCapRule = (rule) => capSector(rule) !== null;
/* the name a row shows when the server sent none (verify.RULE_NAMES writes the same) */
export const capName = (rule) => (capSector(rule) ? `Your ${capSector(rule)} limit` : null);
/* the facts labels behind a cap's value and limit (pipeline.CHECK_FACTS: "<sector> share ...", "Your <sector> limit") */
export const capFacts = (rule) => {
  const s = capSector(rule);
  return s ? [[`${s.toLowerCase()} share`], [`your ${s.toLowerCase()} limit`]] : null;
};

/* where one limit came from, by the one rule (LIMITS_MODEL: set by you > from your words > assumed): a key the investor's words
   set (result.limits.from_words, a list of keys; a {key: words} map gives its keys) reads "from your words"; else an edited one
   ("sector_caps" covers every industry) "set by you"; else "assumed". key: "floor", "sector_caps.Energy", ... */
export function sourceOf(limits, key) {
  const L = obj(limits) || {}, said = Array.isArray(L.from_words) ? L.from_words : Object.keys(obj(L.from_words) || {});
  if (said.includes(key)) return "words";
  const edited = arr(L.edited);
  return edited.includes(key) || (String(key).startsWith("sector_caps.") && edited.includes("sector_caps")) ? "you" : "assumed";
}
export const sourceWords = (src) => SOURCE_WORDS[src] || null;

/* the caps of a Result as rows, in GICS order: {key, sector, share, pct (the share in %, one decimal), excluded, source} */
export function capsOf(result) {
  const L = obj(obj(result) && result.limits) || {}, caps = obj(L.sector_caps) || {};
  return GICS_SECTORS.filter((s) => isNum(caps[s])).map((s) => ({ key: `sector_caps.${s}`, sector: s, share: caps[s],
    pct: Math.round(caps[s] * 1000) / 10, excluded: Math.round(caps[s] * 1000) === 0, source: sourceOf(L, `sector_caps.${s}`) }));
}

/* the editor's rows ({sector, pct} as typed: pct a string or a number of percent) -> {caps: {GICS sector: share}} in GICS order,
   or {error} in one plain sentence. A row with no industry and no share is skipped; 0 % excludes the industry. */
export function capsFromRows(rows) {
  const caps = {};
  for (const row of arr(rows)) {
    const sector = obj(row) && typeof row.sector === "string" ? row.sector.trim() : "";
    const typed = obj(row) && row.pct !== undefined && row.pct !== null ? String(row.pct).trim().replace(/\s*%$/, "") : "";
    if (!sector && !typed) continue;
    if (!GICS_SECTORS.includes(sector)) return { error: "Pick an industry for each limit, or remove the row." };
    if (Object.prototype.hasOwnProperty.call(caps, sector)) return { error: `${sector} has two limits; keep one.` };
    if (typed === "") return { error: `Enter the largest share for ${sector}, from 0 % (none of it) to 100 %.` };
    const p = Number(typed);
    if (!Number.isFinite(p) || p < 0 || p > 100) return { error: `Enter a share for ${sector} between 0 % (none of it) and 100 %.` };
    caps[sector] = Math.round(p * 10) / 1000;
  }
  const out = {};
  for (const s of GICS_SECTORS) if (Object.prototype.hasOwnProperty.call(caps, s)) out[s] = caps[s];
  return { caps: out };
}

/* the same caps? (the editor sends nothing new when the rows say what the run already has) */
export function sameCaps(a, b) {
  const x = obj(a) || {}, y = obj(b) || {}, kx = Object.keys(x), ky = Object.keys(y);
  return kx.length === ky.length && kx.every((k) => isNum(y[k]) && Math.abs(x[k] - y[k]) < 1e-9);
}

/* the investor's words that still stand once the editor typed `caps`: a cap's "from your words" stays only while its value is
   unchanged (an edit makes it set by you); every other key of from_words stays */
export function wordsAfter(limits, caps) {
  const L = obj(limits) || {}, before = obj(L.sector_caps) || {}, now = obj(caps) || {};
  const said = Array.isArray(L.from_words) ? L.from_words : Object.keys(obj(L.from_words) || {});
  return said.filter((k) => {
    if (!String(k).startsWith("sector_caps.")) return true;
    const s = k.slice("sector_caps.".length);
    return isNum(before[s]) && isNum(now[s]) && Math.abs(before[s] - now[s]) < 1e-9;
  });
}
