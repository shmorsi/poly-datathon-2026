import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401
import re

t = open(OUT / "table.md").read()
t = re.sub(r"\$-([\d,\.]+)", r"−$\1", t)                 # $-207,146.34 -> −$207,146.34
t = re.sub(r"(?<![\w\-])-(\d)", r"−\1", t)                # -10.6065 % -> −10.6065 %
t = re.sub(r"[+−-]0\.0000 pt", "0.0000 pt", t)
t = t.replace("−0.0000 / −0.0000", "0.0000 / 0.0000").replace("+0.00 $", "$0.00")
t = t.replace("+0.29 $", "+$0.29").replace("−0.45 $", "−$0.45")
t = t.replace("Robert with 40 % NVDA", "Robert after (40 % NVDA)")

head = """# Lane accuracy: independent recompute of the headline numbers

Run 2026-11-15 by an independent script set in `scripts/audit_independent/` (`core.py`, `daily.py`, `events_ind.py`, `deep_ind.py`,
`report.py` and the checks named below), Python 3 + pandas/numpy from the repo's `.venv`, every script run with `-I`.
**No repository module was imported**: the code was written from `docs/finance_methods.md` (sections 2 to 4 and Appendix C)
and the raw files only. Compared against the saved runs `$EPI_AUDIT_RUNS/{robert,mateo,amira,canadian}.json` (as_of
2026-11-12, run at repo commit 934bfe4). No AWS call, no repo file written.

**Result: 32 of 32 listed figures OK, 0 CHECK, 0 WRONG.** Every value of mine rounds to the page value, and the largest
gap with the engine's unrounded value is 0.009 pt (look-through, explained in row 14) or $0.45 (whole-dollar display).
Most values agree to 1e-12. The engine's code, read after my recompute, implements the documented methods. I found one
CHECK outside the brief's list (the "89 %" in the storm reasons, below; it is not rendered on the page) and three
wording or provenance notes in the methods doc.

Gap = my value − the engine's unrounded value in the saved run (pt = percentage point). The page value is the engine's
value rounded for display (0.1 pp, ROUND_HALF_UP; dollars to the dollar). Rule: CHECK if a gap is above 0.1 pt or
$100, or if my value does not round to the page value.

"""

