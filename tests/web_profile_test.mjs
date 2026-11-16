// Lane profile-ui: the fifth investor, "You" (R46, R49). The pure helpers of web/lib/you.js on committed fixtures only (R17):
// three answers of POST /api/profile/read in lane profile-ai's shape (tests/fixtures/web/profile_read_{ok,clarify,none}.json).
// The card from a fixture answer, the "from your words" and "assumed" labels, the clarify path, the static fallback, the request
// bodies (the read and the run), lane hold's limits card, and the plain-words gate (no advice word, no " · " string).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as Y from "../web/lib/you.js";
import { adviceHits, metaHits } from "../scripts/gate_rules.mjs";

const fx = (name) => JSON.parse(readFileSync(new URL(`./fixtures/web/profile_read_${name}.json`, import.meta.url), "utf8"));
const robert = JSON.parse(readFileSync(new URL("./fixtures/web/robert.json", import.meta.url), "utf8"));
let n = 0;
const t = (name, fn) => { try { fn(); } catch (e) { e.message = `${name}: ${e.message}`; throw e; } n += 1; };
const you = (name, extra) => ({ text: "words", read: Y.readOf(fx(name)), edits: {}, edited: [], ...(extra || {}) });
const row = (m, key) => m.rows.find((r) => r.key === key);
const item = (m, key) => m.rows.flatMap((r) => r.items).find((i) => i.key === key);
const figures = (s) => (String(s).match(/\d[\d,.]*/g) || []).length;

t("the read request: the words, trimmed to one line, capped at the reader's own limit; nothing for empty words", () => {
  assert.deepEqual(Y.readBody("  I'm 34,\n saving   for a home. "), { text: "I'm 34, saving for a home." });
  assert.equal(Y.readBody("   "), null);
  assert.equal(Y.readBody(null), null);
  assert.equal(Y.readBody("x".repeat(3000)).text.length, Y.MAX_TEXT);
});

t("the card from the ok answer: plain rows, each with where it came from", () => {
  const m = Y.cardModel(you("ok"));
  assert.deepEqual(m.rows.map((r) => r.label), ["Age", "Money", "What it is for", "When you need it", "Ups and downs you accept", "Your values"]);
  assert.equal(item(m, "age").text, "45");
  assert.equal(item(m, "amount").text, "$200,000");
  assert.equal(item(m, "horizon_years").text, "In about eight years", "the horizon in words, not a figure (R22)");
  assert.equal(item(m, "goal").text, "Growth with some stability");
  assert.equal(row(m, "reaction_2022"), undefined, "a field the words never gave and the reader never assumes is not shown");
  assert.deepEqual(row(m, "values").items.map((i) => i.text),
    ["No crypto", "No Energy companies", "Values screen: on"]);
  assert.equal(m.clarify, null);
  assert.equal(m.canRun, true);
});

t("from your words vs assumed: the words' fields carry the exact words; the assumed ones are editable", () => {
  const m = Y.cardModel(you("ok"));
  for (const k of ["age", "amount", "horizon_years", "crypto", "sector_caps.Energy", "esg"]) assert.equal(item(m, k).source, "words", k);
  assert.equal(item(m, "age").words, "I'm 45");
  assert.equal(item(m, "sector_caps.Energy").words, "No oil companies");
  for (const k of ["goal", "risk"]) { assert.equal(item(m, k).source, "assumed", k); assert.ok(item(m, k).edit, `${k} editable`); }
  assert.equal(Y.FROM_WORDS, "from your words");
  assert.equal(Y.ASSUMED, "assumed");
  /* an edit on the card: the value changes and its tag becomes "set by you" */
  const y = you("ok", { edits: { goal: Y.editValue("goal", "growth") }, edited: ["goal"] });
  const e = Y.cardModel(y);
  assert.equal(item(e, "goal").text, "Growing it over the long run");
  assert.equal(item(e, "goal").source, "you");
  assert.equal(Y.editValue("horizon_years", "12"), 12);
  assert.equal(Y.editValue("horizon_years", "99"), null);
  assert.equal(Y.editValue("risk", "wild"), null);
  assert.equal(Y.editValue("crypto", "yes"), true);
});

