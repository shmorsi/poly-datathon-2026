/* EPICENTRE Replay, lane U5: #money, where the money and the risk sat (design doc §2.4; rulings R1, R11, R13, R16).
   mount(el, store) draws, from the Result on the store (web/lib/money.js builds the model; every number is a Result value):
   1. the pair, large: the moved line's share of the money and its share of the risk, each over one bar on the same scale
      (the move magenta; the limit the checks measured it against drawn on its bar). "Too Canadian?" leads with Canada's
      share of the money and of the risk, today then with the move; a question with no move shows the line that carried the
      most risk, today only;
   2. the row under it: independent bets and Canada's shares, today then with the move;
   3. "The same 40 % in three bets" (result.ladder, R11) and "Leave 2022 out" (result.not_2022), when the Result has them;
   4. the notes: the persona's floor is an assumption (R13), history is not a forecast, the fiction label.
   Numbers with a facts row are buttons that open their thread (store.thread, lane U6's drawer). Motion (window.EPI_MOTION,
   never under reduced motion): once per run, when the pair comes into view, the risk bar grows out of the money bar and its
   figure counts up to the exact value (one rAF loop, the --dur-lamp token, the --ease-out curve). DOM by createElement. */
import { moneyModel, moneyLead, dialNote, compareOf, canadaLine } from "../lib/money.js";
import { say, plain } from "../lib/meaning.js";
import { head, details, mean, figs, marks, markIcon, term } from "./clarity.js";
import { standingLine } from "../lib/status.js";

const SVG = "http://www.w3.org/2000/svg";
export function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}
export function icon(id, cls) {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", cls || "icon");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  const u = document.createElementNS(SVG, "use");
  u.setAttribute("href", `#${id}`);
  s.append(u);
  return s;
}
/* the arrow between today and with the move (drawn: the page's sprite has none at this size) */
export function arrow() {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "mn-arrow");
  s.setAttribute("viewBox", "0 0 20 12");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", "M1 6h16M12.5 1.5 17.5 6l-5 4.5");
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", "1.5");
  p.setAttribute("stroke-linecap", "round");
  p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
}

/* a number: a button that opens its thread when the Result has its facts row, plain text otherwise */
export function num(text, fact, cls, label, meaning) {
  const n = !fact ? h("span", { class: cls }, text)
    : h("button", { type: "button", class: `${cls} is-traced`, "data-fact": fact, "aria-haspopup": "dialog", "aria-controls": "thread",
      "aria-label": `${label || text}. Open where this number came from.` }, text);
  return meaning ? mean(n, meaning) : n;
}

const motionOn = () => globalThis.EPI_MOTION !== false && !document.documentElement.classList.contains("motion-off")
  && !(globalThis.matchMedia && globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches);
const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
export function ms(name) { const t = token(name), v = parseFloat(t); return Number.isFinite(v) ? (/ms$/.test(t) ? v : v * 1000) : 0; }
/* the --ease-out token as a function of t (a cubic bezier, solved by bisection: the page's one curve, never a second one) */
export function curve(name) {
  const m = /cubic-bezier\(([^)]+)\)/.exec(token(name)), c = m ? m[1].split(",").map(Number) : [0.23, 1, 0.32, 1];
  const [x1, y1, x2, y2] = c.length === 4 && c.every(Number.isFinite) ? c : [0.23, 1, 0.32, 1];
  const at = (a, b, t) => 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3;
  return (x) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let lo = 0, hi = 1, t = x;
    for (let i = 0; i < 24; i++) { t = (lo + hi) / 2; if (at(x1, x2, t) < x) lo = t; else hi = t; }
    return at(y1, y2, t);
  };
}

/* ---- the pair: two lines, one scale; each segment is a full-width strip clipped to its stretch (so it can morph) ---- */
function layout(segs, key) {
  let at = 0;
  return segs.map((s) => { const w = s[key] === null ? 0 : Math.max(0, s[key]); const out = { l: at, w }; at += w; return out; });
}
const clip = (l, w) => `inset(0 calc(${(Math.max(0, 1 - l - w) * 100).toFixed(3)}% + 1px) 0 calc(${(l * 100).toFixed(3)}% + 1px))`;

