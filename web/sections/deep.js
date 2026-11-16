/* EPICENTRE Replay, lane U8: #deep, "Not just 2022" (design doc R5, R11). mount(el, store) draws the Result's deep history:
   the sourced crises before 2021 replayed by stand-in, today's mix against the move and the stand-in alone, the investor's
   floor ruled through every row. Every number is a Result value through PF.fmt (web/lib/deep.js builds the model); the
   section hides itself when the Result has no deep_history. A disclosure: it never changes the verdict. */
import { plain } from "../lib/meaning.js";              // plain words (lane clarity, the cold-user test): data-written notes too
import { deepModel, stripesOf, kindsOf, closedView, CLASS } from "../lib/deep.js";

const SVG = "http://www.w3.org/2000/svg";
function h(tag, props, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "vars") for (const [p, x] of Object.entries(v)) { if (x !== null && x !== undefined) n.style.setProperty(p, String(x)); }
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}
function s(tag, attrs, ...kids) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, String(v));
  for (const c of kids) n.append(c);
  return n;
}
const hide = { "aria-hidden": "true", focusable: "false" };
/* the kind markers: index.html's #m-fact / #m-assumption symbols; the same shapes drawn in place where the page has no sprite */
const mark = (kind) => s("svg", { class: "deep-mark", viewBox: "0 0 12 12", ...hide },
  ...(document.getElementById(`m-${kind}`) ? [s("use", { href: `#m-${kind}` })]          // the page's own symbol (ruling R16)
    : kind === "fact" ? [s("circle", { cx: 6, cy: 6, r: 5, fill: "currentColor" })]
    : [s("circle", { cx: 6, cy: 6, r: 4.25, fill: "none", stroke: "currentColor", "stroke-width": 1.5 }),
      s("path", { d: "M6 1A5 5 0 0 0 6 11Z", fill: "currentColor" })]));
/* the class glyph is the gauge in small: the gold floor and a bar that stops short of it, reaches it or goes through it */
const END = { held: 6, touched: 9.25, broke: 15 };
const glyph = (key) => s("svg", { class: "deep-glyph", viewBox: "0 0 16 12", ...hide },
  s("rect", { x: 1, y: 4.5, width: END[key] - 1, height: 3, fill: "currentColor" }),
  s("path", { class: "deep-glyph-floor", d: "M9.25 1.5v9" }));

const possessive = (name) => (name ? `${name}’s` : null);
const num = (text, kind) => h("span", { class: "deep-n" }, kind ? mark(kind) : null, h("span", { text }));
const month = (PF, ym) => PF.fmt.month(`${ym}-01`);

/* inside the details: what the old header said (the method line, the robust-claims sentence and its sensitivity line) */
function head(m) {
  const span = m.span ? `, ${m.span.from} to ${m.span.to},` : "";
  return h("div", { class: "deep-dhead" },
    h("p", { class: "deep-lede", id: "deep-lede", text: m.state === "ok" ? `${m.n} earlier crises${span} replayed on ${m.on} with similar public indexes that existed then.`
      : `${m.n} earlier crises${span} by similar public indexes that existed then.` }),
    m.claims.length ? h("p", { class: "deep-claim", text: m.claims.join(" ") }) : null,
    m.claims.length && m.claimTest.test ? h("p", { class: "deep-test" }, mark("assumption"), h("span", { text: m.claimTest.test })) : null,
    !m.claims.length && m.claimTest.none && m.state === "ok" ? h("p", { class: "deep-test" }, h("span", { text: m.claimTest.none })) : null);
}

