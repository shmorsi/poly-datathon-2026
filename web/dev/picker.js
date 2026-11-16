/* Harness for lane picker (web/dev/picker.html, never published): the hero's question box stands in for sections/hero.js, and
   mountPicker gets the same api hero.js gives it. ?mode=live|static, ?investor=robert|mateo|amira|canadian. In live mode,
   Replay logs the question and the POST /api/run body the stage would send (PF.requestBody, as sections/replay.js builds it). */
import { store } from "../state.js";
import { loadRun, land } from "../data.js";
import { askLabel, throughWords, goLabel, namesMove } from "../lib/movepicker.js";
import { mountPicker } from "../sections/movepicker.js";

const NAMES = { robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "Too Canadian?" };
const params = new URLSearchParams(location.search);
const mode = params.get("mode") === "live" ? "live" : "static";
const investor = NAMES[params.get("investor")] ? params.get("investor") : "robert";
const q = document.getElementById("hx-q"), log = document.getElementById("log"), fns = [];
let edited = false;

function relabel() {
  const s = store.get(), name = NAMES[s.investor], moved = namesMove(q.value, s.result);
  document.getElementById("hx-two").textContent = askLabel(name, moved);
  document.getElementById("hx-go-t").textContent = goLabel(name, moved);
  document.getElementById("hx-years").textContent = throughWords(s.result);
}
function show() {
  const r = store.get().result;
  if (!edited && r && typeof r.question === "string") q.value = r.question.replace(/(\d) (?=%)/g, "$1\u00a0");
  q.readOnly = store.get().mode !== "live";
  relabel();
  for (const fn of fns) fn();
}
const api = {
  text: () => q.value,
  write(text) { q.value = String(text).replace(/(\d) (?=%)/g, "$1\u00a0"); edited = true; relabel(); for (const fn of fns) fn(); },
  follow() { edited = false; show(); },          // (the hero also settles the words and rings the pill on a cue)
  name: (id) => NAMES[id] || null,
  onText(fn) { fns.push(fn); },
};

store.set({ mode, investor });
store.on("result", show);
q.addEventListener("input", () => { edited = true; relabel(); for (const fn of fns) fn(); });
document.getElementById("hx-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const words = q.value.replace(/\u00a0/g, " ").trim(), r = store.get().result, P = globalThis.PF;
  const body = mode === "live" && r && P ? P.requestBody({ ...P.planFrom(r, investor), q: words }, null, false) : null;
  log.textContent = mode === "live" ? `Replay would send: ${JSON.stringify({ question: body.question, pilot: body.pilot, portfolio: body.portfolio })}`
    : `Replay would play the saved run on screen: “${r ? r.question : ""}”`;
});
loadRun(investor).then((r) => { land(r, { question: r.question }); mountPicker(document.getElementById("hx-pick"), store, api); show(); },
  () => { log.textContent = "No saved run for this investor on this server."; });