function bar(which, pair, P) {
  const segs = pair.segments || [];
  const b = h("div", { class: "mn-bar", "data-bar": which, "aria-hidden": "true" });
  if (pair.kind === "canada") {
    const side = pair[which];
    const fill = h("span", { class: "mn-seg is-subject" });
    fill.style.clipPath = clip(0, side.v);
    b.append(fill);
    if (side.was) {
      const was = h("span", { class: "mn-was-mark", title: `Today ${side.was.text}` });
      was.style.left = `${(side.was.v * 100).toFixed(3)}%`;
      b.append(was);
    }
    return b;
  }
  const lay = layout(segs, which);
  segs.forEach((s, i) => {
    if (s[which] === null || s[which] <= 0) return;
    const seg = h("span", { class: `mn-seg${s.subject ? " is-subject" : ""}`, "data-key": s.key,
      title: `${s.key}: ${P.fmt.share(s.money)} of the money${s.risk === null ? "" : `, ${P.fmt.pct(s.risk)} of the risk`}` });
    seg.style.clipPath = clip(lay[i].l, lay[i].w);
    b.append(seg);
  });
  const tick = which === "money" ? pair.moneyTick : pair.riskTick;
  if (tick) {
    const t = h("span", { class: "mn-tick", "data-status": tick.status || null });
    t.style.left = `${(Math.abs(tick.v) * 100).toFixed(3)}%`;
    b.append(t);
  }
  return b;
}

function tickLabel(tick) {
  if (!tick) return null;
  const what = /warning/i.test(tick.label) ? "risk_warning" : "one_company_limit";
  const n = h("p", { class: "mn-tick-label", "data-status": tick.status || null }, tick.label, " ", mean(h("span", { class: "mn-fig" }, tick.text), say(what, tick.text)));
  n.style.setProperty("--x", String(Math.abs(tick.v)));
  return n;
}

function line(which, pair, P) {
  const side = pair[which];
  const fact = side.fact || null;
  const real = `${side.text} ${side.label}`;
  const figure = fact
    ? h("button", { type: "button", class: "mn-num is-traced", "data-fact": fact, "aria-haspopup": "dialog", "aria-controls": "thread",
      "aria-label": `${real}. Open where this number came from.` }, h("span", { class: "mn-num-vis", "aria-hidden": "true" }, side.text))
    : h("span", { class: "mn-num" }, h("span", { class: "mn-num-vis", "aria-hidden": "true" }, side.text), h("span", { class: "sr" }, side.text));
  const who = pair.kind === "canada" ? "Canadian lines" : pair.subject;
  mean(figure, which === "money" ? say("money_share", side.text, who) : say("risk_share", side.text, who));
  const was = side.was ? h("p", { class: "mn-line-was" }, "Today ", mean(h("span", { class: "mn-fig" }, side.was.text),
    say(which === "money" ? "money_share" : "risk_share", side.was.text, `${who}, today, without the move`))) : null;
  const tick = which === "money" ? pair.moneyTick : pair.riskTick;
  return h("div", { class: "mn-line", "data-line": which },
    h("p", { class: "mn-figwrap" }, figure),
    h("div", { class: "mn-track" },
      h("p", { class: "mn-label" }, side.label, was ? " " : null, was),
      bar(which, pair, P),
      tickLabel(tick)));
}

/* the text alternative of the two bars: every line's share of the money and of the risk */
function pairTable(pair, P) {
  if (!pair.segments) return null;
  /* a table sizes to its content whatever its width says, so the visually-hidden box is a block around it (never the table) */
  return h("div", { class: "mn-vh" }, h("table", {},
    h("caption", {}, "Each line of the mix: its share of the money and its share of the risk"),
    h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Line"), h("th", { scope: "col" }, "Share of the money"), h("th", { scope: "col" }, "Share of the risk"))),
    h("tbody", {}, pair.segments.map((s) => h("tr", {}, h("th", { scope: "row" }, s.key), h("td", {}, P.fmt.share(s.money)),
      h("td", {}, s.risk === null ? "not given" : P.fmt.pct(s.risk)))))));
}

function pairBlock(m, P) {
  const pair = m.pair;
  if (!pair) return null;
  return h("div", { class: "mn-pair", "data-kind": pair.kind },
    line("money", pair, P),
    line("risk", pair, P),
    pairTable(pair, P));
}

