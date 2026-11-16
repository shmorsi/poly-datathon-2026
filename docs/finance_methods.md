# EPICENTRE finance methods

The definitions, data, checks and limits behind every number the product shows. It is written from the code and the data as they stand on the day of the run (section 1); the technical documentation reuses its finance sections.

## At a glance

- **What it is.** The definitions, data, checks and limits behind every number EPICENTRE shows for four fictional investors: history, not a forecast; team assumptions, not regulation.
- **Against the issuers.** Our total returns match the funds' published returns within 0.15 pp on 12 of 12 figures (largest gap 0.06 pp; Wilson 95 % interval 75.8 % to 100 %; Indicative, N = 12 on four funds; section 7).
- **Against a second reader.** An independent script on the raw files equals the tools on 4 of 4 mixes (Wilson 51.0 % to 100 %; Indicative; Appendix C), and the risk-share and independent-bets bounds fail on 0 of 500 re-drawn test fixtures (Wilson 0.0 % to 0.8 %; Measured; section 8).
- **Four verdicts.** Robert is inside his limits today and outside them after putting 40 % in NVIDIA (worst drop −34.5 % against his −15.0 % floor). Mateo and Amira are inside, with caveats (the values screen; the crypto cap). "Too Canadian?" is inside today and after, while Canada's share of the risk moves from 97.5 % to 68.3 % (section 9).
- **Robustness.** Robert's verdicts hold in 4 of 4 re-judged variants (shock dates one session earlier or later; history from 2022-01-03; Wilson 51.0 % to 100 %; Indicative). One session later the tariff shock check reads −4.5 % instead of −9.0 % for the after mix, which is why it is a caution and never the rule that decides (section 8).
- **Three limits that matter.** Five years are one regime; the 37 shocks were chosen in 2026 with hindsight; costs, taxes and real portfolios are not modelled (section 10).

## 1. What this is

- **Team assumptions, not regulation.** The limits, thresholds and rules below are EPICENTRE's documented assumptions (spec §5). The investor's own answers set the limits; the starting values are marked ◐ and can be edited. Nothing here is advice: the product says "inside" or "outside the limits you set".
- **Fictional investors, fictional money.** Robert, Mateo, Amira and "Too Canadian?" are fictional (the case's three personas and the workshop's own question). A dollar figure applies a real drawdown to a fictional amount: the drawdown is ● fact, the dollars are ○ fiction ("would have been").
- **History, not a forecast.** "This already happened; it is not a forecast." Returns are nominal, in Canadian dollars, before inflation, trading costs and taxes (ETF prices already carry their fund fees).
- **Kinds.** ● fact: computed from the data. ◐ assumption: a rule, a threshold or a proxy we chose, or a limit the investor typed. ○ fiction: a fictional amount or mix.
- **The run.** Every number below was re-run on 2026-11-15 from main at commit dde82c7 (fund pages, filings and the holdings rebuild were read on 2026-11-14), on the starter pack retrieved 2026-11-13 (Python 3.12.15, numpy 2.5.4, pandas 3.1.1). Appendix B lists the commands.
- **Evidence labels.** Two uses of the words Measured and Indicative. For a shock family the product's label counts separate clean episodes: Measured is 3 or more and none mixed, Indicative is 1 or 2 or a mixed one used, Can't say is none (section 3). For a rate this document measures, the label counts trials: Measured is N of 30 or more, Indicative is N below 30, and the rate is written k / N with its Wilson 95 % interval, its date, whether a model was involved and its limit.

## 2. Data and processing

| File | Source, dates, size | Processing | Licence and where it lives |
|---|---|---|---|
| `assets_universe.csv` | Organizers' AlphaForge pack, compiled 2026-11-13: 31 assets (20 stocks, 4 stock ETFs, 4 bond ETFs, 1 gold ETF, 2 crypto) | Read with pandas only; the pack's `build_dataset.py` is never run (untrusted download). Sector labels are the organizers' own | Free to use within the datathon (the pack's own terms); `data/starter/` is gitignored and never committed |
| `prices_daily.csv` | Yahoo Finance via yfinance, retrieved 2026-11-13; 2021-11-12 to 2026-11-12; 40,049 daily rows in the listing currency (`.TO` CAD, the rest USD) | Adjusted close; one correction; union calendar; bounded fill; USD to CAD (below) | Yahoo's terms (legal.yahoo.com/us/en/yahoo/terms/otos/index.html, as recorded in the pack on 2026-11-13); we have not confirmed that they allow redistribution, so the file is never committed |
| `corporate_actions.csv` | Same download; 658 rows by ex-date (651 dividends, 7 splits) | Dividends feed the trailing yield (CAD, ex-date rate); may be incomplete for ETFs | Yahoo's terms, as for prices; never committed |
| `fx_usdcad_daily.csv` | Bank of Canada Valet, series FXUSDCAD; 1,245 rows; no rate on Canadian holidays | Carried forward, never back-filled | Bank of Canada's terms (bankofcanada.ca/terms/); not committed |
| `macro_rates.csv` | Bank of Canada and FRED; 8,281 long-format rows, 2021-11-01 to 2026-11-12 | Only the Bank of Canada policy rate (V39079) is read: the Sharpe ratio's risk-free rate and the shaded hiking cycle. Yields, CPI and unemployment are not used in any verdict (monthly rows are dated to the reference month, not the release date) | The Bank of Canada rows under the Bank of Canada's terms; the FRED rows under FRED's terms (fred.stlouisfed.org/legal/; the originals are U.S. government agencies, the Federal Reserve Board and the Bureau of Labor Statistics); not committed |
| `data/events.csv` | 37 shocks, each with a source URL on 13 hosts and `verified_on` 2026-11-14 (section 4) | Date by the dating rule; text in English and French | Our own work: team-written summaries of public announcements (91 to 267 characters), one source link per row; the figures in a summary come from the cited page and are never shown as results. Committed |
| `data/esg_flags.csv` | 8 rows: Vanguard's published ESGV exclusion categories and companies' own annual filings (section 6) | Dated by source; no disclosure, no flag | Our own work, except one short quotation (20 to 450 characters) from a company's own annual filing in each of the five controversy rows, cited with its document, section and date; the three category rows restate Vanguard's published criteria. Committed |
| `data/etf_holdings.csv` | 166 rows for 9 ETFs from the issuers' own pages and files; holdings as of 2026-11-12 (section 5) | Exposure only; top 25 or 26 holdings plus sector and country splits | The issuers' terms forbid redistributing holdings: local only (gitignored), rebuilt by `scripts/fetch_holdings.py` |
| `data/personas.json` | Fictional investors, limits, six illustration mixes | English keys; limits read through `governance.load_limits` | Our own work: fictional investors, limits and mixes, no real client data. Committed |
| `data/deep_episodes.csv`, `data/deep_proxies.csv`, `data/cache/deep/` | 11 earlier crises (1973 to 2020) and 31 proxy rows; monthly panel from Kenneth French Data Library, Statistics Canada tables 10-10-0122-01 and 10-10-0125-01, FRED USD/CAD and World Bank gold | `scripts/fetch_deep.py` writes URL, SHA-256 and licence per file; the manifest of the download used here records no retrieval time (`"retrieved_at": "not recorded"`, so the page says "Data retrieved: not recorded"), and its 9 raw files and the panel match their SHA-256. A ◐ proxy disclosure shown beside the verdict, never inside it. The 11 crises are on the page; their numbers live in each run's `deep_history`, re-computed independently in [audit_independent.md](audit_independent.md), and this document quotes none | Statistics Canada Open Licence; World Bank Pink Sheet CC BY 4.0, where the gold price is the LBMA fix, a third-party input (LBMA's own price files are not used); FRED public domain, citation requested; the Kenneth French library states no licence, so raw files stay local and uncommitted |

**Processing, in this order (spec §9).**
1. **Adjusted close.** `adj_close` (back-adjusted for splits and dividends) in the listing currency, so a gain or a fall is a total return. Splits are already inside it.
2. **One correction.** On 2022-08-22 the pack lists CNQ.TO with a CAD 0.75 dividend and a 1.021 "split" on the same ex-date; the pack's own README notes that CNQ did not split its shares and that the factor likely reflects a special distribution, which `adj_close` then counts twice. The raw day reads +2.78 %, the corrected day +0.67 %. The cross-check: the pack's `close` is split-adjusted, so it carries the same 1.021 factor, and it moved +0.61 % that day; that equals the day's true total return (the price −1.46 % plus the 0.75 distribution, 2.07 % of the price), so the corrected +0.67 % is right and the raw +2.78 % counts the distribution twice. `adj_close` dated before 2022-08-22 is multiplied by 1.021 (this ticker only; a test pins +0.67 %). The gap, about 2.1 pp, is the kind of error the reconciliation tolerance (section 7) is built to catch.
3. **Calendar.** The union of TSX and US trading days: 1,282 sessions from 2021-11-12 to 2026-11-12. Crypto (UTC days, seven a week) is sampled on those days and never adds one.
4. **Fill.** A price is carried forward at most 3 days; a longer gap is flagged "missing data" and left empty. On the full history no ticker of the 31 is flagged.
5. **Currency.** USD/CAD is carried forward from the last Bank of Canada rate (37 of the 1,282 sessions have no rate of their own) and never back-filled with a later one. USD lines times USD/CAD give CAD; a USD price before the first rate is flagged, never converted.
6. **No look-ahead.** Everything dated after `as_of` is dropped before any pivot, fill, join or computation. A real-data test (`tests/test_data.py`, `as_of` 2025-01-31) scrambles every later row of prices, FX, macro and dividends and requires identical market tables; the sealed-envelope proof repeats it for a whole decision.
7. **Holdings weights.** `data/etf_holdings.csv` weights are fractions. `scripts/fetch_holdings.py` writes up to 8 decimals: harmless, because the issuers publish two decimals of a percent, so a longer fraction is the same figure, not more precision. QQQ and ESGV rows, and SPY's sector split, are typed by a person from the fund page (Invesco's terms bar automated extraction; Vanguard offers no file).

