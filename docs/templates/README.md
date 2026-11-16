# ÉPICENTRE

**Test your move before you make it.**

An investor enters a portfolio and can preview a proposed order. ÉPICENTRE shows how the order would have changed the holdings, risk and exposure through the same historical markets, with evidence the investor can open.

- [Public interactive walkthrough](https://shmorsi.github.io/poly-datathon-2026/)
- [AWS workspace](https://dqetfenyawfe9.cloudfront.net/review.html) with the team's access details
- [One-pager](docs/review_one_pager.md) · [Technical notes](docs/review_technical.md) · [Demo script](docs/review_demo_script.md)

Built for the PolyFinances Datathon 2026 AlphaForge AI case. A self-directed brokerage could place this review beside its order preview. All portfolios and orders are simulated.

## Four walkthroughs

| Example | What to try |
| --- | --- |
| **Robert** | Preview a 40% NVIDIA target. Compare the two historical paths, the largest fall from a previous high, and the lowest account balance. The sample's values and limits are fictional assumptions. |
| **Mateo** | Check the documented values exclusions and inspect the companies inside his funds. Coverage gaps stay visible. |
| **Amira** | Compare her crypto allocation with the illustrative 10% cap, then inspect her direct and fund-mediated NVIDIA exposure. |
| **Too Canadian?** | Preview a 20% U.S. equity allocation and compare estimated country exposure and historical drawdown. |

The AWS workspace also accepts a custom portfolio. The starter set covers 31 securities, including Canadian and U.S. stocks, equity, bond, ESG and gold ETFs, and two digital assets. Investors can leave risk limits empty.

## How the agent works

The app computes the historical results before calling a model. When the investor asks for an explanation, Bedrock Guardrails screen the concern. Claude can select up to three eligible evidence cards in one Converse tool-use response. Code checks the selected IDs and renders the exact computed facts with their sources. The model receives the concern and evidence labels, and its generated words cannot appear as a financial result. The workspace can return a rules-based explanation if Bedrock is unavailable.

## Run locally

Python 3.12 and Node.js 22 are used for the app and tests.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
EPICENTRE_NO_BEDROCK=1 uvicorn server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/review.html`. The saved illustrations load without AWS or a market data pack. For editable calculations, supply the organizers' starter pack in `data/starter/` or set `EPICENTRE_DATA_DIR`. A dated issuer snapshot at `data/etf_holdings.csv` enables detailed company look-through. Both inputs are private local files. For the model-enabled workflow, configure the standard AWS credential chain and set `EPICENTRE_GUARDRAIL_ID` and `EPICENTRE_GUARDRAIL_VERSION` to the published policy. The [AWS notes](docs/aws.md) and [deployment runbook](docs/deploy.md) describe the stack. Set `EPICENTRE_LANDING=review` to serve the order-review landing from the app root.

```sh
python -m pytest -q
node --test tests/test_review_frontend.mjs
python scripts/publish_pages.py --portfolio-review --dry-run --out /tmp/epicentre-review-pages
```

## Sources and boundaries

- Portfolio replays use CAD-adjusted closes through ⟨run:robert:as_of|date⟩ with constant target weights. They exclude taxes and trading fees. The history includes only assets available in the supplied universe.
- Industry and company allocations use dated issuer snapshots when available. A fund's mapped positions may cover only part of its holdings. Public examples publish rounded, sampled portfolio paths and industry summaries. Detailed issuer positions are served through the authenticated workspace.
- The review evaluates historical outcomes and documented user preferences. It does not place orders, recommend investments or forecast returns.

The earlier replay is preserved at [v1.0-submission](https://github.com/shmorsi/poly-datathon-2026/tree/v1.0-submission). Its **Presenter keys** appear in the classic local page at `/index.html?presenter=1`. Code is MIT-licensed. [License](LICENSE)
