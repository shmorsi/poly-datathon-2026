/* #record, the decision record: the end card (lane U9, ruling R6). One page the investor keeps and a broker can audit: the
   investor (fictional), the move, the limits and who set them, the verdict in this replay today and with the move, the money
   twist, the deciding checks, every number with its source (fact id, trace step, data source), the data version, the receipt
   and guardrail status, and a SHA-256 seal of the canonical record (web/lib/record.js, byte for byte proofs.canonical_json).
   "Edit a number" makes the card's numbers editable: any change reseals the record as you type and the seal breaks.
   Download record (JSON) and Print (a clean print sheet = the PDF). Nothing is stored: storeRecord() is the one hook a live
   server may implement after the lead's go (a private versioned bucket, rulings R6 and R15); until then it stores nothing.
   mount(el, store) re-renders when the store's result (or view) changes. Reads globalThis.PF at call time. */
import { buildRecord, sealOf, setAt, parseEdit, changedDigits, twist, replayYears, downloadFile, shownStatus, limitChanges, LIMIT_WORDS,
  STATEMENT, DISCLAIMER, HISTORY, FICTION, TYPED } from "../lib/record.js";
import { head, details, mean, marks, term } from "./clarity.js";
import { standingLine } from "../lib/status.js";
import { keepRanges, plain } from "../lib/meaning.js";

const NS = "http://www.w3.org/2000/svg";
const motionOn = () => globalThis.EPI_MOTION !== false && !matchMedia("(prefers-reduced-motion: reduce)").matches;

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false && kid !== "") el.append(kid.nodeType ? kid : String(kid));
  return el;
}
function s(tag, attrs, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined && v !== false) el.setAttribute(k, String(v));
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}
const icon = (id, cls) => s("svg", { class: `icon${cls ? " " + cls : ""}`, "aria-hidden": "true", focusable: "false" }, s("use", { href: `#${id}` }));
const kindMark = (kind) => {
  const m = globalThis.PF.markerOf(kind);
  return h("span", { class: "rec-kind", "data-kind": kind || "none" }, s("svg", { class: "kind", "aria-hidden": "true", focusable: "false" }, s("use", { href: `#${m.icon}` })), m.word);
};

/* a number as the card prints it, in the unit of its record value */
function show(raw, unit) {
  const f = globalThis.PF.fmt;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return raw === null || raw === undefined ? "" : String(raw);
  switch (unit) {
    case "pct": return f.pct(raw);
    case "share": return f.share(raw);
    case "CAD": return f.money(raw);
    case "days": return f.days(raw);
    case "years": return f.years(raw);
    case "count": return raw.toLocaleString("en-CA", { maximumFractionDigits: 1 });
    case "pp": return f.pct(raw).replace(/%$/, "pp");
    case "score": return raw.toFixed(2);
    default: return String(raw);
  }
}
const UNIT_OF_FACT = { pct: "pct", CAD: "CAD", days: "days", years: "years", count: "count", pp: "pp" };

/* every number on the card: one span per record value, registered by its path so "Edit a number" can reach it */
function numbers() {
  const reg = new Map();
  /* neg: the card prints the value's size ("a 15 % fall"), the record keeps its sign (-0.15); an edit keeps the sign too */
  const make = (path, unit, raw, opts) => {
    if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
    const neg = !!(opts && opts.neg), text = show(neg ? -raw : raw, unit);
    if (!text) return null;
    const el = h("span", { class: "num rec-n", "data-path": path, text });
    const list = reg.get(path) || { unit, raw, text, neg, els: [] };
    list.els.push(el);
    reg.set(path, list);
    return el;
  };
  return { make, reg };
}

// ---- the card, built from the record (never from page state) --------------------------------------------------------
const dateText = (iso) => globalThis.PF.fmt.date(iso) || iso || "";
const lampOf = (key) => (key === null || key === undefined ? null : globalThis.PF.VERDICT[key] || null);
const block = (cls, title, ...kids) => h("section", { class: `rec-block ${cls}` }, title ? h("h4", { class: "rec-h", text: title }) : null, ...kids);

/* a person's name, or null for a case label such as "Too Canadian?" (it names the question, not an investor) */
const personOf = (rec) => (rec.investor.name && !/\?$/.test(rec.investor.name) ? rec.investor.name : null);

function whoBlock(rec, v, N) {
  const i = rec.investor, person = personOf(rec);
  return h("div", { class: "rec-who" },
    h("h3", { class: "rec-name" }, person || (i.name ? `\u201c${i.name}\u201d` : "This investor"),
      person && i.age !== null ? [", ", N.make("investor.age", "count", i.age)] : null),
    h("p", { class: "rec-wholine" }, "Fictional investor. ", i.amount !== null ? [N.make("investor.amount", "CAD", i.amount),
      replayYears(rec) ? keepRanges(` replayed on real ${replayYears(rec)} history.`) : " replayed on real history."] : null));   // the dates: in the annex
}

