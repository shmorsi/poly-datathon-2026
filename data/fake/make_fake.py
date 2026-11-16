"""FAKE synthetic data for development and tests, not market data.

Run from the repo root:  python data/fake/make_fake.py
It regenerates every generated file under data/fake/:
  starter/assets_universe.csv, prices_daily.csv, fx_usdcad_daily.csv, macro_rates.csv
      a 6-ticker pack in the exact starter column format (spec section 9), random walks
  result.json               the spec section 12 Result: Robert, today -> after, FAKE values (with a FAKE
                            `deep_history` fragment, ledger 17: the shape, counts and sentence come from tools.deep)
  result_time_machine.json  the same shape at as_of 2025-01-31, with `realized` filled
Nothing here is tool output or market data. The six universe rows are copied from the
organizers' assets_universe.csv (free to use within the datathon); every other number is invented
so the page, the pipeline and the loaders can be built before the real tools land.
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
START, END = date(2021, 11, 12), date(2026, 11, 12)

# Holidays that exercise the union calendar and the per-asset t0 (spec section 10).
TSX_ONLY = {"2023-10-09", "2024-07-01"}                 # TSX closed, US open
US_ONLY = {"2023-11-23", "2025-07-04", "2026-01-19"}    # US closed, TSX open
BOTH_CLOSED = {"2022-12-26", "2025-12-25"}
ZST_GAP = ("2024-03-04", "2024-03-08")                  # 5 trading days with no ZST.TO row

# asset_id, ticker, name, asset_class, market, currency, sector (copied from the starter pack)
UNIVERSE = [
    ("A13", "NVDA", "NVIDIA", "equity", "NASDAQ", "USD", "Information Technology"),
    ("A21", "XIU.TO", "iShares S&P/TSX 60 Index ETF", "etf_equity", "TSX", "CAD",
     "Broad market (Canada)"),
    ("A25", "XBB.TO", "iShares Core Canadian Universe Bond Index ETF", "etf_bond", "TSX", "CAD",
     "Bonds (Canada aggregate)"),
    ("A26", "ZST.TO", "BMO Ultra Short-Term Bond ETF", "etf_bond", "TSX", "CAD",
     "Bonds (Canada ultra short-term)"),
    ("A29", "GLD", "SPDR Gold Shares", "etf_commodity", "NYSE Arca", "USD", "Gold"),
    ("A30", "BTC-USD", "Bitcoin", "crypto", "Crypto (24/7)", "USD", "Crypto asset"),
]
# start price and daily volatility of the invented random walks
WALK = {"NVDA": (30.0, 0.03), "XIU.TO": (30.0, 0.01), "XBB.TO": (28.0, 0.003),
        "ZST.TO": (49.0, 0.003), "GLD": (170.0, 0.01), "BTC-USD": (64000.0, 0.04)}


def weekdays():
    """Every weekday START..END as ISO strings."""
    out, d = [], START
    while d <= END:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def calendar_days():
    out, d = [], START
    while d <= END:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def row_dates(market):
    """The dates a listing has a row on: TSX, US exchanges, or every UTC day for crypto."""
    if market == "TSX":
        closed = TSX_ONLY | BOTH_CLOSED
    elif market.startswith("Crypto"):
        return calendar_days()
    else:
        closed = US_ONLY | BOTH_CLOSED
    return [d for d in weekdays() if d not in closed]


def make_prices(rng):
    frames = []
    for _id, ticker, _name, _cls, market, currency, _sector in UNIVERSE:
        days = row_dates(market)
        px0, vol = WALK[ticker]
        steps = rng.normal(0.0, vol, len(days))
        steps[0] = 0.0
        close = np.round(px0 * np.exp(np.cumsum(steps)), 6)
        volume = rng.integers(10_000, 1_000_000, len(days))
        frame = pd.DataFrame({"date": days, "ticker": ticker, "open": close, "high": close,
                              "low": close, "close": close, "adj_close": close,
                              "volume": volume, "currency": currency})
        if ticker == "ZST.TO":
            frame = frame[~frame.date.between(*ZST_GAP)]
        frames.append(frame)
    prices = pd.concat(frames, ignore_index=True)
    return prices.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)


def make_fx(rng):
    """usdcad on weekdays minus the Canadian holidays (as in the real Bank of Canada file)."""
    days = [d for d in weekdays() if d not in TSX_ONLY | BOTH_CLOSED]
    x, rows = 1.35, []
    for d in days:
        x += 0.05 * (1.35 - x) + 0.003 * rng.standard_normal()
        usdcad = round(x, 4)
        rows.append((d, usdcad, round(1.0 / usdcad, 6)))
    return pd.DataFrame(rows, columns=["date", "usdcad", "cadusd"])


def make_macro():
    """V39079 (policy rate, percent) on the first of each month: 0.25 until 2022-02-28, then 4.00."""
    rows, y, m = [], START.year, START.month
    while date(y, m, 1) <= END:
        d = date(y, m, 1)
        value = 0.25 if d <= date(2022, 2, 28) else 4.00
        rows.append((d.isoformat(), "V39079", value, "percent", "monthly (FAKE)",
                     "Bank of Canada target for the overnight rate (FAKE)", "FAKE synthetic data"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return pd.DataFrame(rows, columns=["date", "series_id", "value", "unit", "frequency", "label",
                                       "source"])


def write_starter(out=None):
    out = Path(out) if out else HERE / "starter"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    pd.DataFrame(UNIVERSE, columns=["asset_id", "ticker", "name", "asset_class", "market",
                                    "currency", "sector"]).to_csv(out / "assets_universe.csv",
                                                                   index=False)
    make_prices(rng).to_csv(out / "prices_daily.csv", index=False)
    make_fx(rng).to_csv(out / "fx_usdcad_daily.csv", index=False)
    make_macro().to_csv(out / "macro_rates.csv", index=False)


# ---------------------------------------------------------------------------------------------
# The sample Result (spec section 12). Every number below is FAKE: invented for UI development,
# loosely shaped like the section 3 previews for Robert. The tools recompute the real ones.
# ---------------------------------------------------------------------------------------------
NOTE = "FAKE values for UI development, not tool output"
AMOUNT = 600000
DATASET_END = "2026-11-12"
TM_AS_OF = "2025-01-31"
TODAY_W = {"XIU.TO": 0.45, "XBB.TO": 0.35, "GLD": 0.10, "ZST.TO": 0.10}
AFTER_W = {"NVDA": 0.40, "XIU.TO": 0.27, "XBB.TO": 0.21, "GLD": 0.06, "ZST.TO": 0.06}
ALIGNED_W = {"XBB.TO": 0.30, "XIU.TO": 0.35, "SPY": 0.25, "GLD": 0.10}   # moderate mix, spec 10
QUESTION = ("Everyone is talking about NVIDIA. What if I put 40 % in it and Washington slaps new levies on "
            "Canadian goods?")
FAMILIES = ["tariffs", "war_oil", "chips", "rates"]
# Days the exchanges were closed inside the event windows (for t+20 only; FAKE precision).
HOLIDAYS = ["2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20", "2022-07-01", "2022-07-04",
            "2022-09-05", "2022-10-10", "2022-11-24", "2023-10-09", "2023-11-23", "2024-07-04",
            "2024-09-02", "2024-11-28", "2024-12-25", "2025-01-01", "2025-01-20", "2025-02-17",
            "2025-04-18", "2025-05-19", "2025-05-26", "2025-07-04", "2025-09-01", "2025-11-27",
            "2025-12-25", "2026-01-19", "2026-02-16", "2026-04-03"]
WHITE_HOUSE = (38.90, -77.04)
OTTAWA = (45.42, -75.70)
FED = (38.89, -77.05)
PBS = "https://www.pbs.org/newshour/economy/u-s-stocks-shoot-to-historic-gains-after-trump-pauses-most-of-his-tariffs"

# id, date, title, description, family, sign, regions, (lat, lon), source_url, episode,
# confounded, trough_date, today (trough, ret_20, fx_effect, percentile), after (same), exposed
# Troughs are fractions, clipped at 0 (a rise is "no loss"); percentile = worse than that share
# of all 21-day windows. Descriptions paraphrase data/events.csv and the research file.
EVENT_TABLE = [
    ("ukraine_2022", "2022-02-24", "Russia invades Ukraine",
     "Russia invades Ukraine; European stock markets fall and oil climbs.", "war_oil",
     "negative", "UKR;RUS;EUR", (50.45, 30.52),
     "https://www.cnbc.com/2022/02/24/global-markets-roiled-as-russia-invades-ukraine.html",
     "war_oil_feb_2022", False, "2022-03-08", (-0.021, -0.004, 0.0015, 0.62),
     (-0.052, -0.013, 0.0042, 0.71),
     [("CNQ.TO", "sector", "XIU.TO"), ("ENB.TO", "sector", "XIU.TO")]),
    ("fed_75_2022", "2022-06-15", "The Fed raises rates by 0.75 point",
     "The Fed raises its benchmark rate by three-quarters of a point to a 1.5 %-1.75 % range, "
     "its most aggressive hike since 1994.", "rates", "negative", "USA", FED,
     "https://www.cnbc.com/2022/06/15/fed-hikes-its-benchmark-interest-rate-by-three-quarters-of-a-point-the-biggest-increase-since-1994.html",
     "rates_jun_2022", False, "2022-06-24", (-0.034, -0.012, 0.0012, 0.88),
     (-0.126, -0.071, 0.0055, 0.96), [("NVDA", "country", "direct")]),
    ("cpi_sep_2022", "2022-09-13", "Hotter-than-expected US inflation (August CPI)",
     "A hotter-than-expected August inflation report revives fears of an aggressive Fed.",
     "rates", "negative", "USA", FED,
     "https://www.cnbc.com/2022/09/12/stock-futures-are-higher-as-wall-street-awaits-key-inflation-report-.html",
     "rates_sep_2022", False, "2022-09-30", (-0.041, -0.019, 0.0020, 0.93),
     (-0.158, -0.094, 0.0068, 0.985), [("NVDA", "country", "direct")]),
    ("chips_2022", "2022-10-07", "US export controls on advanced chips to China",
     "The Bureau of Industry and Security restricts China's access to advanced chips and "
     "chip-making equipment.", "chips", "negative", "USA;CHN;TWN", (39.90, 116.40),
     "https://www.bis.gov/press-release/commerce-implements-new-export-controls-advanced-computing-semiconductor-manufacturing-items-peoples",
     "chips_oct_2022", False, "2022-10-14", (-0.024, -0.008, 0.0010, 0.75),
     (-0.138, -0.082, 0.0049, 0.97), [("NVDA", "sector", "direct")]),
    ("israel_2023", "2023-10-09", "Hamas attack on Israel (first trading day)",
     "First trading day after the 7 October attack: oil jumps while gold and bonds rise.",
     "war_oil", "negative", "ISR;PSE", (31.50, 34.47),
     "https://www.investmentnews.com/equities/oil-spikes-and-equities-fall-following-hamas-attack-on-israel/244284",
     "war_oil_oct_2023", False, "2023-10-12", (-0.011, -0.003, 0.0009, 0.45),
     (-0.029, -0.010, 0.0021, 0.55),
     [("CNQ.TO", "sector", "XIU.TO"), ("ENB.TO", "sector", "XIU.TO")]),
    ("tariff_threat_2024", "2024-11-26", "Threat of 25 % tariffs on Canada and Mexico",
     "The president-elect promises an order on 20 January imposing 25 % tariffs on all products "
     "from Canada and Mexico, and 10 % more on China.", "tariffs", "negative",
     "USA;CAN;MEX;CHN", OTTAWA,
     "https://www.cnbc.com/2024/11/26/trumps-tariff-threats-signal-start-of-a-wild-ride-in-currency-markets.html",
     "tariffs_nov_2024", False, "2024-12-03", (-0.010, -0.003, 0.0016, 0.35),
     (-0.019, -0.006, 0.0030, 0.40),
     [("XIU.TO", "country", "direct"), ("NVDA", "currency", "direct")]),
    ("deepseek_2025", "2025-01-27", "DeepSeek shock hits AI stocks",
     "A low-cost Chinese AI model triggers a sharp fall in chip stocks.", "chips",
     "negative", "CHN;USA", (30.27, 120.15), "https://fortune.com/2025/01/27/nvidia-deepseek-rout-tech-stocks/",
     "chips_jan_2025", False, "2025-01-27", (-0.018, -0.006, 0.0008, 0.66),
     (-0.112, -0.049, 0.0038, 0.95), [("NVDA", "sector", "direct")]),
    ("tariffs_order_2025", "2025-02-03", "US tariff orders: Canada, Mexico, China",
     "Executive orders of 1 February: 25 % tariffs on Canada and Mexico (10 % on Canadian "
     "energy) and 10 % on China. First trading day 3 February.", "tariffs", "negative",
     "USA;CAN;MEX;CHN", WHITE_HOUSE,
     "https://www.whitehouse.gov/fact-sheets/2025/02/fact-sheet-president-donald-j-trump-imposes-tariffs-on-imports-from-canada-mexico-and-china/",
     "tariffs_feb_mar_2025", False, "2025-02-28", (-0.031, -0.011, 0.0018, 0.82),
     (-0.058, -0.017, 0.0031, 0.84),
     [("XIU.TO", "country", "direct"), ("XBB.TO", "country", "direct"),
      ("NVDA", "currency", "direct")]),
    ("tariffs_canada_2025", "2025-03-04", "25 % US tariffs on Canada take effect",
     "The US tariffs on Canada take effect; Canada retaliates with 25 % on C$30 billion of "
     "imports.", "tariffs", "negative", "USA;CAN", OTTAWA,
     "https://www.kitco.com/news/off-the-wire/2025-03-04/tsx-hits-near-two-month-low-us-tariffs-take-effect",
     "tariffs_feb_mar_2025", False, "2025-03-10", (-0.027, -0.009, 0.0014, 0.79),
     (-0.049, -0.020, 0.0027, 0.81),
     [("XIU.TO", "country", "direct"), ("XBB.TO", "country", "direct"),
      ("NVDA", "currency", "direct")]),
    ("liberation_day_2025", "2025-04-03", "Liberation Day reciprocal tariffs",
     "Announced 2 April after the close: a 10 % baseline tariff and reciprocal tariffs of 11 % "
     "to 50 %.", "tariffs", "negative", "USA;CHN;CAN;EUR", WHITE_HOUSE, PBS,
     "tariffs_apr_2025", False, "2025-04-08", (-0.060, -0.021, 0.0033, 0.92),
     (-0.090, -0.033, 0.0052, 0.90),
     [("XIU.TO", "country", "direct"), ("NVDA", "country", "direct"),
      ("GLD", "currency", "direct")]),
    ("tariff_pause_2025", "2025-04-09", "90-day pause on reciprocal tariffs",
     "Positive shock: a 90-day pause on the reciprocal tariffs.", "tariffs", "positive",
     "USA", WHITE_HOUSE, PBS, "tariffs_apr_2025", False, None, (0.0, 0.034, -0.0011, 0.0),
     (0.0, 0.062, -0.0021, 0.0), [("NVDA", "country", "direct")]),
    ("canada_talks_2025", "2025-10-24", "Trade talks with Canada ended",
     "Washington ends trade talks with Canada after an Ontario advertisement quoting Ronald "
     "Reagan.", "tariffs", "negative", "USA;CAN", OTTAWA,
     "https://www.bloomberg.com/news/articles/2025-10-24/trump-says-all-trade-talks-with-canada-are-terminated",
     "tariffs_oct_2025", False, "2025-11-20", (-0.012, -0.004, 0.0006, 0.48),
     (-0.024, -0.009, 0.0011, 0.52),
     [("XIU.TO", "country", "direct"), ("XBB.TO", "country", "direct")]),
    ("scotus_ieepa_2026", "2026-02-20", "Supreme Court strikes down the IEEPA tariffs",
     "The Supreme Court rules 6-3 that IEEPA does not authorize tariffs, invalidating the "
     "reciprocal tariffs; that evening a 10 % global tariff is signed.", "tariffs", "negative",
     "USA;CAN;MEX;CHN", WHITE_HOUSE, "https://www.cnbc.com/2026/02/20/trump-global-trade-tariff-supreme-court.html",
     "tariffs_feb_2026", True, "2026-03-10", (-0.022, -0.007, 0.0010, 0.70),
     (-0.071, -0.030, 0.0033, 0.80),
     [("XIU.TO", "country", "direct"), ("NVDA", "currency", "direct")]),
    ("iran_2026", "2026-03-02", "US-Israeli strikes on Iran",
     "Strikes on Saturday 28 February raise risk for the Strait of Hormuz. First trading day "
     "2 March.", "war_oil", "negative", "USA;ISR;IRN", (35.69, 51.39),
     "https://www.spglobal.com/energy/en/news-research/latest-news/crude-oil/022826-us-and-israel-strike-iran-raising-oil-supply-security-risks",
     "war_oil_mar_2026", False, "2026-03-09", (-0.018, -0.006, 0.0009, 0.58),
     (-0.044, -0.015, 0.0023, 0.66),
     [("CNQ.TO", "sector", "XIU.TO"), ("ENB.TO", "sector", "XIU.TO")]),
]
# The co-event that makes tariffs_feb_2026 a mixed (confounded) episode under rule B (spec 10).
CONFOUNDED_BY = {"tariffs_feb_2026": "iran_2026"}


def bday_add(iso, n):
    """t+n trading days, weekdays minus the HOLIDAYS list (FAKE precision)."""
    return str(np.busday_offset(iso, n, roll="forward", holidays=HOLIDAYS))


def build_events(as_of):
    """Event rows for every catalog event dated <= as_of (spec 12 shape).
    known = its t+20 is <= as_of; otherwise in progress, shown greyed with no impacts (spec 10)."""
    rows = []
    for (eid, d, title, desc, fam, sign, regions, (lat, lon), url, episode, conf, trough_date,
         today, after, exposed) in EVENT_TABLE:
        if d > as_of:
            continue
        window_end = bday_add(d, 20)
        known = window_end <= as_of

        def impact(v):
            keys = ("trough", "ret_20", "fx_effect", "percentile")
            return dict(zip(keys, v if known else (None,) * 4))

        rows.append({
            "event_id": eid, "date": d, "title": title, "description": desc, "family": fam,
            "sign": sign, "regions": regions.split(";"), "lat": lat, "lon": lon,
            "source_url": url, "known": known, "in_progress": not known, "episode": episode,
            "confounded": conf, "t0": d, "window_end": window_end if known else None,
            "trough_date": trough_date if known else None,
            "today": impact(today), "after": impact(after),
            "exposed": [{"ticker": t, "channel": c, "via": v} for t, c, v in exposed],
        })
    return rows


def build_turbulence(events):
    """Per family: clean episodes only count (n, worst, mean, evidence); mixed ones are listed."""
    out = {}
    for fam in FAMILIES:
        episodes = {}
        for e in events:
            if e["family"] != fam or not e["known"]:
                continue
            ep = episodes.setdefault(e["episode"], {
                "episode": e["episode"], "event_ids": [], "trough_today": 0.0,
                "trough_after": 0.0, "confounded": e["confounded"]})
            ep["event_ids"].append(e["event_id"])
            if e["sign"] == "negative":
                ep["trough_today"] = min(ep["trough_today"], e["today"]["trough"])
                ep["trough_after"] = min(ep["trough_after"], e["after"]["trough"])
        eps = list(episodes.values())
        clean = [x for x in eps if not x["confounded"]]
        n = len(clean)
        out[fam] = {
            "n": n,
            "worst_today": min((x["trough_today"] for x in clean), default=None),
            "worst_after": min((x["trough_after"] for x in clean), default=None),
            "mean_after": round(sum(x["trough_after"] for x in clean) / n, 4) if n else None,
            "evidence": "Measured" if n >= 3 else "Indicative" if n >= 1 else "Can't say",
            "episodes": eps,
        }
    return out


def last_weekday(y, m):
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def month_dates():
    """61 dates: the start, the last weekday of Dec 2021..Oct 2026, the end (monthly, spec 12)."""
    dates = [START.isoformat()]
    for k in range(59):
        dates.append(last_weekday(2021 + (11 + k) // 12, (11 + k) % 12 + 1))
    return dates + [END.isoformat()]


# month index -> value (index 0 = 2021-11-12, 1 = 2021-12, ... 59 = 2026-10, 60 = 2026-11-12)
ANCHORS = {
    "today": {0: 100, 1: 100.5, 2: 97, 3: 96, 4: 97.5, 5: 92, 6: 92.5, 7: 90, 8: 93, 9: 91,
              10: 89.9, 11: 91, 12: 94, 13: 93, 14: 96, 24: 104, 38: 122, 41: 121, 52: 140,
              60: 151.6},
    "after": {0: 100, 1: 101.5, 2: 91, 3: 88, 4: 90, 5: 80, 6: 79, 7: 72, 8: 77, 9: 73,
              10: 66.6, 11: 70, 12: 75, 13: 73, 14: 80, 18: 100, 24: 130, 28: 165, 30: 180,
              36: 230, 38: 262, 41: 217.7, 45: 250, 52: 285, 60: 307},
    "aligned": {0: 100, 1: 100.3, 2: 97, 3: 95.5, 4: 97, 5: 91.5, 6: 91, 7: 88.5, 8: 92, 9: 90,
                10: 87.4, 11: 89, 12: 92, 24: 99, 38: 115, 41: 114, 52: 130, 60: 140.9},
}


def build_series(as_of):
    dates = [d for d in month_dates() if d <= as_of]
    idx = np.arange(len(dates))
    out = {"dates": dates}
    for name, pts in ANCHORS.items():
        xs = sorted(pts)
        out[name] = [round(float(v), 2) for v in
                     np.interp(idx, xs, [pts[x] for x in xs])]
    return out


def days_between(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def metrics_row(cagr, vol, dd, peak, trough, recovery, sharpe, as_of):
    return {"cagr": cagr, "volatility": vol, "max_drawdown": dd, "peak_date": peak,
            "trough_date": trough, "recovery_days": recovery,
            "days_since_trough": days_between(trough, as_of), "sharpe": sharpe,
            "source": "FAKE: data/fake/make_fake.py", "as_of": as_of}


def build_metrics(as_of):
    return {
        "today": metrics_row(0.087, 0.062, -0.106, "2022-01-04", "2022-10-14", 416, 0.84, as_of),
        "after": metrics_row(0.252, 0.268, -0.345, "2021-11-29", "2022-10-14", 241, 0.81, as_of),
        "aligned": metrics_row(0.071, 0.075, -0.129, "2022-01-04", "2022-10-14", 380, 0.48,
                               as_of),
    }


PROFILE = {"goal": "preservation", "horizon_years": 4, "risk": "moderate", "esg": False,
           "crypto": False, "capacity": 90000, "reaction_2022": "held"}
# Robert: band floor -25 % (held in 2022 -> moderate); capacity $90,000 of $600,000 = -15 % binds.
LIMITS = {"floor": -0.15, "floor_source": "capacity", "single_stock": 0.10, "sector": 0.35,
          "crypto": 0.0, "scenario_stress": -0.075, "recovery_days": 487, "risk_share": 0.5}
CHECK_ORDER = ["max_drawdown", "scenario_stress", "single_stock", "sector", "risk_concentration",
               "recovery", "short_horizon", "crypto", "missing_data"]


def pct(x, digits=1):
    return f"{abs(x) * 100:.{digits}f} %"


def usd(x):
    return f"${abs(x):,.0f}"


def check(rule, tier, status, value, limit, holding, reason):
    return {"rule": rule, "tier": tier, "status": status, "value": value, "limit": limit,
            "holding": holding, "reason": reason}


def build_checks(after):
    """The section 5 checklist for Robert; fails by the same holding count once (NVDA)."""
    if not after:
        return [
            check("max_drawdown", "hard", "pass", -0.106, -0.15, None,
                  f"In this history the mix's worst drop was {pct(-0.106)} ({usd(0.106 * AMOUNT)}), "
                  f"inside the {pct(-0.15, 0)} ({usd(90000)}) you said you could absorb."),
            check("scenario_stress", "soft", "pass", -0.06, -0.075, None,
                  f"The worst clean tariff-storm episode cost {pct(-0.06)}, inside half your "
                  f"floor ({pct(-0.075)})."),
            check("single_stock", "soft", "pass", 0.034, 0.10, "RY.TO",
                  f"The largest single company, RY.TO, is {pct(0.034)} of the money, inside the "
                  f"{pct(0.10, 0)} limit."),
            check("sector", "soft", "pass", 0.149, 0.35, None,
                  f"The largest sector, Financials, is {pct(0.149)} of the money, inside the "
                  f"{pct(0.35, 0)} limit."),
            check("crypto", "soft", "pass", 0.0, 0.0, None, "No crypto is held; the limit is 0 %."),
            check("risk_concentration", "warn", "pass", 0.47, 0.5, None,
                  f"The largest line carries {pct(0.47, 0)} of the risk, inside the "
                  f"{pct(0.5, 0)} warning level."),
            check("recovery", "warn", "pass", 416, 487, None,
                  "The worst drop took 416 days to recover, inside the 487 days your horizon "
                  "allows."),
            check("short_horizon", "warn", "pass", 4, 3, None,
                  "You need the money in 4 years, beyond the 3-year short-horizon level."),
            check("missing_data", "warn", "pass", 0, 0, None,
                  "Every held asset has a complete price history."),
        ]
    return [
        check("max_drawdown", "hard", "fail", -0.345, -0.15, None,
              f"In this history the mix fell {pct(-0.345)} ({usd(0.345 * AMOUNT)}) from "
              f"2021-11-29 to 2022-10-14, beyond the {pct(-0.15, 0)} ({usd(90000)}) you said "
              "you could absorb."),
        check("scenario_stress", "soft", "fail", -0.09, -0.075, None,
              f"The worst clean tariff-storm episode cost {pct(-0.09)} ({usd(0.09 * AMOUNT)}), "
              f"beyond half your floor ({pct(-0.075)})."),
        check("single_stock", "soft", "fail", 0.40, 0.10, "NVDA",
              f"NVDA is {pct(0.40)} of the money, beyond the {pct(0.10, 0)} limit for one "
              "company."),
        check("sector", "soft", "fail", 0.426, 0.35, "NVDA",
              f"Information Technology is {pct(0.426)} of the money, beyond the "
              f"{pct(0.35, 0)} limit (same cause as NVDA)."),
        check("crypto", "soft", "pass", 0.0, 0.0, None, "No crypto is held; the limit is 0 %."),
        check("risk_concentration", "warn", "warn", 0.86, 0.5, "NVDA",
              f"NVDA carries {pct(0.86, 0)} of the risk, beyond the {pct(0.5, 0)} warning level."),
        check("recovery", "warn", "pass", 241, 487, None,
              "The worst drop took 241 days to recover, inside the 487 days your horizon "
              "allows."),
        check("short_horizon", "warn", "pass", 4, 3, None,
              "You need the money in 4 years, beyond the 3-year short-horizon level."),
        check("missing_data", "warn", "pass", 0, 0, None,
              "Every held asset has a complete price history."),
    ]


KPIS_TODAY = {
    "max_drawdown": {"value": -0.106, "limit": -0.15},
    "scenario_stress": {"value": -0.06, "limit": -0.075},
    "recovery_days": {"value": 416, "limit": 487},
    "exposure_canada": {"value": 0.90, "limit": None},
}
KPIS_AFTER = {
    "max_drawdown": {"value": -0.345, "limit": -0.15},
    "scenario_stress": {"value": -0.09, "limit": -0.075},
    "recovery_days": {"value": 241, "limit": 487},
    "exposure_canada": {"value": 0.54, "limit": None},
}
# Risk share (spec 10): shares of the portfolio's risk, bets = 1 / sum(RC^2).
RISK = {
    "today": {"shares": {"XIU.TO": 0.47, "XBB.TO": 0.30, "GLD": 0.18, "ZST.TO": 0.05}, "bets": 2.9},
    "after": {"shares": {"NVDA": 0.86, "XIU.TO": 0.07, "XBB.TO": 0.03, "GLD": 0.03,
                         "ZST.TO": 0.01}, "bets": 1.3},
}
DIVERSIFICATION = {
    "today": {"countries": {"CAN": 0.90, "GLOBAL": 0.10},
              "currencies": {"CAD": 0.90, "USD": 0.10, "OTHER": 0.0},
              "sectors": {"Financials": 0.149, "Energy": 0.075, "Industrials": 0.052,
                          "Materials": 0.045, "Information Technology": 0.043},
              "can_risk_share": 0.82},
    "after": {"countries": {"CAN": 0.54, "USA": 0.40, "GLOBAL": 0.06},
              "currencies": {"CAD": 0.54, "USD": 0.46, "OTHER": 0.0},
              "sectors": {"Information Technology": 0.426, "Financials": 0.089, "Energy": 0.045,
                          "Industrials": 0.031, "Materials": 0.027},
              "can_risk_share": 0.11},
}


def build_lookthrough(after, as_of):
    xiu = 0.27 if after else 0.45
    stocks = {"RY.TO": 0.075, "ENB.TO": 0.036, "CNQ.TO": 0.035}   # shares of XIU.TO (FAKE)
    out = {t: {"direct": 0.0, "via": [{"etf": "XIU.TO", "weight": round(xiu * w, 3)}],
               "total": round(xiu * w, 3)} for t, w in stocks.items()}
    if after:
        out = {"NVDA": {"direct": 0.40, "via": [], "total": 0.40}, **out}
    div = DIVERSIFICATION["after" if after else "today"]
    return {"stocks": out, "sectors": div["sectors"], "countries": div["countries"],
            "esg_indirect": {}, "coverage": {"XIU.TO": 0.77}, "snapshot": {"XIU.TO": "2026-11-12"},
            "mode": "lookthrough", "source": "FAKE: data/fake/make_fake.py", "as_of": as_of}


def curve_point(w, tm=False):
    """One size-curve point for NVDA at weight w (FAKE formulas, shaped like spec 10:
    the floor breaks between 8 % and 9 %; 8 % lands exactly on -15 % after 0.1 pp rounding)."""
    dd = round(float(np.interp(w, [0, 0.08, 0.09, 0.40], [-0.106, -0.15004, -0.156, -0.345])), 4)
    # time machine: one known tariff episode, so the stress check only warns and never fails
    shock = round(-0.010 - 0.0225 * w if tm else -0.06 - 0.075 * w, 4)
    fails = (round(dd, 3) < -0.15) + (w > 0.10 + 1e-9) + (not tm and round(shock, 3) < -0.075)
    return {"weight": round(w, 2), "verdict": "Compatible" if fails == 0 else "Incompatible",
            "fails": int(fails), "max_drawdown": dd, "scenario_shock": shock}


def build_tipping_point(tm=False):
    curve = [curve_point(i / 100, tm) for i in range(41)]
    ok = [p["weight"] for p in curve if p["fails"] == 0]
    return {"ticker": "NVDA", "max_weight": max(ok) if ok else None, "curve": curve,
            "still_failing": None}


def build_variations(tm=False):
    shocks = (-0.011, -0.014, -0.015) if tm else (-0.066, -0.081, -0.083)
    return [
        {"label": "NVDA at 8 %, the threshold size in this history",
         "change": {"op": "set", "ticker": "NVDA", "weight": 0.08, "from_ticker": None},
         "verdict": "Compatible", "binding_rule": None, "max_drawdown": -0.15,
         "scenario_shock": shocks[0]},
        {"label": "40 % in QQQ instead (NVDA is 6.5 % of QQQ)",
         "change": {"op": "set", "ticker": "QQQ", "weight": 0.40, "from_ticker": None},
         "verdict": "Incompatible", "binding_rule": "max_drawdown", "max_drawdown": -0.241,
         "scenario_shock": shocks[1]},
        {"label": "NVDA 40 %, funded entirely from XIU.TO",
         "change": {"op": "set", "ticker": "NVDA", "weight": 0.40, "from_ticker": "XIU.TO"},
         "verdict": "Incompatible", "binding_rule": "max_drawdown", "max_drawdown": -0.301,
         "scenario_shock": shocks[2]},
    ]


SENSITIVITY = {
    "floor_flip": -0.345,
    "sentence": "Outside your limits until your floor is -34.5 % or lower; at that floor the "
                "verdict would be Inside, with caveats, because NVDA would still be beyond the "
                "10 % single-company limit.",
}
ATTRIBUTION = {   # share of the max-drawdown stretch's log loss / days inside each family's windows
    "shares": {"rates": 0.46, "war_oil": 0.12, "chips": 0.09, "tariffs": 0.0},
    "days_share": {"rates": 0.23, "war_oil": 0.08, "chips": 0.03, "tariffs": 0.0},
    "peak_date": "2021-11-29", "trough_date": "2022-10-14",
}
COMPARE = [
    {"pilot": "robert", "name": "Robert", "verdict": "Incompatible", "binding_rule": "max_drawdown",
     "reason": "The mix fell 34.5 % in 2022, beyond the 15 % floor set by his capacity "
               "($90,000 of $600,000)."},
    {"pilot": "mateo", "name": "Mateo", "verdict": "Incompatible", "binding_rule": "max_drawdown",
     "reason": "The mix fell 34.5 % in 2022, beyond the 25 % floor of a moderate investor."},
    {"pilot": "amira", "name": "Amira", "verdict": "Tension", "binding_rule": "single_stock",
     "reason": "NVDA is 40.0 % of the money, beyond her 20 % single-company limit; the 34.5 % "
               "drop is inside her 45 % floor."},
]


def known_ids(as_of):
    return [e[0] for e in EVENT_TABLE if bday_add(e[1], 20) <= as_of]


def build_time_machine(as_of):
    """Month-end table for the sealed envelope picker: the decision then, direct holdings,
    known storms only (FAKE rule: NVDA 40 % -> Tension at least, Outside once the drop is deep)."""
    months = []
    for d in [m for m in month_dates()[1:-1] if m <= as_of]:
        deep = d >= "2022-04-29"
        months.append({"as_of": d, "verdict": "Incompatible" if deep else "Tension",
                       "binding_rule": "max_drawdown" if deep else "single_stock",
                       "known_storms": known_ids(d)})
    return {"months": months}


def tariff_reason(e, share_can):
    if e["sign"] == "positive":
        return "tariffs family, a positive shock: shown apart, never inside a loss range"
    base = (f"tariffs family, {'Canada' if 'CAN' in e['regions'] else 'the US'} in the event's "
            f"regions")
    if "CAN" in e["regions"]:
        base += f" and {share_can} of your money is Canadian"
    if e["confounded"]:
        base += f", mixed with {CONFOUNDED_BY[e['episode']]} (Indicative)"
    return base + ", keyword 'tariff'"


def build_scenario(events):
    tariffs = [e for e in events if e["family"] == "tariffs" and e["known"]]
    return {
        "type": "change", "families": ["tariffs"],
        "event_ids": [e["event_id"] for e in tariffs],
        "reasons": {e["event_id"]: tariff_reason(e, "90 %") for e in tariffs},
        "rejected": {"war_oil": "no region overlap with your portfolio, score 0.12",
                     "chips": "the question names no chip event; NVDA is in the move, score 0.31",
                     "rates": "the question names no rate event, score 0.18"},
        "tool_calls": [
            {"tool": "search_events",
             "input": {"query": "tariff war flares up again", "family": "tariffs",
                       "regions": ["USA", "CAN"]},
             "output_summary": f"{len(tariffs)} known tariff events ranked by code, top score 0.91",
             "ms": 38},
            {"tool": "propose_change",
             "input": {"op": "set", "ticker": "NVDA", "weight": 0.4, "from_ticker": None},
             "output_summary": "NVDA 40 %, other lines x 0.6, weights sum to 1", "ms": 4},
            {"tool": "get_exposure", "input": {},
             "output_summary": "Today: 90 % Canada, 10 % global (gold), 90 % CAD", "ms": 21},
        ],
        "method": "bedrock", "intent": "more AI exposure", "check_order": CHECK_ORDER,
        "clarify": None, "widened": None,
        "weather": {"headline": "the tariff war flares up again", "families": ["tariffs"],
                    "regions": ["USA", "CAN"], "no_precedent": False},
    }


def fact(label, value, unit, entity, sign, kind):
    return {"label": label, "value": value, "unit": unit, "entity": entity, "sign": sign,
            "kind": kind}


# value = fraction for "%" rows (x100 on display), whole dollars for "$", whole days for "days"
FACTS = {
    "T1": fact("Worst drop, mix after the move", -0.345, "%", "portfolio after", "negative", "fact"),
    "T2": fact("Worst drop in dollars, mix after the move", 207000, "$", "portfolio after",
               "negative", "fact"),
    "T3": fact("Your floor (set by capacity)", -0.15, "%", "your floor", "negative", "assumption"),
    "T4": fact("What you said you could absorb", 90000, "$", "your capacity", "none", "assumption"),
    "T5": fact("Worst drop, today's mix", -0.106, "%", "portfolio today", "negative", "fact"),
    "T6": fact("Worst tariff-storm episode, mix after the move", -0.09, "%", "tariffs family",
               "negative", "fact"),
    "T7": fact("Worst tariff-storm episode, today's mix", -0.06, "%", "tariffs family",
               "negative", "fact"),
    "T8": fact("Single-storm limit (half your floor)", -0.075, "%", "tariffs family", "negative",
               "assumption"),
    "T9": fact("NVDA share of the money after the move", 0.40, "%", "NVDA", "none", "fact"),
    "T10": fact("NVDA share of the risk after the move", 0.86, "%", "NVDA", "none", "fact"),
    "T11": fact("Largest NVDA size inside your limits in this history", 0.08, "%", "NVDA", "none",
                "scenario"),
    "T12": fact("Share of the 2022 loss inside rate-shock windows", 0.46, "%", "rates family",
                "none", "fact"),
    "T13": fact("Annual growth, mix after the move", 0.252, "%", "portfolio after", "positive",
                "fact"),
    "T14": fact("Annual growth, today's mix", 0.087, "%", "portfolio today", "positive", "fact"),
}
# id -> (step, tool, inputs, outputs, ms) for the 14 rows that hold a fact (Python tools)
FACT_ROWS = {
    "T1": ("COMPARE", "tools.metrics.risk_metrics", {"weights": "after"},
           {"max_drawdown": -0.345, "peak_date": "2021-11-29", "trough_date": "2022-10-14"}, 41),
    "T2": ("COMPARE", "pipeline.dollars", {"amount": AMOUNT, "value": -0.345},
           {"loss_dollars": 207000}, 1),
    "T3": ("OBSERVE", "governance.load_limits", {"capacity": 90000, "reaction_2022": "held"},
           {"floor": -0.15, "floor_source": "capacity", "band_floor": -0.25}, 3),
    "T4": ("OBSERVE", "flight_plan", {"capacity": 90000}, {"capacity": 90000}, 0),
    "T5": ("COMPARE", "tools.metrics.risk_metrics", {"weights": "today"},
           {"max_drawdown": -0.106, "peak_date": "2022-01-04", "trough_date": "2022-10-14"}, 38),
    "T6": ("COMPARE", "tools.events.turbulence", {"weights": "after", "families": ["tariffs"]},
           {"tariffs": {"n": 4, "worst": -0.09, "evidence": "Measured"}}, 112),
    "T7": ("COMPARE", "tools.events.turbulence", {"weights": "today", "families": ["tariffs"]},
           {"tariffs": {"n": 4, "worst": -0.06, "evidence": "Measured"}}, 109),
    "T8": ("OBSERVE", "governance.load_limits", {"floor": -0.15},
           {"scenario_stress": -0.075}, 1),
    "T9": ("OBSERVE", "tools.lookthrough.look_through", {"weights": "after"},
           {"NVDA": {"direct": 0.40, "via": [], "total": 0.40}}, 27),
    "T10": ("COMPARE", "tools.risk.risk_contributions", {"weights": "after"},
            {"shares": {"NVDA": 0.86}, "bets": 1.3}, 64),
    "T11": ("COMPARE", "tools.allocation.tipping_point", {"ticker": "NVDA", "max_weight": 0.40},
            {"max_weight": 0.08, "still_failing": None}, 905),
    "T12": ("COMPARE", "tools.events.drawdown_attribution", {"peak": "2021-11-29"},
            {"shares": {"rates": 0.46}, "days_share": {"rates": 0.23}}, 33),
    "T13": ("COMPARE", "tools.metrics.risk_metrics", {"weights": "after"}, {"cagr": 0.252}, 40),
    "T14": ("COMPARE", "tools.metrics.risk_metrics", {"weights": "today"}, {"cagr": 0.087}, 37),
}
MODEL = "us.anthropic.claude-sonnet-5-5"


def trace_row(tid, step, tool, inputs, outputs, ms, as_of, service="Python", model=None,
              usage=None, request_id=None):
    return {"id": tid, "step": step, "tool": tool, "inputs": inputs, "outputs": outputs,
            "source": "FAKE: data/fake/make_fake.py", "as_of": as_of, "ms": ms,
            "service": service, "model": model, "usage": usage, "request_id": request_id}


def build_trace(as_of):
    """Execution order. Ids T1-T14 are the fact rows (the receipt's id space); T15+ the steps."""
    f = lambda tid: trace_row(tid, *FACT_ROWS[tid][:2], *FACT_ROWS[tid][2:4], FACT_ROWS[tid][4],
                              as_of)
    guard = dict(service="Amazon Bedrock Guardrails")
    bedrock = dict(service="Amazon Bedrock", model=MODEL)
    return [
        trace_row("T15", "OBSERVE", "guardrail.apply_guardrail(INPUT)", {"text": "<question>"},
                  {"action": "NONE", "blocked": False}, 212, as_of,
                  usage={"textUnits": 1}, request_id="FAKE-GR-0001", **guard),
        f("T3"), f("T4"), f("T8"), f("T9"),
        trace_row("T16", "UNDERSTAND", "agents.scenario.run_scenario", {"question": "<question>"},
                  {"type": "change", "families": ["tariffs"], "method": "bedrock"}, 2310, as_of,
                  usage={"inputTokens": 1840, "outputTokens": 212, "cacheReadInputTokens": 1500},
                  request_id="FAKE-BR-0001", **bedrock),
        trace_row("T17", "UNDERSTAND", "search_events", {"family": "tariffs"},
                  {"ranked": 7, "top_score": 0.91}, 38, as_of),
        trace_row("T18", "UNDERSTAND", "propose_change",
                  {"op": "set", "ticker": "NVDA", "weight": 0.4}, {"sum": 1.0}, 4, as_of),
        trace_row("T19", "UNDERSTAND", "get_exposure", {}, {"CAN": 0.90, "GLOBAL": 0.10}, 21,
                  as_of),
        f("T5"), f("T14"), f("T1"), f("T2"), f("T13"), f("T7"), f("T6"), f("T10"), f("T12"),
        f("T11"),
        trace_row("T20", "COMPARE", "governance.evaluate", {"weights": "after"},
                  {"verdict": "Incompatible", "fails": 3}, 57, as_of),
        trace_row("T21", "EXPLAIN", "agents.explainer.explain", {"facts": 14, "verdict": "Outside"},
                  {"sentences": 10, "stop_reason": "end_turn"}, 3120, as_of,
                  usage={"inputTokens": 2210, "outputTokens": 318, "cacheReadInputTokens": 1900},
                  request_id="FAKE-BR-0002", **bedrock),
        trace_row("T22", "VERIFY", "verify.verify_numbers", {"sentences": 11},
                  {"verified": 14, "total": 14, "defects": []}, 6, as_of),
        trace_row("T23", "VERIFY", "guardrail.apply_guardrail(OUTPUT)",
                  {"grounding_source": "<facts JSON>"},
                  {"action": "NONE", "grounding": 0.93, "relevance": 0.88}, 348, as_of,
                  usage={"textUnits": 2}, request_id="FAKE-GR-0002", **guard),
    ]


def build_debrief(tm):
    """The four questions as sections; `sections` hold indexes into `sentences`, each sentence has
    a kind and its [T#] refs (spec 7). Numbers traced by the receipt: 14 (main) or 14 (time machine)."""
    s3 = ("The worst tariff storm cost 1.9 % after the move and 1.0 % today [T6][T7]." if tm
          else "The worst tariff storm cost 9.0 % after the move and 6.0 % today [T6][T7].")
    sentences = [
        ("From 2021-11-29 to 2022-10-14 the mix after the move lost $207,000, or 34.5 % [T1][T2].",
         "fact", ["T1", "T2"]),
        ("Today's mix fell at most 10.6 % [T5].", "fact", ["T5"]),
        ("NVDA would be 40 % of the money and 86 % of the risk [T9][T10].", "fact", ["T9", "T10"]),
        (s3, "fact", ["T6", "T7"]),
        ("Your floor is 15 % because you said you could absorb $90,000 [T3][T4].", "assumption",
         ["T3", "T4"]),
        ("Half of it, 7.5 %, limits any single storm [T8].", "assumption", ["T8"]),
        ("Rate-shock windows account for 46 % of the 2022 loss, a correlation, not a cause [T12].",
         "fact", ["T12"]),
        ("This replays what already happened in a single regime; it is not a forecast.", "limit",
         []),
        ("In this history NVDA at 8 % stays inside your limits [T11].", "scenario", ["T11"]),
        ("A different floor would change the verdict.", "assumption", []),
    ]
    if tm:
        sentences.insert(8, ("Only one tariff storm is known on 2025-01-31, too few to conclude.",
                             "limit", []))
    sections = {"data": [0, 1, 2, 3], "why": [4, 5], "limits": [6, 7],
                "would_change": [9, 10] if tm else [8, 9]}
    if tm:
        sections["limits"] = [6, 7, 8]
    return {
        "verdict_sentence": "Outside your limits: the mix after the move fell 34.5 % [T1], "
                            "beyond the 15 % floor you set [T3].",
        "sections": sections,
        "sentences": [{"text": t, "kind": k, "refs": r} for t, k, r in sentences],
    }


def build_receipt(tm):
    s3 = ("1.9 %", "T6"), ("1.0 %", "T7")
    if not tm:
        s3 = ("9.0 %", "T6"), ("6.0 %", "T7")
    nums = [("verdict", "34.5 %", "T1"), ("verdict", "15 %", "T3"),
            (0, "$207,000", "T2"), (0, "34.5 %", "T1"), (1, "10.6 %", "T5"),
            (2, "40 %", "T9"), (2, "86 %", "T10"), (3, *s3[0]), (3, *s3[1]),
            (4, "15 %", "T3"), (4, "$90,000", "T4"), (5, "7.5 %", "T8"), (6, "46 %", "T12"),
            (9 if tm else 8, "8 %", "T11")]
    # the time-machine variant inserts one limit sentence, so later sentence indexes shift by one
    return {"verified": len(nums), "total": len(nums), "unverified": [], "wrong_entity": [],
            "missing": [], "future_refs": [], "defects": [],
            "matches": [{"sentence": s, "number": n, "ref": r} for s, n, r in nums]}


def build_guardrail():
    base = {"action": "NONE", "blocked": False, "topic_hit": False, "prompt_attack": False,
            "pii_hit": False, "grounding": None, "relevance": None, "automated_reasoning": None,
            "message": None, "error": None}
    return {
        "input": {**base, "latency_ms": 212, "usage": {"textUnits": 1}},
        "output": {**base, "latency_ms": 348, "usage": {"textUnits": 2},
                   "grounding": {"score": 0.93, "threshold": 0.7, "detected": False},
                   "relevance": {"score": 0.88, "threshold": 0.7, "detected": False}},
        "automated_reasoning": None,
    }


def build_figures():
    """Empty placeholders: ui/charts.py (Task 9+) fills these with fig.to_plotly_json()."""
    keys = ["flight_paths", "storm_map", "turbulence", "risk_share", "diversification",
            "size_curve"]
    return {k: {"data": [], "layout": {}} for k in keys}


def build_realized():
    """Sealed envelope, opened: the 12 months after 2025-01-31 for the mix with 40 % NVDA
    (FAKE; the spec previews are -15.9 % high-to-low and -11.3 % from the decision date)."""
    dates = ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-08", "2025-04-30", "2025-05-30",
             "2025-06-30", "2025-07-31", "2025-08-29", "2025-09-30", "2025-10-31", "2025-11-28",
             "2025-12-31", "2026-01-30"]
    values = [100.0, 105.5, 96.4, 88.7, 94.0, 101.5, 106.0, 109.0, 112.5, 114.0, 112.0, 116.0,
              118.5, 119.0]
    followed = [e for e in build_events(DATASET_END)
                if TM_AS_OF < e["date"] <= "2026-01-30" and e["family"] in ("tariffs", "chips")]
    return {
        "max_drawdown_after": -0.159, "drop_from_decision": -0.113, "date": "2025-04-08",
        "limit": -0.15,
        "events": [{"event_id": e["event_id"], "date": e["date"], "title": e["title"]}
                   for e in followed],
        "series": {"dates": dates, "values": values},
    }


