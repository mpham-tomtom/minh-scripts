"""Strategy definitions and the round-by-round generator.

A strategy is a named, parameterized signal function: prices in, a
position signal in [-1, 1] out. The generator produces batches of
variants and accepts feedback from the previous round's failure analysis
(families to drop, filters to add) — that feedback channel is what makes
this a loop instead of a one-shot screen.

Parameters are drawn from coarse grids on purpose: a real edge should
work across a range of reasonable parameters, not at one magic number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

SignalFn = Callable[[pd.DataFrame], pd.Series]


@dataclass
class Strategy:
    name: str
    family: str
    params: dict
    signal_fn: SignalFn = field(repr=False)

    def signal(self, prices: pd.DataFrame) -> pd.Series:
        sig = self.signal_fn(prices)
        return sig.clip(-1.0, 1.0)


# --- indicator helpers -----------------------------------------------------

def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def zscore(close: pd.Series, window: int) -> pd.Series:
    mean = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=1)
    return (close - mean) / std.replace(0, np.nan)


def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    return close.pct_change().rolling(window).std(ddof=1)


def low_vol_filter(prices: pd.DataFrame, window: int = 20, lookback: int = 120) -> pd.Series:
    """1.0 when current vol is below its rolling median, else 0.0."""
    vol = realized_vol(prices["close"], window)
    median = vol.rolling(lookback).median()
    return (vol < median).astype(float)


# --- strategy families -----------------------------------------------------

def _rsi_reversion(period: int, low: float, high: float, vol_filtered: bool) -> SignalFn:
    def fn(prices: pd.DataFrame) -> pd.Series:
        r = rsi(prices["close"], period)
        sig = pd.Series(0.0, index=prices.index)
        sig[r < low] = 1.0
        sig[r > high] = -1.0
        if vol_filtered:
            sig = sig * low_vol_filter(prices)
        return sig

    return fn


def _zscore_reversion(window: int, entry: float, vol_filtered: bool) -> SignalFn:
    def fn(prices: pd.DataFrame) -> pd.Series:
        z = zscore(prices["close"], window)
        sig = (-z / entry).clip(-1.0, 1.0)
        sig[z.abs() < 0.5] = 0.0
        if vol_filtered:
            sig = sig * low_vol_filter(prices)
        return sig

    return fn


def _momentum(lookback: int, vol_filtered: bool) -> SignalFn:
    def fn(prices: pd.DataFrame) -> pd.Series:
        mom = prices["close"].pct_change(lookback)
        sig = np.sign(mom).fillna(0.0)
        if vol_filtered:
            sig = sig * low_vol_filter(prices)
        return sig

    return fn


def _ma_cross(fast: int, slow: int, vol_filtered: bool) -> SignalFn:
    def fn(prices: pd.DataFrame) -> pd.Series:
        f = prices["close"].rolling(fast).mean()
        s = prices["close"].rolling(slow).mean()
        sig = np.sign(f - s).fillna(0.0)
        if vol_filtered:
            sig = sig * low_vol_filter(prices)
        return sig

    return fn


def _reversal_1d(vol_filtered: bool) -> SignalFn:
    def fn(prices: pd.DataFrame) -> pd.Series:
        ret = prices["close"].pct_change()
        sig = (-np.sign(ret)).fillna(0.0)
        if vol_filtered:
            sig = sig * low_vol_filter(prices)
        return sig

    return fn


# --- generation ------------------------------------------------------------

# Coarse grids; deliberately no fine-grained parameter sweeps (see module doc).
_GRIDS = {
    "rsi_reversion": [
        {"period": p, "low": lo, "high": 100 - lo}
        for p in (7, 14, 21)
        for lo in (20, 30)
    ],
    "zscore_reversion": [
        {"window": w, "entry": e} for w in (10, 20, 40) for e in (1.5, 2.0)
    ],
    "momentum": [{"lookback": lb} for lb in (20, 60, 120)],
    "ma_cross": [{"fast": f, "slow": s} for f, s in ((10, 50), (20, 100), (50, 200))],
    "reversal_1d": [{}],
}

_BUILDERS: dict[str, Callable[..., SignalFn]] = {
    "rsi_reversion": _rsi_reversion,
    "zscore_reversion": _zscore_reversion,
    "momentum": _momentum,
    "ma_cross": _ma_cross,
    "reversal_1d": _reversal_1d,
}


@dataclass
class GenerationFeedback:
    """Constraints distilled from the previous round's failure analysis."""

    dropped_families: set[str] = field(default_factory=set)
    require_vol_filter: bool = False
    notes: list[str] = field(default_factory=list)


def generate_strategies(
    round_number: int, feedback: GenerationFeedback | None = None
) -> list[Strategy]:
    """Produce this round's batch of candidate strategies.

    Round 1 explores every family without filters. Later rounds honor the
    feedback: killed families stay dead, and if the analysis showed losers
    were concentrated in high-vol regimes, every variant gets a vol filter.
    """
    feedback = feedback or GenerationFeedback()
    strategies: list[Strategy] = []
    vol_options = [True] if feedback.require_vol_filter else (
        [False] if round_number == 1 else [False, True]
    )
    for family, grid in _GRIDS.items():
        if family in feedback.dropped_families:
            continue
        for params in grid:
            for vol_filtered in vol_options:
                full_params = {**params, "vol_filtered": vol_filtered}
                suffix = "_volf" if vol_filtered else ""
                pstr = "_".join(f"{k}{v}" for k, v in params.items())
                name = f"{family}{('_' + pstr) if pstr else ''}{suffix}_r{round_number}"
                strategies.append(
                    Strategy(
                        name=name,
                        family=family,
                        params=full_params,
                        signal_fn=_BUILDERS[family](**full_params),
                    )
                )
    return strategies
