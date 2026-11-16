# ÉPICENTRE

**See what your next trade changes.**

See through your ETFs, then replay a trade against your own loss limits. ÉPICENTRE is a portfolio and order preview for self-directed investors, built for the 2026 PolyFinances AlphaForge AI Datathon.

[Open the public demo](https://shmorsi.github.io/poly-datathon-2026/) · [Open the AWS workspace](https://dqetfenyawfe9.cloudfront.net/review.html) · [Technical notes](docs/review_technical.md) · [One-pager](docs/review_one_pager.md)

## Try the review

Open **Robert’s portfolio** and switch from **Money** to **Risk**. XIU holds 45% of his money and accounts for about 71% of his modeled portfolio risk. Preview the 40% NVIDIA order to see the same market history with and without the trade, then open the evidence behind the lowest balance.

| Example | What to explore |
| --- | --- |
| **Robert** | See when the proposed NVIDIA order would have crossed his illustrative drawdown and balance limits. |
| **Mateo** | See which issuers trigger his values screen and where the fund disclosures leave gaps. |
| **Amira** | Compare her 15% crypto allocation with a 10% cap and see NVIDIA exposure across direct and ETF positions. |
| **Too Canadian?** | Compare estimated country exposure and historical drawdown after adding U.S. equity exposure. |

The public demo includes four saved cases. In the authenticated AWS workspace, choose **Use my portfolio** to enter your own positions, set optional limits in plain language, and see available issuer-level holdings. All portfolios and orders are simulated.

## From a question to evidence

The application calculates allocation, risk and historical losses. Bedrock Guardrails screen the investor’s question. Claude then uses the `open_evidence` tool to select up to three existing evidence cards. The application validates the selected IDs and displays the calculated result with its source and method. It can select evidence using rules if Bedrock is unavailable.

[Architecture and methods](docs/review_technical.md) · [AWS setup](docs/aws.md) · [Deployment runbook](docs/deploy.md)

## Run locally

Use Python 3.12 and Node.js 22.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
EPICENTRE_NO_BEDROCK=1 uvicorn server:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/review.html` for the saved cases. For custom calculations, place the organizers’ starter pack in `data/starter/` or set `EPICENTRE_DATA_DIR`. Add an eligible issuer snapshot at `data/etf_holdings.csv` for detailed ETF holdings. For Bedrock, configure the standard AWS credential chain and set `EPICENTRE_GUARDRAIL_ID` and `EPICENTRE_GUARDRAIL_VERSION` to the published guardrail. Keep the market data and issuer inputs in your local environment.

```sh
python -m pytest -q
node --test tests/test_review_frontend.mjs
python scripts/publish_pages.py --portfolio-review --dry-run --out /tmp/epicentre-review-pages
```

Replays use daily adjusted closes in CAD through 12 Nov 2026 and hold target weights constant before fees and taxes. ETF exposure uses dated issuer disclosures with coverage visible in the app. The public demo uses rounded weekly paths and industry summaries.

[MIT License](LICENSE)
