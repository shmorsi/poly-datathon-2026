/* EPICENTRE Replay, lane U7: #footer (design doc §2 item 9; R3, R4, R8, R13). The limits of the replay (dated from the
   Result), the data sources with their licences, the code's address, a scannable code to the public static demo (one
   constant: window.EPI_PUBLIC_URL, else the GitHub Pages demo; never a live endpoint, R8), the thesis line and the
   disclaimer. The code is drawn by the vendored qrcode-generator 1.4.4 (web/vendor/qr/qrcode.js, MIT, Kazuhiko Arase),
   loaded once as a classic script, as one SVG path. DOM from createElement/textContent (R16). */
import { marks } from "./clarity.js";                       // red gate 4: the marks’ legend beside the marks
import * as H from "../lib/how.js";

const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs, ...kids) {
  const svg = tag.startsWith("svg:");
  const el = svg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const icon = (id, cls) => h("svg:svg", { class: cls || "icon", "aria-hidden": "true", focusable: "false" }, h("svg:use", { href: `#${id}` }));
const MARK = { fact: "m-fact", assumption: "m-assumption", fiction: "m-fiction" };
/* a source opens beside the page, never in place of it */
const out = (url, text, title) => h("a", { href: url, target: "_blank", rel: "noopener noreferrer", title: title || url, text });

/* audit item 7: every shock on record and every earlier crisis with its own source, folded by default (one tap opens it) */
function recordOf(r) {
  const shocks = H.shocksRecord(r), crises = H.crisesRecord(r), blocks = [];
  const fold = (cls, title, note, mark, table) => h("details", { class: `ft-fold ${cls}` },
    h("summary", { class: "ft-fold-sum" }, mark ? icon(mark, "kind ft-fold-mark") : null, h("span", { class: "ft-fold-t", text: title }),
      h("svg:svg", { class: "ft-fold-chev", viewBox: "0 0 16 16", "aria-hidden": "true", focusable: "false" },
        h("svg:path", { d: "M4 6l4 4 4-4", fill: "none", stroke: "currentColor", "stroke-width": "1.5", "stroke-linecap": "round", "stroke-linejoin": "round" }))),
    note ? h("p", { class: "ft-fold-note", text: note }) : null, h("div", { class: "ft-rec-wrap" }, table));   // a wide table scrolls inside its fold on a phone
  if (shocks) blocks.push(fold("ft-fold-shocks", `The ${shocks.length} shocks on record, each with its source`,
    "Team-written summaries of public announcements, dated by the dating rule. This already happened; it is not a forecast.", null,
    h("table", { class: "ft-rec" },
      h("caption", { class: "sr", text: "Every shock on record with its date, place, kind and source" }),
      h("thead", {}, h("tr", {}, ...["Date", "Shock", "Place", "Kind", "Source"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, shocks.map((x) => h("tr", {},
        h("td", { class: "ft-rec-date", text: x.dateText || x.date }), h("th", { scope: "row", class: "ft-rec-title", text: x.title }),
        h("td", { class: "ft-rec-place", text: x.place || "" }), h("td", { class: "ft-rec-kind", text: x.family || "" }),
        h("td", { class: "ft-rec-src" }, x.url ? out(x.url, x.host, `${x.title}: ${x.url}`) : "")))))));
  if (crises) blocks.push(fold("ft-fold-crises", `The ${crises.length} earlier crises replayed by similar indexes, each with its source`,
    "Replayed month by month with similar indexes in place of today" + "\u2019" + "s funds: an assumption, never part of a verdict.", "m-assumption",
    h("table", { class: "ft-rec" },
      h("caption", { class: "sr", text: "Every earlier crisis with its years, place and source" }),
      h("thead", {}, h("tr", {}, ...["Years", "Crisis", "Place", "Source"].map((t) => h("th", { scope: "col", text: t })))),
      h("tbody", {}, crises.map((x) => h("tr", {},
        h("td", { class: "ft-rec-date", text: x.years || "" }), h("th", { scope: "row", class: "ft-rec-title", text: x.title }),
        h("td", { class: "ft-rec-place", text: x.place || "" }),
        h("td", { class: "ft-rec-src" }, x.url ? out(x.url, x.sourceTitle || x.host, x.url) : "")))))));
  return blocks;
}

/* the encoder, once: a classic script next to this module's folder (it defines window.qrcode) */
let qrPromise = null;
function loadQr() {
  if (typeof window.qrcode === "function") return Promise.resolve(window.qrcode);
  if (!qrPromise) {
    qrPromise = new Promise((resolve) => {
      const s = document.createElement("script");
      s.src = new URL("../vendor/qr/qrcode.js", import.meta.url).href;
      s.async = true;
      s.onload = () => resolve(typeof window.qrcode === "function" ? window.qrcode : null);
      s.onerror = () => resolve(null);
      document.head.append(s);
    });
  }
  return qrPromise;
}

const QUIET = 4;                                  // the standard quiet zone, in modules
function qrSvg(make, url) {
  const q = make(0, "M");
  q.addData(url);
  q.make();
  const size = q.getModuleCount(), all = size + 2 * QUIET;
  const px = all * 4;                             // four CSS pixels a module: every module lands on whole pixels
  return h("svg:svg", { class: "ft-qr-svg", viewBox: `0 0 ${all} ${all}`, width: String(px), height: String(px), role: "img", "aria-label": `A scannable code that opens ${H.bareUrl(url)}`,
    "shape-rendering": "crispEdges", "data-modules": String(size) },
    h("svg:rect", { width: String(all), height: String(all), class: "ft-qr-bg" }),
    h("svg:path", { d: H.qrPath((r, c) => q.isDark(r, c), size, QUIET), class: "ft-qr-ink" }));
}

export function mount(el, store) {
  el.classList.add("ft");
  const url = H.publicUrl(window.EPI_PUBLIC_URL);
  const limits = h("ul", { class: "ft-limits" });
  const sources = h("ul", { class: "ft-sources" });
  const qr = h("div", { class: "ft-qr", "aria-hidden": "false" });
  const record = h("div", { class: "ft-record" });
  el.replaceChildren(h("div", { class: "frame ft-frame" },
    h("p", { class: "ft-thesis", text: "Ending higher does not mean your limits held." }),          // R38
    h("div", { class: "ft-grid" },
      h("section", { class: "ft-col ft-col-limits", "aria-labelledby": "ft-limits-t" },
        h("h2", { class: "ft-h", id: "ft-limits-t", text: "What this replay is, and is not" }), limits, marks()),
      h("section", { class: "ft-col ft-col-sources", "aria-labelledby": "ft-sources-t" },
        h("h2", { class: "ft-h", id: "ft-sources-t", text: "Data and licences" }), sources),
      h("section", { class: "ft-col ft-col-open", "aria-labelledby": "ft-open-t" },
        h("h2", { class: "ft-h", id: "ft-open-t", text: "Open it yourself" }),
        qr,
        h("p", { class: "ft-scan", text: "Scan to open the saved demo on a phone." }),
        h("p", { class: "ft-url" }, h("a", { href: url, text: H.bareUrl(url) })),
        h("p", { class: "ft-code" }, h("span", { class: "ft-code-label", text: "The code" }), h("a", { href: H.REPO_URL, rel: "noopener noreferrer", text: H.bareUrl(H.REPO_URL) })))),
    record,
    h("div", { class: "ft-base" },
      h("p", { class: "ft-word", text: "EPICENTRE" }),
      h("p", { class: "ft-disclaimer", text: "Educational simulation. This is not financial advice." }))));

  const draw = (r) => {
    limits.replaceChildren(...H.limitsOf(r).map((x) => h("li", { class: `ft-limit${x.lead ? " is-lead" : ""}` },
      icon(MARK[x.kind] || "m-fact", "kind ft-kind"),
      h("span", {}, x.text, x.link ? [" ", h("a", { class: "ft-limit-link", href: x.link.href, text: x.link.text })] : null))));
    sources.replaceChildren(...H.sourcesOf(r).map((s) => h("li", { class: "ft-source" },
      h("p", { class: "ft-src-name" }, h("strong", { text: s.name })),
      s.via ? h("p", { class: "ft-src-via", text: s.via.charAt(0).toUpperCase() + s.via.slice(1) }) : null,
      h("p", { class: "ft-src-use", text: `${s.use} ${s.licence}` }),
      s.links ? h("ul", { class: "ft-src-links", "aria-label": `${s.name}: the documents` },
        s.links.map((l) => h("li", {}, out(l.url, l.label)))) : null)));
    record.replaceChildren(...recordOf(r));
  };
  store.on("result", draw);
  draw(store.get().result);

  /* lane clarity (R22): the folds stay folds; the page's depth switch (store key depth, lane u0) opens or closes them all, and
     a reader's own tap still works */
  const depth = (d) => { for (const f of el.querySelectorAll("details.ft-fold")) f.open = d === "detailed"; };
  store.on("depth", depth);
  store.on("result", () => { if ((store.get() || {}).depth === "detailed") depth("detailed"); });
  if ((store.get() || {}).depth === "detailed") depth("detailed");

  /* the encoder after first paint (idle, or the footer near the viewport); its box keeps its place meanwhile */
  H.whenNear(el, () => loadQr().then((make) => {
    if (!make) { qr.hidden = true; return; }
    try { qr.replaceChildren(qrSvg(make, url)); } catch (e) { qr.hidden = true; console.warn("[footer] the scannable code could not be drawn"); }
  }));
}
