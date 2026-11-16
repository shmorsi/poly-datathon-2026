/* "Watch the AI work" (lane agentlog, ruling R42; the participants' deck slide 5 "What agentic means", the technical workshop
   levels 5-10): the run's own trace as a mission log in plain words. Pure: no DOM, no network, no clock.
   Every row is read from the Result the page already holds (trace, scenario, receipt, guardrail, navigator_effect, checks); a key
   that is absent hides its row, never a guessed one. Every number is the run's own: a trace row's ms, a count of the run's own
   rows, a receipt tally, a Guardrails score. The browser judges nothing (pitfall 5). PF (web/lib.js) is read at call time.
   A row: {id, part, step, actor, status, text, items, quote, sub, ms, time}
     part   "read" (OBSERVE + UNDERSTAND) | "compare" (COMPARE) | "explain" (EXPLAIN + VERIFY) | "after" (the drawer only)
     actor  "guard" (Amazon Bedrock Guardrails) | "ai" (Claude on Amazon Bedrock) | "code" (Python, no model)
     status "done" | "caught" (a defect named) | "blocked" | "refused" | "asked" | "none" (nothing found, said so) | "error" */
import { smart, modelName, stepRows, FAMILY } from "./replay.js";

const isNum = (x) => typeof x === "number" && Number.isFinite(x);
const arr = (x) => (Array.isArray(x) ? x : []);
const obj = (x) => (x && typeof x === "object" && !Array.isArray(x) ? x : null);
const str = (x) => (typeof x === "string" && x.trim() ? x.trim() : null);
const PFx = () => (typeof globalThis !== "undefined" && globalThis.PF) || null;
const NB = " ";
const plural = (n, one, many) => (n === 1 ? one : many || one + "s");
const WORDS_N = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const times = (n) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);

/* agents/scenario.py LOOP_MAX_DECISIONS (= config.SCENARIO_MAX_TURNS): the cap of the "loop" engine, where the model picks
   each tool. The "converse" engine (the saved runs) makes exactly one model call over tool outputs code computed first. */
export const LOOP_CAP = 4;
export const ACTOR = { ai: "AI", code: "Code", guard: "Guardrails" };
const NOUN = { tariffs: "tariff war", war_oil: "war and oil", chips: "chip war", rates: "rate shock" };
/* agents/memory.py DEFECT_TYPES in plain words (static text, never words from a run) */
const DEFECT_WORDS = {
  unverified_number: "a number not found in the facts", wrong_entity: "a number that did not say what it measures",
  wrong_kind: "a fact and an assumption mixed up", wrong_side: "today and after the move crossed",
  wrong_direction: "a fall written as a rise", advice: "advice words", future_date: "something dated after the decision",
  spelled_number: "a number written in words", unknown_ref: "a reference to a fact that does not exist",
  verdict_words: "the verdict not in its exact words", missing_failed_limit: "a broken limit left out",
  missing_caveat_phrase: "a caveat left out", missing_section: "a question left unanswered",
  missing_limits_phrase: "the not-a-forecast line left out", too_long: "an explanation over its word budget",
};

/* a time as the log's readout prints it: under 1 ms, whole ms under 100 ms, else seconds with one decimal ("0.6 s") */
export function timeText(ms) {
  if (!isNum(ms) || ms < 0) return "";
  if (ms < 1) return `<1${NB}ms`;
  if (ms < 100) return `${Math.round(ms)}${NB}ms`;
  return `${(Math.round(ms / 100) / 10).toFixed(1)}${NB}s`;
}
/* the plain line for a defect type (the memory rows) */
export const defectWords = (types) => arr(types).map((t) => DEFECT_WORDS[t]).filter(Boolean);

