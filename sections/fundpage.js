/* EPICENTRE Replay, lane funds: the fund drawer. A right-side dialog, opened from the holdings card (lane hold's hook in
   web/sections/hold.js: a fund row, or "What's inside the funds"): one fund as a fund page shows it, or what the investor ends
   up owning. DOM by createElement / textContent only (R16); words and numbers from web/lib/fundpage.js (pure, node-tested);
   every number is a Result key (result.funds; result.funds_private in the live app only, red gate 8).
   openFunds(store, what, opener)   what = a fund's ticker or "owning"; focus goes back to `opener` when the drawer closes.
   Throws when the run has no fund pages (result.funds absent): the caller then opens its own inline panel. */
import { drawerModel } from "../lib/fundpage.js";
import { sharebar, sharebarModel } from "../lib/sharebar.js";

const PF = () => globalThis.PF;
function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(3)) if (c !== null && c !== undefined && c !== false && c !== "") n.append(c);
  return n;
}
function ensureCss() {                       // the integrated page links both (lane hold's hook needs fundpage.css); a harness gets them once
  for (const f of ["fundpage.css", "sharebar.css"])
    if (!document.querySelector(`link[href$="css/${f}"]`)) document.head.append(h("link", { rel: "stylesheet", href: new URL(`../css/${f}`, import.meta.url).href }));
}
/* one share bar (web/lib/sharebar.js): today and with the move one above the other */
const bar = (rows, label, family, unit, empty) => sharebar(sharebarModel(rows, { top: 5 }), { fmt: PF().fmt, label, family, unit, empty });
const ms = (name) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(`--${name}`)) || 0;   // a motion token, in ms
const still = () => globalThis.EPI_MOTION === false || document.documentElement.classList.contains("motion-off") ||
  (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);

let D = null;                                // the one drawer of the page
function build(store) {
  ensureCss();
  const root = h("div", { id: "fundpage", class: "fp-root", hidden: true });
  const scrim = h("div", { class: "fp-scrim", "aria-hidden": "true" });
  const close = h("button", { type: "button", class: "fp-x", "aria-label": "Close" }, h("span", { "aria-hidden": "true", text: "×" }));
  const sides = h("div", { class: "fp-sides", role: "group", "aria-label": "Whose mix" });
  const tabs = h("nav", { class: "fp-tabs", "aria-label": "The funds" });
  const scroll = h("div", { class: "fp-scroll" });
  const panel = h("div", { class: "fp-panel", role: "dialog", "aria-modal": "true", "aria-labelledby": "fp-title", tabindex: "-1" },
    h("div", { class: "fp-top" }, h("p", { class: "fp-top-t", text: "Inside the funds" }), sides, close), tabs, scroll);
  root.append(scrim, panel);
  document.body.append(root);
  const d = { store, root, panel, scroll, tabs, sides, what: "owning", side: null, opener: null, open: false, t: 0 };
  const shut = () => hide(d);
  close.addEventListener("click", shut);
  scrim.addEventListener("click", shut);
  scrim.addEventListener("wheel", (ev) => ev.preventDefault(), { passive: false });     // the page behind stays where it was
  scrim.addEventListener("touchmove", (ev) => ev.preventDefault(), { passive: false });
  root.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); shut(); return; }
    if (ev.key !== "Tab") return;
    const f = [...panel.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && (document.activeElement === first || document.activeElement === panel)) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });
  tabs.addEventListener("keydown", (ev) => {      // arrows move along the tabs
    if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
    const b = [...tabs.querySelectorAll("button")], i = b.indexOf(document.activeElement);
    if (i < 0) return;
    ev.preventDefault();
    b[(i + (ev.key === "ArrowRight" ? 1 : b.length - 1)) % b.length].focus();
  });
  store.on("result", () => { if (d.open) render(d, false); });
  store.on("investor", () => { if (d.open) hide(d); });
  return d;
}

export function openFunds(store, what, opener) {
  const r = store.get().result, P = PF();
  if (!drawerModel(r, P, what, null)) throw new Error("this run carries no fund pages");
  if (!D || !D.root.isConnected) D = build(store);
  D.store = store; D.what = what || "owning"; D.side = null; D.opener = opener || document.activeElement;
  render(D, true);
  show(D);
}

