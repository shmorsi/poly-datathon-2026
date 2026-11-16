/* EPICENTRE Replay, lane judge: the pure helpers behind "Try to trip it up" (web/sections/testai.js) and the bar's "Judging?
   Start here" popover. No DOM, no network: the section fetches, this module decides. Contract: INTERFACES.md "tests.json"
   (data/demo_runs/tests.json, the ai lane's recording: {version, tests: [{id, label, question, shows, kind, pilot?, key?,
   response?}]}; kind "run" names a saved run by its 16-hex key, "blocked" and "clarify" carry the API's own JSON).
   testsSource({meta, override})  where the page reads tests.json: window.EPI_TESTS_URL, else the static build's
                                  <meta name="epicentre-tests">, else null (no request at all: the section stays hidden,
                                  nothing 404s, release gate (e) stays clean)
   readTests(json)                the cards' tests, checked (an unknown kind or a test without its question is dropped)
   actionFor(test, mode)          what "Run it" does: {type: "inline"} (static blocked / clarify: the recorded answer in the
                                  card), {type: "load", key, pilot} (static run: the saved run onto the stage), {type: "live",
                                  question, pilot} (live: the question down the app's normal path), or null (cannot run)
   stopOf(response)               who stopped or answered a blocked / clarify question, in words, and the answer's own text
   cardView(test, mode)           every string a card shows
   judgeSteps(o), keyAction(key, open)   the popover: its steps and its keys (it never opens by itself: the pill is enough)
   spans(n)                       the cards' columns on the 12-column grid: two full rows, never an orphan (6 = 3 + 3, 7 = 4 + 3)
   Copy rules: R1 past tense, R16 no " · " strings, R18 typographic quotes, R22 at most 3 figures a card, red gate 1 (never an
   advice word outside the quoted question). */
import { schedule } from "./replay.js";
import { countFigures, plain } from "./meaning.js";