const traceOf = (r) => arr(obj(r) && r.trace).map(obj).filter(Boolean);
const tool = (t) => String(t.tool || "");
function row(id, part, step, actor, text, more) {
  const o = { id, part, step, actor, status: "done", text: smart(text), items: null, quote: null, sub: null, ms: null, ...more };
  o.line = smart(o.line || text);              // the run screen's one-line form
  o.time = timeText(o.ms);
  if (o.quote) o.quote = (Array.isArray(o.quote) ? o.quote : [o.quote]).map(str).filter(Boolean).map((q) => smart(q));
  if (o.sub) o.sub = smart(o.sub);
  if (o.items) o.items = o.items.map((it) => ({ label: smart(it.label), text: smart(it.text) }));
  return o;
}
function cleanReason(label, why) {           // "War & oil: no words in your question point to it; best score 0.20." -> the reason
  let t = String(why || "").trim();
  if (label && t.toLowerCase().startsWith(label.toLowerCase() + ":")) t = t.slice(label.length + 1).trim();
  return t.replace(/;\s*best score[^;]*$/i, "").replace(/\.$/, "").trim();
}
function moveText(r, sc) {                   // "NVIDIA → 40 %" (the stage's chip words), from the Result only
  const PF = PFx(), mv = PF && typeof PF.moveOf === "function" ? PF.moveOf(r) : null;
  const ch = obj(sc.change);
  if (!mv && !ch) return null;
  const name = mv ? mv.name : str(ch.ticker), w = mv ? mv.weight : ch.weight;
  const share = PF && isNum(w) ? PF.fmt.share(w) : null;
  if (!name) return null;
  if (ch && str(ch.op) === "replace" && str(ch.from_ticker)) return `${ch.from_ticker} → ${name}`;
  return share ? `${name} → ${share}` : name;
}
const readFrom = (r, sc) => {                // scenario.read_from, shown only when it stands in the question as written
  const said = str(sc.read_from), q = str(r.question);
  return said && q && q.toLowerCase().includes(said.toLowerCase()) ? said : null;
};
const famLabel = (f) => FAMILY[f] || null;
const reasonIn = (s) => { const m = /\(([^()]{6,})\)/.exec(String(s || "")); return m ? m[1] : null; };

