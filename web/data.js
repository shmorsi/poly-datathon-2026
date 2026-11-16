/* EPICENTRE Replay: where Results come from (lane U0; contract in INTERFACES.md). No DOM. Reads globalThis.PF at call time.
   detectMode()                     "static" when the page is the static build (<meta name="epicentre-mode" content="static">),
                                    a file:// page or ?static=1; else GET /api/health: it answers -> "live", otherwise "static".
   health(), serverNote(h, mode)    the live server's /api/health answer; the one honest line when it cannot look through the
                                    funds (holdings false, and deep false), never in static mode.
   loadRun(investor)                Promise<Result>: static runs/<investor>.json (else runs/index.json's entry for that investor);
                                    live GET /api/demo-run?pilot=<investor>. Cached per investor; never touches the store.
   runLive(body, onStep)            Promise<Result>: POST /api/run (NDJSON progress lines to onStep, then the result line); the
                                    landed Result goes on the store with its view (land) before the promise resolves. Live only.
   recompute(investor, result, id)  Promise<{fact_id, value, match, delta, ...}>: live POST /api/recompute {run_id, id}; static:
                                    the build-time check the Result carries, else {fact_id, value: null, match: null, static: true}.
   peekRun(investor)                the cached Result if it already arrived, else null (synchronous).
   land(result, extra)              store.set({...extra, result, view: PF.view(result), weightIndex: null, thread: null}): the one
                                    place result and view are set (a new run resets the dial and closes the thread drawer).
   An Error this module throws carries .plain = true when its message is a sentence the page may show (the server's own words
   or ours); any other error's message is never shown (PF.failureLine). */
import { store } from "./state.js";

const pf = () => globalThis.PF;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const plain = (message, extra) => Object.assign(new Error(message), { plain: true }, extra || {});
const meta = (name) => {
  const m = typeof document !== "undefined" ? document.querySelector(`meta[name="epicentre-${name}"]`) : null;
  return m ? m.content : null;
};

export const NO_RUN = "There is no saved run for this investor yet.";
export const NO_SERVER = "The server could not be reached. Check the connection, then try again.";
export const DROPPED = "The connection dropped before the answer arrived. Run the check again.";
export const STATIC_ONLY = "Live runs need the live app; this page replays saved runs.";

/* ---- mode, and what the live server says about itself (GET /api/health: data, bedrock, guardrail, holdings, deep) ---- */
let modePromise = null;
let healthPayload = null;
export const health = () => healthPayload;            // the last /api/health answer, or null (static mode never asks)

/* the one honest line a live server owes the reader when it cannot do what the saved runs show (lane b6's health keys);
   null when there is nothing to say, and always null in static mode */
export const SERVER_NOTE_HOLDINGS = "This live server reads funds directly: their holdings files are dated after the replay ends.";
export const SERVER_NOTE_DEEP = "This live server reads funds directly: their holdings files are dated after the replay ends, and it has no deep-history panel.";
export const SERVER_NOTE_TAIL = "The saved runs show the full look-through.";
export function serverNote(h, mode) {
  if (mode !== "live" || !isObj(h) || h.holdings !== false) return null;
  return `${h.deep === false ? SERVER_NOTE_DEEP : SERVER_NOTE_HOLDINGS} ${SERVER_NOTE_TAIL}`;
}

export function detectMode() {
  if (modePromise) return modePromise;
  modePromise = (async () => {
    const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
    if (meta("mode") === "static" || params.has("static")) return "static";
    if (typeof location !== "undefined" && location.protocol === "file:") return "static";
    const ctl = typeof AbortController === "function" ? new AbortController() : null;
    const timer = ctl ? setTimeout(() => ctl.abort(), 2500) : null;
    try {
      const res = await fetch("/api/health", { cache: "no-store", signal: ctl ? ctl.signal : undefined });
      if (!res.ok) return "static";
      try { const body = await res.json(); healthPayload = isObj(body) ? body : null; } catch (e) { healthPayload = null; }
      return "live";
    } catch (e) {
      return "static";
    } finally {
      if (timer) clearTimeout(timer);
    }
  })();
  return modePromise;
}

