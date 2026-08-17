"""Scoring metrics: IC, ICIR, signal decay / half-life, and supporting stats.

IC (Information Coefficient): Pearson correlation between the signal value
and the return that follows it. Computed per month, because a single IC
reading over the whole sample hides inconsistency.

ICIR: mean(monthly IC) / std(monthly IC). Consistency matters more than any
single hot month.

Half-life: how many bars it takes the signal's predictive power to fall to
half its 1-bar strength, estimated from the decay of IC across horizons.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_LAGS = (1, 5, 10, 20, 50)


@dataclass(frozen=True)
class ICStats:
    monthly_ic: pd.Series
    ic_mean: float
    ic_std: float
    icir: float
    # Two-sided p-value that the mean monthly IC is zero (t-test).
    p_value: float


def monthly_ic(signal: pd.Series, forward_returns: pd.Series) -> pd.Series:
    """Monthly IC: mean of globally-standardized signal x forward-return products.

    Deliberately NOT a within-month Pearson correlation. Pearson demeans by
    the month's own sample means, and for signals derived from recent returns
    that demeaning is contaminated: a mean-reversion signal fires after
    negative returns, those same returns drag the month's mean return down,
    and the "correlation" becomes mechanically positive even on iid noise
    (empirically ~ +0.17 mean monthly IC for RSI reversion on a pure random
    walk). Standardizing both series over the full evaluated sample and
    averaging the products per month is mean-zero under the null and still
    estimates the true correlation when the signal is real.

    Months with fewer than 10 paired observations are skipped.
    """
    df = pd.DataFrame({"signal": signal, "fwd": forward_returns}).dropna()
    if len(df) < 30 or df["signal"].std(ddof=1) == 0 or df["fwd"].std(ddof=1) == 0:
        return pd.Series(dtype=float)
    z_s = (df["signal"] - df["signal"].mean()) / df["signal"].std(ddof=1)
    z_f = (df["fwd"] - df["fwd"].mean()) / df["fwd"].std(ddof=1)
    prod = z_s * z_f
    grouped = prod.groupby(pd.Grouper(freq="ME"))
    ics = grouped.mean()[grouped.count() >= 10]
    return ics.dropna()


def ic_stats(signal: pd.Series, forward_returns: pd.Series) -> ICStats:
    ics = monthly_ic(signal, forward_returns)
    if len(ics) < 3:
        return ICStats(ics, np.nan, np.nan, np.nan, np.nan)
    mean = float(ics.mean())
    std = float(ics.std(ddof=1))
    icir = mean / std if std > 0 else np.nan
    t_res = stats.ttest_1samp(ics.values, 0.0)
    return ICStats(ics, mean, std, icir, float(t_res.pvalue))


def ic_decay_curve(
    signal: pd.Series, returns: pd.Series, lags: tuple[int, ...] = DEFAULT_LAGS
) -> pd.Series:
    """|IC| of the signal against returns h bars ahead, for each horizon h.

    Uses the cumulative return from t+1 to t+h so the curve answers "how much
    predictive power is left if I act h bars late".
    """
    out = {}
    log_ret = np.log1p(returns)
    for lag in lags:
        fwd = log_ret.rolling(lag).sum().shift(-lag)
        df = pd.DataFrame({"s": signal, "f": fwd}).dropna()
        if len(df) < 30 or df["s"].nunique() < 2:
            out[lag] = np.nan
        else:
            out[lag] = abs(float(df["s"].corr(df["f"])))
    return pd.Series(out, name="abs_ic")


def signal_half_life(decay: pd.Series, noise_floor: float = 0.0) -> float:
    """Estimate the half-life (in bars) from a decay curve of |IC| by horizon.

    Fits |IC(h)| ~ IC0 * exp(-h / tau) by regressing log|IC| on the horizon;
    half-life = tau * ln(2). Returns inf when the curve doesn't decay
    (predictive power holds across all measured horizons), and 0.0 when
    there is no measurable IC at any horizon.

    noise_floor: |IC| values at or below this are treated as zero. Pass
    ~2/sqrt(n_observations) so a flat curve of statistically-invisible ICs
    reads as "no signal" (half-life 0) instead of "eternal signal" (inf).
    """
    d = decay.dropna()
    d = d[d > max(noise_floor, 1e-6)]
    if len(d) == 0:
        return 0.0
    if len(d) < 3:
        # Not enough points to fit; conservative fallback to shortest horizon.
        return float(d.index.min())
    x = np.asarray(d.index, dtype=float)
    y = np.log(d.values)
    slope, _intercept, _r, _p, _se = stats.linregress(x, y)
    if slope >= 0:
        return float("inf")
    tau = -1.0 / slope
    return float(tau * np.log(2.0))


def sharpe_ratio(strategy_returns: pd.Series, periods_per_year: int = 252) -> float:
    r = strategy_returns.dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return np.nan
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods_per_year))


def max_drawdown(strategy_returns: pd.Series) -> float:
    equity = (1.0 + strategy_returns.fillna(0.0)).cumprod()
    peak = equity.cummax()
    return float((equity / peak - 1.0).min())
