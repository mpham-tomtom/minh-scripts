"""Data loading, synthetic data generation, and the in-sample/out-of-sample split.

The split is the foundation of the whole framework: the most recent
``holdout_fraction`` of the data is locked away before the loop starts and can
only be released once, by the out-of-sample gate. ``ResearchData`` enforces
this at the object level so a leak is a hard error, not a silent mistake.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class OutOfSampleLeakError(RuntimeError):
    """Raised when code tries to read the held-out data more than once."""


class ResearchData:
    """Price history with an enforced in-sample / out-of-sample split.

    The loop only ever sees ``in_sample``. The held-out tail is released
    exactly once via :meth:`release_out_of_sample`, which the gate calls at
    the very end. A second release attempt raises, so nothing upstream of the
    gate can peek and then let the gate "re-use" supposedly fresh data.
    """

    def __init__(self, prices: pd.DataFrame, holdout_fraction: float = 0.25):
        if not 0.05 <= holdout_fraction <= 0.5:
            raise ValueError("holdout_fraction must be between 0.05 and 0.5")
        if "close" not in prices.columns:
            raise ValueError("prices must have a 'close' column")
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise ValueError("prices must be indexed by a DatetimeIndex")
        prices = prices.sort_index()
        split_at = int(round(len(prices) * (1.0 - holdout_fraction)))
        if split_at < 100 or len(prices) - split_at < 60:
            raise ValueError("not enough data on one side of the split")
        self._in_sample = prices.iloc[:split_at].copy()
        self._out_of_sample = prices.iloc[split_at:].copy()
        self._oos_released = False

    @property
    def in_sample(self) -> pd.DataFrame:
        return self._in_sample.copy()

    @property
    def split_date(self) -> pd.Timestamp:
        return self._out_of_sample.index[0]

    @property
    def out_of_sample_released(self) -> bool:
        return self._oos_released

    def release_out_of_sample(self) -> pd.DataFrame:
        """Hand over the held-out data. Callable exactly once, by the gate."""
        if self._oos_released:
            raise OutOfSampleLeakError(
                "out-of-sample data was already released; it is no longer "
                "fresh and must not be tested against again"
            )
        self._oos_released = True
        return self._out_of_sample.copy()


def load_prices_csv(path: str, date_column: str = "date", close_column: str = "close") -> pd.DataFrame:
    """Load a daily price series from CSV into the frame ResearchData expects."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    if date_column not in df.columns or close_column not in df.columns:
        raise ValueError(f"CSV must contain '{date_column}' and '{close_column}' columns")
    df[date_column] = pd.to_datetime(df[date_column])
    df = df.set_index(date_column).sort_index()
    out = pd.DataFrame({"close": df[close_column].astype(float)})
    return out.dropna()


def generate_synthetic_prices(
    n_days: int = 4000,
    seed: int = 7,
    trend_persistence: float = 0.98,
    trend_vol: float = 0.0009,
    base_vol: float = 0.011,
    start: str = "2010-01-04",
) -> pd.DataFrame:
    """Simulate a daily close series with a weak, slow-moving momentum edge.

    Daily returns are a persistent latent drift (AR(1) with ~35-day
    half-life at the default persistence of 0.98) buried under much larger
    regime-switching noise. Trend-following signals can recover the drift;
    mean-reversion signals have nothing real to find. The edge is
    deliberately faint — day-to-day returns are ~98% noise — because the
    point of the demo is that only a disciplined loop + gate separates a
    real edge like this from luck.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, periods=n_days)

    # Regime-switching volatility: calm vs stressed, sticky regimes.
    vol = np.empty(n_days)
    stressed = False
    for t in range(n_days):
        if rng.random() < (0.02 if not stressed else 0.06):
            stressed = not stressed
        vol[t] = base_vol * (2.5 if stressed else 1.0)

    trend = np.empty(n_days)
    trend[0] = 0.0
    for t in range(1, n_days):
        trend[t] = trend_persistence * trend[t - 1] + rng.normal(0.0, trend_vol)

    rets = 0.0002 + trend + rng.normal(0.0, 1.0, size=n_days) * vol
    close = 100.0 * np.exp(np.cumsum(rets))
    return pd.DataFrame({"close": close}, index=dates)
