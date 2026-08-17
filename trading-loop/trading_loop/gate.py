"""The out-of-sample gate.

Every strategy that survives the loop is re-tested on data it has never
seen. Three checks, all mandatory:

1. ICIR holds: out-of-sample ICIR must not drop more than `max_icir_drop`
   (default 50%) from in-sample, and must stay above the noise floor.
2. Decay holds: the out-of-sample half-life must remain tradeable.
3. Significance after multiple-testing correction: the p-value of the
   out-of-sample mean IC must pass a Bonferroni-adjusted threshold of
   alpha / N, where N is EVERY strategy tested across ALL rounds — not
   just the survivors that reached the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import BacktestResult, run_backtest


@dataclass
class GateResult:
    name: str
    in_sample_icir: float
    oos_icir: float
    in_sample_half_life: float
    oos_half_life: float
    oos_p_value: float
    bonferroni_threshold: float
    icir_holds: bool
    decay_holds: bool
    significant: bool
    oos_result: BacktestResult = field(repr=False)

    @property
    def passed(self) -> bool:
        return self.icir_holds and self.decay_holds and self.significant


def run_gate(
    survivors: list[BacktestResult],
    out_of_sample: pd.DataFrame,
    total_strategies_tested: int,
    alpha: float = 0.05,
    max_icir_drop: float = 0.5,
    min_half_life: float = 5.0,
    min_oos_icir: float = 0.3,
    cost_per_turnover: float = 0.0005,
) -> list[GateResult]:
    """Test every loop survivor on the held-out data.

    total_strategies_tested must count every strategy ever backtested in
    the loop (all rounds), because that is the number of chances luck had.
    """
    if total_strategies_tested < len(survivors):
        raise ValueError(
            "total_strategies_tested cannot be smaller than the survivor count"
        )
    threshold = alpha / max(total_strategies_tested, 1)
    results: list[GateResult] = []
    for is_result in survivors:
        oos = run_backtest(
            is_result.strategy, out_of_sample, cost_per_turnover=cost_per_turnover
        )
        is_icir = is_result.ic.icir
        oos_icir = oos.ic.icir

        icir_holds = (
            np.isfinite(oos_icir)
            and np.isfinite(is_icir)
            and oos_icir >= min_oos_icir
            # Same-sign and within the allowed drop from in-sample.
            and np.sign(oos_icir) == np.sign(is_icir)
            and abs(oos_icir) >= (1.0 - max_icir_drop) * abs(is_icir)
        )
        decay_holds = oos.half_life >= min_half_life
        significant = np.isfinite(oos.ic.p_value) and oos.ic.p_value <= threshold

        results.append(
            GateResult(
                name=is_result.strategy.name,
                in_sample_icir=is_icir,
                oos_icir=oos_icir,
                in_sample_half_life=is_result.half_life,
                oos_half_life=oos.half_life,
                oos_p_value=oos.ic.p_value,
                bonferroni_threshold=threshold,
                icir_holds=bool(icir_holds),
                decay_holds=bool(decay_holds),
                significant=bool(significant),
                oos_result=oos,
            )
        )
    return results