/* ---- G1 (the case: "returns and volatility calculated over an explicit period"): growth per year and volatility, today then
   with the move, over the replay's own dates, in CAD with dividends reinvested; volatility's tooltip says it is one indicator ---- */
function compareBlock(c) {
  if (!c) return null;
  const row = (label, a, b, kind, af, bf) => h("div", { class: "mn-cmp-row" }, h("dt", {}, label),
    h("dd", {}, num(a, af, c.after ? "mn-cmp-was" : "mn-cmp-now", `${label} today: ${a}`, say(kind, a, "today")),
      c.after ? h("span", { class: "mn-cmp-when" }, " today") : null,
      c.after ? [arrow(), num(b, bf, "mn-cmp-now", `${label} with the move: ${b}`, say(kind, b, "with the move")), h("span", { class: "mn-cmp-when" }, " with the move")] : null));
  return h("div", { class: "mn-compare" },
    h("p", { class: "mn-cmp-period" }, c.period),
    h("dl", { class: "mn-cmp" },
      row("Growth per year", c.today.cagr, c.after && c.after.cagr, "growth", c.today.cagrFact, c.after && c.after.cagrFact),
      row("Volatility, a year", c.today.vol, c.after && c.after.vol, "volatility", c.today.volFact, c.after && c.after.volFact)),
    h("p", { class: "mn-costs" }, markIcon("assumption"), h("span", { class: "sr" }, "Assumption: "), "Not counted: currency conversion costs, taxes and trading costs."),
    marks());
}

/* R39: "More spread, not softer: worst fall −11.9 % → −12.9 % (−14.2 % hedged like XSP)", every figure a key */
function canadaNode(c) {
  if (!c) return null;
  const fig = (text, words) => mean(h("span", { class: "cl-fig" }, text), say("worst_fall", text, words));
  return h("div", { class: "mn-xsp" },
    h("p", { class: "mn-xsp-line" }, h("strong", {}, `${c.lead}: `), "worst fall ", fig(c.today, "today"), " → ", fig(c.after, "with the move"), " (",
      fig(c.hedged, "hedged like XSP, by a similar index"), " hedged like XSP, ", h("span", { class: "mn-xsp-kind" }, markIcon(c.hedgedKind),
        h("span", { class: "sr" }, "assumption: "), "by a ", term("similar index")), ")."));
}

/* ---- the row under the pair: today, then with the move ---- */
function statMeaning(label, text, when) {
  const L = String(label || "");
  const kind = /independent bets/i.test(L) ? "bets" : /share of your money/i.test(L) ? "money_share" : /share of the risk/i.test(L) ? "risk_share" : null;
  const who = (/^(.+?)’s share/.exec(L) || [])[1];
  const x = who ? (who === "Canada" ? "Canadian lines" : who) : null;
  if (!kind) return say(L.toLowerCase(), text, when);
  return kind === "bets" ? say("bets", text, when) : say(kind, text, `${x || "it"}, ${when}`);
}
function statsBlock(m) {
  if (!m.stats.length) return null;
  const moved = m.kind !== "mix";
  return h("div", { class: "mn-statwrap" },
    h("p", { class: "mn-key" }, moved ? "Today, then with the move" : "Today"),
    h("ul", { class: "mn-stats", "data-n": String(m.stats.length) }, m.stats.map((s) => {
      const said = [s.today ? `today ${s.today.text}` : null, s.after ? `with the move ${s.after.text}` : null].filter(Boolean).join(", ");
      return h("li", { class: "mn-stat" },
        h("p", { class: "mn-stat-label" }, s.label),
        h("p", { class: "mn-stat-val", "aria-label": `${s.label}: ${said}` },
          s.today ? num(s.today.text, s.today.fact, s.after ? "mn-stat-was" : "mn-stat-now", `${s.label} today, ${s.today.text}`, statMeaning(s.label, s.today.text, "today")) : null,
          s.today && s.after ? arrow() : null,
          s.after ? num(s.after.text, s.after.fact, "mn-stat-now", `${s.label} with the move, ${s.after.text}`, statMeaning(s.label, s.after.text, "with the move")) : null),
        s.note ? h("p", { class: "mn-stat-note" }, s.note) : null);
    })));
}