/* ---- OBSERVE + UNDERSTAND ---- */
function readRows(r, tr, rows) {
  const sc = obj(r.scenario) || {};
  const gRow = tr.find((t) => /^guardrail\.apply_guardrail\(INPUT\)/.test(tool(t)));
  const gIn = obj(obj(r.guardrail) && r.guardrail.input);
  if (gRow || gIn) {
    const out = obj(gRow && gRow.outputs) || {};
    const blocked = out.blocked === true || (!!gIn && gIn.blocked === true);
    const failed = !blocked && !!(out.error || (gIn && gIn.error));
    const ms = gRow && isNum(gRow.ms) ? gRow.ms : gIn && isNum(gIn.latency_ms) ? gIn.latency_ms : null;
    rows.push(row("guard-in", "read", "OBSERVE", "guard", blocked ? "Guardrails stopped your question: nothing was sent to a model."
      : failed ? "Guardrails could not check your question this time." : "Guardrails checked your question: passed.",
    { status: blocked ? "blocked" : failed ? "error" : "done", ms, line: blocked ? "Guardrails stopped your question" : failed ? "Guardrails could not check your question" : "Guardrails checked your question: passed" }));
  }
  if (r.status === "blocked" && !(rows.length && rows[rows.length - 1].status === "blocked"))
    rows.push(row("stop", "read", "OBSERVE", "code", "Code stopped the run before any model read your question.", { status: "blocked", quote: str(r.message) }));

  /* the searches: who chose them is the Result's own word (tool_calls[].chosen_by) */
  const calls = arr(sc.tool_calls).map(obj).filter(Boolean);
  const searches = calls.filter((c) => c.tool === "search_events"), expo = calls.find((c) => c.tool === "get_exposure");
  if (searches.length || expo) {
    const byModel = calls.every((c) => c.chosen_by === "model");
    const fams = searches.map((c) => obj(c.args) && str(c.args.family)).filter(Boolean);
    const each = searches.length > 1 && fams.length === searches.length && new Set(fams).size === fams.length;
    const who = byModel ? "The AI reader" : "Code";
    const did = [searches.length ? `searched the shock record ${times(searches.length)}${each ? ", one kind of shock each" : ""}` : null,
      expo ? "checked where your money is" : null].filter(Boolean).join(each ? ", and " : " and ");
    const items = searches.map((c) => ({ label: famLabel(obj(c.args) && c.args.family) || "Every kind of shock",
      text: c.error ? `not run: ${String(c.error).replace(/\.$/, "")}` : isNum(c.rows) ? `${c.rows} found` : "searched" }));
    rows.push(row("search", "read", "UNDERSTAND", byModel ? "ai" : "code", `${who} ${did}.`, {
      items: items.length ? items : null, ms: calls.reduce((a, c) => a + (isNum(c.ms) ? c.ms : 0), 0),
      sub: byModel ? null : "Code ran these searches itself and handed the results to the AI reader.",
      line: `${who} searched the shock record ${times(searches.length)}` }));
  }

  /* the AI's decision: only when a trace row or a model call proves a model answered (R15) */
  const mc = arr(sc.model_calls).map(obj).filter(Boolean);
  const turn = tr.find((t) => tool(t) === "navigator.model_turn");
  const used = sc.method === "bedrock";
  const fams = arr(sc.families).filter((f) => FAMILY[f]), ids = arr(sc.event_ids).filter((x) => typeof x === "string");
  if (mc.length || turn) {
    const ms = turn && isNum(turn.ms) ? turn.ms : mc.reduce((a, c) => a + (isNum(c.latency_ms) ? c.latency_ms : 0), 0) || null;
    const model = modelName((turn && turn.model) || (mc[0] && mc[0].model_id));
    const rid = str((turn && turn.request_id) || (mc[0] && mc[0].request_id));
    const sub = [model && `${model} on Amazon Bedrock`, rid && `request ${rid.slice(0, 8)}`].filter(Boolean).join(", ") || null;
    const abstained = used && !fams.length && !ids.length && obj(sc.weather) && sc.weather.no_precedent === true;
    if (used && str(sc.clarify)) rows.push(row("decide", "read", "UNDERSTAND", "ai", "The AI reader asked you one question instead of guessing:", { status: "asked", quote: sc.clarify, ms, sub }));
    else if (abstained) rows.push(row("decide", "read", "UNDERSTAND", "ai", "The AI reader found no close precedent at this date and said so, instead of picking one.", { status: "none", ms, sub }));
    else if (used) {
      const from = readFrom(r, sc), mv = moveText(r, sc);
      const items = [mv && { label: "The move", text: mv },
        fams.length ? { label: "The shock", text: fams.map((f) => NOUN[f]).join(" and ") + (from ? `, from your words “${from}”` : "") } : null,
        ids.length ? { label: "Precedents", text: `the ${ids.length === 1 ? "closest one" : `${ids.length} closest`} on record` } : null].filter(Boolean);
      rows.push(row("decide", "read", "UNDERSTAND", "ai", `The AI reader read your words and decided${items.length ? ":" : "."}`, { items: items.length ? items : null, ms, sub,
        line: `The AI reader decided: ${[mv, fams.map((f) => NOUN[f]).join(" and ")].filter(Boolean).join(", ") || "the plan"}` }));
    } else rows.push(row("decide", "read", "UNDERSTAND", "ai", "The AI reader answered.", { ms, sub }));
  } else if (sc.method === "fallback") {
    rows.push(row("decide", "read", "UNDERSTAND", "code", "No model read this question: the keyword rules read your words.", { status: "done" }));
  }

  /* code checked the plan: what it kept, what it set aside and why (scenario.rejected, written by code from its own searches) */
  if (sc.method === "fallback" && str(sc.fallback_reason) && (mc.length || turn)) {
    rows.push(row("plan", "read", "UNDERSTAND", "code", "Code refused the AI’s plan, and the keyword rules answered:", {
      status: "refused", quote: reasonIn(sc.fallback_reason) || sc.fallback_reason }));
  } else if (used && !str(sc.clarify)) {
    const kept = [obj(sc.change) ? "the move" : null, fams.length ? `the ${fams.map((f) => NOUN[f]).join(" and ")}` : null,
      ids.length ? `${ids.length} ${plural(ids.length, "precedent")}` : null].filter(Boolean);
    const rej = Object.entries(obj(sc.rejected) || {}).filter(([f]) => FAMILY[f]).map(([f, why]) => ({ label: FAMILY[f], reason: cleanReason(FAMILY[f], why) }));
    const same = rej.length > 1 && rej.every((x) => x.reason === rej[0].reason);
    const items = same ? [{ label: "Set aside", text: `${rej.map((x) => x.label).join(", ")}: ${rej[0].reason.replace(/\bpoint to it$/, "point to them")}` }]
      : rej.map((x, i) => ({ label: i ? "" : "Set aside", text: `${x.label}: ${x.reason}` }));
    if (str(sc.widened)) items.push({ label: "Widened", text: sc.widened });
    const kept_ = kept.length ? `kept ${kept.length > 1 ? kept.slice(0, -1).join(", ") + " and " + kept[kept.length - 1] : kept[0]}` : null;
    const set = rej.length ? `set aside ${WORDS_N[rej.length] || rej.length} ${plural(rej.length, "kind")} of shock` : null;
    rows.push(row("plan", "read", "UNDERSTAND", "code", `Code checked every field of the plan against your words and its own searches${kept_ || set ? ": " + [kept_, set].filter(Boolean).join("; ") : ""}.`, {
      items: items.length ? items : null, line: `Code checked the plan${set ? `: ${set}` : ""}` }));
  }
}

