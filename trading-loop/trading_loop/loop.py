"""The loop orchestrator: generate -> backtest -> score -> analyze -> select.

Hard rules encoded here, per the framework:
- Runs on in-sample data only; the out-of-sample frame never enters.
- Kill threshold on ICIR (default 0.3) and on half-life (default 5 bars).
- Capped number of rounds (default and maximum 5).
- Every strategy ever tested is counted, so the gate can Bonferroni-correct
  against the true number of attempts.
- Failure analysis is distilled into GenerationFeedback for the next round:
  families where every variant died are dropped; if unfiltered variants
  lose in high-vol months while vol-filtered siblings survive, the next
  round requires the filter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import BacktestResult, run_backtest
from .strategies import GenerationFeedback, generate_strategies

MAX_ROUNDS = 5


@dataclass
class RoundReport:
    round_number: int
    tested: list[BacktestResult]
    survivors: list[BacktestResult]
    feedback: GenerationFeedback


@dataclass
class LoopResult:
    rounds: list[RoundReport]
    survivors: list[BacktestResult]
    total_strategies_tested: int
    kill_log: list[str] = field(default_factory=list)


def _analyze_failures(
    tested: list[BacktestResult],
    survivors: list[BacktestResult],
    prior: GenerationFeedback,
) -> GenerationFeedback:
    """Turn this round's casualties into constraints for the next round."""
    # Constraints (dropped families, required filters) accumulate across
    # rounds; notes are per-round so each report reads cleanly.
    feedback = GenerationFeedback(
        dropped_families=set(prior.dropped_families),
        require_vol_filter=prior.require_vol_filter,
        notes=[],
    )
    surviving_families = {r.strategy.family for r in survivors}
    tested_families = {r.strategy.family for r in tested}
    for family in sorted(tested_families - surviving_families):
        # Only drop a family once its vol-filtered variants have also been
        # tried and failed; failing unfiltered in round 1 earns a retry with
        # the filter, not a death sentence.
        tried_filtered = any(
            r.strategy.family == family and r.strategy.params.get("vol_filtered")
            for r in tested
        )
        if tried_filtered:
            feedback.dropped_families.add(family)
            feedback.notes.append(f"dropped family '{family}': no variant survived")
        else:
            feedback.notes.append(
                f"family '{family}' failed unfiltered; retrying with vol filter"
            )

    # If vol-filtered variants outperform their unfiltered siblings on ICIR,
    # the losers are being hurt by high-vol regimes -> require the filter.
    filtered = [r.ic.icir for r in tested if r.strategy.params.get("vol_filtered")]
    unfiltered = [
        r.ic.icir for r in tested if not r.strategy.params.get("vol_filtered")
    ]
    filtered = [x for x in filtered if np.isfinite(x)]
    unfiltered = [x for x in unfiltered if np.isfinite(x)]
    if filtered and unfiltered and np.mean(filtered) > np.mean(unfiltered) + 0.1:
        if not feedback.require_vol_filter:
            feedback.require_vol_filter = True
            feedback.notes.append(
                "vol-filtered variants materially outperform; requiring vol filter"
            )
    return feedback


def run_loop(
    in_sample: pd.DataFrame,
    rounds: int = 3,
    min_icir: float = 0.3,
    min_half_life: float = 5.0,
    cost_per_turnover: float = 0.0005,
    verbose: bool = True,
) -> LoopResult:
    if not 1 <= rounds <= MAX_ROUNDS:
        raise ValueError(f"rounds must be between 1 and {MAX_ROUNDS}")

    round_reports: list[RoundReport] = []
    kill_log: list[str] = []
    feedback = GenerationFeedback()
    # Survivors accumulate across rounds, deduplicated by (family, params):
    # the same variant regenerated in a later round is the same strategy.
    pool: dict[str, BacktestResult] = {}
    total_tested = 0

    for round_number in range(1, rounds + 1):
        strategies = generate_strategies(round_number, feedback)
        if not strategies:
            kill_log.append(f"round {round_number}: nothing left to generate, stopping")
            break
        tested: list[BacktestResult] = []
        survivors: list[BacktestResult] = []
        for strat in strategies:
            result = run_backtest(strat, in_sample, cost_per_turnover=cost_per_turnover)
            tested.append(result)
            total_tested += 1
            if not np.isfinite(result.ic.icir) or result.ic.icir < min_icir:
                kill_log.append(
                    f"{strat.name}: killed on ICIR "
                    f"({result.ic.icir:.3f} < {min_icir})"
                )
            elif result.half_life < min_half_life:
                kill_log.append(
                    f"{strat.name}: killed on half-life "
                    f"({result.half_life:.1f} < {min_half_life} bars)"
                )
            else:
                survivors.append(result)
                key = f"{strat.family}|{sorted(strat.params.items())}"
                best = pool.get(key)
                if best is None or result.ic.icir > best.ic.icir:
                    pool[key] = result

        feedback = _analyze_failures(tested, survivors, feedback)
        round_reports.append(
            RoundReport(round_number, tested, survivors, feedback)
        )
        if verbose:
            print(
                f"round {round_number}: tested {len(tested)}, "
                f"survived {len(survivors)}, pool {len(pool)}"
            )
            for note in feedback.notes:
                print(f"  feedback: {note}")

    final = sorted(pool.values(), key=lambda r: r.ic.icir, reverse=True)
    return LoopResult(
        rounds=round_reports,
        survivors=final,
        total_strategies_tested=total_tested,
        kill_log=kill_log,
    )