/* ruling R22, the closed view: one question, the two figures as the answer, the kinds in words, the honesty line */
function closed(v) {
  const fig = (f) => h("p", { class: `deep-fig f-${f.key}` },
    h("span", { class: "deep-fig-lbl" }, h("span", { class: `deep-key k-${f.key === "move" ? "move" : "today"}`, "aria-hidden": "true" }), h("span", { text: f.label }),
      h("span", { class: "sr", text: ":" })),
    h("span", { class: "deep-fig-n" }, h("b", { text: String(f.n) }), h("span", { text: ` of ${f.of}` })),
    h("span", { class: "deep-fig-txt", text: f.caption }));
  const word = (c) => (c ? h("span", { class: "deep-cls", "data-tone": c.cls, title: c.why || null }, glyph(c.cls), h("span", { text: c.word }),
    c.why ? h("span", { class: "sr", text: `: ${c.why}` }) : null) : null);
  const cant = () => h("span", { class: "deep-val is-none", text: "Can\u2019t say" });
  const matrix = v.kinds.length ? h("div", { class: "deep-kinds is-words", "data-move": v.move ? "yes" : "no" },
    h("h3", { class: "deep-h3 deep-kq", id: "deep-kq", text: "Did your rule survive each kind of earlier crisis?" }),
    h("div", { class: "deep-ktable", role: "table", "aria-labelledby": "deep-kq" },
      h("div", { role: "row", class: "deep-krow deep-khead" },
        h("span", { role: "columnheader", class: "kc-kind", text: "Kind of crisis" }),
        h("span", { role: "columnheader", class: "kc-today" }, h("span", { class: "deep-key k-today", "aria-hidden": "true" }), h("span", { text: "Your mix today" })),
        v.move ? h("span", { role: "columnheader", class: "kc-after" }, h("span", { class: "deep-key k-move", "aria-hidden": "true" }), h("span", { text: "With the move" })) : null),
      v.kinds.flatMap((x) => x.lines.map((l, i) => h("div", { role: "row", class: "deep-krow", "data-first": i === 0 ? "yes" : "no" },
        h("div", { role: "rowheader", class: "kc-kind" }, h("span", { class: i === 0 ? "deep-ttl" : "sr", text: x.label }),
          i === 0 && x.asked ? h("span", { class: "deep-asked", text: "The kind you asked about" }) : null),
        h("div", { role: "cell", class: "kc-today" }, l.cant ? cant() : word(l.today)),
        v.move ? h("div", { role: "cell", class: "kc-after" }, l.cant ? cant() : word(l.after)) : null))))) : null;
  /* Simple (the fintech-UX pass): only the question, its one answer sentence and the lower-bound line; the figures and the kinds
     matrix open first in the details, so Detailed still shows all of it */
  const sw = (k) => h("span", { class: `deep-sw sw-${k}`, "aria-hidden": "true" });
  const readout = v.readout && v.marks.length ? h("div", { class: "deep-readout" },
    h("p", { class: "deep-big" }, h("span", { class: "deep-big-lbl" }, h("span", { class: `deep-key k-${v.readout.side === "move" ? "move" : "today"}`, "aria-hidden": "true" }),
      h("span", { text: v.readout.word })), h("span", { class: "deep-big-n" }, h("b", { text: String(v.readout.n) }), h("span", { class: "deep-big-of", text: ` of ${v.readout.of}` }))),
    h("div", { class: "deep-markbox" },
      h("ol", { class: "deep-marks", "aria-label": "Each earlier crisis, in date order" }, v.marks.map((x) => h("li", { class: "deep-markc", "data-cls": x.cls || "none", title: x.label },
        h("span", { class: "deep-dot", "aria-hidden": "true" }), h("span", { class: "deep-yr4", "aria-hidden": "true", text: x.year }),
        h("span", { class: "deep-yr2", "aria-hidden": "true", text: x.short }), h("span", { class: "sr", text: x.label })))),
      h("p", { class: "deep-mkey", "aria-hidden": "true" },
        [["broke", "Broke your floor"], ["touched", "Too close to call"], ["held", "Held above your floor"]].map(([k, w]) => h("span", { class: "deep-mk" }, sw(k), h("span", { text: w })))))) : null;
  return { simple: h("header", { class: "deep-r22" },
      h("h2", { class: "deep-title", id: "deep-title", text: v.question }),
      v.answer ? h("p", { class: "deep-answer", text: v.answer }) : null,
      readout,
      h("p", { class: "deep-kind" }, mark("assumption"), h("span", { text: v.line }))),
    more: [v.figs.length ? h("div", { class: "deep-lead", "data-n": v.figs.length }, v.figs.map(fig)) : null, matrix] };
}

