#!/usr/bin/env python3
"""Run the full loop-engineering workflow end to end.

Usage:
    python run_loop.py --synthetic                 # demo on generated data
    python run_loop.py --csv prices.csv            # your own daily OHLCV CSV
    python run_loop.py --csv prices.csv --rounds 4 --holdout 0.3

The CSV needs a 'date' column and a 'close' column.
"""

from __future__ import annotations

import argparse

from trading_loop.data import load_csv, make_synthetic_prices, split_data
from trading_loop.gate import run_gate
from trading_loop.loop import run_loop


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", help="path to a daily price CSV (date + close columns)")
    source.add_argument(
        "--synthetic", action="store_true", help="use generated demo data"
    )
    parser.add_argument("--rounds", type=int, default=3, help="loop rounds (max 5)")
    parser.add_argument(
        "--holdout", type=float, default=0.25, help="out-of-sample fraction (0.2-0.3)"
    )
    parser.add_argument(
        "--cost", type=float, default=0.0005, help="cost per unit turnover (5 bps default)"
    )
    parser.add_argument("--seed", type=int, default=7, help="seed for synthetic data")
    args = parser.parse_args()

    prices = (
        make_synthetic_prices(seed=args.seed) if args.synthetic else load_csv(args.csv)
    )
    split = split_data(prices, holdout_frac=args.holdout)
    print(
        f"data: {len(prices)} bars | in-sample {len(split.in_sample)} "
        f"({split.in_sample.index.min().date()} .. {split.in_sample.index.max().date()}) | "
        f"held out {len(split.out_of_sample)} "
        f"({split.out_of_sample.index.min().date()} .. {split.out_of_sample.index.max().date()})"
    )
    print("the held-out slice will not be touched until the gate\n")

    loop_result = run_loop(
        split.in_sample, rounds=args.rounds, cost_per_turnover=args.cost
    )
    print(
        f"\nloop done: {loop_result.total_strategies_tested} strategies tested, "
        f"{len(loop_result.survivors)} unique survivors"
    )
    if not loop_result.survivors:
        print("nothing survived the loop — no edge found in this data")
        return 0

    print("\ntop in-sample survivors:")
    for r in loop_result.survivors[:10]:
        print(
            f"  {r.strategy.name:48s} ICIR {r.ic.icir:6.3f}  "
            f"half-life {r.half_life:6.1f}  sharpe {r.sharpe:6.2f}  "
            f"maxDD {r.max_dd:6.1%}"
        )

    print(
        f"\n=== OUT-OF-SAMPLE GATE (Bonferroni over "
        f"{loop_result.total_strategies_tested} strategies tested) ==="
    )
    gate_results = run_gate(
        loop_result.survivors,
        split.out_of_sample,
        total_strategies_tested=loop_result.total_strategies_tested,
        cost_per_turnover=args.cost,
    )
    passed = [g for g in gate_results if g.passed]
    for g in gate_results:
        marks = (
            f"icir:{'PASS' if g.icir_holds else 'fail'} "
            f"decay:{'PASS' if g.decay_holds else 'fail'} "
            f"sig:{'PASS' if g.significant else 'fail'}"
        )
        print(
            f"  {g.name:48s} IS-ICIR {g.in_sample_icir:6.3f} -> OOS-ICIR "
            f"{g.oos_icir:6.3f}  p={g.oos_p_value:.2e} "
            f"(thr {g.bonferroni_threshold:.2e})  [{marks}]"
        )

    print(f"\n{len(passed)} of {len(gate_results)} survivors passed the full gate")
    if passed:
        print("viable strategies (paper trade 4-8 weeks before any real money):")
        for g in passed:
            print(f"  {g.name}")
    else:
        print(
            "no strategy passed — everything the loop found was overfit. "
            "that is the gate doing its job."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