def cagr_from(series, key):
    days = days_between(series["dates"][0], series["dates"][-1])
    return round((series[key][-1] / 100.0) ** (365.25 / days) - 1, 3)


def tm_stress_check(after):
    """Time machine: one tariff storm is known on 2025-01-31, so the stress check only warns."""
    value = -0.019 if after else -0.010
    return check("scenario_stress", "soft", "warn", value, -0.075, None,
                 f"Only 1 tariff storm is known on 2025-01-31 ({pct(value)}): too few storms to "
                 "conclude.")


def swap_stress(checks, after):
    return [tm_stress_check(after) if c["rule"] == "scenario_stress" else c for c in checks]


# FAKE deep history (ledger 17): peak month, trough month, then (depth, months to recover) today and after the move.
# Every number is invented for the UI (None = not regained by 2021-10); the 11 episodes themselves come from data/deep_episodes.csv.
DEEP_FAKE_SOURCE = "FAKE: invented numbers for UI development, not tool output (the real fragment is a proxy replay, monthly, CAD)"
DEEP_FAKE = {
    "oil_embargo_1973": ("1973-05", "1974-09", (-0.155, 9), (-0.34, None)),
    "volcker_1979": ("1980-11", "1982-06", (-0.165, 5), (-0.18, 12)),
    "crash_1987": ("1987-08", "1987-11", (-0.105, 13), (-0.12, 20)),
    "gulf_war_1990": ("1990-06", "1990-10", (-0.04, 3), (-0.06, 5)),
    "bond_rout_1994": ("1994-01", "1994-06", (-0.08, 8), (-0.10, 10)),
    "russia_ltcm_1998": ("1998-04", "1998-08", (-0.12, 8), (-0.14, 12)),
    "dotcom_2000": ("2000-08", "2001-09", (-0.11, 24), (-0.52, 120)),
    "gfc_2008": ("2008-05", "2009-02", (-0.17, 12), (-0.45, 44)),
    "euro_2011": ("2011-05", "2011-09", (-0.035, 4), (-0.05, 6)),
    "taper_2013": ("2013-04", "2013-06", (-0.045, 4), (-0.07, 5)),
    "covid_2020": ("2020-01", "2020-03", (-0.09, 4), (-0.16, 8)),
}


