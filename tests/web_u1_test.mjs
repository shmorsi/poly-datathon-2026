/* Lane U1 (globe + hero) pure helpers: web/lib/u1.js. Run: node tests/web_u1_test.mjs (also run by tests/test_web_lib.py).
   Fixtures are written here (shape of the §12 Result) plus the committed web/fake_result.json through the real PF.view. */
import { strict as assert } from "node:assert";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import * as U from "../web/lib/u1.js";
import { load, NAMES } from "./web_fixtures.mjs";

const require = createRequire(import.meta.url);
const PF = require("../web/lib.js");
let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); }
  catch (e) { failed += 1; console.error(`FAIL ${name}\n     ${e && e.message}`); }
}

const ev = (id, date, family, lat, lon, today, after, extra = {}) =>
  ({ event_id: id, date, title: id.replace(/_/g, " "), family, lat, lon, place: "Somewhere", today: { trough: today }, after: after === undefined ? null : { trough: after }, ...extra });
function run({ move = true, families = ["tariffs"], events, turbulence } = {}) {
  const r = {
    status: "ok", pilot: "robert", amount: 600000, question: "What if I put 40 % in it and the tariff war flares up again?",
    question_type: move ? "change" : "shock", as_of: "2026-11-12",
    profile: { name: "Robert", age: 59, capacity: 90000, capacity_dollars: 90000 },
    limits: { floor: -0.15, floor_source: "capacity", capacity_dollars: 90000 },
    portfolio: move ? { NVDA: 0.4, XIU: 0.6 } : { XIU: 1 }, baseline: move ? { portfolio: { XIU: 1 }, verdict: "Compatible" } : null,
    tipping_point: move ? { ticker: "NVDA" } : null,
    scenario: { families, change: move ? { op: "set", ticker: "NVDA", weight: 0.4 } : null },
    events: events || [
      ev("liberation_day_2025", "2025-04-03", "tariffs", 38.9, -77.04, -0.0596, -0.0899),
      ev("tariffs_canada_2025", "2025-03-04", "tariffs", 45.42, -75.7, -0.0189, -0.034),
      ev("tariff_pause_2025", "2025-04-09", "tariffs", 38.9, -77.04, 0, 0),
      ev("jackson_hole_2022", "2022-08-26", "rates", 38.89, -77.05, -0.0412, -0.1351),
      ev("ukraine_2022", "2022-02-24", "war_oil", 50.45, 30.52, 0, -0.012),
      ev("iran_2026", "2026-03-02", "war_oil", 35.69, 51.39, -0.0549, -0.0458),
      ev("chip_selloff_2024", "2024-07-17", "chips", 25.04, 121.56, -0.0162, -0.0954),
    ],
    turbulence: turbulence || { tariffs: { n: 6, worst_today: -0.0596, worst_after: -0.0899 }, war_oil: { n: 10 } },
  };
  return r;
}
const viewOf = (r) => PF.view(PF.withPaths(r));

test("easing tokens: the CSS cubic-bezier curves, exact at the ends and monotone", () => {
  for (const f of [U.easeOut, U.easeInOut]) {
    assert.equal(f(0), 0); assert.equal(f(1), 1); assert.equal(f(-1), 0); assert.equal(f(2), 1);
    let prev = 0; for (let i = 1; i <= 100; i++) { const y = f(i / 100); assert.ok(y >= prev - 1e-9, `monotone at ${i}`); prev = y; }
  }
  assert.ok(U.easeInOut(0.1) < 0.01 && U.easeInOut(0.9) > 0.99, "ease-in-out: slow start, slow landing");
  assert.ok(Math.abs(U.easeInOut(0.5) - 0.596) < 0.002, "cubic-bezier(.77,0,.175,1) at x = 0.5 (solved, not assumed symmetric)");
  assert.ok(U.easeOut(0.2) > 0.6, "ease-out is strong: most of the way by 20 % of the time");
});

test("askedFamily: the navigator's first family, null when the question names no shock", () => {
  assert.equal(U.askedFamily(run()), "tariffs");
  assert.equal(U.askedFamily(run({ families: [] })), null);
  assert.equal(U.askedFamily({}), null);
  assert.equal(U.askedFamily(null), null);
});

