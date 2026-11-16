/* EPICENTRE Replay, lane U5: #checklist, the checks (design doc §2.5; rulings R1, R13, R16; the critique's problem 5).
   mount(el, store): result.checks in PF.view's order (the most serious first), the asked shock's check pinned into the
   visible three, "Showing 3 of 8 checks" and a "Show all 8 checks" control. Each row: the status as icon + word in its tone
   (a row's colour says what it did to the verdict: only a hard limit that broke reads Outside, with the octagon; a soft
   limit, a preference or a warning reads Caution), the plain name, the tier as quiet text, the value and the limit in
   Archivo tabular figures, the row that decided the verdict marked, and a quiet "Details" control with a chevron that shows
   the code's own reason. The checks stay on the size asked; when the dial moves, a line says so. DOM by createElement. */
import { checksModel, checklistLead, RULE_MEANING, dialNote, limitsBlock, limitsLine, recheckBody, mergeRecheck, noLimitsBlock } from "../lib/money.js";
import { say } from "../lib/meaning.js";
import { h, icon, num, ms } from "./money.js";
import { head, details } from "./clarity.js";
import { standingLine } from "../lib/status.js";
import { industryEditor, readRows } from "./sectorcaps.js";

const SVG = "http://www.w3.org/2000/svg";
function chevron() {
  const s = document.createElementNS(SVG, "svg");
  s.setAttribute("class", "ck-chev");
  s.setAttribute("viewBox", "0 0 12 12");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  const p = document.createElementNS(SVG, "path");
  p.setAttribute("d", "M2.5 4.5 6 8l3.5-3.5");
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", "1.5");
  p.setAttribute("stroke-linecap", "round");
  p.setAttribute("stroke-linejoin", "round");
  s.append(p);
  return s;
}
const idOf = (rule) => `ck-why-${String(rule).replace(/[^\w-]/g, "")}`;

/* a row; compact (the three on top, R22): dollars only, no per-row control (their reasons are in the details) */
function rowNode(x, open, compact) {
  const [vk, lk] = RULE_MEANING[x.rule] || ["value", "limit"];
  const value = compact ? x.valueShort : x.value, limit = compact ? x.limitShort : x.limit;
  const meta = [x.tierText ? h("span", { class: "ck-tier" }, x.tierText) : null,
    x.decided ? h("span", { class: "ck-decided" }, x.decidedWord || "Decided the verdict") : null,
    x.asked ? h("span", { class: "ck-asked" }, "The shock asked about: ", x.asked) : null,
    x.own ? h("span", { class: "ck-own" }, x.own) : null,
    x.srcText ? h("span", { class: "ck-src", "data-source": x.src }, x.srcText) : null,
    x.ruleWords ? h("span", { class: "ck-rule" }, x.ruleWords) : null].filter(Boolean);
  const change = x.change ? h("p", { class: "ck-change" }, h("span", { class: "ck-change-lbl" }, "What would change the answer: "), x.change) : null;
  const why = h("div", { class: "ck-why", id: idOf(x.rule), hidden: !open },
    x.reason ? h("p", {}, x.reason) : null,
    x.evidence ? h("p", { class: "ck-evidence" }, "Evidence: ", x.evidence) : null,
    x.same ? h("p", { class: "ck-same" }, `Same cause as ${x.same}.`) : null);
  const more = !compact && (x.reason || x.evidence || x.same)
    ? h("button", { type: "button", class: "ck-more", "aria-expanded": open ? "true" : "false", "aria-controls": idOf(x.rule),
      "data-rule": x.rule }, h("span", {}, "Details"), h("span", { class: "sr" }, ` about ${x.name}`), chevron())
    : null;
  return h("li", { class: "ck-row", "data-tone": x.tone, "data-rule": x.rule, "data-decided": x.decided ? "yes" : null,
    "data-hard": x.hard ? "yes" : "no" },
    h("div", { class: "ck-main" },
      h("p", { class: "ck-status", "data-tone": x.tone }, icon(x.icon, "icon ck-icon"), h("span", {}, x.word)),
      h("div", { class: "ck-what" }, h("p", { class: "ck-name" }, x.name), meta.length ? h("p", { class: "ck-meta" }, meta) : null),
      h("p", { class: "ck-val" }, h("span", { class: "ck-lbl" }, "In this replay "), value ? num(value, x.valueFact, "ck-fig", `${x.name}, in this replay: ${x.value}`, say(vk, x.value)) : null),
      h("p", { class: "ck-lim" }, limit ? [h("span", { class: "ck-lbl" }, "Your limit "), num(limit, x.limitFact, "ck-fig", `${x.name}, your limit: ${x.limit}`, say(lk, x.limit))] : null),
      compact ? null : h("div", { class: "ck-act" }, more)),
    compact ? null : change, compact ? null : why);
}

