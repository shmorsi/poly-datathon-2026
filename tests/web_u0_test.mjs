// Lane U0's pure tests: the store (web/state.js) and the data layer (web/data.js) under node, with fetch mocked.
// Run: node tests/web_u0_test.mjs   (tests/test_web_lib.py runs every tests/web_*_test.{cjs,mjs})
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
globalThis.PF = require("../web/lib.js");
const { store, resetStore } = await import("../web/state.js");
const data = await import("../web/data.js");

let passed = 0;
const test = async (name, fn) => {
  try { await fn(); passed += 1; }
  catch (e) { console.error(`FAIL ${name}\n`, e); process.exitCode = 1; }
};

// ---- the store ----
await test("set merges, announces only changed keys, then '*' once", () => {
  resetStore();
  const seen = [];
  store.on("phase", (v, s) => seen.push(["phase", v, s.phase]));
  store.on("investor", (v) => seen.push(["investor", v]));
  store.on("*", (changed) => seen.push(["*", Object.keys(changed).sort().join(",")]));
  store.set({ phase: "reading", investor: "robert" });          // investor unchanged: not announced
  assert.deepEqual(seen, [["phase", "reading", "reading"], ["*", "phase"]]);
  store.set({ phase: "reading" });                              // nothing changed: nothing announced
  assert.equal(seen.length, 2);
});

await test("the state is frozen and replaced, never mutated in place", () => {
  resetStore();
  const before = store.get();
  store.set({ weightIndex: 3 });
  assert.equal(before.weightIndex, null);
  assert.equal(store.get().weightIndex, 3);
  assert.ok(Object.isFrozen(store.get()));
  assert.throws(() => { "use strict"; store.get().weightIndex = 4; }, TypeError);
});

await test("a throwing listener is logged and the others still run", () => {
  resetStore();
  const quiet = console.error; const logged = [];
  console.error = (...a) => logged.push(a.join(" "));
  let ran = false;
  store.on("thread", () => { throw new Error("boom"); });
  store.on("thread", () => { ran = true; });
  store.set({ thread: "T1" });
  console.error = quiet;
  assert.ok(ran && logged.length === 1 && /thread/.test(logged[0]));
});

await test("on() returns an unsubscribe; a set inside a listener lands at once", () => {
  resetStore();
  let n = 0;
  const off = store.on("phase", () => { n += 1; });
  store.on("phase", (v) => { if (v === "landed") store.set({ weightIndex: 7 }); });
  store.set({ phase: "landed" });
  assert.equal(store.get().weightIndex, 7);
  off();
  store.set({ phase: "idle" });
  assert.equal(n, 1);
});

await test("the initial state names every INTERFACES.md key", () => {
  resetStore();
  const keys = Object.keys(store.get()).sort();
  assert.deepEqual(keys, ["depth", "globe", "investor", "mode", "phase", "question", "race", "replay", "result", "steps", "thread", "view", "weightIndex"]);
  assert.equal(store.get().depth, "simple");
  assert.equal(store.get().investor, "robert");
  assert.equal(store.get().phase, "idle");
});

// ---- data.js, fetch mocked ----
const RUN = (pilot, extra) => ({ status: "ok", pilot, run_id: `run-${pilot}`, question: `${pilot}'s question`, as_of: "2026-11-12",
  verdict: "Compatible", ...extra });
const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
let calls = [];
const mock = (routes) => {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push([String(url), init && init.method ? init.method : "GET", init && init.body ? JSON.parse(init.body) : null]);
    for (const [pattern, reply] of routes) if (pattern.test(String(url))) return typeof reply === "function" ? reply(url, init) : reply.clone();
    return json({ message: "not here" }, 404);
  };
};

await test("static mode: runs/<investor>.json, cached, never the store", async () => {
  resetStore();
  store.set({ mode: "static" });
  mock([[/\/web\/runs\/mateo\.json$/, json(RUN("mateo"))]]);
  const r = await data.loadRun("mateo");
  assert.equal(r.pilot, "mateo");
  assert.equal(store.get().result, null);                       // loading never changes the page
  await data.loadRun("mateo");
  assert.equal(calls.length, 1);                                // cached
  assert.equal(data.peekRun("mateo").run_id, "run-mateo");
  assert.equal(data.peekRun("amira"), null);
});

