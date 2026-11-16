/* EPICENTRE, the sealed decision record (lane U9, ruling R6): pure helpers, no DOM, no network.
   - canonicalJson(x): byte for byte proofs.canonical_json (Python is the reference; tests/web_u9_test.mjs checks the bytes
     against proofs.py). Keys sorted by code point, no spaces, integral numbers as integers, other numbers Python's
     format(x, ".10f") with its trailing zeros stripped (an exact tie at the 10th decimal rounds to even, as Python does;
     a plain toFixed would round it up), -0 as 0, strings as json.dumps(ensure_ascii=False).
   - sha256Hex(text): the SHA-256 of the UTF-8 bytes, by the browser's Web Crypto (crypto.subtle) when the page has it,
     else by sha256HexSync (plain JS, the same digest; a page served over plain http has no crypto.subtle).
   - buildRecord(result, opts): the record the investor keeps and a broker can audit, every value copied from a Result key
     (nothing computed here but counts, comparisons and look-ups), null where the Result has no value.
   - setAt / parseEdit / changedDigits / downloadFile: the tamper check ("Edit a number": any change gives another seal).
   Reads globalThis.PF (web/lib.js) at call time, never at import time. */

// ---- canonical JSON (proofs._canon) ------------------------------------------------------------------------------
const FIVE_10 = 5n ** 10n;

/* Python's format(x, ".10f"): exact decimal of the double, ties to even. An exact tie at the 10th decimal is an odd
   multiple of 2^-11 (x * 2048 an odd integer); everything else is correctly rounded by toFixed already. */
function fixed10(x) {
  const m = x * 2048;
  if (Number.isInteger(m) && m % 2 !== 0) {
    const twice = BigInt(Math.abs(m)) * FIVE_10;          // 2 * |x| * 10^10, an odd integer
    let n = (twice - 1n) / 2n;                              // the lower candidate
    if (n % 2n === 1n) n += 1n;                             // the even one wins
    const s = n.toString().padStart(11, "0");
    return (x < 0 ? "-" : "") + s.slice(0, -10) + "." + s.slice(-10);
  }
  return x.toFixed(10);
}

function canonNumber(x) {
  if (Number.isNaN(x)) return "nan";                       // what format() writes (JSON never carries one)
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  if (Number.isInteger(x)) return BigInt(x).toString();    // 600000.0 -> 600000, -0.0 -> 0, 1e21 -> every digit
  const t = fixed10(x).replace(/0+$/, "").replace(/\.$/, "");
  return t === "" || t === "-0" ? "0" : t;
}

const codePoints = (s) => Array.from(s, (c) => c.codePointAt(0));
function byCodePoint(a, b) {                               // Python sorts str keys by code point, not by UTF-16 unit
  const x = codePoints(a), y = codePoints(b), n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
}

export function canonicalJson(x) {
  if (x === null) return "null";
  switch (typeof x) {
    case "boolean": return x ? "true" : "false";
    case "number": return canonNumber(x);
    case "bigint": return x.toString();
    case "string": return JSON.stringify(x);               // = json.dumps(x, ensure_ascii=False) for well-formed text
    case "object":
      if (Array.isArray(x)) return "[" + x.map(canonicalJson).join(",") + "]";
      return "{" + Object.keys(x).sort(byCodePoint).map((k) => JSON.stringify(k) + ":" + canonicalJson(x[k])).join(",") + "}";
    default: throw new TypeError(`canonical_json: cannot write a ${typeof x}`);
  }
}

// ---- SHA-256 --------------------------------------------------------------------------------------------------------
const PRIMES = [];
for (let n = 2; PRIMES.length < 64; n++) if (PRIMES.every((p) => n % p)) PRIMES.push(n);
const frac32 = (v) => Math.floor((v - Math.floor(v)) * 2 ** 32) >>> 0;
const K = Uint32Array.from(PRIMES, (p) => frac32(Math.cbrt(p)));
const H0 = Uint32Array.from(PRIMES.slice(0, 8), (p) => frac32(Math.sqrt(p)));
const rotr = (x, n) => (x >>> n) | (x << (32 - n));