/* R35: the second limit, capacity, as a fact row from result.capacity (the path's own dollars; no check of its own) */
function capacityNode(c) {
  if (!c) return null;
  return h("li", { class: "ck-row ck-capacity", "data-tone": c.tone, "data-rule": "capacity" },
    h("div", { class: "ck-main" },
      h("p", { class: "ck-status", "data-tone": c.tone }, c.icon ? icon(c.icon, "icon ck-icon") : h("span", { class: "ck-icon-none", "aria-hidden": "true" }), h("span", {}, c.word)),
      h("div", { class: "ck-what" }, h("p", { class: "ck-name" }, c.name), h("p", { class: "ck-meta" }, h("span", { class: "ck-rule" }, c.meta))),
      h("p", { class: "ck-val" }, h("span", { class: "ck-lbl" }, "In this replay "), c.value ? h("span", { class: "ck-fig" }, c.value) : null),
      h("p", { class: "ck-lim" }, h("span", { class: "ck-lbl" }, "Your limit "), h("span", { class: "ck-fig" }, c.limit))),
    h("p", { class: "ck-change ck-cap-when" }, c.when));
}

/* your limits (PF.youRows + result.limits): the workshop's "tolerance is not capacity" in one line, and the one control that
   types a limit: live, it asks the server to judge the same run again (POST /api/recheck); static, it says why it cannot */
function youNode(Y, ui) {
  const dl = h("dl", { class: "ck-you-dl" }, Y.rows.filter((x) => x.key !== "floor_pct").map((x) => h("div", { class: "ck-you-item" },
    h("dt", {}, x.label), h("dd", {}, x.value, x.tag || x.typed ? h("span", { class: "ck-typed" }, x.tag || "set by you") : null))));
  const floor = Y.rows.find((x) => x.key === "floor_pct");
  const floorLine = floor && Y.floorNote ? h("p", { class: "ck-you-floor" }, h("strong", {}, `Your floor, ${floor.value}: `),
    Y.floorNote.charAt(0).toLowerCase() + Y.floorNote.slice(1)) : null;
  const btn = h("button", { type: "button", class: "ck-you-edit", "aria-expanded": ui.editing ? "true" : "false", "aria-controls": "ck-you-form",
    disabled: !Y.edit.live, "aria-describedby": Y.edit.live ? null : "ck-you-why" }, icon("i-edit", "icon ck-edit"), h("span", {}, "Edit your limits"));
  const form = Y.edit.live ? h("form", { class: "ck-you-form", id: "ck-you-form", hidden: !ui.editing, novalidate: true },
    h("label", { class: "ck-field" }, h("span", { class: "ck-field-lbl" }, "The most you could lose"),
      h("span", { class: "ck-field-in" }, h("span", { "aria-hidden": "true" }, "$"),
        h("input", { name: "capacity", inputmode: "numeric", autocomplete: "off", value: Y.edit.capacity === null ? "" : String(Y.edit.capacity) }),
        Y.edit.amountText ? h("span", { class: "ck-field-of" }, `of ${Y.edit.amountText}`) : null)),
    h("label", { class: "ck-field" }, h("span", { class: "ck-field-lbl" }, "One company, at most"),
      h("span", { class: "ck-field-in" }, h("input", { name: "single", inputmode: "decimal", autocomplete: "off", value: Y.edit.single === null ? "" : String(Y.edit.single) }),
        h("span", { "aria-hidden": "true" }, "%"))),
    /* lane sector-limits: "Limit by industry +" rows; the draft lives in ui.caps so a redraw keeps what was typed */
    industryEditor(ui.caps || (ui.caps = (Y.edit.caps || []).map((c) => ({ ...c }))), (rows) => { ui.caps = rows; }),
    h("div", { class: "ck-you-acts" }, h("button", { type: "submit", class: "btn btn-quiet ck-you-go" }, ui.busy ? "Checking" : "Check again"),
      h("button", { type: "button", class: "linkbtn ck-you-cancel" }, "Cancel"))) : null;
  return h("section", { class: "ck-you", "aria-labelledby": "ck-you-title" },
    h("div", { class: "ck-you-head" }, h("h3", { class: "ck-you-title", id: "ck-you-title" }, "Your limits"),
      h("p", { class: "ck-you-note" }, Y.note), btn,
      Y.edit.why ? h("p", { class: "ck-you-why", id: "ck-you-why" }, Y.edit.why) : null),
    dl, floorLine, form,
    h("p", { class: "ck-you-status", "aria-live": "polite", hidden: !ui.status }, ui.status || "",
      ui.rechecked ? [" ", h("button", { type: "button", class: "linkbtn ck-you-reset" }, "Back to the run\u2019s limits")] : null));
}