def build_deep_history(tm):
    """The FAKE `deep_history` fragment. Its shape, counts and sentence are written by tools.deep itself (`_summary`,
    `deep_sentence`, `_money`, `_round_pp`), so the fake cannot drift from the real fragment."""
    if str(HERE.parents[1]) not in sys.path:
        sys.path.insert(0, str(HERE.parents[1]))
    from tools import deep
    as_of = TM_AS_OF if tm else DATASET_END
    n_months, last = (38, "2025-01") if tm else (49, "2025-12")

    def replay(k, eid, side):
        peak, trough = DEEP_FAKE[eid][:2]
        depth, months = DEEP_FAKE[eid][2 + side]
        peak_value = round(100.0 + 3 * k, 4)
        return {"episode_id": eid, "replayable": True, "uncovered": [], "depth": depth, "peak": peak, "trough": trough,
                "peak_value": peak_value, "trough_value": round(peak_value * (1 + depth), 4),
                "loss_dollars": deep._money(AMOUNT, depth), "recovery_months": months,
                "beyond_floor": bool(deep._round_pp(depth) < deep._round_pp(LIMITS["floor"])),
                "source": DEEP_FAKE_SOURCE, "as_of": as_of}

    def check(strength, direction, corr, te, real, proxy):
        return {"strength": strength, "direction": direction, "n_months": n_months,
                "window": {"start": "2021-12", "end": last}, "corr": corr, "te_ann": te, "drawdown_real": real,
                "drawdown_proxy": proxy, "drawdown_gap": round(proxy - real, 4), "uncovered": [],
                "source": DEEP_FAKE_SOURCE, "as_of": as_of}

    rows = [{"episode_id": e["episode_id"], "title": e["title_en"], "start": e["start"], "end": e["end"],
             "kind": e["kind"], "family": e["family"], "place": e["place"], "lat": e["lat"], "lon": e["lon"],
             "source_url": e["source_url"], "today": replay(k, e["episode_id"], 0), "after": replay(k, e["episode_id"], 1)}
            for k, e in enumerate(deep.load_episodes())]
    fragment = {"frequency": "monthly", "window": {"start": deep.DEEP_START, "end": deep.DEEP_END},
                "proxy": {"today": check("strong", None, 0.97, 0.02, -0.094, -0.088),
                          "after": check("weak", "gentler", 0.86, 0.13, -0.32, -0.16)},
                "episodes": rows, "summary": {side: deep._summary(rows, side) for side in ("today", "after")},
                "sentence": "", "source": DEEP_FAKE_SOURCE, "as_of": as_of}
    fragment["sentence"] = deep.deep_sentence(fragment, LIMITS["floor"])
    return fragment


