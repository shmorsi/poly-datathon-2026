/* The release gate's rules (scripts/release_gate.mjs), pure: no DOM, no network. Tests: tests/web_gate_test.mjs.
   the red gates (README, Limits) red gates 1, 4, 5; the official case's responsible boundaries ("must not ... present themselves as providing
   personalized financial advice"; "does not ask teams to predict future returns"); design doc rulings R1, R16, R18, R20, R22.
   adviceHits(text, questions)  advice / forecast words and phrases (EN + FR) left after the exemptions: quoted investor
                                questions, an investor's own first-person question, and the disclaimers
   verdictHits(text)            the verdict words (R20: reserved for the move the investor asked)
   metaHits(text)               " · " meta strings (R16)
   REQUIRED                     the two lines every screen keeps visible (red gates 4 and 5)
   parseColor(css), isGreen(css, tokens)   the pass-mark colour (R20: "never green" at another size); self-contained, so the
                                gate can also run them inside the page by their source text
   ranges(sizes)                [0, 1, 2, 5] -> "0-2, 5" for the report */

export const REQUIRED = Object.freeze([
  "Educational simulation. This is not financial advice.",
  "This already happened; it is not a forecast.",
]);

/* honesty lines that carry an advice word only to deny it (removed before the scan) */
export const DISCLAIMERS = Object.freeze([
  "Educational simulation. This is not financial advice.",
  "This already happened; it is not a forecast.",
  "Fictional illustration, not a recommendation.",
  "A replay at another size, not a recommendation.",
  "Client-run simulation, not a recommendation or a suitability assessment.",
  "Past performance does not guarantee future results.",
  "Simulation éducative. Ceci n'est pas un conseil financier.",
  "Les rendements passés ne garantissent pas les rendements futurs.",
]);

const L = "\\p{L}\\p{N}_";
const B = `(?<![${L}])`;            // a word boundary that knows accented letters (\b does not)
const E = `(?![${L}])`;
const rx = (body) => new RegExp(B + "(?:" + body + ")" + E, "giu");

/* id, what the report calls it, the pattern; neg = an exemption when a negation precedes it ("not a recommendation") */
export const BANNED = Object.freeze([
  { id: "buy", label: "buy", re: rx("(?:buy|buys|buying)") },
  { id: "sell", label: "sell", re: new RegExp(B + "(?:sell|sells|selling)" + E + "(?![-‐‑]offs?)", "giu") },
  { id: "hold-verb", label: "hold (a verb)", re: rx("(?:you|we|i|they|investors?|to|should|could|would|will|can|may|might|must|keep|just|simply|then|please|always|never|don't|do not|better)\\s+(?:hold|holds|holding)") },
  { id: "hold-imperative", label: "hold (an order)", re: new RegExp("(?:^|[.!?;:]\\s+|[\"“(]\\s*)(?:hold)" + E, "giu") },
  { id: "hold-phrase", label: "hold up / hold on / hold through", re: rx("(?:hold|holds|holding|held)\\s+(?:up|on|onto|through|off|steady|tight|until)") },
  { id: "you-should", label: "you should", re: rx("you\\s+(?:should|shouldn't|ought\\s+to)") },
  { id: "recommend", label: "recommend", re: rx("(?:we\\s+|i\\s+)?(?:would\\s+)?recommend(?:s|ed|ing)?") },
  { id: "recommendation", label: "recommendation", re: rx("recommendations?"), neg: true },
  { id: "safe", label: "safe", re: rx("(?:safe|safer|safest|safely|unsafe)") },
  { id: "allowed", label: "allowed / allow", re: rx("(?:allow|allows|allowed|allowing|disallowed)") },   // permission words (R1)
  { id: "fits-you", label: "fits you", re: rx("(?:fits?|suits?)\\s+(?:you|your)|(?:a\\s+)?good\\s+fit") },
  { id: "forecast", label: "will fall / will rise", re: rx("(?:will|is\\s+going\\s+to|are\\s+going\\s+to)\\s+(?:fall|rise|drop|climb|recover|crash|rebound|gain|lose|go\\s+up|go\\s+down|grow|outperform|underperform|double|soar|plunge|tumble|surge|decline)") },
  { id: "guaranteed", label: "guaranteed", re: rx("guarantee(?:d|s)?"), neg: true },
  { id: "expected-return", label: "expected return", re: rx("expected\\s+(?:returns?|gains?|profits?)") },
  { id: "fr-acheter", label: "acheter", re: rx("(?:acheter|achetez|achetons|achète|achètes|achètent)") },
  { id: "fr-vendre", label: "vendre", re: rx("(?:vendre|vendez|vendons)") },
  { id: "fr-devriez", label: "vous devriez", re: rx("vous\\s+devriez") },
  { id: "fr-recommande", label: "recommandé", re: rx("recommand(?:é|ée|és|ées|er|ons|ez)") },
  { id: "fr-recommandation", label: "recommandation", re: rx("recommandations?"), neg: true },
  { id: "fr-securitaire", label: "sécuritaire", re: rx("s[ée]curitaires?") },
  { id: "fr-garanti", label: "garanti", re: rx("garanti(?:e|s|es)?"), neg: true },
  { id: "fr-attendu", label: "rendement attendu", re: rx("rendements?\\s+attendus?") },
]);