/* ---- COMPARE: one line, the replay and the checks (the verdict is code's) ---- */
function compareRows(r, tr, rows) {
  const st = stepRows(r).find((s) => s.step === "COMPARE");
  const checks = arr(r.checks).map(obj).filter(Boolean);
  if (!st || st.status !== "done" || !checks.length) return;
  const stress = checks.find((c) => c.rule === "scenario_stress");
  const fam = stress && str(stress.family) && NOUN[stress.family];
  const sub = stress && isNum(stress.n_episodes) && fam
    ? `The shock check replayed the ${stress.n_episodes} earlier ${fam} ${plural(stress.n_episodes, "episode")} on record. The verdict comes from code, never from the AI.`
    : "The verdict comes from code, never from the AI.";
  rows.push(row("replay", "compare", "COMPARE", "code", `Code replayed the move day by day and ran ${checks.length} ${plural(checks.length, "check")} against your limits.`, { ms: st.ms, sub,
    line: `Code replayed the move: ${checks.length} ${plural(checks.length, "check")} against your limits` }));
}

/* ---- EXPLAIN + VERIFY: draft 1, the named defect, the re-ask, the number check, Guardrails, the memory ---- */
function explainRows(r, tr, rows) {
  const rc = obj(r.receipt), ft = rc && obj(rc.first_try);
  const drafts = tr.filter((t) => tool(t) === "explain.draft");
  const checksR = tr.filter((t) => tool(t) === "verify.receipt");
  const load = tr.find((t) => tool(t) === "agents.memory.load"), rec = tr.find((t) => tool(t) === "agents.memory.record");
  const loaded = defectWords(obj(load && load.outputs) && load.outputs.types);
  if (loaded.length) rows.push(row("memory-in", "explain", "EXPLAIN", "code",
    `Code reminded the AI of ${loaded.length === 1 ? "a mistake" : "mistakes"} earlier runs made: ${loaded.join("; ")}.`, {}));
  const d1 = drafts[0];
  if (d1) {
    const facts = obj(d1.inputs) && isNum(d1.inputs.facts) ? d1.inputs.facts : null;
    rows.push(row("draft1", "explain", "EXPLAIN", "ai", `The AI wrote the explanation${facts ? ` from ${facts} computed facts` : ""}${drafts.length > 1 ? " (draft 1)" : ""}.`, {
      ms: isNum(d1.ms) ? d1.ms : null, sub: modelName(d1.model) ? `${modelName(d1.model)} on Amazon Bedrock` : null,
      line: `The AI wrote the explanation${drafts.length > 1 ? " (draft 1)" : ""}` }));
  }
  /* the self-correction (workshop levels 9-10): the defects code named, as the re-ask carried them (else the first try's) */
  const d2 = drafts[1];
  const named = arr(obj(d2 && d2.inputs) && d2.inputs.retry_numbers).map(str).filter(Boolean);
  const ftDefects = arr(ft && ft.defects).map(str).filter(Boolean);
  const defects = named.length ? named : ftDefects;
  if (defects.length && (d2 || ftDefects.length)) {
    const byReceipt = ftDefects.length && defects.every((d) => ftDefects.includes(d));
    const tally = byReceipt && isNum(ft.verified) && isNum(ft.total) ? ` (${ft.verified} of ${ft.total} numbers traced)` : "";
    const k = defects.length;
    rows.push(row("caught", "explain", "VERIFY", "code", `${byReceipt ? "The number check" : "Code’s checks"} caught ${WORDS_N[k] && k < 11 ? WORDS_N[k] : k} ${plural(k, "defect")} in draft 1${tally}. Code told the AI exactly what was wrong:`, {
      status: "caught", quote: defects.slice(0, 3), ms: checksR[0] && isNum(checksR[0].ms) ? checksR[0].ms : null,
      line: `${byReceipt ? "The number check" : "Code’s checks"} caught ${k === 1 ? "a defect" : `${k} defects`} in draft 1` }));
  }
  if (d2) rows.push(row("draft2", "explain", "EXPLAIN", "ai", defects.length ? "The AI rewrote the explanation with that one message (draft 2)." : "The AI wrote a second draft.", {
    ms: isNum(d2.ms) ? d2.ms : null, line: defects.length ? "The AI rewrote it with code’s note (draft 2)" : "The AI wrote a second draft" }));
  if (rc && isNum(rc.verified) && isNum(rc.total) && rc.total > 0) {
    const n = isNum(rc.drafts) ? rc.drafts : drafts.length || 1, all = rc.verified === rc.total;
    const last = checksR[checksR.length - 1];
    rows.push(row("check", "explain", "VERIFY", "code", all
      ? (n > 1 ? `The number check passed draft ${n}: ${rc.verified} of ${rc.total} numbers traced to the data.` : `The number check traced ${rc.verified} of ${rc.total} numbers to the data, on the first draft.`)
      : `The number check traced ${rc.verified} of ${rc.total} numbers to the data.`, { status: all ? "done" : "caught", ms: last && isNum(last.ms) ? last.ms : null,
      line: `${n > 1 && all ? `Draft ${n} passed: ` : ""}${rc.verified} of ${rc.total} numbers traced to the data` }));
  }
  const gOut = obj(obj(r.guardrail) && r.guardrail.output), gr = gOut && obj(gOut.grounding);
  const gRow = tr.find((t) => tool(t) === "guardrail.output");
  if (gr && isNum(gr.score) && isNum(gr.threshold)) {
    const low = gr.detected === true || gr.score < gr.threshold;
    rows.push(row("guard-out", "explain", "VERIFY", "guard", `Guardrails checked the explanation against the facts: grounding ${gr.score.toFixed(2)}, ${low ? "under" : "above"} the ${gr.threshold.toFixed(2)} bar.`, {
      status: low || gOut.blocked === true ? "caught" : "done", ms: gRow && isNum(gRow.ms) ? gRow.ms : isNum(gOut.latency_ms) ? gOut.latency_ms : null,
      line: `Guardrails: grounding ${gr.score.toFixed(2)}, ${low ? "under" : "above"} the ${gr.threshold.toFixed(2)} bar` }));
  }
  const saved = defectWords(obj(rec && rec.outputs) && rec.outputs.types);
  if (saved.length) rows.push(row("memory-out", "explain", "VERIFY", "code", `Code saved this run’s ${saved.length === 1 ? "mistake" : "mistakes"} for the next run’s prompt: ${saved.join("; ")}.`, {
    line: `Code saved the ${saved.length === 1 ? "mistake" : "mistakes"} for the next run` }));
}

