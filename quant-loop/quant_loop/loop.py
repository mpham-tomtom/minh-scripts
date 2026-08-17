"""Stages 1-5 wired into the research loop, with the guardrails built in.

Each round: generate candidates -> backtest in-sample -> score -> analyze why
the losers lost -> feed that back into the next round's generation. Hard
guardrails from the framework:

* the loop only ever receives ``ResearchData.in_sample`` — it cannot reach
  the held-out set by construction;
* a hard cap of 5 rounds (more rounds = more chances to overfit);
* a parameter-robustness check: a candidate only survives if jittered
  neighbor parameterizations also score, killing one-magic-number strategies;
* every strategy ever tested is counted, because the gate's Bonferroni
  correction must cover all attempts, not just the finalists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import backtest
from .metrics import StrategyScore, icir, monthly_ic, score_strategy
from .strategies import Strategy, generate_candidates

HARD_MAX_ROUNDS = 5


@dataclass
class LoopConfig:
    rounds: int = 3
    candidates_per_round: int = 15
    icir_min: float = 0.3
    half_life_min_days: float = 5.0
    neighbor_icir_min: float = 0.15  # median ICIR of jittered params must clear this
    cost_bps: float = 5.0
    max_survivors: int = 8
    seed: int = 42

    def __post_init__(self) -> None:
        if self.rounds > HARD_MAX_ROUNDS:
            raise ValueError(
                f"rounds={self.rounds} exceeds the hard cap of {HARD_MAX_ROUNDS}; "
                "more rounds means more opportunity to overfit"
            )


@dataclass
class Candidate:
    strategy: Strategy
    score: StrategyScore
    sharpe: float
    verdict: str  # "survived" or the reason it was killed
    neighbor_median_icir: float | None = None


@dataclass
class RoundLog:
    round_num: int
    candidates: list[Candidate]
    failure_analysis: dict[str, str]
    banned_families: set[str]


@dataclass
class LoopResult:
    survivors: list[Candidate]
    rounds: list[RoundLog]
    total_strategies_tested: int = 0
    survivor_data: dict = field(default_factory=dict)  # name -> in-sample score


def _evaluate(strategy: Strategy, prices: pd.DataFrame, cost_bps: float) -> tuple[StrategyScore, float]:
    result = backtest(strategy, prices, cost_bps=cost_bps)
    score = score_strategy(result.signal, result.forward_returns, prices["close"])
    return score, result.annualized_sharpe


def _neighbor_median_icir(
    strategy: Strategy, prices: pd.DataFrame, cost_bps: float, rng: np.random.Generator
) -> float:
    values = []
    for nb in strategy.neighbors(rng, n=4):
        result = backtest(nb, prices, cost_bps=cost_bps)
        values.append(icir(monthly_ic(result.signal, result.forward_returns)))
    return float(np.median(values)) if values else 0.0


def _analyze_failures(candidates: list[Candidate]) -> tuple[dict[str, str], set[str], dict[str, list[dict]]]:
    """Stage 4: read why the losers lost and turn it into next-round constraints."""
    by_family: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_family.setdefault(c.strategy.family, []).append(c)

    analysis: dict[str, str] = {}
    banned: set[str] = set()
    seeds: dict[str, list[dict]] = {}
    for family, members in by_family.items():
        survivors = [c for c in members if c.verdict == "survived"]
        if survivors:
            seeds[family] = [c.strategy.params for c in survivors]
            analysis[family] = (
                f"{len(survivors)}/{len(members)} survived; refining around "
                f"surviving parameters next round"
            )
            continue
        reasons = pd.Series([c.verdict for c in members]).value_counts()
        top_reason = str(reasons.index[0])
        mean_ic = float(np.mean([c.score.mean_ic for c in members]))
        if mean_ic < -0.005:
            analysis[family] = (
                f"all {len(members)} failed ({top_reason}); mean IC {mean_ic:.3f} is "
                "negative — the family is fighting the market's actual behavior. Banned."
            )
            banned.add(family)
        else:
            analysis[family] = (
                f"all {len(members)} failed ({top_reason}); IC near zero — no signal "
                "found here yet, family deprioritized but not banned"
            )
    return analysis, banned, seeds


def run_loop(in_sample_prices: pd.DataFrame, config: LoopConfig | None = None) -> LoopResult:
    """Run the full generate/test/score/analyze/select loop on in-sample data.

    Pass ``ResearchData.in_sample`` here — never the full history. The
    out-of-sample set stays locked inside ResearchData until the gate.
    """
    config = config or LoopConfig()
    rng = np.random.default_rng(config.seed)

    result = LoopResult(survivors=[], rounds=[])
    banned: set[str] = set()
    seeds: dict[str, list[dict]] = {}
    pool: dict[str, Candidate] = {}  # carried-forward survivors by name

    for round_num in range(1, config.rounds + 1):
        fresh = generate_candidates(
            n=config.candidates_per_round,
            round_num=round_num,
            rng=rng,
            banned_families=banned,
            seed_params=seeds,
        )
        result.total_strategies_tested += len(fresh)

        round_candidates: list[Candidate] = []
        for strategy in fresh:
            score, sharpe = _evaluate(strategy, in_sample_prices, config.cost_bps)
            if score.icir < config.icir_min:
                verdict = f"killed: ICIR {score.icir:.2f} < {config.icir_min} (likely noise)"
            elif score.half_life < config.half_life_min_days:
                verdict = (
                    f"killed: half-life {score.half_life:.1f}d < "
                    f"{config.half_life_min_days:.0f}d (edge gone before costs are paid)"
                )
            else:
                nb_icir = _neighbor_median_icir(strategy, in_sample_prices, config.cost_bps, rng)
                if nb_icir < config.neighbor_icir_min:
                    verdict = (
                        f"killed: neighbor params score {nb_icir:.2f} — works only at "
                        "one magic parameter, classic overfit"
                    )
                else:
                    verdict = "survived"
                round_candidates.append(
                    Candidate(strategy, score, sharpe, verdict, neighbor_median_icir=nb_icir)
                )
                continue
            round_candidates.append(Candidate(strategy, score, sharpe, verdict))

        analysis, newly_banned, seeds = _analyze_failures(round_candidates)
        banned |= newly_banned
        result.rounds.append(
            RoundLog(round_num, round_candidates, analysis, set(banned))
        )

        for cand in round_candidates:
            if cand.verdict == "survived":
                pool[cand.strategy.name] = cand

        # Selection: keep only the strongest survivors in the carried pool.
        ranked = sorted(pool.values(), key=lambda c: c.score.icir, reverse=True)
        pool = {c.strategy.name: c for c in ranked[: config.max_survivors]}

    result.survivors = sorted(pool.values(), key=lambda c: c.score.icir, reverse=True)
    result.survivor_data = {c.strategy.name: c.score for c in result.survivors}
    return result