function askBlock(rec, v, N, part) {
  const m = rec.move, sh = rec.shock, person = personOf(rec);
  const kids = [];
  if (part === "move") {
    if (m) {
      const scaled = m.op === "replace" && m.from_ticker ? `, in place of ${m.from_ticker}` : "; the other lines scaled down in proportion";
      kids.push(h("p", { class: "rec-moveline" },
        h("span", { class: "rec-move" }, `${m.name} to `, N.make("move.weight", "share", m.weight)),
        m.today_weight !== null ? [" from ", N.make("move.today_weight", "share", m.today_weight), " today"] : null, `${scaled}.`));
      kids.push(h("p", { class: "rec-fiction", text: FICTION }));
    } else kids.push(h("p", { class: "rec-moveline", text: "No move: the question replays your mix as it is." }));
    return block("rec-ask rec-ess-move", null, ...kids);
  }
  if (rec.question) kids.push(h("p", { class: "rec-qlabel", text: person ? `${person}\u2019s question` : "The question" }),
    h("blockquote", { class: "rec-q" }, h("p", { text: `“${rec.question}”` })));
  const how = { bedrock: "Read from the question by the AI reader (Claude on Amazon Bedrock); code computed every number.",
    fallback: "Read from the question by the keyword rules, with the AI reader off; code computed every number." }[rec.reading && rec.reading.method];
  if (how) kids.push(h("p", { class: "rec-read", text: how }));
  const ca = rec.canada;
  if (m && ca && ca.with_move !== null) kids.push(h("p", { class: "rec-canada" }, "Canada: ", N.make("canada.today", "pct", ca.today), " of the money today, ",
    N.make("canada.with_move", "pct", ca.with_move), " with the move."));
  if (sh && sh.label) kids.push(h("p", { class: "rec-shock" }, "The shock you asked about: ", h("strong", { text: sh.label }),
    sh.episodes !== null ? [", ", N.make("shock.episodes", "count", sh.episodes), " earlier episodes on record."] : "."));
  return block("rec-ask", null, ...kids);
}

function verdictBlock(rec, v) {
  const one = (label, key, quiet) => {
    const l = lampOf(key);
    return l ? h("div", { class: `rec-lamp${quiet ? " is-secondary" : ""}`, "data-tone": l.tone }, h("span", { class: "rec-lamp-label", text: label }),
      h("span", { class: "rec-lamp-word" }, icon(l.icon), h("span", { class: "verdict", text: l.word }))) : null;
  };
  const years = replayYears(rec);
  const pair = rec.move ? [one("Today’s mix", rec.verdict.today, true), h("span", { class: "rec-arrow", "aria-hidden": "true", text: "→" }),
    one("With the move", rec.verdict.with_move)] : [one("Your mix", rec.verdict.mix)];
  return block("rec-verdict", null, h("div", { class: "rec-lamps" }, pair),
    years ? h("p", { class: "rec-replay", text: `in this ${years} replay` }) : null,
    h("p", { class: "standing-line rec-standing", text: standingLine(!!rec.move) }));
}

function moneyBlock(rec, v, N, part) {
  const m = rec.money, tw = twist(rec, "your"), kids = [];
  if (part === "twist") return tw ? h("p", { class: "rec-twist" }, tw.lines.slice(0, 2).join(" "), tw.lines[2] ? h("span", { class: "rec-both", text: tw.lines[2] }) : null) : null;
  const rows = [];
  if (tw) rows.push(h("li", null, "With the move it ended at ", N.make("money.end_with_move", "CAD", m.end_with_move),
    "; today’s mix at ", N.make("money.end_today", "CAD", m.end_today), ", from ", N.make("investor.amount", "CAD", rec.investor.amount), "."));
  m.breaches.forEach((b, i) => rows.push(h("li", { class: "rec-break" }, N.make(`money.breaches.${i}.depth`, "pct", b.depth),
    ` from its high, ${dateText(b.peak_date)} to ${dateText(b.trough_date)}.`)));     // R35: never "the same fall on your amount"
  if (!m.breaches.length) {
    const w = m.worst;
    rows.push(w ? h("li", null, rec.move ? "With the move, the worst fall was " : "Your mix\u2019s worst fall was ", N.make("money.worst.depth", "pct", w.depth),
      w.peak_date && w.trough_date ? ` from its high, ${dateText(w.peak_date)} to ${dateText(w.trough_date)}` : "", ". It never broke your floor.")
      : h("li", { text: `In this replay the ${rec.move ? "move" : "mix"} never broke your floor.` }));
  }
  return block("rec-money", "The money", ...kids, rows.length ? h("ul", { class: "rec-list" }, rows) : null,
    h("p", { class: "rec-note", text: HISTORY }));
}

