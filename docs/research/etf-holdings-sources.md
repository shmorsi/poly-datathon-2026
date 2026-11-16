# ETF holdings: sources, dates and licence (public note)

The look-through data itself is **not in this repo**: BlackRock/iShares, State Street, Invesco
and Vanguard all forbid redistributing fund holdings ("in whole or in part"). Run
`python scripts/fetch_holdings.py` (or get the local `data/etf_holdings.csv` from the team).
Research done 2026-11-14 from the issuers' own files.

| ETF | Issuer page | Holdings as of | Sectors / countries as of | Top-25 coverage |
|---|---|---|---|---|
| XIU.TO | https://www.blackrock.com/ca/investors/en/products/239832/ishares-sptsx-60-index-etf | 2026-11-12 | 2026-11-12 | 76.8 % |
| SPY | https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy | 2026-11-12 | 2026-11-12 | 51.8 % |
| QQQ | https://www.invesco.com/qqq-etf/en/about.html | 2026-11-12 | 2026-10-31 (ICB sectors) | 71.4 % |
| ESGV | https://investor.vanguard.com/investment-products/etfs/profile/esgv | 2026-11-12 | 2026-09-30 (ICB sectors) | 54.1 % |
| XBB.TO | https://www.blackrock.com/ca/investors/en/products/239493/ishares-core-canadian-universe-bond-index-etf | 2026-11-12 | Canada ≈ 96 % | n/a (bonds) |
| ZST.TO | https://bmogam.com/ca-en/products/exchange-traded-fund/bmo-ultra-short-term-bond-etf-zst/ | page data not readable | CAN assumed (listing market), to verify | n/a |
| AGG, TLT | iShares US product pages 239458, 239454 | 2026-11-12 | USA (simplification) | n/a |
| GLD | https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld | n/a | "Global": shown apart on the globe, like crypto | n/a |

Facts the app and the demo rely on (from the files above):
- NVDA is 6.14 % of SPY, 6.53 % of QQQ and 6.58 % of ESGV.
- XIU.TO holds ENB 3.59 % and CNQ 3.45 %; XIU.TO's Energy sector is 16.65 %.
- XOM is in SPY (1.07 %), not in ESGV.
- QQQ and ESGV report ICB sectors; docs/finance_methods.md maps them to GICS.
- ESGV's exclusion screens are published on its Vanguard page (used for the ESG check, §9).