t("a conflict is never silent: a value you set over your words shows one amber line and the way back (LIMITS_MODEL)", () => {
  const y = you("ok", { edits: { esg: false }, edited: ["esg"] });
  const m = Y.cardModel(y);
  assert.deepEqual(m.conflicts.map((c) => c.line), ["You said you care about ESG; you switched the values screen off. The replay uses your switch."]);
  assert.equal(Y.USE_WORDS, "Use my words instead");
  assert.equal(item(m, "esg").text, "Values screen: off");
  assert.equal(item(m, "esg").source, "you");
  assert.equal(Y.withYou({ question: "q" }, { investor: "you", you: y }).profile.esg, false, "the replay uses your switch");
  const c2 = Y.conflicts(you("ok", { edits: { crypto: true, horizon_years: 3 }, edited: ["crypto", "horizon_years"] }));
  assert.deepEqual(c2.map((c) => c.line), ["You said no crypto; you allowed crypto. The replay uses your choice.",
    "You said \u201cin 8 years\u201d; you chose \u201cIn about three years\u201d. The replay uses your choice."]);
  assert.deepEqual(Y.cardModel(you("ok", { edits: { goal: "growth" }, edited: ["goal"] })).conflicts, [], "an assumed field you change is no conflict");
  assert.deepEqual(Y.cardModel(you("ok")).conflicts, []);
});

t("the card shows at most three figures (R22) and no advice word or meta string", () => {
  for (const name of ["ok", "clarify", "none"]) {
    const m = Y.cardModel(you(name));
    const shown = m.rows.flatMap((r) => [r.label, ...r.items.map((i) => i.text)]);
    assert.ok(shown.reduce((a, s) => a + figures(s), 0) <= 3, `${name}: ${shown.join(" | ")}`);
    for (const s of [...shown, Y.PROMPT, Y.EXAMPLE, Y.PRIVACY, Y.STATIC_LINE, Y.WAIT_LINE, ...Object.values(Y.REACTIONS), ...Object.values(Y.GOALS),
      ...Object.values(Y.RISKS), ...Object.values(Y.CRYPTO), ...Object.values(Y.ESG)]) {
      assert.deepEqual(adviceHits(s), [], s);
      assert.deepEqual(metaHits(s), [], s);
    }
  }
});

t("the clarify path: the one question inline, Replay waits, the answer goes back with the same words", () => {
  const y = you("clarify");
  const m = Y.cardModel(y);
  assert.equal(m.clarify, "How much money is this, in dollars, and how much of it could you afford to lose at most? You can also say you set no limit.");
  assert.equal(item(m, "amount"), undefined, "no amount yet: no Money row");
  assert.equal(Y.youGate({ investor: "you", mode: "live", you: y }, robert), "wait");
  assert.equal(Y.withAnswer("I'm 34 and want to grow my money over 15 years. No crypto.", "$60,000, and I could lose $9,000"),
    "I'm 34 and want to grow my money over 15 years. No crypto. $60,000, and I could lose $9,000");
  assert.equal(Y.withAnswer("no full stop", "yes"), "no full stop. yes");
  assert.equal(Y.withAnswer("words", "  "), "words");
});

t("the capacity question: no replay until it is answered, or skipped with a visible 'not set' (limits-QA case 3)", () => {
  const a = fx("ok");
  const open = { ...a, status: "clarify", can_run: true, profile: { ...a.profile, capacity: null },
    clarify: "How much of it could you afford to lose at most? You can also say you set no limit." };
  const y = { text: "w", read: Y.readOf(open), edits: {}, edited: [] };
  const holdings = { pilot: "you", portfolio: { ...Y.NEUTRAL }, amount: 200000 };
  assert.equal(Y.youGate({ investor: "you", mode: "live", you: y, holdings }, robert), "wait");
  assert.equal(Y.cardModel(y).clarify, open.clarify);
  const skipped = { ...y, skip: true };
  assert.equal(Y.youGate({ investor: "you", mode: "live", you: skipped, holdings }, robert), "run");
  const m = Y.cardModel(skipped);
  assert.equal(m.clarify, null, "the question folds once you skip it");
  assert.equal(item(m, "capacity").text, "Not set (no capacity line)");
  assert.equal(item(m, "capacity").source, "you");
  assert.equal(Y.SKIP_LABEL, "Replay without it");
});