method = """
## How each number was rebuilt (my code, the documented method)

- **Market tables.** `adj_close` in the listing currency; CNQ.TO × 1.021 before 2022-08-22; union TSX+US calendar
  from the price file: **1,282 sessions** (doc: 1,282), **37 without their own Bank of Canada rate** (doc: 37); fill at most 3
  days; USD/CAD carried forward, never back-filled; USD lines × USD/CAD. **Path:** constant weights rebalanced daily,
  base 100. A day counts only if a held line's exchange traded, so the all-TSX "Too Canadian?" mix runs on 1,255 TSX
  sessions; its volatility matches the engine to 1e-10, which shows the engine applies the same rule. **Metrics:** drawdown
  against the running high (base included); CAGR over calendar days / 365.25; dollars = amount × drawdown; end value = amount ×
  last level / 100.
- **Size curve.** `set` NVDA to x% from today's mix (others × (1 − x)), 0 to 40 % in 1 % steps, floor compared after
  ROUND_HALF_UP to 0.1 pp. All 41 points equal the engine's to 1e-15. 8 % reads −15.000040 % (shown −15.0 %, inside); 9 %
  reads −15.640878 % (fails). The 25-start-month band (T58/T59, 9 % to 35 %) is also equal, start by start.
- **Risk.** Sample covariance (ddof 1) of the daily CAD returns on the counted days; RC_i = w_i(Σw)_i / w'Σw; Meucci
  ENB = exp(−Σ p_k ln p_k) over the eigenvectors of Σ.
- **Look-through.** Σ weight × the ETF's CAN country row (direct `.TO` lines = CAN, NVDA = USA, GLD = GLOBAL) from
  `data/etf_holdings.csv`.
- **Shock check.** My own engine: I re-derived the dating rule from `announced_at` (37 of 37 dates match `date`). It uses
  per-asset t0 and a per-asset baseline (the last own-exchange price before t0; crypto: the row dated announced − 1 day).
  Weights are fixed at t−1 and held. Campaign episodes merge same-family, same-sign events whose [t−1, t+20] windows
  overlap. The trough is the lowest point over the episode, clipped at 0. Rule B: a co-event of another family dated after
  the first t0 and on or before the trough makes the episode mixed; it is then scored up to the co-event's t0 and counts if
  that span holds at least 5 sessions. This reproduces **all 24 family × mix results** (6 mixes × 4 families: worst, n and
  label) exactly, including Amira's crypto baseline. Robert after: tariff_threat_2024 and cusma_2026 drop out (4 sessions
  each before hbm_2024 / ceasefire_end_2026); canada_50_2026 counts on its 12 sessions before saudi_pipeline_2026.
- **Deep history.** Monthly CAD proxy returns from `panel.csv`; XIU.TO→CA_EQ, XBB.TO→CAD_BOND, ZST.TO→CAD_TBILL,
  GLD→GOLD, NVDA→CHIPS; constant weights rebalanced monthly; base 1 at the end of the month before the window starts.
  All **33 values (11 episodes × today / after / chips alone)** equal the engine's. With the base taken at the end of the
  first month instead, 4 of the 33 values differ (for example 1973–74 chips alone −53.8 %), so the engine uses the right base.
- **The panel itself, rebuilt from the raw downloads** over the three windows: CHIPS = French 49 "Chips" × the FRED
  DEXCAUS month-end move, USDCAD_END = FRED month-end, GOLD = World Bank × FRED EXCAUS monthly-average move, CA_EQ = French
  Canada local-currency block (2000–02, 2008–09) and the StatCan TSX close + the previous month's yield / 12 (1973–74,
  vectors found by their labels), CAD_BOND = the 2/4/7.5/20-year par-bond ladder from StatCan 1–3/3–5/5–10/10+ yields
  (standard constant-maturity formula), CAD_TBILL = previous month's 3-month yield / 12. **Every column is exact to
  0.00001 pp.** The 9 raw files and `panel.csv` match their manifest SHA-256. The ladder weights (28/22/21/29 %) are a
  stated assumption that I could not check against XBB.TO.

## Wider checks (page figures beyond the list; all equal the engine)

Mateo's price of values (CNQ.TO removed): −12.89 %, war & oil −5.77 %, CAGR 9.79 %. Too Canadian?: XIU.TO's risk share 90.0
→ 63.9 %, Canada's share of the risk 97.5 → 68.3 % (equal after the same country-row rescaling), bets 1.14 → 1.39. Amira:
NVDA 15.98 % direct + inside QQQ, Information Technology 37.54 %. Robert's ladder rows: SPY or QQQ at 40 % give −14.20 % and −18.37 %,
end values $1,021,677 and $1,049,726. Recovery 416 / 187 days.

## Sensitivity of the method choices my code shares with the engine (a shared choice cannot be caught by agreement)

| Choice | Test | Effect on the listed figures |
|---|---|---|
| CNQ.TO × 1.021 before 2022-08-22 | Direction checked on the raw rows: corrected day +0.665 %; true total return (price + the 0.75 dividend) +0.608 %; raw +2.779 % | Right fix. Mateo's worst fall unchanged without it (the low is 2022-07-14); only his CAGR moves (+0.04 pt) |
| Rule B co-events of either sign | Negative-only co-events | None (tariff n = 6, −5.96 % / −8.99 %) |
| USD line's baseline on a TSX-only t−1 | The union-calendar t−1 price instead of the asset's own session | None |
| Daily covariance | Weekly (Friday) returns | NVDA's risk share 90.0 % (vs 89.6 %), bets 2.35 → 1.18 (vs 2.43 → 1.16): the claim is robust |
| ROUND_HALF_UP before the floor | Raw comparison | The first failing size would read 8 %, not 9 % (documented as pitfall 5; the page says "between 8 % and 9 %") |
"""

