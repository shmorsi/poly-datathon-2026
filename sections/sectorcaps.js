/* EPICENTRE Replay, lane sector-limits: the industry rows of #checklist's live limits editor (agreed with lane hold, 16:55: its
   limits card opens this same editor). industryEditor(rows, onChange) -> a <fieldset>: one row per industry limit (a GICS sector
   <select>, the largest share in %, "set by you" or "from your words", Remove) and the "Limit by industry +" button; it keeps its
   rows in `rows` (the caller's draft, so a redraw of the section keeps what was typed) and calls onChange(rows) after each edit.
   readRows(fieldset) reads the rows as typed. DOM by createElement; it never judges a cap (governance does, on the server). */
import { GICS_SECTORS, sourceWords } from "../lib/sectorcaps.js";
import { h } from "./money.js";

let uid = 0;

function rowNode(row, i) {
  const id = `ck-cap-${uid}-${i}`;
  const select = h("select", { name: "cap-sector", id: `${id}-s`, "aria-label": `Industry ${i + 1}` },
    h("option", { value: "" }, "Pick an industry"),
    GICS_SECTORS.map((s) => h("option", { value: s, selected: row.sector === s ? true : null }, s)));
  const tag = sourceWords(row.source || "you");
  return h("div", { class: "ck-cap-row", "data-cap-row": String(i) },
    h("span", { class: "ck-field-in ck-cap-pick" }, select),
    h("label", { class: "ck-field-in ck-cap-share", for: `${id}-p` },
      h("span", { class: "sr" }, `Largest share for industry ${i + 1}`),
      h("span", { "aria-hidden": "true" }, "at most"),
      h("input", { name: "cap-pct", id: `${id}-p`, inputmode: "decimal", autocomplete: "off",
        value: row.pct === null || row.pct === undefined ? "" : String(row.pct) }),
      h("span", { "aria-hidden": "true" }, "%")),
    h("span", { class: "ck-typed ck-cap-tag" }, tag === "from your words" ? "from your words" : "set by you"),
    h("button", { type: "button", class: "linkbtn ck-cap-remove", "data-cap-remove": String(i) },
      "Remove", h("span", { class: "sr" }, ` the limit for industry ${i + 1}`)));
}

/* rows: [{sector, pct, source}] (pct in %, 0 = none of it); the fieldset owns its clicks and keeps `rows` current */
export function industryEditor(rows, onChange) {
  uid += 1;
  const draft = Array.isArray(rows) ? rows : [];
  const box = h("fieldset", { class: "ck-caps" },
    h("legend", { class: "ck-field-lbl" }, "Limits by industry"),
    h("p", { class: "ck-caps-note" }, "0 % keeps an industry out of the mix, its share inside your funds included."),
    h("div", { class: "ck-caps-rows" }, draft.map(rowNode)),
    h("button", { type: "button", class: "btn btn-quiet ck-cap-add" }, "Limit by industry +"));
  const sync = () => { const now = readRows(box); draft.splice(0, draft.length, ...now.map((x, i) => ({ ...draft[i], ...x }))); };
  const redraw = (focus) => {
    box.querySelector(".ck-caps-rows").replaceChildren(...draft.map(rowNode));
    if (typeof onChange === "function") onChange(draft);
    if (focus) box.querySelector(focus)?.focus({ preventScroll: true });
  };
  box.addEventListener("input", (ev) => {
    sync();
    const n = ev.target.closest("[data-cap-row]"), i = Number(n && n.dataset.capRow);
    if (Number.isInteger(i) && draft[i] && draft[i].source !== "you") {                // an edited share is yours
      draft[i].source = "you";
      const tag = n.querySelector(".ck-cap-tag");
      if (tag) tag.textContent = "set by you";
    }
    if (typeof onChange === "function") onChange(draft);
  });
  box.addEventListener("change", (ev) => {
    if (!ev.target.closest("select")) return;
    sync();
    const i = Number(ev.target.closest("[data-cap-row]")?.dataset.capRow);
    if (Number.isInteger(i) && draft[i]) draft[i].source = "you";        // a changed industry is yours
    if (typeof onChange === "function") onChange(draft);
  });
  box.addEventListener("click", (ev) => {
    if (ev.target.closest(".ck-cap-add")) {
      sync();
      draft.push({ sector: "", pct: "", source: "you" });
      redraw(`[data-cap-row="${draft.length - 1}"] select`);
      return;
    }
    const gone = ev.target.closest("[data-cap-remove]");
    if (gone) {
      sync();
      draft.splice(Number(gone.dataset.capRemove), 1);
      redraw(".ck-cap-add");
    }
  });
  return box;
}

/* the rows as typed: [{sector, pct}] (pct a string, "" when empty) */
export function readRows(box) {
  if (!box) return [];
  return [...box.querySelectorAll("[data-cap-row]")].map((n) => ({
    sector: String(n.querySelector("select")?.value || ""), pct: String(n.querySelector("input")?.value || "").trim() }));
}
