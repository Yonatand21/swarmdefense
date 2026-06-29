"""Thin CLI: run scenarios deterministically and print / emit the contract.

- single run  : print a Result, optionally emit JSON (Phase 0)
- --runs N    : Monte Carlo aggregation, print distribution summary (Phase 1)
- --all       : emit every canonical scenario's Monte Carlo JSON + a manifest for the dashboard,
                which reads them statically -- no server (Phase 2; honors §11/§12).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.montecarlo import DEFAULT_RUNS, run_montecarlo
from engine.requirements import solve
from engine.simulation import simulate
from schema.loader import DEFAULT_SCENARIO_DIR, load_effectors, load_scenario, load_scenarios
from schema.result import MonteCarloResult, Result
from schema.solver import Requirement, SolverResult

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
DASHBOARD_DATA_DIR = ROOT / "frontend" / "public" / "data"


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


def _print_solver(res: SolverResult) -> None:
    if res.feasible and res.recommended is not None:
        r = res.recommended
        wub = "unlimited" if r.waves_until_black is None else f"{r.waves_until_black:.1f}"
        _boxed(
            [
                f"REQUIREMENT met: p90 armed leakers <= {res.requirement.max_p90_armed_leakers:g}  "
                f"({res.candidates_evaluated} postures, {res.runs} runs each)",
                f"Recommended : {r.label}",
                f"Procurement : {_fmt_money(r.procurement_cost)}  (consumable munitions stocked)",
                f"Protection  : p90 armed {r.p90_armed_leakers:g} | cost-exchange {r.cost_exchange_median:.2f}x",
                f"SUSTAINMENT : waves-until-black {wub}  (the logistics race headline)",
            ]
        )
        print("  Ledger (burn vs stock):")
        for ln in res.recommended_ledger:
            if ln.consumable and ln.waves_until_black is not None:
                print(
                    f"    {ln.effector_id:<18} {ln.rounds_per_wave:5.1f} rounds/wave  "
                    f"mag {ln.magazine:<4} -> {ln.waves_until_black:.2f} waves"
                )
            else:
                print(f"    {ln.effector_id:<18} {ln.rounds_per_wave:5.1f} rounds/wave  (reusable)")
    else:
        b = res.best_achievable
        _boxed(
            [
                f"REQUIREMENT UNMET: nothing in inventory holds this picture at p90 <= "
                f"{res.requirement.max_p90_armed_leakers:g}",
                f"Closest     : {b.label}",
                f"Best p90    : {b.p90_armed_leakers:g} armed leakers  (gap {res.binding_gap:g})",
                f"Implication : accept {b.p90_armed_leakers:g}, or acquire capability beyond this inventory",
            ]
        )

    print("  Cost / protection frontier:")
    for c in res.frontier:
        mark = "  <- recommended" if (res.recommended and c.label == res.recommended.label) else ""
        print(f"    {_fmt_money(c.procurement_cost):>12}  -> p90 armed {c.p90_armed_leakers:g}{mark}")


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
    parser.add_argument(
        "--requirements",
        action="store_true",
        help="Inverse-design: find the cheapest posture that meets a leak tolerance for this swarm.",
    )
    parser.add_argument(
        "--max-leakers",
        type=float,
        default=2.0,
        help="Requirements tolerance: max p90 armed leakers (default 2).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export every scenario's Monte Carlo JSON + manifest for the dashboard.",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=f"Where --all / --emit write JSON (default for --all: {DASHBOARD_DATA_DIR}).",
    )
    args = parser.parse_args(argv)

    if args.all:
        runs = args.runs if args.runs > 1 else DEFAULT_RUNS
        out_dir = Path(args.out_dir) if args.out_dir else DASHBOARD_DATA_DIR
        _export_all(load_scenarios(args.scenario_dir), runs, out_dir)
        return 0

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

    if args.requirements:
        catalog = load_effectors(Path(args.scenario_dir) / "effectors.yaml")
        runs = args.runs if args.runs > 1 else DEFAULT_RUNS
        res = solve(
            scenario.swarm,
            scenario.approach_distance,
            Requirement(max_p90_armed_leakers=args.max_leakers),
            catalog,
            base_seed=scenario.seed,
            runs=runs,
        )
        _print_solver(res)
        if args.emit:
            _emit(f"{args.scenario}.requirements.json", res.model_dump_json(indent=2))
        return 0

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


def _export_all(scenarios, runs: int, out_dir: Path) -> None:
    """Run every scenario at `runs`x and write JSON + a manifest the dashboard loads statically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, scenario in scenarios.items():
        mc = run_montecarlo(scenario, runs=runs)
        filename = f"{name}.montecarlo.json"
        (out_dir / filename).write_text(mc.model_dump_json(indent=2), encoding="utf-8")
        manifest.append(
            {
                "name": name,
                "description": scenario.description.strip(),
                "file": filename,
                "runs": runs,
            }
        )
        print(f"  {name}: median leakers {mc.metrics.leakers_total.median:g}, "
              f"exchange {mc.metrics.cost_exchange_ratio.median:.2f}x")
    (out_dir / "index.json").write_text(
        json.dumps({"scenarios": manifest}, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(manifest)} scenarios + index.json to {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