/* POST /api/recheck {run_id, limits} (server.py): the same run judged with the limits you typed; plain sentences only */
async function postRecheck(body) {
  let res;
  try { res = await fetch("/api/recheck", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" }); }
  catch (e) { throw new Error("The server could not be reached. Check the connection, then try again."); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) throw new Error((data && typeof data.message === "string" && data.message.trim()) || "The limits could not be checked again. Try once more.");
  return data;
}

export function mount(el, store) {
  if (!el) return;
  el.classList.add("ck");
  el.setAttribute("aria-labelledby", "checklist-title");
  let all = false, lastResult, drawn = false, swap = false;
  let ui = { editing: false, busy: false, status: null, rechecked: false };
  const originals = new Map();                             // run_id -> the Result as it landed, before any recheck
  const open = new Set();
  const P = () => globalThis.PF;

  function draw(focusAll) {
    const st = store.get() || {}, m = P() ? checksModel(st.result, st.view, P()) : null;
    if (!m) {
      const none = P() ? noLimitsBlock(st.result, st.view, st.mode, P()) : null;     // no limits set: the editor still opens
      el.hidden = !none;
      el.replaceChildren(...(none ? [h("div", { class: "frame ck-frame" }, head("checklist-title", none.question, none.answer), youNode(none.Y, ui))] : []));
      return;
    }
    el.hidden = false;
    const L = checklistLead(st.result, st.view, P());
    const note = dialNote(st.result, st.view, st.weightIndex, P());
    const cols = (extra) => h("div", { class: `ck-cols${extra ? ` ${extra}` : ""}`, "aria-hidden": "true" },
      h("span", { class: "ck-c-what" }, "Check"), h("span", { class: "ck-c-val" }, "In this replay"), h("span", { class: "ck-c-lim" }, "Your limit"));
    const list = h("ol", { class: "ck-list", id: "ck-list" }, L.rows.map((x) => rowNode(x, false, true)), capacityNode(L.capacity));
    /* the details: why the three read as they did, the other checks (each with its own reason), your limits and the editor */
    const reasons = L.rows.filter((x) => x.reason || x.change || x.evidence);
    const whyThree = reasons.length ? h("section", { class: "ck-whys", "aria-labelledby": "ck-whys-t" },
      h("h3", { class: "ck-sub-h", id: "ck-whys-t" }, "Why these read as they did"),
      h("ul", { class: "ck-why-list" }, reasons.map((x) => h("li", { class: "ck-why-item", "data-tone": x.tone },
        h("p", { class: "ck-why-name" }, x.name, h("span", { class: "ck-why-full" }, x.value && x.limit ? `${x.value} against your limit of ${x.limit}` : x.value || "")),
        x.reason ? h("p", {}, x.reason) : null,
        x.evidence ? h("p", { class: "ck-evidence" }, "Evidence: ", x.evidence) : null,
        x.change ? h("p", { class: "ck-change" }, h("span", { class: "ck-change-lbl" }, "What would change the answer: "), x.change) : null)))) : null;
    const rest = L.rest.length ? h("section", { class: "ck-rest", "aria-labelledby": "ck-rest-t" },
      h("h3", { class: "ck-sub-h", id: "ck-rest-t" }, L.rest.length === 1 ? "The other check" : `The other ${L.rest.length} checks`),
      cols(), h("ol", { class: "ck-list" }, L.rest.map((x) => rowNode(x, open.has(x.rule), false)))) : null;
    const Y = limitsBlock(st.result, st.view, st.mode, P());
    const frame = h("div", { class: "frame ck-frame" },
      head("checklist-title", L.question, L.answer),
      h("p", { class: "ck-dial", "aria-live": "polite", hidden: !note }, note || ""),
      h("div", { class: "ck-top" }, cols(), list),
      h("p", { class: "cl-quiet ck-limits-line" }, limitsLine(st.result, st.view).text),     // who set these limits, in one muted line
      h("p", { class: "cl-quiet ck-honest" }, m.history),
      h("p", { class: "cl-quiet ck-unmeasured" }, m.unmeasured),
      details("checklist", store, [whyThree, rest, Y ? youNode(Y, ui) : null, h("p", { class: "ck-legend" }, m.legend)],
        { label: "Your rules: the details" }));
    if (swap && drawn) frame.classList.add("is-swap");
    swap = false;
    drawn = true;
    el.replaceChildren(frame);
    if (focusAll) frame.querySelector(".ck-all")?.focus({ preventScroll: true });
  }

  const redraw = (focus) => { draw(false); if (focus) el.querySelector(focus)?.focus({ preventScroll: true }); };
  el.addEventListener("submit", async (ev) => {
    const form = ev.target.closest(".ck-you-form");
    if (!form) return;
    ev.preventDefault();
    if (ui.busy) return;
    const st = store.get() || {}, r = st.result;
    const typed = { capacity: String(form.elements.capacity.value || "").replace(/[^\d.]/g, ""), single: String(form.elements.single.value || "").replace(/[^\d.]/g, ""),
      caps: readRows(form.querySelector(".ck-caps")) };
    const L = (r && r.limits) || {};
    if (typed.capacity && r && Number(typed.capacity) === Math.round([r.profile && r.profile.capacity, L.capacity_dollars].find((x) => typeof x === "number") || NaN)) typed.capacity = "";
    if (typed.single && typeof L.single_stock === "number" && Number(typed.single) === Math.round(L.single_stock * 1000) / 10) typed.single = "";
    const made = recheckBody(r, typed);
    if (made.error) { ui = { ...ui, status: made.error }; redraw(".ck-you-form input"); return; }
    ui = { ...ui, busy: true, status: "Checking the same run with your limits\u2026" };
    redraw(".ck-you-go");
    try {
      const rc = await postRecheck(made.body), merged = mergeRecheck(r, rc, made.body, typed);
      if (!merged) throw new Error("The limits could not be checked again. Try once more.");
      if (!originals.has(r.run_id)) originals.set(r.run_id, r);
      const word = (P().VERDICT[merged.verdict] || {}).word;
      ui = { editing: false, busy: false, rechecked: true,
        status: `Checked again with the limits you typed${word ? `: ${word}, in this replay` : ""}. ${standingLine(!!P().moveOf(merged))} The replay and the dial above keep the limits the run started with.` };
      store.set({ result: merged, view: P().view(merged) });
      el.querySelector(".ck-you-edit")?.focus({ preventScroll: true });
    } catch (e) {
      ui = { ...ui, busy: false, status: e && e.message ? e.message : "The limits could not be checked again. Try once more." };
      redraw(".ck-you-go");
    }
  });
  el.addEventListener("click", (ev) => {
    if (ev.target.closest(".ck-you-edit")) { ui = { ...ui, editing: !ui.editing, status: ui.rechecked ? ui.status : null }; redraw(ui.editing ? ".ck-you-form input" : ".ck-you-edit"); return; }
    if (ev.target.closest(".ck-you-cancel")) { ui = { ...ui, editing: false, caps: null, status: ui.rechecked ? ui.status : null }; redraw(".ck-you-edit"); return; }
    if (ev.target.closest(".ck-you-reset")) {
      const st = store.get() || {}, o = st.result && originals.get(st.result.run_id);
      ui = { editing: false, busy: false, status: null, rechecked: false };
      if (o) store.set({ result: o, view: P().view(o) });
      el.querySelector(".ck-you-edit")?.focus({ preventScroll: true });
      return;
    }
    const traced = ev.target.closest("[data-fact]");
    if (traced && el.contains(traced)) { store.set({ thread: traced.dataset.fact }); return; }
    const more = ev.target.closest(".ck-more");
    const keyed = ev.detail === 0;                         // Enter or Space: no motion (never animate a keyboard action)
    if (more && el.contains(more)) {
      const rule = more.dataset.rule, region = el.querySelector(`#${idOf(rule)}`), on = more.getAttribute("aria-expanded") !== "true";
      if (on) open.add(rule); else open.delete(rule);
      more.setAttribute("aria-expanded", on ? "true" : "false");
      if (region) { region.hidden = !on; region.classList.toggle("is-new", on && !keyed); }
      return;
    }
  });
  let queued = false;
  const later = () => { if (queued) return; queued = true; queueMicrotask(() => { queued = false; draw(false); }); };
  store.on("result", (r) => {
    if (r === lastResult) return;
    const same = r && lastResult && r.run_id && r.run_id === lastResult.run_id;     // a recheck of the same run keeps its line
    if (!same) { ui = { editing: false, busy: false, status: null, rechecked: false }; originals.clear(); }
    lastResult = r; all = false; open.clear(); swap = true; later();
  });
  store.on("view", later);
  store.on("weightIndex", () => {
    const st = store.get() || {}, n = el.querySelector(".ck-dial"), text = dialNote(st.result, st.view, st.weightIndex, P());
    if (!n) return;
    n.textContent = text || "";
    n.hidden = !text;
  });
  lastResult = (store.get() || {}).result;
  draw(false);
}
