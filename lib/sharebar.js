/* EPICENTRE Replay, lane funds: ONE share bar for every breakdown of the money (the lead 16:40, /tmp/epi_lanes/LIMITS_MODEL.md
   "BREAKDOWN BARS": "my percentage in each industry and each stock in a little coloured horizontal bar, biggest percentage biggest
   proportionally, hover with the mouse"). Used by the fund drawer (web/sections/fundpage.js); any lane may use it.
   sharebarModel(rows, opts)  pure: rows = [{ id, label, items: [{ key, name, share, dollars?, move? }] }] (share = a fraction
                              of the whole bar, e.g. of the money); one key order for every row (the largest first, by its
                              largest share on any row), so a key keeps its place and its tone from "Today" to "With the move";
                              the `top` largest keys (5) are segments and the legend, the rest one "Other (n)" segment.
   sharebar(model, opts)      the DOM: one thin bar per row (widths exactly the shares; what no key covers stays an empty track),
                              the legend under the bars, and one tooltip (the name, the % of the money, the $) on hover, tap or
                              keyboard (the bar is one tab stop; the arrows walk its segments). textContent only (R16).
   opts: { top = 5, fmt (PF.fmt: pct, money), label (the group's accessible name), family ("industry" | "country" | "company" |
   "fund": the hue), unit ("of your money" | "of the fund"), empty (the words for a row with nothing, "None") }. Tests: tests/web_funds_test.mjs. CSS: web/css/sharebar.css. */

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
export const OTHER = "__other__";

export function sharebarModel(rows, { top = 5 } = {}) {
  const clean = (Array.isArray(rows) ? rows : []).map((r) => ({ id: str(r && r.id) || "row", label: str(r && r.label) || "",
    items: (Array.isArray(r && r.items) ? r.items : []).filter((x) => x && str(x.key) && isNum(x.share) && x.share > 0) }));
  const best = new Map(), names = new Map(), moves = new Set();
  for (const r of clean) for (const x of r.items) {
    if (x.other) continue;                       // a group that stands for n names (e.g. "15 more companies") is always Other
    best.set(x.key, Math.max(best.get(x.key) || 0, x.share));
    if (!names.has(x.key)) names.set(x.key, str(x.name) || x.key);
    if (x.move) moves.add(x.key);
  }
  const order = [...best.keys()].sort((a, b) => best.get(b) - best.get(a) || (a < b ? -1 : 1));
  const keys = order.slice(0, top), rest = order.slice(top);
  const tone = Object.fromEntries(keys.map((k, i) => [k, i]));
  const out = clean.map((r) => {
    const by = new Map(r.items.map((x) => [x.key, x]));
    const segs = keys.filter((k) => by.has(k)).map((k) => ({ key: k, name: names.get(k), share: by.get(k).share,
      dollars: isNum(by.get(k).dollars) ? by.get(k).dollars : null, tone: tone[k], move: moves.has(k), other: false }));
    const others = r.items.filter((x) => x.other || !keys.includes(x.key));
    if (others.length) {
      const dollars = others.every((x) => isNum(x.dollars)) ? others.reduce((a, x) => a + x.dollars, 0) : null;
      const count = others.reduce((a, x) => a + (x.other && isNum(x.count) ? x.count : 1), 0);
      segs.push({ key: OTHER, name: `Other (${count})`, share: others.reduce((a, x) => a + x.share, 0), dollars, tone: "other",
        move: false, other: true, count });
    }
    segs.sort((a, b) => (a.other - b.other) || b.share - a.share);           // largest first; Other always last
    let x = 0;
    for (const s of segs) { s.x0 = x; x += s.share; }
    return { id: r.id, label: r.label, segs, covered: Math.min(1, x) };
  });
  const grouped = out.some((r) => r.segs.some((g) => g.other)), most = Math.max(0, ...out.map((r) => (r.segs.find((g) => g.other) || {}).count || 0));
  const legend = [...keys.map((k) => ({ key: k, name: names.get(k), tone: tone[k], move: moves.has(k),
    values: out.map((r) => { const s = r.segs.find((g) => g.key === k); return s ? { share: s.share, dollars: s.dollars } : null; }) })),
    ...(grouped ? [{ key: OTHER, name: `Other (${Math.max(most, rest.length)})`, tone: "other", move: false,
      values: out.map((r) => { const s = r.segs.find((g) => g.other); return s ? { share: s.share, dollars: s.dollars } : null; }) }] : [])];
  return { rows: out, legend, keys, more: rest.length };
}

/* the tooltip's words for one segment: "Information Technology: 42.6 % of your money, $255,568" */
export function segWords(seg, fmt, unit = "of your money") {
  if (!seg) return "";
  const pct = fmt && typeof fmt.pct === "function" ? fmt.pct(seg.share) : "";
  const money = isNum(seg.dollars) && fmt && typeof fmt.money === "function" ? `, ${fmt.money(seg.dollars)}` : "";
  return `${seg.name}: ${pct} ${unit}${money}`;
}