function side(m) {
  if (!m.proxies.length) return null;
  return h("div", { class: "deep-note deep-side", role: "group", "aria-labelledby": "deep-who" },
    h("h3", { class: "deep-h3", id: "deep-who", text: "Who stands in for whom" }),
    h("ul", { class: "deep-proxies" }, m.proxies.map((p) => h("li", { "data-strength": p.strength || null },
      h("span", { class: "deep-tk", text: p.ticker }), h("span", { class: "deep-lb", text: p.label }),
      p.strength ? h("span", { class: "deep-st", text: p.strength === "can\u2019t say" || p.strength === "can't say" ? "can\u2019t say" : `${p.strength} match` }) : null))));
}

/* one readout cell: the value and its class (icon + word), or "Can't say" when that side was not replayed */
function readout(sd, col) {
  return h("div", { role: "cell", class: `deep-c ${col}` },
    sd ? [h("span", { class: "deep-val", text: sd.text }),
      sd.cls ? h("span", { class: "deep-cls", "data-tone": sd.cls.tone, title: sd.why || null }, glyph(sd.cls.key), h("span", { text: sd.cls.word }),
        sd.why ? h("span", { class: "sr", text: `: ${sd.why}` }) : null) : null]
      : h("span", { class: "deep-val is-none", text: "Can’t say" }));
}

function table(m, PF) {
  const mv = m.move, alone = mv && m.cols.alone ? "Similar index alone" : null;
  const key = (k) => h("span", { class: `deep-key k-${k}`, "aria-hidden": "true" });
  const L = { today: "Today’s mix", after: "With the move", worse: "Compared with today" };
  const hrow = h("div", { role: "row", class: "deep-row deep-hrow" },
    h("span", { role: "columnheader", class: "deep-c c-crisis" }, key("none"), h("span", { text: "Crisis" })),
    h("span", { class: "deep-c c-gauge", "aria-hidden": "true" }, m.floor ? [h("span", { class: "g-floor" }),
      h("span", { class: "g-floor-lbl" }, h("span", { text: "Your floor" }), h("b", { text: m.floor.text }))] : null),
    h("span", { role: "columnheader", class: "deep-c c-today" }, key("today"), h("span", { text: L.today })),
    m.cols.after ? h("span", { role: "columnheader", class: "deep-c c-after" }, key("move"), h("span", { text: L.after }),
      mv.weightText ? h("span", { class: "deep-sub", text: `${mv.name} ${mv.weightText}` }) : null) : null,
    alone ? h("span", { role: "columnheader", class: "deep-c c-alone" }, key("alone"), h("span", { text: alone })) : null,
    m.cols.worse ? h("span", { role: "columnheader", class: "deep-c c-worse" }, key("none"), h("span", { text: L.worse })) : null);
  const ncols = 2 + [m.cols.after, alone, m.cols.worse].filter(Boolean).length;
  const rows = m.rows.map((x, i) => { const more = detail(m, x, PF, `deep-d-${i}`, ncols); return h("div", { role: "row", class: "deep-row", "data-i": i, vars: { "--i": i } },
    h("div", { role: "rowheader", class: "deep-c c-crisis" },
      x.url ? h("a", { class: "deep-ttl", href: x.url, target: "_blank", rel: "noopener noreferrer", text: x.title })
        : h("span", { class: "deep-ttl", text: x.title }),
      h("span", { class: "deep-meta" }, h("span", { class: "deep-yr", text: x.years }), x.place ? h("span", { class: "deep-pl", title: x.place, text: x.place }) : null),
      x.asked && m.askedLabel ? h("span", { class: "deep-asked", text: `${m.askedLabel}, the kind of shock you asked about` }) : null,
      more ? h("button", { type: "button", class: "deep-more", "aria-expanded": "false", "aria-controls": `deep-d-${i}` },
        s("svg", { viewBox: "0 0 12 12", ...hide }, s("path", { d: "M3 4.5l3 3 3-3", fill: "none", stroke: "currentColor", "stroke-width": 1.5 })),
        h("span", { class: "sr", text: `Details: ${x.title}` })) : null),
    h("div", { class: "deep-c c-gauge", "aria-hidden": "true" }, m.floor ? h("span", { class: "g-floor" }) : null,
      x.g.zone !== null ? h("span", { class: "g-zone", vars: { "--z": x.g.zone } }) : null,
      x.today ? h("span", { class: "g-bar g-today", vars: { "--d": x.g.t } }) : null,
      x.after ? h("span", { class: "g-bar g-move", vars: { "--d": x.g.a } }) : null,
      x.alone ? h("span", { class: "g-alone", vars: { "--d": x.g.al } }) : null),
    readout(x.today, "c-today"),
    m.cols.after ? readout(x.after, "c-after") : null,
    alone ? h("div", { role: "cell", class: "deep-c c-alone" }, h("span", { class: "deep-val is-alone", text: x.alone ? x.alone.text : "" })) : null,
    m.cols.worse ? h("div", { role: "cell", class: "deep-c c-worse" },
      x.worse === null ? null : h("span", { class: "deep-worse", "data-worse": x.worse === "close" ? "close" : x.worse ? "yes" : "no",
        text: x.worse === "close" ? "Too close to call" : x.worse ? "Worse" : "No worse" })) : null, more); });
  const big = m.scale > 0.5, ticks = [];
  for (let k = 0; k <= Math.round(m.scale * 10); k += big ? 2 : 1) ticks.push({ x: k / 10 / m.scale, text: PF.fmt.pct(-k / 10, 0) });
  const arow = h("div", { class: "deep-row deep-arow", "aria-hidden": "true" }, h("span", { class: "deep-c c-crisis", text: "Worst fall, month-end" }),
    h("span", { class: "deep-c c-gauge" }, ticks.map((t) => h("span", { class: t.x > 0.95 ? "g-tick is-end" : "g-tick", vars: { "--x": t.x }, text: t.text.replace(/^−0/, "0") }))));
  const keyLine = m.robust ? h("p", { class: "deep-keyline", id: "deep-keyline" }, "Broke and Held come out the same in every sensitivity run; Touched is too close to call: within a point of your floor, or it changes with your floor, the window or the weighting.") : null;
  return [h("div", { class: "deep-table", role: "table", "aria-labelledby": "deep-title", "aria-describedby": keyLine ? "deep-lede deep-keyline" : "deep-lede",
    "data-move": mv ? "yes" : "no", "data-cols": [m.cols.after, alone, m.cols.worse].filter(Boolean).length + 1,
    "data-floor": m.floor && m.floor.f > 0.6 ? "end" : null,           // a floor near the gauge's end labels to its left
    vars: { "--f": m.floor ? m.floor.f : null, "--step": `${(m.step * 100).toFixed(4)}%` } }, hrow, rows, arow), keyLine];
}