/* ---- R11: the same weight in three bets ---- */
function ladderBlock(m) {
  const L = m.ladder;
  if (!L) return null;
  const f = L.floor ? Math.abs(L.floor.v) / L.scale : null;
  const amount = L.amountText ? `your ${L.amountText}` : "your amount";
  const head = h("div", { class: "mn-lrow mn-lhead", role: "row" },
    h("span", { class: "mn-lc c-name", role: "columnheader" }, `Where the ${L.weightText} went`),
    h("span", { class: "mn-lc c-gauge", role: "columnheader" },
      h("span", { class: "sr" }, "Worst fall against the floor"),
      f === null ? null : h("span", { class: "mn-floor-lbl", "aria-hidden": "true", "data-side": f > 0.6 ? "left" : "right", style: `--f:${f.toFixed(4)}` },
        "Your floor ", h("b", {}, L.floor.text))),

    h("span", { class: "mn-lc c-dd", role: "columnheader" }, "Worst fall"),
    h("span", { class: "mn-lc c-end", role: "columnheader" }, "Ended at"),
    h("span", { class: "mn-lc c-verdict", role: "columnheader" }, m.phrase.charAt(0).toUpperCase() + m.phrase.slice(1)));
  const rows = (L.today ? [L.today, ...L.rows] : L.rows).map((x) => {
    const d = Math.abs(x.dd) / L.scale;
    const gauge = h("span", { class: "mn-lc c-gauge", role: "cell" },
      h("span", { class: "sr" }, `${x.ddText}${x.beyond === true ? ", past the floor" : x.beyond === false ? ", inside the floor" : ""}`),
      f !== null && d > f ? h("span", { class: "mn-zone", "aria-hidden": "true", style: `--f:${f.toFixed(4)};--d:${d.toFixed(4)}` }) : null,
      h("span", { class: `mn-gbar${x.isMove ? " is-move" : x.isToday ? " is-today" : ""}`, "aria-hidden": "true", style: `--d:${d.toFixed(4)}` }),
      f === null ? null : h("span", { class: "mn-floor", "aria-hidden": "true", style: `--f:${f.toFixed(4)}` }));
    return h("div", { class: `mn-lrow${x.isMove ? " is-move" : x.isToday ? " is-today" : ""}`, role: "row" },
      h("span", { class: "mn-lc c-name", role: "rowheader" }, h("span", { class: "mn-lname" }, x.name),
        h("span", { class: "mn-lsub" }, h("span", { class: "mn-ltk" }, x.ticker || x.note), x.isMove ? h("span", { class: "mn-ltag-move" }, "the move") : null)),
      gauge,

      h("span", { class: "mn-lc c-dd", role: "cell" }, h("span", { class: "mn-lbl" }, "Worst fall"), mean(h("span", { class: "mn-fig" }, x.ddText), say("worst_fall", x.ddText, `with ${L.weightText} in ${x.name}`)),
        x.floorWord ? h("span", { class: "mn-floorword", "data-cls": x.floorWord.cls }, x.floorWord.word) : null),
      h("span", { class: "mn-lc c-end", role: "cell" }, x.endText ? [h("span", { class: "mn-lbl" }, "Ended at"), mean(h("span", { class: "mn-fig" }, x.endText), say("end_value", x.endText))] : null),
      h("span", { class: "mn-lc c-verdict", role: "cell" }, x.verdict
        ? h("span", { class: "mn-verdict", "data-tone": x.verdict.tone }, icon(x.verdict.icon), x.verdict.word) : null));
  });
  const who = `Your ${L.weightText}`;
  return h("section", { class: "mn-ladder", "aria-labelledby": "mn-ladder-title" },
    h("div", { class: "mn-sub-head" },
      h("h3", { class: "mn-h3", id: "mn-ladder-title" }, `The same ${L.weightText} in ${L.countWord} bets.`),
      h("p", { class: "mn-sub-lede" }, `${who}, put in one bet at a time on the same history: how far each fell against your floor. Only your mix today and the move you asked about are judged against all your limits.`),
      h("p", { class: "mn-kind" }, icon("m-fact", "kind"), h("span", {}, "Fact: real 2021–26 prices, judged by the same checks."))),
    h("div", { class: "mn-lt", role: "table", "aria-labelledby": "mn-ladder-title" }, head, rows),
    h("p", { class: "standing-line mn-standing", text: standingLine(true) }));
}