## 3. Methods and why

Each paragraph gives the reason first, then the exact definition (spec §10). The limits are the investor's answers; the starting values by tolerance band (`data/personas.json`) are ◐ assumptions:

| Band (from "in 2022 you sold / held / bought more") | Floor: worst drop | One company | One sector | Crypto |
|---|---:|---:|---:|---:|
| Low (sold) | −15 % | 10 % | 30 % | 0 % |
| Moderate (held) | −25 % | 10 % | 35 % | 0 % |
| High (bought more) | −45 % | 20 % | 40 % | 10 % |

Other thresholds: the shock check limit is 0.5 of the floor; the values screen warns at 1 % of the money inside funds; every comparison rounds to 0.1 pp; recovery may take 0.3333 of the horizon; "short horizon" is under 3 years; one line carrying more than 50 % of the risk is a warning.

**Constant weights, rebalanced to target every day (base 100, CAD).** The weights a rule checks must be the weights the drawdown measures, so one definition serves the drawdown, the risk shares and the size curve. (Inside one storm's window the weights are instead fixed on the day before the storm and held, so that each asset's own start day composes exactly; the storm numbers below use that convention.) A day counts when at least one held asset's exchange traded, and returns run between consecutive counted days (a USD line keeps the USD/CAD move of a TSX-only day). This is a ◐ assumption: a real investor drifts between rebalancing dates.

**The worst drop, not the end-to-end return.** A floor is about the worst point on the way, and a start date can hide it. Maximum drawdown is the lowest value against the running high, with its peak and trough dates; recovery is the calendar days from the trough back to the previous peak (none = not recovered); the worst 12-month fall is shown beside it so the start date does not do the work. CAGR uses calendar days / 365.25, volatility is the daily standard deviation times √252, and the Sharpe ratio is (CAGR − the mean Bank of Canada policy rate) / volatility. **Every dollar loss is the fictional amount times the drawdown**, so a loss and a floor in dollars share one base: Robert's current mix would have lost $63,639 at its worst, on a drawdown of −10.6 %.

**A storm's trough, not its 20-day return.** A storm that rebounds fast hides its worst point. `event_impact` reports the trough (the lowest value from t0 to t+20 against the day before, clipped at 0) and the 20-day return separately. Liberation Day (2025-04-03): Robert's current mix troughs at −6.0 % on 2025-04-08 yet stands only −0.9 % after 20 sessions (the low came the day before the 90-day pause of 2025-04-09, which the catalog lists as a relief event); with 40 % NVIDIA the same figures are −9.0 % and −0.5 %.

**Per-asset t0 and the crypto baseline.** Exchanges close on different days, so one "day 0" would misread a storm. t0 is the first day each asset's own exchange trades on or after the shock date (the TSX was closed on 2023-10-09 while US markets traded), and its baseline is the last price before it. Crypto rows are UTC days, so its baseline is the row dated the announcement day minus one.

**Campaign episodes.** A campaign of announcements (tariff orders, then their effective date) is one fall; counting each headline would count one fall many times. Same-family, same-sign events whose [t−1, t+20] windows overlap form one episode, named after its first event; its trough is measured from the first event's t−1. The 37 events make 32 episodes: 28 loss episodes and 4 relief episodes (positive events never join a loss episode or enter a loss range), and 5 campaigns contain two events.

**Rule B: mixed episodes.** A fall that another headline explains must not be charged to this family. An episode is mixed only if an event of another family is dated after its first t0 and on or before its trough date (an event after the low cannot explain it); the page names the co-event. A mixed episode is first scored on its drop up to the co-event's t0, and counts as clean on that window when it holds at least 5 sessions, with the full mixed trough shown beside it. Example, Robert's current mix: canada_50_2026 is scored on its 12 sessions before saudi_pipeline_2026 (−1.4 %; −2.2 % over the whole window).

**Evidence levels and the shock check.** The page must say how much history stands behind a number. Per family: n = separate clean episodes; **Measured** = 3 or more clean and none mixed; **Indicative** = 1 or 2 clean, or a mixed episode is used (the label names the co-event, "Indicative (mixed with saudi_pipeline_2026)"); **Can't say** = none. The shock check on the checklist is the worst clean-episode trough among the question's families (all four if none is named) against half the floor. Beyond the limit it is a **warn** ("Caution"), never a fail, and a caveat for the verdict when it rests on 2 or more separate episodes; inside the limit it passes. With no episode it is a warn that reads "no close precedent at this date"; with fewer than 2 separate clean episodes, a warn that reads "too few separate episodes to conclude": thin evidence never gives a pass or a fail, and neither warn ever counts toward the verdict, alone or next to another warn (R51): the row says why it could not conclude. It is always phrased with its count ("In the 6 separate earlier Tariff war episodes the worst clean one cost 6.0 %, inside half your floor (7.5 %)"), as history and never as a forecast. A single storm's number is quoted as "this storm", never as a family rule (single-storm numbers can flip on a tiny margin).

**Risk share and independent bets.** Ten stocks are not diversification; where the risk sits matters more than how many lines there are. Risk contribution RC_i = w_i (Σw)_i / (wᵀΣw), with Σ the covariance of daily CAD returns up to `as_of`; the shares sum to 1 (a hedge such as gold can be negative). **Independent bets** is the effective number of bets of Meucci (2009), ENB = exp(−Σ p_k ln p_k) over the principal components of Σ: two lines that move together read about 1, two uncorrelated lines of equal risk read 2. It is never 1/ΣRC², which reads two near-duplicate lines as two bets (section 8 pins the difference). Robert's current mix: 2.43 bets, XIU.TO carrying 71.1 % of the risk on 45 % of the money; after the move, 1.16 bets, NVDA carrying 89.6 % of the risk on 40 % of the money.

