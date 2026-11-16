# EPICENTRE

[![tests](https://github.com/shmorsi/poly-datathon-2026/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/shmorsi/poly-datathon-2026/actions/workflows/tests.yml)

**Crash-test your move before you make it.** « Passez votre placement au crash-test avant d’agir. »

### ▶ [Open the demo](https://shmorsi.github.io/poly-datathon-2026/): no install, no login, works on a phone

![Robert’s replay at its end frame: the AI’s reading, the shock on the globe, his money against his floor, the verdict](docs/img/replay-end-frame.png)

*Robert’s saved run (a fictional investor). This already happened; it is not a forecast. Fictional illustration, not a recommendation.*

An investor types the move they are tempted by, in their own words: *“⟨run:robert:question⟩”* EPICENTRE replays that move on real daily history, ⟨run:robert:series.dates.0|month⟩ to ⟨run:robert:as_of|month⟩ (the 2022 fall of stocks and bonds together, and ⟨run:robert:events|len⟩ sourced geopolitical and rate shocks), today’s mix against the mix with the move, and answers in dollars: **Inside your limits**, **Inside, with caveats** or **Outside your limits**. It never says buy, sell or hold.

**Why it stands out**

- **It challenges the request; it never recommends.** Most AI investing demos recommend a trade. An order-execution-only broker such as National Bank Direct Brokerage may not; EPICENTRE is a pre-trade crash test for self-directed investors that shows what the move already did, against the investor’s own limits.
- **Agents read, code counts.** Claude on Amazon Bedrock turns the words into a plan that code validates, asks when information is missing, abstains without a precedent and writes the explanation; Bedrock Guardrails screen the words first; code computes every number and the verdict, then checks every number the AI wrote.
- **Every sentence can be traced.** Each sentence is marked ● fact, ◐ assumption or ○ fiction; click any number for its data row, its trace step and **Recompute**.
- **Ending higher does not mean your limits held.** Robert’s move ends the five years higher and still breaks his floor in 2022: the verdict follows his limits, not the final return.

PolyFinances Datathon 2026, AlphaForge AI case. Educational simulation: nothing is bought or sold, and nothing here is advice.

## Try it

| | Where | What you get |
|---|---|---|
| **Static demo**, public and permanent | https://shmorsi.github.io/poly-datathon-2026/ | The four saved real runs, read-only, request ids shown as recorded; no AWS call, so it keeps working after the AWS account closes; works on a phone |
| **Live app on AWS** | https://dqetfenyawfe9.cloudfront.net, with the password given to the jury separately | The real pipeline on your own words, and a sealed record kept in the S3 vault; live until the AWS account closes |

Documents: [technical documentation](docs/technical.md), [AWS architecture and evidence](docs/aws.md), [evaluation](docs/eval_results.md), [finance methods](docs/finance_methods.md), [one-pager](docs/one_pager.md). Every number in them taken from a run is filled by `scripts/fill_docs.py` from the final saved runs, and the PDFs are printed from these same files.

## The tour

Robert, ⟨run:robert:profile.age⟩, retires in about ⟨run:robert:profile.horizon_years⟩ years. Follow him:

1. **The hero.** Every shock on record lights the night Earth; his words fill the command bar: “⟨run:robert:question⟩” Press **Replay**.
2. **The AI reads.** Claude on Amazon Bedrock turns the words into chips: NVIDIA to ⟨run:robert:scenario.change.weight|pct0⟩, the tariff war, its earlier episodes.
3. **The shock flies home.** The globe turns to “Liberation Day” in Washington; a cyan line drops to that date on the chart.
4. **The race.** Today’s mix against the move, in dollars, under a gold floor that follows every new high.
5. **The verdict.** **Outside your limits**, in this 2021–26 replay. His two limits are assumed for this fictional profile: no fall of more than ⟨run:robert:limits.floor|pct0⟩ from any high (his tolerance), and the ⟨run:robert:profile.capacity_dollars|usd⟩ he could afford to lose (his capacity: stay above ⟨run:robert:capacity.line|usd⟩). With the move, the money fell from ⟨run:robert:breaches.0.peak_value|usd⟩ to ⟨run:robert:breaches.0.trough_value|usd⟩ by ⟨run:robert:breaches.0.trough_date|month⟩, ⟨run:robert:breaches.0.depth|pct⟩ from its high and below ⟨run:robert:capacity.line|usd⟩ for ⟨run:robert:capacity.after.sessions_below|int⟩ sessions, and again from ⟨run:robert:breaches.1.peak_value|usd⟩ to ⟨run:robert:breaches.1.trough_value|usd⟩ by ⟨run:robert:breaches.1.trough_date|month⟩, past the ⟨run:robert:limits.floor|pct0⟩ rule but ⟨run:robert:capacity.after.floor_breaks.1.margin_dollars|usd⟩ above that line. Ending higher does not mean your limits held.
6. **Where it breaks.** Drag NVIDIA from 0 to ⟨run:robert:scenario.change.weight|pct0⟩: in this replay, his floor first broke at ⟨run:robert:tipping_point.curve.verdict=Incompatible.weight|pct0⟩. No size is ever marked acceptable.
7. **Money against risk.** With the move, ⟨run:robert:scenario.change.weight|pct0⟩ of the money carried ⟨run:robert:risk.after.shares.NVDA|pct⟩ of the risk; then independent bets and Canada’s share.
8. **Not just 2022.** ⟨run:robert:deep_history.episodes|len⟩ crises since ⟨run:robert:deep_history.episodes.0.trigger_date|year⟩, by public stand-ins: ◐ probably milder than the real thing, never the verdict.
9. **Why, and pull the thread.** The checks open with his limits (editable in the live app); each sentence of the explanation is marked ● fact, ◐ assumption or ○ fiction; click a number for its row, its trace step and **Recompute**.
10. **AI off.** Switching the navigator off changes no verdict in these four runs; it changes the question answered: without it, Robert’s shock check replays every family’s earlier episodes (worst ⟨run:robert:navigator_effect.checks_without.rule=scenario_stress.value|pct⟩) instead of the ⟨run:robert:turbulence.tariffs.n⟩ tariff war episodes he asked about (worst ⟨run:robert:turbulence.tariffs.worst_after|pct⟩).
11. **Four investors**, four deciding checks: Robert’s floor, Mateo’s values, Amira’s crypto share, and “Too Canadian?”, the workshop’s XSP question.
12. **How it works.** This run’s five steps with their real milliseconds, tokens and request ids; AWS, one job each.
13. **The sealed record.** Every number with its source under a SHA-256 seal: edit one and the seal breaks; download it, print it, or keep it in the vault (live app).

## How it works

Observe, Understand, Compare, Explain: the method of National Bank’s finance workshop, plus one step we added, Verify. Every tool and model call is a row of the run’s trace.

| Step | What happens | Who |
|---|---|---|
| **Observe** | Read the plan and the limits (assumed for the personas, typed in the live editor); screen the question | Code, with its advice check; Bedrock Guardrails |
| **Understand** | Words or a headline become a validated move, shock families and sourced precedents, or one clarifying question | The navigator: Claude Sonnet 5.5, one Converse call; code validates it, and keyword rules answer if it fails |
| **Compare** | Replay both mixes on the same days; shocks by episode; risk share; where it breaks; the checks and the verdict | Code only |
| **Explain** | Four answers (what data, why, what limits, what would change it), each number citing its facts row | The debrief: Claude Sonnet 5.5, one call, at most one re-ask |
| **Verify** | Trace every number to its row and name each defect; show the grounding score, advisory | Code (the receipt); Bedrock Guardrails |

![EPICENTRE architecture: the browser, CloudFront, the FastAPI server on EC2 with its five steps, Amazon Bedrock and Guardrails, the S3 record vault, CloudWatch, IAM and the static demo](docs/img/architecture.svg)

The model chooses words; code decides the rest, and a rules engine (`governance.py`) cannot be talked out of a limit. The bounded tool loop stays an evaluation arm: as good on the development set (38 / 40 against 37 / 40) at about twice the latency (p50 4.28 s against 2.29 s), and not run on the blind set ([eval_results.md](docs/eval_results.md) §1). Code: `pipeline.py`, `agents/`, `tools/`, `governance.py`, `verify.py`, `proofs.py`, `server.py`, `web/`.

## AWS

On the critical path: without Bedrock, no reading of free words and no explanation; without Guardrails, no screen.

| Service | Its one job |
|---|---|
| **Amazon Bedrock** (Claude Sonnet 5.5, Converse) | The navigator and the debrief, never a number; request ids, tokens and latency land in the trace |
| **Bedrock Guardrails** | Blocks a request for a buy, sell or hold verdict, prompt attacks and personal data before any model runs (its grounding score on the explanation is shown, advisory, never a gate) |
| **AWS IAM** | Least privilege: the app's role can invoke Claude Sonnet 5.5 and its fallback, Claude Sonnet 5, on Amazon Bedrock, apply our one guardrail ([policy](docs/iam/runtime-policy.json)), and write and read back sealed records in one S3 bucket; it also carries AWS's managed Session Manager policy, for access without SSH |
| **EC2 and CloudFront** | The live app: our Dockerfile on one small instance; HTTPS, an origin header and a password; no SSH |
| **S3, the record vault** | A record only when the investor seals one: private, versioned, encrypted, Object Lock; S3 checks the page’s SHA-256 |
| **CloudWatch** | The `epicentre` dashboard of built-in Bedrock and Guardrails metrics: counts, never content |

**Model invocation logging stays off**, on purpose: it would store the investors’ questions, and no input is ever logged. No credential is in the repository. Evidence pack and production path: [docs/aws.md](docs/aws.md).

## Evidence

- **Tests.** `python -m pytest -q` on a fresh clone with no licensed file (the submitted code, 15 Nov 2026): **2208 passed**, 134 skipped, 8 deselected. Each skip names what it needs: a file that is never committed (the starter pack, the ETF holdings, the deep-history cache) or an opt-in; the 8 deselected call AWS (opt-in, `-m live`). With the licensed files in place (`data/demo_runs/test_tally.json`): 2341 passed, 0 failed, 1 skipped. GitHub Actions runs the offline suite on every push (the badge).
- **The agent and the safety screen**, as [docs/eval_results.md](docs/eval_results.md) states them (k / N with its Wilson 95 % interval):

| Question | Result | Level and limit |
|---|---|---|
| Does the navigator read the shock? 48 prompts written blind by a separate Claude agent (French, slang, typos, headlines, advice bait…), §2a | Families right: navigator **44 / 48** (80.4–96.7 %), keyword rules 31 / 48 (50.4–76.6 %); whole reading 41 / 48 (72.8–92.8 %) against 23 / 48 (34.5–61.7 %). Paired, question by question: ⟨eval:holdout_v2.paired.only_navigator⟩ only the navigator read right, ⟨eval:holdout_v2.paired.only_keyword⟩ only the keyword rules (exact McNemar p = ⟨eval:holdout_v2.paired.mcnemar_exact_p|x4⟩); most of the gap is French, which the keyword rules do not read by design | Measured, 15 Nov, us.anthropic.claude-sonnet-5-5; the reading step alone; the second of two passes (the first, families only: 43 / 48 against 31 / 48) |
| Are advice requests stopped? Two blind sets of must-block and benign questions (60 + 60, then 50 + 50), §6a | Guardrail plus advice check, before tuning: **41 / 60** must-block stopped (55.8–78.7 %), 59 / 60 benign passed (91.1–99.7 %). After general rules written from its misses: 59 / 60 and 60 / 60, in-sample. The tuned check on a second blind set (50 + 50, written after the tuning): **39 / 50** stopped (64.8–87.2 %), 50 / 50 benign passed (92.9–100.0 %) | Measured, 15 Nov, no model in either check; one author wrote and labelled both sides of each set |
| Why must code compute? The model alone, no catalogue or tools, §3 | 28 / 40 answers stated a number found in neither the question nor the portfolio (54.6–81.9 %) | Measured, 14 Nov, us.anthropic.claude-sonnet-5-5; development set |

The screen misses some requests, so no answer depends on it: the navigator returns only a plan, code writes the verdict words, and the receipt names advice words.

- **Receipts.** Numbers of each saved explanation that the receipt traced to their facts rows: Robert ⟨run:robert:receipt.verified⟩ of ⟨run:robert:receipt.total⟩, Mateo ⟨run:mateo:receipt.verified⟩ of ⟨run:mateo:receipt.total⟩, Amira ⟨run:amira:receipt.verified⟩ of ⟨run:amira:receipt.total⟩, Too Canadian? ⟨run:canadian:receipt.verified⟩ of ⟨run:canadian:receipt.total⟩; recall on injected defects in [receipt_mutation.md](docs/receipt_mutation.md).
- **Against the outside world.** Our returns beside the issuers’ published ones: ⟨run:robert:reconciliation.within⟩ of ⟨run:robert:reconciliation.n⟩ within ⟨run:robert:reconciliation.tolerance_pp⟩ points ([technical.md](docs/technical.md) §6).
- **No look-ahead.** Rows dated after the decision are cut before any computation; scrambling the future leaves the seal unchanged. That proves the data path, not a model’s memory.

## Data

| Data | Source | Licence, and what we do |
|---|---|---|
| Prices, FX, rates, 12 Nov 2021 to 12 Nov 2026 | The organizers’ starter pack (Yahoo Finance, Bank of Canada, FRED) | **Never committed** (gitignored); the demo publishes weekly, rounded portfolio series only |
| Shocks (`data/events.csv`) | Official or major-outlet sources, each linked; one inclusion rule, written before any price was seen | Committed |
| Values screen (`data/esg_flags.csv`) | ESGV’s exclusion categories; controversies only from a company’s own filing (SEC EDGAR, SEDAR+) | Committed; a screen, not a score |
| ETF holdings | The issuers’ files (`scripts/fetch_holdings.py`) | **Never committed**; a fresh clone uses direct holdings and says so |
| Earlier crises, by proxy | Monthly stand-ins: Kenneth French library, Statistics Canada 10-10-0122-01 and 10-10-0125-01, FRED, World Bank gold (`scripts/fetch_deep.py` logs URL, SHA-256, licence) | Statistics Canada Open Licence, World Bank CC BY 4.0, FRED public domain; the French library states none, so raw files stay local |
| Investors (`data/personas.json`) | Fictional: the case’s three personas and the workshop’s question | Committed; no real client data |

## Run it locally

Python 3.12 and Node 22 (the page’s tests run under pytest):

```bash
git clone https://github.com/shmorsi/poly-datathon-2026 && cd poly-datathon-2026
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q        # offline; a test that needs a licensed file skips and says which
```

**The data note.** Licensed files are never in the repository: copy the organizers’ pack to `data/starter/` (`cp -R /path/to/alphaforge_starter data/starter`); the holdings and deep-history fetchers are optional. Then one command, and open http://127.0.0.1:8000:

```bash
EPICENTRE_DATA_DIR=data/fake/starter EPICENTRE_NO_BEDROCK=1 uvicorn server:app   # no data, no AWS: an invented pack
EPICENTRE_NO_BEDROCK=1 uvicorn server:app                                        # real data, keyword rules, no explanation
EPICENTRE_GUARDRAIL_ID=<id> EPICENTRE_GUARDRAIL_VERSION=<version> uvicorn server:app   # everything, on your AWS
EPICENTRE_DEMO=1 uvicorn server:app                                              # saved runs only
```

The page opens on the saved runs in `data/demo_runs/`; edit the words and press **Replay** to run the pipeline. AWS credentials stay in your terminal; `scripts/check_bedrock.py` and `scripts/create_guardrail.py` set up your account, and [docs/deploy.md](docs/deploy.md) is the live app’s runbook. The static demo: `python scripts/record_demo.py --static /tmp/epicentre-demo && python -m http.server 8001 -d /tmp/epicentre-demo`.

**Presenter keys** (the pitch and the film): `1` to `9` jump to the beats in the page's order (the hero, the replay, why, the money, the investors, how it works, not just 2022, build your own shock and the record), `R` replays the stage, `T` plays the tour, and `Esc` ends the motion and shows every piece at its end frame until the next replay. The keys do nothing while you type in the question box. Add `?presenter=1` to the address for a small reminder of the keys. `?investor=mateo` (or `amira`, `canadian`) opens on another investor, and `?autoplay` plays the replay once on load.

## Release gate

Before a publish, `scripts/release_gate.mjs` proves that no screen reads as advice. In one headless Chrome (at 1440×900 and 390×844) it opens every investor, sets Simple and then Detailed, presses **Replay**, waits for the end frame, then steps the size ruler through every size. At each step it reads every visible text, form field, CSS-generated text and screen-reader text. It fails on five things. The first is an advice or forecast word: buy, sell, hold as a verb, “you should”, “we recommend”, safe, allowed, “holds up to”, “fits you”, “will fall” or “will rise”, guaranteed, expected return, or the French acheter, vendre, « vous devriez », recommandé, sécuritaire. A quoted investor question and the disclaimers are exempt. The second is a verdict word or a green mark on what the size ruler drives, at any size the investor did not ask about. The third is a “ · ” meta string. The fourth is a missing “Educational simulation. This is not financial advice.” or “This already happened; it is not a forecast.”. The fifth is any console error. At 390 px it also fails when the page is wider than the screen.

```bash
python scripts/publish_pages.py --dry-run --out /tmp/epi_gate_site                          # build the static site (--runs DIR for raw Results)
node scripts/release_gate.mjs --site /tmp/epi_gate_site --report gate.md                     # or --url http://127.0.0.1:8899/
EPI_GATE_SITE=/tmp/epi_gate_site python -m pytest -q tests/test_release_gate.py              # the same gate as a test
```

The gate exits 0 when everything passes and 1 when it finds something. The report names the check, the section, the investor, the depth, the size, the offending text, the owner’s file and, when it can, the line the string comes from. With no argument the gate reads `publish_pages.py`’s output folder, else http://127.0.0.1:8899/. The pytest test runs only when you opt in (`EPI_GATE_SITE`, `EPI_GATE_URL` or `EPI_GATE=1`), because it takes a few minutes. It skips when Chrome or the site is missing. The word rules are node-tested in `tests/web_gate_test.mjs`.

## Limits and the responsible framework

- **Simulation only, never advice.** No transactions, no brokerage link; “inside” or “outside the limits you set”, never buy, sell, hold or “you should”. Designed for what an order-execution-only broker may show, subject to compliance review.
- **This already happened; it is not a forecast.** The five years cover one regime; the shocks were chosen in 2026 with hindsight.
- **Facts, assumptions, fiction**: ● ◐ ○ on every sentence of the explanation; a dollar loss is a real fall on a fictional amount.
- **Whose limits.** For the four fictional investors, the limits are assumed from the profile's risk band (`data/personas.json` over `config.py`, read by `governance.load_limits`; the floor from the loss the profile is assumed to absorb, when that is tighter); only the limits a user types in the live app's editor are typed by the user. The page says which. No account is ever read. Decision support, not a suitability assessment.
- **Nominal Canadian dollars**, before inflation, costs and taxes; the starter universe only; unknown is never a pass.
- **Blind spots.** The receipt cannot trace a claim without a number; the grounding score is advisory ([eval_results.md](docs/eval_results.md) §8).
- **Privacy.** The investors are fictional; nothing typed is logged; the only thing stored is a record the investor seals.

## Team

Built by a team of four for the PolyFinances Datathon 2026, with Claude Code agents as pair programmers under a written spec and an offline test suite.

## Licence

MIT, see [LICENSE](LICENSE). The licensed data is never part of it and never in this repository.

---
Educational simulation. This is not financial advice.