/* ---- the drawer's closing row: what the AI changed here (R37: the question answered, never the verdict unless the run says so) */
function effectRow(r, rows) {
  const ne = obj(r.navigator_effect);
  const said = ne && str(ne.sentence);                     // code's own R37 sentence, unless a key it reads was missing
  if (said && !/\b(None|null|undefined|NaN)\b|\s{2}/.test(said)) { rows.push(row("effect", "after", "COMPARE", "code", said, {})); return; }
  if (!ne || ne.same === true || !str(ne.verdict) || !str(ne.verdict_without)) return;
  const d = arr(ne.diffs).map(obj).find((x) => x && x.what === "families");
  if (!d) return;
  const nav = arr(d.navigator).filter((f) => NOUN[f]), kw = arr(d.fallback).filter((f) => NOUN[f]);
  const asked = nav.length ? `the ${nav.map((f) => NOUN[f]).join(" and ")} you asked about` : "the shock you asked about";
  const instead = kw.length ? `the keyword rules would have read the ${kw.map((f) => NOUN[f]).join(" and ")} instead of ${asked}`
    : `the keyword rules read no shock in your words, so the shock check would have replayed every kind of shock instead of ${asked}`;
  const same = ne.verdict === ne.verdict_without;
  rows.push(row("effect", "after", "COMPARE", "code", `Without the AI reader, ${instead}. ${same ? "The verdict would have been the same: the AI changed the question answered, not the answer." : "The verdict would have been different."}`, {}));
}