const NEGATION = new RegExp(`(?:${B}(?:not|never|no|nor|nothing|none|without|pas|aucune?|ni|sans|rien)|n't)\\s+(?:[\\p{L}']+\\s+){0,3}$`, "iu");

export const VERDICT_RE = new RegExp(B + "(?:inside|outside)(?:\\s+(?:your|his|her|their|[\\p{L}]+'s)\\s+limits|,?\\s+with\\s+caveats)" + E, "giu");
export const META_RE = /\s·\s/g;

/* one spelling for every space and apostrophe the page may use */
export function norm(text) {
  return String(text == null ? "" : text).replace(/[     ]/g, " ").replace(/[’ʼ]/g, "'")
    .replace(/\s+/g, " ").trim();
}
const fold = (s) => norm(s).toLowerCase().replace(/[“”«»"]/g, "").replace(/\s+/g, " ").trim();
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const FIRST_PERSON = new RegExp(`${B}(?:(?:i|i'm|i've|i'd|my|me|mine|we|our|je|mon|ma|mes|moi|nous|notre|nos)${E}|j')`, "iu");

/* the text left to judge: the disclaimers, the investors' questions (whole, or quoted in part) and any first-person question
   are cut out; `cut` lists what was cut, so a report can show the exemptions it used */
export function exempt(text, questions = []) {
  let t = norm(text);
  const cut = [];
  for (const d of DISCLAIMERS) {
    const re = new RegExp(escapeRe(norm(d)), "giu");
    t = t.replace(re, (m) => { cut.push({ why: "disclaimer", text: m }); return " ⟦disclaimer⟧ "; });
  }
  const qs = [...new Set(questions.map(norm).filter((q) => q.length >= 8))].sort((a, b) => b.length - a.length);
  for (const q of qs) {
    const re = new RegExp(escapeRe(q).replace(/\\?'/g, "['’]").replace(/ /g, "\\s+"), "giu");
    t = t.replace(re, (m) => { cut.push({ why: "investor question", text: m }); return " ⟦question⟧ "; });
  }
  const folded = qs.map(fold);
  t = t.replace(/([“"«‘])([^“”"«»‘]{1,800}?)([”"»’])/gu, (m, a, inner) => {
    const f = fold(inner).replace(/(?:…|\.\.\.)$/, "").trim();
    const isQ = /\?\s*(?:…|\.\.\.)?$/.test(inner.trim()) || (f.length >= 3 && folded.some((q) => q.includes(f)));   // a question, or part of one
    if (!isQ) return m;
    cut.push({ why: "quoted question", text: m });
    return " ⟦quoted question⟧ ";
  });
  t = t.replace(/[^.!?⟧]*\?/gu, (s) => {
    if (!FIRST_PERSON.test(s)) return s;
    cut.push({ why: "an investor's own question", text: s.trim() });
    return " ⟦question⟧ ";
  });
  return { text: t, cut };
}

function context(t, at, len) {
  const a = Math.max(0, at - 60), b = Math.min(t.length, at + len + 60);
  return (a ? "…" : "") + t.slice(a, b).trim() + (b < t.length ? "…" : "");
}

/* every advice / forecast hit in `text` after the exemptions: [{id, label, match, context}] */
export function adviceHits(text, questions = []) {
  const { text: t } = exempt(text, questions);
  const hits = [];
  for (const rule of BANNED) {
    rule.re.lastIndex = 0;
    for (const m of t.matchAll(rule.re)) {
      const at = m.index + (m[0].length - m[0].trimStart().length);
      const word = m[0].trim().replace(/^[.!?;:"“(]\s*/u, "");
      if (rule.neg && NEGATION.test(t.slice(Math.max(0, at - 48), at))) continue;
      hits.push({ id: rule.id, label: rule.label, match: word, context: context(t, at, word.length) });
    }
  }
  return hits;
}

export function verdictHits(text) {
  const t = norm(text);
  return [...t.matchAll(VERDICT_RE)].map((m) => ({ match: m[0], context: context(t, m.index, m[0].length) }));
}

export function metaHits(text) {
  const t = norm(text);
  return [...t.matchAll(META_RE)].map((m) => ({ match: "·", context: context(t, m.index, 3) }));
}

/* a CSS colour -> {r, g, b, a} (rgb(), rgba(), color(srgb ...), #hex), or null */
export function parseColor(css) {
  const s = String(css || "").trim().toLowerCase();
  let m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
  if (m) {
    const a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return { r: +m[1], g: +m[2], b: +m[3], a };
  }
  m = s.match(/^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/);
  if (m) {
    const a = m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
    return { r: +m[1] * 255, g: +m[2] * 255, b: +m[3] * 255, a };
  }
  m = s.match(/^#([0-9a-f]{6})([0-9a-f]{2})?$/);
  if (m) {
    const n = parseInt(m[1], 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: m[2] ? parseInt(m[2], 16) / 255 : 1 };
  }
  return null;
}

/* the pass-mark green: one of the page's green tokens (--clear, --status-ok), or any clearly green hue */
export function isGreen(css, tokens) {
  const parse = (x) => {
    const s = String(x || "").trim().toLowerCase();
    let m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/);
    if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]) };
    m = s.match(/^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/);
    if (m) return { r: +m[1] * 255, g: +m[2] * 255, b: +m[3] * 255, a: m[4] === undefined ? 1 : m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]) };
    m = s.match(/^#([0-9a-f]{6})$/);
    if (m) { const n = parseInt(m[1], 16); return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 }; }
    return null;
  };
  const c = parse(css);
  if (!c || c.a < 0.2) return false;
  for (const t of tokens || []) {
    const k = parse(t);
    if (k && Math.abs(k.r - c.r) + Math.abs(k.g - c.g) + Math.abs(k.b - c.b) <= 12) return true;
  }
  const r = c.r / 255, g = c.g / 255, b = c.b / 255, max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return false;
  const d = max - min, s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  return h >= 85 && h <= 160 && s >= 0.35 && l >= 0.2 && l <= 0.85;
}

/* [0, 1, 2, 5, 7, 8] -> "0-2, 5, 7-8" */
export function ranges(list) {
  const xs = [...new Set(list.filter((x) => Number.isFinite(x)))].sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < xs.length; i++) {
    let j = i;
    while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j++;
    out.push(j > i ? `${xs[i]}-${xs[j]}` : `${xs[i]}`);
    i = j;
  }
  return out.join(", ");
}
