/* dev harness for lane agentlog: a saved run on the store, the stage's phaseClock emulated (R.schedule's beats), live steps faked */
import { store } from "../state.js";
import { mount } from "../sections/agentlog.js";

const T = { lift: 0, chips: 1000, fly: 2200, handoff: 3400, race: 4200, raceMs: 2400, lamp: 6720, end: 7700 };
const $ = (id) => document.getElementById(id);
const timers = [];
const clear = () => { while (timers.length) clearTimeout(timers.pop()); };
const phase = (p, extra = {}) => { $("dev-phase").textContent = p; store.set({ phase: p, phaseClock: { phase: p, at: performance.now(), T, ...extra } }); };
async function load(who) {
  const r = await (await fetch(`/runs/${who}.json`)).json();
  $("dev-q").textContent = `“${r.question}”`;
  store.set({ result: r, investor: who });
}
function play() {
  clear();
  phase("reading");
  timers.push(setTimeout(() => phase("flying"), T.fly), setTimeout(() => phase("racing"), T.race), setTimeout(() => phase("landed"), T.lamp));
}
function live() {
  clear();
  phase("reading", { live: true });
  const steps = ["OBSERVE", "UNDERSTAND", "COMPARE", "EXPLAIN", "VERIFY"].map((step) => ({ step, status: "waiting" }));
  const ms = [640, 2400, 4600, 6200, 700];
  let t = 0;
  steps.forEach((s, i) => {
    timers.push(setTimeout(() => { steps[i] = { ...s, status: "running" }; store.set({ steps: steps.slice() }); }, t));
    t += ms[i] / 2;
    timers.push(setTimeout(() => { steps[i] = { ...s, status: "done", ms: ms[i] }; store.set({ steps: steps.slice() }); }, t));
  });
  timers.push(setTimeout(() => { phase("flying"); timers.push(setTimeout(() => phase("racing"), T.race - T.fly), setTimeout(() => phase("landed"), T.lamp - T.fly)); }, t + 200));
}
window.addEventListener("load", async () => {
  await load(new URLSearchParams(location.search).get("investor") || "robert");
  window.__log = mount($("agentlog"), store);
  $("dev-play").onclick = play;
  $("dev-skip").onclick = () => { clear(); phase("landed", { instant: true }); };
  $("dev-live").onclick = live;
  $("dev-who").onchange = (e) => load(e.target.value);
  window.__dev = { play, live, phase, T, store };
  document.documentElement.dataset.ready = "1";
});
