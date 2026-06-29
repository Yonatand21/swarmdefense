"""Monte Carlo aggregation -- the analysis core (ARCHITECTURE_AND_PLAN.md §8, §10 Phase 1).

One run lies (leakers are probabilistic); the distribution tells the truth. This module runs a
scenario many times over derived seeds, aggregates the headline metrics into distributions, builds
the attrition curve and magazine timeline, and selects the median-leaker run as the single
representative trace for replay (the §5 commitment).

Memory-light by design: we never retain N full traces. Pass 1 keeps only small per-run summaries;
pass 2 re-simulates the chosen representative seed to recover its trace (exact, because the engine
is deterministic).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engine.models import Scenario
from engine.simulation import simulate
from schema.result import (
    AttritionPoint,
    Distribution,
    MagazineStat,
    Metrics,
    MonteCarloMetrics,
    MonteCarloResult,
    RunTrace,
)

DEFAULT_RUNS = 500


@dataclass
class _RunSummary:
    seed: int
    metrics: Metrics
    alive_series: list[int]
    dry_ticks: dict[str, Optional[int]]


def run_montecarlo(
    scenario: Scenario,
    runs: int = DEFAULT_RUNS,
    base_seed: Optional[int] = None,
) -> MonteCarloResult:
    if runs < 1:
        raise ValueError("runs must be >= 1")
    base = scenario.seed if base_seed is None else base_seed

    summaries = [_run_one(scenario, base + i) for i in range(runs)]

    metrics = _aggregate_metrics(summaries)
    attrition = _attrition_curve(summaries, runs)
    magazine = _magazine_timeline(scenario, summaries, runs)

    representative_seed = _representative_seed(summaries)
    representative = _representative_trace(scenario, representative_seed)

    total_threats = sum(e.count for e in scenario.swarm)
    armed_threats = sum(e.count for e in scenario.swarm if not e.spec.is_decoy)

    return MonteCarloResult(
        scenario_name=scenario.name,
        runs=runs,
        base_seed=base,
        total_threats=total_threats,
        armed_threats=armed_threats,
        metrics=metrics,
        attrition_curve=attrition,
        magazine_timeline=magazine,
        representative_seed=representative_seed,
        representative=representative,
    )


def _run_one(scenario: Scenario, seed: int) -> _RunSummary:
    result = simulate(scenario.model_copy(update={"seed": seed}))
    alive_series = [sum(1 for t in frame.threats if t.alive) for frame in result.trace.frames]
    dry_ticks = _first_dry_ticks(result.trace)
    return _RunSummary(seed=seed, metrics=result.metrics, alive_series=alive_series, dry_ticks=dry_ticks)


def _first_dry_ticks(trace: RunTrace) -> dict[str, Optional[int]]:
    """First tick each effector entered a reload (i.e. ran its magazine dry)."""
    first: dict[str, Optional[int]] = {}
    for frame in trace.frames:
        for eff in frame.effectors:
            if eff.effector_id not in first:
                first[eff.effector_id] = None
            if first[eff.effector_id] is None and eff.reloading:
                first[eff.effector_id] = frame.tick
    return first


def _aggregate_metrics(summaries: list[_RunSummary]) -> MonteCarloMetrics:
    def col(getter) -> Distribution:
        return Distribution.from_values([float(getter(s.metrics)) for s in summaries])

    return MonteCarloMetrics(
        leakers_total=col(lambda m: m.leakers_total),
        leakers_armed=col(lambda m: m.leakers_armed),
        leakers_decoy=col(lambda m: m.leakers_decoy),
        defeated=col(lambda m: m.defeated),
        cost_exchange_ratio=col(lambda m: m.cost_exchange_ratio if m.cost_exchange_ratio is not None else 0.0),
        defender_cost=col(lambda m: m.defender_cost),
        damage_to_asset=col(lambda m: m.damage_to_asset),
        shots_fired=col(lambda m: m.shots_fired),
    )


def _attrition_curve(summaries: list[_RunSummary], runs: int) -> list[AttritionPoint]:
    """Mean threats-alive per tick. Runs that ended early contribute 0 past their end."""
    max_ticks = max((len(s.alive_series) for s in summaries), default=0)
    curve: list[AttritionPoint] = []
    for tick in range(max_ticks):
        total = sum(s.alive_series[tick] if tick < len(s.alive_series) else 0 for s in summaries)
        curve.append(AttritionPoint(tick=tick + 1, mean_alive=total / runs))
    return curve


def _magazine_timeline(
    scenario: Scenario, summaries: list[_RunSummary], runs: int
) -> list[MagazineStat]:
    stats: list[MagazineStat] = []
    for eff in scenario.defense.effectors:
        dry = [s.dry_ticks.get(eff.id) for s in summaries]
        hit = [t for t in dry if t is not None]
        stats.append(
            MagazineStat(
                effector_id=eff.id,
                dry_fraction=len(hit) / runs,
                mean_first_dry_tick=(sum(hit) / len(hit)) if hit else None,
            )
        )
    return stats


def _representative_seed(summaries: list[_RunSummary]) -> int:
    """Median-leaker run, ties broken by lowest seed; lower-median index (§5)."""
    ordered = sorted(summaries, key=lambda s: (s.metrics.leakers_total, s.seed))
    return ordered[(len(ordered) - 1) // 2].seed


def _representative_trace(scenario: Scenario, seed: int) -> RunTrace:
    return simulate(scenario.model_copy(update={"seed": seed})).trace
