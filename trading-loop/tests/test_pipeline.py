import numpy as np
import pandas as pd
import pytest

from trading_loop.backtest import run_backtest
from trading_loop.data import DataSplit, make_synthetic_prices, split_data
from trading_loop.gate import run_gate
from trading_loop.loop import run_loop
from trading_loop.strategies import GenerationFeedback, generate_strategies


def test_split_holds_out_recent_data():
    prices = make_synthetic_prices(n_days=1000)
    split = split_data(prices, holdout_frac=0.25)
    assert len(split.out_of_sample) == 250
    assert split.in_sample.index.max() < split.out_of_sample.index.min()


def test_split_rejects_overlap():
    prices = make_synthetic_prices(n_days=100)
    with pytest.raises(ValueError, match="overlap"):
        DataSplit(in_sample=prices.iloc[:60], out_of_sample=prices.iloc[50:])


def test_generation_honors_feedback():
    fb = GenerationFeedback(dropped_families={"momentum", "ma_cross"}, require_vol_filter=True)
    strategies = generate_strategies(2, fb)
    assert strategies
    assert all(s.family not in {"momentum", "ma_cross"} for s in strategies)
    assert all(s.params["vol_filtered"] for s in strategies)


def test_backtest_signal_is_lagged():
    """A signal that 'knows' today's return must NOT earn today's return."""
    prices = make_synthetic_prices(n_days=600, seed=11)
    from trading_loop.strategies import Strategy

    cheat = Strategy(
        name="cheat",
        family="cheat",
        params={},
        signal_fn=lambda p: np.sign(p["close"].pct_change()).fillna(0.0),
    )
    result = run_backtest(cheat, prices, cost_per_turnover=0.0)
    # If lookahead existed, every bar would be a win and sharpe would be huge.
    assert result.sharpe < 5.0


def test_loop_rejects_too_many_rounds():
    prices = make_synthetic_prices(n_days=800)
    with pytest.raises(ValueError, match="rounds"):
        run_loop(prices, rounds=6)


def test_gate_requires_honest_total_count():
    prices = make_synthetic_prices(n_days=1200)
    split = split_data(prices)
    loop_result = run_loop(split.in_sample, rounds=1, verbose=False)
    if loop_result.survivors:
        with pytest.raises(ValueError, match="total_strategies_tested"):
            run_gate(
                loop_result.survivors,
                split.out_of_sample,
                total_strategies_tested=len(loop_result.survivors) - 1,
            )


def test_end_to_end_on_synthetic_data():
    """The full workflow runs, counts every attempt, and gate output is sane."""
    prices = make_synthetic_prices(n_days=2500, seed=7)
    split = split_data(prices, holdout_frac=0.25)
    loop_result = run_loop(split.in_sample, rounds=2, verbose=False)

    tested_per_round = [len(r.tested) for r in loop_result.rounds]
    assert loop_result.total_strategies_tested == sum(tested_per_round)

    gate_results = run_gate(
        loop_result.survivors,
        split.out_of_sample,
        total_strategies_tested=loop_result.total_strategies_tested,
    )
    assert len(gate_results) == len(loop_result.survivors)
    for g in gate_results:
        assert g.bonferroni_threshold == pytest.approx(
            0.05 / loop_result.total_strategies_tested
        )
        # passed implies all three sub-checks
        if g.passed:
            assert g.icir_holds and g.decay_holds and g.significant


def test_planted_edge_passes_gate():
    """The default synthetic data has a persistent planted drift; the loop
    must find it and at least one strategy must pass the full gate."""
    prices = make_synthetic_prices()
    split = split_data(prices, holdout_frac=0.25)
    loop_result = run_loop(split.in_sample, rounds=3, verbose=False)
    assert loop_result.survivors, "loop found nothing on data with a real edge"
    gate_results = run_gate(
        loop_result.survivors,
        split.out_of_sample,
        total_strategies_tested=loop_result.total_strategies_tested,
    )
    passed = [g for g in gate_results if g.passed]
    assert passed, "no strategy passed the gate despite a real planted edge"
    # The short-lived reversion edge must NOT be among the passers: its
    # ~1-bar half-life makes it untradeable per the decay rule.
    assert all("reversion" not in g.name and "reversal" not in g.name for g in passed)


def test_gate_kills_noise_strategies():
    """On pure random-walk data nothing should pass the gate."""
    rng = np.random.default_rng(42)
    n = 2500
    idx = pd.bdate_range("2016-01-04", periods=n)
    close = 100.0 * np.exp(np.cumsum(rng.standard_normal(n) * 0.01))
    prices = pd.DataFrame({"close": close}, index=idx)
    split = split_data(prices, holdout_frac=0.25)
    loop_result = run_loop(split.in_sample, rounds=2, verbose=False)
    gate_results = run_gate(
        loop_result.survivors,
        split.out_of_sample,
        total_strategies_tested=loop_result.total_strategies_tested,
    )
    assert not any(g.passed for g in gate_results)
