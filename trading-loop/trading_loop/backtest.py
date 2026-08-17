"""Vectorized backtester.

Signals are lagged one bar before being applied to returns: a signal
computed on bar t earns the return of bar t+1. This is the single most
common source of accidental lookahead in home-grown backtests, so it is
enforced here rather than left to each strategy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import (
    DEFAULT_LAGS,
    ICStats,
    ic_decay_curve,
    ic_stats,
    max_drawdown,
    sharpe_ratio,
    signal_half_life,
)
from .strategies import Strategy


@dataclass
class BacktestResult:
    strategy: Strategy
    signal: pd.Series
    strategy_returns: pd.Series
    ic: ICStats
    half_life: float
    decay_curve: pd.Series
    sharpe: float
    max_dd: float
    total_return: float


def run_backtest(
    strategy: Strategy,
    prices: pd.DataFrame,
    cost_per_turnover: float = 0.0005,
    lags: tuple[int, ...] = DEFAULT_LAGS,
) -> BacktestResult:
    """Backtest one strategy on one price frame.

    cost_per_turnover: cost charged per unit of position change
    (0.0005 = 5 bps per full flip leg), covering commission + slippage.
    """
    signal = strategy.signal(prices).astype(float)
    asset_returns = prices["close"].pct_change()

    position = signal.shift(1).fillna(0.0)
    turnover = position.diff().abs().fillna(0.0)
    strategy_returns = position * asset_returns - turnover * cost_per_turnover

    forward_returns = asset_returns.shift(-1)
    ic = ic_stats(signal, forward_returns)
    decay = ic_decay_curve(signal, asset_returns, lags)
    # |IC| below ~2 standard errors of a correlation on this many bars is
    # indistinguishable from zero; without this floor a flat curve of
    # negligible ICs would fit as an "eternal" (infinite half-life) signal.
    noise_floor = 2.0 / np.sqrt(max(len(prices), 4))
    half_life = signal_half_life(decay, noise_floor=noise_floor)

    equity = (1.0 + strategy_returns.fillna(0.0)).cumprod()
    return BacktestResult(
        strategy=strategy,
        signal=signal,
        strategy_returns=strategy_returns,
        ic=ic,
        half_life=half_life,
        decay_curve=decay,
        sharpe=sharpe_ratio(strategy_returns),
        max_dd=max_drawdown(strategy_returns),
        total_return=float(equity.iloc[-1] - 1.0) if len(equity) else np.nan,
    )