function checksBlock(rec, v, N, onFact) {
  /* every check, in the checklist's order (PF.view's rows), each with the checklist's word, icon and tier (one vocabulary, R20) */
  const order = v.rows.map((x) => rec.checks.findIndex((c) => c.rule === x.rule)).filter((i) => i >= 0);
  const rest = rec.checks.map((c, i) => i).filter((i) => !order.includes(i));
  const unit = (rule) => (["max_drawdown", "scenario_stress"].includes(rule) ? "pct" : rule === "recovery" ? "days" : rule === "short_horizon" ? "years" : "share");
  const factBtn = (id) => h("button", { type: "button", class: "rec-fact", "aria-label": `Open the trace of ${id}`, onclick: () => onFact(id), text: id });
  const rows = [...order, ...rest].map((i) => {
    const c = rec.checks[i], st = shownStatus(c.status, c.tier), u = unit(c.rule), tier = (v.rows.find((x) => x.rule === c.rule) || {}).tier || "";
    if (!st) return null;
    return h("li", { class: "rec-check", "data-tone": st.tone, "data-rule": c.rule },
      h("span", { class: "rec-st" }, icon(st.icon), st.word),
      h("span", { class: "rec-cn", text: c.name || c.rule }),
      h("span", { class: "rec-cv" }, N.make(`checks.${i}.value`, u, c.value), c.limit !== null ? [" against ", N.make(`checks.${i}.limit`, u, c.limit)] : null),
      h("span", { class: "rec-ct" }, h("span", { class: "rec-tier", text: tier }), c.facts.map(factBtn)));
  }).filter(Boolean);
  return block("rec-checks", rows.length ? `All ${rows.length} checks, the most serious first` : "The checks",
    rows.length ? h("ul", { class: "rec-rows" }, rows) : h("p", { text: "No check was run." }),
    rows.length ? h("p", { class: "rec-legend", text: "Only a hard limit that broke reads Outside; a soft limit, a preference or a warning level can only add a caveat." }) : null);
}

function limitsBlock(rec, v, N) {
  const L = rec.limits, amount = rec.investor.amount;
  const bys = new Set(Object.values(L).filter((x) => x && x.value !== null).map((x) => x.set_by)), mixed = bys.size > 1;
  const tag = (by) => (mixed && by === TYPED ? h("span", { class: "rec-by is-typed", text: "set by you" }) : null);   // one line says the rest
  const row = (name, by, ...value) => h("li", { class: mixed ? null : "is-plain" }, h("span", { class: "rec-ln", text: name }), h("span", { class: "rec-lv" }, ...value), tag(by));
  const rows = [];
  /* R35: two limits, as the workshop teaches: the rule (tolerance) and what you can afford to lose (capacity) */
  if (L.floor.value !== null) rows.push(row("Your rule", L.floor.set_by, h("span", { class: "rec-floor" }, "no fall of more than ",
    N.make("limits.floor.value", "share", L.floor.value, { neg: L.floor.value < 0 }), " from any high")));
  if (L.floor.dollars !== null) rows.push(row("What you can afford to lose", L.floor.set_by, N.make("limits.floor.dollars", "CAD", L.floor.dollars),
    amount !== null ? [" of ", N.make("investor.amount", "CAD", amount)] : null));
  if (L.scenario_stress.value !== null) rows.push(row("Shock limit", L.scenario_stress.set_by, N.make("limits.scenario_stress.value", "share", L.scenario_stress.value, { neg: L.scenario_stress.value < 0 }), " in one shock: a rule of thumb, half your rule"));
  if (L.single_stock.value !== null) rows.push(row("One company", L.single_stock.set_by, "up to ", N.make("limits.single_stock.value", "share", L.single_stock.value)));
  if (L.sector.value !== null) rows.push(row("One sector", L.sector.set_by, "up to ", N.make("limits.sector.value", "share", L.sector.value)));
  if (L.crypto.value !== null) rows.push(row("Crypto", L.crypto.set_by, "up to ", N.make("limits.crypto.value", "share", L.crypto.value)));
  const one = !mixed && bys.size ? [...bys][0] : null;
  /* compliance: a persona's limits come from its profile, never typed by the client; the record's own set_by says which */
  const intro = mixed ? "The limits marked set by you are yours; every other limit here is assumed from the profile, not set by you. None is read from an account."
    : one === TYPED ? "Your limits here are set by you, never read from an account."
    : "Your limits here are assumed from the profile, not set by you, and never read from an account.";
  const after = (rec.after_answer || []).map((c, i) => h("p", { class: "rec-after" }, icon("i-warn"),
    h("span", null, `You changed your ${LIMIT_WORDS[c.limit]} from `, N.make(`after_answer.${i}.from`, "share", c.from), " to ",
      N.make(`after_answer.${i}.to`, "share", c.to), " after seeing the answer.")));
  return block("rec-limits", after.length ? "The limits, as first shown" : "The limits", h("p", { class: "rec-typed", text: intro }),
    rows.length ? h("ul", { class: "rec-rows rec-limit-rows" }, rows) : h("p", { text: "No limits were set, so nothing was checked." }), after);
}

function versionBlock(rec) {
  const r = rec.run, dl = h("dl", { class: "rec-dl" });
  const add = (k, val, cls) => { if (val) dl.append(h("div", null, h("dt", { text: k }), h("dd", { class: cls || null, text: val }))); };
  add("Run", r.run_id, "num");
  add("Data to", dateText(r.as_of));
  add("Replay", rec.replay.first && rec.replay.last ? `${dateText(rec.replay.first)} to ${dateText(rec.replay.last)}` : null);
  add("Code", r.commit, "num");
  add("Recorded", r.recorded_on ? `on ${r.recorded_on}` : null);
  return block("rec-version", "Data version", dl);
}

const corrections = (d) => (d === null || d < 2 ? "on the first draft" : d === 2 ? "after one correction" : `after ${d - 1} corrections`);
const guardWord = (x) => (!x ? null : x.blocked ? "blocked" : x.action === "NONE" ? "passed" : (x.action || "").toLowerCase().replace(/_/g, " "));