**The floor: the stricter of capacity and tolerance.** What an investor would accept is not what he can afford (the workshop's "risk tolerance ≠ risk capacity"). The band floor comes from the 2022 reaction; the capacity floor is −(the largest loss he could absorb) / (the portfolio value); the floor is the one closer to zero, and the checklist says which one binds. On a tie the source is named "capacity", the investor's own dollar answer. Robert: band −25.0 %, capacity $90,000 / $600,000 = −15.0 %, so the floor is −15.0 %, set by capacity. Mateo ($62,500 of $250,000) and Amira ($36,000 of $80,000) equal their bands (−25.0 % and −45.0 %): ties, named capacity.

**Rounding to 0.1 pp, ROUND_HALF_UP.** Float noise must not tip a limit, and a percent is shown to one decimal. Every comparison uses the value rounded to 0.1 pp (ties away from zero: −15.05 % reads −15.1 %), and a limit fails only strictly beyond, so exactly at the limit passes. Robert with NVIDIA at 8 %: raw −15.00004 %, shown −15.0 %, passes; at 9 %: −15.6 %, fails.

**One weight operator, and the size curve from today.** A size answer must not drift between the weights a rule checks and the weights the series measures, so every change goes through one operator: `set` T to x makes T = x and scales every other line by (1 − x) / (1 − T_old); `add` x is `set` T_old + x; `replace` A with B gives B the weight of A. The size curve (`tipping_point` in `tools/allocation.py`) builds each size from today's portfolio, never from the previous size, and judges it with the same function as the verdict. Robert's curve runs NVIDIA from 0 % to 40 % in 1 % steps (41 points): no limit fails up to 8 %, the floor fails from 9 % (−15.6 %), and a second limit, one company above 10 %, fails from 11 %. It is history, not advice: "in this history the floor is crossed between 8 % and 9 %", never a size to reach.

**Fictional illustration mixes (test fixtures).** `data/personas.json` holds six mixes: low, moderate, moderate with ESG, high, high with crypto and high with ESG. They are computed and labelled "Fictional illustration, not a recommendation", and they never reach the screen (the product shows no model mix of named funds). They exist so that a test can check that a mix built for a band stays inside that band's floor; when one fails, the mix is adjusted, never the limits. Worst drops, 2021 to 2026: −9.2 %, −12.9 %, −19.2 %, −17.3 %, −21.3 % and −22.4 %, each inside its band's floor. The high mix sums to 100 % (15 XBB.TO, 30 XIU.TO, 20 SPY, 25 QQQ, 10 GLD).

**Trailing yield.** An income goal needs a yield made only of what was already paid. It is the dividends per share that went ex-dividend in the 365 days to `as_of` (special distributions included), in CAD at the ex-date rate, over the unadjusted CAD close of the last session on or before `as_of`, weighted by the portfolio. Robert today 2.4 %, after the move 1.6 %. History, not a forecast.

**Recovery, short horizon, missing data and the verdict.** The hard verdict rests on full-period evidence. The recovery rule warns only when the drop is deeper than half the floor and took longer than 0.3333 of the horizon to recover (Robert: 487 days for a 4-year horizon). The short-horizon rule warns when the money is needed in under 3 years. The missing-data rule warns when a held asset has a price gap over 3 days, and **a missing-data warn lifts the verdict to "Inside, with caveats" at best**: unknown is never a pass. Verdict: any hard fail (the floor, or with the values screen on a company owned directly that it excludes) gives "Outside your limits"; otherwise any soft or preference fail, a missing-data warn, a shock check beyond its limit that rests on 2 or more separate episodes, or two warnings give "Inside, with caveats"; otherwise "Inside your limits" (in code: Incompatible, Tension, Compatible). One cause counts as one fail: fails on the same holding count once. Look-through coverage is a disclosure, never a warning.

**Per-asset facts for the move picker (`data/asset_facts.json`).** The case asks for returns and volatility calculated over an explicit period, so each of the 31 starter assets carries its own facts, computed by `tools.metrics.asset_facts` and saved as derived numbers only, never a price. Period: the first day in the data to `as_of` (2026-11-12). Currency: CAD, from `adj_close`, USD lines converted with the Bank of Canada USD/CAD rate carried forward. Each asset is a one-line portfolio on the days its own exchange traded (prices carried over a gap; a gap longer than 3 days is listed in `flags`); crypto uses its own UTC days. Total return = last / first − 1; volatility = the daily standard deviation × √(the asset's own sessions a year, its returns / (calendar days / 365.25), ruling R36); the worst fall and its peak and trough dates as for a portfolio; `days` = the priced days behind them. Source: Yahoo Finance adjusted closes (AlphaForge starter pack, retrieved 2026-11-13). Licence: the file is committed because it holds derived figures only (returns, volatilities, falls, dates and day counts); the starter prices themselves stay local and are never committed (red gate 8). History, not a forecast. Rebuild: `.venv/bin/python -c "import json; from tools.metrics import asset_facts; open('data/asset_facts.json', 'w').write(json.dumps(asset_facts(), indent=1) + '\n')"`.

## 4. The shock catalog

**What is in it.** 37 announcements in four families: tariffs 13, war and oil 12, chips 7, rates 5. 33 are loss shocks and 4 are relief shocks (tariff_pause_2025, scotus_ieepa_2026, ceasefire_2026, peace_deal_2026). All 37 are known at 2026-11-12: each has its 20 sessions of data after it (the latest, saudi_pipeline_2026, is dated 2026-09-10). Each row carries a source URL and was read on 2026-11-14.

**Inclusion rule, written before any price was looked at.** An official or major-outlet-sourced announcement in one of the four families: a trade measure, an armed attack or ceasefire, an energy supply decision, a chip or export control, a central-bank or inflation surprise. The market reaction plays no role. Rows the research had set aside only for a modest reaction were therefore restored, because selecting on the outcome is exactly what the rule forbids: boc_100_2022, gallium_2023, red_sea_2023, hbm_2024, cusma_2026, canada_338_2026 and canada_50_2026. One row is an exception: deepseek_2025 is a model release, not one of the announcement types, but the chips family includes a major AI and chip industry shock reported by major outlets, and the spec names it.

**Candidates not added (12).** Five fall inside another event's window and the research wrote no row for them (us_strikes_iran_2025, canada_100_threat_2026, blockade_2026, late_july_2026, oct_escalation_2026). Three are outside the four families or not an announcement (china_duv_2026 is an industry report, midterms_2026 is political, ormuz_100_2026 is an oil price level). Four are unverified (section232_chips_2026, nvidia_ceo_2026, fed_first_hike_2022, uk_gilt_2022).

**Dating rule.** `announced_at` is US Eastern time on the day of the announcement: the time the source states when it gives one (code S), otherwise the part of the day it gives: before the US open (B, 08:00), during the session or not stated (M, 12:00), after the close, evening or night (A, 18:00). `date` is that day when it is a union-calendar session and the time is before 16:00, otherwise the next union session. Only the side of 16:00 and the calendar matter, so the placeholder times change no number. Of the 37 events, 22 fall on the session of their announcement, 7 on the next session because they came after the close, and 8 on the next session because they came on a weekend.

**Sign is the content of the announcement.** A relief event is a de-escalation announcement (a tariff pause, a court voiding tariffs, a ceasefire, a peace deal), decided from what was announced and never from the price move.

**Clean episodes per family, on Robert's current mix** (45 % XIU.TO, 35 % XBB.TO, 10 % GLD, 10 % ZST.TO; `turbulence`, 2026-11-12):

| Family | Loss episodes | Clean n | Worst (episode) | Mean | Evidence |
|---|---:|---:|---|---:|---|
| Tariffs | 8 | 6 | −6.0 % (liberation_day_2025) | −1.9 % | Indicative (mixed with saudi_pipeline_2026) |
| War and oil | 10 | 10 | −5.5 % (iran_2026) | −0.9 % | Indicative (mixed with canada_338_2026) |
| Chips | 7 | 7 | −2.6 % (hbm_2024) | −1.3 % | Measured |
| Rates | 3 | 3 | −4.6 % (jackson_hole_2022) | −2.3 % | Indicative (mixed with chips_2022) |

Which episodes are mixed depends on the portfolio, because rule B looks at each portfolio's own low. For this mix the tariff family has 8 loss episodes and **6 separate episodes count**: five have no other-family shock inside their fall, and canada_50_2026 counts on its 12 sessions before saudi_pipeline_2026. That one mixed episode makes the family **Indicative** rather than Measured. Two more tariff episodes (tariff_threat_2024, mixed with hbm_2024, and cusma_2026, mixed with ceasefire_end_2026) are mixed over their whole fall and are left out because enough clean ones exist. The tariff worst, −6.0 % at Liberation Day, is the same whether canada_50_2026 is scored on 12 sessions (−1.4 %) or in full (−2.2 %).

**The list.** Appendix A gives all 37 shocks with the announced time (US Eastern), the code of the dating rule, the first session, the family, the sign and the campaign each belongs to.

## 5. Sectors: ICB to GICS, and what the look-through can see

**Mapping.** The dataset's sector labels follow GICS. Invesco (QQQ) and Vanguard (ESGV) publish ICB sectors, which `tools/lookthrough.py` renames at read time with the weights unchanged: Technology → Information Technology · Telecommunications → Communication Services · Basic Materials → Materials · Consumer Discretionary, Consumer Staples, Health Care, Industrials, Utilities, Energy, Financials and Real Estate keep their names. Alphabet's two share classes are one company (GOOG is read as GOOGL).

**An upper bound.** ICB Technology includes Alphabet and Meta, which GICS files under Communication Services. So QQQ's 64.4 % and ESGV's 50.6 % "Information Technology" are upper bounds, and so is Amira's look-through technology share, 37.5 % of her money. It stays inside her 40 % sector cap, so the bound passes.

**Coverage is a disclosure.** The company-level rules (one company, the values screen) see only each fund's listed top holdings: XIU.TO 77.9 % of the fund (26 lines), SPY 51.8 % (25), QQQ 72.2 % (26, both Alphabet share classes) and ESGV 54.1 % (25). The sector rule reads the funds' own sector splits, which cover 100 %. Holdings are dated 2026-11-12 for all four; sector splits 2026-11-12 (XIU.TO, SPY), 2026-10-31 (QQQ) and 2026-09-30 (ESGV). This snapshot is used for "today" only: for a past decision date the look-through falls back to direct holdings and says so. Without the local holdings file it does the same, and then the one-company, sector and values rows are warns with no value that say the companies inside the funds are not known from holdings (a company already beyond its limit stays a fail).

**A 0.06 pp difference in XIU.TO's sector rows.** The local file carries the sector split from the fund page (Energy 16.65 %, rows summing to 99.99 %). `scripts/fetch_holdings.py` builds the same rows by summing the issuer CSV's two-decimal line weights (Energy 16.66 %, rows summing to 100.02 %). Re-run on 2026-11-14: the 26 holding lines are identical; 7 of the 11 sector rows differ, by at most 0.06 pp (the "Cash and/or Derivatives" line, 0.25 % summed against 0.31 % on the page). Across the four investors' portfolios, using either version moves any sector share by at most 0.02 pp.

## 6. The values screen

It is an **exclusion screen based on its sources, not an ESG score**, and the page says so. `data/esg_flags.csv` has two kinds of rows; tests pin the outcome of the research row by row.

**Category rows (3).** Vanguard's published ESGV exclusion categories (the ESGV page, undated, read 2026-11-14), applied to our stocks: owning proved or probable fossil-fuel reserves (CNQ.TO, XOM) and, per ICB, pipelines carrying fuels (ENB.TO). A category is a definition of the screen, so it applies at every date.

**Controversy rows (5).** A flag exists only where the company's own annual filing discloses a significant environmental or social legal proceeding (the significance rule below). The row keeps one exact sentence of the filing, the document, the section and the filing date, and counts only from that date (a filing is unknown before it is filed). Our own words never judge. Documents were read on each company's own investor site, never on sec.gov or SEDAR+, which require declared automation; JNJ's and PG's files are served from their investor-relations vendor's CDN and were accepted as company-published (a second reader could not re-confirm the link from each company's investor page).

| Ticker | Flag | Document and date | Section |
|---|---|---|---|
| CNR.TO | environmental | Annual report, 2026-02-04 (the report's own date) | Environmental matters |
| ENB.TO | environmental | Form 10-K, 2026-02-13 | Item 3, Legal proceedings |
| JNJ | social | Form 10-K, 2026-02-11 | Note 19, Legal proceedings |
| PG | environmental | Form 10-K, 2026-08-04 | Item 3, Legal proceedings |
| XOM | environmental | Form 10-K, 2026-02-18 | Note 7, Litigation and other contingencies |

CNR.TO's date is the report's own date: the PDF at the cited URL was generated later, so its public release date is not confirmed.

**The significance rule (Sun 2026-11-15).** The brief asks for *significant* environmental or social controversies, so a disclosed proceeding becomes a flag only when it is one of two kinds. **Environmental enforcement:** an action, penalty, order or agreement of a government authority, a liability designation, or a lawsuit brought by governments, over harm to air, water, land or climate from the company's operations or products (CNR.TO: the EPA names it a potentially responsible party for a contaminated site; ENB.TO: an agreement with Minnesota's DNR over an aquifer breach; PG: a UK Environment Agency civil penalty; XOM: climate suits by state and local governments). **Major social harm:** claims, at scale, of injury to people's health or safety from the company's products or operations, or human-rights abuses (JNJ: talc personal-injury claims). **Not significant, never a flag:** employment and pay disputes, and contract, commercial, securities, tax or competition litigation. The rule judges the kind of harm, not its size, because most filings give no size. Applied to the six disclosures read, it drops one: RY.TO's vacation pay class action (Annual report 2025-12-02, Note 24) is an employment-pay dispute, so RY.TO carries no row (tests pin it as read, disclosed, not significant). Mateo's warning inside his funds is then energy names and one environmental-enforcement name, all inside XIU.TO: 3.3 % of his money (ENB.TO 1.3 %, CNQ.TO 1.2 %, CNR.TO 0.8 %), still above the 1 % level.

**What "no flag" means.** Of the 20 single stocks, 5 carry a controversy row, 1 was read and its disclosure is not significant under the rule (RY.TO), 12 were read and no disclosure was found (AAPL, AMZN, ATD.TO, CNQ.TO, FTS.TO, GOOGL, JPM, MFC.TO, MSFT, NVDA, SHOP.TO, TD.TO) and 2 were not read (TSLA: its investor site answers HTTP 403 to automated reads; CSU.TO: its FY2025 annual information form is on SEDAR+ only). **No flag means no disclosure found in the document read, never a clean bill**: a company not read, or a proceeding outside the document read, is invisible to the screen. A generic "ordinary course of business" sentence is not a disclosure. A reason is identified by its ticker and its flag together, because ENB.TO and XOM carry two rows.

**The quote check.** Each reason holds one sentence of the filing, between 20 and 450 characters, kept verbatim in the French text (tests). On 2026-11-14 a second reader re-downloaded the six documents from the cited URLs and found all six quotes as exact substrings (whitespace-normalised; PDF text read with macOS PDFKit). Afterwards CNR.TO and RY.TO were changed to quote the first, self-contained sentence of their paragraphs, and both were re-checked as exact substrings the same day. These were one-off checks by script, not tests (6 of 6 and 2 of 2 quotes found; Indicative; no model): the tests pin structure, host, date and length. A reader can repeat the check by opening each URL and searching for the sentence.

**Direct and indirect.** The direct rule (only if the investor asked for the screen) fails when a company on the screen, or any Energy-sector stock, is held directly. The indirect rule warns when such names inside the funds' listed holdings reach 1 % of the money after rounding to 0.1 pp; it sees only the listed lines, so it is a lower bound.

## 7. Reconciliation with the issuers' published returns

**What is compared.** Our total return for each fund, from the dataset's adjusted close in the listing currency (CAD for XIU.TO and XBB.TO, USD for SPY and GLD, as the issuers publish them), against the figure printed on the issuer's own fund page, read on 2026-11-14. Ours is the last price on or before the end date over the last price on or before the start date; a "3 years a year" row is annualised, (1 + r)^(1/3) − 1. The pages publish trailing windows (year to date, 1 year, 3 years a year), not calendar years, so those are the windows compared; there is no calendar-year comparison. **Which basis.** State Street's SPY and GLD pages print both a NAV row and a Market Value row for each window; we use the Market Value row, the like-for-like for a price series. The choice matters for GLD: on the pages as re-read on 2026-11-15, its NAV rows differ from its market rows by up to 1.6 pp, and against them four of our five GLD figures would miss the 0.15 pp tolerance (SPY's two kinds of row differ by at most 0.06 pp). iShares Canada's page header prints a NAV total return (year to date, as of 2026-11-12) and we found no market-price return in the part of the pages we could read, so XIU.TO and XBB.TO compare a close with a NAV. Pages: blackrock.com/ca/investors/en/products/239832 (XIU.TO) and /239493 (XBB.TO); ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy (SPY) and /spdr-gold-shares-gld (GLD).

