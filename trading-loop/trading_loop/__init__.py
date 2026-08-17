"""Loop-engineering framework for quantitative strategy research.

Pipeline: generate -> backtest -> score (ICIR) -> decay check -> failure
analysis -> regenerate, for a capped number of rounds, followed by a
Bonferroni-corrected out-of-sample gate on data held out before round 1.
"""

__version__ = "0.1.0"