function checkedBlock(rec, N) {
  const rc = rec.receipt, g = rec.guardrail, kids = [];
  if (rc && rc.total !== null) kids.push(h("p", null, h("strong", { text: "Number check: " }), N.make("receipt.verified", "count", rc.verified), " of ",
    N.make("receipt.total", "count", rc.total), ` numbers in the explanation traced to the data, ${corrections(rc.drafts)}`,
    rc.missing ? [`; ${rc.missing === 1 ? "one required phrase" : rc.missing + " required phrases"} still missing.`] : "."));
  if (g) {
    /* juror fix (approved): never "passed" beside a score under its threshold. The output's grounding score is advisory
       (ruling R21): it is named as such, next to what does gate the numbers, the receipt's own count. */
    const gi = guardWord(g.input), o = g.output || {}, scored = typeof o.grounding === "number";
    const go = scored && !o.blocked ? null : guardWord(g.output);
    const when = rec.run.recorded_on ? `recorded on ${rec.run.recorded_on}` : "recorded with this run";
    const said = [gi ? `input ${gi}` : null, go ? `output ${go}` : null].filter(Boolean).join(", ");
    /* the grounding score shows once on the page, in #how's output-guardrail station (controller, 12:35); the card says the
       plain line, and the downloaded record keeps the full guardrail block */
    kids.push(h("p", null, h("strong", { text: "Guardrails, " + when + ": " }), said ? `${said}.` : null,
      scored && rc && typeof rc.verified === "number" && typeof rc.total === "number"
        ? [said ? " " : null, "Every number was checked by code (", N.make("receipt.verified", "count", rc.verified), " of ",
          N.make("receipt.total", "count", rc.total), ")."] : null,
      [g.input && g.input.request_id, o.request_id].some(Boolean) ? h("span", { class: "rec-ids" }, " Request ids: ",
        [g.input && g.input.request_id, o.request_id].filter(Boolean).map((id) => h("span", { class: "num", text: id })).reduce((a, x) => (a.length ? [...a, ", ", x] : [x]), []), ".") : null));
  }
  if (!kids.length) kids.push(h("p", { text: "No explanation was written for this saved run, so there is no number check and no guardrail result to record." }));
  return block("rec-checked", "Checked by code and by the guardrails", ...kids);
}

/* every number with its source, grouped by the data source its trace row names (the full text once per group) */
function sourcesBlock(rec, N, onFact) {
  const groups = new Map();
  const NONE = "Read from the Result key named; no trace row of its own";
  rec.numbers.forEach((x, i) => { const k = (x.source && rec.sources[x.source]) || NONE; (groups.get(k) || groups.set(k, []).get(k)).push([x, i]); });
  const list = h("ol", { class: "rec-src" });
  for (const [source, xs] of groups) {
    list.append(h("li", { class: "rec-src-g" }, h("p", { class: "rec-src-t", text: plain(source) }),
      h("ul", null, xs.map(([x, i]) => h("li", { class: "rec-src-row" },
        x.fact ? h("button", { type: "button", class: "rec-fact", "aria-label": `Open the trace of ${x.fact}`, onclick: () => onFact(x.fact), text: x.fact })
          : h("span", { class: "rec-fact is-key", title: "A Result key, not a facts row", text: "key" }),
        h("span", { class: "rec-sl", text: plain(x.label || "") }),
        N.make(`numbers.${i}.value`, UNIT_OF_FACT[x.unit] || "count", x.value),
        kindMark(x.kind),
        h("span", { class: "rec-step" }, [x.trace && x.trace !== x.fact ? `${x.trace}` : null, x.step, x.tool].filter(Boolean).join(" "),
          x.key ? h("span", { class: "rec-key", text: x.key }) : null))))));
  }
  return h("details", { class: "rec-block rec-sources" }, h("p", { class: "rec-annex", text: "Annex to the decision record" }),
    h("summary", null, h("span", { class: "rec-h", text: "Every number on this record, with its source" }), h("span", { class: "rec-count num", text: String(rec.numbers.length) }),
      h("span", { class: "rec-show", "aria-hidden": "true" })),
    h("p", { class: "rec-src-how", text: "Each number names its facts row or its Result key, the trace step and tool that computed it, and the data it was read from." }), marks(), list);
}

function footBlock(rec, live) {
  const kept = live ? "Nothing is stored unless you keep this tamper-proof record." : "Nothing here is stored: this record exists in this page until you download or print it.";
  return h("footer", { class: "rec-foot" }, h("p", { class: "rec-statement", text: rec.statement || STATEMENT }),
    h("p", null, [rec.move ? FICTION : null, HISTORY, kept].filter(Boolean).join(" ")),
    h("p", { class: "rec-disclaimer", text: rec.disclaimer || DISCLAIMER }));
}