/* ---- the DOM (browser only; nothing runs at import) ---- */
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
export function sharebar(model, { fmt, label = "", family = "industry", unit = "of your money", empty = "None" } = {}) {
  const root = el("figure", "sb");
  root.dataset.family = family;
  root.setAttribute("role", "group");
  if (label) root.setAttribute("aria-label", label);
  const tip = el("p", "sb-tip");
  tip.hidden = true;
  tip.setAttribute("aria-hidden", "true");
  const two = model.rows.length > 1;
  const pct = (x) => (fmt && typeof fmt.pct === "function" ? fmt.pct(x) : "");
  const bars = model.rows.map((r) => {
    const bar = el("span", "sb-bar");
    bar.tabIndex = 0;
    bar.setAttribute("role", "img");
    bar.setAttribute("aria-label", `${r.label ? `${r.label}: ` : ""}${r.segs.map((s) => segWords(s, fmt, unit)).join("; ")}.`);
    r.segs.forEach((s, i) => {
      const seg = el("span", "sb-seg");
      seg.dataset.tone = s.move ? "move" : String(s.tone);
      seg.dataset.i = String(i);
      seg.style.left = `${(s.x0 * 100).toFixed(3)}%`;
      seg.style.width = `${(s.share * 100).toFixed(3)}%`;
      bar.append(seg);
    });
    let at = -1;
    const show = (i, anchor) => {
      const s = r.segs[i];
      if (!s) { hide(); return; }
      at = i;
      bar.querySelectorAll(".sb-seg").forEach((g, j) => g.classList.toggle("is-on", j === i));
      tip.textContent = segWords(s, fmt, unit);
      tip.hidden = false;
      const box = root.getBoundingClientRect(), b = bar.getBoundingClientRect(), seg = bar.children[i].getBoundingClientRect();
      const mid = (anchor === undefined ? seg.left + seg.width / 2 : anchor) - box.left;
      tip.style.top = `${b.bottom - box.top + 6}px`;
      tip.style.left = `${Math.max(0, Math.min(box.width - tip.offsetWidth, mid - tip.offsetWidth / 2))}px`;
    };
    const hide = () => { at = -1; tip.hidden = true; bar.querySelectorAll(".sb-seg.is-on").forEach((g) => g.classList.remove("is-on")); };
    const pick = (ev) => {
      const t = ev.target.closest && ev.target.closest(".sb-seg");
      if (t && bar.contains(t)) show(Number(t.dataset.i), ev.clientX);
    };
    bar.addEventListener("pointermove", (ev) => { if (ev.pointerType === "mouse") pick(ev); });
    bar.addEventListener("pointerleave", (ev) => { if (ev.pointerType === "mouse" && document.activeElement !== bar) hide(); });
    bar.addEventListener("pointerdown", (ev) => { if (ev.pointerType !== "mouse") pick(ev); });
    bar.addEventListener("focus", () => show(at >= 0 ? at : 0));
    bar.addEventListener("blur", hide);
    bar.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        ev.preventDefault();
        const n = r.segs.length;
        show(((at < 0 ? 0 : at) + (ev.key === "ArrowRight" ? 1 : n - 1)) % n);
      } else if (ev.key === "Escape" && !tip.hidden) { ev.stopPropagation(); hide(); }
    });
    const row = el("div", "sb-row");
    if (two || r.label) row.append(el("span", "sb-row-l", r.label));
    row.append(r.segs.length ? bar : el("span", "sb-none", empty));        // an empty row says so instead of an empty track
    return row;
  });
  const legend = el("ul", "sb-legend");
  legend.dataset.cols = String(model.rows.length);
  if (two) {
    const head = el("li", "sb-li sb-li-head");
    head.setAttribute("aria-hidden", "true");
    head.append(el("span", "sb-ln"), ...model.rows.map((r) => el("span", "sb-lv", r.label)));
    legend.append(head);
  }
  for (const g of model.legend) {
    const li = el("li", "sb-li");
    const sw = el("span", "sb-sw");
    sw.dataset.tone = g.move ? "move" : String(g.tone);
    sw.setAttribute("aria-hidden", "true");
    const name = el("span", "sb-ln");
    name.append(sw, document.createTextNode(g.name));
    li.append(name, ...g.values.map((v, i) => {
      const c = el("span", "sb-lv fig", v ? pct(v.share) : "–");
      if (two) { const s = el("span", "sr", ` ${model.rows[i].label}`); c.prepend(s); }
      return c;
    }));
    legend.append(li);
  }
  root.append(el("div", "sb-rows"), legend, tip);
  root.firstChild.append(...bars);
  return root;
}
