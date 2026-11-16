/* EPICENTRE page helpers: pure functions, no DOM, no network.
   Loaded before app.js (exported as window.PF) and by node for tests/web_lib_test.cjs (module.exports).
   Each helper bridges the page's own shapes to the API contract (plan D Task 4 / ledger §6, §7, §9, §15). */
(function (root, factory) {
  const PF = factory();
  if (typeof module === "object" && module.exports) module.exports = PF;
  if (root) root.PF = PF;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  /* what the investor said they did in 2022 sets the risk level and the typed reaction (ledger §0, §15) */
  const RISK_FROM_2022 = { sold: "low", held: "moderate", "bought more": "high" };
  const REACTION_2022 = { sold: "sold", held: "held", "bought more": "bought" };
  const LIMIT_KEYS = ["floor", "single_stock", "sector", "crypto"];   // the only limits the investor can edit

  const num = (x) => (x === null || x === undefined || x === "" ? NaN : Number(x));

  /* the POST /api/run body: weights are fractions, the headline is folded into the question (the API has no headline field) */
  function requestBody(plan, userLimits, redteam) {
    const portfolio = {};
    for (const [ticker, pct] of Object.entries(plan.holdings || {})) {
      const w = num(pct) / 100;
      if (Number.isFinite(w) && w > 0) portfolio[ticker] = Number(w.toFixed(10));
    }
    const move = String(plan.q || "").trim(), headline = String(plan.hl || "").trim();
    const question = headline ? (move ? move + " " : "") + "Headline: " + headline : move;
    const capacity = num(plan.capacity);
    const profile = {
      goal: plan.goal,
      horizon_years: plan.horizon,
      risk: RISK_FROM_2022[plan.in_2022] || null,
      esg: !!plan.esg,
      crypto: !!plan.crypto,
      capacity: Number.isFinite(capacity) ? capacity : null,
      reaction_2022: REACTION_2022[plan.in_2022] || null,
    };
    let limits = null;
    for (const k of LIMIT_KEYS) {
      const v = userLimits ? num(userLimits[k]) : NaN;
      if (Number.isFinite(v)) (limits = limits || {})[k] = v;
    }
    return { portfolio, amount: num(plan.amount), pilot: plan.pilot || null, question, profile, limits, redteam: !!redteam };
  }

  /* the four questions of a credible explanation (spec §7): one heading per debrief section */
  const QUESTIONS = [
    { id: "data", title: "What data?" },
    { id: "why", title: "Why this verdict?" },
    { id: "limits", title: "What limits?" },
    { id: "would_change", title: "What would change the answer?" },
  ];
  const titleOf = (id) => (QUESTIONS.find((q) => q.id === id) || {}).title || "";
  const tidy = (s) => ({ text: String(s && s.text != null ? s.text : ""), kind: (s && s.kind) || "fact", refs: Array.isArray(s && s.refs) ? s.refs : [] });

  /* ledger §6 shape: sections {data|why|limits|would_change: [index into sentences]}; the prototype's list form
     [{id, title, text}] is still accepted. Sections without a sentence are left out. */
  function debriefSections(debrief) {
    if (!debrief) return [];
    const secs = debrief.sections, sentences = Array.isArray(debrief.sentences) ? debrief.sentences : [];
    if (Array.isArray(secs)) {
      return secs.filter((s) => s && s.text).map((s) => ({ id: s.id === "change" ? "would_change" : s.id, title: s.title || titleOf(s.id === "change" ? "would_change" : s.id), sentences: [tidy({ text: s.text, kind: s.kind, refs: s.refs })] }));
    }
    const out = [];
    for (const q of QUESTIONS) {
      let picked = [];
      if (secs && Array.isArray(secs[q.id])) picked = secs[q.id].map((i) => sentences[i]).filter(Boolean);
      else if (!secs) picked = sentences.filter((s) => s && s.section === q.id);
      if (picked.length) out.push({ id: q.id, title: q.title, sentences: picked.map(tidy) });
    }
    return out;
  }

  /* the navigator's blocks, in the order code ranked the checks (scenario.check_order holds rule ids, the binding one first) */
  const BLOCKS = ["floor", "risk", "diversification", "turbulence", "values", "size"];
  const RULE_BLOCK = {
    max_drawdown: "floor", recovery: "floor", short_horizon: "floor", missing_data: "floor",
    single_stock: "risk", crypto: "risk", risk_concentration: "risk",
    sector: "diversification",
    scenario_stress: "turbulence", weather: "turbulence",   // "weather" = the prototype's old id for the shock check
    esg_direct: "values", esg_indirect: "values",
  };
  function blockOrder(result) {
    const order = (result && result.scenario && Array.isArray(result.scenario.check_order) && result.scenario.check_order) || [];
    const out = [];
    for (const id of order) {
      const block = BLOCKS.includes(id) ? id : RULE_BLOCK[id];
      if (block && !out.includes(block)) out.push(block);
    }
    for (const block of BLOCKS) if (!out.includes(block)) out.push(block);
    return out;
  }

  /* tokens of one model call: Converse names (inputTokens/outputTokens) or the short names (input/output) */
  function tokensOf(usage) {
    if (!usage) return 0;
    const n = (...keys) => { for (const k of keys) { const v = Number(usage[k]); if (Number.isFinite(v)) return v; } return 0; };
    return Math.round(n("inputTokens", "input") + n("outputTokens", "output"));
  }

  /* the kinds of evidence a number or a sentence can have (spec 22): the SVG symbol to draw and the word to print beside it.
     limit and assumption share the half-filled mark (a rule the check takes as given); scenario and fiction share the ring (made up). */
  const MARKERS = {
    fact: { icon: "m-fact", word: "fact" },
    assumption: { icon: "m-assumption", word: "assumption" },
    limit: { icon: "m-assumption", word: "limit" },
    scenario: { icon: "m-fiction", word: "scenario" },
    fiction: { icon: "m-fiction", word: "fiction" },
  };
  /* an unknown or missing kind is never drawn as a fact (red gate 4): the pending ring and the word "unlabelled" */
  const markerOf = (kind) => (Object.prototype.hasOwnProperty.call(MARKERS, kind) ? MARKERS[kind] : { icon: "i-pending", word: "unlabelled" });

  /* A question that changes nothing (shock, fit, diversification) comes with series.after, baseline and tipping_point
     null (pipeline._compare). The one path drawn is then the evaluated mix: after becomes a copy of today, and the
     events' and shock families' "after" numbers read from today where the server left them empty, so every chart has
     its arrays. The page hides the "with the move" labels because moveOf(r) is null. A question with a move is untouched. */
  const finite = (x) => typeof x === "number" && Number.isFinite(x);
  function withPaths(r) {
    const s = r && r.series;
    if (!s || Array.isArray(s.after) || !Array.isArray(s.today)) return r;
    s.after = s.today.slice();
    for (const e of Array.isArray(r.events) ? r.events : []) {
      if (e && e.today && finite(e.today.trough) && !(e.after && finite(e.after.trough))) e.after = { ...e.today };
    }
    for (const t of Object.values(r.turbulence && typeof r.turbulence === "object" ? r.turbulence : {})) {
      if (t && finite(t.worst_today) && !finite(t.worst_after)) t.worst_after = t.worst_today;
    }
    return r;
  }

  /* a fraction in tenths of a percentage point, ties away from zero: governance.round_pp (pitfall 5). The toPrecision
     trims float noise the way Python's repr does, so -0.1505 is -151 here and there, never -150. */
  function tenths(x) {
    const v = Number(x);
    if (!Number.isFinite(v)) return NaN;
    return Math.sign(v) * Math.round(Number((Math.abs(v) * 1000).toPrecision(12)));
  }

  /* the drawer's ticker select: the line `from` becomes `to`, same weight, same place in the table. Null when another line
     already holds `to` (no silent merge); the same object when there is nothing to rename. */
  function renameLine(holdings, from, to) {
    if (!holdings || from === to || !Object.prototype.hasOwnProperty.call(holdings, from)) return holdings;
    if (Object.prototype.hasOwnProperty.call(holdings, to)) return null;
    return Object.fromEntries(Object.entries(holdings).map(([k, w]) => [k === from ? to : k, w]));
  }

  /* the one plain line the page shows when a run gives no Result (red gate: never the text of an exception).
     Shown as written: a plain sentence the server sent (an Error tagged .plain, a Result with status "error") and the
     page's own drop sentence (.dropped). Anything else, a render bug above all, gets the fixed sentence. */
  const UNSHOWN = "The check could not be shown. Run the check again.";
  function failureLine(x) {
    const text = x && typeof x.message === "string" ? x.message.trim() : "";
    if (x && x.status === "error") return text || "The check could not run. Run it again.";
    if (x && (x.plain || x.dropped) && text) return text;
    return UNSHOWN;
  }

  /* ---- W-S1: the formatter. U+2212 minus, U+00A0 before % (word units keep a normal space), en-CA grouping; anything that
     is not a finite number (null, undefined, NaN, a string) prints "" so the caller hides its line ---- */
  const MINUS = "\u2212", NB = "\u00a0";
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const isNum = (x) => typeof x === "number" && Number.isFinite(x);
  const ISO = /^(\d{4})-(\d{2})-(\d{2})/;
  const fmt = {
    money(x) {
      if (!isNum(x)) return "";
      const n = Math.round(Math.abs(x));
      return (x < 0 && n > 0 ? MINUS : "") + "$" + n.toLocaleString("en-CA");
    },
    pct(x, d = 1) {   // a fraction; one decimal is governance.round_pp's tenth of a point (ties away from zero)
      if (!isNum(x)) return "";
      const units = d === 1 ? tenths(x) : Math.sign(x) * Math.round(Number((Math.abs(x) * 100 * 10 ** d).toPrecision(12)));
      const v = Math.abs(units) / (d === 1 ? 10 : 10 ** d);
      return (units < 0 ? MINUS : "") + v.toFixed(d) + NB + "%";
    },
    share(x) {        // a weight: whole points when it is whole, else one decimal
      if (!isNum(x)) return "";
      return fmt.pct(x, Math.abs(tenths(x)) % 10 === 0 ? 0 : 1);
    },
    date(iso) {
      const m = typeof iso === "string" && ISO.exec(iso);
      return m && +m[2] >= 1 && +m[2] <= 12 ? `${+m[3]}${NB}${MON[+m[2] - 1]}${NB}${m[1]}` : "";
    },
    month(iso) {
      const m = typeof iso === "string" && ISO.exec(iso);
      return m && +m[2] >= 1 && +m[2] <= 12 ? `${MON[+m[2] - 1]}${NB}${m[1]}` : "";
    },
    days(n) { if (!isNum(n)) return ""; const d = Math.round(n); return d === 1 ? "1 day" : `${d.toLocaleString("en-CA")} days`; },
    years(n) { if (!isNum(n)) return ""; const y = Math.round(n); return y === 1 ? "1 year" : `${y} years`; },
  };
  /* a code-written reason (governance) as the page prints it: U+00A0 before %, recovery days rounded for display (ledger §10) */
  const tidyReason = (s) => String(s == null ? "" : s).replace(/(\d) %/g, "$1" + NB + "%").replace(/(\d+\.\d+) days\b/g, (_, d) => fmt.days(Number(d)));

  /* the move the investor asked about: its ticker, display name and new weight (null when the question changes nothing) */
  const NAMES = { NVDA: "NVIDIA", TSLA: "Tesla", MSFT: "Microsoft", AAPL: "Apple", AMZN: "Amazon", GOOGL: "Alphabet", META: "Meta",
    "SHOP.TO": "Shopify", "CNQ.TO": "Canadian Natural", "ENB.TO": "Enbridge", "BTC-USD": "Bitcoin", "ETH-USD": "Ether" };
  const nameOf = (tk) => NAMES[tk] || tk;
  function moveOf(r) {
    if (!r || r.question_type !== "change" || !r.portfolio || typeof r.portfolio !== "object") return null;
    const base = (r.baseline && r.baseline.portfolio) || {};
    let tk = (r.tipping_point && r.tipping_point.ticker) || (r.scenario && r.scenario.change && r.scenario.change.ticker) || null;
    if (!tk || !(tk in r.portfolio)) tk = Object.keys(r.portfolio).find((k) => Math.abs((r.portfolio[k] || 0) - (base[k] || 0)) > 1e-9) || null;
    return tk && isNum(r.portfolio[tk]) ? { ticker: tk, name: nameOf(tk), weight: r.portfolio[tk] } : null;
  }

  /* ---- words keyed by the Result's own values. The browser maps the server's verdict and statuses to words; it never
     computes a check, a status or a verdict (one judge, red gate 2) ---- */
  const VERDICT = {   // config.VERDICT_WORDS; tone and icon name the lamp
    Compatible: { word: "Inside your limits", tone: "inside", icon: "i-in" },
    Tension: { word: "Inside, with caveats", tone: "caveat", icon: "i-warn" },
    Incompatible: { word: "Outside your limits", tone: "outside", icon: "i-out" },
  };
  const NO_LIMITS = { word: "No limits set", tone: "none", icon: "i-pending" };
  const verdictOfKey = (k) => (k === null ? { key: null, ...NO_LIMITS } : Object.prototype.hasOwnProperty.call(VERDICT, k) ? { key: k, ...VERDICT[k] } : null);
  const STATUS = { fail: { word: "Outside", tone: "outside", icon: "i-out" }, warn: { word: "Caution", tone: "caveat", icon: "i-warn" },
    pass: { word: "Inside", tone: "inside", icon: "i-in" } };
  const TIER = { hard: "Hard limit", soft: "Soft limit", preference: "Preference", warn: "Caution only" };
  const RULE_NAMES = { max_drawdown: "Your floor", scenario_stress: "Shock check", single_stock: "One company", sector: "One sector",
    crypto: "Crypto", esg_direct: "Your values, held directly", esg_indirect: "Your values, inside your funds",
    risk_concentration: "Where the risk sits", recovery: "Time to recover", short_horizon: "Horizon", missing_data: "Data gaps" };
  const FAMILY = { tariffs: "Tariff war", war_oil: "War & oil", chips: "Chip war", rates: "Rate shock" };   // config.FAMILY_LABELS
  const CHANNEL = { country: "country", sector: "sector", currency: "currency" };
  const PRONOUN = { robert: ["he", "his"], mateo: ["he", "his"], amira: ["she", "her"] };
  const GOAL = { preservation: "Preserve capital, with some growth", balance: "Balance growth and stability",
    growth: "Grow capital over the long term", income: "Income" };
  const STOP = new Set(["blocked", "error", "clarify", "limits_missing"]);
  const own = (o, k) => !!o && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
  const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
  const arr = (x) => (Array.isArray(x) ? x : []);
  const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
  const isoDay = (x) => (typeof x === "string" && ISO.test(x) ? x.slice(0, 10) : null);
  const seg = (...parts) => parts.filter((p) => p && p[0]);           // [[text, "num"?], ...]: numbers set in B612 by the page

  /* series / running high − 1: the shape of the fall view (ledger §14), as a fraction, null for a missing value. The page
     never turns it into dollars (ruling R18): every dollar it prints is a Result key. */
  function ddPath(values) {
    let high = -Infinity;
    return values.map((v) => {
      if (!isNum(v) || v <= 0) return null;
      high = Math.max(high, v);
      return v / high - 1;
    });
  }
  const dayIndex = (dates, d) => (isoDay(d) ? dates.findIndex((x) => x >= d) : -1);   // the first drawn day on or after d
  const dollarsOf = (k, value) => {          // a Result's own dollars for this number (kpis.*.loss_dollars), else null
    k = obj(k);
    return k && isNum(k.loss_dollars) && (!isNum(k.value) || !isNum(value) || Math.abs(k.value - value) < 1e-9) ? k.loss_dollars : null;
  };

  /* a facts row (ledger §15 units) as the page prints it: years and days in words, never through the percent formatter */
  function factText(f) {
    f = obj(f);
    if (!f || !isNum(f.value)) return "";
    switch (f.unit) {
      case "pct": return fmt.pct(f.value);
      case "pp": return fmt.pct(f.value).replace(/%$/, "pp");        // round_pp's tenth and U+2212, like every percent
      case "CAD": return fmt.money(f.value);
      case "days": return fmt.days(f.value);
      case "years": return fmt.years(f.value);
      case "months": { const m = Math.round(f.value); return m === 1 ? "1 month" : `${m} months`; }
      case "count": return f.value.toLocaleString("en-CA", { maximumFractionDigits: 1 });
      default: return "";
    }
  }
  const text = (s) => (s ? s : null);                                  // "" (a value the formatter refused) hides the line
  function fallOf(m, kpi) {     // one side's worst drop: the fraction, its dollars as the Result quotes them (ledger §30), its dates
    m = obj(m);
    if (!m || !isNum(m.max_drawdown)) return null;
    const dollars = dollarsOf(kpi, m.max_drawdown), trough = isoDay(m.trough_date);
    return { dd: m.max_drawdown, ddText: fmt.pct(m.max_drawdown), dollars, dollarsText: dollars === null ? null : fmt.money(dollars),
      peak: isoDay(m.peak_date), trough, troughText: text(fmt.date(trough)), year: trough ? trough.slice(0, 4) : null };
  }
  const growthOf = (m) => (obj(m) && isNum(m.cagr) ? { v: m.cagr, text: fmt.pct(m.cagr) } : null);

  /* a check's value against its limit, in the unit of its rule (null when the value is not a number: the row shows its reason) */
  function compareOf(c, ctx) {      // ctx: the evaluated mix's kpis and the floor (its dollars only when the capacity set it)
    const v = c.value, l = c.limit, k = obj(ctx) || {};
    const unit = UNIT[c.rule] || (CAP.test(String(c.rule)) ? fmt.share : null);   // a rule whose value has no known unit (missing_data counts funds) shows its reason
    if (!isNum(v) || !unit) return null;
    let val = unit(v), lim = isNum(l) ? (unit === fmt.pct ? fmt.share(l) : unit(l)) : "";   // a limit prints as the floor does ("−15 %")
    if (CAP.test(String(c.rule)) && isNum(l) && Math.round(l * 1000) === 0) lim = "Excluded (0\u00a0%)";   // LIMITS_MODEL: 0 is an exclusion
    if (c.rule === "max_drawdown") {                 // the dollars are the Result's (kpis.max_drawdown.loss_dollars, capacity_dollars)
      const d = dollarsOf(obj(k.kpis) && k.kpis.max_drawdown, v), f = obj(k.floor);
      if (d !== null) val = `${fmt.money(d)} (${val})`;
      if (lim) lim = f && f.dollarsText && isNum(f.v) && Math.abs(f.v - l) < 1e-9 ? `${f.dollarsText} (${fmt.share(l)})` : fmt.share(l);
    }
    if (c.rule === "single_stock" && str(c.holding)) val = `${nameOf(c.holding)} ${val}`;
    return lim ? `${val} against your limit ${lim}` : val;
  }
  const UNIT = { max_drawdown: fmt.pct, scenario_stress: fmt.pct, single_stock: fmt.share, sector: fmt.share, crypto: fmt.share,
    esg_direct: fmt.share, esg_indirect: fmt.share, risk_concentration: fmt.share, recovery: fmt.days, short_horizon: fmt.years };
  const RANK = { fail: 0, warn: 1, pass: 2 };
  const CAP = /^sector_cap:./;                 // lane sector-limits: governance's row per industry you limited ("sector_cap:Energy")
  const capName = (rule) => (CAP.test(String(rule)) ? `Your ${String(rule).slice("sector_cap:".length)} limit` : null);
  function rowsOf(r, floor) {            // every check the server sent, deciding rows first (status, then code's check_order)
    const ctx = { kpis: obj(r.kpis), floor };                           // r.checks and r.kpis are the same evaluated mix
    const order = arr(obj(r.scenario) && r.scenario.check_order);
    const pos = (rule) => (order.includes(rule) ? order.indexOf(rule) : order.length);
    return arr(r.checks).map((c, i) => [obj(c), i]).filter(([c]) => c && own(STATUS, c.status) && str(c.rule))
      .sort(([a, i], [b, j]) => RANK[a.status] - RANK[b.status] || pos(a.rule) - pos(b.rule) || i - j)
      .map(([c]) => ({ rule: c.rule, status: c.status, ...STATUS[c.status], name: str(c.name) || RULE_NAMES[c.rule] || capName(c.rule) || c.rule,
        compare: compareOf(c, ctx), tier: TIER[c.tier] || null, reason: text(tidyReason(str(c.reason) || "")) }));
  }

  /* the shocks for the hero: each at its epicentre, sorted by date, with the trough the default run measured on its move (on
     the mix itself when nothing changes); a missing trough is null, never invented. `exposed` may lack `via` (ledger §30). */
  /* null (not an array) = not known from holdings (a fresh clone, direct mode or gaps: ledger §30), never "no exposure" */
  function exposureOf(list) {
    if (!Array.isArray(list)) return null;
    const groups = new Map();
    for (const x of arr(list)) {
      const ch = obj(x) && (CHANNEL[x.channel] || str(x.channel));
      if (!ch || !str(x.ticker)) continue;
      const g = groups.get(ch) || { channel: ch, tickers: [], via: [] };
      if (!g.tickers.includes(x.ticker)) g.tickers.push(x.ticker);
      if (str(x.via) && !g.via.includes(x.via.trim())) g.via.push(x.via.trim());
      groups.set(ch, g);
    }
    return [...groups.values()].map((g) => ({ ...g, via: g.via.length ? g.via.join("; ") : null }));
  }
  function shocksOf(r, move) {
    const events = arr(r.events).map(obj).filter((e) => e && isoDay(e.date) && isNum(e.lat) && isNum(e.lon))
      .map((e) => {
        const side = obj(move ? e.after : e.today), t = side && isNum(side.trough) ? side.trough : null;
        return { id: str(e.event_id) || e.date, date: isoDay(e.date), title: str(e.title), place: str(e.place), lat: e.lat, lon: e.lon,
          family: str(e.family), familyLabel: FAMILY[e.family] || null, trough: t, troughText: t === null ? null : text(fmt.pct(t)),
          picked: e.picked === true, exposure: exposureOf(e.exposed),
          exposureNote: !Array.isArray(e.exposed) || (!e.exposed.length && (e.exposed_mode === "direct" || arr(e.exposed_gaps).length))
            ? "Not known from holdings" : null };
      }).sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    if (!events.length) return null;
    const first = events[0].date, last = events[events.length - 1].date;
    return { events, n: events.length, first, last, span: `${fmt.month(first)} to ${fmt.month(last)}` };
  }

  /* the sentences, as segments so the page sets numbers in B612 and the verdict in its tone. Third person on the story
     screens (the default run), second person in the cockpit (the investor is "you"). Each is null when a part is missing. */
  const HERO = { Compatible: "inside {his} limits", Tension: "inside {his} limits, with caveats", Incompatible: "outside {his} limits" };
  function linesOf(v, r) {
    const { who, move, verdict, fall, growth, floor } = v, his = who.his;
    const md = arr(r.checks).find((c) => obj(c) && c.rule === "max_drawdown" && own(STATUS, c.status));   // the server's own status
    const out = { hero: null, thesis: null, dollar: null, note: null, today: null };
    if (who.name && verdict && own(HERO, verdict.key))
      out.hero = seg([`${who.name}’s ${move ? "move" : "mix"}, replayed on real history: `], [HERO[verdict.key].replace("{his}", his), "verdict"], ["."]);
    if (who.name && move && growth.after && growth.today)
      out.thesis = seg([`With `], [v.move.weightText, "num"], [` in ${move.name}, ${who.name}’s money would have grown `], [growth.after.text, "num"],
        [" a year, against "], [growth.today.text, "num"], [md ? (md.status === "fail" ? `, and fallen below ${his} floor.` : `, and stayed above ${his} floor.`) : "."]);
    const main = move ? fall.after : fall.today, word = md ? { fail: "past", pass: "inside" }[md.status] : null;
    /* the limit named by its real source (ruling R18; governance.load_limits keeps the stricter floor): the capacity -> the
       dollars the investor said they could absorb; the 2022 band or an edited floor -> the floor itself */
    const limit = !word || !floor ? [] : floor.capacityText
      ? [[`, ${word} the `], [floor.capacityText, "num"], [" you said you could absorb"]] : [[`, ${word} your floor of `], [floor.text, "num"]];
    if (main && main.dollarsText && v.amountText) {
      out.dollar = move
        ? seg([`With `], [move.weightText, "num"], [` in ${move.name}, this mix fell `], [main.ddText.replace(MINUS, ""), "num"],
          [" at its worst in this history. The same fall on your "], [v.amountText, "num"], [" would have been "], [main.dollarsText, "num"], ...limit, ["."])
        : seg([`Your mix fell `], [main.ddText.replace(MINUS, ""), "num"], [" at its worst in this history: "], [main.dollarsText, "num"],
          [" on your "], [v.amountText, "num"], ...limit, ["."]);
    }
    const t = move ? fall.today : null, td = t && t.dollarsText;      // the dollars only when the Result quotes them
    out.note = seg(t && [`Your mix today fell `], t && [t.ddText.replace(MINUS, ""), "num"], td && [" ("], td && [td, "num"], t && [td ? "). " : ". "],
      ["This already happened; it is not a forecast."]);
    if (move && v.today) out.today = `Today: ${v.today.word.charAt(0).toLowerCase()}${v.today.word.slice(1)}`;
    return out;
  }

  const PILOT = { robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "Too Canadian?" };   // the investor tabs' words
  const shortCommit = (c) => (typeof c === "string" && /^[0-9a-f]{7,40}$/i.test(c.trim()) ? c.trim().slice(0, 7) : null);

  /* PF.view: everything the page shows, from one §12 Result. A missing key gives null (the page hides that line); nothing
     here prints undefined, NaN or a constant. opts: {commit, saved} from the static index or the page's own mode. */
  function view(r, opts) {
    r = obj(r) || {};
    const o = obj(opts) || {}, profile = obj(r.profile) || {}, limits = obj(r.limits) || {}, metrics = obj(r.metrics) || {};
    const status = str(r.status), amount = isNum(r.amount) && r.amount > 0 ? r.amount : null;
    const id = str(r.pilot), pr = PRONOUN[id] || ["they", "their"];
    const move = moveOf(r);
    const capacity = [profile.capacity, profile.capacity_dollars, limits.capacity_dollars].find(isNum);
    /* the floor has dollars only when the capacity set it (floor_source "capacity", not edited): the Result's capacity_dollars.
       A floor set by the 2022 band or edited is named as itself (ruling R18). */
    const edited = arr(limits.edited).includes("floor");
    const cap = isNum(limits.floor) && limits.floor_source === "capacity" && !edited ? [limits.capacity_dollars, capacity].find((x) => isNum(x) && x > 0) : undefined;
    const kp = (x) => obj(x) && obj(x.kpis) && x.kpis.max_drawdown;     // the dollars of a worst drop, as the Result quotes them
    const v = {
      status, message: str(r.message), mode: str(r.mode), saved: r.mode === "demo_replay" || o.saved === true,
      stop: STOP.has(status), run_id: str(r.run_id), question: str(r.question), asOf: text(fmt.date(r.as_of)), commit: shortCommit(o.commit),
      who: { id, name: str(profile.name) || PILOT[id] || null, age: isNum(profile.age) ? profile.age : null, he: pr[0], his: pr[1] },
      amount, amountText: amount === null ? null : fmt.money(amount),
      capacity: isNum(capacity) ? capacity : null, capacityText: isNum(capacity) ? fmt.money(capacity) : null,
      move: move && { ...move, weightText: fmt.share(move.weight), readAs: `${move.name} to ${fmt.share(move.weight)}` },
      verdict: own(r, "verdict") ? verdictOfKey(r.verdict) : null,
      today: move && obj(r.baseline) && own(r.baseline, "verdict") ? verdictOfKey(r.baseline.verdict) : null,
      fall: { today: fallOf(metrics.today, move ? kp(r.baseline) : kp(r)), after: move ? fallOf(metrics.after, kp(r)) : null },
      growth: { today: growthOf(metrics.today), after: move ? growthOf(metrics.after) : null },
      floor: isNum(limits.floor) ? { v: limits.floor, text: fmt.share(limits.floor), source: edited ? "edited" : str(limits.floor_source),
        dollars: isNum(cap) ? -cap : null, dollarsText: isNum(cap) ? fmt.money(-cap) : null, capacityText: isNum(cap) ? fmt.money(cap) : null,
        label: isNum(cap) ? fmt.money(-cap) : fmt.share(limits.floor) } : null,
      shockFamily: FAMILY[arr(obj(r.scenario) && r.scenario.families)[0]] || null,       // from the Result, never page state
      rows: [], breaches: [], paths: null, shocks: shocksOf(r, move),
      facts: Object.entries(obj(r.facts) || {}).map(([id, f]) => [id, obj(f), factText(f)]).filter(([, f, t]) => f && t)
        .map(([id, f, t]) => ({ id, label: str(f.label), text: t, kind: str(f.kind), marker: markerOf(f.kind) })),
    };
    const s = obj(r.series), dates = s && arr(s.dates).map(isoDay), today = s && arr(s.today);
    v.ok = !v.stop && !!s && dates.length > 1 && dates.every(Boolean) && today.length === dates.length;
    v.rows = rowsOf(r, v.floor);
    const pairs = (x) => arr(x).filter((p) => Array.isArray(p) && p.length === 2 && isoDay(p[0]) && isoDay(p[1])).map((p) => [isoDay(p[0]), isoDay(p[1])]);
    v.breaches = arr(r.breaches).map(obj).filter((b) => b && isNum(b.depth) && isoDay(b.trough_date))
      .sort((a, b) => a.depth - b.depth).map((b) => ({ peak: isoDay(b.peak_date), trough: isoDay(b.trough_date), troughText: fmt.date(b.trough_date),
        year: b.trough_date.slice(0, 4), dd: b.depth, ddText: fmt.pct(b.depth), dollars: isNum(b.loss_dollars) ? b.loss_dollars : null,
        dollarsText: isNum(b.loss_dollars) ? fmt.money(b.loss_dollars) : null, below: pairs(b.below_floor) }));
    if (v.ok && amount !== null) {
      const after = move && arr(s.after).length === dates.length ? arr(s.after) : null;
      const P = { dates, today: ddPath(today), after: after && ddPath(after), floor: v.floor ? v.floor.v : null, trough: -1, hatch: [] };
      const main = P.after || P.today, side = P.after ? v.fall.after : v.fall.today;
      /* one value per fact: the Result's own troughs sit on the line at their dates (the readout there reads the quoted number) */
      const pin = (path, d, x) => { const i = dayIndex(dates, d); if (i >= 0 && path[i] !== null && isNum(x)) path[i] = x; return i; };
      for (const b of v.breaches) pin(main, b.trough, b.dd);
      if (P.after && v.fall.today) pin(P.today, v.fall.today.trough, v.fall.today.dd);
      if (side) P.trough = pin(main, side.trough, side.dd);
      /* the hatch: the Result's below_floor stretches (the server's round_pp decides a breach, pitfall 5), as day indices */
      P.hatch = v.breaches.flatMap((b) => b.below).map(([a, z]) => [dayIndex(dates, a), dayIndex(dates, z)])
        .map(([i, j]) => [i, j < 0 ? dates.length - 1 : j]).filter(([i, j]) => i >= 0 && j >= i).sort((x, y) => x[0] - y[0]);
      v.paths = P;
    }
    v.lines = linesOf(v, r);
    return v;
  }

  /* the hero's words from the default run (at most 35 on the screen with the headline, the note and the bar: tested) */
  function heroCopy(v) {
    v = obj(v) || {};
    const who = obj(v.who) || {}, line = arr(obj(v.lines) && v.lines.hero).map((s) => s[0]).join("");
    return { line: line || null, segs: (obj(v.lines) && v.lines.hero) || null,
      button: who.name ? `Replay ${who.name}’s ${v.move ? "move" : "mix"}` : "Replay the move",
      readout: v.shocks ? [`${v.shocks.n} shocks on record`, v.shocks.span] : null };
  }

  /* where a shock sits on the poster: the camera of web/globe.js (distance D = CAMERA_D, the globe tilted by `tilt` degrees and
     turned to `lon0`), in units of the disc radius, y down. visible: in front of the horizon. The no-WebGL rings use it. */
  function globeProject(lat, lon, o) {
    o = obj(o) || {};
    const D = isNum(o.D) ? o.D : 6, r = isNum(o.r) ? o.r : 1, R = Math.PI / 180;
    const a = lat * R, b = lon * R, th = -(Math.PI / 2 + (isNum(o.lon0) ? o.lon0 : -18) * R), ph = (isNum(o.tilt) ? o.tilt : 26) * R;
    const x = r * Math.cos(a) * Math.cos(b), y = r * Math.sin(a), z = -r * Math.cos(a) * Math.sin(b);
    const x1 = x * Math.cos(th) + z * Math.sin(th), z1 = -x * Math.sin(th) + z * Math.cos(th);
    const y2 = y * Math.cos(ph) - z1 * Math.sin(ph), z2 = y * Math.sin(ph) + z1 * Math.cos(ph);
    const k = Math.sqrt(D * D - 1) / (D - z2);
    return { x: x1 * k, y: -y2 * k, z: z2 / r, visible: z2 > r / D };
  }

  /* the investor card's rows (mock 03), from a Result or an investor of /api/pilots (no run yet: no floor and no limits rows) */
  function youRows(src) {
    src = obj(src) || {};
    const p = obj(src.profile), l = obj(src.limits) || {}, amount = isNum(src.amount) ? src.amount : null;
    if (!p) return [];
    const capacity = [p.capacity, p.capacity_dollars, l.capacity_dollars].find(isNum), rows = [];
    const add = (label, value, note) => { if (value) rows.push(note ? { label, value, note } : { label, value }); };
    add("Objective", GOAL[p.goal] || null);
    add("When you need the money", isNum(p.horizon_years) ? `In ${fmt.years(p.horizon_years)}` : null);
    add("The most you could lose", isNum(capacity) && amount !== null ? `${fmt.money(capacity)} of ${fmt.money(amount)}` : null);
    if (isNum(l.floor)) {
      const band = [l.band_floor, l.appetite_floor].find(isNum);
      add("Your floor", fmt.share(l.floor), l.floor_source === "capacity"
        /* release gate (a): what happened, past tense, no permission verb: the floor the 2022 reaction alone pointed to, beside this one */
        ? "Set by the loss you could absorb." + (isNum(band) ? ` Your reaction to the 2022 fall alone pointed to ${fmt.share(band)}, ${
          Math.abs(band) > Math.abs(l.floor) + 1e-9 ? "a deeper fall than this floor" : Math.abs(band) < Math.abs(l.floor) - 1e-9 ? "a shallower fall than this floor" : "the same floor"}.` : "")
        : l.floor_source === "band" ? "Set by your 2022 reaction." : null);
    }
    if (isNum(l.single_stock))
      add("Limits", `One company up to ${fmt.share(l.single_stock)}; ` + (l.crypto === 0 || p.crypto === false || !isNum(l.crypto) ? "no crypto" : `crypto up to ${fmt.share(l.crypto)}`));
    if (typeof p.esg === "boolean") add("Values", p.esg ? "Screen out companies with major controversies" : "No values screen");
    return rows;
  }

  /* the five questions → one typed profile (ledger §15: goal, horizon 1–40, capacity, the 2022 reaction, esg, crypto) */
  function profileFromAnswers(a, amount) {
    a = obj(a) || {};
    const years = Number(a.horizon), loss = Number(a.loss);
    if (!own(GOAL, a.goal)) return { error: "Choose what this money is for." };
    if (!Number.isInteger(years) || years < 1 || years > 40) return { error: "Choose a number of years between 1 and 40." };
    if (!Number.isFinite(loss) || loss <= 0) return { error: "Enter the loss as a positive amount." };
    if (!own(RISK_FROM_2022, a.in_2022)) return { error: "Choose what you did in 2022." };
    const capacity = a.unit === "%" ? (isNum(amount) ? Math.round(amount * loss) / 100 : NaN) : loss;
    if (!Number.isFinite(capacity) || (isNum(amount) && capacity > amount)) return { error: "Enter a loss no larger than the amount." };
    return { profile: { goal: a.goal, horizon_years: years, risk: RISK_FROM_2022[a.in_2022], esg: !!a.esg, crypto: !!a.crypto, capacity,
      reaction_2022: REACTION_2022[a.in_2022] } };
  }

  /* the plan PF.requestBody sends, from a Result (today's mix) or an investor of /api/pilots (one shape, D Task 5) */
  const IN_2022 = { sold: "sold", held: "held", bought: "bought more" };
  function planFrom(src, pilot) {
    src = obj(src) || {};
    const p = obj(src.profile) || {}, base = obj(src.baseline) && obj(src.baseline.portfolio);
    const mix = base || obj(src.portfolio) || {}, holdings = {};
    for (const [tk, w] of Object.entries(mix)) if (isNum(w)) holdings[tk] = Number((w * 100).toFixed(8));
    return { pilot: str(pilot) || str(src.pilot), amount: src.amount, capacity: [p.capacity, p.capacity_dollars].find(isNum) ?? null,
      in_2022: own(RISK_FROM_2022, p.in_2022) ? p.in_2022 : IN_2022[p.reaction_2022] || null, goal: p.goal, horizon: p.horizon_years,
      esg: !!p.esg, crypto: !!p.crypto, holdings, q: str(src.question) || "", hl: "" };
  }

  /* the static demo (runs/index.json from scripts/record_demo.py): an investor's run is its first entry, its own question first */
  const staticRun = (index, pilot) => arr(index).find((x) => obj(x) && x.pilot === pilot && str(x.file)) || null;
  /* what a failed run puts back: the last Result that rendered fully for this investor (a map pilot -> Result), never another
     investor's, never a stopped answer (W-S1 review I2) */
  const lastGood = (last, pilot) => {
    const r = obj(last) && own(last, pilot) ? obj(last[pilot]) : null;
    return r && !STOP.has(str(r.status)) ? r : null;
  };

  return { requestBody, debriefSections, blockOrder, tokensOf, markerOf, withPaths, tenths, renameLine, failureLine, UNSHOWN,
    fmt, tidyReason, factText, moveOf, view, heroCopy, globeProject, youRows, profileFromAnswers, planFrom, staticRun, lastGood, shortCommit, VERDICT, STATUS };
});