test("ignition order: date order, ties by id; the schedule ends so the last ring settles by totalMs", () => {
  const v = viewOf(run());
  const ids = U.ignitionOrder(U.shocksOf(v));
  assert.deepEqual(ids, ["ukraine_2022", "jackson_hole_2022", "chip_selloff_2024", "tariffs_canada_2025", "liberation_day_2025", "tariff_pause_2025", "iran_2026"]);
  assert.deepEqual(U.ignitionOrder([{ id: "b", date: "2025-01-01" }, { id: "a", date: "2025-01-01" }]), ["a", "b"]);
  const s = U.ignitionSchedule(ids, 4000);
  assert.equal(s.length, 7); assert.equal(s[0].at, 0); assert.equal(s[6].at, 3400);
  assert.ok(s.every((x, i) => i === 0 || x.at > s[i - 1].at));
  assert.deepEqual(U.ignitionSchedule(["x"], 4000), [{ id: "x", at: 0 }]);
  assert.deepEqual(U.ignitionSchedule([], 4000), []);
});

test("ring radius encodes the measured fall; no fall, a rise or a missing trough draws no ring", () => {
  assert.equal(U.ringRadius(null), null); assert.equal(U.ringRadius(undefined), null); assert.equal(U.ringRadius(NaN), null);
  assert.equal(U.ringRadius(0), null); assert.equal(U.ringRadius(0.02), null);
  assert.equal(U.ringRadius(-0.0004), null, "a fall that rounds to 0.0 % is no fall");
  assert.ok(Math.abs(U.ringRadius(-0.0899) - (U.RING_MIN + U.RING_PER_FALL * 0.0899)) < 1e-12);
  assert.ok(U.ringRadius(-0.135) > U.ringRadius(-0.09) && U.ringRadius(-0.09) > U.ringRadius(-0.01), "deeper fall, wider ring");
  assert.equal(U.ringRadius(-0.9), U.ringRadius(-0.5), "capped");
});

test("the globe draws the evaluated mix: events' after troughs with a move, today's without", () => {
  const withMove = U.shocksOf(viewOf(run()));
  assert.equal(withMove.find((e) => e.id === "liberation_day_2025").trough, -0.0899);
  const r = run({ move: false }); for (const e of r.events) e.after = null;
  const noMove = U.shocksOf(viewOf(r));
  assert.equal(noMove.find((e) => e.id === "liberation_day_2025").trough, -0.0596);
});

test("worst precedent: the asked family's deepest fall on the evaluated mix (Robert: Liberation Day, Washington)", () => {
  const v = viewOf(run());
  const w = U.worstPrecedent(v, "tariffs");
  assert.equal(w.id, "liberation_day_2025"); assert.equal(w.lat, 38.9); assert.equal(w.lon, -77.04);
  assert.equal(U.worstPrecedent(v, "war_oil").id, "iran_2026");
  assert.equal(U.worstPrecedent(v, null), null);
  assert.equal(U.worstPrecedent(v, "nothing"), null);
  const r = run({ move: false }); for (const e of r.events) e.after = null;
  assert.equal(U.worstPrecedent(viewOf(r), "war_oil").id, "iran_2026", "today's trough without a move");
});

test("hero view: the lead's composition when the worst epicentre is in view, else a turn that puts it where Washington sits", () => {
  assert.deepEqual(U.heroView(null), U.HOME);
  assert.deepEqual(U.heroView({ lat: 38.9, lon: -77.04 }), { lat: 20, lon: -80 });
  const tehran = U.heroView({ lat: 35.69, lon: 51.39 });
  assert.deepEqual(tehran, { lat: 17, lon: 48 });
  assert.ok(U.arcDeg(tehran, { lat: 35.69, lon: 51.39 }) < 25);
  assert.deepEqual(U.heroView({ lat: 25.04, lon: 121.56 }), { lat: 6, lon: 119 });
  assert.equal(U.heroView({ lat: 10, lon: -179 }).lon, 178, "wraps across the date line");
  assert.ok(Math.abs(U.arcDeg({ lat: 0, lon: 0 }, { lat: 0, lon: 90 }) - 90) < 1e-9);
});