const obj = (x) => (x !== null && typeof x === "object" && !Array.isArray(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);

export const KINDS = Object.freeze(["run", "blocked", "clarify"]);
export const KEY_RE = /^[0-9a-f]{16}$/;                 // a saved run's file name (scripts/record_demo.py KEY_FILE)
export const DEFAULT_PILOT = "robert";
export const NAMES = Object.freeze({ robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "Too Canadian?" });   // lib.js PILOT
const BACK = Object.freeze({ robert: "Back to Robert’s own question", mateo: "Back to Mateo’s own question",
  amira: "Back to Amira’s own question", canadian: "Back to the Too Canadian? question" });   // a case title is not a name
export const DISCLAIMER = "Educational simulation. This is not financial advice.";
export const MAX_TESTS = 8;

export const TITLE = "Try to trip it up";
const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"];
export const countWord = (n) => WORDS[n] || String(n);
export const lede = (n) => `${countWord(n)} question${n === 1 ? "" : "s"} that show${n === 1 ? "s" : ""} what the AI does — and what it refuses to do.`;

/* ---- where tests.json lives ---- */
const SAFE_URL = /^(?:\.{0,2}\/)?[\w./-]*\.json$|^https?:\/\/[^\s"'<>]+\.json$/i;
export function testsSource(o) {
  const x = obj(o) || {};
  for (const c of [x.override, x.meta]) {
    const u = str(c);
    if (u && SAFE_URL.test(u) && !u.includes("..")) return u;
  }
  return null;
}

/* ---- the tests ---- */
export function readTests(json) {
  const j = obj(json);
  const list = j && Array.isArray(j.tests) ? j.tests : [];
  const seen = new Set();
  const out = [];
  for (const raw of list) {
    const t = obj(raw);
    if (!t) continue;
    const id = str(t.id), question = str(t.question), kind = str(t.kind);
    if (!id || !question || !KINDS.includes(kind) || seen.has(id)) continue;
    const pilot = str(t.pilot) && Object.prototype.hasOwnProperty.call(NAMES, t.pilot.trim()) ? t.pilot.trim() : DEFAULT_PILOT;
    seen.add(id);
    out.push({ id, label: str(t.label) || null, question, shows: str(t.shows), kind, pilot,
      key: str(t.key) && KEY_RE.test(t.key.trim()) ? t.key.trim() : null, response: obj(t.response) });
    if (out.length === MAX_TESTS) break;
  }
  return out;
}

/* what "Run it" does in this mode; null when the card cannot run (it is then not drawn) */
export function actionFor(test, mode) {
  const t = obj(test);
  if (!t || !str(t.question)) return null;
  const pilot = t.pilot || DEFAULT_PILOT;
  if (mode === "live") return { type: "live", question: t.question, pilot };
  if (t.kind === "run") return t.key ? { type: "load", key: t.key, pilot } : null;
  return stopOf(t.response) ? { type: "inline" } : null;
}

/* the saved run's file on a static site, next to the page's own runs/<investor>.json */
export const runPath = (key) => (typeof key === "string" && KEY_RE.test(key) ? `runs/${key}.json` : null);

/* ---- a recorded refusal or question back ---- */
const tool = (row) => (obj(row) && typeof row.tool === "string" ? row.tool : "");
export function stopOf(response) {
  const r = obj(response);
  if (!r || (r.status !== "blocked" && r.status !== "clarify")) return null;
  const text = answerText(r.message);
  if (!text) return null;
  if (r.status === "clarify") return { kind: "clarify", by: "model", glyph: "disc", badge: "The AI reader asked one question back.", text };
  const g = obj(obj(r.guardrail) && r.guardrail.input);
  const rows = Array.isArray(r.trace) ? r.trace : [];
  if (g && g.blocked === true) {
    return { kind: "blocked", by: "guardrails", glyph: "diamond", badge: "Amazon Bedrock Guardrails stopped it. No model saw the question.", text };
  }
  if (rows.some((row) => tool(row) === "advice_guard.screen")) {
    return { kind: "blocked", by: "advice", glyph: "square", badge: "The advice check (code) stopped it. No model saw the question.", text };
  }
  return { kind: "blocked", by: null, glyph: "square", badge: "The safety check stopped it. No model saw the question.", text };
}

/* the API's sentence without the disclaimer paragraph it ends with (the page's footer keeps that line), straight quotes curled */
export function answerText(message) {
  const m = str(message);
  if (!m) return null;
  const body = m.split(/\n\s*\n/).map((p) => p.trim()).filter((p) => p && p !== DISCLAIMER).join(" ");
  return body ? curl(body) : null;
}
export const curl = (s) => String(s).replace(/(^|[\s(\[:])"/g, "$1“").replace(/"/g, "”")
  .replace(/(\w)'(\w)/g, "$1’$2");

/* a recorded line as a sentence: R28's plain words (meaning.plain: the AI reader, not the navigator), a capital, a full stop */
export function sentence(text) {
  const t = str(text);
  if (!t) return null;
  const p = plain(t);
  const c = p.charAt(0).toUpperCase() + p.slice(1);
  return curl(/[.!?\u2026]$/.test(c) ? c : `${c}.`);
}

/* the question in typographic quotes (R18), whatever quotes it arrived with */
export function quoted(q) {
  const s = str(q);
  return s ? `“${curl(s.replace(/^["“”]+|["“”]+$/g, ""))}”` : "";
}

/* ---- one card ---- */
export function cardView(test, mode) {
  const t = obj(test) || {};
  const pilot = t.pilot || DEFAULT_PILOT;
  const label = t.label ? curl(plain(t.label)) : null;
  const act = actionFor(t, mode);
  const stop = mode === "live" ? null : stopOf(t.response);
  return {
    id: t.id, kind: t.kind, pilot, label, investor: NAMES[pilot] || null,
    question: quoted(t.question), shows: sentence(t.shows), action: act ? act.type : null,
    button: { text: "Run it", label: `Run it: ${label || quoted(t.question)}` },
    answer: act && act.type === "inline" ? stop : null,
    back: BACK[pilot] || "Back to the investor’s own question",
  };
}

/* the line a card shows once its run is on the stage (past tense; the years come from the run, lib/how.js's qualifier) */
export function playingLine(type, qualifier) {
  const q = str(qualifier) || "in this replay";
  if (type === "live-stop") return "Sent to the live app. Its answer shows in the stage above.";   // a refusal or a question back: no replay
  return type === "live" ? `Sent to the live app. It runs in the stage above, ${q}.` : `It played in the stage above, ${q}.`;
}
export const LOAD_FAILED = "This recorded run could not be loaded. Reload the page, then press Run it again.";

/* R22: the figures a card shows (its question, its line, the recorded answer and its date) */
export function cardFigures(view, extra) {
  const v = obj(view) || {};
  const parts = [v.question, v.shows, v.answer && v.answer.text, v.answer && v.answer.badge, extra];
  return parts.reduce((n, s) => n + (s ? countFigures(s) : 0), 0);
}

/* ---- the bench's layout: n cards in two full rows on the 12 columns (the first row takes the extra one), each card's span ---- */
export function spans(n) {
  const k = Math.max(0, Math.floor(Number(n) || 0));
  if (!k) return [];
  const a = k <= 3 ? k : Math.ceil(k / 2), b = k - a;
  if (12 % a || (b && 12 % b)) return Array(k).fill(4);              // no clean split: three a row
  return [...Array(a).fill(12 / a), ...Array(b).fill(b ? 12 / b : 0)];
}

/* ---- the popover ---- */
/* the replay's own length, from the stage's timeline (lib/replay.js): never a typed number */
export function replaySeconds() {
  const t = schedule({});
  return t && Number.isFinite(t.end) ? Math.max(1, Math.round(t.end / 1000)) : null;
}

export const JUDGE_LABEL = "Judging? Start here";
export const JUDGE_SHORT = "Judging?";
export const JUDGE_TITLE = "Three things to try";
export const NOTE_STATIC = "To type your own questions, use the live app (password in the submission form).";
export const NOTE_LIVE = "This is the live app: type your own question in the question box.";

export function judgeSteps(o) {
  const x = obj(o) || {};
  const secs = Number.isFinite(x.seconds) ? x.seconds : replaySeconds();
  const steps = [{ id: "replay", text: `Press Replay${secs ? ` (${secs} s)` : ""}.`, target: "replay" }];
  if (x.tests > 0) steps.push({ id: "tests", text: `Try to trip up the AI (${countWord(x.tests).toLowerCase()} questions).`, target: "testai" });
  steps.push({ id: "numbers", text: "Check any number (click it).", target: x.numbers || "why" });
  return { title: steps.length === 3 ? JUDGE_TITLE : `${countWord(steps.length)} things to try`,
    steps: steps.map((s, i) => ({ ...s, n: i + 1 })), note: x.mode === "live" ? NOTE_LIVE : NOTE_STATIC };
}

/* the popover's keys: Esc closes it (focus goes back to the button); nothing else is taken from the page */
export function keyAction(key, open) {
  return open && (key === "Escape" || key === "Esc") ? "close" : null;
}
