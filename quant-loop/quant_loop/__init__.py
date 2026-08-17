"""quant_loop: a loop-engineering framework for finding tradeable edges.

Implements the quant research loop:
    generate -> backtest -> score (ICIR) -> analyze failures -> select -> repeat,
followed by a strict out-of-sample gate with a Bonferroni correction for
multiple testing.

Educational use only. Trading involves real financial risk. Past performance
does not guarantee future results.
"""

from .data import ResearchData, generate_synthetic_prices, load_prices_csv
from .strategies import Strategy, generate_candidates
from .backtest import backtest
from .metrics import monthly_ic, icir, ic_decay_curve, estimate_half_life
from .loop import LoopConfig, run_loop
from .gate import run_gate

__all__ = [
    "ResearchData",
    "generate_synthetic_prices",
    "load_prices_csv",
    "Strategy",
    "generate_candidates",
    "backtest",
    "monthly_ic",
    "icir",
    "ic_decay_curve",
    "estimate_half_life",
    "LoopConfig",
    "run_loop",
    "run_gate",
]
