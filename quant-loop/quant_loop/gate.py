"""The out-of-sample gate — the step that separates real edges from fast overfitting.

Every survivor is re-scored on data it has never seen. Three checks, all
mandatory:

1. ICIR holds: the out-of-sample ICIR may not collapse by more than
   ``max_icir_drop`` (default 50%) versus in-sample, and must stay positive.
2. Decay holds: the out-of-sample half-life must stay at or above the
   tradeable minimum.
3. Significance after multiple-testing correction: the out-of-sample IC's
   one-sided p-value must clear alpha / N_total_tested (Bonferroni), where
   N counts every strategy the loop ever backtested — not just the finalists.
   Testing 200 things and celebrating the one that passes at p<0.05 is just
   automated luck-finding.
"""

from __future__ import annotations

from dataclasses import dataclass

from .backtest import backtest
from .data import ResearchData
from .loop import Candidate, LoopConfig, LoopResult
from .metrics import StrategyScore, score_strategy


@dataclass
class GateVerdict:
    candidate: Candidate
    oos_score: StrategyScore
    icir_holds: bool
    decay_holds: bool
    significant_after_correction: bool
    bonferroni_threshold: float
    passed: bool

    @property
    def name(self) -> str:
        return self.candidate.strategy.name


@dataclass
class GateResult:
    verdicts: list[GateVerdict]
    total_strategies_tested: int
    alpha: float
    bonferroni_threshold: float

    @property
    def viable(self) -> list[GateVerdict]:
        return [v for v in self.verdicts if v.passed]


def run_gate(
    loop_result: LoopResult,
    data: ResearchData,
    config: LoopConfig | None = None,
    alpha: float = 0.05,
    max_icir_drop: float = 0.5,
) -> GateResult:
    """Test every loop survivor on the held-out data, exactly once.

    ``data.release_out_of_sample()`` can only be called a single time; if
    anything upstream already touched the held-out set, this raises instead
    of silently grading strategies on stale "fresh" data.
    """
    config = config or LoopConfig()
    oos_prices = data.release_out_of_sample()

    n_tested = max(1, loop_result.total_strategies_tested)
    threshold = alpha / n_tested

    verdicts: list[GateVerdict] = []
    for cand in loop_result.survivors:
        result = backtest(cand.strategy, oos_prices, cost_bps=config.cost_bps)
        oos = score_strategy(result.signal, result.forward_returns, oos_prices["close"])

        is_icir = cand.score.icir
        icir_holds = oos.icir > 0 and oos.icir >= is_icir * (1.0 - max_icir_drop)
        decay_holds = oos.half_life >= config.half_life_min_days
        significant = oos.p_value < threshold

        verdicts.append(
            GateVerdict(
                candidate=cand,
                oos_score=oos,
                icir_holds=icir_holds,
                decay_holds=decay_holds,
                significant_after_correction=significant,
                bonferroni_threshold=threshold,
                passed=icir_holds and decay_holds and significant,
            )
        )

    return GateResult(
        verdicts=verdicts,
        total_strategies_tested=n_tested,
        alpha=alpha,
        bonferroni_threshold=threshold,
    )
