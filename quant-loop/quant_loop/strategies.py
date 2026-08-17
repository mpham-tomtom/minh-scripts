"""Strategy families and candidate generation (Stage 1 of the loop).

Every strategy is a parameterized signal generator: prices in, a continuous
signal series out. Continuous signals (rather than binary entries) are what
make the Information Coefficient meaningful — IC is the correlation between
signal strength and the return that follows.

Signals are z-scored over a trailing window and clipped to [-3, 3], so a
signal value doubles directly as a position size in the backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

_ZSCORE_WINDOW = 250
_CLIP = 3.0


def _standardize(raw: pd.Series) -> pd.Series:
    # Scale-only standardization: dividing by rolling std puts every family's
    # signal on a comparable footing without subtracting the rolling mean —
    # demeaning a slow signal over a trailing window would subtract away the
    # very trend level the signal is trying to carry.
    std = raw.rolling(_ZSCORE_WINDOW, min_periods=60).std()
    z = raw / std.replace(0.0, np.nan)
    return z.clip(-_CLIP, _CLIP)


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, min_periods=period).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, min_periods=period).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def signal_ma_momentum(prices: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    """Trend following: long when the fast MA sits above the slow MA."""
    close = prices["close"]
    raw = close.rolling(fast).mean() / close.rolling(slow).mean() - 1.0
    return _standardize(raw)


def signal_rsi_reversion(prices: pd.DataFrame, period: int) -> pd.Series:
    """Mean reversion: fade overbought/oversold RSI readings."""
    raw = (50.0 - _rsi(prices["close"], period)) / 50.0
    return _standardize(raw)


def signal_zscore_reversion(prices: pd.DataFrame, lookback: int) -> pd.Series:
    """Mean reversion: fade the price's z-score against its rolling mean."""
    close = prices["close"]
    mean = close.rolling(lookback).mean()
    std = close.rolling(lookback).std()
    raw = -(close - mean) / std.replace(0.0, np.nan)
    return _standardize(raw)


def signal_breakout(prices: pd.DataFrame, lookback: int) -> pd.Series:
    """Momentum: distance of today's close from the prior N-day high/low range."""
    close = prices["close"]
    high = close.rolling(lookback).max().shift(1)
    low = close.rolling(lookback).min().shift(1)
    width = (high - low).replace(0.0, np.nan)
    raw = (2.0 * close - high - low) / width
    return _standardize(raw)


def signal_vol_filtered_momentum(
    prices: pd.DataFrame, lookback: int, vol_lookback: int
) -> pd.Series:
    """Momentum, scaled down when realized volatility is elevated."""
    close = prices["close"]
    mom = close.pct_change(lookback)
    vol = close.pct_change().rolling(vol_lookback).std()
    med_vol = vol.rolling(_ZSCORE_WINDOW, min_periods=60).median()
    damp = (med_vol / vol.replace(0.0, np.nan)).clip(upper=1.5)
    return _standardize(mom * damp)


@dataclass(frozen=True)
class Strategy:
    """A named, fully-parameterized signal generator."""

    name: str
    family: str
    params: dict = field(hash=False)
    _fn: Callable[..., pd.Series] = field(repr=False, hash=False)

    def signal(self, prices: pd.DataFrame) -> pd.Series:
        return self._fn(prices, **self.params)

    def neighbors(self, rng: np.random.Generator, n: int = 4) -> list["Strategy"]:
        """Nearby parameterizations, used by the robustness check.

        A real edge works across a range of reasonable parameters, not one
        magic number — so each candidate is also scored at jittered params.
        """
        out = []
        for i in range(n):
            jittered = {}
            for key, value in self.params.items():
                bump = max(1, int(round(abs(value) * 0.2)))
                jittered[key] = max(2, int(value + rng.integers(-bump, bump + 1)))
            if "fast" in jittered and "slow" in jittered:
                jittered["slow"] = max(jittered["slow"], jittered["fast"] + 2)
            out.append(
                Strategy(
                    name=f"{self.name}~nb{i}",
                    family=self.family,
                    params=jittered,
                    _fn=self._fn,
                )
            )
        return out


_FAMILY_SPECS = {
    "ma_momentum": (
        signal_ma_momentum,
        {"fast": (5, 40), "slow": (30, 150)},
    ),
    "rsi_reversion": (
        signal_rsi_reversion,
        {"period": (5, 30)},
    ),
    "zscore_reversion": (
        signal_zscore_reversion,
        {"lookback": (5, 60)},
    ),
    "breakout": (
        signal_breakout,
        {"lookback": (10, 100)},
    ),
    "vol_filtered_momentum": (
        signal_vol_filtered_momentum,
        {"lookback": (10, 80), "vol_lookback": (10, 40)},
    ),
}


def generate_candidates(
    n: int,
    round_num: int,
    rng: np.random.Generator,
    banned_families: set[str] | None = None,
    seed_params: dict[str, list[dict]] | None = None,
) -> list[Strategy]:
    """Stage 1: propose ``n`` candidate strategies for this round.

    Round 1 samples parameters uniformly across every family. Later rounds
    apply the feedback from Stage 4: families whose members all failed are
    banned, and surviving parameterizations seed jittered variations so the
    pool concentrates around what actually worked.
    """
    banned = banned_families or set()
    seeds = seed_params or {}
    families = [f for f in _FAMILY_SPECS if f not in banned]
    if not families:
        return []

    candidates: list[Strategy] = []
    seen: set[tuple] = set()
    attempts = 0
    while len(candidates) < n and attempts < n * 30:
        attempts += 1
        family = families[int(rng.integers(len(families)))]
        fn, ranges = _FAMILY_SPECS[family]
        family_seeds = seeds.get(family, [])
        if family_seeds and rng.random() < 0.6:
            base = dict(family_seeds[int(rng.integers(len(family_seeds)))])
            params = {}
            for key, value in base.items():
                lo, hi = ranges[key]
                bump = max(1, int(round((hi - lo) * 0.1)))
                params[key] = int(np.clip(value + rng.integers(-bump, bump + 1), lo, hi))
        else:
            params = {key: int(rng.integers(lo, hi + 1)) for key, (lo, hi) in ranges.items()}
        if "fast" in params and "slow" in params and params["slow"] <= params["fast"] + 2:
            params["slow"] = params["fast"] + 10
        key = (family, tuple(sorted(params.items())))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            Strategy(
                name=f"r{round_num}_{family}_{len(candidates):02d}",
                family=family,
                params=params,
                _fn=fn,
            )
        )
    return candidates
