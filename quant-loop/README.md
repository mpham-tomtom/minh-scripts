# quant-loop

A loop-engineering framework for finding trading strategies that survive
out-of-sample testing, built after the "How Quants Use Loop Engineering to
Find Trades That Actually Work" framework.

The core idea: a single backtest on the data a strategy was built from is a
closed-book exam where the student already saw the answer key. Instead, run a
loop — generate, backtest, score, analyze failures, select — and then force
every survivor through a strict gate on held-out data it has never seen, with
a multiple-testing correction for every attempt made along the way.

## Quick start

```bash
pip install -r requirements.txt
python run_loop.py                     # demo on synthetic data
python run_loop.py --csv prices.csv    # your own daily data (date,close)
python -m pytest tests                 # test suite
```

## How the pieces map to the framework

| Step | Module | What it does |
|---|---|---|
| 1. Split data first | `data.py` | `ResearchData` locks the most recent 25% away; it can be released exactly once, by the gate. A second access raises `OutOfSampleLeakError`. |
| 2. Generate candidates | `strategies.py` | Five parameterized families (MA momentum, RSI reversion, z-score reversion, breakout, vol-filtered momentum) emitting continuous signals. |
| 3. Backtest | `backtest.py` | Vectorized: signal at close of day *t* earns day *t+1*'s return, minus transaction costs on turnover. |
| 4. Score with ICIR | `metrics.py` | Monthly Information Coefficient, ICIR = mean(IC)/std(IC). Below 0.3 is killed as likely noise. |
| 5. Decay check | `metrics.py` | IC recomputed at forward lags 1/5/10/20/50; exponential fit gives the signal half-life. Under 5 days is killed as untradeable after costs. |
| 6–7. Failure analysis → feedback | `loop.py` | Families whose members all fail with negative IC get banned; surviving parameterizations seed jittered variants next round. |
| 8. Repeat, capped | `loop.py` | Hard cap of 5 rounds (`HARD_MAX_ROUNDS`) — more rounds is more opportunity to overfit. |
| 9–10. Out-of-sample gate | `gate.py` | ICIR must hold (drop < 50%, stay positive), half-life must hold, and the out-of-sample IC must be significant at the **Bonferroni-corrected** threshold: alpha / (every strategy ever tested, not just finalists). |

Extra guardrail beyond the write-up: a **parameter-robustness check**. Before
a candidate survives a round, four jittered-parameter neighbors are scored
too; if the neighborhood's median ICIR is poor, the candidate is killed as a
one-magic-number overfit. Real edges work across a range of reasonable
parameters.

## What a run looks like

The synthetic demo embeds a faint, slow momentum edge (a persistent latent
drift, ~35-day half-life, buried under regime-switching noise ~10x its size)
so there is exactly one real thing to find. A typical run:

- 45 strategies tested across 3 rounds;
- mean-reversion families get banned in round 1 (negative IC — fighting the
  market's actual behavior);
- 8 momentum-flavored survivors reach the gate;
- 7 are discarded there — most with *positive* out-of-sample ICIR that still
  fails the Bonferroni-corrected significance test;
- 1 passes all three checks.

If nothing passes, that is the framework working: the gate caught in-sample
luck before real money did.

## Notes on the statistics

- **Monthly IC uses full-sample demeaning, not within-month demeaning.**
  Demeaning inside a ~21-day window mechanically biases the correlation
  negative for slow signals built from that same month's returns (the
  classic small-sample autocorrelation bias) — enough to flip the measured
  sign of a genuine momentum edge. Each month's IC stays bounded in [-1, 1].
- **Signals are scale-standardized, not z-scored.** Subtracting a trailing
  rolling mean from a slow signal subtracts away the trend level the signal
  exists to carry; dividing by rolling volatility is enough to make families
  comparable.
- **The significance test at the gate** is the one-sided p-value of the
  pooled out-of-sample IC, tested against `alpha / N_total_tested`.

## Layout

```
quant_loop/
  data.py        # ResearchData split-and-lock, CSV loader, synthetic generator
  strategies.py  # strategy families + candidate generation with feedback
  backtest.py    # signal -> positions -> net returns
  metrics.py     # IC, ICIR, decay curve, half-life, significance
  loop.py        # the 5-stage loop with guardrails
  gate.py        # the out-of-sample gate
  report.py      # plain-text reports
run_loop.py      # end-to-end CLI
tests/           # 14 tests covering metrics, isolation, thresholds, the gate
```

## Disclaimers

Educational purposes only. Trading involves real financial risk and past
performance does not guarantee future results. Even strategies that pass the
full loop and gate can lose money live (slippage, regime shifts). This is a
simplified version of professional practice — real desks add walk-forward
analysis, Monte Carlo simulation, and live paper-trading periods. Paper trade
any strategy for at least 4–8 weeks before real money, never trade money you
cannot afford to lose, and never trade with borrowed money.