| ETF | Window (issuer basis) | Issuer % | Ours % | Gap pp | Within 0.15 pp |
|---|---|---:|---:|---:|---|
| XIU.TO | YTD to 2026-11-12, NAV | 17.93 | 17.99 | +0.06 | yes |
| XBB.TO | YTD to 2026-11-12, NAV | 0.69 | 0.63 | -0.06 | yes |
| SPY | YTD to 2026-10-31, market | 11.67 | 11.69 | +0.02 | yes |
| SPY | 1 year to 2026-10-31, market | 11.97 | 12.00 | +0.03 | yes |
| SPY | YTD to 2026-09-30, market | 12.66 | 12.71 | +0.05 | yes |
| SPY | 1 year to 2026-09-30, market | 15.66 | 15.71 | +0.05 | yes |
| SPY | 3 years a year to 2026-10-31, market | 23.25 | 23.28 | +0.03 | yes |
| GLD | YTD to 2026-10-31, market | -10.23 | -10.23 | +0.00 | yes |
| GLD | 1 year to 2026-10-31, market | -3.35 | -3.35 | +0.00 | yes |
| GLD | YTD to 2026-09-30, market | -3.90 | -3.90 | +0.00 | yes |
| GLD | 1 year to 2026-09-30, market | 7.14 | 7.14 | +0.00 | yes |
| GLD | 3 years a year to 2026-10-31, market | 24.54 | 24.56 | +0.02 | yes |

**Result.** 12 of 12 figures are within 0.15 pp; the largest gap is 0.06 pp (the two NAV rows, XIU.TO +0.06 and XBB.TO −0.06); GLD agrees to two decimals on 4 of 5 windows. Wilson 95 % interval for 12 of 12: 75.8 % to 100 %. Evidence level: Indicative (N = 12, below 30). No model is involved. The 12 figures come from 4 funds with overlapping windows, not 12 independent trials, so the interval is generous.

**Why 0.15 pp.** It sits between the noise and the error the check exists to catch: the largest observed gap is 0.06 pp, and a distribution counted twice, as CNQ.TO's was, moves a return by about 2.1 pp. A tolerance of 0.15 pp is 2.5 times the largest gap and far below that error. It was chosen once the gaps were known, so 12 of 12 is a consistency check, not a blind test.

**Why the two largest gaps are the NAV rows.** For XIU.TO and XBB.TO we compare a market close with a NAV. A premium or discount to NAV is a possible cause; we did not test it, and it cannot explain every gap, since SPY's market rows differ from ours by 0.02 to 0.05 pp.

