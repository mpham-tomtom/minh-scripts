#!/usr/bin/env python3
"""End-to-end demo of the quant research loop + out-of-sample gate.

    python run_loop.py                     # synthetic data demo
    python run_loop.py --csv prices.csv    # your own daily closes (date,close)

Educational use only. Not investment advice.
"""

from __future__ import annotations

import argparse

from quant_loop import (
    LoopConfig,
    ResearchData,
    generate_synthetic_prices,
    load_prices_csv,
    run_gate,
    run_loop,
)
from quant_loop.report import format_gate_report, format_loop_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="CSV with 'date' and 'close' columns")
    parser.add_argument("--rounds", type=int, default=3, help="loop rounds (hard cap 5)")
    parser.add_argument("--candidates", type=int, default=15, help="candidates per round")
    parser.add_argument("--holdout", type=float, default=0.25, help="out-of-sample fraction")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.csv:
        prices = load_prices_csv(args.csv)
        print(f"loaded {len(prices)} rows from {args.csv}")
    else:
        prices = generate_synthetic_prices()
        print(f"generated {len(prices)} days of synthetic prices (weak momentum edge embedded)")

    # Step 1: split before anything else. The held-out tail is locked until the gate.
    data = ResearchData(prices, holdout_fraction=args.holdout)
    print(
        f"in-sample: {len(data.in_sample)} days up to {data.split_date.date()}; "
        f"out-of-sample locked away until the gate"
    )

    # Steps 2-8: the loop, on in-sample data only.
    config = LoopConfig(rounds=args.rounds, candidates_per_round=args.candidates, seed=args.seed)
    loop_result = run_loop(data.in_sample, config)
    print(format_loop_report(loop_result))

    # Steps 9-10: the gate, with Bonferroni correction for every strategy tested.
    gate = run_gate(loop_result, data, config)
    print(format_gate_report(gate))


if __name__ == "__main__":
    main()
