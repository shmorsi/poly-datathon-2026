// Lane U9 (the decision record, ruling R6): node tests of web/lib/record.js. Run: node tests/web_u9_test.mjs
// 1. canonicalJson is byte for byte proofs.canonical_json: a fixed table (bytes written by proofs.py) and, when a Python that
//    can import proofs is found (EPI_PYTHON, .venv/bin/python, python3, python), a live Python -> JS comparison.
// 2. sha256HexSync and sha256Hex (Web Crypto) agree with node:crypto.
// 3. buildRecord: values are pinned on the committed fixtures only (ruling R17): U0's tests/fixtures/web/*.json through
//    tests/web_fixtures.mjs. tests/web_u9_fixture.json is the same run cut to the keys the record reads: it must give the same
//    seal. web/fake_result.json and the saved runs under /tmp are shape checks only, skipped when absent. Any edit gives
//    another seal; the number put back, the seal again.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as R from "../web/lib/record.js";
import { load, NAMES } from "./web_fixtures.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
globalThis.PF = require("../web/lib.js");
let passed = 0;
const test = async (name, fn) => {
  try { await fn(); passed++; } catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; }
};

// ---- 1. the canonical form ------------------------------------------------------------------------------------------
const CASES = [
  [{ b: 1.0, a: [1 / 2048, -0.0, 3 / 2048, 1e-12, "é😀", null, true], z: 0.1 + 0.2 },
    '{"a":[0.0004882812,0,0.0014648438,0,"é😀",null,true],"b":1,"z":0.3}'],
  [[600000, 600000.0, -0.15, -0.3452439040250206, 0.425947, 1e21, -1e-11, 5e-11, 2.5, -2.5], '[600000,600000,-0.15,-0.345243904,0.425947,1000000000000000000000,0,0.0000000001,2.5,-2.5]'],
  [{ "￿": 1, "😀": 2, z: 3, "é": 4, A: 5, "": 6 }, '{"":6,"A":5,"z":3,"é":4,"￿":1,"😀":2}'],
  [["quote \" back \\ slash / tab \t nl \n cr \r ctl \u0001 \u001f del \u007f ls   nbsp   minus −"],
    '["quote \\" back \\\\ slash / tab \\t nl \\n cr \\r ctl \\u0001 \\u001f del \u007f ls   nbsp   minus −"]'],
  [{ nested: { list: [[], {}, [1, [2, [3]]]], f: false } }, '{"nested":{"f":false,"list":[[],{},[1,[2,[3]]]]}}'],
  [[-1 / 2048, 5 / 2048, 7 / 2048, 1 - 1 / 2048, 123456.5 / 2048, 0.00048828125], null],
  [[1e-7, 123456789.123456789, 4503599627370495.5, 0.1, 0.7, 1 / 3, 2 / 3, -1 / 3, 9.999999999995e-1], null],
];
await test("canonicalJson: the fixed bytes of proofs.canonical_json", () => {
  for (const [x, want] of CASES) if (want !== null) assert.equal(R.canonicalJson(x), want);
});
await test("canonicalJson: ties at the 10th decimal round to even (Python), not up (toFixed)", () => {
  assert.equal(R.canonicalJson(1 / 2048), "0.0004882812");          // toFixed(10) would give ...813
  assert.equal(R.canonicalJson(-1 / 2048), "-0.0004882812");
  assert.equal(R.canonicalJson(3 / 2048), "0.0014648438");
  assert.equal((1 / 2048).toFixed(10), "0.0004882813");
});
await test("canonicalJson refuses what Python refuses (undefined, a function)", () => {
  assert.throws(() => R.canonicalJson({ a: undefined }), TypeError);
  assert.throws(() => R.canonicalJson([() => 1]), TypeError);
});