**Limits.** Four funds out of 31 assets: no single stock, no crypto, and not QQQ, ESGV, ZST.TO, AGG or TLT. The trailing windows end on the issuers' dates (2026-11-12 for iShares Canada; month-ends and quarter-ends for State Street), so no calendar-year check exists. Dividends enter ours through Yahoo's adjustment; a different dividend treatment would show as a gap.

## 8. Validation and robustness

| Check | How | Result (2026-11-15) | Level and limit |
|---|---|---|---|
| Finance-truth tests | Written by a different owner than the code they judge; they pin each definition and each headline number of the four investors; real-data cases skip without the starter pack | `tests/test_metrics.py` 13, `test_governance.py` 81, `test_events.py` 6, `test_deep.py` 31: 131 passed | They pin today's numbers; a method error shared by code and test would pass |
| Independent recompute | A 34-line script on the raw CSV files, none of our code, same documented method (Appendix C) | Worst drop, its low date and CAGR of four mixes equal the tools to two decimals | Same method, so a shared misreading would not show |
| Issuer reconciliation | Section 7 | 12 of 12 within 0.15 pp; largest gap 0.06 pp | Indicative, N = 12; four funds |
| Robustness variants | Robert's move re-judged with shock dates one session earlier or later and a history from 2022-01-03; three storm windows reported (below; Appendix D) | Inside today and outside after, in 4 of 4 re-judged variants each | Indicative, N = 4; one investor, one move; method variants not measured yet |
| Risk-share and bets fixture | `scripts/check_bets_fixture.py 10000 0 500 engine` (below; Appendix B explains the last word, `engine`) | 0 failures in 500 seeds | Measured, N = 500; synthetic returns |
| No look-ahead | Perturbation tests: every row after `as_of` scrambled, identical output required | 22 perturbation and scramble tests in `tests/test_data.py` and `tests/test_proofs.py` pass | Proves the data path, not a model's memory. ESG flags, the holdings snapshot, the deep panel and macro release dates are not scrambled |

**The bets fixture.** The test draws one seed, so it passes or fails on that draw alone; the sweep re-draws the fixture (two lines of 1 % and 2 % daily volatility at weights 2/3 and 1/3, plus a near-duplicate of the first) for 500 seeds. Measured 2026-11-15, numpy 2.5.4, pandas 3.1.1, no model involved; exit status 0.

| Bound (10,000 returns per line, seeds 0 to 499) | Result | k / N | Wilson 95 % |
|---|---|---|---|
| Risk shares equal 0.5 ± 0.02 | fails on 0; largest deviation 0.0148 (seed 307) | 0 / 500 fail | 0.0 % to 0.8 % |
| Independent bets equal 2.0 ± 0.05 | fails on 0; largest gap 0.0054 (seed 342) | 0 / 500 fail | 0.0 % to 0.8 % |
| A near-duplicate pair (correlation at least 0.9947) reads under 1.1 bets | met on 500; largest value 1.000001 | 500 / 500 met | 99.2 % to 100.0 % |
| The retired 1/ΣRC² on that pair | reads 2.0000 and fails the same bound | 0 / 500 met | 0.0 % to 0.8 % |

At 2,000 returns per line the share bound fails on 42 of 500 seeds (exit status 1), which is why the fixture uses 10,000. The near-duplicate pair is what pins Meucci's measure against 1/ΣRC² and a covariance-blind count. Limit: it checks the fixture's bounds on synthetic Gaussian returns, not the estimator on real prices.

**How steady is Robert's headline?** Robert's move (40 % NVIDIA, asked against the tariff family) is re-judged under the variants the spec asks for, for his current mix ("today") and for the mix after the move ("after"). Every verdict is `governance.evaluate` on the history to 2026-11-12; Appendix D is the script, run on 2026-11-15.
- *Shock dates one session earlier or later.* A scratch copy of `data/events.csv` with every `date` moved one union-calendar session, read back through `load_events` and passed to the tools as their `events`.
- *Single storm, 10, 20 and 40 sessions.* The worst trough, among the tariff family's 11 loss storms, of one storm over its first 10, 20 or 40 sessions (`event_impact`). Reported, not scored: the checklist always uses 20-session campaign episodes.
- *History from 2022-01-03.* The worst drop and the size curve recomputed on a history that starts on 2022-01-03, so the last weeks of 2021 are gone. The shock check is unchanged, because the earliest of the 37 shocks is dated 2022-02-24.

| Variant | Investor | Verdict | Worst drop | Tariff shock check | Largest NVIDIA size inside the floor |
|---|---|---|---:|---:|---:|
| baseline | Robert today | Inside your limits | −10.6 % | −6.0 % | n/a |
| baseline | Robert after | Outside your limits | −34.5 % | −9.0 % | 8 % |
| shock dates one session earlier | Robert today | Inside your limits | −10.6 % | −5.5 % | n/a |
| shock dates one session earlier | Robert after | Outside your limits | −34.5 % | −8.7 % | 8 % |
| shock dates one session later | Robert today | Inside your limits | −10.6 % | −4.0 % | n/a |
| shock dates one session later | Robert after | Outside your limits | −34.5 % | −4.5 % | 8 % |
| single storm, 10 sessions | Robert today | n/a | n/a | −6.0 % | n/a |
| single storm, 10 sessions | Robert after | n/a | n/a | −9.0 % | n/a |
| single storm, 20 sessions | Robert today | n/a | n/a | −6.0 % | n/a |
| single storm, 20 sessions | Robert after | n/a | n/a | −9.0 % | n/a |
| single storm, 40 sessions | Robert today | n/a | n/a | −6.0 % | n/a |
| single storm, 40 sessions | Robert after | n/a | n/a | −9.8 % | n/a |
| history from 2022-01-03 | Robert today | Inside your limits | −10.6 % | −6.0 % | n/a |
| history from 2022-01-03 | Robert after | Outside your limits | −32.3 % | −9.0 % | 8 % |

The size column is the tool's size curve for the baseline and the two date shifts (every limit counted) and a scan of the floor alone for the restart; both read 8 %. A cell reads n/a where the variant does not apply: a storm window is not a verdict, and the size question is about the move, not about today's mix.

What moved and what did not:
- *Baseline.* Inside your limits today (worst drop −10.6 %), outside after the move (−34.5 % against the −15.0 % floor); no limit is crossed up to NVIDIA at 8 %.
- *Shock dates one session earlier.* Verdicts, worst drops and the 8 % size do not move: the worst drop does not read the catalog, and the shock check is a caution, never a fail. The tariff shock check reads −5.5 % today and −8.7 % after (from −6.0 % and −9.0 %); Liberation Day is still the worst episode, and the after mix is still beyond half the floor (−7.5 %).
- *Shock dates one session later.* Verdicts, worst drops and the 8 % size do not move, but the shock check does: −4.0 % today and −4.5 % after. For the after mix that is inside half the floor, so its caution disappears, and its worst episode becomes tariffs_order_2025; today's mix reads Measured instead of Indicative. The reason is the dating: Liberation Day was announced after the close of 2025-04-02 and first traded on 2025-04-03, so one session later its baseline is a close that already holds the first day of the fall. This is the knife-edge of single-storm numbers: the page quotes them as "this storm", never as a family rule, and the hard verdict does not rest on them.
- *Single storm, 10 and 20 sessions.* The worst storm is Liberation Day (low 2025-04-08): −6.0 % today and −9.0 % after, the baseline's shock check.
- *Single storm, 40 sessions.* Today's worst is unchanged (−6.0 %). After the move it reads −9.8 %, from tariffs_canada_2025 (first session 2025-03-04), whose longer window runs to 2025-04-30 and so also contains Liberation Day's fall. A longer window lets an earlier storm absorb a later one, which is why the product scores 20-session campaign episodes and not a window chosen per storm.
- *History from 2022-01-03.* Today's mix is unchanged (−10.6 %, peak 2022-03-04, low 2022-10-11). After the move the worst drop is −32.3 % instead of −34.5 % (peak 2022-01-03, low 2022-10-14), still beyond −15.0 %. NVIDIA at 8 % is the largest size inside the floor (−14.8 %) and 9 % is not (−15.3 %): the floor is crossed between 8 % and 9 % here too.

**Count.** Robert today is inside his limits in 4 of 4 variants that re-judge the verdict, and Robert after is outside in 4 of 4 (Wilson 95 % interval 51.0 % to 100 % for each; Indicative, N = 4, below 30; run 2026-11-15; no model). Limit: four hand-chosen changes to one move are not four independent trials, and the three storm-window rows are reported, not scored.