test("caption: the asked family's name and the Result's own episode count; a question with no shock says so", () => {
  const c = U.heroCaption(run(), viewOf(run()));
  assert.deepEqual(c, { family: "tariffs", label: "Tariff war", n: 6, count: "6 earlier episodes on record" });
  const one = run({ turbulence: { tariffs: { n: 1 } } });
  assert.equal(U.heroCaption(one, viewOf(one)).count, "1 earlier episode on record");
  const none = run({ turbulence: {} });
  assert.equal(U.heroCaption(none, viewOf(none)).count, null, "no count without turbulence[family].n: never invented");
  const div = run({ families: [] }), d = U.heroCaption(div, viewOf(div));
  assert.equal(d.family, null); assert.equal(d.none, true);
  assert.equal(`${d.label} ${d.count}`, "No shock named: the replay covers your mix\u2019s own five years");
  assert.equal(U.heroCaption(null, null), null);
  const abst = run({ families: ["rates"] }); abst.scenario.weather = { no_precedent: true }; abst.scenario.event_ids = [];
  assert.equal(U.heroCaption(abst, viewOf(abst)).label, "No close precedent on record:", "an abstention is not 'no shock named'");
});

test("the first five seconds: the sweep starts 195° east of the investor's view; the quiet counter rises 1 … N in step", () => {
  assert.deepEqual(U.sweepStart(U.HOME), { lat: 20, lon: 115 }, "Robert: from Asia, past Europe and the Middle East, to the Americas");
  const one = U.counterText(1), all = U.counterText(37);
  assert.equal(one.n + one.rest, "1 shock on record");
  assert.equal(all.n + all.rest, "37 shocks on record");
  assert.equal(U.counterText(0), null); assert.equal(U.counterText(2.5), null);
  let peak = 0; for (let i = 1; i <= 1000; i++) peak = Math.max(peak, (U.easeTurn(i / 1000) - U.easeTurn((i - 1) / 1000)) * 1000);
  assert.ok(peak < 1.8 && U.easeTurn(0) === 0 && U.easeTurn(1) === 1 && Math.abs(U.easeTurn(0.5) - 0.5) < 1e-6, `a slow turn (peak ${peak.toFixed(2)} x mean)`);
  const rob = U.sweepPath(U.HOME);
  assert.deepEqual(rob, { from: { lat: 20, lon: 115 }, to: { lat: 20, lon: -80 } }, "Robert: 195° west, Asia to the Americas");
  assert.deepEqual(U.sweepPath({ lat: 16, lon: 48 }).to, { lat: 16, lon: 48 }, "Mateo: west from Asia to the Middle East");
  assert.deepEqual(U.sweepPath({ lat: 6, lon: 118 }).to, { lat: 6, lon: 118 }, "Amira: the short way, her shock is in view");
  for (const lon of [-179, -80, 0, 60, 114, 116, 180]) {
    const p = U.sweepPath({ lat: 0, lon }); assert.deepEqual(p.from, U.SWEEP_FROM, "always from the sweep poster's view");
    assert.ok(Math.abs(((p.to.lon - lon) % 360 + 360) % 360) < 1e-9, `ends on the view (${lon})`);
    assert.ok(p.to.lon <= 115 + 90 && p.to.lon >= 115 - 270, `never most of a full turn (${lon})`);
  }
  assert.deepEqual(U.HOME_MARKET, { lat: 43.65, lon: -79.38, place: "Toronto" });
});

test("legend: what a ring is and what its size means (the count is the counter's line)", () => {
  const v = viewOf(run());
  const l = U.legendText(v, PF.fmt.month);
  assert.equal(l.lead, "Each ring is a shock: tariffs, war and oil, chips, rates.");
  assert.equal(l.ring, "The wider its ring, the further your mix with the move fell after it.");
  assert.equal(l.past, "This already happened; it is not a forecast.", "red gate 4 where history is shown");
  const r = run({ move: false }); for (const e of r.events) e.after = null;
  assert.doesNotMatch(U.legendText(viewOf(r), PF.fmt.month).ring, /move/);
  assert.equal(U.legendText({}, PF.fmt.month).lead, "Each ring is a shock: tariffs, war and oil, chips, rates.");
});

