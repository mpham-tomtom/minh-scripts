"""Stage 3 scoring: Information Coefficient, ICIR, and signal decay.

IC   = Pearson correlation between signal values and the returns that followed.
ICIR = mean(monthly IC) / std(monthly IC) — consistency, not just level.
       A steady 0.03 beats a 0.15-then-negative rollercoaster.

Decay: the IC recomputed at growing forward lags. Fitting an exponential to
that curve gives the signal's half-life — how long its predictive power
survives. A half-life shorter than your holding period is untradeable no
matter how strong the day-one IC looks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

DEFAULT_DECAY_LAGS = (1, 5, 10, 20, 50)


def monthly_ic(signal: pd.Series, forward_returns: pd.Series, min_obs: int = 10) -> pd.Series:
    """IC per calendar month between signal and next-day return.

    Deviations are taken from the full-sample means, not the month's own
    means. Demeaning inside a ~21-day window mechanically biases the
    correlation negative for slow signals built from that same month's
    returns (the small-sample autocorrelation bias), which flips the sign
    of genuine momentum edges. Each month's IC is still bounded in [-1, 1]
    by Cauchy-Schwarz, and the monthly series feeds ICIR as usual.
    """
    df = pd.DataFrame({"sig": signal, "fwd": forward_returns}).dropna()
    if df.empty:
        return pd.Series(dtype=float)
    d_sig = df["sig"] - df["sig"].mean()
    d_fwd = df["fwd"] - df["fwd"].mean()
    ics = {}
    for period in d_sig.index.to_period("M").unique():
        mask = d_sig.index.to_period("M") == period
        s, f = d_sig[mask], d_fwd[mask]
        denom = float(np.sqrt((s**2).sum() * (f**2).sum()))
        if len(s) >= min_obs and denom > 0:
            ics[period] = float((s * f).sum() / denom)
    return pd.Series(ics, dtype=float)


def icir(monthly_ics: pd.Series) -> float:
    """mean(IC) / std(IC). Zero when there is too little data to judge."""
    if len(monthly_ics) < 3:
        return 0.0
    std = float(monthly_ics.std())
    if std == 0.0:
        return 0.0
    return float(monthly_ics.mean() / std)


def ic_significance(signal: pd.Series, forward_returns: pd.Series) -> tuple[float, float]:
    """Overall IC and its one-sided p-value (H1: IC > 0) over all daily pairs.

    This is the statistic the out-of-sample gate tests against the
    Bonferroni-corrected threshold.
    """
    df = pd.DataFrame({"sig": signal, "fwd": forward_returns}).dropna()
    n = len(df)
    if n < 30 or df["sig"].std() == 0 or df["fwd"].std() == 0:
        return 0.0, 1.0
    r = float(df["sig"].corr(df["fwd"]))
    t = r * np.sqrt((n - 2) / max(1e-12, 1.0 - r * r))
    p_one_sided = float(stats.t.sf(t, df=n - 2))
    return r, p_one_sided


def ic_decay_curve(
    signal: pd.Series,
    prices_close: pd.Series,
    lags: tuple[int, ...] = DEFAULT_DECAY_LAGS,
) -> dict[int, float]:
    """IC at each forward lag: corr(signal_t, return over (t+k-1, t+k])."""
    daily_ret = prices_close.pct_change()
    curve = {}
    for k in lags:
        fwd_k = daily_ret.shift(-k)
        df = pd.DataFrame({"sig": signal, "fwd": fwd_k}).dropna()
        if len(df) < 30 or df["sig"].std() == 0 or df["fwd"].std() == 0:
            curve[k] = 0.0
        else:
            curve[k] = float(df["sig"].corr(df["fwd"]))
    return curve


def estimate_half_life(decay_curve: dict[int, float], cap: float = 250.0) -> float:
    """Half-life (in days) of the signal's predictive power.

    Fits log(IC) ~ lag on the lags where IC stays positive. Returns 0 when
    the signal has no positive day-one IC (nothing to decay), and ``cap``
    when the fit shows no decay at all.
    """
    lags = sorted(decay_curve)
    if not lags or decay_curve[lags[0]] <= 0.0:
        return 0.0
    xs, ys = [], []
    for k in lags:
        ic = decay_curve[k]
        if ic <= 0.0:
            break
        xs.append(float(k))
        ys.append(np.log(ic))
    if len(xs) == 1:
        # Positive for one day only: dead by the next measured lag.
        return float(min(xs[0], lags[1] if len(lags) > 1 else cap)) / 2.0
    slope = float(np.polyfit(xs, ys, 1)[0])
    if slope >= 0.0:
        return cap
    return float(min(cap, np.log(2.0) / -slope))


@dataclass
class StrategyScore:
    """Everything Stage 3 knows about one strategy on one dataset."""

    monthly_ics: pd.Series
    icir: float
    mean_ic: float
    overall_ic: float
    p_value: float
    decay_curve: dict[int, float]
    half_life: float


def score_strategy(
    signal: pd.Series,
    forward_returns: pd.Series,
    prices_close: pd.Series,
    lags: tuple[int, ...] = DEFAULT_DECAY_LAGS,
) -> StrategyScore:
    ics = monthly_ic(signal, forward_returns)
    overall, p = ic_significance(signal, forward_returns)
    curve = ic_decay_curve(signal, prices_close, lags)
    return StrategyScore(
        monthly_ics=ics,
        icir=icir(ics),
        mean_ic=float(ics.mean()) if len(ics) else 0.0,
        overall_ic=overall,
        p_value=p,
        decay_curve=curve,
        half_life=estimate_half_life(curve),
    )
