/* dev only (lane U0): the integrated page plus a store inspector. Open /dev/u0.html on the dev server (add ?static=1 for the
   static mode, ?investor=mateo, ?motion=0). Shows the mode, each section's mount state, the store keys as they change, and
   buttons that drive the store the way the lanes do (investor, replay, weightIndex). */
import { store } from "../state.js";

const box = document.getElementById("u0-inspector");
box.style.cssText = "position:fixed;right:8px;bottom:8px;z-index:60;width:340px;max-height:46vh;overflow:auto;padding:8px 10px;" +
  "background:rgba(0,0,0,.86);border:1px solid var(--rule);border-radius:8px;font:12px/1.45 var(--font-text);color:var(--ink-2)";
const el = (tag, text) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; };
const short = (v) => {
  if (v === null || v === undefined) return String(v);
  if (typeof v === "object") return v.run_id ? `Result ${v.pilot || ""} ${v.run_id}` : Array.isArray(v) ? `[${v.length}]` : "{…}";
  return String(v).slice(0, 60);
};
const log = [];
function render() {
  const s = store.get();
  const secs = (window.__epi && window.__epi.sections) || {};
  box.replaceChildren(
    el("strong", `mode ${s.mode} · ${s.investor} · phase ${s.phase} · w ${s.weightIndex}`),
    el("div", Object.entries(secs).map(([k, v]) => `${k}:${v}`).join("  ")),
    el("div", `errors: ${(window.__errors || []).length}`),
    ...["robert", "mateo", "amira", "canadian"].map((id) => {
      const b = el("button", id); b.type = "button"; b.className = "chip"; b.onclick = () => store.set({ investor: id }); return b;
    }),
    (() => { const b = el("button", "replay"); b.type = "button"; b.className = "chip"; b.onclick = () => store.set({ replay: Date.now() }); return b; })(),
    (() => { const b = el("button", "w=8"); b.type = "button"; b.className = "chip"; b.onclick = () => store.set({ weightIndex: 8 }); return b; })(),
    el("pre", log.slice(-12).join("\n")),
  );
  box.lastChild.style.cssText = "margin:6px 0 0;white-space:pre-wrap;font:11px/1.4 var(--font-num)";
}
store.on("*", (changed) => { for (const [k, v] of Object.entries(changed)) log.push(`${new Date().toISOString().slice(14, 23)} ${k} = ${short(v)}`); render(); });
render();
if (window.__epi) window.__epi.ready().then(render);
