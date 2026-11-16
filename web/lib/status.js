/* EPICENTRE Replay: the page's one status vocabulary (lane U5 owns it; #checklist, #record and #how import it so every section
   names a check and a floor the same way). Pure: no DOM, no globals, no network. Tests: tests/web_status_test.mjs.
   The server decides every status, tier, verdict and whether a floor broke (one judge, red gate 2); this module only names them.

   1. A check's status, in the tone of what the row did to the verdict (governance.verdict): only a hard limit that broke reads
      "Outside" with the octagon; a soft limit or a preference that broke, and any warning, read "Caution" (they can only add a
      caveat); a pass reads "Inside". The tier decides the octagon, never the colour alone (status = icon + word).
   2. What a fall did to the floor, for what-if rows (other bets, other crises): "Broke your floor", "Touched your floor" (beyond
      it by 1 point or less, ruling R11), "Held above your floor"; a neutral word with no pass mark (no green, no check icon), so
      an alternative the investor never asked about never reads as approved. */

/* the standing line under EVERY verdict (the regulation flaw hunter, CRITICAL, Sun 15 Nov): whatever the question was, the answer
   compares what already happened with the investor's own limits and never says whether to act. One text for the whole page. */
export const STANDING_LINE = "This compares what the move already did with the limits shown here. It does not say whether to make it.";
export const STANDING_LINE_MIX = "This compares what your mix already did with the limits shown here. It does not say what to do with it.";
export const standingLine = (hasMove) => (hasMove ? STANDING_LINE : STANDING_LINE_MIX);

export const SHOWN = Object.freeze({
  outside: Object.freeze({ word: "Outside", tone: "outside", icon: "i-out" }),
  caution: Object.freeze({ word: "Caution", tone: "caveat", icon: "i-warn" }),
  inside: Object.freeze({ word: "Inside", tone: "inside", icon: "i-in" }),
});

/* a check row's display status from the server's status and tier; null for an unknown status (the row shows its reason) */
export function shownStatus(status, tier) {
  if (status === "fail") return tier === "hard" ? SHOWN.outside : SHOWN.caution;
  if (status === "warn") return SHOWN.caution;
  if (status === "pass") return SHOWN.inside;
  return null;
}

/* the marker on the row that set the verdict: only a broken hard limit "decided the verdict" (Outside your limits); a soft
   limit, a preference or a warning "added the caveat" (Inside, with caveats), so the marker never contradicts the lamp */
export function bindingWord(status, tier) {
  if (status === "fail" && tier === "hard") return "Decided the verdict";
  if (status === "fail" || status === "warn") return "Added the caveat";
  return null;
}

/* the rule in one sentence, for a legend under any list of checks */
export const STATUS_LEGEND = "A hard limit decides the verdict on its own; a soft limit, a preference or a warning level can only add a caveat.";

export const FLOOR_WORDS = Object.freeze({ broke: "Broke your floor", touched: "Touched your floor", held: "Held above your floor" });

/* a fraction in tenths of a percentage point, ties away from zero (web/lib.js tenths, governance.round_pp) */
function tenths(x) {
  return Math.sign(x) * Math.round(Number((Math.abs(x) * 1000).toPrecision(12)));
}
const isNum = (x) => typeof x === "number" && Number.isFinite(x);

/* what a worst fall did to the floor. `beyond` is the server's own judgement (beyond_floor, after round_pp): false = held,
   true = beyond it, then named "touched" when the margin is 1 point or less (R11) and "broke" otherwise; a server class
   ("broke" | "touched" | "held", e.g. deep_history) is taken as it is. null when the server did not say. */
export function floorClass(depth, floor, beyond) {
  if (beyond === "broke" || beyond === "touched" || beyond === "held") return beyond;
  if (beyond === false) return "held";
  if (beyond !== true || !isNum(depth) || !isNum(floor)) return null;
  return Math.abs(tenths(depth) - tenths(floor)) <= 10 ? "touched" : "broke";
}

/* the words for a floor class, with a neutral tone (never "inside", never the check icon) */
export function floorWord(cls) {
  return Object.prototype.hasOwnProperty.call(FLOOR_WORDS, cls) ? { cls, word: FLOOR_WORDS[cls], tone: "neutral" } : null;
}
