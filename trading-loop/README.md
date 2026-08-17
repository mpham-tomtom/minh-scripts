# trading-loop

A loop-engineering framework for quantitative strategy research: generate
strategies, backtest them, score them with ICIR, check signal decay, feed
failure analysis back into generation, repeat — then force every survivor
through a Bonferroni-corrected out-of-sample gate on data that was locked
away before round 1.

The point of the framework is not to find strategies. It is to **kill**
strategies that only look good because they were fit to noise. On a random
walk, nothing should pass the gate (there is a test asserting exactly that).

## Quick start

```bash
pip install -r requirements.txt

# Demo on synthetic data (has a weak planted mean-reversion edge)
python run_loop.py --synthetic

# Your own data: daily CSV with 'date' and 'close' columns
python run_loop.py --csv prices.csv --rounds 3 --holdout 0.25

# Tests
python -m pytest tests/ -q
```

## How it maps to the framework

| Stage | Module | What it does |
|---|---|---|
| Data split | `trading_loop/data.py` | Holds out the most recent 20–30% before anything else runs. `DataSplit` refuses overlapping or out-of-order splits. |
| 1. Generation | `trading_loop/strategies.py` | Parameterized families (RSI reversion, z-score reversion, momentum, MA cross, 1-day reversal) on **coarse** grids — no magic-number sweeps. Accepts `GenerationFeedback` from the previous round. |
| 2. Backtest | `trading_loop/backtest.py` | Vectorized; signals are force-lagged one bar (no lookahead), turnover costs charged. |
| 3. Scoring | `trading_loop/metrics.py` | Monthly IC (signal vs forward return), ICIR = mean/std of monthly ICs, plus Sharpe and max drawdown for context. |
| Decay check | `trading_loop/metrics.py` | \|IC\| by horizon (1/5/10/20/50 bars), exponential fit → half-life. Under 5 bars → killed. |
| 4–5. Analyze & select | `trading_loop/loop.py` | Kills ICIR < 0.3 and half-life < 5. Failure analysis: families with zero survivors are dropped; if vol-filtered variants beat unfiltered ones, the filter becomes mandatory next round. Hard cap of 5 rounds. |
| OOS gate | `trading_loop/gate.py` | Three mandatory checks on the held-out data: ICIR holds (≥ 0.3, same sign, drop ≤ 50%), half-life holds (≥ 5 bars), and mean-IC p-value ≤ 0.05 / N where **N counts every strategy tested in every round**, not just the survivors. |

## Interpreting ICIR

- **≥ 0.5** strong, consistently informative signal
- **0.3 – 0.5** moderate, needs more validation
- **< 0.3** probably noise — the loop kills these automatically

## What the loop refuses to do

- Run more than 5 rounds (`MAX_ROUNDS`).
- Let the out-of-sample slice leak into the loop (`DataSplit` validates this).
- Gate against a dishonest attempt count (`run_gate` raises if the total is
  smaller than the survivor count).
- Earn returns on the bar the signal was computed (backtester lags all
  signals; there is a lookahead regression test).

## Disclaimers

Educational tooling only — not financial advice. Trading involves real risk
of loss; past performance does not guarantee future results. Even strategies
that pass the full gate can lose money live (slippage, regime shifts). Real
quant firms layer walk-forward analysis, Monte Carlo simulation, and paper
trading on top of this. Paper trade for at least 4–8 weeks before risking
money, size positions you can afford to lose, and never trade borrowed money.