export function sha256HexSync(text) {
  const bytes = new TextEncoder().encode(String(text));
  const n = bytes.length, words = (((n + 8) >> 6) + 1) << 4;     // whole 64-byte blocks: data, 0x80, the 64-bit length
  const w = new Uint32Array(words);
  for (let i = 0; i < n; i++) w[i >> 2] |= bytes[i] << (24 - (i & 3) * 8);
  w[n >> 2] |= 0x80 << (24 - (n & 3) * 8);
  w[words - 2] = Math.floor((n * 8) / 2 ** 32);
  w[words - 1] = (n * 8) >>> 0;
  const H = Uint32Array.from(H0), W = new Uint32Array(64);
  for (let off = 0; off < words; off += 16) {
    for (let t = 0; t < 16; t++) W[t] = w[off + t];
    for (let t = 16; t < 64; t++) {
      const a = W[t - 15], b = W[t - 2];
      W[t] = W[t - 16] + (rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3)) + W[t - 7] + (rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10));
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let t = 0; t < 64; t++) {
      const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + W[t]) | 0;
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
  }
  return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
}

const subtleOf = () => { const c = globalThis.crypto; return c && c.subtle && typeof c.subtle.digest === "function" ? c.subtle : null; };

/* {hex, by}: by "Web Crypto" (crypto.subtle) or "script" (sha256HexSync); both give the same 64 hex digits */
export async function sha256Hex(text) {
  const subtle = subtleOf();
  if (subtle) {
    try {
      const buf = await subtle.digest("SHA-256", new TextEncoder().encode(String(text)));
      return { hex: Array.from(new Uint8Array(buf), (x) => x.toString(16).padStart(2, "0")).join(""), by: "Web Crypto" };
    } catch (e) { /* an insecure context can refuse: the script digest below is the same function */ }
  }
  return { hex: sha256HexSync(text), by: "script" };
}

/* the seal of a record: SHA-256 of its canonical JSON as UTF-8 (Python: hashlib.sha256(canonical_json(r).encode())) */
export const sealOf = (record) => sha256Hex(canonicalJson(record));

// ---- the one status vocabulary (ruling R20; the checklist's mapping, lane U5b's web/lib/status.js once it lands) --------
/* a row says what it did to the verdict: only a hard limit that broke reads "Outside"; a soft limit or a preference that broke,
   and any warning, read "Caution" (they can only add a caveat); a pass reads "Inside". The server's status and tier decide. */
const SHOWN = { outside: { word: "Outside", tone: "outside", icon: "i-out" }, caution: { word: "Caution", tone: "caveat", icon: "i-warn" },
  inside: { word: "Inside", tone: "inside", icon: "i-in" } };
export function shownStatus(status, tier) {
  if (status === "fail") return tier === "hard" ? SHOWN.outside : SHOWN.caution;
  if (status === "warn") return SHOWN.caution;
  if (status === "pass") return SHOWN.inside;
  return null;
}

