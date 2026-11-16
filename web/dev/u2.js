/* dev only (lane U2): mounts ONLY the Replay stage on the real store (web/state.js) and the real runs (web/data.js), with
   stand-ins for the globe (U1), the race (U3, coded against INTERFACES.md until web/race.js lands) and the dial (U4).
   ?investor=mateo  ?globe=none (the no-WebGL fallback)  ?motion=0  ?live=1 (POST /api/run on the dev server)  ?race=real */
import { store } from "../state.js";
import { loadRun, runLive } from "../data.js";
import { mount } from "../sections/replay.js";

const qs = new URLSearchParams(location.search);
if (qs.get("motion") === "0") window.EPI_MOTION = false;
if (qs.get("motion") === "1") window.EPI_MOTION = true;
const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, a = {}) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };

/* ---- stand-in race: today's line grey at 45 %, the move magenta, the floor ribbon gold, red hatch under it, cyan ticks ---- */
function raceModel(r, wi) {
  const tp = r.tipping_point, fam = (r.scenario && r.scenario.families || [])[0];
  const shocks = (r.events || []).filter((e) => e.family === fam).map((e) => ({ id: e.event_id, date: e.date }));
  if (tp && tp.paths) {
    const mv = window.PF.moveOf(r), curve = tp.curve;
    let k = 0; curve.forEach((c, i) => { if (Math.abs(c.weight - mv.weight) < Math.abs(curve[k].weight - mv.weight)) k = i; });
    return { dates: tp.paths.dates, today: tp.paths.values[0], after: tp.paths.values[wi ?? k], paths: tp.paths.values, floor: r.limits.floor, shocks };
  }
  const s = r.series, keep = s.dates.map((d, i) => i).filter((i) => i % 5 === 0 || i === s.dates.length - 1);
  return { dates: keep.map((i) => s.dates[i]), today: keep.map((i) => (s.today[i] * r.amount) / 100), after: null, floor: r.limits.floor, shocks };
}
function createRace(el, m) {
  el.classList.add("dev-race");
  const W = Math.max(320, el.clientWidth), H = Math.max(200, el.clientHeight), L = 8, Rr = 96, T = 12, B = 28;
  const t = (d) => Date.parse(d), t0 = t(m.dates[0]), t1 = t(m.dates[m.dates.length - 1]);
  const all = [...m.today, ...(m.after || [])], vmin = Math.min(...all) * 0.92, vmax = Math.max(...all) * 1.04;
  const x = (d) => L + ((t(d) - t0) / (t1 - t0)) * (W - L - Rr), y = (v) => T + (1 - (v - vmin) / (vmax - vmin)) * (H - T - B);
  const line = (vals) => vals.map((v, i) => `${i ? "L" : "M"}${x(m.dates[i]).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const ribbonOf = (vals) => { let hi = -Infinity; return vals.map((v) => (hi = Math.max(hi, v)) * (1 + m.floor)); };
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img", "aria-label": "Stand-in race chart" });
  const vp = (px, py) => { const b = root.getBoundingClientRect(); return { x: b.left + (px * b.width) / W, y: b.top + (py * b.height) / H }; };
  const clip = svg("clipPath", { id: "dev-clip" }), rect = svg("rect", { x: 0, y: 0, width: W, height: H });
  clip.append(rect); root.append(clip);
  const g = svg("g", { "clip-path": "url(#dev-clip)" });
  const main = m.after || m.today, rib = ribbonOf(main);
  const hatch = svg("path", { fill: "rgba(255,106,92,.16)" }), ribbon = svg("path", { fill: "none", stroke: "#D2B48C", "stroke-width": 1 });
  const today = svg("path", { d: line(m.today), fill: "none", stroke: "#C9D7E8", "stroke-opacity": m.after ? .45 : 1, "stroke-width": 1.5 });
  const after = svg("path", { fill: "none", stroke: "#FF5FC8", "stroke-width": 2 });
  const paint = (vals) => {
    const rb = ribbonOf(vals);
    ribbon.setAttribute("d", line(rb));
    after.setAttribute("d", m.after ? line(vals) : "");
    let d = ""; vals.forEach((v, i) => { if (v < rb[i]) d += `M${x(m.dates[i])},${y(rb[i])}V${y(v)}h1.6V${y(rb[i])}Z`; });
    hatch.setAttribute("d", d);
  };
  paint(main);
  g.append(hatch, ribbon, today, after);
  const axis = svg("line", { x1: L, x2: W - Rr, y1: H - B, y2: H - B, stroke: "rgba(255,255,255,.14)" });
  root.append(axis, g);
  for (let yr = +m.dates[0].slice(0, 4) + 1; yr <= +m.dates[m.dates.length - 1].slice(0, 4); yr++) {
    const tx = svg("text", { x: x(`${yr}-01-01`), y: H - 8, "text-anchor": "middle" }); tx.textContent = String(yr); root.append(tx);
  }
  for (const s of m.shocks) root.append(svg("line", { x1: x(s.date), x2: x(s.date), y1: H - B - 6, y2: H - B + 2, stroke: "#9FE6FF", "stroke-width": 1.5 }));
  const endA = svg("text", { class: "end", x: W - Rr + 8, y: y(main[main.length - 1]) + 4, fill: m.after ? "#FF5FC8" : "#C9D7E8" });
  endA.textContent = window.PF.fmt.money(main[main.length - 1]);
  root.append(endA);
  if (m.after) { const e2 = svg("text", { class: "end", x: W - Rr + 8, y: y(m.today[m.today.length - 1]) + 4, fill: "#A9B2BF" }); e2.textContent = window.PF.fmt.money(m.today[m.today.length - 1]); root.append(e2); }
  el.replaceChildren(root);
  return {
    draw(p) { rect.setAttribute("width", String(Math.max(0, Math.min(1, p)) * W)); },
    setWeight(i) { if (m.paths && m.paths[i]) paint(m.paths[i]); },
    xOfDate: (iso) => vp(x(iso), 0).x, yOfValue: (v) => vp(0, y(v)).y,   // viewport px, as U3's
    markers: () => m.shocks.map((s) => ({ kind: "shock", id: s.id, date: s.date, ...vp(x(s.date), H - B) })),
    destroy() { el.replaceChildren(); },
  };
}

/* ---- stand-in globe: the poster disc, fixed under the content; "hero" = big, right of centre; "stage" = the stage's slot ---- */
function createStandInGlobe() {
  const d = document.createElement("div");
  d.className = "dev-globe";
  document.body.prepend(d);
  let layout = "hero";
  const rectOf = () => {
    if (layout === "stage") {
      const s = document.getElementById("replay-globe").getBoundingClientRect(), D = Math.min(s.width, s.height);
      return { x: s.left + (s.width - D) / 2, y: s.top + (s.height - D) / 2, D };
    }
    const D = Math.min(innerWidth * 0.62, innerHeight * 1.02);
    return { x: innerWidth * 0.68 - D / 2, y: innerHeight * 0.5 - D / 2 - scrollY, D };
  };
  const place = (msv) => {
    const r = rectOf();
    d.style.transition = msv ? `transform ${msv}ms cubic-bezier(0.77, 0, 0.175, 1)` : "none";
    d.style.width = d.style.height = "100px";
    d.style.transform = `translate(${r.x}px, ${r.y}px) scale(${r.D / 100})`;
  };
  addEventListener("scroll", () => place(0), { passive: true });
  addEventListener("resize", () => place(0), { passive: true });
  place(0);
  const wait = (msv) => new Promise((res) => setTimeout(res, msv || 0));
  return {
    flyTo: (lat, lon, msv) => wait(msv), focusFamily: () => {}, igniteAll: (o, msv) => wait(msv),
    setLayout(name, msv) { layout = name; place(msv); return wait(msv); },
    project(lat, lon) {                      // the poster is turned to lon0 −18, tilt 26 (PF.globeProject's defaults)
      const r = rectOf(), p = window.PF.globeProject(lat, lon, {}), k = r.D / 2 / 1.0;
      return { x: r.x + r.D / 2 + p.x * k * 0.9, y: r.y + r.D / 2 + p.y * k * 0.9, visible: p.visible };
    },
    dispose() { d.remove(); },
  };
}

/* ---- boot: the store, the run, the stage; the stand-in command bar and dial drive the store as U1 and U4 do ---- */
async function boot() {
  while (!window.PF) await new Promise((r) => setTimeout(r, 20));
  const investor = qs.get("investor") || "robert";
  const live = qs.get("live") === "1";
  store.set({ mode: live ? "live" : "static", investor });
  if (qs.get("globe") !== "none") store.set({ globe: createStandInGlobe() });
  const deps = { data: { runLive } };
  if (qs.get("race") !== "real") deps.race = { raceModel, createRace };
  const api = mount(document.getElementById("replay"), store, deps);
  const box = document.getElementById("dev-q"), row = document.getElementById("dev-investors");
  for (const id of ["robert", "mateo", "amira", "canadian"]) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "chip"; b.textContent = id;
    b.onclick = () => store.set({ investor: id });
    row.append(b);
  }
  const load = async (id) => { const r = await loadRun(id); store.set({ result: r, view: window.PF.view(r), question: r.question || "", weightIndex: null }); box.value = r.question || ""; };
  store.on("investor", (id) => load(id));
  box.addEventListener("input", () => store.set({ question: box.value }));
  document.getElementById("dev-replay").onclick = () => store.set({ question: box.value, replay: Date.now() });
  const w = document.getElementById("dev-w"), wv = document.getElementById("dev-wv");
  w.addEventListener("input", () => { const i = +w.value; store.set({ weightIndex: i }); const race = store.get().race; if (race) race.setWeight(i); wv.textContent = i + " %"; });
  document.getElementById("dev-w0").onclick = () => { store.set({ weightIndex: null }); wv.textContent = "asked"; };
  await load(investor);
  window.__u2 = { store, api, ready: true };
}
boot().catch((e) => console.error("[dev u2] boot failed", e));
