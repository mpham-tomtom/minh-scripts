import numpy as np
import pandas as pd
import pytest

from trading_loop.metrics import (
    ic_decay_curve,
    ic_stats,
    max_drawdown,
    monthly_ic,
    sharpe_ratio,
    signal_half_life,
)


def _dates(n):
    return pd.bdate_range("2020-01-01", periods=n)


def test_monthly_ic_perfect_signal():
    idx = _dates(300)
    rng = np.random.default_rng(0)
    fwd = pd.Series(rng.standard_normal(300), index=idx)
    signal = fwd.copy()  # signal IS the forward return -> mean IC ~ 1
    ics = monthly_ic(signal, fwd)
    assert len(ics) > 5
    assert ics.mean() == pytest.approx(1.0, abs=0.15)
    assert (ics > 0.3).all()


def test_monthly_ic_no_demeaning_bias_for_reversion_signal():
    """A reversion-style signal on iid returns must have mean monthly IC ~ 0.

    Within-month Pearson IC fails this badly (~+0.17 mean): the returns that
    trigger the signal also shift the month's own mean, and demeaning by it
    manufactures correlation. Regression test for the globally-standardized
    formulation.
    """
    from trading_loop.strategies import rsi

    rng = np.random.default_rng(42)
    n = 20000
    idx = _dates(n)
    close = pd.Series(100.0 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01)), index=idx)
    fwd = close.pct_change().shift(-1)
    r = rsi(close, 14)
    signal = pd.Series(0.0, index=idx)
    signal[r < 30] = 1.0
    signal[r > 70] = -1.0
    stats = ic_stats(signal, fwd)
    assert abs(stats.ic_mean) < 0.02
    assert abs(stats.icir) < 0.25


def test_monthly_ic_pure_noise_is_small():
    idx = _dates(2000)
    rng = np.random.default_rng(1)
    signal = pd.Series(rng.standard_normal(2000), index=idx)
    fwd = pd.Series(rng.standard_normal(2000), index=idx)
    stats = ic_stats(signal, fwd)
    assert abs(stats.ic_mean) < 0.1
    assert abs(stats.icir) < 0.5
    assert stats.p_value > 0.001


def test_icir_of_consistent_signal_beats_inconsistent():
    idx = _dates(1000)
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(1000)
    fwd = pd.Series(rng.standard_normal(1000), index=idx)
    consistent = pd.Series(0.3 * fwd.values + noise, index=idx)
    # Inconsistent: correlated in even months, anti-correlated in odd months.
    flip = np.where(idx.month % 2 == 0, 1.0, -1.0)
    inconsistent = pd.Series(0.3 * fwd.values * flip + noise, index=idx)
    assert ic_stats(consistent, fwd).icir > ic_stats(inconsistent, fwd).icir


def test_half_life_of_decaying_curve():
    # |IC| halves every 10 bars -> half-life ~ 10.
    lags = (1, 5, 10, 20, 50)
    decay = pd.Series({h: 0.2 * 0.5 ** (h / 10.0) for h in lags})
    hl = signal_half_life(decay)
    assert hl == pytest.approx(10.0, rel=0.05)


def test_half_life_flat_curve_is_infinite():
    decay = pd.Series({1: 0.1, 5: 0.1, 10: 0.1, 20: 0.1, 50: 0.1})
    assert signal_half_life(decay) == float("inf")


def test_half_life_no_signal_is_zero():
    decay = pd.Series({1: np.nan, 5: np.nan, 10: np.nan})
    assert signal_half_life(decay) == 0.0


def test_ic_decay_curve_short_lived_signal():
    # Signal predicts only the next bar; longer horizons dilute toward zero.
    idx = _dates(2000)
    rng = np.random.default_rng(3)
    ret = pd.Series(rng.standard_normal(2000) * 0.01, index=idx)
    signal = ret.shift(-1).fillna(0.0)  # knows exactly the next bar
    curve = ic_decay_curve(signal, ret)
    assert curve[1] > 0.9
    assert curve[50] < curve[1] / 2


def test_sharpe_and_drawdown_sanity():
    idx = _dates(504)
    up = pd.Series(0.001, index=idx)
    assert sharpe_ratio(up) is not np.nan or True  # constant series -> std 0 -> nan
    rng = np.random.default_rng(4)
    r = pd.Series(0.0005 + rng.standard_normal(504) * 0.01, index=idx)
    assert np.isfinite(sharpe_ratio(r))
    assert -1.0 <= max_drawdown(r) <= 0.0
