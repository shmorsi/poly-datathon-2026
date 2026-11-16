/* EPICENTRE Replay, lane U8: the model of #deep ("Not just 2022", design doc R5 and R11). Pure: no DOM, no network.
   deepModel(result, PF, view) reads result.deep_history (+ deep_validation, deep_windows) and returns what the section draws.
   Every number it returns is a Result value (or PF.fmt of one): it never makes a new number. Two shapes are read:
   the tools.deep fragment (episodes[].today = {depth, replayable, beyond_floor, peak, trough, loss_dollars, ...}) and the
   lane fixture (episodes[].today = a bare worst fall). A missing key hides its line; nothing is invented. */

import { floorClass, floorWord } from "./status.js";

const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const arr = (x) => (Array.isArray(x) ? x : []);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const first = (...xs) => xs.find((x) => x !== undefined && x !== null);
const YM = /^(\d{4})-(\d{2})/;

/* ruling R18: typographic apostrophes and quotes in every string the Result hands the page (its words are kept) */
export function typo(s) {
  return typeof s !== "string" ? s : s.replace(/(\w)\x27(\w)/g, "$1\u2019$2").replace(/(^|[\s(])\x27/g, "$1\u2018").replace(/\x27/g, "\u2019")
    .replace(/(^|[\s(])\x22/g, "$1\u201c").replace(/\x22/g, "\u201d");
}
const tstr = (x) => { const v = str(x); return v && typo(v); };

/* the worst fall of one side of a crisis row (a fraction <= 0), or null when it was not replayed */
export function depthOf(side) {
  if (isNum(side)) return side;
  const s = obj(side);
  if (!s || s.replayable === false) return null;
  const d = first(s.depth, s.worst, s.max_drawdown);
  return isNum(d) ? d : null;
}

/* the class words of R11. The Result's own class wins; then the server's beyond_floor with the one-point band; the bare
   comparison (tenths of a point, governance.round_pp) is the fixture's fallback only, so the page never disagrees on rounding */
export const CLASS = {
  broke: { key: "broke", word: "Broke", tone: "broke", say: "broke the floor by more than a point" },
  touched: { key: "touched", word: "Touched", tone: "touched", say: "touched the floor, within a point" },
  held: { key: "held", word: "Held", tone: "held", say: "stayed above the floor" },
};
const classWord = (x) => { const k = str(x) && x.trim().toLowerCase(); return k && Object.prototype.hasOwnProperty.call(CLASS, k) ? CLASS[k] : null; };
export function classOf(row, side, depth, floor, PF) {
  const s = obj(obj(row) && row[side]), r = obj(row) || {};
  const given = classWord(s && first(s.class, s.outcome, s.classification)) || classWord(r[side + "_class"])
    || classWord(obj(r.class) && r.class[side]) || classWord(obj(r.classes) && r.classes[side]);
  if (given) return given;
  if (!isNum(depth) || !isNum(floor) || !PF || typeof PF.tenths !== "function") return null;
  const t = PF.tenths(depth), f = PF.tenths(floor);
  if (s && typeof s.beyond_floor === "boolean") return !s.beyond_floor ? CLASS.held : t < f - 10 ? CLASS.broke : CLASS.touched;
  return t < f - 10 ? CLASS.broke : t < f ? CLASS.touched : CLASS.held;
}

/* "1973–74", "1987", "2007–09", "1999–2001" from the row's start and end months */
export function yearsOf(start, end) {
  const a = YM.exec(String(start || "")), b = YM.exec(String(end || ""));
  if (!a) return "";
  if (!b || b[1] === a[1]) return a[1];
  return a[1].slice(0, 2) === b[1].slice(0, 2) ? `${a[1]}–${b[1].slice(2)}` : `${a[1]}–${b[1]}`;
}

/* the gauge's extent: the deepest value drawn or the floor, up to the next ten points (a scale, never printed as data) */
export function scaleOf(values, floor) {
  const m = Math.max(0, ...values.filter(isNum).map((v) => -v), isNum(floor) ? -floor : 0);
  return m > 0 ? Math.min(1, Math.ceil(m * 10 - 1e-9) / 10) : 1;
}

/* the moved line's stand-in alone: the Result's own number, never derived */
const aloneOf = (row) => { const r = obj(row) || {}; const a = first(r.proxy_alone, r.stand_in_alone, r.alone); return isNum(a) ? a : depthOf(a); };

/* worse / no worse: the Result's flag wins; else the move fell more than a point deeper than today's mix (the same band
   as "touched", so a 0.1-point gap never reads as worse) */
export function worseOf(row, today, after, PF) {
  const r = obj(row) || {};
  const flag = first(r.move_worse, r.worse, obj(r.compare) && r.compare.worse);
  if (typeof flag === "boolean") return flag;
  if (!isNum(today) || !isNum(after) || !PF || typeof PF.tenths !== "function") return null;
  return PF.tenths(after) < PF.tenths(today) - 10;
}

/* the headline sentence: result.deep_history.robust_claims only (R11: the directions that survive the sensitivity runs) */
export function claimsOf(dh) {
  const c = obj(dh) && dh.robust_claims;
  if (obj(c)) return arr(c.claims).length && str(c.sentence) ? [tstr(c.sentence)] : [];   // B3: the code-written sentence, when a claim survived
  const list = typeof c === "string" ? [c] : arr(c).map((x) => (typeof x === "string" ? x : obj(x) && first(str(x.text), str(x.sentence), str(x.claim))));
  return list.map(tstr).filter(Boolean);
}
/* the lead (critic polish): two figures from B3's own counts of the row classes, never counted here. A side is null when
   the Result has no count for it (no move, or a Result without counts): the page then leads with the sentence alone */
export function leadOf(dh) {
  const c = obj(obj(dh) && dh.counts);
  if (!c) return null;
  /* one rule for "broke" (R39): a row B3 calls touched that still went past the floor (margin_pp > 0, robust_claims.rows) is
     counted as "went just past your rule", with the smallest and largest margin, so a −16.1 % fall never reads as held */
  const rows = arr(obj(dh.robust_claims) && dh.robust_claims.rows).map(obj).filter(Boolean);
  const cls = new Map(arr(dh.episodes).map(obj).filter(Boolean).map((e) => [str(first(e.id, e.episode_id)), e]));
  const past = (k) => rows.filter((x) => { const e = cls.get(x.id), s = obj(x[k]); return e && e[`${k}_class`] === "touched" && s && isNum(s.margin_pp) && s.margin_pp > 0; })
    .map((x) => x[k].margin_pp);
  const side = (k) => { if (!(isNum(c[`${k}_broke`]) && isNum(c[`${k}_replayable`]) && c[`${k}_replayable`] > 0)) return null;
    const m = past(k);
    return { broke: c[`${k}_broke`], touched: isNum(c[`${k}_touched`]) ? c[`${k}_touched`] : 0, of: c[`${k}_replayable`], all: isNum(c.n) ? c.n : null,
      past: m.length, lo: m.length ? Math.min(...m) : null, hi: m.length ? Math.max(...m) : null }; };
  const out = { after: side("after"), today: side("today") };
  return out.after || out.today ? out : null;
}

/* the sensitivity runs every claim survived (B3's robust_claims.test), and the sentence it writes when none did */
export function claimTestOf(dh) {
  const c = obj(obj(dh) && dh.robust_claims);
  return c ? { test: tstr(c.test), none: arr(c.claims).length ? null : tstr(c.sentence) } : { test: null, none: null };
}
/* the per-crisis direction that survived every run (B3's robust_claims.rows[].direction): "further" | "no_further" | null
   (too close to call); undefined when the Result has no robust rows */
export function directionsOf(dh) {
  const rows = arr(obj(obj(dh) && dh.robust_claims) && dh.robust_claims.rows).map(obj).filter((x) => x && str(x.id));
  return rows.length ? new Map(rows.map((x) => [x.id, x.direction === "further" || x.direction === "no_further" ? x.direction : null])) : null;
}

/* the proxy check against 2021–26 (R11): result.deep_validation, else the tools.deep fragment's own proxy check */
const side = (real, proxy, gap, within) => (isNum(real) && isNum(proxy)
  ? { real, proxy, gap: isNum(gap) ? gap : null, within: typeof within === "boolean" ? within : null } : null);
export function validationOf(r, dh) {
  const dv = obj(obj(r) && r.deep_validation), p = obj(obj(dh) && first(dh.proxy_check, dh.proxy));
  let today = null, after = null, window = null, weak = null, notes = null;
  if (dv) {
    const g = obj(dv.gap_pp) || {}, w2 = obj(dv.within_2pp) || {};
    const real = (k) => first(isNum(dv[`${k}_real_window`]) ? dv[`${k}_real_window`] : null, dv[`${k}_real`]);
    today = side(real("today"), dv.today_proxy, g.today, w2.today); after = side(real("after"), dv.after_proxy, g.after, w2.after);
    const pa = p && obj(p.after); weak = pa && pa.strength === "weak" ? str(pa.direction) || "rough" : null;
    const w = obj(dv.window); window = w ? { start: str(w.start), end: str(w.end) } : { start: str(dv.start), end: str(dv.end) };
    notes = typeof dv.method_notes === "string" ? str(dv.method_notes) : arr(dv.method_notes).map(str).filter(Boolean).join(" ") || null;
  } else if (p) {
    const t = obj(p.today), a = obj(p.after);
    today = t && side(t.drawdown_real, t.drawdown_proxy); after = a && side(a.drawdown_real, a.drawdown_proxy);
    const w = obj((t && t.window) || (a && a.window)); window = w ? { start: str(w.start), end: str(w.end) } : null;
    weak = a && a.strength === "weak" ? str(a.direction) || "rough" : null;
  }
  if (!today && !after) return null;
  return { today, after, window: window && window.start && window.end ? window : null, weak, notes };
}

/* "One company falls further than its industry": shown with numbers only when the Result carries both of them */
export function gentleOf(r, dh) {
  const dv = obj(obj(r) && r.deep_validation) || {}, w = obj(obj(r) && r.deep_windows) || {};
  const g = obj(first(obj(dh) && dh.gentle_case, dv.gentle_case, dv.gentle, w.gentle_case));
  if (!g) return null;
  const company = first(g.real, g.company, g.own), industry = first(g.stand_in, g.industry);
  if (!isNum(company) || !isNum(industry)) return null;
  const win = obj(g.window);
  return { company, industry, gentler: typeof g.gentler === "boolean" ? g.gentler : null, label: str(g.label),
    window: win && str(win.start) && str(win.end) ? { start: win.start, end: win.end } : null, year: str(String(first(g.year, "") || "")) };
}

/* who stands in for whom: deep_windows.proxies (or deep_history.proxies), each with the Result's strength word */
export function proxiesOf(r, dh) {
  const w = obj(obj(r) && r.deep_windows) || {};
  return arr(first(w.proxies, obj(dh) && dh.proxies)).map(obj).filter((p) => p && str(p.ticker) && str(p.label))
    .map((p) => ({ ticker: p.ticker, label: typo(p.label), strength: str(p.strength), note: str(p.note) && !/\d/.test(p.note) ? tstr(p.note) : null }));
}

/* the lines with no stand-in, as the Result names them (coverage.missing, the rows' uncovered lists, a cant_say reason) */
export function missingOf(r, dh) {
  const w = obj(obj(r) && r.deep_windows) || {}, cov = obj(w.coverage) || obj(obj(dh) && dh.coverage) || {};
  const names = new Set(arr(cov.missing).map((m) => (typeof m === "string" ? m : obj(m) && str(m.ticker))).filter(Boolean));
  for (const e of arr(obj(dh) && dh.episodes).map(obj).filter(Boolean))
    for (const s of ["today", "after"]) for (const t of [...arr(obj(e[s]) && e[s].uncovered), ...arr(obj(e[`${s}_detail`]) && e[`${s}_detail`].uncovered)]) if (str(t)) names.add(t);
  const reason = first(str(w.status) === "cant_say" ? str(w.reason) : null, str(cov.reason), str(obj(dh) && dh.reason));
  return { tickers: [...names], reason: reason ? typo(reason) : null };
}

const HTTP = /^https?:\/\/[^\s"'<>]+$/i;

/* where the deep panel comes from, never "not recorded" (pre-freeze G6): the sources' retrieval date when the Result carries
   one, else the panel's build date, else the run's own as_of, each labelled for what it is */
const ISO_DAY = (x) => (typeof x === "string" && /^\d{4}-\d{2}-\d{2}/.test(x) ? x.slice(0, 10) : null);
export function provenanceOf(r, dh, PF) {
  const F = PF && obj(PF.fmt), p = obj(obj(dh) && dh.panel) || {}, dv = obj(obj(r) && r.deep_validation) || {};
  if (!F) return null;
  const got = ISO_DAY(first(obj(dh) && dh.retrieved_at, p.retrieved_at));
  if (got) return `Sources retrieved on ${F.date(got)}.`;
  const built = ISO_DAY(first(obj(dh) && dh.panel_built, p.built_at, p.built, dv.panel_built));
  if (built) return `Panel built on ${F.date(built)}.`;
  const asOf = ISO_DAY(first(obj(dh) && dh.as_of, obj(r) && r.as_of));
  return asOf ? `The panel as this run used it, run as of ${F.date(asOf)}.` : null;
}
/* the Result's source line without a clause that only says nothing was recorded */
export const sourceText = (s) => (typeof s === "string" ? s.replace(/\s*Data retrieved:\s*not recorded\.?/gi, "").trim() || null : null);

/* how the stand-ins were built: deep_validation.method_notes and its Canada check, as the Result words them */
export function methodsOf(r) {
  const dv = obj(obj(r) && r.deep_validation) || {}, c = obj(dv.canada), sc = c && obj(c.splice_check), sp = c && obj(c.splice);
  return { notes: arr(dv.method_notes).map(tstr).filter(Boolean),
    canada: c && sp && str(sp.to) ? { to: sp.to, source: tstr(sp.source), currency: tstr(c.currency),
      check: sc && isNum(sc.corr) && isNum(sc.months) ? { corr: sc.corr, months: sc.months, start: str(sc.start), end: str(sc.end) } : null } : null };
}
const yearOf = (ym) => { const m = YM.exec(String(ym || "")); return m ? m[1] : null; };

/* everything #deep draws, from one Result. show: false hides the section (no deep_history key, no rows, no PF yet) */
export function deepModel(result, PF, view) {
  const r = obj(result) || {}, dh = obj(r.deep_history), F = PF && obj(PF.fmt);
  if (!dh || !F) return { show: false };
  const v = obj(view) || (typeof PF.view === "function" ? obj(PF.view(r)) : null) || {};
  const limits = obj(r.limits) || {}, floor = isNum(limits.floor) ? limits.floor : null;
  const mv = obj(v.move), who = str(obj(v.who) && v.who.name);
  const pick = (e, key, depth) => {
    if (depth === null) return null;
    const s = obj(e[key]) || obj(e[`${key}_detail`]) || {};             // tools.deep keeps the detail on the side, B3 beside it
    return { v: depth, text: F.pct(depth), cls: classOf(e, key, depth, floor, PF), why: tstr(e[`${key}_why`]), peak: str(s.peak), trough: str(s.trough),
      dollars: isNum(s.loss_dollars) ? s.loss_dollars : null, months: isNum(s.recovery_months) ? s.recovery_months : null };
  };
  const dirs = directionsOf(dh), asked = arr(obj(r.scenario) && r.scenario.families).map(str).filter(Boolean);
  const rows = arr(dh.episodes).map(obj).filter((e) => e && str(first(e.title, e.title_en))).map((e) => {
    const t = depthOf(e.today), a = mv ? depthOf(e.after) : null, al = mv ? aloneOf(e) : null;
    const id = str(first(e.id, e.episode_id)), both = mv && t !== null && a !== null;
    /* worse / no worse: the direction that survived every sensitivity run (R11) when the Result has one, else the row's own */
    const dir = both && dirs && dirs.has(id) ? dirs.get(id) : undefined;
    return { id, title: tstr(first(e.title, e.title_en)), years: yearsOf(e.start, e.end),
      start: str(e.start), end: str(e.end), place: tstr(e.place), url: HTTP.test(String(e.source_url || "")) ? e.source_url : null,
      sourceTitle: tstr(e.source_title), today: pick(e, "today", t), after: pick(e, "after", a),
      asked: !!(str(e.family) && asked.includes(e.family)),            // the same family of shock as the question (the page's thread)
      alone: al === null ? null : { v: al, text: F.pct(al), trough: str(e.alone_trough) },
      worse: !both ? null : dir === undefined ? worseOf(e, t, a, PF) : dir === null ? "close" : dir === "further" };
  });
  if (!rows.length) return { show: false };
  const scale = scaleOf(rows.flatMap((x) => [x.today && x.today.v, x.after && x.after.v, x.alone && x.alone.v]), floor);
  const frac = (d) => (isNum(d) ? Math.min(1, Math.max(0, -d / scale)) : 0);
  /* the hatch is geometry, not a class: only where a bar passes the floor (a "touched" row may stop short of it, R11 + B3) */
  const past = (s) => !!(s && isNum(floor) && PF.tenths(s.v) < PF.tenths(floor));
  for (const x of rows) {
    const deep = [x.today, x.after].filter(past).map((s) => frac(s.v));
    x.g = { t: x.today ? frac(x.today.v) : null, a: x.after ? frac(x.after.v) : null, al: x.alone ? frac(x.alone.v) : null,
      zone: deep.length && isNum(floor) ? Math.max(...deep) : null };
  }
  const proxies = proxiesOf(r, dh), missing = missingOf(r, dh), moved = obj(dh.moved), pf = obj(r.portfolio) || {};
  missing.items = missing.tickers.map((tk) => ({ ticker: tk, share: isNum(pf[tk]) ? F.share(pf[tk]) : null }));
  const listed = mv ? proxies.find((p) => p.ticker === mv.ticker) || null : null;
  const stand = !mv ? null : moved && str(moved.label) && (!str(moved.ticker) || moved.ticker === mv.ticker)
    ? { ticker: mv.ticker, label: typo(moved.label), strength: listed ? listed.strength : null } : listed;
  const years = rows.flatMap((x) => [yearOf(x.start), yearOf(x.end)]).filter(Boolean).sort();
  return {
    show: true, state: rows.some((x) => x.today) ? "ok" : "cant_say", who, amountText: str(v.amountText),
    askedLabel: rows.some((x) => x.asked) ? str(v.shockFamily) : null,
    /* ruling R18, one voice: the instrument speaks to the investor (your $600,000), never names them */
    on: str(v.amountText) ? `your ${v.amountText}` : "your mix",
    floor: isNum(floor) ? { v: floor, text: F.share(floor), f: frac(floor) } : null,
    move: mv ? { ticker: mv.ticker, name: str(mv.name) || mv.ticker, weightText: str(mv.weightText) } : null,
    standIn: stand, n: rows.length, span: years.length ? { from: years[0], to: years[years.length - 1] } : null,
    rows, scale, step: 0.1 / scale,
    cols: { after: rows.some((x) => x.after), alone: rows.some((x) => x.alone), worse: rows.some((x) => x.worse !== null) },
    robust: rows.some((x) => (x.today && x.today.why) || (x.after && x.after.why)) || !!directionsOf(dh),
    claims: claimsOf(dh), claimTest: claimTestOf(dh), lead: leadOf(dh), validation: validationOf(r, dh), gentle: gentleOf(r, dh), proxies, missing,
    methods: methodsOf(r),
    source: tstr(sourceText(dh.source)), provenance: provenanceOf(r, dh, PF), kind: str(first(dh.kind, obj(r.deep_windows) && r.deep_windows.kind)) || "assumption",
  };
}

/* P1, behind window.EPI_STRIPES (default off; ruling R5): the risk stripes from result.deep_windows. One stripe per start
   month, its class from the stretch's worst fall (the same rule as the rows); runs of one class merged into one mark. No
   share of stretches is returned: the page never prints one (it reads as odds). */
export function stripesOf(result, PF) {
  const r = obj(result) || {}, w = obj(r.deep_windows), s = w && obj(w.stripes), F = PF && obj(PF.fmt);
  if (!w || !s || !F || str(w.status) === "cant_say") return null;
  const starts = arr(s.starts).map((x) => (YM.test(String(x)) ? String(x).slice(0, 7) : null));
  const floor = isNum(w.floor) ? w.floor : isNum(obj(r.limits) && r.limits.floor) ? r.limits.floor : null;
  if (!starts.length || starts.some((x) => !x) || floor === null) return null;
  const line = (key, label) => {
    const v = arr(s[key]);
    if (v.length !== starts.length || !v.every(isNum)) return null;
    const cls = v.map((d) => (classOf({}, key, d, floor, PF) || CLASS.held).key), runs = [];
    cls.forEach((c, i) => { const last = runs[runs.length - 1]; if (last && last.cls === c) last.n += 1; else runs.push({ cls: c, i, n: 1 }); });
    return { key, label, values: v, cls, runs };
  };
  const rows = [line("today", "Today’s mix"), line("after", "With the move")].filter(Boolean);
  if (!rows.length) return null;
  const decades = [];
  starts.forEach((m, i) => { if (m.endsWith("-01") && m[3] === "0") decades.push({ i, label: m.slice(0, 4) }); });
  const h = isNum(w.horizon_months) ? w.horizon_months : null;
  return { n: starts.length, starts, rows, decades, floor, months: h, years: h && h % 12 === 0 ? h / 12 : null,
    first: F.month(`${starts[0]}-01`), last: F.month(`${starts[starts.length - 1]}-01`) };
}

/* Each kind of earlier crisis (the lead's addition, then the pre-freeze judge, defect 1): #deep speaks only of the deep record.
   One row per kind that the 11 sourced crises contain (war and oil, rate shocks), and the crises whose family is none of the four
   kinds of shock make the last row. Each side is the worst fall of its group, a Result number, with B3's own row class (the assumption marker: by
   stand-in, probably milder than the real thing). The 2021–26 shocks are the stage's to tell (they are measured over a window, not
   from the high), so they never appear here. No end value, no probability. */
export const KINDS = Object.freeze([
  { id: "war_oil", label: "War and oil" }, { id: "rates", label: "Rate shocks" },
  { id: "chips", label: "Chip and tech slumps" }, { id: "tariffs", label: "Tariffs" },
]);
export function kindsOf(result, PF) {
  const r = obj(result) || {}, F = PF && obj(PF.fmt), dh = obj(r.deep_history);
  const floor = isNum(obj(r.limits) && r.limits.floor) ? r.limits.floor : null;
  if (!F || floor === null || !dh) return null;
  const v = typeof PF.view === "function" ? obj(PF.view(r)) || {} : {}, move = !!obj(v.move);
  const asked = arr(obj(r.scenario) && r.scenario.families).map(str).filter(Boolean);
  /* status.js names the class (Broke / Touched / Held above your floor; neutral, never green); `by` says who decided it */
  const cell = (d, given, why) => { if (!isNum(d)) return null; const c = floorClass(d, floor, given);
    return { v: d, text: F.pct(d), cls: c, word: c ? floorWord(c).word : null, by: typeof given === "string" ? "result" : "rounding", why: tstr(why) || null }; };
  const CLS = ["broke", "touched", "held"];
  const served = (t, k) => { const c = str(t[`${k}_class`]); return c && CLS.includes(c) ? c : null; };
  const eps = arr(dh.episodes).map(obj).filter((e) => e && str(first(e.title, e.title_en)));
  const cant = str(dh.status) === "cant_say";
  const earlier = (match) => {
    const mine = eps.filter(match);
    if (!mine.length) return null;
    const when = mine.map((e) => yearsOf(e.start, e.end)).filter(Boolean).join(", ");
    if (cant || mine.every((e) => depthOf(e.today) === null)) return { kind: "assumption", when, cant: true, n: mine.length };
    const worst = (side) => {
      const got = mine.filter((e) => depthOf(e[side]) !== null);
      if (!got.length) return null;
      const e = got.reduce((a, b) => (depthOf(b[side]) < depthOf(a[side]) ? b : a)), d = depthOf(e[side]), own = served(e, side);
      const c = cell(d, own || (classOf(e, side, d, floor, PF) || {}).key || null, own && e[`${side}_why`]);
      return own ? c : c && { ...c, by: "rounding" };                  // B3's row class, else the fixture's fallback rule
    };
    return { kind: "assumption", when, n: mine.length, today: worst("today"), after: move ? worst("after") : null };
  };
  const ids = KINDS.map((k) => k.id);
  const rows = KINDS.map((k) => ({ id: k.id, label: k.label, asked: asked.includes(k.id), earlier: earlier((e) => e.family === k.id) }))
    .concat([{ id: "crash", label: "Market crashes and credit crises", asked: false, earlier: earlier((e) => !ids.includes(e.family)) }])
    .filter((x) => x.earlier);
  return rows.length ? { rows, move, floorText: F.share(floor) } : null;
}

/* ruling R22 (clarity first): what #deep shows while its details are closed: one question, the answer as the two figures from
   B3's counts, the kinds matrix in words only (no number in a cell), the honesty lines. The section renders exactly these
   strings, and the node test counts the numbers in them (at most six). Everything else waits behind "Show the details". */
export const QUESTION = "Is it just 2022?";
/* R36 (F4): what monthly stand-ins miss, said plainly (never the lower-bound wording) */
export const MILDER = "Replayed monthly by similar indexes: probably milder than the real thing (monthly closes hide intraday and single-company falls).";
export const HONESTY = "This already happened; it is not a forecast. Earlier crises are replayed by similar indexes.";
export function closedView(m, k) {
  const L = m && m.show ? m.lead : null, figs = [];
  const tail = (n) => (n > 0 ? `; ${n} ${n === 1 ? "was" : "were"} too close to call.` : ".");
  const rule = m && m.floor ? `your ${m.floor.text.replace(/^\u2212/, "")} rule` : "your rule";
  const pts = (s) => (s.lo === s.hi ? `by ${s.lo.toFixed(1)} points` : `by ${s.lo.toFixed(1)} to ${s.hi.toFixed(1)} points`);
  const close = "too close to call with monthly similar indexes";
  if (L && L.after && m.move) {
    const s = L.after, just = !s.broke && s.past > 0;          // the same rule as today's mix below
    figs.push({ key: "move", label: "With the move", n: just ? s.past : s.broke, of: s.of,
      caption: just ? `earlier crises went just past ${rule} (${pts(s)}): ${close}.`
        : `earlier crises broke ${rule}${s.past ? `; ${s.past} more went just past it (${pts(s)}): ${close}.` : "."}` });
  }
  if (L && L.today) {
    const s = L.today, just = !s.broke && s.past > 0;          // nothing broke clearly: the figure counts the ones just past
    figs.push({ key: "today", label: "Your mix today", n: just ? s.past : s.broke, of: s.of,
      caption: just ? `went just past ${rule} (${pts(s)}): ${close}.`
        : `${figs.length ? "broke it" : `earlier crises broke ${rule}`}${s.past ? `; ${s.past} more went just past it (${pts(s)}): ${close}.` : "."}` });
  }
  const lead = figs[0];
  const cant = m && m.show && m.state === "cant_say"
    ? `Can’t say for the earlier crises: no similar index reaches back for ${m.missing.tickers.join(", ") || "this mix"}.` : null;
  const word = (c) => (c ? { cls: c.cls, word: c.word, why: c.why || null } : null);
  const kinds = k ? k.rows.map((x) => ({ id: x.id, label: x.label, asked: x.asked, lines: [
    { kind: "assumption", when: "Earlier crises", cant: !!x.earlier.cant, today: word(x.earlier.today), after: k.move ? word(x.earlier.after) : null }] })) : [];
  /* Simple shows only the question, this one answer sentence (B3's counts, as they are) and the lower-bound line */
  const crises = (s) => (s.all === null || s.of === s.all ? "earlier crises" : "replayed crises");
  const answer = cant ? cant : !lead ? null : lead.key === "move"
    ? (L.after.broke > 0 ? `No: with the move, ${L.after.broke} of ${lead.of} ${crises(L.after)} broke ${rule}.`
      : L.after.past > 0 ? `With the move, ${L.after.past} of the ${lead.of} ${crises(L.after)} went just past ${rule} (${pts(L.after)}): ${close}.`
        : `With the move, none of the ${lead.of} ${crises(L.after)} broke ${rule}.`)
    : (L.today.broke > 0 ? `No: ${L.today.broke} of ${lead.of} ${crises(L.today)} broke ${rule}.`
      : L.today.past > 0 ? `${L.today.past} of the ${lead.of} ${crises(L.today)} went just past ${rule} (${pts(L.today)}): ${close}.`
        : `None of the ${lead.of} ${crises(L.today)} broke ${rule}.`);
  /* the design director's folded view (item 8): the figure as a big readout beside one mark per crisis, in date order, for the
     same side: broke (filled), too close to call (amber outline), held (a hairline outline); the year under each mark */
  const sideKey = lead ? lead.key === "move" ? "after" : "today" : null;
  const marks = sideKey && m && m.rows ? m.rows.map((x) => { const s = x[sideKey], y = YM.exec(String(x.start || ""));
    return { cls: s && s.cls ? s.cls.key : null, year: y ? y[1] : "", short: y ? y[1].slice(2) : "",
      label: `${x.years}, ${x.title}: ${s && s.cls ? s.cls.say : "can\u2019t say"}` }; }) : [];
  const readout = lead ? { n: lead.n, of: lead.of, side: lead.key, word: lead.key === "move" ? "With the move" : "Your mix today" } : null;
  return { question: QUESTION, kindLine: "An assumption, replayed by similar indexes. It never changes the verdict.", marks, readout,
    no: !!(lead && lead.n > 0), figs, cant, kinds, move: !!(k && k.move), honesty: HONESTY, answer,
    line: `${MILDER} It never changes the verdict. ${HONESTY.split(". ")[0]}.`,
    legend: MILDER };
}
/* the numbers a closed #deep (Simple) puts on screen: the question, the answer, the lower-bound line (ruling R22 counts them) */
export function simpleText(v) { return [v.question, v.answer || "", v.readout ? `${v.readout.n} of ${v.readout.of}` : "", v.line].filter(Boolean); }
export function numbersIn(v) { return simpleText(v).join(" ").match(/\d+(?:[.,]\d+)?/g) || []; }