**Other checks on the same headline** (Robert after the move, floor −15.0 %, worst drop −34.5 %).
- *A harder restart.* With the history restarted on 2023-01-01, so that 2022 is gone, the worst drop is −16.9 % (peak 2025-01-23, low 2025-04-08), still beyond the floor; his current mix reads −6.1 % over the same start. A test pins the −16.9 %.
- *One size step.* On the size curve NVIDIA at 8 % ends at −15.0 % (raw −15.00004 %, inside after rounding) and at 9 % at −15.6 %, outside. The edge is real but narrow, so the claim is only that the floor is crossed between 8 % and 9 %.
- *A looser floor.* The tool's own scan of the floor, in 0.1 pp steps: "Outside your limits until your floor is −34.5 % or lower; at that floor the verdict would be Inside, with caveats because NVDA would still be beyond the single-company limit."
- *The band as well as the capacity.* −34.5 % is also beyond the moderate band's −25.0 % floor, so the verdict does not rest on his capacity alone.
- *The mixed tariff episode.* The tariff worst stays −6.0 % (today) whether canada_50_2026 is scored on 12 sessions or in full.
- *The rate cycle.* Rate-decision windows contain 32.3 % of the trading days of the worst fall and 24.9 % of its log loss. This is a correlation, not a cause: the floor broke in a slow fall from 2021-11-29 to 2022-10-14, not on one headline.

**Not yet measured.** The method variants (no rebalancing, monthly rebalancing, currency-hedged USD lines, a block bootstrap of the daily returns) are not measured in this document, and no statement here rests on them.

## 9. The four investors

All four are fictional. "Today" is the portfolio as held; "after" applies the investor's own move. Every figure is the tool's, on the history to 2026-11-12; dollars apply the drawdown to the fictional amount (○).

### Robert (59, preservation)

**Plan.** $600,000; the money is needed in 4 years; he could absorb $90,000; in 2022 he held on (moderate band); no values screen, no crypto. Portfolio: 45 % XIU.TO, 35 % XBB.TO, 10 % GLD, 10 % ZST.TO. His move: put 40 % in NVIDIA (the other lines scale to 27 %, 21 %, 6 % and 6 %), asked against the tariff family.

**Limits.** Floor −15.0 % ($90,000), **set by his capacity**: his tolerance band alone would allow −25.0 %. One company 10 %, one sector 35 %, crypto 0 %, shock check −7.5 %, recovery 487 days.

**Verdict.** Inside your limits today; **Outside your limits** after the move. The binding rule is the floor (hard). Two more rows fail (NVDA as one company, Information Technology as one sector), counted as one cause; the shock check is in Caution; the risk-share warning rises.

| | Today | After the move | Limit |
|---|---:|---:|---:|
| Worst drop (dollars on $600,000) | −10.6 % ($63,639) | −34.5 % ($207,146) | −15.0 % ($90,000) |
| Peak to low | 2022-03-04 to 2022-10-11 | 2021-11-29 to 2022-10-14 | |
| Tariff shock check (6 separate earlier episodes, Indicative) | −6.0 % | −9.0 % | −7.5 % |
| Recovery | 416 days | 187 days | 487 days |
| Largest company | RY.TO 4.3 % | NVDA 40.0 % | 10 % |
| Largest sector | Financials 18.6 % | Information Technology 42.6 % | 35 % |
| Largest share of the risk | XIU.TO 71.1 % | NVDA 89.6 % | warns above 50 % |
| Independent bets | 2.43 | 1.16 | |
| CAGR | 8.7 % | 25.2 % | |

**Size, in this history.** On the size curve NVIDIA at 8 % ends at −15.0 % (inside, after rounding) and at 9 % at −15.6 % (outside): the floor is crossed between 8 % and 9 %. A second limit, one company at 10 %, fails from 11 %. **Lesson.** The move grew faster (CAGR 8.7 % to 25.2 %) and broke the floor his own capacity sets: a good outcome is not a good decision.

### Mateo (41, balance)

**Plan.** $250,000 for 10 years; he could absorb $62,500; held in 2022 (moderate); values screen on, no crypto. Portfolio: 35 % XIU.TO, 35 % XBB.TO, 8 % CNQ.TO, 10 % MSFT, 12 % GLD. Question (spec ruling R14: his card is decided by his values): “I care about my values: does my portfolio own companies with major controversies, and what if an oil shock came from the Middle East?” It asks the values screen (owned directly and inside his funds) and the war and oil shock check. No move.

**Limits.** Floor −25.0 % ($62,500): capacity and band tie, named capacity. One company 10 %, one sector 35 %, crypto 0 %, shock check −12.5 %, recovery 1,217 days.

**Verdict.** **Outside your limits.** The binding rule is the values screen: he turned it on, so a company it excludes and that he owns directly breaks a hard limit, like the floor (ruling of 2026-11-15): CNQ.TO is held directly (8.0 % of the money; the limit is 0 %). A warning follows: companies on the screen inside his funds add up to 3.3 % of the money (ENB.TO, CNQ.TO and CNR.TO inside XIU.TO), above the 1 % level. His numbers pass: worst drop −11.4 % ($28,580; 2022-04-04 to 2022-07-14) against −25.0 % ($62,500); war and oil shock check −4.2 % against −12.5 % over 10 separate earlier episodes (Measured); MSFT at exactly 10.0 % passes; XIU.TO carries 45.9 % of the risk, under the 50 % level; 3.89 independent bets. **Lesson.** His values say no, not his numbers. The price of his values is computed on his own portfolio, with CNQ.TO removed and the rest scaled up (no new security, spec §24 resolution 7), against the portfolio as it is: worst drop −12.9 % against −11.4 %, worst war and oil shock −5.8 % against −4.2 %, CAGR 9.8 % against 11.5 %.

### Amira (26, growth)

**Plan.** $80,000 for 15 years; she could absorb $36,000; in 2022 she bought more (high band); no values screen; crypto allowed up to the band's cap. Portfolio: 15 % NVDA, 15 % QQQ, 10 % SHOP.TO, 15 % BTC-USD, 30 % XIU.TO, 15 % XBB.TO. Question: the US–China chip war (chips family). No move.

**Limits.** Floor −45.0 % ($36,000): capacity and band tie, named capacity. One company 20 %, one sector 40 %, crypto 10 %, shock check −22.5 %, recovery 1,825 days.

**Verdict.** **Inside, with caveats.** The binding rule is the crypto cap, a soft limit: crypto is 15.0 % of the money against 10 %. High risk is accepted but not anything: worst drop −41.3 % ($33,077; 2021-11-19 to 2022-10-11) against −45.0 % ($36,000); chip shock check −9.6 % against −22.5 % over 7 separate earlier episodes (Indicative, mixed with tariffs_order_2025); NVIDIA as one company 16.0 % (direct and inside her funds) against 20 %; Information Technology 37.5 % against 40 %, an upper bound (section 5) that still passes; NVDA carries 27.8 % of the risk. Six lines behave like **1.44 independent bets**. **Lesson.** High risk is accepted, but not anything: the crypto share is capped and one bet is not diversification.

### Too Canadian? (the workshop's own question)

**Plan.** Mateo's amount and limits without the values screen: $250,000 for 10 years, floor −25.0 % ($62,500), shock check −12.5 %. Portfolio: 60 % XIU.TO, 30 % XBB.TO, 10 % ZST.TO. Question: would adding 20 % SPY improve diversification? (SPY stands in for the workshop's XSP, which the dataset does not contain; it is not currency-hedged, so the US dollar share is part of the answer.) The shock check runs all four families.

**Verdict.** Inside your limits today and after, with one risk-share warning each time. The floor holds (−11.9 % ($29,798) today, −12.9 % ($32,255) after, against −25.0 %), and so does the shock check (−7.0 % today, −8.1 % after, against −12.5 %, over 26 separate earlier episodes, Indicative). What moves is **where the risk sits**:

| | Today | After adding 20 % SPY |
|---|---:|---:|
| Canada's share of the money | 97.5 % | 78.0 % |
| Canada's share of the risk | 97.5 % | 68.3 % |
| US dollar share of the money | 0.0 % | 20.0 % |
| XIU.TO's share of the risk (warns above 50 %) | 90.0 % | 63.9 % |
| Independent bets | 1.14 | 1.39 |
| CAGR | 8.8 % | 10.1 % |

**Lesson.** Diversification is about where the risk sits, not how many lines there are: the verdict does not change, the concentration does.

## 10. Limits

