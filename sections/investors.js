/* EPICENTRE Replay, lane U7: #investors, "Three investors, three answers" (design doc §2 item 7; R14, R15, R13, R4). A ledger
   of the four saved runs (data.loadRun for each): who, their own words with the asked shock and the move, the answer with
   "in this <years> replay" under it, the check that decided it, and when the run was recorded. Pressing a row sets
   {investor, replay} on the store; the replay stage scrolls itself to the stage (a fallback scroll when it is not mounted).
   Every number is a Result key through PF.view and web/lib/how.js. DOM from createElement/textContent (R16). */
import { loadRun } from "../data.js";
import { standingLine } from "../lib/status.js";
import * as H from "../lib/how.js";
import { head, details, marks } from "./clarity.js";
import { keepRanges } from "../lib/meaning.js";
import { PERSONA_TEST, sectorLine } from "../lib/money.js";
import { mixBar } from "./hold.js";

const SVGNS = "http://www.w3.org/2000/svg";
function h(tag, attrs, ...kids) {
  const svg = tag.startsWith("svg:");
  const el = svg ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const icon = (id, cls) => h("svg:svg", { class: cls || "icon", "aria-hidden": "true", focusable: "false" }, h("svg:use", { href: `#${id}` }));
const TONE = { inside: "tone-in", caveat: "tone-caution", outside: "tone-out" };
const LQ = "“", RQ = "”";

function playButton(id, x, store, nameId) {
  const play = h("button", { class: "inv-play", type: "button", "aria-describedby": nameId,
    "aria-label": `Replay ${x.name}${x.move ? ": " + x.move : ""}` },
    h("span", { class: "inv-play-face" }, icon("i-play", "icon inv-play-icon"), h("span", { text: "Replay" })));   // the face moves on press, never the button (its box is the row's)
  play.addEventListener("click", () => {
    store.set({ investor: id, replay: Date.now() });
    requestAnimationFrame(() => {                         // the stage scrolls itself; without it, go where the replay starts
      const stage = document.getElementById("replay");
      if (stage && stage.dataset.mount === "ready") return;
      const hero = document.getElementById("hero");
      (hero && hero.dataset.mount === "ready" ? hero : document.body).scrollIntoView({ block: "start" });
    });
  });
  return play;
}

/* R22: one line per investor, no figures: who, the shock asked about, the answer (with "in this <years> replay"), the check
   that shaped it, Replay */
const BY = (label) => (/^decided/i.test(label) ? "Decided by" : /caveat/i.test(label) ? "Caveat from" : /answers/i.test(label) ? "Answered by" : label);
function line(id, r, store) {
  const x = H.ledgerRow(r, id);
  if (!x) return h("div", { class: "inv-line is-empty" }, h("p", { class: "inv-none", text: "There is no saved run for this investor yet." }));
  const nameId = `inv-${id}-name`, d = x.decided;
  return h("article", { class: "inv-line", "aria-labelledby": nameId },
    h("div", { class: "inv-namecell" }, h("h3", { class: "inv-name", id: nameId, text: x.name }),
      mixBar(r)),                               // lane hold: the mix today, one thin bar under the name (names on hover or tap, no figures)
    h("p", { class: "inv-asked" }, x.family ? [h("span", { class: "inv-dot", "aria-hidden": "true" }), h("span", { class: "sr", text: "Shock asked about: " }), x.family] : null),
    h("p", { class: `inv-verdict status ${TONE[x.verdict.tone] || "tone-quiet"}` }, icon(x.verdict.icon, "icon inv-v-icon"),
      h("span", { text: x.verdict.word }), h("span", { class: "inv-qual", text: x.qualifier })),
    h("p", { class: "standing-line inv-standing", text: standingLine(!!(globalThis.PF && globalThis.PF.moveOf(r))) }),
    h("p", { class: "inv-by" }, d ? [h("span", { class: "inv-by-label", text: `${BY(x.decidedLabel)} ` }), h("strong", { text: d.name })] : null),
    ownLine(id, r),
    h("div", { class: "inv-act" }, h("p", { class: "inv-now", text: "On screen now" }), playButton(id, x, store, nameId)));
}

/* G4: a persona's own stated test, in view on the card (Amira: "not exclusively tech", her one-sector line) */
function ownLine(id, r) {
  const test = PERSONA_TEST[id], s = test && test.rule === "sector" ? sectorLine(r, globalThis.PF) : null;
  return s ? h("p", { class: "inv-own" }, h("span", { class: "inv-own-k", text: `${test.words}. ` }), s.text) : null;
}

/* the details: each investor in their own words, the move, and the sentence of the check that shaped the answer */
function words(id, r) {
  const x = H.ledgerRow(r, id);
  if (!x) return null;
  const d = x.decided;
  return h("section", { class: "inv-words-item", "aria-label": x.name },
    h("p", { class: "inv-w-name" }, h("strong", { text: x.name }), x.meta ? h("span", { class: "inv-meta", text: ` ${x.meta}` }) : null,
      x.kicker ? h("span", { class: "inv-meta", text: ` ${x.kicker}` }) : null),
    x.question ? h("blockquote", { class: "inv-q" }, h("p", { text: `${LQ}${x.question.replace(/(\d) %/g, "$1\u00a0%")}${RQ}` })) : null,
    x.move ? h("p", { class: "inv-w-move" }, h("span", { class: "sr", text: "The move: " }), x.move) : null,
    d && d.sentence ? h("p", { class: "inv-why", text: d.sentence }) : null,
    x.without ? h("p", { class: "inv-without", text: x.without }) : null,
    x.recorded ? h("p", { class: "inv-rec", text: x.recorded.text }) : null);
}

export function mount(el, store) {
  el.classList.add("inv");
  el.setAttribute("aria-labelledby", "investors-title");
  const list = h("ul", { class: "inv-list" });
  const rows = new Map(H.INVESTORS.map((id) => [id, h("li", { class: "inv-row is-loading", "data-id": id })]));
  for (const li of rows.values()) list.append(li);
  const more = h("div", { class: "inv-more" });
  const said = new Map();                                  // id -> the check that shaped its answer (to say "a different check")
  const answer = h("span", { text: "Each investor asked in their own words, against their own limits." });
  el.replaceChildren(h("div", { class: "frame inv-frame" },
    head("investors-title", "Does it adapt to the investor?", answer),
    list,
    h("p", { class: "cl-quiet inv-honest", text: "This already happened; it is not a forecast. Fictional illustration, not a recommendation." }),
    details("investors", store, [more,
      h("p", { class: "inv-note" }, icon("m-assumption", "kind"),
        h("span", {}, "Their limits are assumptions for these fictional profiles; on the live app you can type your own. ",
          h("a", { class: "inv-note-link", href: "#checklist", text: "Edit your limits in the checklist (live app)." }))), marks()],
      { label: "The investors: the details" })));

  const current = (id) => {
    for (const [rid, li] of rows) (rid === id ? li.setAttribute("aria-current", "true") : li.removeAttribute("aria-current"));
  };
  const landed = (id, r) => {
    const li = rows.get(id);
    li.classList.remove("is-loading");
    li.replaceChildren(line(id, r, store));
    const x = r ? H.ledgerRow(r, id) : null;
    said.set(id, x && x.decided ? x.decided.rule || x.decided.name : null);
    const w = words(id, r);
    more.querySelector(`[data-w="${id}"]`)?.remove();
    if (w) { w.dataset.w = id; more.append(w); }
    [...more.children].sort((a, b) => H.INVESTORS.indexOf(a.dataset.w) - H.INVESTORS.indexOf(b.dataset.w)).forEach((n) => more.append(n));
    const rules = [...said.values()];
    if (rules.length === H.INVESTORS.length && rules.every(Boolean) && new Set(rules).size === rules.length) {
      const qual = x && x.qualifier ? `, ${x.qualifier}` : "";
      answer.textContent = keepRanges(`Yes: a different check shaped each answer${qual}.`);
    }
  };
  /* the other investors' saved runs after first paint (idle, or the ledger near the viewport): the hero goes first */
  H.whenNear(el, () => {
    for (const id of H.INVESTORS) loadRun(id).then((r) => landed(id, r), () => landed(id, null));
  });
  store.on("investor", current);
  current(store.get().investor);
}
