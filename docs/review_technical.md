# EPICENTRE | Portfolio X-ray

Technical notes · PolyFinances Datathon 2026 · AlphaForge AI · `portfolio-review` candidate

**In one paragraph.** EPICENTRE measures the portfolio as it stands and replays a user-defined change against the same historical market period. It exposes fund coverage and portfolio risk sources, explains where each metric comes from, and lets the investor request an explanation focused on an existing piece of evidence.

## 1. Workflow and architecture

The experiment asks whether a self-directed brokerage can explain portfolio concentration and the impact of a hypothetical order against an investor’s own limits. The experience starts with the current portfolio. The optional preview compares the new allocation on the same historical dates. National Bank Direct Brokerage is the reference brokerage for this product concept.

| Component | Role |
| --- | --- |
| `web/review.html` | Shows positions, Money and Risk lenses, dated ETF exposure, historical replay and selected evidence. The saved examples are Robert, Mateo, Amira and Too Canadian? |
| `POST /api/review` | Validates the input and applies an optional funded allocation change to a copy. It computes CAD portfolio paths, drawdown, risk contribution, ETF look-through, and evidence for the view. A review without an order returns the base portfolio alone. |
| `POST /api/review/explain` | Accepts a review reference and a stated goal. Amazon Bedrock can choose from the review’s existing evidence. The server validates the returned identifier and can choose an evidence item by rules when Bedrock is unavailable. |
| Saved static walkthrough | Renders derived, rounded weekly paths from recorded examples and approved industry aggregates. Company detail is available through the API when a compatible snapshot is installed. |

## 2. Calculation methods

**Positions and financing.** Enter a fictional account value in CAD, the current tickers and weights, a maximum historical drawdown and, optionally, a dollar loss capacity. Weights must total 100%. An order sets a target weight and can be funded from a selected holding. Optional preferences include a crypto allocation cap and a values screen based on issuer exclusions and documented company disclosures.

**Daily path.** The organizers’ starter set covers November 12, 2021 to November 12, 2026. The review aligns adjusted closes and converts USD-denominated lines using the Bank of Canada USD/CAD rate series. Both paths start with the same account value. The model rebalances to fixed weights daily. Wealth changes and their drawdowns are computed before fees, taxes and inflation. The chart distinguishes a fall from the running high from an absolute CAD balance floor based on the starting account value and entered dollar loss capacity.

**Risk lens.** The money weight is the fraction invested. Risk share allocates historical portfolio variance using the covariance of daily CAD returns. Multiply a holding’s weight by its covariance with the portfolio, then divide by portfolio variance. Volatility and correlation can make the modeled contribution larger than the money weight. A diversifying holding’s contribution can be negative. Individual risk shares use held securities and funds as portfolio lines. Sector and company look-through shows economic exposure in the Money lens.

**ETF exposure.** An industry’s portfolio share is the fund’s portfolio weight multiplied by the industry’s share of the fund. Company exposure combines a direct investment with attributable portions of disclosed ETF holdings. The output identifies the source, snapshot date and disclosed coverage. A missing or newer-than-review snapshot limits the drill-through. Dated company coverage and sector coverage can differ. The holdings snapshot describes present-day exposure. The price replay uses historical fund prices.

## 3. Explanation and controls

The evidence is created by the calculation. A typical item records a comparison, units, method and provenance, such as the largest historical drawdown or the amount attributable to an ETF. The optional Amazon Bedrock Converse call receives the selected focus and evidence labels. It selects an identifier from that set. The application displays the server-computed evidence text for the selected identifier. Submitted holdings and the underlying price or issuer rows stay outside the model request. The goal is screened for account details and advice requests before it reaches the model. A deterministic selector supplies a verified item when the model is unavailable or its response fails validation. The browser can show market context as an optional disclosure.

A review reference must correspond to an existing calculation. The order is simulated in application state. The prototype reads fictional positions, never connects to a brokerage account and has no trade execution path. The original project includes a password-protected EC2 and CloudFront deployment design, Bedrock Guardrails and a least-privilege runtime role. See the AWS notes for evidence from the classic workflow. [AWS architecture and evidence](aws.md)

## 4. Evidence example

In the recorded Robert example, XIU is 45% of the existing allocation and 71.1% of its historical risk contribution. To reproduce the displayed risk share, use the baseline weights and the covariance of aligned daily CAD returns. The optional hypothetical 40% NVIDIA allocation is compared to the original portfolio on those same market dates. Its recorded low is $408,174 CAD and it is below the assumed $510,000 CAD balance floor for 188 market sessions. The starting $600,000 CAD and $90,000 CAD capacity are fictional assumptions. The public path is rounded for display. [Calculation methods and provenance](finance_methods.md)

For a holdings example, open XIU’s Financials exposure. The saved issuer snapshot reports 41.23% of the fund in Financials. Multiplying by Robert’s 45% fund weight gives approximately 18.55% of the whole portfolio. The holding date, coverage and issuer link let the user inspect this result. [XIU issuer page](https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf)

## 5. Reproduction and validation

Use the `portfolio-review` checkout. Install the Python dependencies, put the organizers’ starter set in `data/starter/`, run `EPICENTRE_NO_BEDROCK=1 uvicorn server:app --host 127.0.0.1 --port 8000`, then open `/review.html`. Put a permitted issuer snapshot in `data/etf_holdings.csv` to enable company detail. For Bedrock, run with the project’s AWS configuration and credentials. See the README and deployment runbook for variables. [Runbook](deploy.md)

The review API checks cover same-base historical paths, single-holding funding limits, combined direct and fund exposure, a baseline-only request and rejection of an unknown evidence reference. Frontend checks cover weight parsing, funding validation, drawdown from a running high and ticker identification. The saved view can be inspected separately to confirm it carries only the public cut. [Python checks](../tests/test_order_review.py) · [Browser logic checks](../tests/test_review_frontend.mjs)

## 6. Limitations and next steps

The five-year window covers a limited set of market conditions. The historical statistic depends on the price and currency data, weights, dates and daily rebalancing assumption. The modeled loss says how these allocations behaved over that window. A fund snapshot shows only its dated disclosure and can omit underlying companies. Future product work could add a broader instrument universe, more dated issuer snapshots and usability measurement at the brokerage order ticket.