t("words beat the reader's defaults, and the card says what they replaced (LIMITS_MODEL CONFLICTS)", () => {
  const m = Y.cardModel(you("ok"));
  assert.equal(item(m, "esg").beat, "default: off");
  assert.equal(item(m, "horizon_years").beat, "default: ten years");
  assert.equal(item(m, "crypto").beat, null, "no crypto is the default too: nothing replaced");
  assert.equal(item(m, "goal").beat, undefined, "an assumed field replaced nothing");
});

t("lane hold's limits card: what the words set, tagged, with the exact words; none when the words want no limits", () => {
  const li = Y.limitsInOf(you("ok"));
  assert.deepEqual(li.limits, { crypto: 0, sector_caps: { Energy: 0 } });
  assert.equal(li.capacity, 40000);
  assert.deepEqual(li.source, { crypto: "words", "sector_caps.Energy": "words", capacity: "words", esg: "words" });
  assert.equal(li.esg, true);
  assert.equal(li.words.esg, "No oil companies");
  const sw = Y.limitsInOf(you("ok", { edits: { esg: false, crypto: true }, edited: ["esg", "crypto"] }));
  assert.equal(sw.esg, false); assert.equal(sw.source.esg, "you");
  assert.equal(sw.limits.crypto, undefined, "your crypto choice replaces the words' cap");
  const body = Y.withYou({ question: "q" }, { investor: "you", you: you("ok", { edits: { crypto: true }, edited: ["crypto"] }) });
  assert.equal(body.limits.crypto, undefined); assert.equal(body.profile.crypto, true);
  assert.equal(li.words.capacity, "losing $40,000 at most");
  assert.equal(li.pilot, "you");
  assert.equal(li.none, false);
  const none = Y.limitsInOf(you("none"));
  assert.equal(none.none, true);
  assert.equal(none.words.none, "no limits");
  assert.deepEqual(none.limits, {});
});

t("the run body: the profile exactly as server.Profile, the amount, the limits as the reader gave them, the holdings", () => {
  const base = { portfolio: { "XIU.TO": 1 }, amount: 600000, pilot: "you", question: "What if I put 20 % in NVIDIA?", profile: { goal: "x" }, limits: null, redteam: false };
  const holdings = { pilot: "you", portfolio: { ...Y.NEUTRAL }, amount: 200000, assumed: true };
  const b = Y.withYou(base, { investor: "you", mode: "live", you: you("ok"), holdings });
  assert.equal(b.pilot, "you");
  assert.equal(b.question, base.question);
  assert.deepEqual(b.profile, { goal: "balance", horizon_years: 8, esg: true, crypto: false, risk: "moderate", capacity: 40000 });
  assert.equal(b.amount, 200000);
  assert.deepEqual(b.portfolio, Y.NEUTRAL);
  assert.deepEqual(b.limits, { crypto: 0, sector_caps: { Energy: 0 }, from_words: ["crypto", "sector_caps.Energy", "esg", "capacity", "horizon_years"] });
  assert.ok(!JSON.stringify(b.limits).includes("oil"), "never the investor's words inside the limits (they reach the navigator)");
  /* a field changed on the card leaves from_words */
  const e = Y.withYou(base, { investor: "you", you: you("ok", { edits: { esg: false }, edited: ["esg"] }), holdings });
  assert.equal(e.profile.esg, false);
  assert.ok(!e.limits.from_words.includes("esg"));
  /* no limits (R49): the profile stays, limits {none: true}; the edited holdings win over the neutral mix */
  const mine = { pilot: "you", portfolio: { SPY: 0.6, AGG: 0.4 }, amount: 50000 };
  const z = Y.withYou(base, { investor: "you", you: you("none"), holdings: mine });
  assert.deepEqual(z.limits, { none: true });
  assert.equal(z.profile.horizon_years, 20);
  assert.deepEqual(z.portfolio, { SPY: 0.6, AGG: 0.4 });
  /* limits.assumed (lane sector-limits): the reader's assumed answers, never one from the words or one you changed */
  assert.equal(b.limits.assumed, undefined, "the ok words assumed only the goal and the risk");
  const cl = Y.withYou(base, { investor: "you", you: you("clarify"), holdings });
  assert.deepEqual(cl.limits.assumed, ["esg"], "the reader assumed the values screen off");
  const pen = Y.withYou(base, { investor: "you", you: you("clarify", { edits: { esg: true }, edited: ["esg"] }), holdings });
  assert.equal(pen.limits.assumed, undefined, "changed with the pen: set by you");
  assert.equal(z.limits.assumed, undefined, "no limits: nothing to tag");
  /* the other four investors: the body is unchanged */
  assert.equal(Y.withYou(base, { investor: "robert", you: you("ok"), holdings }), base);
  assert.equal(Y.withYou(base, { investor: "you", you: null, holdings }), base);
});