test("persona: who, in one short sentence; the limits apart, in ONE quiet line (the lead 19:10: the front page is the portfolio and the words)", () => {
  const p = U.personaLines(viewOf(run()));
  const text = p.who.map((s) => s[0]).join(""), lim = p.limits.map((s) => s[0]).join("");
  assert.equal(text.replace(/\u00a0/g, " "), "Robert, 59, has $600,000.");
  /* R35 (15:55): the two limits apart, the floor rule from any high and the dollar line to stay above (capacity) */
  assert.equal(lim.replace(/\u00a0/g, " "), "Limits used, assumed for this fictional profile: no fall of more than 15 % from a high, and stay above $510,000.");
  assert.doesNotMatch(text + lim, /loss limit/, "R35: never one loss limit for both");
  assert.equal((lim.match(/[.!?](\s|$)/g) || []).length, 1, "one sentence");
  assert.doesNotMatch(text + lim, /\b(his|her)\b/, "one voice (R18): no his/her");
  assert.deepEqual(p.who.filter((s) => s[1] === "num").map((s) => s[0].replace(/\u00a0/g, " ")), ["59", "$600,000"]);
  assert.deepEqual(p.limits.filter((s) => s[1] === "num").map((s) => s[0].replace(/\u00a0/g, " ")), ["15 %", "$510,000"]);
  assert.match(p.note, /^Fictional illustration, not a recommendation\./);
  assert.match(p.note, /Fictional profiles; their limits are assumed\. Type your own on the live app, or describe yourself under You\./);   // R38: never "typed by you" for a persona
  assert.doesNotMatch(text + p.note, / · /, "no dot-joined meta strings (rules/web.md)");
  const c = run(); c.pilot = "canadian"; c.profile = { name: "Too Canadian?", age: null, capacity: 62500 }; c.amount = 250000;
  c.limits = { floor: -0.25, floor_source: "capacity", capacity_dollars: 62500 };
  const pc = U.personaLines(viewOf(c));
  assert.equal(pc.who.map((s) => s[0]).join("").replace(/\u00a0/g, " "), "A $250,000 portfolio.");
  assert.equal(pc.limits.map((s) => s[0]).join("").replace(/\u00a0/g, " "),
    "Limits used, assumed for this fictional profile: no fall of more than 25 % from a high, and stay above $187,500.");
  assert.equal(U.personaLines({}), null);
});

test("no advice words in any hero text", () => {
  const v = viewOf(run()), p = U.personaLines(v), l = U.legendText(v, PF.fmt.month), c = U.heroCaption(run(), v);
  const all = [p.note, ...p.who.map((s) => s[0]), ...p.limits.map((s) => s[0]), l.lead, l.ring, c.label, c.count].join(" ").toLowerCase();
  for (const w of [" buy", " sell", " hold ", "you should", "safe", "recommend "]) assert.ok(!all.includes(w), `no "${w.trim()}"`);
});

test("hero frame (R41): the desktop Earth an instrument in the right half, at most 540 px; the phone a small band above the words", () => {
  const d = U.heroFrame(1440, 900);
  assert.equal(d.cx, 1055); assert.equal(d.r, 270); assert.ok(d.cy - d.r >= 64 + 100 && d.cy + d.r <= 900 - 80, "between the headline and the key");
  assert.ok(2 * d.r <= 0.72 * 756, "about 70 % of the old 756 px disc");
  const s = U.heroFrame(1280, 800); assert.equal(s.cx, 938); assert.equal(s.r, 235); assert.ok(s.cy + s.r <= 800 - 80);
  const m = U.heroFrame(390, 844); assert.equal(m.cx, 195); assert.equal(m.r, 101); assert.equal(m.cy, 64 + 8 + 27 + 8 + 101);
  for (const [w, h] of [[390, 844], [360, 740], [1024, 768], [1280, 800], [1440, 900], [1920, 1080]]) {   // the poster frame stays inside
    const f = U.heroFrame(w, h), half = f.r * 10 / 9;
    assert.ok(f.cx - half >= 0 && f.cx + half <= w, `poster inside the viewport at ${w}x${h}`);
  }
  assert.deepEqual(U.heroFrame(0, 0), { cx: 0, cy: 0, r: 0 });
});

