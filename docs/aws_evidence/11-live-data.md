# The live app's data: how the instance got it, and its key numbers beside the laptop's

The licensed local files were never copied by an agent. On the instance, the organizers' own `build_dataset.py` (read
line by line first: HTTPS downloads from Yahoo Finance, the Bank of Canada and FRED, CSV writes, nothing else) rebuilt
the starter data in a throwaway container with no AWS credentials and the instance metadata endpoint blocked; the ETF
holdings came from the issuers with `scripts/fetch_holdings.py`; `scripts/fetch_deep.py` could not run there (the
Kenneth French library refuses connections from the instance). Then the repository's own pipeline ran the four
investors with Bedrock off, on the laptop and on the instance, so only the data differs.

Facts read on the instance:

- starter/assets_universe.csv: 31 rows, sha256 f78de8ecb36d
- starter/prices_daily.csv: 40049 rows, sha256 71e15c1c6829
- starter/corporate_actions.csv: 658 rows, sha256 37d99f1472f9
- starter/fx_usdcad_daily.csv: 1245 rows, sha256 f04e218ac5b0
- starter/macro_rates.csv: 8284 rows, sha256 a78800ff64b8
- starter/data_quality_warnings.txt: Generated 2026-11-15. Window 2021-11-12 to 2026-11-12. No warnings. 
- the script that built them: build_dataset.py sha256 1c6bd7ce45e3 (the organizers' file, reviewed line by line)
- holdings fetched on the instance: 73 rows; newest holding row dated 2026-11-13
- deep panel on the instance: absent

| Investor | Worst fall today, laptop / instance | With the move, laptop / instance | The mix's verdict today, laptop / instance | Look-through, laptop / instance |
|---|---|---|---|---|
| Robert | −10.61 % / −10.61 % | −34.52 % / −34.52 % | Inside your limits / Inside, with caveats | lookthrough / direct |
| Mateo | −11.43 % / −11.43 % | n/a / n/a | Inside, with caveats / Inside, with caveats | lookthrough / direct |
| Amira | −41.35 % / −41.35 % | n/a / n/a | Inside, with caveats / Inside, with caveats | lookthrough / direct |
| Too Canadian? | −11.92 % / −11.92 % | −12.90 % / −12.90 % | Inside your limits / Inside, with caveats | lookthrough / direct |

The prices agree. The look-through differs for one reason: holdings fetched today are dated after the replay's last
day (12 Nov 2026), and `tools/lookthrough.py` reads funds directly for any snapshot newer than the run (red gate 3,
no look-ahead). Until the team sends the laptop's holdings file and deep panel (`send_data.sh`), the live server
(from the final redeploy on) reports `"holdings": false` on `/api/health`, the live page is to say so in one line (asked of the UI lane), and the
saved runs stay the canonical demo. This already happened; it is not a forecast.

Captured 2026-11-15 16:41 UTC. Masked like the rest of the pack.

## After the redeploy of 13:50 EST: the live runs beside the saved runs (the final one: 13-final-redeploy.txt)

Run through CloudFront with the password on the final code (guardrail version 1, 2026-11-15 18:58 UTC); each verdict is the run's own.

| Investor | Live verdict | Saved run's verdict | Same | The mix today, live / saved |
|---|---|---|---|---|
| Robert | Outside your limits | Outside your limits | yes | Inside, with caveats / Inside your limits |
| Mateo | Outside your limits | Outside your limits | yes | n/a / n/a |
| Amira | Inside, with caveats | Inside, with caveats | yes | n/a / n/a |
| Too Canadian? | Inside, with caveats | Inside your limits | no | Inside, with caveats / Inside your limits |

Where they differ, the cause is the one above: the live server reads funds directly until it has holdings dated on or
before the replay's last day, so a check that looks through a fund's holdings can read differently. The saved runs stay
the canonical demo; `/api/health` says `"holdings": false` and the live page says so in one line.