function show(d) {
  clearTimeout(d.t);
  d.root.dataset.motion = still() ? "off" : "on";
  d.root.hidden = false;
  d.open = true;
  document.documentElement.classList.add("fp-lock");
  void d.root.offsetWidth;
  requestAnimationFrame(() => { d.root.classList.add("is-open"); d.panel.focus({ preventScroll: true }); });
}
function hide(d) {
  if (!d.open) return;
  d.open = false;
  d.root.classList.remove("is-open");
  document.documentElement.classList.remove("fp-lock");
  const done = () => { if (!d.open) d.root.hidden = true; };
  if (d.root.dataset.motion === "on") d.t = setTimeout(done, ms("dur-panel-exit") + 20); else done();
  const back = d.opener;
  if (back && back.isConnected && typeof back.focus === "function") back.focus({ preventScroll: true });
}

/* ---- the drawer's content ---- */
const SVG = "http://www.w3.org/2000/svg";
function icon(id) {                          // a status icon from the page's sprite (index.html's symbols); status = icon + word
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "fp-i"); s.setAttribute("aria-hidden", "true"); s.setAttribute("focusable", "false");
  const u = document.createElementNS(SVG, "use");
  u.setAttribute("href", `#${id}`);
  s.append(u);
  return s;
}
function render(d, fresh) {
  const r = d.store.get().result, P = PF(), m = drawerModel(r, P, d.what, d.side);
  if (!m) { hide(d); return; }
  d.what = m.view; d.side = m.side;
  d.sides.replaceChildren(...(m.sides.length > 1 ? m.sides.map((s) => {
    const b = h("button", { type: "button", class: "fp-side", "aria-pressed": String(s.id === m.side), text: s.label });
    b.addEventListener("click", () => {
      if (d.side === s.id) return;
      d.side = s.id; render(d, false);
      const again = [...d.sides.children].find((x) => x.textContent === s.label);      // the redrawn button keeps the focus
      if (again) again.focus({ preventScroll: true });
    });
    return b;
  }) : []));
  d.sides.hidden = m.sides.length < 2;
  d.tabs.replaceChildren(...m.tabs.map((t) => {
    const on = t.id === m.view;
    const b = h("button", { type: "button", class: "fp-tab", "aria-current": on ? "page" : null, "data-id": t.id },
      h("span", { class: "fp-tab-t", text: t.label }), t.sub ? h("span", { class: "fp-tab-s", text: t.sub }) : null);
    b.addEventListener("click", () => { if (d.what !== t.id) go(t.id); });
    return b;
  }));
  function go(tk) {                          // a tab (or a fund row) opens that view; the redrawn tab keeps the focus
    d.what = tk; d.more = false; render(d, true);
    const t = [...d.tabs.querySelectorAll(".fp-tab")].find((x) => x.dataset.id === tk);
    if (t) t.focus({ preventScroll: true });
  }
  const body = m.page ? fundView(m.page, d) : ownView(m.owning, d, go);
  d.scroll.replaceChildren(body);
  if (fresh) d.scroll.scrollTop = 0;
  const cur = d.tabs.querySelector('[aria-current="page"]');
  if (cur && typeof cur.scrollIntoView === "function") cur.scrollIntoView({ block: "nearest", inline: "nearest" });
  grow(d);
}

/* the bars draw left to right when a view opens (clip-path only; reduced motion: drawn at once) */
function grow(d) {
  const bars = d.scroll.querySelectorAll(".sb-bar");
  if (still() || d.root.dataset.motion !== "on") { bars.forEach((b) => { b.style.clipPath = ""; }); return; }
  bars.forEach((b) => { b.style.transition = "none"; b.style.clipPath = "inset(0 100% 0 0)"; });
  void d.scroll.offsetWidth;
  requestAnimationFrame(() => requestAnimationFrame(() => bars.forEach((b) => { b.style.transition = ""; b.style.clipPath = "inset(0 0 0 0)"; })));
}

