"""Thin CLI: run a scenario deterministically and print / emit the Result (the contract).

Phase 0 scope (ARCHITECTURE_AND_PLAN.md §10): one deterministic run printing a result object.
Monte Carlo aggregation and the metrics dashboard arrive in Phase 1/2.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.montecarlo import DEFAULT_RUNS, run_montecarlo
from engine.simulation import simulate
from schema.loader import DEFAULT_SCENARIO_DIR, load_scenario, load_scenarios
from schema.result import MonteCarloResult, Result

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def _fmt_money(value: float) -> str:
    return f"${value:,.0f}"


def _boxed(lines: list[str]) -> None:
    width = max(len(line) for line in lines)
    print("-" * width)
    for line in lines:
        print(line)
    print("-" * width)


def _print_summary(result: Result) -> None:
    m = result.metrics
    ratio = "n/a (attacker spent $0)" if m.cost_exchange_ratio is None else f"{m.cost_exchange_ratio:.2f}x"
    _boxed(
        [
            f"Scenario : {result.scenario_name}  (seed={result.seed}, ticks={result.trace.ticks})",
            f"Threats  : {m.total_threats} launched | {m.defeated} defeated | {m.leakers_total} leaked",
            f"Leakers  : {m.leakers_armed} armed (damage {m.damage_to_asset:g}) | {m.leakers_decoy} decoy",
            f"Shots    : {m.shots_fired} fired",
            f"Cost     : defender {_fmt_money(m.defender_cost)} vs attacker {_fmt_money(m.attacker_cost)}",
            f"Exchange : {ratio}  (defender $ / attacker $; lower is better for the defender)",
        ]
    )


def _print_mc_summary(mc: MonteCarloResult) -> None:
    m = mc.metrics
    lt, ce = m.leakers_total, m.cost_exchange_ratio
    dry = [s for s in mc.magazine_timeline if s.dry_fraction > 0]
    if dry:
        dry_txt = ", ".join(
            f"{s.effector_id}~t{s.mean_first_dry_tick:.0f} ({s.dry_fraction:.0%})" for s in dry
        )
    else:
        dry_txt = "none ran dry"
    _boxed(
        [
            f"Scenario : {mc.scenario_name}  ({mc.runs} runs, base_seed={mc.base_seed})",
            f"Leakers  : median {lt.median:g} | p10-p90 {lt.p10:g}-{lt.p90:g} | "
            f"max {lt.max:g}  (of distribution)",
            f"Armed    : median {m.leakers_armed.median:g} | decoy median {m.leakers_decoy.median:g}",
            f"Exchange : median {ce.median:.2f}x | p10-p90 {ce.p10:.2f}x-{ce.p90:.2f}x",
            f"Def cost : mean {_fmt_money(m.defender_cost.mean)} | shots mean {m.shots_fired.mean:.0f}",
            f"Magazine : {dry_txt}",
            f"Repr.run : seed {mc.representative_seed} (median-leaker), {mc.representative.ticks} ticks",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Counter-swarm engagement sandbox (Phase 0).")
    parser.add_argument("scenario", nargs="?", help="Scenario name to run.")
    parser.add_argument("--list", action="store_true", help="List available scenarios and exit.")
    parser.add_argument("--seed", type=int, default=None, help="Override the scenario seed.")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help=f"Monte Carlo run count. 1 = single run; >1 aggregates (canonical: {DEFAULT_RUNS}).",
    )
    parser.add_argument(
        "--scenario-dir",
        default=str(DEFAULT_SCENARIO_DIR),
        help="Directory containing threats/effectors/scenarios YAML.",
    )
    parser.add_argument("--emit", action="store_true", help="Write the result JSON to outputs/.")
    args = parser.parse_args(argv)

    if args.list or not args.scenario:
        scenarios = load_scenarios(args.scenario_dir)
        print("Available scenarios:")
        for name, sc in scenarios.items():
            print(f"  {name}\n      {sc.description.strip()}")
        if not args.scenario:
            return 0
        return 0

    scenario = load_scenario(args.scenario, args.scenario_dir)
    if args.seed is not None:
        scenario = scenario.model_copy(update={"seed": args.seed})

    if args.runs > 1:
        mc = run_montecarlo(scenario, runs=args.runs)
        _print_mc_summary(mc)
        if args.emit:
            _emit(f"{mc.scenario_name}.montecarlo.json", mc.model_dump_json(indent=2))
        return 0

    result = simulate(scenario)
    _print_summary(result)
    if args.emit:
        _emit(f"{result.scenario_name}.result.json", result.model_dump_json(indent=2))
    return 0


def _emit(filename: str, payload: str) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / filename
    out_path.write_text(payload, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    raise SystemExit(main())