t("Replay for You: waits for the card, runs live on it, plays a run that already answers it", () => {
  const holdings = { pilot: "you", portfolio: { ...Y.NEUTRAL }, amount: 200000 };
  const st = { investor: "you", mode: "live", you: you("ok"), holdings };
  assert.equal(Y.youGate({ investor: "robert", mode: "live" }, robert), null);
  assert.equal(Y.youGate({ investor: "you", mode: "live", you: null }, robert), "wait");
  assert.equal(Y.youGate(st, robert), "run", "the run on screen is Robert's");
  const plan = Y.planOf(st.you, holdings);
  const mine = { pilot: "you", amount: 200000, status: "ok", profile: { ...plan.profile, name: null, age: null },
    limits: { floor: -0.2, crypto: 0, edited: ["crypto"] } };
  assert.equal(Y.youGate(st, mine), null, "the same profile, amount and limits: the stage plays it");
  assert.equal(Y.youGate({ ...st, you: you("ok", { edits: { risk: "high" }, edited: ["risk"] }) }, mine), "run", "an edit on the card runs again");
});

t("the static fallback: one recorded example, else one honest line", () => {
  assert.equal(Y.STATIC_LINE, "Describing yourself needs the live app.");
  assert.equal(Y.youGate({ investor: "you", mode: "static", you: null }, robert), "wait");
  assert.equal(Y.exampleOf(null), null);
  assert.equal(Y.exampleOf({ version: 1, text: "", read: fx("ok") }), null);
  const ex = Y.exampleOf({ version: 1, text: "I'm 45 …", read: fx("ok"), key: "0123456789abcdef" });
  assert.equal(ex.file, "runs/0123456789abcdef.json");
  assert.equal(Y.cardModel({ read: ex.read }).rows.length, 6);
  assert.equal(Y.youGate({ investor: "you", mode: "static" }, { pilot: "you" }), null, "the example's run plays like a saved run");
  const inline = Y.exampleOf({ words: "I'm 45 …", response: fx("ok"), result: { pilot: "you", status: "ok" } });
  assert.equal(inline.result.pilot, "you", "a run inside the file is used as it is");
  assert.equal(inline.file, null);
  assert.equal(Y.exampleOf({ text: "x", read: { status: "blocked" } }), null);
});

t("the neutral starting mix is personas.json's moderate illustration, the same for everyone", () => {
  const personas = JSON.parse(readFileSync(new URL("../data/personas.json", import.meta.url), "utf8"));
  assert.deepEqual({ ...Y.NEUTRAL }, personas.illustration_mixes.moderate);
  assert.ok(Math.abs(Object.values(Y.NEUTRAL).reduce((a, b) => a + b, 0) - 1) < 1e-9);
});

t("an answer that is not a profile is not a card", () => {
  assert.equal(Y.cardModel({ read: Y.readOf({ status: "blocked", message: "This reads like a request for advice." }) }), null);
  assert.equal(Y.cardModel({ read: Y.readOf({ status: "error", message: "Keep it under 1,500 characters." }) }), null);
  assert.equal(Y.readOf({ status: "error", message: "Keep it under 1,500 characters." }).message, "Keep it under 1,500 characters.");
  assert.equal(Y.readOf(fx("none")).keyword, true, "a 503's keyword reading still fills the card, with its note");
  assert.equal(Y.readOf(fx("none")).move, "What if I put 20 % in Shopify?");
});

console.log(`web_profile_test: ${n} passed`);