/* one crisis in full: high to low, the same fall in dollars on the investor's amount (R13), the months back, the source */
function detail(m, x, PF, id, ncols) {
  const F = PF.fmt, on = m.on;
  const line = (label, sd) => {
    if (!sd || !sd.peak || !sd.trough) return null;
    const back = sd.months === null ? " Not back to that high within the data." : ` Back to that high ${sd.months === 1 ? "1 month" : `${sd.months} months`} later.`;
    return h("p", {}, h("b", { text: `${label}: ` }), `from its high in ${month(PF, sd.peak)} to its low in ${month(PF, sd.trough)}, `, num(sd.text, "assumption"),
      sd.dollars !== null && on ? [`; the same fall on ${on} is `, num(F.money(-sd.dollars), "assumption"), "."] : ".", back,
      sd.cls && sd.why ? ` ${sd.cls.word}: ${sd.why}.` : "");
  };
  const parts = [x.place ? h("p", {}, h("b", { text: "Where it started: " }), x.place) : null, line("Today’s mix", x.today), m.move ? line("With the move", x.after) : null,
    m.move && x.alone && x.alone.trough ? h("p", {}, h("b", { text: `${m.standIn ? theLabel(m.standIn.label) : "The similar index"} alone: ` }), num(x.alone.text, "assumption"),
      `, its low in ${month(PF, x.alone.trough)}.`) : null,
    x.url ? h("p", { class: "deep-src" }, "Source: ", h("a", { href: x.url, target: "_blank", rel: "noopener noreferrer", text: x.sourceTitle || x.url.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0] })) : null].filter(Boolean);
  if (parts.length < 3) return null;                                   // a place and a source alone are already on the row
  return h("div", { role: "cell", "aria-colspan": ncols, class: "deep-detail", id, hidden: true }, parts);
}