/* what each number on the card is, for the line that names the changed ones */
const FIXED = { "investor.amount": "the amount", "investor.age": "the age", "move.weight": "the size of the move", "move.today_weight": "today\u2019s weight",
  "shock.episodes": "the count of earlier episodes", "money.end_with_move": "the end value with the move", "money.end_today": "the end value of today\u2019s mix",
  "limits.floor.value": "the floor", "limits.floor.dollars": "the floor in dollars", "limits.scenario_stress.value": "the shock limit",
  "limits.single_stock.value": "the one-company limit", "limits.sector.value": "the one-sector limit", "limits.crypto.value": "the crypto limit",
  "receipt.verified": "the number check\u2019s traced count", "receipt.total": "the number check\u2019s total", "guardrail.output.grounding": "the grounding score",
  "guardrail.output.threshold": "the grounding threshold", "canada.today": "Canada\u2019s share today", "canada.with_move": "Canada\u2019s share with the move",
  "money.worst.depth": "the worst fall", "money.worst.loss_dollars": "the worst fall in dollars" };
function labelOf(rec, path) {
  if (FIXED[path]) return FIXED[path];
  const p = path.split(".");
  if (p[0] === "money" && p[1] === "breaches") return `break ${+p[2] + 1} of the floor${p[3] === "depth" ? "" : " in dollars"}`;
  if (p[0] === "after_answer") { const c = (rec.after_answer || [])[+p[1]]; return `your ${c ? LIMIT_WORDS[c.limit] : "limit"} ${p[2] === "from" ? "as first shown" : "as changed"}`; }
  if (p[0] === "checks") { const c = rec.checks[+p[1]]; return `the ${(c && c.name ? c.name : "check").toLowerCase().replace(/^your /, "")} ${p[2] === "limit" ? "limit" : "value"}`; }
  if (p[0] === "numbers") { const n = rec.numbers[+p[1]]; return n ? `${n.fact ? n.fact + ", " : ""}${plain(n.label || "a number").replace(/^./, (c) => c.toLowerCase())}` : "a number"; }
  return path;
}

// ---- the seal: 64 hex digits on a ring that splits when the record no longer matches the run --------------------------
function sealBlock() {
  const C = 100, R_OUT = 95, R_TXT = 83, R_IN = 71;
  const half = (right, r) => s("path", { class: "rec-ring", d: `M${C} ${C - r}A${r} ${r} 0 0 ${right ? 1 : 0} ${C} ${C + r}` });
  const gL = s("g", { class: "rec-half rec-half-l" }, half(false, R_OUT), half(false, R_IN));
  const gR = s("g", { class: "rec-half rec-half-r" }, half(true, R_OUT), half(true, R_IN));
  const chars = [];
  for (let i = 0; i < 64; i++) {
    const a = ((i + 0.5) * 360) / 64;                       // degrees clockwise from the top
    const t = s("text", { class: "rec-hx", x: C, y: C - R_TXT, transform: `rotate(${a.toFixed(3)} ${C} ${C})`, "text-anchor": "middle",
      "dominant-baseline": "central", style: `--i:${i}` });
    (a < 180 ? gR : gL).append(t);
    chars.push(t);
  }
  const crack = s("path", { class: "rec-crack", d: "M100 1l-3.5 7 4 6.5-4 6.5 3.5 8.5M100 170l3.5 7-4 6.5 4 6.5-3.5 9" });
  const useI = s("use", { href: "#i-in", x: 88, y: 66, width: 24, height: 24 });
  const word = s("text", { class: "rec-mid-w", x: C, y: 110, "text-anchor": "middle" }, "Intact");
  const sub = s("text", { class: "rec-mid-s", x: C, y: 128, "text-anchor": "middle" }, "SHA-256");
  const svg = s("svg", { class: "rec-ring-svg", viewBox: "0 0 200 200", role: "img", "aria-label": "The record’s fingerprint" }, gL, gR, crack,
    s("g", { class: "rec-mid" }, useI, word, sub));
  const status = h("p", { class: "rec-seal-status", role: "status" });
  const sealed = h("p", { class: "rec-hash" }, h("span", { class: "rec-hash-l", text: "Fingerprint of the run" }), h("span", { class: "num rec-hash-v" }));
  const now = h("p", { class: "rec-hash is-now", hidden: true }, h("span", { class: "rec-hash-l", text: "This record now" }), h("span", { class: "num rec-hash-v" }));
  const how = h("p", { class: "rec-hash-how" });
  const changes = h("p", { class: "rec-changes", hidden: true });
  const oeo = h("p", { class: "rec-oeo", text: "For an order-execution-only broker: shown before the order, kept after it." });
  const el = h("figure", { class: "rec-seal" }, svg, h("figcaption", null, status, changes, oeo));
  const hexes = h("div", { class: "rec-hexes" }, sealed, now, how);
  const digits = (target, hex, diff) => {
    target.replaceChildren(...Array.from(hex, (c, i) => [i && i % 8 === 0 ? (i % 32 === 0 ? h("br") : " ") : null,
      diff && diff[i] ? h("mark", { text: c }) : c]).flat().filter((x) => x !== null));
  };
  function paint(hexNow, hexRun, by, changed) {
    const broken = hexNow !== hexRun, diff = changedDigits(hexRun, hexNow);
    chars.forEach((t, i) => { t.textContent = hexNow[i] || ""; t.classList.toggle("is-changed", broken && diff[i]); });
    el.classList.toggle("is-broken", broken);
    useI.setAttribute("href", broken ? "#i-out" : "#i-in");
    word.textContent = broken ? "Changed" : "Intact";
    svg.setAttribute("aria-label", broken ? "The record’s fingerprint no longer matches" : `The record’s fingerprint: SHA-256 ${hexRun}`);
    status.replaceChildren(icon(broken ? "i-out" : "i-in"), h("strong", { text: broken ? "Record changed:" : "Record intact:" }),
      broken ? " this record no longer matches the run." : " this record matches the run.");
    digits(sealed.lastChild, hexRun, null);
    now.hidden = !broken;
    const list = Array.isArray(changed) ? changed : [];
    changes.hidden = !broken || !list.length;
    changes.textContent = list.length ? `Changed: ${list.slice(0, 3).join("; ")}${list.length > 3 ? `; and ${list.length - 3} more` : ""}.` : "";
    if (broken) digits(now.lastChild, hexNow, diff);
    how.textContent = `Fingerprinted with SHA-256; stored under S3 Object Lock in the live app. The hash is of the record in canonical JSON (proofs.canonical_json), computed here by ${by === "Web Crypto" ? "the browser\u2019s Web Crypto" : "the page\u2019s own script"}; the downloaded file carries a one-line check.`;
  }
  return { el, paint, chars, hexes };
}