def build_result(tm):
    as_of = TM_AS_OF if tm else DATASET_END
    events = build_events(as_of)
    series = build_series(as_of)
    metrics = build_metrics(as_of)
    kpis_today, kpis_after = json.loads(json.dumps([KPIS_TODAY, KPIS_AFTER]))   # deep copies
    checks_today, checks_after = build_checks(False), build_checks(True)
    facts = json.loads(json.dumps(FACTS))
    trace = build_trace(as_of)
    lookthrough = {"today": build_lookthrough(False, as_of), "after": build_lookthrough(True, as_of)}
    if tm:
        for key in ("today", "after"):
            metrics[key]["cagr"] = cagr_from(series, key)
        kpis_today["scenario_stress"]["value"], kpis_after["scenario_stress"]["value"] = -0.010, -0.019
        checks_today, checks_after = swap_stress(checks_today, False), swap_stress(checks_after, True)
        facts["T6"].update(label="Worst tariff storm known on 2025-01-31, mix after the move",
                           value=-0.019)
        facts["T7"].update(label="Worst tariff storm known on 2025-01-31, today's mix", value=-0.010)
        facts["T13"]["value"], facts["T14"]["value"] = metrics["after"]["cagr"], metrics["today"]["cagr"]
        for row in trace:
            if row["id"] in ("T6", "T7"):
                worst = -0.019 if row["id"] == "T6" else -0.010
                row["outputs"] = {"tariffs": {"n": 1, "worst": worst, "evidence": "Indicative"}}
            if row["id"] in ("T13", "T14"):
                row["outputs"] = {"cagr": facts[row["id"]]["value"]}
        for key in ("today", "after"):   # past dates use direct holdings only (spec 9)
            lt = lookthrough[key]
            lt["mode"] = "direct"
            lt["stocks"] = {t: v for t, v in lt["stocks"].items() if v["direct"] > 0}
            lt["coverage"], lt["snapshot"] = {}, {}
    return {
        "_note": NOTE,
        "run_id": "fake-robert-tm-001" if tm else "fake-robert-001",
        "as_of": as_of, "mode": "demo_replay", "status": "ok",
        "message": f"Sealed envelope: this decision uses only what was known on {TM_AS_OF}."
                   if tm else None,
        "question": QUESTION, "question_type": "change", "pilot": "robert", "amount": AMOUNT,
        "profile": PROFILE, "limits": LIMITS, "portfolio": AFTER_W,
        "baseline": {"portfolio": TODAY_W, "verdict": "Compatible", "checks": checks_today,
                     "metrics": metrics["today"], "kpis": kpis_today},
        "aligned": {"weights": ALIGNED_W, "label": "Fictional illustration, not a recommendation"},
        "scenario": build_scenario(events), "events": events,
        "turbulence": build_turbulence(events), "series": series, "metrics": metrics,
        "worst_rolling": {
            "today": {"value": -0.106, "peak_date": "2022-01-04", "trough_date": "2022-10-14"},
            "after": {"value": -0.345, "peak_date": "2021-11-29", "trough_date": "2022-10-14"}},
        "kpis": kpis_after, "risk": RISK, "diversification": DIVERSIFICATION,
        "lookthrough": lookthrough, "checks": checks_after, "verdict": "Incompatible",
        "tipping_point": build_tipping_point(tm), "variations": build_variations(tm),
        "sensitivity": SENSITIVITY, "attribution": ATTRIBUTION, "compare": COMPARE,
        "price_of_values": None, "time_machine": build_time_machine(as_of), "deep_history": build_deep_history(tm),
        "facts": facts,
        "debrief": build_debrief(tm), "receipt": build_receipt(tm), "redteam": None,
        "guardrail": build_guardrail(), "trace": trace, "figures": build_figures(),
        "realized": build_realized() if tm else None,
    }


def write_results():
    for tm, name in ((False, "result.json"), (True, "result_time_machine.json")):
        (HERE / name).write_text(json.dumps(build_result(tm), indent=1) + "\n")


def main():
    write_starter()
    write_results()
    print(f"FAKE data written under {HERE} (starter/*.csv, result.json, result_time_machine.json)")


if __name__ == "__main__":
    main()
