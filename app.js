/* EPICENTRE Replay: the page's boot and the integrator (lane U0; contract in INTERFACES.md and the design doc §4).
   1. Collects every console error and uncaught failure into window.__errors (the capture scripts read it).
   2. Decides the mode (data.js: the static build's meta, else GET /api/health), the investor (?investor=, else Robert) and loads
      that investor's saved run (data.js: runs/<id>.json in static mode, GET /api/demo-run in live mode; never fake data), then
      puts result, view and question on the store.
   3. Imports every section named by a [data-module] element of index.html (web/sections/<name>.js) and calls mount(el, store):
      a module that is missing or throws is logged once and skipped (its element folds away); the page never blanks.
   4. Reloads the run whenever store.investor changes (one store update when the run is already here), and prefetches the others.
   window.__epi = { store, ready(), sections, timing, data } for the harness pages, the capture scripts and the recording;
   ?autoplay asks for one replay once the page is ready; ?presenter=1 shows the presenter keys (1-9, R, T, Esc).
   window.EPI_MOTION (ruling R9): true unless ?motion=0; setting it false adds html.motion-off, which stops CSS motion. */
import { store } from "./state.js";
import { detectMode, loadRun, peekRun, land, runLive, recompute, health, serverNote, cancelLive } from "./data.js";
import { initialDepth, mountDepth } from "./depth.js";
import { createTour, mountTourButton } from "./tour.js";
import { mountRail } from "./rail.js";
import { PUBLIC_URL } from "./lib/how.js";
import { mean } from "./sections/clarity.js";

/* the public static demo (the footer's QR, the share links): one constant (lane U7b's lib/how.js), on window for every lane;
   a page may set its own before app.js runs. Never a live endpoint (R8). */
if (typeof window.EPI_PUBLIC_URL !== "string" || !window.EPI_PUBLIC_URL) window.EPI_PUBLIC_URL = PUBLIC_URL;

/* ---- 1. errors: every console.error, uncaught exception and unhandled rejection is kept (never shown on the page) ---- */
const errors = (window.__errors = Array.isArray(window.__errors) ? window.__errors : []);
const keep = (what) => { try { errors.push(String(what).slice(0, 500)); } catch (e2) { /* nothing to keep */ } };
const consoleError = console.error.bind(console);
console.error = (...args) => {
  keep(args.map((a) => (a && a.stack) || (a && a.message) || a).join(" "));
  consoleError(...args);
};
addEventListener("error", (e) => keep(e.message || (e.target && e.target.src) || "error"));
addEventListener("unhandledrejection", (e) => keep((e.reason && (e.reason.stack || e.reason.message)) || e.reason || "unhandled rejection"));

/* ---- motion flag (R9): one switch every lane reads at call time ---- */
const params = new URLSearchParams(location.search);
let motion = params.get("motion") !== "0";
Object.defineProperty(window, "EPI_MOTION", {
  configurable: true,
  get() { return motion; },
  set(on) { motion = !!on; document.documentElement.classList.toggle("motion-off", !motion); },
});
window.EPI_MOTION = motion;

/* ---- presenter keys (ruling R19e, the pitch and the film; R22 adds T): 1-9 jump to the beats in order, R replays the stage,
   T plays the tour, Esc ends the
   motion (every piece at its end frame) until the next replay. Ignored while typing, with a modifier, or when a section has
   already used the key (the drawer's Esc). A keyboard action never animates: the jump is instant. ?presenter=1 shows a reminder. */
const BEATS = ["hero", "replay", "why", "money", "investors", "how", "deep", "scenario", "record"];   // the page's order (14:30 ruling)
const typing = (t) => !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ""));
let endedByEsc = false;
let tour = null;                                 // the tour (tour.js), created once the sections are mounted
const motionOn = () => window.EPI_MOTION !== false && !matchMedia("(prefers-reduced-motion: reduce)").matches;

function onPresenterKey(e) {
  if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || typing(e.target)) return;
  if (/^[1-9]$/.test(e.key)) {
    const el = document.getElementById(BEATS[Number(e.key) - 1]);
    if (!el || el.dataset.mount !== "ready" || !el.getClientRects().length) return;   // not on this page or folded away
    e.preventDefault();
    if (el.id === "hero") window.scrollTo(0, 0);
    else el.scrollIntoView({ block: "start" });
  } else if ((e.key === "t" || e.key === "T") && tour) {
    e.preventDefault();
    tour.start();
  } else if (e.key === "r" || e.key === "R") {
    e.preventDefault();
    store.set({ replay: Date.now() });
  } else if (e.key === "Escape") {
    endedByEsc = true;
    window.EPI_MOTION = false;
  }
}

/* the live server's honest line (lane b6's health keys), never in static mode: a small "Live server" chip in the bar's end group
   (the coordinator, 17:05: the first screen keeps its room), its sentence in the page's tooltip on hover, focus or tap and as
   the chip's description; without the bar, the one quiet line under it */
