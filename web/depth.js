/* EPICENTRE Replay: the "Simple / Detailed" switch (ruling R22, lane U0). One store key, `depth`: "simple" (the default: every
   section shows its question, its answer and at most 1-3 large numbers) or "detailed" (every section's "Show the details"
   opens). Sections listen to store.on("depth"). The switch sits in the top bar's end group (lane U7b's .bar-end, built once at
   its mount), before the date; ?depth=detailed opens the page detailed (captures, the film). DOM from createElement only. */

const OPTIONS = [["simple", "Simple"], ["detailed", "Detailed"]];

export function initialDepth(params) {
  return params && params.get("depth") === "detailed" ? "detailed" : "simple";
}

export function mountDepth(store) {
  const group = document.createElement("div");
  group.className = "depth";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", "How much detail the page shows");
  const buttons = OPTIONS.map(([value, label]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "depth-opt";
    b.dataset.depth = value;
    b.textContent = label;
    b.addEventListener("click", () => store.set({ depth: value }));
    group.append(b);
    return b;
  });
  const paint = (depth) => {
    for (const b of buttons) b.setAttribute("aria-pressed", String(b.dataset.depth === depth));
    document.documentElement.dataset.depth = depth;
  };
  paint(store.get().depth || "simple");
  store.on("depth", paint);
  const end = document.querySelector("#bar .bar-end");
  if (end) end.prepend(group);
  else {                                          // no bar on this page: a quiet pill at the top right
    group.classList.add("is-floating");
    document.body.append(group);
  }
  return group;
}
