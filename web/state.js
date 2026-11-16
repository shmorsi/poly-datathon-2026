/* EPICENTRE Replay: the one store (lane U0; contract in INTERFACES.md). Every section reads it, sets only the keys it owns and
   listens to the keys it draws. Plain ES module, no DOM.
   store.get()        the current state (a frozen object: read it, never write to it)
   store.set(patch)   shallow merge; then, for every key whose value changed (Object.is), its listeners in registration order,
                      then the "*" listeners once with the changed keys ({key: value}). A listener that throws is logged and
                      skipped; the others still run. A set() made inside a listener is applied and announced at once.
   store.on(key, fn)  fn(value, state) on each change of `key` (state = the latest state); returns an unsubscribe.
   Keys (INTERFACES.md): mode, investor, question, result, view, weightIndex, phase, steps, replay, globe, race, thread,
   depth (R22). */

const INITIAL = {
  mode: null,              // "live" | "static", set by app.js before any section mounts (null = not known yet: data.js asks)
  investor: "robert",      // "robert" | "mateo" | "amira" | "canadian"
  question: "",            // the command bar's words
  result: null,            // the Result on screen (U0 sets it with view whenever a run loads or lands)
  view: null,              // PF.view(result)
  weightIndex: null,       // 0..40 on tipping_point.curve, or null = the asked size (U4's dial)
  phase: "idle",           // "idle" | "reading" | "flying" | "racing" | "landed" (U2's timeline)
  steps: [],               // [{step, status, service, ms}] (U2, from the live NDJSON progress lines)
  replay: 0,               // Date.now() of the last replay request (hero.js, investors.js)
  globe: null,             // the globe API (hero.js), null without WebGL
  race: null,              // the race API (replay.js)
  thread: null,            // the fact id the thread drawer shows (U6), or null
  depth: "simple",         // "simple" | "detailed" (R22: the bar's switch, U0's depth.js; detailed opens every "Show the details")
};

let state = Object.freeze({ ...INITIAL });
const listeners = new Map();          // key -> array of functions (a copy is iterated, so unsubscribing inside a call is safe)

function call(fn, value, key) {
  try { fn(value, state); }
  catch (e) { console.error(`[store] a listener of "${key}" failed:`, e); }
}

function emit(key, value) {
  const fns = listeners.get(key);
  if (fns) for (const fn of fns.slice()) call(fn, value, key);
}

export const store = {
  get() { return state; },

  set(patch) {
    if (!patch || typeof patch !== "object") return;
    const changed = {};
    let any = false;
    for (const key of Object.keys(patch)) {
      if (!Object.is(state[key], patch[key])) { changed[key] = patch[key]; any = true; }
    }
    if (!any) return;
    state = Object.freeze({ ...state, ...changed });
    for (const key of Object.keys(changed)) emit(key, state[key]);
    emit("*", changed);
  },

  on(key, fn) {
    if (typeof fn !== "function") throw new TypeError("store.on(key, fn): fn must be a function");
    const fns = listeners.get(key) || [];
    fns.push(fn);
    listeners.set(key, fns);
    return () => {
      const now = listeners.get(key) || [];
      const i = now.indexOf(fn);
      if (i >= 0) now.splice(i, 1);
    };
  },
};

/* for tests and the dev harness pages only: back to the first state, every listener dropped */
export function resetStore() {
  state = Object.freeze({ ...INITIAL });
  listeners.clear();
}