// ---- the record -----------------------------------------------------------------------------------------------------
export const SCHEMA = "epicentre.decision-record/1";
export const STATEMENT = "Client-run simulation, not a recommendation or a suitability assessment.";
export const DISCLAIMER = "Educational simulation. This is not financial advice.";
export const HISTORY = "This already happened; it is not a forecast.";
export const FICTION = "Fictional illustration, not a recommendation.";
export const TYPED = "typed by you";
export const ASSUMED = "assumed for this fictional profile";
export const FROM_WORDS = "from your words";                 // limits-QA: a "You" record keeps each limit's real source
export const ASSUMED_DEFAULT = "assumed (a default)";

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const num = (x) => (typeof x === "number" && Number.isFinite(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const iso = (x) => (typeof x === "string" && /^\d{4}-\d{2}-\d{2}/.test(x) ? x.slice(0, 10) : null);
const same = (a, b) => num(a) !== null && num(b) !== null && Math.abs(a - b) < 1e-9;
const factNo = (id) => { const m = /^T(\d+)$/.exec(id); return m ? +m[1] : Infinity; };

/* the move the question asked for (PF.moveOf decides; without web/lib.js the ticker stands for its name) */
function moveOf(r) {
  const pf = globalThis.PF, change = obj(obj(r.scenario) && r.scenario.change) || {};
  let m = pf && typeof pf.moveOf === "function" ? pf.moveOf(r) : null;
  if (!m && !pf && r.question_type === "change" && obj(r.portfolio)) {
    const tk = str(obj(r.tipping_point) && r.tipping_point.ticker) || str(change.ticker);
    if (tk && num(r.portfolio[tk]) !== null) m = { ticker: tk, name: tk, weight: r.portfolio[tk] };
  }
  if (!m) return null;
  const base = obj(obj(r.baseline) && r.baseline.portfolio);
  return { op: str(change.op), ticker: m.ticker, name: m.name, weight: m.weight,
    today_weight: base ? num(base[m.ticker]) ?? 0 : null, from_ticker: str(change.from_ticker) };
}

/* the trace row that produced a number: the fact's own row, else the first row a test picks */
const traceRow = (trace, id) => trace.find((t) => t.id === id) || null;
function sourceOf(t) {
  if (!t) return { trace: null, step: null, tool: null, source: null };
  return { trace: str(t.id), step: str(t.step), tool: str(t.tool), source: str(t.source) };
}
const keyOf = (t) => {
  const inp = obj(t && t.inputs) || {};
  return str(inp.path) ? str(inp.path) + (str(inp.key) ? `[${inp.key}]` : "") : null;
};

/* the facts a check row cites: the trace rows keyed by its rule (checks.value / checks.limit), else the facts holding the
   same value (a measured fact for the value, an assumed one for the limit) */
function factsOfCheck(c, facts, trace) {
  const pick = (part, kinds, v) => {
    const t = trace.find((x) => { const i = obj(x.inputs); return i && i.key === c.rule && i.path === `checks.${part}` && facts[x.id]; });
    if (t) return t.id;
    if (num(v) === null) return null;
    const ids = Object.keys(facts).filter((id) => same(obj(facts[id]) && facts[id].value, v)).sort((a, b) => factNo(a) - factNo(b));
    return ids.find((id) => kinds.includes(facts[id].kind)) || null;
  };
  return [pick("value", ["fact"], c.value), pick("limit", ["assumption", "limit"], c.limit)].filter(Boolean);
}

/* the date a saved run was recorded on, as the server's own sentence says it ("... recorded on 15 Nov 2026.") */
const recordedOn = (message) => { const m = /recorded on (\d{1,2} [A-Z][a-z]{2} \d{4})/.exec(String(message || "")); return m ? m[1] : null; };

/* "your calmer self": the limits the investor changed after seeing the answer, first shown -> now (the record keeps the first
   ones and its verdict; each change is one line, sealed with the rest). Only the limits a person can type are compared. */
export const LIMIT_WORDS = { floor: "floor", single_stock: "one-company limit", sector: "one-sector limit", crypto: "crypto limit" };
export function limitChanges(first, now) {
  const a = obj(first && first.limits) || {}, b = obj(now && now.limits) || {};
  return Object.keys(LIMIT_WORDS).filter((k) => num(a[k]) !== null && num(b[k]) !== null && !same(a[k], b[k]))
    .map((k) => ({ limit: k, from: a[k], to: b[k] }));
}

export function buildRecord(result, opts) {
  const r = obj(result) || {}, o = obj(opts) || {};
  const facts = obj(r.facts) || {}, trace = arr(r.trace).map(obj).filter(Boolean);
  const profile = obj(r.profile) || {}, L = obj(r.limits) || {}, move = moveOf(r);
  const dates = arr(obj(r.series) && r.series.dates);
  const edited = arr(L.edited), words = arr(L.from_words), persona = ["robert", "mateo", "amira", "canadian"].includes(str(r.pilot));
  const setBy = (k) => (edited.includes(k) ? TYPED : words.includes(k) ? FROM_WORDS : persona ? ASSUMED : ASSUMED_DEFAULT);
  const capacity = [L.capacity_dollars, profile.capacity_dollars, profile.capacity].map(num).find((x) => x !== null && x > 0) ?? null;
  const floorDollars = num(L.floor) !== null && L.floor_source === "capacity" && !edited.includes("floor") ? capacity : null;
  const family = str(arr(obj(r.scenario) && r.scenario.families)[0]);
  const turb = family ? obj(obj(r.turbulence) && r.turbulence[family]) : null;
  const curve = arr(obj(r.tipping_point) && r.tipping_point.curve).map(obj).filter(Boolean);
  const endAt = (w) => { const p = num(w) === null ? null : curve.find((c) => same(c.weight, w)); return p ? num(p.end_value) : null; };
  const evalRow = (which) => trace.find((t) => t.tool === "governance.evaluate" && obj(t.inputs) && t.inputs.which === which) || null;
  const pathRow = trace.find((t) => t.tool === "tools.portfolio.portfolio_series") || null;
  const side = move ? "after" : "today";
  const worstM = obj(obj(r.metrics) && r.metrics[side]), kpi = obj(obj(r.kpis) && r.kpis.max_drawdown);
  const div = obj(r.diversification), canAt = (k) => num(obj(obj(div && div[k]) && div[k].countries) && div[k].countries.CAN);
  const pf = globalThis.PF, label = pf && typeof pf.view === "function" ? pf.view(r).shockFamily : null;
  const amountFact = Object.values(facts).map(obj).find((f) => f && f.entity === "your amount") || null;
  const rec = {
    schema: SCHEMA, statement: STATEMENT, disclaimer: str(r.disclaimer) || DISCLAIMER, history: HISTORY,
    run: { run_id: str(r.run_id), as_of: iso(r.as_of), commit: str(o.commit), mode: str(r.mode), status: str(r.status),
      recorded_on: recordedOn(r.message) },
    replay: { first: iso(dates[0]), last: iso(dates[dates.length - 1]) || iso(r.as_of) },
    investor: { name: str(profile.name), age: num(profile.age), pilot: str(r.pilot), fictional: true, amount: num(r.amount),
      currency: str(amountFact && amountFact.unit), horizon_years: num(profile.horizon_years) },
    question: str(r.question),
    reading: { method: str(obj(r.scenario) && r.scenario.method) },   /* "bedrock": the navigator read it; "fallback": the keyword rules */
    move: move && { ...move, note: FICTION },
    shock: family && { family, label: str(label), episodes: num(turb && turb.n), worst_today: num(turb && turb.worst_today),
      worst_with_move: move ? num(turb && turb.worst_after) : null, evidence: str(turb && turb.evidence),
      event_ids: arr(obj(r.scenario) && r.scenario.event_ids).filter((x) => typeof x === "string") },
    limits: {
      floor: { value: num(L.floor), dollars: floorDollars, source: str(L.floor_source), set_by: setBy("floor") },
      scenario_stress: { value: num(L.scenario_stress), set_by: setBy("floor") },
      single_stock: { value: num(L.single_stock), set_by: setBy("single_stock") },
      sector: { value: num(L.sector), set_by: setBy("sector") },
      crypto: { value: num(L.crypto), set_by: setBy("crypto") },
    },
    verdict: move ? { today: str(obj(r.baseline) && r.baseline.verdict), with_move: str(r.verdict) } : { mix: str(r.verdict) },
    money: {
      end_today: move ? endAt(move.today_weight) : null, end_with_move: move ? endAt(move.weight) : null,
      breaches: arr(r.breaches).map(obj).filter((b) => b && num(b.depth) !== null).map((b) => ({ peak_date: iso(b.peak_date),
        trough_date: iso(b.trough_date), recovery_date: iso(b.recovery_date), depth: b.depth, loss_dollars: num(b.loss_dollars) })),
      /* the evaluated mix's worst fall (the floor check's number), its dollars as the Result quotes them (kpis, ledger §30) */
      worst: worstM && num(worstM.max_drawdown) !== null ? { depth: worstM.max_drawdown, peak_date: iso(worstM.peak_date), trough_date: iso(worstM.trough_date),
        loss_dollars: kpi && same(kpi.value, worstM.max_drawdown) ? num(kpi.loss_dollars) : null } : null,
    },
    /* Canada's share of the money (diversification.*.countries.CAN): today, and with the move when there is one */
    canada: canAt("today") === null ? null : { today: canAt("today"), with_move: move ? canAt("after") : null },
    checks: arr(r.checks).map(obj).filter((c) => c && str(c.rule)).map((c) => ({ rule: c.rule, name: str(c.name), status: str(c.status),
      tier: str(c.tier), shown: (shownStatus(c.status, c.tier) || {}).word || null, value: num(c.value), limit: num(c.limit),
      holding: str(c.holding), same_cause_as: str(c.same_cause_as), facts: factsOfCheck(c, facts, trace) })),
    numbers: [], sources: {},
    receipt: null, guardrail: null,
  };
  rec.numbers = numbersOf(r, rec, facts, trace, { endRow: pathRow, seriesRow: evalRow(side), side, curve, move });
  /* each data source's text once (S1, S2, ... in order of first use); a number names its source by that id */
  const ids = new Map();
  for (const n of rec.numbers) {
    if (n.source === null) continue;
    if (!ids.has(n.source)) ids.set(n.source, `S${ids.size + 1}`);
    n.source = ids.get(n.source);
  }
  rec.sources = Object.fromEntries([...ids].map(([text, id]) => [id, text]));
  const after = arr(o.after).map(obj).filter((c) => c && LIMIT_WORDS[c.limit] && num(c.from) !== null && num(c.to) !== null);
  if (after.length) rec.after_answer = after.map((c) => ({ limit: c.limit, from: c.from, to: c.to, when: "after seeing the answer" }));
  const rc = obj(r.receipt);
  if (rc) rec.receipt = { verified: num(rc.verified), total: num(rc.total), drafts: num(rc.drafts), missing: arr(rc.missing).length };
  const g = obj(r.guardrail), gi = g && obj(g.input), go = g && obj(g.output);
  if (gi || go) {
    const one = (x) => x && { action: str(x.action), blocked: x.blocked === true, request_id: str(x.request_id),
      grounding: num(obj(x.grounding) && x.grounding.score), threshold: num(obj(x.grounding) && x.grounding.threshold) };
    rec.guardrail = { input: one(gi), output: one(go) };
  }
  return rec;
}

/* every number on the card with its source: each facts row (fact id -> its trace row: step, tool, the Result key it read,
   the data source), then the card's own numbers no facts row holds (the two end values, each break of the floor), each
   pointed at the trace row that computed its path. Dollars on the fictional amount are fiction, as in the facts table. */
function numbersOf(r, rec, facts, trace, ctx) {
  const out = [];
  for (const id of Object.keys(facts).sort((a, b) => factNo(a) - factNo(b) || (a < b ? -1 : a > b ? 1 : 0))) {
    const f = obj(facts[id]);
    if (!f || num(f.value) === null) continue;
    const t = traceRow(trace, id);
    out.push({ fact: id, key: keyOf(t), label: str(f.label), value: f.value, unit: str(f.unit), kind: str(f.kind), ...sourceOf(t) });
  }
  const add = (key, label, value, unit, kind, t) => {
    if (num(value) !== null) out.push({ fact: null, key, label, value, unit, kind, ...sourceOf(t) });
  };
  const { move, curve, endRow, seriesRow, side } = ctx;
  if (move) {
    const at = (w) => curve.findIndex((c) => same(c.weight, w));
    add(`tipping_point.curve[${at(move.weight)}].end_value`, "End value with the move", rec.money.end_with_move, "CAD", "fiction", endRow);
    add(`tipping_point.curve[${at(move.today_weight)}].end_value`, "End value of today\u2019s mix", rec.money.end_today, "CAD", "fiction", endRow);
  }
  if (rec.money.worst) {
    add(`metrics.${side}.max_drawdown`, "Worst fall of the evaluated mix", rec.money.worst.depth, "pct", "fact", seriesRow);
    add("kpis.max_drawdown.loss_dollars", "The same fall on the amount", rec.money.worst.loss_dollars, "CAD", "fiction", seriesRow);
  }
  if (rec.canada) {
    add("diversification.today.countries.CAN", "Canada\u2019s share of the money today", rec.canada.today, "pct", "fact", null);
    add("diversification.after.countries.CAN", "Canada\u2019s share of the money with the move", rec.canada.with_move, "pct", "fact", null);
  }
  rec.money.breaches.forEach((b, i) => {
    add(`breaches[${i}].depth`, `Break ${i + 1} of the floor, the fall from its high`, b.depth, "pct", "fact", seriesRow);
    add(`breaches[${i}].loss_dollars`, `Break ${i + 1}, the same fall on the amount`, b.loss_dollars, "CAD", "fiction", seriesRow);
  });
  return out;
}

// ---- the tamper check -----------------------------------------------------------------------------------------------
const parts = (path) => String(path).split(".").map((p) => (/^\d+$/.test(p) ? +p : p));
export function getAt(rec, path) {
  let x = rec;
  for (const p of parts(path)) { if (x === null || typeof x !== "object") return undefined; x = x[p]; }
  return x;
}
/* a copy of the record with one value replaced (the record itself is never changed) */
export function setAt(rec, path, value) {
  const copy = structuredClone(rec), ps = parts(path);
  let x = copy;
  for (const p of ps.slice(0, -1)) { if (x === null || typeof x !== "object") return copy; x = x[p]; }
  if (x !== null && typeof x === "object") x[ps[ps.length - 1]] = value;
  return copy;
}
/* what a number typed on the card becomes in the record: a fraction for a percent, a plain number otherwise; text that is
   not a number any more goes in as the text itself (it still changes the seal, which is the point) */
export function parseEdit(text, unit) {
  const t = String(text ?? "").replace(/\s+/g, " ").trim();
  const clean = t.replace(/[−‒–]/g, "-").replace(/\b(days?|years?|CAD)\b/gi, "").replace(/[\s  ,$%]/g, "");
  if (!/^-?\d+(\.\d+)?$/.test(clean)) return t;
  const v = Number(clean);
  return unit === "pct" || unit === "share" ? v / 100 : v;
}
/* the positions of the seal's hex digits that differ (the avalanche: one changed number moves about 60 of 64) */
export const changedDigits = (a, b) => Array.from(String(a || ""), (c, i) => c !== String(b || "")[i]);

// ---- words and the file -------------------------------------------------------------------------------------------
export const timesWord = (n) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);
/* "2021–26": the replay's first and last years, from the series dates */
export function replayYears(rec) {
  const a = rec && rec.replay && rec.replay.first, b = rec && rec.replay && rec.replay.last;
  if (!a || !b) return null;
  const y1 = a.slice(0, 4), y2 = b.slice(0, 4);
  return y1 === y2 ? y1 : `${y1}–${y1.slice(0, 2) === y2.slice(0, 2) ? y2.slice(2) : y2}`;
}
/* the money twist (ruling R3): both facts from the record, the two end values and the count of breaks of the floor */
export function twist(rec, his = "your") {
  const m = rec && rec.money, move = rec && rec.move;
  if (!m || !move || num(m.end_with_move) === null || num(m.end_today) === null) return null;
  const n = m.breaches.length;
  const ended = m.end_with_move > m.end_today ? "higher" : m.end_with_move < m.end_today ? "lower" : "level";
  const lines = [`Ended ${ended}.`, n ? `Broke ${his} floor ${timesWord(n)} on the way.` : `Never broke ${his} floor on the way.`];
  if (ended === "higher" && n) lines.push("Both are true.");
  return { ended, breaks: n, lines };
}

export const CANONICAL_FORM = "proofs.canonical_json: keys sorted, no spaces, integral numbers as integers, other numbers to 10 " +
  "decimals with trailing zeros stripped (ties to even), -0 as 0; then SHA-256 of the UTF-8 bytes";
/* the downloaded file: the record, its seal, how the seal is made and one line that checks it (run from the repository) */
export function downloadFile(rec, seal) {
  const id = String((rec && rec.run && rec.run.run_id) || "run").replace(/[^\w-]/g, "");
  const name = `epicentre-record-${id}.json`;
  const check = `python3 -c "import json, hashlib, proofs; d = json.load(open('${name}')); ` +
    `print(hashlib.sha256(proofs.canonical_json(d['record']).encode('utf-8')).hexdigest() == d['sha256'])"`;
  const body = { record: rec, sha256: seal, canonical_form: CANONICAL_FORM, check };
  return { name, type: "application/json", text: JSON.stringify(body, null, 2) + "\n" };
}