function chevron() {
  const c = document.createElementNS(SVG, "svg");
  c.setAttribute("class", "cl-chev"); c.setAttribute("viewBox", "0 0 12 12"); c.setAttribute("aria-hidden", "true"); c.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  for (const [k, v] of Object.entries({ d: "M2.5 4.5 6 8l3.5-3.5", fill: "none", stroke: "currentColor", "stroke-width": "1.6", "stroke-linecap": "round", "stroke-linejoin": "round" })) p.setAttribute(k, v);
  c.append(p);
  return c;
}
const part = (title, id, ...kids) => h("section", { class: "fp-part", "aria-labelledby": id }, h("h3", { class: "fp-h", id, text: title }), ...kids);
/* details behind one button (the coordinator: one screen per fund, at most six big numbers) */
function moreButton(d, label, panel) {
  const id = `fp-more-${Math.random().toString(36).slice(2, 8)}`;
  panel.id = id;
  panel.hidden = !d.more;
  const b = h("button", { type: "button", class: "cl-more fp-more", "aria-expanded": String(!!d.more), "aria-controls": id },
    h("span", { class: "cl-more-word", text: d.more ? "Hide the list" : label }), chevron());
  b.addEventListener("click", () => {
    d.more = !d.more;
    panel.hidden = !d.more;
    b.setAttribute("aria-expanded", String(d.more));
    b.firstChild.textContent = d.more ? "Hide the list" : label;
    if (d.more) grow({ ...d, scroll: panel });
  });
  return b;
}

function stat(s) {
  return h("div", { class: `fp-stat${s.side ? " is-side" : ""}${s.date ? " is-date" : ""}` },
    h("dt", { text: s.k }), h("dd", {}, h("span", { class: "fp-stat-v", text: s.v }), s.sub ? h("span", { class: "fp-stat-s", text: s.sub }) : null));
}
function fundView(p, d) {
  const kids = [
    h("header", { class: "fp-head" },
      h("p", { class: "fp-tk", text: p.ticker }),
      h("h2", { class: "fp-name", id: "fp-title", text: p.name }),
      h("p", { class: "fp-about", text: p.about })),
    p.concentration ? h("p", { class: `fp-conc${p.concentrated ? " is-conc" : ""}`, text: p.concentration }) : null,
    h("dl", { class: "fp-stats" }, p.stats.map(stat)),
    p.datedNote ? h("p", { class: "fp-dated", text: p.datedNote }) : null,
    p.note ? h("p", { class: "fp-note", text: p.note }) : null,
  ];
  if (p.top) {
    const table = h("table", { class: "fp-table" },
      h("caption", { class: "sr", text: `${p.topTitle}, ${p.sideWord.toLowerCase()}` }),
      h("thead", {}, h("tr", {}, h("th", { scope: "col", class: "fp-c-rank" }, h("span", { class: "sr", text: "Rank" })),
        h("th", { scope: "col", class: "fp-c-name", text: "Company" }), h("th", { scope: "col", class: "fp-c-num", text: `Of ${p.ticker}` }),
        h("th", { scope: "col", class: "fp-c-num", text: p.side === "after" ? "Yours, with the move" : "Yours today" }))),
      h("tbody", {}, p.top.map((x) => h("tr", {},
        h("td", { class: "fp-c-rank fig", text: String(x.rank) }),
        h("th", { scope: "row", class: "fp-c-name" }, h("span", { class: "fp-co", text: x.name }), x.ticker ? h("span", { class: "fp-co-tk", text: x.ticker }) : null),
        h("td", { class: "fp-c-num fig", text: x.shareText }),
        h("td", { class: "fp-c-num fig fp-yours", text: p.inMix ? x.yoursText : "–" })))));
    kids.push(part(p.topTitle, "fp-h-top", table, p.topNote ? h("p", { class: "fp-small", text: p.topNote }) : null));
  } else if (p.licence) {
    kids.push(part(p.topTitle, "fp-h-top", h("p", { class: "fp-licence" }, h("span", { text: `${p.licence.line} ` }),
      p.licence.href ? h("a", { class: "fp-link", href: p.licence.href, target: "_blank", rel: "noopener noreferrer", text: p.licence.link }) : null)));
  }
  /* the fund's own industries and countries, always in view (the cold first-time user: "keep the bars clearly visible") */
  if (p.split.sectors.length) kids.push(part("By industry", "fp-h-sec", bar(p.split.sectors, `${p.ticker} by industry`, "industry", "of the fund")));
  if (p.split.countries.length) kids.push(part("By country", "fp-h-cty", bar(p.split.countries, `${p.ticker} by country`, "country", "of the fund")));
  kids.push(h("p", { class: "fp-foot" }, h("span", { text: `${p.exposure} ` }),
    p.url && !p.licence ? h("a", { class: "fp-link", href: p.url, target: "_blank", rel: "noopener noreferrer", text: "The issuer’s page" }) : null));
  return h("div", { class: "fp-view", "data-view": p.ticker }, kids);
}