test("stage frame: the left third of a one-viewport stage, or the stage's own slot", () => {
  const f = U.stageFrame({ left: 0, top: 0, width: 1440, height: 900 });
  assert.equal(f.cx, 240); assert.equal(f.cy, 450); assert.equal(f.r, 216);
  assert.deepEqual(U.stageFrame({ left: 10, top: 20, width: 300, height: 200 }, true), { cx: 160, cy: 120, r: 100 });
  const m = U.stageFrame({ left: 0, top: 0, width: 390, height: 844 }); assert.equal(m.cx, 195); assert.ok(m.r <= 117);
  assert.equal(U.stageFrame(null), null); assert.equal(U.stageFrame({ left: 0, top: 0, width: 0, height: 10 }), null);
});

test("sticky box: pinned while its section covers the viewport, then leaves with it", () => {
  assert.deepEqual(U.stickyBox({ left: 0, top: 300, width: 1440, height: 1800, bottom: 2100 }, 900), { left: 0, top: 300, width: 1440, height: 900, bottom: 1200 });
  assert.deepEqual(U.stickyBox({ left: 0, top: -500, width: 1440, height: 1800, bottom: 1300 }, 900), { left: 0, top: 0, width: 1440, height: 900, bottom: 900 });
  assert.deepEqual(U.stickyBox({ left: 0, top: -1200, width: 1440, height: 1800, bottom: 600 }, 900), { left: 0, top: -300, width: 1440, height: 900, bottom: 600 });
  assert.deepEqual(U.stickyBox({ left: 0, top: 0, width: 1440, height: 600, bottom: 600 }, 900), { left: 0, top: 0, width: 1440, height: 600, bottom: 600 });
});

test("frames blend linearly; the ends are the frames themselves", () => {
  const a = { cx: 0, cy: 0, r: 100 }, b = { cx: 100, cy: 50, r: 20 };
  assert.equal(U.mixFrame(a, b, 0), a); assert.equal(U.mixFrame(a, b, 1), b);
  assert.deepEqual(U.mixFrame(a, b, 0.5), { cx: 50, cy: 25, r: 60 });
  assert.equal(U.mixFrame(null, b, 0.3), b); assert.equal(U.mixFrame(a, null, 0.3), a);
});

test("the committed fake Result: every helper runs on the real PF.view and nothing prints undefined or NaN", () => {
  const r = JSON.parse(readFileSync(new URL("../web/fake_result.json", import.meta.url), "utf8"));
  const v = viewOf(r);
  const fam = U.askedFamily(r), cap = U.heroCaption(r, v), p = U.personaLines(v), l = U.legendText(v, PF.fmt.month);
  const w = U.worstPrecedent(v, fam);
  assert.ok(w && Number.isFinite(w.lat));
  const all = JSON.stringify([cap, p, l, U.heroView(w), U.ignitionSchedule(U.ignitionOrder(U.shocksOf(v)), 4000)]);
  assert.doesNotMatch(all, /undefined|NaN/);
});

test("R22 on the four committed runs: the closed hero shows at most six numbers, no text a reader cannot use", () => {
  for (const name of NAMES) {
    const r = load(name), v = PF.view(r), c = U.heroCopy(r, v);
    const n = c.strings.reduce((k, t) => k + U.numbersIn(t), 0);
    /* R22's six, plus the two figures R35 adds to the persona line (the value to stay above and the floor's percent) */
    assert.ok(n <= 8, `${name}: ${n} numbers in the hero (${c.strings.join(" | ")})`);
    assert.ok(c.counter && c.counter.n === String(v.shocks.n), `${name}: the counter ends on the Result's own count`);
    assert.ok(c.persona && c.strings.includes(c.legend.past), `${name}: the persona sentence and "This already happened"`);
    for (const t of c.strings) assert.doesNotMatch(t, /undefined|NaN|null/, `${name}: ${t}`);
  }
  assert.equal(U.numbersIn("Robert, 59, has $600,000 and a $90,000 loss limit"), 3);
  assert.equal(U.numbersIn("No shock named: the replay covers your mix\u2019s own five years"), 0);
});

