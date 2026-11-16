"""Independent recompute core (no repo imports). Follows docs/finance_methods.md sections 2-3.

Market tables: adj_close in listing currency, CNQ.TO x1.021 before 2022-08-22, union TSX+US calendar,
ffill <= 3 days, USD/CAD carried forward (never back-filled), USD lines x USD/CAD -> CAD.
Portfolio: constant weights rebalanced daily, base 100, a day counts when one held asset's exchange traded.
"""
from __future__ import annotations
import os, sys  # noqa: E401
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this folder only (the scripts run with -I)
from paths import DEEP, OUT, REPO, RUNS  # noqa: E402,F401

import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd

# REPO comes from paths.py
STARTER = REPO / "data/starter"
AS_OF = pd.Timestamp("2026-11-12")


def load_raw():
    px = pd.read_csv(STARTER / "prices_daily.csv", parse_dates=["date"])
    px = px[px["date"] <= AS_OF]
    fx = pd.read_csv(STARTER / "fx_usdcad_daily.csv", parse_dates=["date"])
    fx = fx[fx["date"] <= AS_OF]
    uni = pd.read_csv(STARTER / "assets_universe.csv")
    return px, fx, uni


class Market:
    def __init__(self, cnq_fix: bool = True, fill_limit: int = 3):
        px, fx, uni = load_raw()
        self.uni = uni.set_index("ticker")
        self.currency = self.uni["currency"].to_dict()
        self.market = self.uni["market"].to_dict()
        adj = px.pivot(index="date", columns="ticker", values="adj_close").sort_index()
        close = px.pivot(index="date", columns="ticker", values="close").sort_index()
        if cnq_fix:
            m = adj.index < pd.Timestamp("2022-08-22")
            adj.loc[m, "CNQ.TO"] = adj.loc[m, "CNQ.TO"] * 1.021
        self.adj_raw = adj  # listing currency, own rows only (NaN elsewhere)
        self.close_raw = close
        # exchange calendars from the price file
        tsx = [t for t in adj.columns if t.endswith(".TO")]
        us = [t for t in adj.columns if not t.endswith(".TO") and not t.endswith("-USD")]
        self.tsx_days = adj[tsx].dropna(how="all").index
        self.us_days = adj[us].dropna(how="all").index
        self.days = self.tsx_days.union(self.us_days)  # union calendar
        # listing-currency prices on the union calendar, ffill at most fill_limit days
        allp = adj.reindex(adj.index.union(self.days))
        # fill on the union calendar only (crypto sampled on union days: its own row on that date)
        self.local = adj.reindex(self.days).ffill(limit=fill_limit)
        fxs = fx.set_index("date")["usdcad"].dropna().sort_index()
        self.fx_raw = fxs
        # carried forward, never back-filled
        self.usdcad = fxs.reindex(fxs.index.union(self.days)).ffill().reindex(self.days)
        cad = self.local.copy()
        for t in cad.columns:
            if self.currency.get(t) == "USD":
                cad[t] = cad[t] * self.usdcad
        self.cad = cad

    def exchange_days(self, t):
        if t.endswith(".TO"):
            return self.tsx_days
        if t.endswith("-USD"):
            return None  # crypto never adds a day
        return self.us_days

    def counted_days(self, tickers, start=None):
        sets = [self.exchange_days(t) for t in tickers]
        sets = [s for s in sets if s is not None]
        if not sets:
            d = self.days
        else:
            d = sets[0]
            for s in sets[1:]:
                d = d.union(s)
        d = d[(d <= AS_OF)]
        if start is not None:
            d = d[d >= pd.Timestamp(start)]
        return d

    def series(self, w: dict, start=None, prices=None):
        """Base-100 path, constant weights rebalanced daily on the counted days."""
        prices = self.cad if prices is None else prices
        tick = [t for t, x in w.items() if x != 0]
        days = self.counted_days(tick, start)
        p = prices[tick].reindex(days)
        r = p.pct_change().iloc[1:]
        if r.isna().any().any():
            bad = r.columns[r.isna().any()].tolist()
            raise ValueError(f"missing returns in {bad}")
        pr = (r * pd.Series({t: w[t] for t in tick})).sum(axis=1)
        v = 100 * (1 + pr).cumprod()
        v = pd.concat([pd.Series([100.0], index=[days[0]]), v])
        return v, r


def apply_set(w: dict, ticker: str, x: float) -> dict:
    old = w.get(ticker, 0.0)
    k = (1 - x) / (1 - old)
    out = {t: v * k for t, v in w.items() if t != ticker}
    out[ticker] = x
    return out


def apply_add(w: dict, ticker: str, x: float) -> dict:
    return apply_set(w, ticker, w.get(ticker, 0.0) + x)


def drawdown(v: pd.Series):
    hi = v.cummax()
    dd = v / hi - 1
    tdate = dd.idxmin()
    depth = dd.min()
    pdate = v.loc[:tdate].idxmax()
    # recovery: first date after trough with v >= peak value
    after = v.loc[tdate:]
    rec = after[after >= v.loc[pdate]]
    rdate = rec.index[0] if len(rec) else None
    return depth, pdate, tdate, rdate


def cagr(v: pd.Series):
    years = (v.index[-1] - v.index[0]).days / 365.25
    return (v.iloc[-1] / v.iloc[0]) ** (1 / years) - 1


def round_pp(x: float) -> float:
    """Round a fraction to 0.1 pp, ROUND_HALF_UP (ties away from zero)."""
    d = Decimal(repr(float(x) * 100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(d) / 100


def risk_contrib(r: pd.DataFrame, w: dict):
    tick = list(r.columns)
    wv = np.array([w[t] for t in tick])
    S = np.cov(r.values.T, ddof=1)
    Sw = S @ wv
    tot = wv @ Sw
    rc = wv * Sw / tot
    # Meucci effective number of bets over principal components
    lam, E = np.linalg.eigh(S)
    y = E.T @ wv
    p = (y ** 2) * lam / tot
    p = p[p > 0]
    enb = float(np.exp(-(p * np.log(p)).sum()))
    return dict(zip(tick, rc)), enb


def fmt(x, nd=1):
    return f"{x * 100:.{nd}f} %"
