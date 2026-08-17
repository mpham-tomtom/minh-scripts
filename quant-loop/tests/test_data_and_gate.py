import numpy as np
import pandas as pd
import pytest

from quant_loop.data import OutOfSampleLeakError, ResearchData, generate_synthetic_prices
from quant_loop.gate import run_gate
from quant_loop.loop import HARD_MAX_ROUNDS, LoopConfig, run_loop


def test_split_is_chronological_and_sized():
    prices = generate_synthetic_prices(n_days=1000, seed=1)
    data = ResearchData(prices, holdout_fraction=0.25)
    ins = data.in_sample
    assert len(ins) == 750
    assert ins.index.max() < data.split_date


def test_out_of_sample_releases_exactly_once():
    data = ResearchData(generate_synthetic_prices(n_days=1000, seed=1))
    oos = data.release_out_of_sample()
    assert len(oos) > 0
    with pytest.raises(OutOfSampleLeakError):
        data.release_out_of_sample()


def test_round_cap_is_enforced():
    with pytest.raises(ValueError):
        LoopConfig(rounds=HARD_MAX_ROUNDS + 1)


def test_loop_never_touches_out_of_sample():
    data = ResearchData(generate_synthetic_prices(n_days=1500, seed=2))
    config = LoopConfig(rounds=1, candidates_per_round=4, seed=0)
    run_loop(data.in_sample, config)
    assert not data.out_of_sample_released


def test_loop_kills_below_thresholds():
    data = ResearchData(generate_synthetic_prices(n_days=2500, seed=3))
    config = LoopConfig(rounds=2, candidates_per_round=8, seed=0)
    result = run_loop(data.in_sample, config)
    for cand in result.survivors:
        assert cand.score.icir >= config.icir_min
        assert cand.score.half_life >= config.half_life_min_days
    assert result.total_strategies_tested >= 8


def test_bonferroni_threshold_scales_with_total_tested():
    data = ResearchData(generate_synthetic_prices(n_days=2500, seed=4))
    config = LoopConfig(rounds=2, candidates_per_round=10, seed=1)
    result = run_loop(data.in_sample, config)
    gate = run_gate(result, data, config, alpha=0.05)
    assert gate.bonferroni_threshold == pytest.approx(0.05 / result.total_strategies_tested)
    for v in gate.verdicts:
        assert v.passed == (
            v.icir_holds and v.decay_holds and v.significant_after_correction
        )


def test_gate_rejects_pure_noise_strategies():
    # Pure random walk: nothing real to find, so nothing should pass the gate.
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("2012-01-02", periods=3000)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, size=3000)))
    data = ResearchData(pd.DataFrame({"close": close}, index=idx))
    config = LoopConfig(rounds=3, candidates_per_round=12, seed=2)
    result = run_loop(data.in_sample, config)
    gate = run_gate(result, data, config)
    assert gate.viable == []
