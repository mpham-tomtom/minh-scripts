"""Plain-text reporting for loop rounds and the final gate."""

from __future__ import annotations

from .gate import GateResult
from .loop import LoopResult


def format_loop_report(result: LoopResult) -> str:
    lines: list[str] = []
    for rnd in result.rounds:
        survived = [c for c in rnd.candidates if c.verdict == "survived"]
        lines.append(f"\n=== Round {rnd.round_num} ===")
        lines.append(
            f"tested {len(rnd.candidates)} candidates, {len(survived)} survived"
        )
        for cand in sorted(rnd.candidates, key=lambda c: c.score.icir, reverse=True):
            mark = "+" if cand.verdict == "survived" else "-"
            lines.append(
                f"  {mark} {cand.strategy.name:34s} {cand.strategy.params} "
                f"ICIR={cand.score.icir:5.2f} meanIC={cand.score.mean_ic:6.3f} "
                f"HL={cand.score.half_life:5.1f}d sharpe={cand.sharpe:5.2f}"
            )
            if cand.verdict != "survived":
                lines.append(f"      {cand.verdict}")
        lines.append("  failure analysis fed to next round:")
        for family, note in rnd.failure_analysis.items():
            lines.append(f"    {family}: {note}")
        if rnd.banned_families:
            lines.append(f"  banned families: {sorted(rnd.banned_families)}")
    lines.append(
        f"\nloop finished: {len(result.survivors)} survivors out of "
        f"{result.total_strategies_tested} strategies tested"
    )
    return "\n".join(lines)


def format_gate_report(gate: GateResult) -> str:
    lines = [
        "\n=== OUT-OF-SAMPLE GATE ===",
        f"strategies tested across all rounds: {gate.total_strategies_tested}",
        f"Bonferroni-corrected significance threshold: "
        f"{gate.alpha} / {gate.total_strategies_tested} = {gate.bonferroni_threshold:.2e}",
    ]
    for v in gate.verdicts:
        cand = v.candidate
        lines.append(f"\n  {cand.strategy.name} {cand.strategy.params}")
        lines.append(
            f"    ICIR      in-sample {cand.score.icir:5.2f} -> "
            f"out-of-sample {v.oos_score.icir:5.2f}   "
            f"[{'HOLDS' if v.icir_holds else 'FAILS'}]"
        )
        lines.append(
            f"    half-life in-sample {cand.score.half_life:5.1f}d -> "
            f"out-of-sample {v.oos_score.half_life:5.1f}d  "
            f"[{'HOLDS' if v.decay_holds else 'FAILS'}]"
        )
        lines.append(
            f"    OOS IC {v.oos_score.overall_ic:6.3f}, p-value {v.oos_score.p_value:.2e} "
            f"vs {v.bonferroni_threshold:.2e}  "
            f"[{'SIGNIFICANT' if v.significant_after_correction else 'NOT SIGNIFICANT'}]"
        )
        lines.append(f"    => {'VIABLE' if v.passed else 'DISCARDED'}")
    viable = gate.viable
    lines.append(
        f"\n{len(viable)} of {len(gate.verdicts)} survivors passed the gate."
    )
    if viable:
        lines.append(
            "Viable strategies still require 4-8 weeks of paper trading before "
            "any real capital. Past performance does not guarantee future results."
        )
    else:
        lines.append(
            "No strategy passed. That is the framework working: what looked good "
            "in-sample was luck, and the gate caught it before your money did."
        )
    return "\n".join(lines)