/* a readout's plain words by its own label (lane clarity) */
function readMeaning(label, text) {
  const L = String(label || "");
  if (/^worst fall in 2022/i.test(L)) return say("worst_fall", text, "within 2022");
  if (/^worst fall/i.test(L)) return say("worst_fall", text);
  if (/^ended at/i.test(L)) return say("end_value", text);
  return say(L.charAt(0).toLowerCase() + L.slice(1), text);
}

/* ---- R19(b), "Too Canadian?": the workshop's XSP question (result.hedge_compare, lane B3) ---- */
function hedgeBlock(m) {
  const H = m.hedge;
  if (!H) return null;
  const read = (label, text, fact) => (text ? h("div", {}, h("dt", {}, label), h("dd", {}, num(text, fact, "mn-fig", `${label}: ${text}`, readMeaning(label, text)))) : null);
  const col = (x, title, sub) => h("div", { class: "mn-hedge-col", "data-kind": x.kind },
    h("p", { class: "mn-hedge-label" }, icon(x.kind === "fact" ? "m-fact" : "m-assumption", "kind"),
      h("span", { class: "sr" }, x.kind === "fact" ? "Fact: " : "Assumption: "), title),
    h("p", { class: "mn-hedge-sub" }, sub),
    h("dl", { class: "mn-hedge-dl" }, read("Worst fall", x.ddText, x.ddFact), read("Worst fall in 2022", x.y2022Text, x.y2022Fact),
      read("Ended at", x.endText, x.endFact)));
  const S = H.sentence;
  const said = S ? h("p", { class: "mn-hedge-text" }, `In 2022 ${H.ticker} returned `, num(S.usd, S.usdFact, "mn-fig"), " in US dollars and ",
    num(S.cad, S.cadFact, "mn-fig"), " in Canadian dollars",
    S.pp ? [`: unhedged, the currency ${S.softened ? "softened" : "deepened"} the year by `, h("span", { class: "mn-fig" }, `${S.pp}\u00a0points`),
      ". A fund hedged to the Canadian dollar follows the US-dollar return."] : ".") : null;
  return h("section", { class: "mn-hedge", "aria-labelledby": "mn-hedge-title" },
    h("div", { class: "mn-sub-head" },
      h("h3", { class: "mn-h3", id: "mn-hedge-title" }, "The workshop\u2019s question: would XSP help?"),
      h("p", { class: "mn-sub-lede" }, `Your mix with ${H.weightText || "the move"} of the S&P 500, two ways: unhedged, as ${H.ticker} in Canadian dollars, and hedged to the Canadian dollar, the way XSP is built.`)),
    h("div", { class: "mn-hedge-pair" },
      col(H.unhedged, "Unhedged, in Canadian dollars", `${H.ticker} converted every day at the Bank of Canada rate, as the verdict judged it.`),
      col(H.hedged, "Hedged to the Canadian dollar, by a similar index", `${H.ticker} on its US-dollar returns, no hedging cost counted.`)),
    said,
    H.method ? h("p", { class: "mn-hedge-method" }, icon("m-assumption", "kind"), h("span", {}, plain(H.method))) : null, marks());
}

/* ---- "Even without 2022:": result.not_2022, the worst fall on the dates from 2023 on, in the floor's own terms (R13) ---- */
function not2022Block(m) {
  const n = m.not2022;
  if (!n) return null;
  const fig = (text, fact, label, meaning) => num(text, fact, "mn-fig", label, meaning);
  const subject = n.moved ? "the mix with the move" : "this mix";
  const lead = `counting only from ${n.from} on, ${subject} ${n.beyond === true ? "still fell " : "fell at most "}`;
  const floorPart = n.floorText
    ? (n.beyond === true ? [", past your ", n.floorText, " floor"] : n.beyond === false ? [", inside your ", n.floorText, " floor"] : [])
    : [];
  return h("section", { class: "mn-n22", "aria-labelledby": "mn-n22-title" },
    n.status ? h("p", { class: "mn-status", "data-tone": n.status.tone }, icon(n.status.icon), n.status.word) : null,
    h("p", { class: "mn-n22-text" }, h("strong", { class: "mn-runin", id: "mn-n22-title" }, "Even without 2022:"), " ", lead,
      fig(n.fallText, n.facts.depth, `${n.fallText}, the worst fall from ${n.from} on`, say("worst_fall", n.fallText, `counting only from ${n.from} on`)),
      " from its high (", n.peak, " to ", n.trough, ")", ...floorPart, ".",
      n.path ? [" In dollars it went from ", h("span", { class: "mn-fig" }, n.path.from), " to ", h("span", { class: "mn-fig" }, n.path.to),
        n.path.fall ? [" (", mean(h("span", { class: "mn-fig" }, n.path.fall), say("worst_dollars", n.path.fall, "on the path itself")), ")"] : null, "."] : null,
      n.back ? [" It was back at its high by ", n.back, "."] : null));
}