test("the four committed real runs (R17 fixtures): the asked shock, its worst precedent, the caption and the turn", () => {
  const want = { robert: ["tariffs", "liberation_day_2025", 6], mateo: ["war_oil", null, null], amira: ["chips", null, null], canadian: [null, null, null] };
  for (const name of NAMES) {
    const r = load(name), v = viewOf(r), fam = U.askedFamily(r), w = U.worstPrecedent(v, fam), cap = U.heroCaption(r, v);
    const p = U.personaLines(v), l = U.legendText(v, PF.fmt.month);
    assert.ok(p && p.who.length && l.lead.startsWith("Each ring is a shock:"), name);
    assert.doesNotMatch(JSON.stringify([p, l, cap]), /undefined|NaN| · /, name);
    if (fam) {
      assert.ok(w && Number.isFinite(w.lat) && w.family === fam && w.trough < 0, `${name}: a worst precedent in the asked family`);
      for (const e of U.shocksOf(v)) if (e.family === fam && Number.isFinite(e.trough)) assert.ok(e.trough >= w.trough, `${name}: none deeper`);
      assert.equal(cap.family, fam); assert.ok(cap.n === null || Number.isInteger(cap.n));
      const hv = U.heroView(w); assert.ok(U.arcDeg(hv, w) <= 45, `${name}: the turn shows the epicentre`);
    } else assert.equal(cap.none, true, `${name}: the no-shock caption`);
    if (name === "robert") {
      assert.equal(fam, want.robert[0]); assert.equal(w.id, want.robert[1]); assert.equal(cap.n, want.robert[2]);
      assert.deepEqual(U.heroView(w), U.HOME, "the lead's composition for Robert");
    }
  }
});

test("unproject is the exact inverse of the globe's camera (PF.globeProject), at any turn", () => {
  for (const view of [U.HOME, { lat: 39, lon: -77 }, { lat: 17, lon: 48 }, { lat: -30, lon: 150 }]) {
    for (let i = 0; i < 200; i++) {
      const lat = -80 + ((i * 37) % 160), lon = -180 + ((i * 113) % 360);
      const p = PF.globeProject(lat, lon, { tilt: view.lat, lon0: view.lon });
      if (!p.visible) continue;
      const q = U.unproject(p.x, p.y, view);
      assert.ok(q, `on the disc: ${lat},${lon}`);
      const dLon = Math.abs(((q.lon - lon + 540) % 360) - 180);
      assert.ok(Math.abs(q.lat - lat) < 1e-6 && (dLon < 1e-6 || Math.abs(lat) > 89.9), `${lat},${lon} via ${view.lat},${view.lon}: ${q.lat},${q.lon}`);
    }
  }
  const c = U.unproject(0, 0, { lat: 38.9, lon: -77.04 });
  assert.ok(Math.abs(c.lat - 38.9) < 1e-9 && Math.abs(c.lon + 77.04) < 1e-9 && c.facing > 0.999, "the disc centre is the view");
  assert.equal(U.unproject(1.01, 0, U.HOME), null, "off the disc");
});

test("caseLine: each case names what it tests, in plain words, never advice", () => {
  for (const id of ["robert", "mateo", "amira", "canadian"]) {
    const c = U.caseLine(id);
    assert.ok(c && c.tag && c.tests, id);
    assert.ok(c.tag.length <= 32, `${id}: the chip tag stays short (${c.tag})`);
    assert.ok(!/\b(buy|sell|hold|you should)\b/i.test(c.tag + c.tests), `${id}: no advice words`);
    assert.notEqual(c.tag, c.tag.toUpperCase(), `${id}: sentence case`);
  }
  assert.match(U.caseLine("robert").tests, /hyped/);
  assert.match(U.caseLine("mateo").tests, /values/);
  assert.match(U.caseLine("amira").tests, /anything goes/);
  assert.match(U.caseLine("canadian").tests, /S&P 500/);
  for (const id of ["robert", "mateo", "amira", "canadian"]) assert.ok(U.caseLine(id).tests.length <= 75, `${id}: one line at 1280`);
  assert.equal(U.caseLine("you"), null);
  assert.equal(U.caseLine("nobody"), null);
});

test("STACK_LINE: the first screen says where it fits and what runs it (the lead 19:25: first impression for the bank and AWS)", () => {
  assert.match(U.STACK_LINE, /^A pre-trade check for self-directed investors, never advice\./);
  assert.match(U.STACK_LINE, /Claude on Amazon Bedrock/);
  assert.match(U.STACK_LINE, /Guardrails/);
  assert.match(U.STACK_LINE, /code computes every number/);
  assert.doesNotMatch(U.STACK_LINE, /\b(buy|sell|hold|should|allowed|recommend)\b|\d| · /i);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
