"""Stage 2: backtesting. Signals become positions, positions become returns.

Deliberately simple and vectorized: position at today's close is the signal
computed from data up to today, and it earns tomorrow's return. Transaction
costs are charged on turnover so high-churn strategies pay for it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .strategies import Strategy


@dataclass
class BacktestResult:
    strategy: Strategy
    signal: pd.Series          # standardized signal, aligned to decision date
    forward_returns: pd.Series  # the return each signal value was predicting
    strategy_returns: pd.Series  # daily P&L after costs
    total_return: float
    annualized_sharpe: float
    max_drawdown: float


def backtest(strategy: Strategy, prices: pd.DataFrame, cost_bps: float = 5.0) -> BacktestResult:
    """Run one strategy over one price history.

    The signal at date t is paired with the return over (t, t+1]; that pairing
    is exactly what the Information Coefficient later correlates.
    """
    close = prices["close"]
    daily_ret = close.pct_change()
    signal = strategy.signal(prices)

    # Position sizing: the clipped z-score, scaled to a max of 1x notional.
    position = (signal / 3.0).clip(-1.0, 1.0).fillna(0.0)

    fwd_ret = daily_ret.shift(-1)
    gross = position * fwd_ret
    turnover = position.diff().abs().fillna(0.0)
    net = (gross - turnover * cost_bps / 1e4).dropna()

    valid = signal.notna() & fwd_ret.notna()
    sig = signal[valid]
    fwd = fwd_ret[valid]

    equity = (1.0 + net).cumprod()
    peak = equity.cummax()
    max_dd = float((equity / peak - 1.0).min()) if len(equity) else 0.0
    std = float(net.std())
    sharpe = float(net.mean() / std * np.sqrt(252)) if std > 0 else 0.0

    return BacktestResult(
        strategy=strategy,
        signal=sig,
        forward_returns=fwd,
        strategy_returns=net,
        total_return=float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        annualized_sharpe=sharpe,
        max_drawdown=max_dd,
    )