/* while editing: one status line in the flow, right after the row being edited (so the number typed in never moves), never
   over the card's text */
function liveLine(restore) {
  const ic = s("svg", { class: "icon", "aria-hidden": "true", focusable: "false" }, s("use", { href: "#i-out" }));
  const note = h("span", { class: "rec-live-n" }), hex = h("span", { class: "num rec-live-hex" });
  const el = h("p", { class: "rec-live", hidden: true }, ic, h("strong", { text: "Record changed:" }), note, hex, restore);
  function paint(now, n) {
    el.hidden = !n;
    note.textContent = n === 1 ? "one number changed; its fingerprint is now" : `${n} numbers changed; its fingerprint is now`;
    hex.textContent = `${now.slice(0, 16)}\u2026`;
  }
  function place(node) {                         /* inside the number's list row, else right after its paragraph or heading */
    const row = node.closest("li");
    if (row) { if (el.parentNode !== row) row.append(el); return; }
    const host = node.closest("p, h3, blockquote");
    if (host && host.nextSibling !== el) host.after(el);
  }
  return { el, paint, place };
}

/* the one storage hook (rulings R6, R15; lane B6's POST /api/record: a private, versioned bucket, the record as
   proofs.canonical_json under records/<run_id>/<sha256>.json). Only in live mode and only when the investor asks (red gate 6:
   nothing typed is stored unless the investor seals it). The vault's own SHA-256 must equal the page's seal: it is shown.
   Returns {stored, same, key, version, text}; it never throws. */
const mask = (id) => (id.length > 10 ? `${id.slice(0, 4)}\u2026${id.slice(-4)}` : id);
export async function storeRecord(record, sha256, opts) {
  if (!opts || opts.mode !== "live") return { stored: false, text: "Storage needs the live app: this page replays saved runs. Download the record or print it." };
  let res, body = null;
  try {
    res = await fetch("/api/record", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ record, sha256 }) });
    body = await res.json().catch(() => null);
  } catch (e) {
    return { stored: false, text: "The server could not be reached, so nothing was kept. Download the record or print it." };
  }
  if (res.ok && body && typeof body.sha256 === "string" && (body.status === "stored" || (body.status === undefined && (body.key || body.version_id)))) {
    const same = body.sha256 === sha256, version = typeof body.version_id === "string" ? body.version_id : null;
    const until = typeof body.retain_until === "string" && /^\d{4}-\d{2}-\d{2}/.test(body.retain_until) ? globalThis.PF.fmt.date(body.retain_until.slice(0, 10)) : null;
    return { stored: true, same, key: body.key || null, version, text: same
      ? `Kept in the private, versioned record vault${version ? `, version ${mask(version)}` : ""}${until ? `, locked until ${until}` : ""}. The vault computed the same fingerprint.`
      : "Kept, but the vault computed another fingerprint than this page: the two copies differ. Download this one too." };
  }
  if (res.status === 404) return { stored: false, text: "This server keeps no records yet. Download the record or print it." };
  const msg = body && typeof body.message === "string" && body.message.trim() ? body.message.trim() : null;
  return { stored: false, text: msg || "Nothing was kept. Download the record or print it." };
}