function python() {
  const cands = [process.env.EPI_PYTHON, join(ROOT, ".venv/bin/python"), join(ROOT, "../poly-datathon-2026/.venv/bin/python"), "python3", "python"];
  for (const c of cands.filter(Boolean)) {
    if (c.includes("/") && !existsSync(c)) continue;
    const r = spawnSync(c, ["-c", "import proofs"], { cwd: ROOT, encoding: "utf8" });
    if (r.status === 0) return c;
  }
  return null;
}
const PY = python();
const pyCanon = (objs) => {
  const code = "import json, sys, hashlib, proofs\nfor line in sys.stdin:\n    c = proofs.canonical_json(json.loads(line))\n" +
    "    print(json.dumps([c, hashlib.sha256(c.encode('utf-8')).hexdigest()]))";
  const r = spawnSync(PY, ["-c", code], { cwd: ROOT, input: objs.map((o) => JSON.stringify(o)).join("\n") + "\n", encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  return r.stdout.trim().split("\n").map((l) => JSON.parse(l));
};

// ---- 3. the record (built here so the live Python check can seal it too) ---------------------------------------------
const TRIMMED = JSON.parse(readFileSync(join(ROOT, "tests/web_u9_fixture.json"), "utf8"));
const FIX = load("robert");
const FIX_REC = R.buildRecord(FIX, { commit: "abc1234" });
const shapes = [
  join(ROOT, "web/fake_result.json"),
  ...["/tmp/epi_runs_v1", "/tmp/epi_video/runs"].flatMap((d) => ["robert", "mateo", "amira", "canadian"].map((p) => join(d, `${p}.json`))),
].filter(existsSync);
const parsed = (p) => { try { const x = JSON.parse(readFileSync(p, "utf8")); return x && typeof x === "object" && Array.isArray(x.checks) ? x : null; } catch (e) { return null; } };
const results = [...NAMES.map((n) => [`fixture ${n}`, load(n)]), ["the trimmed fixture", TRIMMED], ...shapes.map((p) => [p, parsed(p)]).filter(([, r]) => r)];
const records = results.map(([p, r]) => [p, R.buildRecord(r, { commit: "abc1234" })]);

await test("canonicalJson = proofs.canonical_json, live from Python (cases and every record)", () => {
  if (!PY) { console.log("  (no Python that imports proofs: the live check is skipped, the fixed bytes above still hold)"); return; }
  const objs = [...CASES.map(([x]) => x), ...records.map(([, rec]) => rec)];
  const py = pyCanon(objs);
  objs.forEach((o, i) => {
    assert.equal(R.canonicalJson(o), py[i][0], `case ${i}`);
    assert.equal(R.sha256HexSync(R.canonicalJson(o)), py[i][1], `seal ${i}`);
  });
});

// ---- 2. SHA-256 -----------------------------------------------------------------------------------------------------
await test("sha256HexSync and Web Crypto agree with node:crypto", async () => {
  const texts = ["", "abc", "a".repeat(55), "a".repeat(56), "a".repeat(63), "a".repeat(64), "a".repeat(119), "é😀− %", "x".repeat(100000)];
  for (const t of texts) {
    const want = createHash("sha256").update(t, "utf8").digest("hex");
    assert.equal(R.sha256HexSync(t), want, `len ${t.length}`);
    assert.equal((await R.sha256Hex(t)).hex, want);
  }
  assert.equal(R.sha256HexSync("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

await test("buildRecord: plain JSON, no undefined, the Result's own values", () => {
  assert.ok(records.length >= 1, "no Result to test");
  for (const [p, rec] of records) {
    const walk = (x, path) => {
      assert.notEqual(x, undefined, `${p}: undefined at ${path}`);
      if (typeof x === "number") assert.ok(Number.isFinite(x), `${p}: ${path}`);
      if (x && typeof x === "object") for (const [k, v] of Object.entries(x)) walk(v, `${path}.${k}`);
    };
    walk(rec, "record");
    assert.equal(rec.schema, R.SCHEMA);
    assert.equal(rec.statement, "Client-run simulation, not a recommendation or a suitability assessment.");
    assert.equal(rec.disclaimer, "Educational simulation. This is not financial advice.");
    const r = results.find(([q]) => q === p)[1];
    assert.equal(rec.run.run_id, r.run_id);
    assert.equal(rec.investor.amount, r.amount);
    assert.equal(rec.question, r.question);
    assert.equal(rec.checks.length, r.checks.length);
    rec.checks.forEach((c, i) => { assert.equal(c.status, r.checks[i].status); assert.equal(c.value, r.checks[i].value); });
    for (const n of rec.numbers) {
      assert.ok(n.fact || n.key, `${p}: a number without a fact or a key`);
      if (n.fact) assert.equal(n.value, r.facts[n.fact].value);
      assert.ok(["fact", "assumption", "fiction", "limit", "scenario"].includes(n.kind), `${p}: kind ${n.kind}`);
    }
    assert.equal(rec.numbers.filter((n) => n.fact).length, Object.values(r.facts).filter((f) => typeof f.value === "number").length);
  }
});

await test("the record reads only the keys the trimmed fixture keeps: the same run cut to them gives the same seal", async () => {
  assert.equal(TRIMMED.run_id, FIX.run_id);
  assert.equal((await R.sealOf(R.buildRecord(TRIMMED, { commit: "abc1234" }))).hex, (await R.sealOf(FIX_REC)).hex);
});

await test("buildRecord on the committed fixture (Robert's move): the move, both verdicts, end values, breaks, the facts of each check", () => {
  const rec = FIX_REC, r = FIX;
  assert.equal(rec.run.run_id, "663294979c43");
  assert.deepEqual([rec.move.ticker, rec.move.name, rec.move.weight, rec.move.today_weight], ["NVDA", "NVIDIA", 0.4, 0]);
  assert.deepEqual([rec.money.end_with_move, rec.money.end_today], [1847077, 911676]);
  assert.deepEqual(rec.money.breaches.map((b) => [b.depth, b.loss_dollars]), [[-0.345243904, -207146.34], [-0.1692460973, -101547.66]]);
  assert.deepEqual(R.twist(rec).lines, ["Ended higher.", "Broke your floor twice on the way.", "Both are true."], "ruling R3's words, in the second person (R18)");
  assert.deepEqual(rec.checks.find((c) => c.rule === "max_drawdown").facts, ["T29", "T25"]);
  assert.deepEqual([rec.limits.floor.value, rec.limits.floor.dollars], [-0.15, 90000]);
  assert.deepEqual([rec.canada.today, rec.canada.with_move].map((x) => Math.round(x * 1000)), [876, 526]);
  assert.equal(rec.move.weight, r.portfolio.NVDA);
  assert.equal(rec.move.today_weight, 0);
  assert.equal(rec.verdict.today, r.baseline.verdict);
  assert.equal(rec.verdict.with_move, r.verdict);
  const curve = r.tipping_point.curve;
  assert.equal(rec.money.end_with_move, curve.find((c) => Math.abs(c.weight - r.portfolio.NVDA) < 1e-9).end_value);
  assert.equal(rec.money.end_today, curve[0].end_value);
  assert.equal(rec.money.breaches.length, r.breaches.length);
  assert.deepEqual(rec.money.breaches.map((b) => b.loss_dollars), r.breaches.map((b) => b.loss_dollars));
  const floor = rec.checks.find((c) => c.rule === "max_drawdown");
  assert.equal(floor.facts.length, 2);
  assert.equal(r.facts[floor.facts[0]].value, floor.value);
  assert.equal(r.facts[floor.facts[1]].value, floor.limit);
  assert.equal(rec.limits.floor.set_by, R.ASSUMED);
  assert.equal(rec.limits.floor.dollars, r.limits.capacity_dollars);
  assert.deepEqual(R.twist(rec, "his").lines.slice(0, 2), [r.tipping_point.curve[40].end_value > curve[0].end_value ? "Ended higher." : "Ended lower.",
    `Broke his floor ${R.timesWord(r.breaches.length)} on the way.`]);
  assert.equal(R.replayYears(rec), "2021–26");
});

await test("the tamper check: an edit gives another seal, the number put back gives the seal again", async () => {
  const rec = FIX_REC;
  const seal = (await R.sealOf(rec)).hex;
  assert.match(seal, /^[0-9a-f]{64}$/);
  assert.equal((await R.sealOf(R.buildRecord(FIX, { commit: "abc1234" }))).hex, seal, "the same Result gives the same seal");
  const path = "investor.amount", v = R.getAt(rec, path);
  const edited = R.setAt(rec, path, v + 1);
  assert.equal(R.getAt(rec, path), v, "the record itself is never changed");
  const broken = (await R.sealOf(edited)).hex;
  assert.notEqual(broken, seal);
  assert.ok(R.changedDigits(seal, broken).filter(Boolean).length > 40, "one changed number moves most of the 64 digits");
  assert.equal((await R.sealOf(R.setAt(edited, path, v))).hex, seal);
  assert.equal(R.parseEdit("−34.5 %", "pct"), -0.345);
  assert.equal(R.parseEdit("$1,847,077", "CAD"), 1847077);
  assert.equal(R.parseEdit("−$207,146", "CAD"), -207146);
  assert.equal(R.parseEdit("416 days", "days"), 416);
  assert.equal(R.parseEdit("forty", "pct"), "forty");
});

await test("the downloaded file: record, seal, canonical form, and a check line Python can run", async () => {
  const rec = FIX_REC;
  const seal = (await R.sealOf(rec)).hex, f = R.downloadFile(rec, seal);
  assert.match(f.name, /^epicentre-record-[\w-]+\.json$/);
  const back = JSON.parse(f.text);
  assert.equal(back.sha256, seal);
  assert.equal(R.sha256HexSync(R.canonicalJson(back.record)), seal, "the file's record, read back, has the same seal");
  assert.match(back.check, /proofs\.canonical_json/);
  if (PY) assert.equal(pyCanon([back.record])[0][1], seal, "Python reads the file and finds the same seal");
});

await test("buildRecord: each data source once (S1, S2, ...); the body POST /api/record sends stays under the server's 128 KB cap", () => {
  for (const [p, rec] of records) {
    const texts = Object.values(rec.sources);
    assert.equal(new Set(texts).size, texts.length, `${p}: a source text twice`);
    for (const n of rec.numbers) assert.ok(n.source === null || Object.prototype.hasOwnProperty.call(rec.sources, n.source), `${p}: ${n.source}`);
    assert.ok(Buffer.byteLength(JSON.stringify({ record: rec, sha256: "0".repeat(64) })) < 120 * 1024, `${p}: the record is too large to keep`);   // server.py RECORD_MAX_BODY_BYTES = 128 KB (3c5f5fe)
  }
  assert.ok(Object.keys(FIX_REC.sources).length >= 5);
});

await test("buildRecord: the worst fall and Canada's share are the Result's own keys", () => {
  for (const [p, rec] of records) {
    const r = results.find(([q]) => q === p)[1], side = rec.move ? "after" : "today";
    if (r.metrics && r.metrics[side] && typeof r.metrics[side].max_drawdown === "number") {
      assert.equal(rec.money.worst.depth, r.metrics[side].max_drawdown);
      if (rec.money.worst.loss_dollars !== null) assert.equal(rec.money.worst.loss_dollars, r.kpis.max_drawdown.loss_dollars);
    }
    const can = r.diversification && r.diversification.today && r.diversification.today.countries && r.diversification.today.countries.CAN;
    if (typeof can === "number") assert.equal(rec.canada.today, can);
    if (rec.canada && rec.canada.with_move !== null) assert.equal(rec.canada.with_move, r.diversification.after.countries.CAN);
  }
});

await test("storeRecord (lane B6's POST /api/record {record, sha256}): live only, the vault's seal compared, never a throw", async () => {
  const { storeRecord } = await import("../web/sections/record.js");
  const calls = [], realFetch = globalThis.fetch;
  const reply = (status, body) => async (url, init) => { calls.push([url, init && JSON.parse(init.body)]); return { ok: status < 300, status, json: async () => body }; };
  const answer = (status, extra) => ({ status, key: null, version_id: null, sha256: "abc", retain_until: null, message: "m", ...extra });
  globalThis.fetch = reply(200, answer("stored"));
  assert.deepEqual(await storeRecord({ a: 1 }, "abc", { mode: "static" }), { stored: false, text: "Storage needs the live app: this page replays saved runs. Download the record or print it." });
  assert.equal(calls.length, 0, "static mode never calls the server");
  globalThis.fetch = reply(404, { message: "That page or action was not found." });
  assert.match((await storeRecord({ a: 1 }, "abc", { mode: "live" })).text, /keeps no records yet/);
  assert.deepEqual(calls[0], ["/api/record", { record: { a: 1 }, sha256: "abc" }], "the seal goes with the record: the vault checks it");
  globalThis.fetch = reply(200, answer("stored", { key: "records/r/abc.json", version_id: "v123456789012345", retain_until: "2026-11-22T14:00:00Z" }));
  let out = await storeRecord({ a: 1 }, "abc", { mode: "live" });
  assert.deepEqual([out.stored, out.same, out.version], [true, true, "v123456789012345"]);
  assert.match(out.text, /^Kept in the private, versioned record vault, version v123\u20262345, locked until 22\u00a0Nov\u00a02026\. The vault computed the same fingerprint\.$/,
    "the version id is shown masked");
  out = await storeRecord({ a: 1 }, "def", { mode: "live" });
  assert.deepEqual([out.stored, out.same], [true, false]);
  globalThis.fetch = reply(200, answer("off", { message: "Record storage is off on this server; download the record instead." }));
  out = await storeRecord({ a: 1 }, "abc", { mode: "live" });
  assert.deepEqual([out.stored, out.text], [false, "Record storage is off on this server; download the record instead."]);
  globalThis.fetch = reply(422, { message: "The seal does not match the record: it changed after it was sealed, so it was not stored." });
  assert.match((await storeRecord({ a: 1 }, "abc", { mode: "live" })).text, /^The seal does not match the record/);
  globalThis.fetch = async () => { throw new Error("down"); };
  out = await storeRecord({ a: 1 }, "abc", { mode: "live" });
  assert.equal(out.stored, false);
  assert.doesNotMatch(out.text, /down/, "an exception's text never reaches the page");
  globalThis.fetch = realFetch;
});

await test("words: once, twice, n times; the replay years", () => {
  assert.deepEqual([1, 2, 3].map(R.timesWord), ["once", "twice", "3 times"]);
  assert.equal(R.replayYears({ replay: { first: "2021-11-12", last: "2026-11-12" } }), "2021–26");
  assert.equal(R.replayYears({ replay: { first: "1999-01-01", last: "2001-01-01" } }), "1999–2001");
  assert.equal(R.twist({ move: {}, money: { end_with_move: 2, end_today: 1, breaches: [] } }, "her").lines.join(" "), "Ended higher. Never broke her floor on the way.");
});

await test("one status vocabulary (R20): the record's mapping is the checklist's (web/lib/money.js) and status.js's once it lands", async () => {
  const theirs = [];
  for (const f of ["../web/lib/status.js", "../web/lib/money.js"]) {
    if (!existsSync(join(ROOT, "tests", f))) continue;
    const m = await import(f);
    if (typeof m.shownStatus === "function") theirs.push([f, m.shownStatus]);
  }
  assert.ok(theirs.length, "no shared mapping found to compare with");
  for (const status of ["fail", "warn", "pass", "error", null]) for (const tier of ["hard", "soft", "preference", "warn", null]) {
    for (const [f, fn] of theirs) {
      const a = R.shownStatus(status, tier), b = fn(status, tier);
      assert.deepEqual(a && [a.word, a.icon, a.tone], b && [b.word, b.icon, b.tone], `${f} ${status} ${tier}`);
    }
  }
  assert.equal(R.shownStatus("fail", "soft").word, "Caution");
  assert.equal(R.shownStatus("fail", "hard").word, "Outside");
  const one = FIX_REC.checks.find((c) => c.rule === "single_stock");
  assert.deepEqual([one.status, one.tier, one.shown], ["fail", "soft", "Caution"], "the record's file says what the client saw");
});

// ---- 4. the section mounted on a minimal DOM (no browser): it renders, and the tamper flow works end to end -------------
const until = async (cond, what, ms = 4000) => {
  const t0 = Date.now();
  while (!cond()) { if (Date.now() - t0 > ms) throw new Error(`timed out waiting for ${what}`); await new Promise((ok) => setTimeout(ok, 10)); }
};
const drained = () => new Promise((ok) => setTimeout(ok, 120));          /* pending digests finish before the fake DOM goes */
class FNode { constructor() { this.childNodes = []; this.parentNode = null; } get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; } }
class FText extends FNode { constructor(t) { super(); this.data = String(t); this.nodeType = 3; } get textContent() { return this.data; } set textContent(v) { this.data = String(v); } }
class FEl extends FNode {
  constructor(tag) {
    super(); this.nodeType = 1; this.tagName = String(tag).toUpperCase(); this.attrs = new Map(); this.listeners = new Map(); this.cls = new Set(); this.dataset = {}; this.hidden = false;
    const self = this;
    this.classList = { add: (...c) => c.forEach((x) => self.cls.add(x)), remove: (...c) => c.forEach((x) => self.cls.delete(x)), contains: (c) => self.cls.has(c),
      toggle: (c, f) => { const on = f === undefined ? !self.cls.has(c) : !!f; on ? self.cls.add(c) : self.cls.delete(c); return on; },
      replace: (a, b) => { if (self.cls.delete(a)) self.cls.add(b); } };
  }
  get children() { return this.childNodes.filter((n) => n instanceof FEl); }
  get className() { return [...this.cls].join(" "); }
  set className(v) { this.cls = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get textContent() { return this.childNodes.map((n) => n.textContent).join(""); }
  set textContent(v) { this.childNodes = []; this.append(String(v)); }
  append(...xs) { for (const x of xs) { const n = typeof x === "string" ? new FText(x) : x; n.parentNode = this; this.childNodes.push(n); } }
  replaceChildren(...xs) { this.childNodes = []; this.append(...xs); }
  remove() { if (this.parentNode) this.parentNode.childNodes = this.parentNode.childNodes.filter((n) => n !== this); this.parentNode = null; }
  after(n) { if (n.remove) n.remove(); const p = this.parentNode; p.childNodes.splice(p.childNodes.indexOf(this) + 1, 0, n); n.parentNode = p; }
  prepend(n) { if (n.remove) n.remove(); this.childNodes.unshift(n); n.parentNode = this; }
  setAttribute(k, v) { if (k === "class") this.className = v; else if (k === "hidden") this.hidden = true;
    else if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(v); this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  removeAttribute(k) { if (k === "hidden") this.hidden = false; this.attrs.delete(k); }
  addEventListener(t, fn) { (this.listeners.get(t) || this.listeners.set(t, []).get(t)).push(fn); }
  removeEventListener() {}
  fire(type, extra) { const ev = { type, target: this, preventDefault() {}, stopPropagation() {}, ...extra };
    for (let n = this; n; n = n.parentNode) for (const fn of (n.listeners && n.listeners.get(type)) || []) fn(ev); }
  matches(sel) {
    return sel.split(",").map((x) => x.trim()).some((one) => {
      const m = /^\.([\w-]+)$/.exec(one); if (m) return this.cls.has(m[1]);
      const d = /^\[data-path="([^"]+)"\]$/.exec(one); if (d) return this.dataset.path === d[1];
      return /^[a-z][a-z0-9]*$/.test(one) && this.tagName === one.toUpperCase();
    });
  }
  get nextSibling() { const p = this.parentNode; return p ? p.childNodes[p.childNodes.indexOf(this) + 1] || null : null; }
  querySelectorAll(sel) { const out = []; const walk = (n) => { for (const c of n.children) { if (c.matches(sel)) out.push(c); walk(c); } }; walk(this); return out; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  closest(sel) { for (let n = this; n instanceof FEl; n = n.parentNode) if (n.matches(sel)) return n; return null; }
  focus() {} blur() {}
}
await test("the section mounts on all four committed fixture runs (static and live) and the seal breaks and heals (a minimal DOM)", async () => {
  const saved = ["document", "matchMedia", "IntersectionObserver"].map((k) => [k, globalThis[k]]);
  globalThis.document = { createElement: (t) => new FEl(t), createElementNS: (ns, t) => new FEl(t), querySelector: () => null, body: new FEl("body"), documentElement: new FEl("html") };
  globalThis.matchMedia = () => ({ matches: false });
  globalThis.IntersectionObserver = class { observe() {} disconnect() {} };
  try {
    const { mount } = await import("../web/sections/record.js");
    const listeners = new Map();
    let state = Object.freeze({ mode: "static", result: load("robert"), view: null, thread: null });
    const store = { get: () => state, set(p) { state = Object.freeze({ ...state, ...p }); for (const k of Object.keys(p)) for (const fn of listeners.get(k) || []) fn(state[k], state); },
      on(k, fn) { (listeners.get(k) || listeners.set(k, []).get(k)).push(fn); return () => {}; } };
    const el = new FEl("section");
    mount(el, store);
    const status = () => (el.querySelector(".rec-seal-status") || { textContent: "" }).textContent;
    await until(() => /^Record intact/.test(status()), "the first seal");
    const text = el.textContent;
    assert.ok(el.querySelector(".rec-card"), "the card is drawn");
    for (const words of ["What do you keep?", "Robert", "Ended higher. Broke your floor twice on the way.", "Both are true.", "in this 2021–26 replay",
      "For an order-execution-only broker: shown before the order, kept after it.", "assumed from the profile, not set by you, and never read from an account.",
      "Client-run simulation, not a recommendation or a suitability assessment.", "Educational simulation. This is not financial advice.",
      "This already happened; it is not a forecast.", "Fictional illustration, not a recommendation."]) assert.ok(text.includes(words), words);
    assert.doesNotMatch(text.replace(/“[^”]*”/g, ""), /\b(his|her|he|she)\b/i, "one voice inside the card (R18)");
    assert.doesNotMatch(text, /\b(buy|sell|hold|you should|we recommend|recommended)\b/i, "no advice words");
    const g = load("robert").guardrail.output.grounding, rc = load("robert").receipt;
    assert.ok(text.includes(`Every number was checked by code (${rc.verified} of ${rc.total}).`), "the plain line, from the Result's own receipt");
    assert.ok(!text.includes("Output grounding") && g.score !== undefined, "the grounding score shows once on the page, in #how (controller, 12:35)");
    assert.doesNotMatch(text, /output passed/i, "never 'passed' beside a score under its threshold");
    assert.ok(text.includes("private, versioned Amazon S3 (live app only)"));
    assert.equal(status(), "Record intact: this record matches the run.");
    assert.ok(el.querySelectorAll(".rec-n").length > 30, "the numbers are registered");
    el.querySelector(".rec-edit").fire("click");
    const n = el.querySelector('[data-path="money.end_with_move"]');
    n.textContent = "$2,847,077";
    n.fire("input");
    await until(() => /^Record changed/.test(status()), "the broken seal");
    assert.equal(status(), "Record changed: this record no longer matches the run.");
    assert.match(el.querySelector(".rec-changes").textContent, /^Changed: the end value with the move, \$1,847,077 to \$2,847,077\.$/);
    const liveLine = el.querySelector(".rec-live");
    assert.ok(liveLine && !liveLine.hidden && liveLine.parentNode === n.closest("li") && liveLine.closest(".rec-money"),
      "the seal's state sits in the flow, inside the edited row (the number typed in does not move)");
    assert.match(liveLine.textContent, /^Record changed:one number changed; its fingerprint is now[0-9a-f]{16}\u2026Put the run\u2019s numbers back$/);
    n.fire("keydown", { key: "Escape" });
    await until(() => /^Record intact/.test(status()), "the seal again");
    assert.equal(status(), "Record intact: this record matches the run.");
    assert.ok(el.querySelector(".rec-live").hidden, "no line once the record matches again");
    el.querySelector(".rec-keep").fire("click");
    await until(() => !el.querySelector(".rec-kept").hidden, "the keep message");
    assert.equal(el.querySelector(".rec-kept").textContent, "Storage needs the live app: this page replays saved runs. Download the record or print it.");
    store.set({ result: load("mateo") });
    await until(() => el.textContent.includes("What do you keep?") && el.textContent.includes("Mateo") && /^Record intact/.test(status()), "Mateo's record");
    assert.ok(el.textContent.includes("Mateo") && el.textContent.includes("What do you keep?") && el.textContent.includes("No move: the question replays your mix as it is."));
    const { checksModel } = await import("../web/lib/money.js");            /* the checklist's own rows (lane U5b) */
    for (const name of NAMES) {                        /* one vocabulary (R20): every row's word, icon and tier is the checklist's */
      const r = load(name), box = new FEl("section"), one = { get: () => Object.freeze({ mode: "static", result: r, view: null }), set() {}, on() { return () => {}; } };
      mount(box, one);
      await until(() => box.querySelector(".rec-seal-status") && /^Record intact/.test(box.querySelector(".rec-seal-status").textContent), `${name}'s seal`);
      const mine = box.querySelectorAll(".rec-check").map((li) => ({ rule: li.dataset.rule, word: li.querySelector(".rec-st").textContent,
        icon: li.querySelector(".rec-st").children[0].children[0].getAttribute("href").slice(1), tier: li.querySelector(".rec-tier").textContent }));
      const theirs = checksModel(r, globalThis.PF.view(r), globalThis.PF).rows.map((x) => ({ rule: x.rule, word: x.word, icon: x.icon, tier: x.tierText || "" }));
      assert.deepEqual(mine, theirs, `${name}: the record's rows are the checklist's`);
      assert.ok(box.textContent.includes(`All ${theirs.length} checks, the most serious first`), name);
    }
    for (const name of NAMES) {                        /* mount() on each of the four fixture runs, live and static: no throw, a card, a seal */
      for (const mode of ["static", "live"]) {
        const box = new FEl("section"), one = { get: () => Object.freeze({ mode, result: load(name), view: null }), set() {}, on() { return () => {}; } };
        assert.doesNotThrow(() => mount(box, one), `${name} ${mode}`);
        await until(() => box.querySelector(".rec-seal-status") && /^Record intact/.test(box.querySelector(".rec-seal-status").textContent), `${name} ${mode}`);
        assert.ok(box.querySelector(".rec-card") && !box.hidden, `${name} ${mode}: no card`);
        assert.match(box.querySelector(".rec-seal-status").textContent, /^Record intact:/, `${name} ${mode}`);
        assert.equal(box.querySelectorAll(".rec-hx").length, 64);
      }
    }
  } finally {
    await drained();
    for (const [k, v] of saved) globalThis[k] = v;
  }
});

await test("your calmer self: the record keeps the limits first shown; a limit changed after the answer is one sealed line", async () => {
  const r = load("robert"), loose = { ...r, limits: { ...r.limits, floor: -0.35, edited: ["floor"] }, rechecked: true };
  assert.deepEqual(R.limitChanges(r, loose), [{ limit: "floor", from: -0.15, to: -0.35 }]);
  assert.deepEqual(R.limitChanges(r, r), []);
  const plain = R.buildRecord(r, {}), kept = R.buildRecord(r, { after: R.limitChanges(r, loose) });
  assert.equal(plain.after_answer, undefined, "no change, no line: the seal of a plain run is unchanged");
  assert.deepEqual(kept.after_answer, [{ limit: "floor", from: -0.15, to: -0.35, when: "after seeing the answer" }]);
  assert.equal(kept.limits.floor.value, -0.15, "the limits as first shown");
  assert.notEqual((await R.sealOf(kept)).hex, (await R.sealOf(plain)).hex, "the change is sealed too");
  /* the section, with lane U5b's own merge of a recheck (web/lib/money.js mergeRecheck) */
  const { mergeRecheck } = await import("../web/lib/money.js");
  const saved = ["document", "matchMedia", "IntersectionObserver"].map((k) => [k, globalThis[k]]);
  globalThis.document = { createElement: (t) => new FEl(t), createElementNS: (ns, t) => new FEl(t), querySelector: () => null, body: new FEl("body"), documentElement: new FEl("html") };
  globalThis.matchMedia = () => ({ matches: false });
  globalThis.IntersectionObserver = class { observe() {} disconnect() {} };
  try {
    const { mount } = await import("../web/sections/record.js");
    const listeners = new Map();
    let state = Object.freeze({ mode: "live", result: r, view: null });
    const store = { get: () => state, set(p) { state = Object.freeze({ ...state, ...p }); for (const k of Object.keys(p)) for (const fn of listeners.get(k) || []) fn(state[k], state); },
      on(k, fn) { (listeners.get(k) || listeners.set(k, []).get(k)).push(fn); return () => {}; } };
    const el = new FEl("section"), hashText = () => (el.querySelector(".rec-hash-v") || { textContent: "" }).textContent;
    mount(el, store);
    await until(() => hashText().length > 60, "the first seal");
    const seal0 = hashText();
    const merged = mergeRecheck(r, { checks: r.checks, verdict: r.verdict }, { limits: { floor: -0.35 } }, { capacity: 210000 });
    store.set({ result: merged });
    await until(() => hashText().length > 60 && hashText() !== seal0, "the seal with the change");
    const text = el.textContent;
    assert.ok(text.includes("You changed your floor from −15 % to −35 % after seeing the answer."), "the line");
    assert.ok(text.includes("The limits, as first shown") && text.includes("no fall of more than 15 % from any high"), "the first limits stay on the record");
    assert.notEqual(hashText(), seal0, "sealed with the change");
    assert.equal(el.querySelector(".rec-seal-status").textContent, "Record intact: this record matches the run.");
    store.set({ result: r });
    await until(() => hashText() === seal0, "the first seal again");
    assert.ok(!el.textContent.includes("after seeing the answer"), "back to the run's limits: no line");
  } finally {
    await drained();
    for (const [k, v] of saved) globalThis[k] = v;
  }
});

console.log(`web_u9_test: ${passed} passed${PY ? " (live Python check: " + PY + ")" : ""}`);