function note(title, ...body) {
  return h("div", { class: "deep-note" }, h("h3", { class: "deep-h3", text: title }), h("p", {}, ...body));
}
const span = (PF, w) => (w ? `From ${month(PF, w.start)} to ${month(PF, w.end)}` : null);
const theLabel = (label) => (/^the\s/i.test(label) ? `The${label.slice(3)}` : `The ${label}`);
function notes(m, PF) {
  const F = PF.fmt, v = m.validation, mv = m.move, g = m.gentle, out = [];
  if (v) {
    const when = span(PF, v.window), close = (s) => (s.within === true ? ", within 2 points" : "");
    out.push(note("Checked against the real funds",
      v.today ? [`${when ? `${when}, the` : "The"} similar indexes gave `, num(F.pct(v.today.proxy), "assumption"), " for today’s mix; the real funds gave ",
        num(F.pct(v.today.real), "fact"), `${close(v.today)}.`] : null,
      v.after && mv ? [" With the move: ", num(F.pct(v.after.proxy), "assumption"), " by similar index, ", num(F.pct(v.after.real), "fact"), " with the real funds",
        v.after.gap !== null && v.after.gap > 0 ? `, ${v.after.gap.toFixed(1)} points gentler` : "",
        v.weak || (v.after.gap !== null && v.after.gap > 2) ? ", so the rows with the move are probably milder than the real thing." : "."] : null));
  }
  if (mv && g) {
    const who = m.standIn ? `${theLabel(m.standIn.label)} stands in for ${mv.name}.` : `A similar index replays ${mv.name}.`, when = span(PF, g.window);
    const nums = [` ${when ? `${when}, ` : ""}${mv.name} alone fell `, num(F.pct(g.company), "fact"), " at worst, its similar index ", num(F.pct(g.industry), "assumption")];
    out.push(g.gentler === false
      ? note(`The similar index for ${mv.name}`, who, nums, ": here the similar index fell further.")
      : note(`Probably milder than ${mv.name} itself`, who, nums, `. One company can fall further than its industry, so the rows with the move are probably milder than the real thing, never ${possessive(mv.name)} own history.`));
  } else if (mv && ((m.standIn && m.standIn.strength === "weak") || (v && v.weak))) {
    const who = m.standIn ? `${theLabel(m.standIn.label)} stands in for ${mv.name}.` : `A similar index replays ${mv.name}.`;
    out.push(note(`Probably milder than ${mv.name} itself`, `${who} One company can fall further than its industry, so the rows with the move are probably milder than the real thing, never ${possessive(mv.name)} own history.`));
  }
  const miss = m.missing.tickers.length && m.state === "ok" ? ` No similar index for ${m.missing.tickers.join(", ")}: can’t say.` : "";
  out.push(side(m), note("What this is", `Monthly data; industries and indexes stand in for today’s funds.${miss} This already happened; it is not a forecast. Fictional illustration, not a recommendation.`));
  return h("div", { class: "deep-notes" }, out, methods(m, PF), m.source || m.provenance ? h("p", { class: "deep-source", text: [m.source, m.provenance].filter(Boolean).join(" ") }) : null);
}

/* how the stand-ins were built: the Result's own method notes and its Canada check, folded */
function methods(m, PF) {
  const c = m.methods && m.methods.canada, list = [...(m.methods ? m.methods.notes : [])];
  if (c) list.push([`Before ${month(PF, c.to)}, the Canadian stock market comes from ${c.source || "a splice"}`,
    c.check ? `; checked against Fama/French Canada on ${c.check.months} months, correlation ${c.check.corr.toFixed(3)}.` : ".", c.currency ? ` ${c.currency}.` : ""].join(""));
  if (!list.length) return null;
  return h("details", { class: "deep-method" }, h("summary", { text: "How the similar indexes were built" }),
    h("ul", {}, list.map((x) => h("li", { text: plain(x) }))));
}

function cantSay(m) {
  const t = m.missing.items.map((x) => (x.share ? `${x.ticker} (${x.share} of the mix)` : x.ticker));
  const ring = s("svg", { class: "deep-cant-icon", viewBox: "0 0 12 12", ...hide }, ...(document.getElementById("i-pending") ? [s("use", { href: "#i-pending" })]
    : [s("circle", { cx: 6, cy: 6, r: 4.25, fill: "none", stroke: "currentColor", "stroke-width": 1.5, "stroke-dasharray": "2 3", pathLength: 25 })]));
  return h("div", { class: "deep-cant" }, h("p", { class: "deep-cant-word" }, ring, h("span", { text: "Can’t say" })),
    h("p", { class: "deep-cant-why", text: t.length ? `No similar index reaches back for ${t.join(", ")}, so none of the ${m.n} crises could be replayed on ${m.on}.`
      : m.missing.reason || `None of the ${m.n} crises could be replayed on ${m.on}.` }));
}