/* ---- Mateo's test: what your values cost in this replay (result.price_of_values) ---- */
function valuesBlock(m) {
  const V = m.values;
  if (!V) return null;
  const col = (x, title) => h("div", { class: "mn-hedge-col", "data-kind": x.kind },
    h("p", { class: "mn-hedge-label" }, icon(x.kind === "fact" ? "m-fact" : "m-assumption", "kind"),
      h("span", { class: "sr" }, x.kind === "fact" ? "Fact: " : "Assumption: "), title),
    h("p", { class: "mn-hedge-sub" }, x.label || ""),
    h("dl", { class: "mn-hedge-dl" }, x.rows.map((y) => h("div", {}, h("dt", {}, y.label), h("dd", {}, num(y.text, y.fact, "mn-fig", `${y.label}: ${y.text}`, readMeaning(y.label, y.text)))))));
  const out = V.removed.length ? V.removed.join(" and ") : "the lines your values screen excludes";
  return h("section", { class: "mn-hedge mn-values", "aria-labelledby": "mn-values-title" },
    h("div", { class: "mn-sub-head" },
      h("h3", { class: "mn-h3", id: "mn-values-title" }, "What your values cost in this replay."),
      h("p", { class: "mn-sub-lede" }, `Your portfolio as it is, beside the same portfolio without ${out}, the rest scaled up.`)),
    h("div", { class: "mn-hedge-pair" }, col({ ...V.now, label: V.now.note }, "As it is"), col(V.alt, `Without ${out}`)),
    V.sentence ? h("p", { class: "mn-hedge-text" }, V.sentence) : null,
    h("p", { class: "mn-hedge-method" }, icon("m-assumption", "kind"),
      h("span", {}, "Assumption: the money in the excluded lines is spread over the others in proportion; the same prices and shocks, judged the same way.")), marks());
}

/* ---- the twist: the risk bar grows out of the money bar, its figure counts up to the exact value ---- */
function twistOf(root, pair, P) {
  if (pair && pair.kind === "canada") return canadaTwist(root, pair, P);
  if (!pair || !pair.segments) return null;
  const riskBar = root.querySelector('.mn-bar[data-bar="risk"]'), vis = root.querySelector('.mn-line[data-line="risk"] .mn-num-vis');
  if (!riskBar || !vis) return null;
  const segs = pair.segments, from = layout(segs, "money"), to = layout(segs, "risk");
  const els = segs.map((s) => riskBar.querySelector(`.mn-seg[data-key="${CSS.escape(s.key)}"]`));
  const a = pair.money.v, b = pair.risk.v;
  return function paint(p) {
    const e = Math.max(0, Math.min(1, p));
    segs.forEach((s, i) => {
      const el = els[i];
      if (!el) return;
      el.style.clipPath = clip(from[i].l + (to[i].l - from[i].l) * e, from[i].w + (to[i].w - from[i].w) * e);
    });
    vis.textContent = e <= 0 ? pair.money.text : e >= 1 ? pair.risk.text : P.fmt.pct(a + (b - a) * e);
    root.dataset.twist = e >= 1 ? "done" : "on";
  };
}

/* "Too Canadian?": both shares roll from today to with the move, each bar's fill with its figure */
function canadaTwist(root, pair, P) {
  const lines = ["money", "risk"].map((w) => ({ side: pair[w], fill: root.querySelector(`.mn-bar[data-bar="${w}"] .mn-seg`),
    vis: root.querySelector(`.mn-line[data-line="${w}"] .mn-num-vis`) }));
  if (lines.some((l) => !l.fill || !l.vis || !l.side.was)) return null;
  return function paint(p) {
    const e = Math.max(0, Math.min(1, p));
    for (const l of lines) {
      const v = l.side.was.v + (l.side.v - l.side.was.v) * e;
      l.fill.style.clipPath = clip(0, v);
      l.vis.textContent = e <= 0 ? l.side.was.text : e >= 1 ? l.side.text : P.fmt.pct(v);
    }
    root.dataset.twist = e >= 1 ? "done" : "on";
  };
}