/* the store's mode once app.js (or a dev harness) has set it; before that, the probe */
const currentMode = async () => { const m = store.get().mode; return m === "live" || m === "static" ? m : detectMode(); };

/* ---- one fetch, read as JSON; a non-200 carries the server's own sentence when it sent one ---- */
async function problemOf(res) {
  try {
    const body = await res.json();
    const msg = isObj(body) && (body.message || body.detail || body.error);
    if (typeof msg === "string" && msg.trim()) return msg.trim();
  } catch (e) { /* not JSON */ }
  return res.status === 404 ? NO_RUN : NO_SERVER;
}

async function getJSON(url) {
  let res;
  try { res = await fetch(url, { cache: "no-store" }); }
  catch (e) { throw plain(NO_SERVER); }
  if (!res.ok) throw plain(await problemOf(res), { status: res.status });
  try { return await res.json(); }
  catch (e) { throw plain(NO_RUN); }
}

const usable = (r) => isObj(r) && r.status !== "error";

/* ---- saved runs ---- */
const cache = new Map();                 // "<mode>:<investor>" -> Promise<Result>
let indexPromise = null;                 // the static build's runs/index.json, read once

/* the saved runs sit next to index.html, as this module does: resolve against it, so a page in a sub-folder (web/dev/) or a site
   on a sub-path reads the same files */
const site = (path) => new URL(path, import.meta.url).href;

async function staticRun(investor) {
  try {
    const r = await getJSON(site(`runs/${encodeURIComponent(investor)}.json`));
    if (usable(r)) return r;
  } catch (e) { /* an older static build: look the investor up in runs/index.json */ }
  if (!indexPromise) indexPromise = getJSON(site("runs/index.json")).catch(() => []);
  const index = await indexPromise;
  const P = pf();
  const entry = P && typeof P.staticRun === "function" ? P.staticRun(index, investor)
    : (Array.isArray(index) ? index.find((x) => isObj(x) && x.pilot === investor && typeof x.file === "string") : null);
  if (!entry) throw plain(NO_RUN);
  const r = await getJSON(site(entry.file));
  if (!usable(r)) throw plain(NO_RUN);
  if (entry.commit && !r.commit) Object.defineProperty(r, "commit", { value: entry.commit, enumerable: false });
  return r;
}

async function liveRun(investor) {
  const r = await getJSON(`/api/demo-run?pilot=${encodeURIComponent(investor)}`);
  if (!usable(r)) throw plain((isObj(r) && typeof r.message === "string" && r.message) || NO_RUN);
  return r;
}

const landed = new Map();                // "<mode>:<investor>" -> the Result, once its fetch resolved (peekRun reads it)

export async function loadRun(investor) {
  const id = String(investor || "robert");
  const mode = await currentMode();
  const key = `${mode}:${id}`;
  if (!cache.has(key)) {
    const p = (mode === "live" ? liveRun(id) : staticRun(id));
    cache.set(key, p);
    p.then((r) => { landed.set(key, r); },
      () => { if (cache.get(key) === p) cache.delete(key); });          // a failure is not remembered: the next call retries
  }
  return cache.get(key);
}

/* the investor's saved run if it has already arrived (synchronously), else null: lets app.js swap investors in one store update */
export function peekRun(investor) {
  const m = store.get().mode;
  return (m === "live" || m === "static") ? landed.get(`${m}:${String(investor || "robert")}`) || null : null;
}

/* ---- the store's result and view, always together ---- */
export function viewOf(result) {
  const P = pf();
  if (!result || !P || typeof P.view !== "function") return null;
  const commit = result.commit || meta("commit") || null;
  return P.view(result, commit ? { commit } : undefined);
}

