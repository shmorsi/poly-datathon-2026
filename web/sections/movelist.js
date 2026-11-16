/* The asset list of "Try another move" as an instrument panel (lane picker): on a fine pointer, the face opens this listbox
   instead of the system menu (names first, the ticker small, each fund with what is inside it, the move marked in magenta).
   The real <select> stays the source of truth and the control on touch screens; this panel only sets its value and fires
   "change". Keys: Up / Down / Home / End / Page Up / Page Down, type to jump, Enter or Space to choose, Esc or Tab to close. It
   follows its face when the page scrolls and closes once the face leaves the screen.
   ARIA: a button with aria-haspopup="listbox" and aria-expanded; the listbox keeps focus and names the active option with
   aria-activedescendant. DOM from createElement and textContent only (R16). */
const PAGE = 8;

function h(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "text") n.textContent = v; else if (k === "class") n.className = v; else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}

/* rows: [{group?: label} | {value, name, ticker, hint}] in the select's order; opts.labelledby: the list's label id */
export function createList(field, select, rows, opts = {}) {
  const id = `${select.id || "mp"}-list`;
  const button = h("button", { class: "mp-open", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false",
    "aria-controls": id, "aria-label": select.getAttribute("aria-label") || "Choose" });
  const list = h("div", { class: "mp-list", id, role: "listbox", tabindex: "-1", hidden: true,
    "aria-labelledby": opts.labelledby || null, "aria-label": opts.labelledby ? null : select.getAttribute("aria-label") });
  const options = [];
  function fill(rs) {                            // the rows, in the select's order: group headings, then their options
    options.length = 0;
    list.replaceChildren();
    let group = null;
    for (const r of rs) {
      if (r.group) {
        const gid = `${id}-g${options.length}`;
        group = h("div", { class: "mp-group", role: "group", "aria-labelledby": gid }, h("p", { class: "mp-group-h", id: gid, text: r.group }));
        list.append(group);
        continue;
      }
      const o = h("div", { class: "mp-opt", role: "option", id: `${id}-${options.length}`, "aria-selected": "false", "data-value": r.value },
        h("span", { class: "mp-opt-dot", "aria-hidden": "true" }), h("span", { class: "mp-opt-name", text: r.name }),
        r.ticker ? h("span", { class: "mp-opt-tk", text: r.ticker }) : null,
        r.hint ? h("span", { class: "mp-opt-hint", text: r.hint }) : null);
      (r.top || !group ? list : group).append(o);
      options.push(o);
    }
  }
  fill(rows);
  field.classList.add("has-list");
  field.append(button);
  document.body.append(list);                   // fixed on the page: never clipped by the hero, above the globe and the bar
  let active = -1, typed = "", typedAt = 0, openedAt = 0;
  const label = select.getAttribute("aria-label") || "Choose";

  const visible = () => options.filter((o) => !o.hidden);
  function mark(i, scroll) {
    const vs = visible();
    if (!vs.length) return;
    active = Math.max(0, Math.min(vs.length - 1, i));
    for (const o of options) o.classList.toggle("is-active", o === vs[active]);
    list.setAttribute("aria-activedescendant", vs[active].id);
    if (scroll) vs[active].scrollIntoView({ block: "nearest" });
  }
  function sync() {                              // the select's value is the selected option; the button says it
    for (const o of options) o.setAttribute("aria-selected", String(o.dataset.value === select.value));
    const cur = select.selectedOptions && select.selectedOptions[0];
    button.setAttribute("aria-label", cur ? `${label}: ${cur.textContent}` : label);
  }
  function place() {                             // under the field, or over it when there is more room above
    const r = field.getBoundingClientRect(), gap = 6, bar = 72, below = innerHeight - r.bottom - gap - 12, above = r.top - gap - bar;
    const up = below < 260 && above > below, room = Math.max(160, Math.min(440, up ? above : below));
    list.style.left = `${Math.round(Math.max(8, Math.min(r.left, innerWidth - Math.max(r.width, 320) - 8)))}px`;
    list.style.width = `${Math.round(Math.min(innerWidth - 16, Math.max(r.width, 320)))}px`;
    list.style.maxHeight = `${Math.round(room)}px`;
    list.style.top = up ? "" : `${Math.round(r.bottom + gap)}px`;
    list.style.bottom = up ? `${Math.round(innerHeight - r.top + gap)}px` : "";
  }
  function open() {
    if (!list.hidden) return;
    sync();
    place();
    openedAt = performance.now();
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    field.classList.add("is-open");
    const vs = visible(), at = vs.findIndex((o) => o.dataset.value === select.value);
    mark(at < 0 ? 0 : at, false);
    const sel = vs[active];
    if (sel) list.scrollTop = Math.max(0, sel.offsetTop - list.clientHeight / 2 + sel.offsetHeight / 2);
    list.focus({ preventScroll: true });
    document.addEventListener("pointerdown", outside, true);
    addEventListener("scroll", away, { passive: true });
    addEventListener("resize", away);
  }
  function close(refocus) {
    if (list.hidden) return;
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    field.classList.remove("is-open");
    document.removeEventListener("pointerdown", outside, true);
    removeEventListener("scroll", away);
    removeEventListener("resize", away);
    if (refocus) button.focus({ preventScroll: true });
  }
  /* the page scrolled (a smooth scroll that brought the control into view, or the reader): the list follows its face, and
     closes once the face has left the screen */
  const away = () => {                          // (a scroll that is still bringing it in, just after it opened, never closes it)
    const r = field.getBoundingClientRect();
    if ((r.bottom < 0 || r.top > innerHeight) && performance.now() - openedAt > 900) close(false); else place();
  };
  function choose(o) {
    if (!o) return;
    close(true);
    if (select.value !== o.dataset.value) {
      select.value = o.dataset.value;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
  const outside = (e) => { if (!list.contains(e.target) && !field.contains(e.target)) close(false); };

  button.addEventListener("click", () => (list.hidden ? open() : close(true)));
  button.addEventListener("keydown", (e) => {
    if (!list.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) {   // opened from elsewhere, focus on the face: step into the list
      e.preventDefault(); list.focus({ preventScroll: true }); mark(active + (e.key === "ArrowDown" ? 1 : -1), true); return;
    }
    if (!list.hidden && e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
  });
  list.addEventListener("keydown", (e) => {
    const n = visible().length;
    const go = { ArrowDown: active + 1, ArrowUp: active - 1, Home: 0, End: n - 1, PageDown: active + PAGE, PageUp: active - PAGE }[e.key];
    if (go !== undefined) { e.preventDefault(); mark(go, true); return; }
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(visible()[active]); return; }
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key === "Tab") { close(true); return; }   // focus back on the face first, so Tab moves on from there (the list sits at the end of the page)
    if (e.key.length === 1 && /\S/.test(e.key) && !e.altKey && !e.ctrlKey && !e.metaKey) {   // type to jump, by name
      e.preventDefault();                        // the page's presenter keys (T, R, 1-8) skip a key the list has used
      const now = performance.now();
      typed = (now - typedAt > 600 ? "" : typed) + e.key.toLowerCase(); typedAt = now;
      const vs = visible(), from = typed.length === 1 ? active + 1 : active;
      const hit = [...vs.slice(from), ...vs.slice(0, from)].find((o) => o.querySelector(".mp-opt-name").textContent.toLowerCase().startsWith(typed));
      if (hit) mark(vs.indexOf(hit), true);
    }
  });
  list.addEventListener("pointermove", (e) => {
    const o = e.target.closest(".mp-opt");
    if (o && !o.hidden) mark(visible().indexOf(o), false);
  });
  list.addEventListener("click", (e) => { const o = e.target.closest(".mp-opt"); if (o) choose(o); });
  list.addEventListener("focusout", (e) => { if (!list.contains(e.relatedTarget) && e.relatedTarget !== button) close(false); });

  sync();
  return {
    sync,
    close,
    rebuild(rs) { close(false); fill(rs); sync(); },
    setLabel(value, text) { const o = options.find((x) => x.dataset.value === value); if (o) o.querySelector(".mp-opt-name").textContent = text; },
    get open() { return !list.hidden; },
  };
}