await test("static mode: an older build is read through runs/index.json", async () => {
  resetStore();
  store.set({ mode: "static" });
  mock([[/\/web\/runs\/index\.json$/, json([{ key: "abc", pilot: "amira", file: "runs/abc.json", commit: "1234567" }])],
        [/\/web\/runs\/abc\.json$/, json(RUN("amira"))]]);
  const r = await data.loadRun("amira");
  assert.equal(r.pilot, "amira");
  assert.deepEqual(calls.map((c) => c[0].replace(/^.*\/web\//, "")), ["runs/amira.json", "runs/index.json", "runs/abc.json"]);
});

await test("a missing run rejects with a plain sentence and is not cached", async () => {
  resetStore();
  store.set({ mode: "static" });
  mock([[/\/web\/runs\/index\.json$/, json([])]]);
  await assert.rejects(data.loadRun("canadian"), (e) => e.plain === true && e.message === data.NO_RUN);
  mock([[/\/web\/runs\/canadian\.json$/, json(RUN("canadian"))]]);
  assert.equal((await data.loadRun("canadian")).pilot, "canadian");
});

await test("live mode: GET /api/demo-run?pilot=<investor>; an error Result is refused", async () => {
  resetStore();
  store.set({ mode: "live" });
  mock([[/^\/api\/demo-run\?pilot=robert$/, json(RUN("robert"))],
        [/^\/api\/demo-run\?pilot=mateo$/, json({ status: "error", message: "No saved run for Mateo." })]]);
  assert.equal((await data.loadRun("robert")).run_id, "run-robert");
  await assert.rejects(data.loadRun("mateo"), (e) => e.plain && /Mateo/.test(e.message));
});

await test("land sets result and its PF.view together, resets the dial and the drawer", () => {
  resetStore();
  store.set({ weightIndex: 12, thread: "T3" });
  const seen = [];
  store.on("result", (r, s) => seen.push([r.pilot, s.view !== null, s.weightIndex, s.thread, s.question]));
  data.land(RUN("robert"), { question: "q" });
  assert.deepEqual(seen, [["robert", true, null, null, "q"]]);
  assert.equal(typeof store.get().view, "object");
});

const ndjson = (lines) => new Response(new ReadableStream({
  start(c) { const enc = new TextEncoder(); for (const l of lines) c.enqueue(enc.encode(JSON.stringify(l) + "\n")); c.close(); },
}), { status: 200, headers: { "Content-Type": "application/x-ndjson" } });

await test("runLive streams progress to onStep, lands the Result, resolves it", async () => {
  resetStore();
  store.set({ mode: "live" });
  const result = RUN("robert", { run_id: "live-1" });
  mock([[/^\/api\/run$/, () => ndjson([{ type: "progress", step: "OBSERVE", status: "run", service: "Python", ms: null },
    { type: "progress", step: "OBSERVE", status: "done", service: "Python", ms: 12 }, { type: "result", result }])]]);
  const steps = [];
  const r = await data.runLive({ pilot: "robert", q: "x" }, (s) => steps.push(`${s.step}:${s.status}`));
  assert.equal(r.run_id, "live-1");
  assert.deepEqual(steps, ["OBSERVE:run", "OBSERVE:done"]);
  assert.equal(store.get().result.run_id, "live-1");
  assert.equal(calls[0][1], "POST");
});

await test("runLive: a stream with no result line is 'dropped'; an error Result keeps the page's run", async () => {
  resetStore();
  store.set({ mode: "live" });
  data.land(RUN("robert", { run_id: "kept" }));
  mock([[/^\/api\/run$/, () => ndjson([{ type: "progress", step: "OBSERVE", status: "run" }])]]);
  await assert.rejects(data.runLive({}, null), (e) => e.dropped === true && e.plain === true);
  mock([[/^\/api\/run$/, () => ndjson([{ type: "result", result: { status: "error", message: "The guardrail stopped this question." } }])]]);
  await assert.rejects(data.runLive({}, null), (e) => /guardrail/.test(e.message));
  assert.equal(store.get().result.run_id, "kept");
  store.set({ mode: "static" });
  await assert.rejects(data.runLive({}, null), (e) => e.message === data.STATIC_ONLY);
});

await test("recompute: live posts {run_id, id} and normalizes the server's answer", async () => {
  resetStore();
  store.set({ mode: "live" });
  mock([[/^\/api\/recompute$/, json({ id: "T4", stored: -0.15, value: -0.15, same: true, text: "-15.0 %" })]]);
  const a = await data.recompute("robert", { run_id: "abc" }, "T4");
  assert.deepEqual([a.fact_id, a.value, a.match, a.delta, a.text], ["T4", -0.15, true, 0, "-15.0 %"]);
  assert.deepEqual([calls[0][2].run_id, calls[0][2].id], ["abc", "T4"]);
});

await test("recompute: static mode reads the saved check, else match null, with no request", async () => {
  resetStore();
  store.set({ mode: "static" });
  mock([]);
  const none = await data.recompute("robert", { run_id: "abc" }, "T4");
  assert.deepEqual([none.fact_id, none.match, none.static], ["T4", null, true]);
  const saved = await data.recompute("robert", { recomputed: { T4: { value: 2, stored: 2, same: true } } }, "T4");
  assert.deepEqual([saved.match, saved.delta, saved.static], [true, 0, true]);
  assert.equal(calls.length, 0);
});

await test("the live server's honest line: holdings false (and deep false), from a stubbed /api/health; never in static mode", async () => {
  resetStore();
  mock([[/^\/api\/health$/, json({ data: true, bedrock: true, guardrail: true, holdings: false, deep: false })]]);
  assert.equal(await data.detectMode(), "live");
  assert.deepEqual(data.health(), { data: true, bedrock: true, guardrail: true, holdings: false, deep: false });
  assert.equal(data.serverNote(data.health(), "live"), "This live server reads funds directly: their holdings files are dated after the " +
    "replay ends, and it has no deep-history panel. The saved runs show the full look-through.");
  assert.equal(data.serverNote({ holdings: false, deep: true }, "live"), "This live server reads funds directly: their holdings files are " +
    "dated after the replay ends. The saved runs show the full look-through.");
  assert.equal(data.serverNote({ holdings: true, deep: false }, "live"), null);
  assert.equal(data.serverNote({ holdings: false, deep: false }, "static"), null);
  assert.equal(data.serverNote(null, "live"), null);
  assert.equal(data.serverNote({ data: true }, "live"), null);               // an older server says nothing about holdings
});

await test("cancelLive: an investor switch aborts the live run in flight; it rejects with .aborted and lands nothing", async () => {
  resetStore();
  store.set({ mode: "live" });
  data.land(RUN("robert", { run_id: "kept" }));
  globalThis.fetch = (url, init) => new Promise((res, rej) => {
    init.signal.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
  });
  const p = data.runLive({ pilot: "robert" }, null);
  await new Promise((r) => setTimeout(r, 10));                    // the run has started (its request is in flight)
  data.cancelLive();
  await assert.rejects(p, (e) => e.aborted === true && e.plain === true);
  assert.equal(store.get().result.run_id, "kept");
});

console.log(`web_u0_test: ${passed} passed${process.exitCode ? ", FAILURES above" : ""}`);