- **One regime.** Five years contain the 2022 fall of stocks and bonds together and little else of that depth: one shock is not a climate. Older history by proxy (11 earlier crises, monthly, public stand-ins) is a ◐ disclosure shown beside the verdict, never inside it, and never mixed with a ● 2021 to 2026 number in one sentence.
- **Hindsight in the catalog.** The 37 shocks were chosen in 2026, with a rule written before any price was looked at but with hindsight about which events mattered. They are questions to test, not a sample. Each family holds 5 to 13 announcements and 3 to 10 separate loss episodes, so a single storm's number is quoted as "this storm", never as a family rule.
- **Survivorship bias.** The universe was picked in 2026 from names that are large today; a test on it looks better than a selection made in 2021 would have.
- **Coverage of the market.** 31 assets. Real estate, savings accounts and GICs are outside this universe; real estate appears only as a sector inside the index funds. One currency pair (USD/CAD).
- **Fictional money and portfolios.** The limits are the investor's answers; EPICENTRE's starting values are ◐ and need confirmation. Constant weights rebalanced every day are an assumption: a real investor drifts.
- **Costs, taxes, inflation.** Trading costs and taxes are not modelled (fees sit inside ETF prices). Returns are nominal, before inflation, so a fall in a year of high inflation is larger in real terms than shown.
- **Look-through is partial and a snapshot.** Holdings are dated 2026-11-12 and used for "today" only; the listed lines cover 51.8 % to 77.9 % of the four equity funds; sectors are ICB mapped to GICS and are upper bounds for Information Technology. Without the issuers' files the look-through falls back to direct holdings, flagged: unknown is never a pass.
- **The values screen is not a score.** It rests on one published exclusion list and on five disclosed proceedings that meet the significance rule; 2 of 20 stocks were not read, and no flag never means a clean bill (section 6).
- **Windows show correlation, not cause.** A fall that sits inside a family's shock windows may have other causes; the page never says a headline "broke" a floor.
- **Dated data.** Monthly macro rows are dated to the reference month, not the release date, and FRED values are the latest revision; no verdict uses CPI. Crypto rows are UTC days sampled on the union calendar. Yahoo data is not exchange-certified, and `adj_close` for older dates changes if the data is downloaded again.
- **A hard verdict sits on a rounded edge.** The floor is compared after rounding to 0.1 pp, so the page says a limit is crossed between two whole percents, never at one.
- **Reconciliation is narrow.** Four funds, trailing windows, 12 figures (section 7). Section 8 lists what is not yet measured.
- **Not a forecast, not advice.** Every statement is about what already happened; the product says "inside" or "outside the limits you set".

## Appendix A. The 37 shocks

Announced time is US Eastern; "Time" is the code of the dating rule of section 4; the first session is the union-calendar `date`; every row has a source URL in `data/events.csv`.

| Event | Announced (ET) | Time | First session | Family | Sign | Campaign |
|---|---|---|---|---|---|---|
| ukraine_2022 | 2022-02-24 08:00 | B | 2022-02-24 | war_oil | − | ukraine_2022 |
| fed_75_2022 | 2022-06-15 14:00 | S | 2022-06-15 | rates | − | fed_75_2022 |
| boc_100_2022 | 2022-07-13 12:00 | M | 2022-07-13 | rates | − | fed_75_2022 |
| jackson_hole_2022 | 2022-08-26 12:00 | M | 2022-08-26 | rates | − | jackson_hole_2022 |
| cpi_sep_2022 | 2022-09-13 08:30 | S | 2022-09-13 | rates | − | jackson_hole_2022 |
| chips_2022 | 2022-10-07 12:00 | M | 2022-10-07 | chips | − | chips_2022 |
| svb_2023 | 2023-03-08 18:00 | A | 2023-03-09 | rates | − | svb_2023 |
| opec_cut_2023 | 2023-04-02 12:00 | M | 2023-04-03 | war_oil | − | opec_cut_2023 |
| gallium_2023 | 2023-07-03 12:00 | M | 2023-07-03 | chips | − | gallium_2023 |
| israel_2023 | 2023-10-07 12:00 | M | 2023-10-09 | war_oil | − | israel_2023 |
| ai_chips_2023 | 2023-10-17 08:45 | S | 2023-10-17 | chips | − | ai_chips_2023 |
| red_sea_2023 | 2023-12-18 12:00 | M | 2023-12-18 | war_oil | − | red_sea_2023 |
| iran_israel_2024 | 2024-04-13 18:00 | A | 2024-04-15 | war_oil | − | iran_israel_2024 |
| chip_selloff_2024 | 2024-07-17 12:00 | M | 2024-07-17 | chips | − | chip_selloff_2024 |
| iran_missiles_2024 | 2024-10-01 12:00 | M | 2024-10-01 | war_oil | − | iran_missiles_2024 |
| tariff_threat_2024 | 2024-11-25 19:33 | S | 2024-11-26 | tariffs | − | tariff_threat_2024 |
| hbm_2024 | 2024-12-02 12:00 | M | 2024-12-02 | chips | − | hbm_2024 |
| deepseek_2025 | 2025-01-27 12:00 | M | 2025-01-27 | chips | − | deepseek_2025 |
| tariffs_order_2025 | 2025-02-01 12:00 | M | 2025-02-03 | tariffs | − | tariffs_order_2025 |
| tariffs_canada_2025 | 2025-03-04 08:00 | B | 2025-03-04 | tariffs | − | tariffs_order_2025 |
| liberation_day_2025 | 2025-04-02 18:00 | A | 2025-04-03 | tariffs | − | liberation_day_2025 |
| tariff_pause_2025 | 2025-04-09 12:00 | M | 2025-04-09 | tariffs | + | tariff_pause_2025 |
| h20_2025 | 2025-04-15 18:00 | A | 2025-04-16 | chips | − | h20_2025 |
| israel_iran_2025 | 2025-06-13 08:00 | B | 2025-06-13 | war_oil | − | israel_iran_2025 |
| canada_35_2025 | 2025-07-10 18:00 | A | 2025-07-11 | tariffs | − | canada_35_2025 |
| china_100_2025 | 2025-10-10 12:00 | M | 2025-10-10 | tariffs | − | china_100_2025 |
| canada_talks_2025 | 2025-10-23 18:00 | A | 2025-10-24 | tariffs | − | china_100_2025 |
| greenland_2026 | 2026-01-17 12:00 | M | 2026-01-19 | tariffs | − | greenland_2026 |
| scotus_ieepa_2026 | 2026-02-20 12:00 | M | 2026-02-20 | tariffs | + | scotus_ieepa_2026 |
| iran_2026 | 2026-02-28 12:00 | M | 2026-03-02 | war_oil | − | iran_2026 |
| ceasefire_2026 | 2026-04-07 18:00 | A | 2026-04-08 | war_oil | + | ceasefire_2026 |
| peace_deal_2026 | 2026-06-14 18:00 | A | 2026-06-15 | war_oil | + | peace_deal_2026 |
| cusma_2026 | 2026-07-01 12:00 | M | 2026-07-01 | tariffs | − | cusma_2026 |
| ceasefire_end_2026 | 2026-07-07 12:00 | M | 2026-07-07 | war_oil | − | ceasefire_end_2026 |
| canada_338_2026 | 2026-07-20 12:00 | M | 2026-07-20 | tariffs | − | cusma_2026 |
| canada_50_2026 | 2026-08-22 12:00 | M | 2026-08-24 | tariffs | − | canada_50_2026 |
| saudi_pipeline_2026 | 2026-09-10 12:00 | M | 2026-09-10 | war_oil | − | saudi_pipeline_2026 |

Sign: − a loss shock, + a relief shock. Campaign: the first event of the episode the shock belongs to (campaign episodes, section 3).

## Appendix B. Reproduce it

From the repository root, with the starter pack in `data/starter/` and the holdings file in `data/etf_holdings.csv` (both local, never committed). Each command prints the numbers quoted above.

```
# section 7: the reconciliation table
.venv/bin/python -c "import sys; sys.path[:0] = ['.', 'tests']; import test_metrics as m; print(m.reconciliation_markdown())"
# section 8: the bets fixture sweep (exit status 0)
.venv/bin/python scripts/check_bets_fixture.py 10000 0 500 engine
# section 9: each investor's verdict (add ['kpis'] or ['checks'] for the rows)
.venv/bin/python -c "import json, governance as g; P = json.load(open('data/personas.json'))['pilots']; F = {'robert': ['tariffs'], 'mateo': ['war_oil'], 'amira': ['chips'], 'canadian': ['tariffs', 'war_oil', 'chips', 'rates']}; [print(k, g.evaluate(p['profile'], p['portfolio'], F[k], '2026-11-12', amount=p['amount'])['verdict']) for k, p in P.items()]"
# section 4: clean episodes per family on Robert's current mix
.venv/bin/python -c "import governance as g, json; from tools import events as E; w = json.load(open('data/personas.json'))['pilots']['robert']['portfolio']; t = E.turbulence(w, None, '2026-11-12'); print({f: (t[f]['n'], g.fmt_pct(t[f]['worst']), t[f]['label']) for f in E.FAMILIES})"
# section 5: the holdings file rebuilt from the issuers' pages, to a scratch path (needs the network)
.venv/bin/python scripts/fetch_holdings.py --out /tmp/holdings_check.csv
# section 8: Robert's move re-judged under the robustness variants (Appendix D; saved as robustness.py)
.venv/bin/python robustness.py
# section 8: the finance-truth tests
.venv/bin/python -m pytest tests/test_metrics.py tests/test_governance.py tests/test_events.py tests/test_deep.py -q
```

## Appendix C. The independent recompute