function showServerNote(mode) {
  const text = serverNote(health(), mode);
  if (!text) return;
  const end = document.querySelector("#bar .bar-end");
  if (end) {
    const icon = document.createElement("span");                    // the (i): a ring and the letter, drawn by styles.css
    icon.className = "srv-i";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "i";
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip srv-chip";
    chip.setAttribute("aria-label", "Live server");                 // the word, also when only the (i) shows
    const word = document.createElement("span");
    word.className = "srv-chip-w";
    word.textContent = "Live server";
    chip.append(icon, word);
    mean(chip, text);
    const date = end.querySelector(".bar-data");
    end.insertBefore(chip, date || end.firstChild);
    return;
  }
  const note = document.createElement("p");
  note.className = "server-note";
  note.setAttribute("role", "note");
  note.textContent = text;
  const bar = document.getElementById("bar");
  if (bar) bar.after(note); else document.body.prepend(note);
}

function presenterHint() {
  const part = (keys, words) => {
    const span = document.createElement("span");
    keys.forEach((k, i) => {
      if (i) span.append("to ");
      const kbd = document.createElement("kbd");
      kbd.textContent = k;
      span.append(kbd);
    });
    span.append(words);
    return span;
  };
  const box = document.createElement("div");
  box.className = "presenter-hint";
  box.setAttribute("role", "note");
  box.setAttribute("aria-label", "Presenter keys");
  box.append(part(["1", "9"], "the beats"), part(["R"], "replay"), part(["T"], "the tour"), part(["Esc"], "end the motion"));
  document.body.append(box);
}

/* ---- time-boxed sections (ruling R21): a section with data-flag="EPI_X" mounts only while window.EPI_X is not false; its
   stylesheet (data-css) is linked only then, so a section that ships off leaves no request and no trace. "Build your own
   shock" (#scenario): on by default; ?scenario=0 turns it off; to ship it off, set SCENARIO_ON to false. ---- */
const SCENARIO_ON = true;
if (typeof window.EPI_SCENARIO !== "boolean") window.EPI_SCENARIO = params.get("scenario") === "0" ? false : SCENARIO_ON;
/* "Try to trip it up" (#testai, the judge lane): off until its module lands (no request, no 404); ?testai=1 turns it on to test */
const TESTAI_ON = true;
/* "Watch the AI work" (#agentlog, R42, the agentlog lane): off until its module lands (no request, no 404); ?agentlog=1 to test */
const AGENTLOG_ON = true;                       // the agentlog lane's module landed (4a9395f, 12b8934, b761b5b)
if (typeof window.EPI_AGENTLOG !== "boolean") window.EPI_AGENTLOG = params.get("agentlog") === "1" ? true : AGENTLOG_ON;                         // the judge lane's module landed (89e8be7, 5a6773c)
if (typeof window.EPI_TESTAI !== "boolean") window.EPI_TESTAI = params.get("testai") === "1" ? true : TESTAI_ON;
const flaggedOff = (el) => !!el.dataset.flag && window[el.dataset.flag] === false;

function sectionCss(el) {                       // resolves when the section's own stylesheet has loaded (or failed), at most 1.5 s
  const href = el.dataset.css;
  if (!href || document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) return Promise.resolve();
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  const done = new Promise((r) => { link.onload = r; link.onerror = r; });
  document.head.append(link);
  return Promise.race([done, wait(1500)]);
}

/* ---- the investors ---- */
const INVESTORS = ["robert", "mateo", "amira", "canadian"];
const asked = params.get("investor");
const firstInvestor = INVESTORS.includes(asked) ? asked : "robert";

/* ---- 3. sections ---- */
const sections = {};                 // name -> "pending" | "mounted" | "missing" | "failed" | "off" (its flag is false)
const timing = {};                   // name -> ms from navigation start to its mount (performance review)
const MISSING = /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|404/i;