/* P1 (window.EPI_STRIPES === true; off by default, ruling R5): every stretch as one stripe per start month, no share printed */
function stripes(m, PF, sx) {
  const yrs = sx.years ? `${sx.years}-year` : `${sx.months}-month`, next = sx.years ? `${sx.years} years` : `${sx.months} months`;
  const L = sx.rows.length > 1 && m.move ? sx.rows : sx.rows.slice(0, 1);
  const read = h("p", { class: "deep-sx-read", id: "deep-sx-read", "aria-live": "polite",
    text: "Move along the stripes, or use the arrow keys, to read one start month." });
  const cursor = h("span", { class: "deep-sx-cursor", "aria-hidden": "true", hidden: true });
  const grid = h("div", { class: "deep-sx-grid", tabindex: "0", role: "group", "aria-label": `Every ${yrs} stretch, ${sx.first} to ${sx.last}`,
    "aria-describedby": "deep-sx-read" },
    L.map((row) => h("div", { class: "deep-sx-row" }, h("span", { class: "deep-sx-lbl", text: row.label }),
      s("svg", { class: `deep-sx-bar sx-${row.key}`, viewBox: `0 0 ${sx.n} 1`, preserveAspectRatio: "none", ...hide },
        ...row.runs.map((u) => s("rect", { class: `sx-${u.cls}`, x: u.i, y: 0, width: u.n, height: 1 }))))),
    h("div", { class: "deep-sx-axis", "aria-hidden": "true" }, sx.decades.map((d) => h("span", { class: "deep-sx-tick", vars: { "--x": d.i / sx.n }, text: d.label }))),
    cursor);
  let at = -1;
  const show = (i) => {
    at = Math.max(0, Math.min(sx.n - 1, i));
    cursor.hidden = false; cursor.style.setProperty("--x", String((at + 0.5) / sx.n));
    const parts = L.map((row) => `${row.key === "today" ? "today\u2019s mix" : "with the move"} ${PF.fmt.pct(row.values[at])} at worst, so it ${CLASS[row.cls[at]].say}`);
    read.textContent = `From ${PF.fmt.month(`${sx.starts[at]}-01`)}, the next ${next}: ${parts.join("; ")}.`;
  };
  const strip = () => grid.querySelector(".deep-sx-bar");
  grid.addEventListener("pointermove", (e) => { const b = strip().getBoundingClientRect(); if (e.clientX >= b.left && e.clientX <= b.right) show(Math.floor(((e.clientX - b.left) / b.width) * sx.n)); });
  grid.addEventListener("keydown", (e) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, PageDown: 12, PageUp: -12 }[e.key];
    if (step !== undefined) { e.preventDefault(); show((at < 0 ? 0 : at) + (e.shiftKey ? step * 12 : step)); }
    else if (e.key === "Home" || e.key === "End") { e.preventDefault(); show(e.key === "Home" ? 0 : sx.n - 1); }
  });
  return h("div", { class: "deep-sx" }, h("h3", { class: "deep-h3", text: `Every ${yrs} stretch since ${sx.first}` }),
    h("p", { class: "deep-sx-sub", text: `One stripe per start month, ${sx.first} to ${sx.last}: red when the next ${next} went past your floor, amber when they touched it, dark when they stayed above it.` }),
    grid, read);
}

/* "Every kind that already happened" (window.EPI_KINDS, on unless set false): one row per kind of shock, 2021–26 on the real
   funds and the earlier crises by stand-in, each side the worst fall with its status word (web/lib/status.js, never green) */