function download(rec, seal) {
  const f = downloadFile(rec, seal);
  const url = URL.createObjectURL(new Blob([f.text], { type: f.type }));
  const a = h("a", { href: url, download: f.name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* Print: only the record, on white (web/css/record.css @media print); every other part of the page sits out the print */
function printRecord(root, details) {
  const out = [], html = document.documentElement, wasOpen = details ? details.open : false;
  for (let n = root; n && n.parentElement && n !== document.body; n = n.parentElement)
    for (const sib of n.parentElement.children) if (sib !== n) { sib.classList.add("rec-noprint"); out.push(sib); }
  if (details) details.open = true;
  html.classList.add("rec-printing");
  let done = false;
  const back = () => {
    if (done) return;
    done = true;
    out.forEach((x) => x.classList.remove("rec-noprint"));
    html.classList.remove("rec-printing");
    if (details) details.open = wasOpen;
    removeEventListener("afterprint", back);
  };
  addEventListener("afterprint", back);
  try { print(); } finally { setTimeout(back, 1000); }   /* the classes only act in print: a late clean-up shows nothing */
}

// ---- mount ----------------------------------------------------------------------------------------------------------
const commitOf = (state) => {
  const v = state && state.view, meta = document.querySelector('meta[name="epicentre-commit"]');
  return (v && v.commit) || (meta && /^[0-9a-f]{7,40}$/i.test(meta.content) ? meta.content.slice(0, 7) : null);
};
const negOf = (x) => (typeof x === "number" ? -x : x);

export function mount(el, store) {
  el.classList.add("rec");
  let queued = false, seq = 0, active = null;          /* active: the rendered card's own state (its observer, its seal) */
  const firsts = new Map();                              /* run_id -> the Result as first shown (before any limit was changed) */
  const schedule = () => { if (!queued) { queued = true; queueMicrotask(() => { queued = false; render(store.get()); }); } };

  function render(state) {
    seq++;
    if (active && active.observer) active.observer.disconnect();
    const now = state && state.result, pf = globalThis.PF;
    const id = now && typeof now.run_id === "string" ? now.run_id : null;
    if (id && !firsts.has(id)) firsts.set(id, now);
    const r = (id && firsts.get(id)) || now;               /* "your calmer self": the record keeps the limits first shown */
    const v = r && pf ? pf.view(r) : null;
    if (!r || !v || v.stop || !v.ok) { el.replaceChildren(); el.hidden = true; active = null; return; }
    el.hidden = false;
    const rec = buildRecord(r, { commit: commitOf(state), after: limitChanges(r, now) }), N = numbers(), mine = seq;
    const onFact = (id) => store.set({ thread: id });
    const seal = sealBlock();
    const toggle = h("button", { type: "button", class: "linkbtn rec-textbtn rec-edit", "aria-pressed": "false" }, h("span", { class: "rec-switch", "aria-hidden": "true" }), "Edit a number");
    const restore = h("button", { type: "button", class: "linkbtn rec-restore", hidden: true, text: "Put the run’s numbers back" });
    const liveSeal = liveLine(restore);
    const dl = h("button", { type: "button", class: "linkbtn rec-textbtn rec-dl-btn" }, icon("i-down"), "Download record (JSON)");
    const pr = h("button", { type: "button", class: "linkbtn rec-textbtn rec-print" }, "Print");
    const keep = h("button", { type: "button", class: "btn btn-primary rec-keep", text: "Keep this tamper-proof record" });   // the one filled button (design director, item 11)
    const keepBox = h("div", { class: "rec-keepbox" }, keep, h("span", { class: "rec-keepnote", text: "private, versioned Amazon S3 (live app only)" }));
    const kept = h("p", { class: "rec-kept", role: "status", hidden: true });
    const isLive = state.mode === "live";
    const hint = h("p", { class: "rec-hint", hidden: true, text: "Click any underlined number and type: the fingerprint is recomputed as you type. Esc puts a number back." });
    const sources = sourcesBlock(rec, N, onFact);
    const name = personOf(rec);
    /* R22: "What do you keep?" The essentials (who, the move, the verdict today and with it, the money twist), the seal ring and
       "Edit a number" stay; the annex (the question, the money in rows, the limits, every check, the data version, the receipt,
       every number with its source, the seal's digits) folds into "Show the details" (it always prints) */
    const annex = details("record", store, [
      h("div", { class: "rec-grid rec-annex-grid" }, askBlock(rec, v, N, "rest"),
        h("div", { class: "rec-col rec-col-a" }, moneyBlock(rec, v, N), limitsBlock(rec, v, N)),
        h("div", { class: "rec-col rec-col-b" }, checksBlock(rec, v, N, onFact), versionBlock(rec)),
        checkedBlock(rec, N), seal.hexes, h("div", { class: "rec-foot-print", "aria-hidden": "true" }, footBlock(rec, isLive)), sources)],
      { label: "The decision record: the annex" });
    const card = h("article", { class: "rec-card", "aria-label": `Decision record${name ? " for " + name : ""}` },
      h("div", { class: "rec-top" }, whoBlock(rec, v, N), h("div", { class: "rec-tools" }, toggle, dl, pr, keepBox), hint, kept),
      h("div", { class: "rec-grid rec-ess" }, h("div", { class: "rec-ess-col" }, askBlock(rec, v, N, "move"), verdictBlock(rec, v), moneyBlock(rec, v, N, "twist")), seal.el),
      annex, footBlock(rec, isLive));
    /* every number on the card says what it is (lane clarity, R22): the essentials take a tab stop, the long annex hover and tap */
    for (const [path, entry] of N.reg) for (const x of entry.els) mean(x, `${entry.text}: ${labelOf(rec, path)}, on this record.`, { focus: !x.closest(".cl-details") });
    el.setAttribute("aria-labelledby", "record-title");
    el.replaceChildren(h("div", { class: "frame rec-frame" },
      head("record-title", "What do you keep?", ["A ", term("tamper-proof record"), " (SHA-256) of this replay: every number with its source. Change one and the record shows it."]), card));

    const edits = new Map();
    const state1 = { rec, current: rec, sealed: null, by: null, editing: false, n: 0 };
    active = state1;
    const reseal = async () => {
      const my = ++state1.n;
      let cur = rec;
      for (const [p, val] of edits) cur = setAt(cur, p, val);
      const { hex, by } = await sealOf(cur);
      if (mine !== seq || my !== state1.n) return;
      state1.current = cur;
      state1.hex = hex;
      const changed = [...edits.keys()].map((p) => { const e = N.reg.get(p); return `${labelOf(rec, p)}, ${e.text} to ${e.els[0].textContent.trim() || "nothing"}`; });
      seal.paint(hex, state1.sealed, by, changed);
      liveSeal.paint(hex, edits.size);
      restore.hidden = !edits.size;
    };
    sealOf(rec).then(({ hex, by }) => {
      if (mine !== seq) return;
      state1.sealed = hex; state1.by = by; state1.hex = hex;
      seal.paint(hex, hex, by);
      if (motionOn() && "IntersectionObserver" in globalThis) {
        seal.el.classList.add("is-waiting");
        state1.observer = new IntersectionObserver((es) => {
          if (!es.some((e) => e.isIntersecting)) return;
          state1.observer.disconnect();
          seal.el.classList.remove("is-waiting");
          if (motionOn()) {                                   /* paused since: the end state at once */
            seal.el.classList.add("is-sealing");
            seal.el.querySelector(".rec-mid").addEventListener("animationend", () => seal.el.classList.remove("is-sealing"), { once: true });
          }
        }, { threshold: 0.25 });
        state1.observer.observe(seal.el);
      }
    });

    const entryOf = (node) => { const n = node && node.closest ? node.closest(".rec-n") : null; return n && N.reg.get(n.dataset.path) ? [n, N.reg.get(n.dataset.path)] : [null, null]; };
    const setText = (entry, text, except) => entry.els.forEach((x) => { if (x !== except) x.textContent = text; });
    const mark = (path, entry) => entry.els.forEach((x) => x.classList.toggle("is-edited", edits.has(path)));
    function setEditing(on) {
      state1.editing = on;
      toggle.setAttribute("aria-pressed", String(on));
      card.classList.toggle("is-editing", on);
      hint.hidden = !on;
      if (!on) liveSeal.el.hidden = true;
      for (const [path, entry] of N.reg) for (const x of entry.els) {
        if (on) {
          try { x.contentEditable = "plaintext-only"; } catch (e) { x.contentEditable = "true"; }
          x.setAttribute("role", "textbox");
          x.setAttribute("aria-label", `Edit ${labelOf(rec, path)}, now ${x.textContent}`);
          x.spellcheck = false;
          x.inputMode = "decimal";
        } else { x.removeAttribute("contenteditable"); x.removeAttribute("role"); x.removeAttribute("aria-label"); x.removeAttribute("inputmode"); }
      }
      if (!on) putBack();
    }
    function putBack() {
      for (const [path, entry] of N.reg) { setText(entry, entry.text); edits.delete(path); mark(path, entry); }
      reseal();
    }
    toggle.addEventListener("click", () => setEditing(!state1.editing));
    restore.addEventListener("click", putBack);
    dl.addEventListener("click", () => download(state1.current, state1.sealed));
    pr.addEventListener("click", () => printRecord(el, sources));
    keep.addEventListener("click", async () => {
      kept.hidden = false;
      if (state1.current !== rec) { kept.textContent = "Put the run\u2019s numbers back first: only a record that matches its fingerprint is kept."; return; }
      if (store.get().mode !== "live") { kept.textContent = "Storage needs the live app: this page replays saved runs. Download the record or print it."; return; }
      keep.disabled = true;
      kept.textContent = "Keeping\u2026";
      const out = await storeRecord(rec, state1.sealed, { mode: store.get().mode });
      if (mine !== seq) return;
      keep.disabled = false;
      kept.textContent = out.text;
      kept.classList.toggle("is-kept", !!out.stored && out.same);
    });
    card.addEventListener("input", (e) => {
      const [node, entry] = entryOf(e.target);
      if (!node || !state1.editing) return;
      const path = node.dataset.path, text = node.textContent.replace(/\s+/g, " ").trim();
      const typed = parseEdit(text, entry.unit), value = text === entry.text ? entry.raw : entry.neg ? negOf(typed) : typed;
      if (value === entry.raw) edits.delete(path); else edits.set(path, value);
      setText(entry, node.textContent, node);
      mark(path, entry);
      liveSeal.place(node);
      reseal();
    });
    card.addEventListener("keydown", (e) => {
      const [node, entry] = entryOf(e.target);
      if (!node || !state1.editing) return;
      if (e.key === "Enter") { e.preventDefault(); node.blur(); }
      else if (e.key === "Escape") {
        e.preventDefault();
        setText(entry, entry.text);
        edits.delete(node.dataset.path);
        mark(node.dataset.path, entry);
        reseal();
      }
    });
  }

  render(store.get());
  store.on("result", schedule);
  store.on("view", schedule);
}
