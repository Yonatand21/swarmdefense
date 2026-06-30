"""Real-engine acceptance tests for the requirements solver (slower; run by default).

These exercise solve() against the actual Monte Carlo engine on the canonical picture. The
synthetic-evaluator unit suite lives in test_requirements.py.
"""

from __future__ import annotations

from engine.models import SwarmEntry
from engine.requirements import solve
from schema.loader import DEFAULT_SCENARIO_DIR, load_effectors, load_scenario, load_threats
from schema.result import Requirement

RUNS = 40


def _catalog():
    return load_effectors(DEFAULT_SCENARIO_DIR / "effectors.yaml")


def test_finds_a_feasible_posture_for_the_canonical_picture():
    sc = load_scenario("layered_mix")
    res = solve(sc.swarm, sc.approach_distance, Requirement(max_p90_armed_leakers=3), _catalog(), runs=RUNS)
    assert res.feasible
    assert res.recommended is not None
    assert res.recommended.p90_armed_leakers <= 3
    # The autonomous threat can only be killed by interceptor/kinetic, so one must be fielded.
    fielded = {e.id for e in res.recommended.defense.effectors}
    assert fielded & {"interceptor_drone", "kinetic"}
    assert res.candidates_evaluated > 1
    assert res.recommended_result is not None


def test_recommendation_carries_a_sustainment_ledger():
    sc = load_scenario("layered_mix")
    res = solve(sc.swarm, sc.approach_distance, Requirement(max_p90_armed_leakers=3), _catalog(), runs=RUNS)
    consumable = [ln for ln in res.recommended_ledger if ln.consumable]
    assert consumable
    assert all(ln.waves_until_black is not None for ln in consumable)
    assert res.recommended.waves_until_black is not None


def test_is_deterministic():
    sc = load_scenario("layered_mix")
    req = Requirement(max_p90_armed_leakers=3)
    a = solve(sc.swarm, sc.approach_distance, req, _catalog(), runs=RUNS)
    b = solve(sc.swarm, sc.approach_distance, req, _catalog(), runs=RUNS)
    assert a.recommended is not None and b.recommended is not None
    assert a.recommended.label == b.recommended.label
    assert a.recommended.procurement_cost == b.recommended.procurement_cost


def test_frontier_is_pareto_monotonic():
    sc = load_scenario("layered_mix")
    res = solve(sc.swarm, sc.approach_distance, Requirement(max_p90_armed_leakers=3), _catalog(), runs=RUNS)
    f = res.frontier
    assert len(f) >= 2
    costs = [c.procurement_cost for c in f]
    leaks = [c.p90_armed_leakers for c in f]
    assert costs == sorted(costs)
    assert all(b < a for a, b in zip(leaks, leaks[1:]))


def test_infeasible_returns_best_achievable_and_gap():
    """An overwhelming wave: nothing in inventory holds it -> report the gap, not a bare false."""
    autonomous = load_threats(DEFAULT_SCENARIO_DIR / "threats.yaml")["autonomous"]
    swarm = [SwarmEntry(spec=autonomous, count=60)]
    res = solve(swarm, 60.0, Requirement(max_p90_armed_leakers=2), _catalog(), runs=30)
    assert not res.feasible
    assert res.recommended is None
    assert res.best_achievable is not None
    assert res.binding_gap is not None and res.binding_gap["delta"] > 0