function kindsBlock(k) {
  const val = (c) => (c ? [h("span", { class: "deep-val", text: c.text }),
    c.cls ? h("span", { class: "deep-cls", "data-tone": c.cls }, glyph(c.cls), h("span", { text: c.word })) : null] : null);
  const sub = (x, s, label, first) => h("div", { role: "row", class: "deep-krow", "data-first": first ? "yes" : "no", "data-asked": x.asked ? "yes" : "no" },
    h("div", { role: "rowheader", class: "kc-kind" }, h("span", { class: first ? "deep-ttl" : "sr", text: x.label }),
      first && x.asked ? h("span", { class: "deep-asked", text: "The kind you asked about" }) : null),
    h("div", { role: "cell", class: "kc-when" }, mark(s.kind), h("span", { text: label })),
    s.cant ? h("div", { role: "cell", class: "kc-today" }, h("span", { class: "deep-val is-none", text: "Can\u2019t say" }))
      : h("div", { role: "cell", class: "kc-today" }, val(s.today)),
    k.move ? (s.cant ? h("div", { role: "cell", class: "kc-after" }, h("span", { class: "deep-val is-none", text: "Can\u2019t say" }))
      : h("div", { role: "cell", class: "kc-after" }, val(s.after))) : null);
  const rows = k.rows.flatMap((x) => [
    sub(x, x.earlier, x.earlier.when, true)]);
  return h("div", { class: "deep-kinds", "data-move": k.move ? "yes" : "no" },
    h("h3", { class: "deep-h3", id: "deep-q", text: `The worst fall in each kind, against your floor of ${k.floorText}` }),
    h("div", { class: "deep-ktable", role: "table", "aria-labelledby": "deep-q" },
      h("div", { role: "row", class: "deep-krow deep-khead" },
        h("span", { role: "columnheader", class: "kc-kind", text: "Kind of shock" }), h("span", { role: "columnheader", class: "kc-when", text: "When it happened" }),
        h("span", { role: "columnheader", class: "kc-today" }, h("span", { class: "deep-key k-today", "aria-hidden": "true" }), h("span", { text: "Your mix today" })),
        k.move ? h("span", { role: "columnheader", class: "kc-after" }, h("span", { class: "deep-key k-move", "aria-hidden": "true" }), h("span", { text: "With the move" })) : null),
      rows),
    h("p", { class: "deep-knote" }, mark("assumption"), h("span", { text: " Earlier crises replayed monthly by similar indexes: probably milder than the real thing." })));
}

/* a row opens with its chevron, or with a click anywhere on it that is not a link, a button or a text selection */
function wire(root) {
  root.addEventListener("click", (e) => {
    const row = e.target.closest(".deep-row"), own = e.target.closest(".deep-more");
    if (!row || (!own && (e.target.closest("a, button, summary") || !(getSelection() || {}).isCollapsed))) return;
    const btn = own || row.querySelector(".deep-more");
    if (!btn) return;
    const open = btn.getAttribute("aria-expanded") !== "true";
    btn.setAttribute("aria-expanded", String(open));
    const d = document.getElementById(btn.getAttribute("aria-controls"));
    if (d) d.hidden = !open;
    row.classList.toggle("is-open", open);
  });
  return root;
}

/* ruling R22: one "Show the details", closed by default, its state kept while the page lives (and set by store depth) */
let detailsOpen = false;
function setDetails(root, open) {
  detailsOpen = open;
  const b = root && root.querySelector(".deep-toggle"), p = root && root.querySelector(".deep-details");
  if (!b || !p) return;
  b.setAttribute("aria-expanded", String(open)); p.hidden = !open;
  const txt = b.querySelector(".deep-toggle-txt"); if (txt) txt.textContent = open ? "Hide the details" : "Show the details";
}

function build(m, PF) {
  const v = closedView(m.show ? m : null, m.kinds), c = closed(v);
  const details = m.show ? [...c.more, head(m), m.kinds ? kindsBlock(m.kinds) : null, m.state === "ok" ? table(m, PF) : cantSay(m),
    m.state === "ok" && globalThis.EPI_STRIPES === true && m.sx ? stripes(m, PF, m.sx) : null, notes(m, PF)]
    : [...c.more, m.kinds ? kindsBlock(m.kinds) : null];
  const root = h("div", { class: "deep frame", "data-state": m.show ? m.state : "kinds" }, c.simple,
    h("div", { class: "cl-fold deep-fold" }, h("button", { type: "button", class: "cl-more deep-toggle", "aria-expanded": String(detailsOpen), "aria-controls": "deep-details" },
      h("span", { class: "deep-toggle-txt", text: detailsOpen ? "Hide the details" : "Show the details" }),
      s("svg", { class: "cl-chev", viewBox: "0 0 12 12", ...hide }, s("path", { d: "M3 4.5l3 3 3-3", fill: "none", stroke: "currentColor", "stroke-width": 1.5 })))),
    h("div", { class: "deep-details", id: "deep-details", hidden: !detailsOpen }, details));
  root.querySelector(".deep-toggle").addEventListener("click", () => setDetails(root, !detailsOpen));
  return wire(root);
}