function row(x, extra) {
  return h("li", { class: `fp-row${extra ? ` ${extra}` : ""}` },
    h("span", { class: "fp-row-n" }, h("span", { class: "fp-co", text: x.name }), x.how ? h("span", { class: "fp-row-how", text: x.how }) : null),
    h("span", { class: "fp-row-v fig", text: x.shareText || "" }), h("span", { class: "fp-row-d fig", text: x.dollarsText || "" }));
}
function ownView(o, d, go) {
  if (!o) return h("div", { class: "fp-view" }, h("h2", { class: "fp-name", id: "fp-title", text: "What you own" }));
  const kids = [h("header", { class: "fp-head" }, h("p", { class: "fp-tk", text: o.amountText }), h("h2", { class: "fp-name", id: "fp-title", text: o.title }),
    h("p", { class: "fp-about", text: o.fiction }))];
  if (o.limits.length) kids.push(part("The biggest company and industry, against your limits", "fp-h-lim",
    h("ul", { class: "fp-limits" }, o.limits.map((l) => h("li", { class: "fp-limit", "data-tone": l.status ? l.status.tone : null },
      h("span", { class: "fp-limit-st" }, l.status ? icon(l.status.icon) : null, h("span", { text: l.status ? l.status.word : "" })),
      h("span", { class: "fp-limit-n", text: l.name }), h("span", { class: "fp-limit-v fig", text: l.valueText }),
      h("span", { class: "fp-limit-l", text: l.line }))))));
  const shown = o.companies.slice(0, 6), later = o.companies.slice(6);
  const B = o.breakdown, has = (rows) => rows.some((x) => x.items.length);
  kids.push(part(o.companiesTitle, "fp-h-co",
    has(B.companies) ? bar(B.companies, o.companiesTitle, "company", "of your money", o.live ? "None" : "None directly") : null,
    o.licence ? h("p", { class: "fp-licence", text: o.licence }) : null,
    o.companiesNote ? h("p", { class: "fp-small", text: o.companiesNote }) : null));
  if (has(B.sectors)) kids.push(part("By industry", "fp-h-osec", bar(B.sectors, "By industry", "industry", "of your money"), h("p", { class: "fp-small", text: o.sectorNote })));
  if (has(B.countries)) kids.push(part("By country", "fp-h-octy", bar(B.countries, "By country", "country", "of your money")));
  const fundRows = h("ul", { class: "fp-rows" }, o.funds.map((f) => {
    const b = h("button", { type: "button", class: "fp-row fp-row-btn" },
      h("span", { class: "fp-row-n" }, h("span", { class: "fp-co", text: f.ticker }), h("span", { class: "fp-row-how", text: f.label })),
      h("span", { class: "fp-row-v fig", text: f.shareText }), h("span", { class: "fp-row-d fig", text: f.dollarsText }));
    b.addEventListener("click", () => go(f.ticker));
    return h("li", {}, b);
  }));
  if (o.funds.length) kids.push(part("By fund", "fp-h-funds", has(B.funds) ? bar(B.funds, "By fund", "fund", "of your money") : null, fundRows));
  if (o.companies.length > 1 || o.rest || (o.live && o.unlisted)) {        // the full list, one button away
    const panel = h("div", { class: "fp-detail" },
      part(`${o.companiesTitle}, ${o.sideWord.toLowerCase()}`, "fp-h-colist", h("ul", { class: "fp-rows" }, [...shown, ...later].map((x) => row(x)),
        o.rest ? row({ name: `${o.rest.count} more companies`, how: "In the funds’ listed positions", ...o.rest }, "is-more") : null,
        o.unlisted ? row({ name: "The rest of your stock funds", how: "Positions the issuers’ files do not list", ...o.unlisted }, "is-more") : null)));
    kids.push(moreButton(d, "Show every company", panel), panel);
  }
  return h("div", { class: "fp-view", "data-view": "owning" }, kids);
}