extra = """
## Findings outside the brief's list

**1. CHECK: "89 % of your money is there" (Robert's storm reasons) vs Canada's 87.6 %.** In Robert's run,
`scenario.reasons`, `scenario.weather.precedents[].why` and `scenario.keyword_result.reasons` say, for all five tariff
precedents, *"it hit CAN, and 89 % of your money is there"*. The money in Canada is 87.6 %. The 89 % is CAN 87.63 % + USA
1.77 % = 89.40 %. Cause: `agents/scenario.py:226` sums the money over **every** region of the event
(`share = … for r in ev_regions`), but `_reason_text` (`:514-515`) prints that sum next to `overlap`, which keeps only the
regions holding at least 5 % of the money (USA's 1.8 % is left out). Reach: the Result JSON and API only. The page renders the precedent ids,
not this text (no reader in `web/`), and no verdict or number check uses it. Exact fix (owner the AI lead, `agents/**`); the
ranking score keeps `share`, so no precedent pick moves:

```diff
@@ agents/scenario.py search_events
         share = round(min(1.0, sum(float(countries.get(r, 0.0)) for r in ev_regions)), 4)
+        named = round(min(1.0, sum(float(countries.get(r, 0.0)) for r in overlap)), 4)   # the money in the regions the text names
@@
-                     "features": {"family_match": match, "region_overlap": overlap, "exposure_share": share,
+                     "features": {"family_match": match, "region_overlap": overlap, "exposure_share": share, "named_share": named,
@@ agents/scenario.py _reason_text
-        if f["exposure_share"] > 0:
-            hit += f", and {round(f['exposure_share'] * 100)} % of your money is there"
+        named = f.get("named_share", f["exposure_share"])
+        if named > 0:
+            hit += f", and {round(named * 100)} % of your money is there"
```
After the fix the text reads "88 %", the whole-percent form of 87.6 %. Add a test: Robert's today exposure with a
`USA;CAN` event gives "88 %".

**2. Doc wording (owner the data lead, `docs/finance_methods.md` §2 step 2; the numbers are unaffected).** "The cross-check:
the unadjusted close of that day moved +0.61 %" is not accurate. The pack's `close` is split-adjusted, and Yahoo treated 1.021
as a split, so every CNQ.TO close before 2022-08-22 is divided by 1.021 (for example 35.4505 × 1.021 = 36.195, a clean
pre-split-halved price). The +0.61 % matches the true total return (price −1.46 % + the 0.75 dividend, 2.07 % of the
price, = +0.61 %) only because the phantom factor cancels the dividend drop. Suggested text: "the split-adjusted close, which
carries the same 1.021 factor, moved +0.61 %; that equals the day's true total return (price −1.46 % plus the 0.75
distribution, 2.07 %), so the corrected +0.67 % is right and the raw +2.78 % counts the distribution twice."

**3. Stale doc lines and a provenance gap (owner the data lead).** §2's deep-history row says the download "was not complete
… so it quotes no deep-history number". The run and the page now show 11 episodes. The same row says `fetch_deep.py`
"writes URL, time, SHA-256", but the manifest has `"retrieved_at": "not recorded"`. The hashes do match (9 of 9 + panel).
The run's own `deep_history.source` says "Data retrieved: not recorded". Fix: record the retrieval time on the next fetch,
or write "time not recorded" in §2 and update the "quotes no number" sentence.

**Knife edges (not defects, already disclosed):** the 8 % size passes by 0.00004 pp; the tariff check rests on Liberation
Day's dating (−4.5 % one session later, §8). **Latent, not triggered:** `series_from_market` books 0 % for a line with no
price yet (`fillna(0.0)`) and carries prices over a flagged gap. This is documented and backed by the missing-data warn, and no
ticker is flagged on this data.
"""

open(OUT / "accuracy.md", "w").write(head + t + method + extra)
print(open(OUT / "accuracy.md").read()[:2500])
