import numpy as np
import pandas as pd
import pytest

from quant_loop.metrics import (
    estimate_half_life,
    ic_significance,
    icir,
    monthly_ic,
)


def _dates(n):
    return pd.bdate_range("2020-01-01", periods=n)


def test_perfect_signal_has_ic_one():
    idx = _dates(300)
    fwd = pd.Series(np.random.default_rng(0).normal(size=300), index=idx)
    ics = monthly_ic(fwd.copy(), fwd)  # signal == the return it predicts
    assert (ics > 0.999).all()


def test_random_signal_has_low_icir():
    rng = np.random.default_rng(1)
    idx = _dates(2500)
    sig = pd.Series(rng.normal(size=2500), index=idx)
    fwd = pd.Series(rng.normal(size=2500), index=idx)
    assert abs(icir(monthly_ic(sig, fwd))) < 0.3


def test_consistent_weak_signal_beats_inconsistent_strong_one():
    rng = np.random.default_rng(2)
    idx = _dates(2500)
    fwd = pd.Series(rng.normal(size=2500), index=idx)
    steady = fwd * 0.10 + pd.Series(rng.normal(size=2500), index=idx)
    months = idx.to_period("M")
    flip = pd.Series([1 if m.month % 2 else -1 for m in months], index=idx)
    flaky = fwd * 0.5 * flip + pd.Series(rng.normal(size=2500), index=idx)
    assert icir(monthly_ic(steady, fwd)) > icir(monthly_ic(flaky, fwd))


def test_ic_significance_detects_real_correlation():
    rng = np.random.default_rng(3)
    idx = _dates(1000)
    fwd = pd.Series(rng.normal(size=1000), index=idx)
    sig = fwd * 0.2 + pd.Series(rng.normal(size=1000), index=idx)
    r, p = ic_significance(sig, fwd)
    assert r > 0.1
    assert p < 1e-4
    _, p_noise = ic_significance(pd.Series(rng.normal(size=1000), index=idx), fwd)
    assert p_noise > 1e-3


def test_half_life_of_exponential_decay():
    # IC halves every 10 days -> half-life ~= 10
    curve = {k: 0.1 * 0.5 ** (k / 10.0) for k in (1, 5, 10, 20, 50)}
    assert estimate_half_life(curve) == pytest.approx(10.0, rel=0.05)


def test_half_life_zero_when_no_positive_ic():
    assert estimate_half_life({1: -0.02, 5: 0.0, 10: 0.01}) == 0.0


def test_half_life_capped_when_no_decay():
    curve = {k: 0.05 for k in (1, 5, 10, 20, 50)}
    assert estimate_half_life(curve) == 250.0