/* motion (window.EPI_MOTION, default on): the bars draw from zero, crisis by crisis, once the table is in view. Reduced
   motion or the flag off: the end frame at once. CSS owns the timing (web/css/deep.css); this only arms and fires it. */
const still = () => globalThis.EPI_MOTION === false || !globalThis.matchMedia || globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
let watcher = null;
function arm(root) {
  const t = root.querySelector(".deep-table");
  if (watcher) { watcher.disconnect(); watcher = null; }
  if (!t || still() || typeof IntersectionObserver !== "function") return;
  t.classList.add("is-armed");
  watcher = new IntersectionObserver((seen) => {
    if (!seen.some((e) => e.isIntersecting)) return;
    watcher.disconnect(); watcher = null;
    t.classList.remove("is-armed"); t.classList.add("is-live");
  }, { threshold: 0.2 });
  watcher.observe(t);
}

/* the floor's x in the table, in px (--fx), so an opened row's detail hangs off the same gold rule; once per layout */
let sizer = null;
function measure(root) {
  if (sizer) { sizer.disconnect(); sizer = null; }
  const t = root.querySelector(".deep-table"), g = t && t.querySelector(".deep-hrow .c-gauge");
  if (!t || !g || typeof ResizeObserver !== "function") return;
  const f = Number(getComputedStyle(t).getPropertyValue("--f"));
  let last = "", frame = 0;
  const set = () => { const a = t.getBoundingClientRect(), b = g.getBoundingClientRect();
    const fx = Number.isFinite(f) && b.width > 0 ? `${(b.left - a.left + f * b.width).toFixed(1)}px` : "";
    if (fx && fx !== last) { last = fx; t.style.setProperty("--fx", fx); t.style.setProperty("--gx", `${(b.left - a.left).toFixed(1)}px`); } };
  /* the header's gauge cell never changes size with --fx (the table does, when a row opens): no observer loop */
  sizer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(set); }); sizer.observe(g); set();
}

/* the stylesheet, when the page did not link it (the section stands alone in the dev harness and in the page) */
function ensureCss() {
  if (document.querySelector('link[href$="css/deep.css"]')) return;
  const l = document.createElement("link");
  l.rel = "stylesheet"; l.href = new URL("../css/deep.css", import.meta.url).href;
  document.head.append(l);
}

/* a Result that hides #deep says so once in the console (info, not an error), naming the keys it lacks */
const KEYS = ["deep_history", "deep_validation", "deep_windows"];
let told = null;
function tellHidden(result) {
  if (!result || told === result) return;
  told = result;
  const missing = KEYS.filter((k) => result[k] === null || result[k] === undefined);
  console.info(`[deep] #deep is hidden: this Result (${result.run_id || "no run id"}) has ${missing.length ? `no ${missing.join(", ")}` : "no crisis rows"}.`);
}

export function mount(el, store) {
  ensureCss();
  el.setAttribute("aria-labelledby", "deep-title");
  const render = () => {
    const st = store.get(), PF = globalThis.PF;
    const m = PF && PF.fmt ? deepModel(st.result, PF) : { show: false };       // its own PF.view: never a stale view
    if (m.show && globalThis.EPI_STRIPES === true) m.sx = stripesOf(st.result, PF);
    m.kinds = PF && PF.fmt && globalThis.EPI_KINDS !== false ? kindsOf(st.result, PF) : null;
    el.hidden = !m.show && !m.kinds;
    if (!m.show && !m.kinds) { el.replaceChildren(); if (PF && PF.fmt) tellHidden(st.result); return; }
    el.replaceChildren(build(m, PF));
    arm(el); measure(el);
  };
  store.on("result", render);
  store.on("depth", (d) => setDetails(el, d === "detailed"));          // the page's "detailed" depth opens every section
  if (store.get().depth === "detailed") detailsOpen = true;
  render();
  return { render, open: (on) => setDetails(el, on !== false) };
}