export function land(result, extra) {
  /* a new run resets what belonged to the old one: the dial goes back to the asked size, the thread drawer closes */
  store.set({ ...(extra || {}), result: result || null, view: viewOf(result), weightIndex: null, thread: null });
  return result;
}

/* ---- a live run: POST /api/run, NDJSON progress, then the Result ---- */
let liveCtl = null;
/* the live run in flight is cancelled (an investor switch): its promise rejects with .aborted and nothing lands */
export function cancelLive() {
  if (liveCtl) { liveCtl.abort(); liveCtl = null; }
}

export async function runLive(body, onStep) {
  if ((await currentMode()) !== "live") throw plain(STATIC_ONLY);
  cancelLive();
  const ctl = typeof AbortController === "function" ? new AbortController() : null;
  liveCtl = ctl;
  const stopped = () => !!(ctl && ctl.signal.aborted);
  const abortedError = () => plain("", { aborted: true });
  let res;
  try {
    res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
      signal: ctl ? ctl.signal : undefined });
  } catch (e) { throw stopped() ? abortedError() : plain(NO_SERVER); }
  if (!res.ok) throw plain(await problemOf(res), { status: res.status });
  if (!res.body || typeof res.body.getReader !== "function") throw plain(DROPPED, { dropped: true });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "", result = null;
  const feed = (text) => {
    let ev;
    try { ev = JSON.parse(text); } catch (e) { throw plain(DROPPED, { dropped: true }); }
    if (!isObj(ev)) return;
    if (ev.type === "result") { result = ev.result; return; }
    if (ev.type === "progress" && typeof onStep === "function") {
      try { onStep(ev); } catch (e) { console.error("[data] onStep failed:", e); }
    }
  };
  for (;;) {
    let chunk;
    try { chunk = await reader.read(); } catch (e) { throw stopped() ? abortedError() : plain(DROPPED, { dropped: true }); }
    if (chunk.done) break;
    buf += dec.decode(chunk.value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) feed(line);
    }
  }
  if (buf.trim()) feed(buf.trim());
  if (liveCtl === ctl) liveCtl = null;
  if (stopped()) throw abortedError();
  if (!isObj(result)) throw plain(DROPPED, { dropped: true });
  if (result.status === "error") throw plain(typeof result.message === "string" && result.message ? result.message : NO_SERVER, { result });
  land(result);
  return result;
}

/* ---- one number computed again ---- */
function savedCheck(result, factId) {
  const r = isObj(result) ? result : {};
  const places = [r.recomputed, isObj(r.proofs) ? r.proofs.recomputed : null, isObj(r.proofs) ? r.proofs.recompute : null];
  for (const place of places) if (isObj(place) && isObj(place[factId])) return place[factId];
  return null;
}

function normalized(answer, factId, extra) {
  const a = isObj(answer) ? answer : {};
  const value = isNum(a.value) ? a.value : null;
  const stored = isNum(a.stored) ? a.stored : null;
  const match = typeof a.match === "boolean" ? a.match : (typeof a.same === "boolean" ? a.same : null);
  const delta = isNum(a.delta) ? a.delta : (value !== null && stored !== null ? value - stored : null);
  return { ...a, fact_id: a.fact_id || a.id || factId, value, match, delta, ...(extra || {}) };
}

export async function recompute(investor, result, factId) {
  const id = String(factId || "");
  if ((await currentMode()) !== "live") {
    const saved = savedCheck(result, id);
    return saved ? normalized(saved, id, { static: true }) : { fact_id: id, value: null, match: null, delta: null, static: true };
  }
  const runId = isObj(result) && typeof result.run_id === "string" ? result.run_id : null;
  let res;
  try {
    res = await fetch("/api/recompute", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, id, fact_id: id, pilot: investor || null }) });
  } catch (e) { throw plain(NO_SERVER); }
  if (!res.ok) throw plain(await problemOf(res), { status: res.status });
  return normalized(await res.json(), id);
}