/* the whole log of one run, or null when the Result carries no trace */
export function logOf(r) {
  r = obj(r);
  const tr = traceOf(r);
  if (!r || !tr.length) return null;
  const rows = [];
  readRows(r, tr, rows);
  if (r.status !== "blocked" && r.status !== "clarify") { compareRows(r, tr, rows); explainRows(r, tr, rows); }
  effectRow(r, rows);
  const steps = stepRows(r).filter((s) => s.status === "done");
  const total = steps.length ? steps.reduce((a, s) => a + (isNum(s.ms) ? s.ms : 0), 0) : null;
  return { rows, loop: loopOf(r), total, totalText: timeText(total), model: modelOf(tr), recorded: recordedText(r), fold: foldLine(rows, r) };
}
const modelOf = (tr) => { const t = tr.find((x) => x.service === "Amazon Bedrock" && str(x.model)); return t ? modelName(t.model) : null; };
function recordedText(r) {
  const PF = PFx(), d = str(r.recorded_at);
  return d && PF && PF.fmt && typeof PF.fmt.date === "function" && PF.fmt.date(d) ? `Recorded on ${PF.fmt.date(d)}` : null;
}

/* "the code held the loop" (workshop level 8): the model's decisions against the engine's own cap */
export function loopOf(r) {
  const sc = obj(obj(r) && r.scenario);
  if (!sc || !isNum(sc.decisions)) return null;
  const n = sc.decisions, calls = arr(sc.tool_calls).map(obj).filter(Boolean);
  const byCode = calls.filter((c) => c.chosen_by !== "model").length, byModel = calls.length - byCode;
  if (sc.engine === "loop") return { engine: "loop", decisions: n, cap: LOOP_CAP, slots: LOOP_CAP,
    text: `The code held the loop: ${n} of ${LOOP_CAP} AI decisions used; code ran each of the ${calls.length} tool ${plural(calls.length, "call")} the AI asked for.` };
  if (!n) return { engine: str(sc.engine), decisions: 0, cap: null, slots: 0, text: "No AI decision in this run: the keyword rules read your words." };
  return { engine: str(sc.engine) || "converse", decisions: n, cap: 1, slots: 1,
    text: `The code held the loop: ${n === 1 ? "one AI decision, in one call" : `${n} AI decisions`}; code ${byModel ? "ran" : "chose and ran"} ${calls.length === 1 ? "the one tool call" : calls.length === 2 ? "both tool calls" : `all ${calls.length} tool calls`} and checked the answer.` };
}

