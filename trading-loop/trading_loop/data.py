"""Data loading, synthetic data generation, and the in/out-of-sample split.

The split happens ONCE, before the loop starts. The out-of-sample slice is
the most recent portion of the history and must never be touched until the
final gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DataSplit:
    """In-sample data for the loop, out-of-sample data locked for the gate."""

    in_sample: pd.DataFrame
    out_of_sample: pd.DataFrame

    def __post_init__(self) -> None:
        overlap = self.in_sample.index.intersection(self.out_of_sample.index)
        if len(overlap) > 0:
            raise ValueError(
                f"in-sample and out-of-sample overlap on {len(overlap)} rows; "
                "the gate is compromised"
            )
        if len(self.in_sample) and len(self.out_of_sample):
            if self.in_sample.index.max() >= self.out_of_sample.index.min():
                raise ValueError(
                    "out-of-sample data must be strictly after in-sample data"
                )


def split_data(prices: pd.DataFrame, holdout_frac: float = 0.25) -> DataSplit:
    """Hold back the most recent `holdout_frac` of rows as the out-of-sample set.

    The guide recommends 20-30%; default is 25%.
    """
    if not 0.05 <= holdout_frac <= 0.5:
        raise ValueError("holdout_frac should be between 0.05 and 0.5")
    prices = prices.sort_index()
    cut = int(round(len(prices) * (1.0 - holdout_frac)))
    return DataSplit(in_sample=prices.iloc[:cut], out_of_sample=prices.iloc[cut:])


def load_csv(path: str, date_column: str = "date") -> pd.DataFrame:
    """Load an OHLCV (or close-only) CSV into a date-indexed frame.

    Requires at least a `close` column. Column names are lower-cased.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if date_column not in df.columns:
        raise ValueError(f"CSV must have a '{date_column}' column")
    df[date_column] = pd.to_datetime(df[date_column])
    df = df.set_index(date_column).sort_index()
    if "close" not in df.columns:
        raise ValueError("CSV must have a 'close' column")
    return df


def make_synthetic_prices(
    n_days: int = 3500,
    seed: int = 7,
    start: str = "2012-01-03",
    mean_reversion_strength: float = 0.10,
    drift_persistence: float = 0.97,
    drift_vol_ratio: float = 0.35,
    vol_regime_length: int = 250,
) -> pd.DataFrame:
    """Generate daily prices with two planted edges of different lifespans.

    1. A slowly-varying drift (AR(1), persistence ~0.97 -> half-life ~20
       bars). Momentum/trend strategies can catch it, and it survives the
       decay check. Deliberately stronger than anything in real markets so
       the demo has a signal that passes the full gate.
    2. A 1-day mean reversion that only operates in the low-vol regime.
       It is real, but its half-life is ~1 bar — the decay check should
       kill it. That kill is part of what the demo demonstrates.

    Everything else is noise for the loop to (correctly) reject.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n_days)

    # Alternating low/high volatility regimes.
    regime = (np.arange(n_days) // vol_regime_length) % 2
    daily_vol = np.where(regime == 0, 0.008, 0.018)

    # Persistent drift: mu_t = phi * mu_{t-1} + eta_t, stationary sd equal
    # to drift_vol_ratio x the average noise sd.
    target_mu_sd = drift_vol_ratio * float(np.mean(daily_vol))
    eta_sd = target_mu_sd * np.sqrt(1.0 - drift_persistence**2)
    mu = np.empty(n_days)
    mu[0] = 0.0
    eta = rng.standard_normal(n_days) * eta_sd
    for t in range(1, n_days):
        mu[t] = drift_persistence * mu[t - 1] + eta[t]

    shocks = rng.standard_normal(n_days) * daily_vol
    returns = np.empty(n_days)
    returns[0] = shocks[0]
    for t in range(1, n_days):
        # Reversion only operates in the low-vol regime, so a naive
        # backtest that ignores regimes will overfit to the wrong thing.
        reversion = -mean_reversion_strength * returns[t - 1] if regime[t] == 0 else 0.0
        returns[t] = mu[t] + reversion + shocks[t]

    close = 100.0 * np.exp(np.cumsum(returns))
    df = pd.DataFrame({"close": close}, index=dates)
    df.index.name = "date"
    df["volume"] = rng.integers(1_000_000, 5_000_000, n_days)
    return df
