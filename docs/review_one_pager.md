# EPICENTRE | Portfolio X-ray

**See what you own and what a hypothetical order would change.**

`portfolio-review` candidate

## The problem

A brokerage order shows the new position. Robert, a fictional investor approaching retirement, also needs to see how it would change the rest of his portfolio and how both allocations behaved in a difficult market. EPICENTRE brings that comparison beside the holdings for a self-directed brokerage such as National Bank Direct Brokerage.

## The investor experience

Start with the existing portfolio and a loss limit. Switch from **Money** to **Risk** to see which positions drove historical volatility. Open XIU to see its underlying industry exposure and the issuer’s dated snapshot. Company drill-through combines direct positions with disclosed ETF holdings when the issuer data is available. A hypothetical order is optional.

In Robert’s recorded example, XIU accounts for **45% of his money** and about **71% of his modeled portfolio risk**. Previewing a **40% NVIDIA** position makes NVIDIA the source of about **90% of modeled risk**. During the historical replay, the proposed allocation falls to about **$408,000 CAD**, below his assumed **$510,000 CAD** floor. Both allocations start at the same fictional balance.

## The agentic approach

Code calculates exposures, risk and the historical replay first. If the investor asks for an explanation, Amazon Bedrock can use the evidence tool to select an existing item relevant to the investor’s goal. The application checks that selection and displays its source and method. A retirement focus can lead to the loss evidence, while an exposure focus can lead to an ETF breakdown.

## The benefit

Investors can inspect concentration inside a fund and see the size and duration of a historical loss. Mateo can check his selected values exclusions, and Amira can compare her crypto allocation with her cap. The broker can offer the same educational preview beside the portfolio view with an editable allocation.

## Data and limitations

Daily adjusted prices from the Datathon starter set, Bank of Canada CAD conversion rates, and available dated issuer holdings. Public examples use rounded weekly portfolio paths and selected industry aggregates. Company coverage is partial and depends on eligible issuer snapshots. The historical results use fixed target weights with daily rebalancing and exclude fees, taxes and inflation.

---

[Project repository](https://github.com/shmorsi/poly-datathon-2026) · Review entry point `/review.html`

*Educational simulation. No orders are placed.*