/* the one line the stage rests on (R22: one line once the verdict has landed) */
export function foldLine(rows, r) {
  const caught = arr(rows).find((x) => x.id === "caught"), check = arr(rows).find((x) => x.id === "check");
  const sc = obj(obj(r) && r.scenario) || {};
  const n = isNum(sc.decisions) ? sc.decisions : null;
  const first = n === null ? null : n === 0 ? "No AI decision; the keyword rules read your words" : `${WORDS_N[n] && n < 11 ? cap(WORDS_N[n]) : n} AI ${plural(n, "decision")}, checked by code`;
  const rcv = obj(obj(r) && r.receipt);
  const second = caught && check && check.status === "done" ? "a defect caught and fixed"
    : rcv && isNum(rcv.verified) && isNum(rcv.total) && rcv.total ? `${rcv.verified} of ${rcv.total} numbers checked` : null;
  return [first, second].filter(Boolean).join("; ") + (first || second ? "." : "") || null;
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

/* ---- the run screen's clocks ---- */
const HOLD = { caught: 1200, check: 900, "guard-out": 600, draft1: 500, draft2: 500, "memory-out": 500, "memory-in": 500 };
/* a saved run on a compressed clock, fitted to the stage's own schedule T (web/lib/replay.js schedule(): fly, lamp, end):
   OBSERVE + UNDERSTAND before the flight, COMPARE with it, EXPLAIN + VERIFY from the lamp, one row at a time */
export function scheduleOf(rows, T) {
  const t = obj(T) || {};
  const fly = isNum(t.fly) ? t.fly : 2200, lamp = isNum(t.lamp) ? t.lamp : 6720;
  const read = arr(rows).filter((x) => x.part === "read"), cmp = arr(rows).filter((x) => x.part === "compare"),
    exp = arr(rows).filter((x) => x.part === "explain");
  const at = {};
  const span = Math.max(600, fly - 320), gap = read.length > 1 ? Math.min(560, (span - 160) / (read.length - 1)) : 0;
  read.forEach((x, i) => { at[x.id] = Math.round(160 + i * gap); });
  cmp.forEach((x, i) => { at[x.id] = Math.round(fly + 120 + i * 400); });
  let t0 = lamp + 240, last = 560;               // one line at a time: the defect and its fix hold longest
  exp.forEach((x) => { at[x.id] = Math.round(t0); last = HOLD[x.id] || 560; t0 += last; });
  return { at, fold: fly + 60, end: Math.round(t0 + 240), tick: Math.min(560, Math.max(240, gap - 80)) };
}
/* the counter a row's time readout shows while it lands: p in [0, 1] -> the text, landing on the exact value at p = 1 */
export function tickText(ms, p) {
  if (!isNum(ms)) return "";
  const q = Math.max(0, Math.min(1, isNum(p) ? p : 1));
  if (q >= 1 || ms < 100) return timeText(ms);
  const e = 1 - Math.pow(1 - q, 3);
  return timeText(Math.max(100, ms * e));
}

/* a live run: the server's progress lines (store.steps, folded by web/lib/replay.js foldStep) as one row per step, on the real
   clock; the full rows replace them once the Result lands */
const LIVE = {
  OBSERVE: ["guard", "Guardrails are checking your question", "Guardrails checked your question"],
  UNDERSTAND: ["ai", "The AI reader is reading your words", "The AI reader read your words"],
  COMPARE: ["code", "Code is replaying the move against your limits", "Code replayed the move against your limits"],
  EXPLAIN: ["ai", "The AI is writing the explanation", "The AI wrote the explanation"],
  VERIFY: ["code", "The number check is tracing every number", "The number check traced every number"],
};
export function liveRows(steps) {
  return arr(steps).map(obj).filter((s) => s && LIVE[s.step] && s.status && s.status !== "waiting").map((s) => {
    const [actor, running, done] = LIVE[s.step];
    const status = s.status === "running" ? "running" : s.status === "error" ? "error" : s.status === "skipped" ? "skipped" : "done";
    const text = status === "running" ? running + "…" : status === "skipped" ? `${done.replace(/^(\S+ \S+).*/, "$1")}: not run in this run.` : done + ".";
    return { id: "live-" + s.step, part: s.step === "COMPARE" ? "compare" : s.step === "EXPLAIN" || s.step === "VERIFY" ? "explain" : "read",
      step: s.step, actor, status, text, items: null, quote: null, sub: null, ms: status === "done" && isNum(s.ms) ? s.ms : null,
      time: status === "done" && isNum(s.ms) ? timeText(s.ms) : "" };
  });
}
