# An independent re-implementation of the headline numbers

**What.** A separate agent (2026-11-15) rebuilt the page's headline figures from
[finance_methods.md](finance_methods.md) (sections 2 to 4 and Appendix C) and the raw files alone, in its own code: it
shares no code with the engine and imports no module of this repository (every script runs with `python -I`). Its
values were compared with the saved runs (as_of 2026-11-12, run at commit 934bfe4). No AWS call.

**Result.** All 32 headline figures below are OK, and the 33 deep-history values (11 crises x today, after the move and
the chip industry alone, `deep_ind.py`) equal the engine's to 2.2e-16. Most gaps are 0; the largest are 0.009 point
(Canada's look-through share: XIU.TO's country rows sum to 100.02 %, and the engine rescales them) and $0.45 (the page
shows whole dollars). A row is OK when the recomputed value rounds to the page value and is within 0.1 point (or $100)
of the engine's unrounded value.

**Reproduce.** `EPI_AUDIT_RUNS=<the four saved runs> .venv/bin/python -I scripts/audit_independent/report.py` prints this
table ([README](../scripts/audit_independent/README.md); it needs the licensed starter pack, the ETF holdings file and the
deep-history cache, none of them committed).

| # | Number | Page value | My value | Engine (saved run, unrounded) | Gap | Verdict |
|---:|---|---|---|---|---|---|
| 1 | Robert today: worst fall | −10.6 % | -10.6065 % | -10.6065 % | +0.0000 pt | OK |
| 2 | Robert with 40 % NVDA: worst fall | −34.5 % | -34.5244 % | -34.5244 % | +0.0000 pt | OK |
| 3 | …its dollars on $600,000 | −$207,146 | $-207,146.34 | $-207,146.34 | +0.00 $ | OK |
| 4 | …its peak / trough dates | 2021-11-29 / 2022-10-14 | 2021-11-29 / 2022-10-14 | 2021-11-29 / 2022-10-14 | 0 | OK |
| 5 | Robert today: peak / trough dates | 2022-03-04 / 2022-10-11 | 2022-03-04 / 2022-10-11 | 2022-03-04 / 2022-10-11 | 0 | OK |
| 6 | CAGR today | 8.7 % | 8.7284 % | 8.7284 % | +0.0000 pt | OK |
| 7 | CAGR after | 25.2 % | 25.2218 % | 25.2218 % | +0.0000 pt | OK |
| 8 | End value today (2026-11-12) | $911,676 | $911,676.29 | $911,676.00 | +0.29 $ | OK (page shows whole dollars) |
| 9 | End value after | $1,847,077 | $1,847,076.55 | $1,847,077.00 | -0.45 $ | OK (page shows whole dollars) |
| 10 | First NVDA size that breaks the −15 % floor | 9 % | 9 % | 9 % | 0 | OK (8 % reads −15.00004 %, inside only after ROUND_HALF_UP) |
| 11 | Worst fall with 2022 left out (from 2023-01-01) | −16.9 % | -16.9246 % | -16.9246 % | +0.0000 pt | OK (2025-01-23 → 2025-04-08) |
| 12 | NVDA's share of the risk (Euler, daily cov.) | 89.6 % | 89.6205 % | 89.6205 % | +0.0000 pt | OK |
| 13 | Independent bets today → after | 2.4 → 1.2 | 2.4301 → 1.1570 | 2.4301 → 1.1570 | -0.0000 / -0.0000 | OK |
| 14 | Canada's share of the money today (look-through) | 87.6 % | 87.6430 % | 87.6342 % | +0.0088 pt | OK (engine rescales XIU.TO's country rows (sum 100.02 %)) |
| 15 | Canada's share of the money after | 52.6 % | 52.5858 % | 52.5805 % | +0.0053 pt | OK (same rescaling) |
| 16 | Tariff shock check, after (worst clean episode) | −9.0 % | -8.9901 % | -8.9901 % | +0.0000 pt | OK (liberation_day_2025, low 2025-04-08) |
| 17 | …separate clean tariff episodes | 6 | 6 (Indicative) | 6 (Indicative) | 0 | OK |
| 18 | Mateo: worst fall | −11.4 % | -11.4318 % | -11.4318 % | +0.0000 pt | OK |
| 19 | Amira: worst fall | −41.3 % | -41.3462 % | -41.3462 % | -0.0000 pt | OK |
| 20 | Too Canadian? + 20 % SPY, unhedged: worst fall | −12.9 % | -12.9021 % | -12.9021 % | +0.0000 pt | OK |
| 21 | …CAD-hedged stand-in: worst fall | −14.2 % | -14.1990 % | -14.1990 % | +0.0000 pt | OK |
| 22 | SPY 2022, US dollars | −18.2 % | -18.1754 % | -18.1754 % | +0.0000 pt | OK |
| 23 | SPY 2022, Canadian dollars | −12.6 % | -12.5861 % | -12.5861 % | +0.0000 pt | OK |
| 24 | Deep 1973–74: today | −15.2 % | -15.2229 % | -15.2229 % | +0.0000 pt | OK (by proxy, monthly; $91,337) |
| 25 | Deep 1973–74: after | −29.6 % | -29.5719 % | -29.5719 % | +0.0000 pt | OK (by proxy, monthly; $177,432) |
| 26 | Deep 1973–74: US chip industry alone | −57.3 % | -57.2819 % | -57.2819 % | +0.0000 pt | OK (by proxy, monthly) |
| 27 | Deep 2000–02: today | −11.3 % | -11.2793 % | -11.2793 % | +0.0000 pt | OK (by proxy, monthly; $67,676) |
| 28 | Deep 2000–02: after | −50.4 % | -50.4390 % | -50.4390 % | +0.0000 pt | OK (by proxy, monthly; $302,634) |
| 29 | Deep 2000–02: US chip industry alone | −82.5 % | -82.5369 % | -82.5369 % | +0.0000 pt | OK (by proxy, monthly) |
| 30 | Deep 2008–09: today | −17.0 % | -16.9600 % | -16.9600 % | -0.0000 pt | OK (by proxy, monthly; $101,760) |
| 31 | Deep 2008–09: after | −23.7 % | -23.7424 % | -23.7424 % | +0.0000 pt | OK (by proxy, monthly; $142,454) |
| 32 | Deep 2008–09: US chip industry alone | −40.1 % | -40.1000 % | -40.1000 % | +0.0000 pt | OK (by proxy, monthly) |

**What agreement cannot catch.** This code follows the same documented methods, so a choice both make is not tested
by agreement; the a separate reviewer agent such choices one at a time. Counting co-events of either sign or only negative ones gives
the same tariff check (`sensitivity.py`); weekly instead of daily returns moves NVIDIA's share of the risk from 89.6 % to
90.0 % (`sensitivity.py`; the claim stands); comparing the raw values instead of the values rounded to 0.1 point
would put the first failing size at 8 %, not 9 % (8 % reads −15.00004 %; pitfall 5); with the deep history's base at the end of the first month instead of the month before, 5 of the 33
values differ (`deep_ind.py`), so the agreement also confirms the documented base; `claims.py` checks on the raw rows
that the CNQ.TO correction goes the right way.

**Found outside the list (status).** A text-only mismatch in Robert's precedent reasons ("89 % of your money is there"
sums every region of the event, while Canada holds 87.6 %): it is not rendered on the page and changes no verdict or
number check; open, owner `agents/scenario.py`. Two notes in [finance_methods.md](finance_methods.md) section 2 (the
CNQ.TO close wording; the deep-history row's stale lines and the manifest's missing retrieval time): corrected.

This already happened; it is not a forecast. Educational simulation. This is not financial advice.