function mountOne(el, name, loaded) {
  if (loaded.error) {
    const missing = loaded.error instanceof TypeError && MISSING.test(String(loaded.error.message));
    sections[name] = missing ? "missing" : "failed";
    el.dataset.mount = sections[name];
    if (missing) console.warn(`[app] section "${name}" is not on this page yet (web/sections/${name}.js); skipped.`);
    else console.error(`[app] section "${name}" could not load; skipped.`, loaded.error);
    return;
  }
  const mount = loaded.mod && loaded.mod.mount;
  if (typeof mount !== "function") {
    sections[name] = "failed";
    el.dataset.mount = "failed";
    console.error(`[app] section "${name}" has no mount(el, store); skipped.`);
    return;
  }
  const failed = (e) => {
    sections[name] = "failed";
    el.dataset.mount = "failed";
    console.error(`[app] section "${name}" failed to mount; skipped.`, e);
  };
  try {
    const out = mount(el, store);
    sections[name] = "mounted";
    timing[name] = Math.round(performance.now());
    el.dataset.mount = "ready";
    el.querySelectorAll("[data-static]").forEach((n) => n.remove());      // the section draws its own now
    if (out && typeof out.then === "function") out.then(null, failed);
  } catch (e) {
    failed(e);
  }
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/* every module is fetched at once, while the first run is still on its way (startImports at boot); they mount in the page's
   order once the run is here, but a slow one never holds the others back for long */
function startImports() {
  return [...document.querySelectorAll("[data-module]")].flatMap((el) => {
    const name = el.dataset.module;
    if (flaggedOff(el)) { sections[name] = "off"; el.dataset.mount = "off"; return []; }   // shipped off: never fetched
    sections[name] = "pending";
    const loaded = Promise.all([import(`./sections/${name}.js`), sectionCss(el)])
      .then(([mod]) => ({ mod }), (error) => ({ error }));
    return [{ el, name, loaded }];
  });
}

async function mountAll(jobs) {
  const late = [];
  for (const job of jobs) {
    const got = await Promise.race([job.loaded, wait(1200).then(() => null)]);
    if (got) mountOne(job.el, job.name, got);
    else late.push(job.loaded.then((g) => mountOne(job.el, job.name, g)));
  }
  await Promise.race([Promise.all(late), wait(8000)]);
}

/* ---- 2 and 4. the run on screen ---- */
let wanted = null;                   // the investor whose run is on its way (a newer change wins)
let replayAtShow = 0;                // store.replay when the run on screen landed

function show(investor, result) {
  land(result, { question: (result && typeof result.question === "string") ? result.question : "" });
  document.documentElement.dataset.investor = investor;
  replayAtShow = store.get().replay;
}

async function switchTo(investor) {
  wanted = investor;
  if (investor === "you") return;                      // lane profile-ui: "You" has no saved run of its own (sections/you.js lands it)
  const hit = peekRun(investor);
  if (hit) { show(investor, hit); return; }            // already here: one store update, before any replay listener reads it
  const before = replayAtShow;
  let result = null;
  try { result = await loadRun(investor); }
  catch (e) { console.warn(`[app] no saved run for "${investor}"; the page keeps the last one.`, e); return; }
  if (wanted !== investor) return;                     // the investor changed again while this one was loading
  show(investor, result);
  /* a replay asked with the investor change (or while the run was on its way) played the old run: play the new one */
  if (store.get().replay !== before) store.set({ replay: Date.now() });
}

function prefetch() {
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 600));
  idle(() => INVESTORS.forEach((id) => { loadRun(id).catch(() => { /* not saved: the card says so */ }); }));
}

let readyResolve;
const readyPromise = new Promise((r) => { readyResolve = r; });

async function boot() {
  const jobs = startImports();
  const mode = await detectMode();
  store.set({ mode, investor: firstInvestor, depth: initialDepth(params) });
  /* the run of an investor comes from data.js: runs/<id>.json (static) or GET /api/demo-run (live), never fake data */
  let first = null;
  for (let attempt = 0; attempt < 2 && !first; attempt += 1) {         // one retry: a run file being rewritten reads as broken once
    try { first = await loadRun(firstInvestor); }
    catch (e) {
      if (attempt) console.warn(`[app] the saved run for "${firstInvestor}" could not be read; the sections draw without it.`, e);
      else await wait(700);
    }
  }
  if (first) show(firstInvestor, first);
  store.on("investor", (id) => { cancelLive(); switchTo(id); });   // a live run of the previous investor never lands after a switch
  /* a replay after Esc plays with motion again (registered before any section, so it runs before the stage's own listener) */
  store.on("replay", () => { if (endedByEsc) { endedByEsc = false; window.EPI_MOTION = true; } });
  addEventListener("keydown", onPresenterKey);
  if (params.get("presenter") === "1") presenterHint();
  await mountAll(jobs);
  try { showServerNote(mode); } catch (e) { console.error("[app] the live server's note could not show", e); }
  try { mountDepth(store); } catch (e) { console.error("[app] the Simple / Detailed switch could not mount", e); }
  try { mountRail(store); } catch (e) { console.error("[app] the step rail could not mount", e); }
  try { tour = createTour(store, { motionOn }); window.__epi.tour = tour; mountTourButton(tour); }
  catch (e) { console.error("[app] the tour could not mount", e); }
  document.documentElement.classList.add("is-booted");
  /* a link to a section (#replay, #record) lands on it now that the sections have their height */
  const target = location.hash.length > 1 ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
  if (target) target.scrollIntoView({ block: "start" });
  prefetch();
  readyResolve(true);
  if (params.has("autoplay")) store.set({ replay: Date.now() });   // the recording and the capture scripts: play once on load
}

window.__epi = {
  store,
  ready: () => readyPromise,
  sections,
  timing,
  data: { loadRun, runLive, recompute },
};

boot().catch((e) => { console.error("[app] boot failed", e); document.documentElement.classList.add("is-booted"); readyResolve(false); });