The script below reads only the raw CSV files of the starter pack and imports none of our code. It applies the documented method of sections 2 and 3: adjusted close, the CNQ.TO factor, the union calendar, a fill of at most 3 days, USD/CAD carried forward, constant weights rebalanced every day, base 100. Save it as `recompute.py` and run `.venv/bin/python -I recompute.py data/starter/`. The four mixes include both TSX and US lines, so every union session counts; a portfolio held on one exchange only would need the "a day counts when one held exchange traded" rule, which the script does not implement.

```python
import sys
import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else "data/starter/"
px = pd.read_csv(D + "prices_daily.csv", parse_dates=["date"])
fx = pd.read_csv(D + "fx_usdcad_daily.csv", parse_dates=["date"]).dropna().set_index("date")["usdcad"]
cur = px.drop_duplicates("ticker").set_index("ticker")["currency"]
adj = px.pivot(index="date", columns="ticker", values="adj_close")
adj.loc[adj.index < "2022-08-22", "CNQ.TO"] *= 1.021                      # the one documented correction
equity = [t for t in adj.columns if not t.endswith("-USD")]
days = adj[equity].dropna(how="all").index                                # union of TSX and US sessions
cad = adj.reindex(days).ffill(limit=3)                                    # fill at most 3 days
rate = fx.reindex(days, method="ffill")                                   # USD/CAD carried forward
for t in cad.columns:
    if cur[t] == "USD":
        cad[t] = cad[t] * rate

def path(w):
    r = sum(wt * cad[t].pct_change() for t, wt in w.items()).dropna()    # constant weights, rebalanced every day
    v = 100 * (1 + r).cumprod()
    v = pd.concat([pd.Series([100.0], index=[days[0]]), v])
    dd = v / v.cummax() - 1
    years = (v.index[-1] - v.index[0]).days / 365.25
    return dd.min(), dd.idxmin().date(), (v.iloc[-1] / 100) ** (1 / years) - 1

MIXES = {
    "Robert today": {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10},
    "Robert after": {"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06},
    "Mateo": {"XIU.TO": 0.35, "XBB.TO": 0.35, "CNQ.TO": 0.08, "MSFT": 0.10, "GLD": 0.12},
    "Amira": {"NVDA": 0.15, "QQQ": 0.15, "SHOP.TO": 0.10, "BTC-USD": 0.15, "XIU.TO": 0.30, "XBB.TO": 0.15},
}
for name, w in MIXES.items():
    dd, when, cagr = path(w)
    print(f"{name}: worst drop {100 * dd:.2f} % (low {when}), CAGR {100 * cagr:.2f} %")
```

| Mix | Worst drop, script | Worst drop, tools | CAGR, script | CAGR, tools | Date of the low, script and tools |
|---|---:|---:|---:|---:|---|
| Robert today | -10.61 % | -10.61 % | 8.73 % | 8.73 % | 2022-10-11 |
| Robert after | -34.52 % | -34.52 % | 25.22 % | 25.22 % | 2022-10-14 |
| Mateo | -11.43 % | -11.43 % | 11.52 % | 11.52 % | 2022-07-14 |
| Amira | -41.35 % | -41.35 % | 17.93 % | 17.93 % | 2022-10-11 |

The script and the tools agree to two decimals on all four mixes, for the worst drop, its date and the CAGR: 4 of 4 mixes, Wilson 95 % interval 51.0 % to 100 %, Indicative (N = 4, below 30), run on 2026-11-15, no model involved. Same method, same reader: a shared misreading of the method would not show.

## Appendix D. The robustness script

The script below re-judges Robert's move under the variants of section 8. Unlike Appendix C it uses the repository's own tools (`governance.evaluate`, `tools.events`, `tools.allocation.tipping_point`), because what it tests is how the verdict moves when the shock dates, the storm window or the start of the history move, not the arithmetic. Save it as `robustness.py` in the repository root and run `.venv/bin/python robustness.py`, with the starter pack in `data/starter/` and the holdings file in `data/etf_holdings.csv` (without the holdings the funds are not looked through and today's verdict carries caveats). It writes its shifted catalogs to temporary files and changes nothing in the repository. It prints the table of section 8 and the two counts; run on 2026-11-15, and run again the same day on the code of this commit with the same output, line for line. No model is involved.

```python
"""Robustness of Robert's move (spec 15). Read-only; every number comes from the repository's tools.
Save as robustness.py and run from the repository root: .venv/bin/python robustness.py"""
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path[:0] = ["."]
import governance as g
from tools import allocation as A
from tools import events as E
from tools.data import load_market
from tools.metrics import risk_metrics
from tools.portfolio import apply_change, portfolio_series

AS_OF, FAM = "2026-11-12", ["tariffs"]
R = json.load(open("data/personas.json"))["pilots"]["robert"]
PROFILE, AMOUNT, TODAY = R["profile"], R["amount"], R["portfolio"]
MIXES = {"Robert today": TODAY, "Robert after": apply_change(TODAY, R["request"])}
M = load_market(AS_OF)
CAL, BASE = M["calendar"], E.load_events(AS_OF, market=M)
FLOOR = g.load_limits(PROFILE, amount=AMOUNT)["floor"]
WORDS = {"Compatible": "Inside your limits", "Tension": "Inside, with caveats", "Incompatible": "Outside your limits"}
pct = lambda x: "n/a" if x is None else g.fmt_pct(x).replace("\u00a0", " ")


def moved(step):
    """The catalog with every `date` moved `step` union sessions, read back through load_events."""
    t = pd.read_csv(E.EVENTS_CSV, dtype=str, keep_default_na=False)
    t["date"] = [CAL[CAL.searchsorted(pd.Timestamp(d)) + step].strftime("%Y-%m-%d") for d in t["date"]]
    path = Path(tempfile.mkdtemp()) / "events.csv"
    t.to_csv(path, index=False)
    return E.load_events(AS_OF, path=path, market=M)


def judged(variant, name, events, metrics=None, size=None):
    """One row: the verdict of governance.evaluate, or of check_profile when `metrics` replace the history."""
    mix = MIXES[name]
    ev = g.evaluate(PROFILE, mix, FAM, AS_OF, market=M, events=events, amount=AMOUNT, detail=False)
    checks = ev["checks"] if metrics is None else g.check_profile(PROFILE, mix, {**ev["analysis"], "metrics": metrics})
    drop = (metrics or ev["metrics"])["max_drawdown"]
    return [variant, name, WORDS[g.verdict(checks)], drop, ev["stress"]["value"], size]


def storm(name, w):
    """The worst trough of one tariff loss storm over its first w sessions (reported, not scored)."""
    return min(E.event_impact(MIXES[name], e["event_id"], window=(-5, w), as_of=AS_OF, market=M, events=BASE)["trough"]
               for e in BASE if e["family"] == "tariffs" and e["sign"] == "negative" and e["known"])


def tip(events):
    """The tool's size curve: the largest NVIDIA size (1 % steps from today) with no limit crossed."""
    return A.tipping_point(PROFILE, TODAY, "NVDA", [], AS_OF, market=M, events=events, families=FAM, amount=AMOUNT,
                           max_weight=0.4)["max_weight"]


def floor_scan(start):
    """The largest NVIDIA size whose worst drop from `start` stays inside the floor after rounding to 0.1 pp."""
    sizes = (k / 100 for k in range(41))
    ok = [w for w in sizes if g.round_pp(risk_metrics(portfolio_series(
        apply_change(TODAY, {"op": "set", "ticker": "NVDA", "weight": w, "from_ticker": None}),
        start=start, as_of=AS_OF, market=M))["max_drawdown"]) >= g.round_pp(FLOOR)]
    return max(ok)


rows = [judged("baseline", n, BASE, size=tip(BASE) if n == "Robert after" else None) for n in MIXES]
for label, step in (("shock dates one session earlier", -1), ("shock dates one session later", 1)):
    ev = moved(step)
    size = tip(ev)
    rows += [judged(label, n, ev, size=size if n == "Robert after" else None) for n in MIXES]
rows += [[f"single storm, {w} sessions", n, None, None, storm(n, w), None] for w in (10, 20, 40) for n in MIXES]
for n, mix in MIXES.items():
    metrics = risk_metrics(portfolio_series(mix, start="2022-01-03", as_of=AS_OF, market=M))
    rows.append(judged("history from 2022-01-03", n, BASE, metrics, floor_scan("2022-01-03") if n == "Robert after" else None))

print("| Variant | Investor | Verdict | Worst drop | Tariff shock check | Largest NVIDIA size inside the floor |")
print("|---|---|---|---:|---:|---:|")
for variant, name, verdict, drop, shock, size in rows:
    print(f"| {variant} | {name} | {verdict or 'n/a'} | {pct(drop)} | {pct(shock)} | "
          f"{'n/a' if size is None else f'{100 * size:.0f} %'} |")
for name, want in (("Robert today", "Inside your limits"), ("Robert after", "Outside your limits")):
    got = [r[2] for r in rows if r[1] == name and r[2]]
    print(f"{name}: {want} in {got.count(want)} of {len(got)} re-judged variants")
```

Educational simulation. This is not financial advice.