/* ---- mount ---- */
export function mount(el, store) {
  if (!el) return;
  el.classList.add("mn");
  el.setAttribute("aria-labelledby", "money-title");
  let lastResult, paint = null, played = false, io = null, raf = 0, drawn = false;
  const P = () => globalThis.PF;

  function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
  function play() {
    if (!paint || played) return;
    played = true;
    if (!motionOn()) { paint(1); return; }
    const dur = ms("dur-lamp") * 1.5, ease = curve("ease-out"), t0 = performance.now();
    const step = (now) => {
      const p = dur > 0 ? Math.min(1, (now - t0) / dur) : 1;
      paint(ease(p));
      raf = p < 1 ? requestAnimationFrame(step) : 0;
    };
    raf = requestAnimationFrame(step);
  }

  function draw() {
    stop();
    if (io) { io.disconnect(); io = null; }
    const st = store.get() || {}, m = P() ? moneyModel(st.result, st.view, P()) : null;
    if (!m) { el.replaceChildren(); el.hidden = true; return; }
    el.hidden = false;
    const pair = m.pair, L = moneyLead(st.result, st.view, P());
    const note = dialNote(st.result, st.view, st.weightIndex, P());
    const who = pair && (pair.kind === "canada" ? "Canadian lines" : pair.subject);
    const explain = pair ? h("p", { class: "mn-explain" }, pair.kind === "canada"
      ? "Share of the risk: how much of the mix’s ups and downs came from its Canadian lines, on their daily prices."
      : "Share of the risk: how much of the mix’s ups and downs each line caused, on its daily prices.") : null;
    const frame = h("div", { class: "frame mn-frame" },
      head("money-title", L.question, figs(L.answer, pair ? [{ text: pair.risk.text, meaning: say("risk_share", pair.risk.text, who) }] : [])),
      h("p", { class: "mn-dial", "aria-live": "polite", hidden: !note }, note || ""),
      pairBlock(m, P()),
      compareBlock(compareOf(st.result, st.view, P())),
      canadaNode(canadaLine(st.result, st.view, P())),
      L.notes ? h("p", { class: "cl-quiet mn-honest" }, L.notes) : null,
      details("money", store, [explain, statsBlock(m), valuesBlock(m), hedgeBlock(m), ladderBlock(m), not2022Block(m),
        m.notes.floor ? h("p", { class: "cl-quiet mn-note-floor" }, m.notes.floor) : null], { label: "Where the risk sat: the details" }));
    if (drawn && motionOn()) frame.classList.add("is-swap");          // another run landed: the new numbers fade in, nothing moves
    drawn = true;
    el.replaceChildren(frame);
    paint = twistOf(frame, pair, P());
    played = false;
    el.__u5 = { model: m, freeze(p) { stop(); played = true; if (io) { io.disconnect(); io = null; } if (paint) paint(p); } };
    if (!paint) return;
    if (!motionOn() || !("IntersectionObserver" in globalThis)) { played = true; paint(1); return; }
    paint(0);
    const target = frame.querySelector(".mn-pair");
    io = new IntersectionObserver((es) => { if (es.some((x) => x.isIntersecting)) { io.disconnect(); io = null; play(); } }, { threshold: 0.6 });
    io.observe(target);
  }

  el.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-fact]");
    if (b && el.contains(b)) store.set({ thread: b.dataset.fact });
  });
  let queued = false;
  const later = () => { if (queued) return; queued = true; queueMicrotask(() => { queued = false; draw(); }); };   // result + view land together
  store.on("result", (r) => { if (r !== lastResult) { lastResult = r; later(); } });
  store.on("view", later);
  store.on("weightIndex", () => {
    const st = store.get() || {}, n = el.querySelector(".mn-dial"), text = dialNote(st.result, st.view, st.weightIndex, P());
    if (!n) return;
    n.textContent = text || "";
    n.hidden = !text;
  });
  lastResult = (store.get() || {}).result;
  draw();
}
