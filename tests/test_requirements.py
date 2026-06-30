"""
Test suite for the Requirements Solver (inverse-design outer loop).

DESIGN SPINE
------------
solve() takes an INJECTABLE evaluator (same signature as run_montecarlo):

    solve(swarm, approach, requirement, catalog, *, inventory=..., evaluator=run_montecarlo)

Tiers 1-5 pass a SYNTHETIC evaluator with a hand-designed performance landscape, so the correct
answer is computable by hand and the tests are fast + deterministic. A red test there means "the
search is broken", never "the seed was unlucky".

Tiers 6-7 use the REAL engine (slow, marked) -- see also test_requirements_acceptance.py which
already exercises the real engine on the canonical picture.

The synthetic landscape: p90 armed leakers = max(0, threat - k * total_magazine). More magazine ->
fewer leakers (monotone). Procurement cost = sum(unit_cost * magazine) over consumable effectors.
This makes the optimum hand-computable and gives the Tier-2 invariants for free.
"""

import copy
import math

import pytest

from engine.models import EffectorSpec, SwarmEntry, ThreatSpec
from engine.requirements import (
    _RESEED_OFFSET,
    solve,
    system_waves_until_black,
    waves_until_black,
)
from schema.result import CandidatePosture, Requirement, SolverResult  # noqa: F401 (contract import)

THREAT = 30.0


# ============================================================================
# SYNTHETIC HARNESS (real engine shapes; the evaluator is faked, not the engine)
# ============================================================================


class FakeResult:
    """Duck-types MonteCarloResult for the flat fields the solver reads."""

    def __init__(self, p90, consumption, p50=None, cost_exchange_ratio=0.0, runs=1):
        self.p90_armed_leakers = p90
        self.p50_armed_leakers = p50 if p50 is not None else max(0.0, p90 - 1.0)
        self.cost_exchange_ratio = cost_exchange_ratio
        self.consumption_per_wave = consumption
        self.runs = runs


def make_swarm(count: int = 30) -> list[SwarmEntry]:
    spec = ThreatSpec(id="t", category="cheap_mass", cost=1000, speed=2.0, detection_range=30)
    return [SwarmEntry(spec=spec, count=count)] if count else []


def make_catalog(units: dict[str, float]) -> dict[str, EffectorSpec]:
    """Build a catalog of consumable effectors with the given per-round unit costs."""
    return {
        eid: EffectorSpec(
            id=eid, type="kinetic", cost_per_shot=cost, range=20, magazine=1, reload_time=1, p_kill=0.8
        )
        for eid, cost in units.items()
    }


def mags(*values: int) -> list:
    """Buy levels: 'not fielded' plus a magazine-depth option per value."""
    return [None] + [{"magazine": v} for v in values]


def _total_magazine(defense) -> float:
    return sum(e.magazine for e in defense.effectors)


def monotone_evaluator(threat: float = THREAT, k: float = 1.0):
    def evaluator(scenario, runs=1, base_seed=0):
        total = _total_magazine(scenario.defense)
        p90 = max(0.0, threat - k * total)
        fired = min(total, threat)
        n = len(scenario.defense.effectors)
        consumption = {e.id: (fired / n if n else 0.0) for e in scenario.defense.effectors}
        return FakeResult(p90, consumption, runs=runs)
    return evaluator


def _solve(inv, catalog, tol, *, evaluator=None, count=30, base_seed=0, reseed_check=False):
    return solve(
        make_swarm(count),
        60.0,
        Requirement(max_p90_armed_leakers=tol),
        catalog,
        inventory=inv,
        evaluator=evaluator or monotone_evaluator(),
        runs=1,
        base_seed=base_seed,
        reseed_check=reseed_check,
    )


# ============================================================================
# TIER 1 - SEARCH LOGIC
# ============================================================================


def test_finds_unique_optimum():
    """One cheapest-feasible posture exists; solver returns exactly it."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    # tol=2 -> need total >= 28. Cheapest is cheap@30 (cost 30); any mix is dearer.
    res = _solve(inv, catalog, tol=2)
    assert res.feasible
    assert res.recommended.procurement_cost == 30
    fielded = {e.id: e.magazine for e in res.recommended.defense.effectors}
    assert fielded == {"cheap": 30}


def test_cheapest_among_many_feasible():
    """Many postures clear the tolerance; solver returns MIN-cost, not first/most-protective."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    res = _solve(inv, catalog, tol=25)  # need total >= 5 -> cheap@10 (cost 10) is cheapest
    assert res.feasible
    assert res.recommended.procurement_cost == 10
    assert {e.id for e in res.recommended.defense.effectors} == {"cheap"}


def test_strict_boundary_rejected():
    """A cheaper posture that misses by epsilon is rejected (<= vs < at the constraint edge)."""
    catalog = make_catalog({"cheap": 0.5})  # cost = 0.5 * magazine

    def boundary_ev(scenario, runs=1, base_seed=0):
        total = _total_magazine(scenario.defense)
        p90 = 2.0 if total >= 20 else 2.01
        return FakeResult(p90, {e.id: 1.0 for e in scenario.defense.effectors}, runs=runs)

    inv = {"cheap": mags(18, 20)}  # cheap@18 -> cost 9, p90 2.01 (miss); cheap@20 -> cost 10, p90 2.0
    res = _solve(inv, catalog, tol=2, evaluator=boundary_ev)
    assert res.feasible
    assert res.recommended.procurement_cost == 10  # the cost-9 posture is correctly rejected


def test_deterministic_tie_break():
    """Two feasible postures at identical cost -> stable winner (lexicographic id), across reruns."""
    catalog = make_catalog({"cheap": 1.0, "twin": 1.0})
    inv = {"cheap": mags(30), "twin": mags(30)}  # cheap@30 and twin@30 tie at cost 30
    r1 = _solve(inv, catalog, tol=2)
    r2 = _solve(inv, catalog, tol=2)
    assert r1.recommended.id == r2.recommended.id
    assert r1.recommended.id.startswith("cheap")  # 'cheap' < 'twin'


def test_infeasible_returns_best_achievable():
    """Nothing clears tolerance -> feasible False, best_achievable = MIN-p90 posture, gap reported."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(10, 20)}  # max total 20 -> p90 10; tol 0 unreachable
    res = _solve(inv, catalog, tol=0)
    assert res.feasible is False
    assert res.recommended is None
    assert res.best_achievable.p90_armed_leakers == 10
    assert res.binding_gap["constraint"] == "p90_armed_leakers"
    assert res.binding_gap["delta"] == pytest.approx(10.0)


# ============================================================================
# TIER 2 - INVARIANTS
# ============================================================================


def test_monotone_in_tolerance():
    """Loosen the tolerance -> recommended cost can only stay equal or drop."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(10, 20, 30)}
    costs = [_solve(inv, catalog, tol=t).recommended.procurement_cost for t in (4, 12, 20)]
    assert costs[0] >= costs[1] >= costs[2]
    assert costs == [30, 20, 10]


def test_superset_inventory_never_hurts():
    """More allowed options -> recommended cost can only stay equal or drop."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv_a = {"cheap": mags(10, 20, 30)}
    inv_b = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    cost_a = _solve(inv_a, catalog, tol=2).recommended.procurement_cost
    cost_b = _solve(inv_b, catalog, tol=2).recommended.procurement_cost
    assert cost_b <= cost_a


def test_winner_is_non_dominated():
    """No FEASIBLE frontier point is cheaper than the recommendation."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    res = _solve(inv, catalog, tol=2)
    assert res.feasible
    for c in res.frontier:
        assert not (c.feasible and c.procurement_cost < res.recommended.procurement_cost)


def test_frontier_is_pareto():
    """Frontier is sorted by cost ascending with strictly decreasing leakers (no dominated point)."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    f = _solve(inv, catalog, tol=2).frontier
    costs = [c.procurement_cost for c in f]
    leaks = [c.p90_armed_leakers for c in f]
    assert costs == sorted(costs)
    assert all(b < a for a, b in zip(leaks, leaks[1:]))


# ============================================================================
# TIER 3 - THE LEDGER METRIC  (waves_until_black - the logistics race)
# ============================================================================


def test_waves_until_black_arithmetic():
    assert waves_until_black(20, 5) == 4


def test_waves_until_black_floor_convention():
    """magazine 20, consumption 7 -> 2.857 -> floor 2. Pin the convention."""
    assert waves_until_black(20, 7) == 2


def test_waves_until_black_binding_across_effectors():
    """System endurance is the MIN across effectors (whichever runs dry first ends you)."""
    ledger = {"interceptor": waves_until_black(15, 5), "ew": waves_until_black(100, 10)}
    assert system_waves_until_black(ledger) == 3


def test_waves_until_black_divide_by_zero_guard():
    assert waves_until_black(20, 0) == math.inf


def test_ledger_consumption_is_single_source_of_truth():
    """waves_until_black is derived from the SAME rounds/wave the ledger reports (no drift)."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(30)}
    res = _solve(inv, catalog, tol=2)
    assert res.recommended is not None
    for line in res.recommended_ledger:
        if line.consumable:
            assert line.waves_until_black == waves_until_black(line.magazine, line.rounds_per_wave)


# ============================================================================
# TIER 4 - DETERMINISM & ROBUSTNESS
# ============================================================================


def test_bit_identical_reruns():
    """Same inputs -> equal recommendation, frontier, and candidate count."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    r1 = _solve(inv, catalog, tol=2)
    r2 = _solve(inv, catalog, tol=2)
    assert r1.recommended.id == r2.recommended.id
    assert r1.recommended.procurement_cost == r2.recommended.procurement_cost
    assert [c.id for c in r1.frontier] == [c.id for c in r2.frontier]
    assert r1.candidates_evaluated == r2.candidates_evaluated


def test_provenance_candidate_count_matches_grid():
    """candidates_evaluated == product of buy-levels minus the all-'not-fielded' combo."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20), "exp": mags(10)}  # (3 levels) x (2 levels) = 6, minus empty = 5
    res = _solve(inv, catalog, tol=2)
    assert res.candidates_evaluated == 5


def test_robustness_flag_clear_when_comfortable():
    """A comfortably-feasible requirement is stable across seed bases -> flag clear."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(10, 20, 30)}
    # Deterministic evaluator (no seed dependence) -> reseed identical -> never flips.
    res = _solve(inv, catalog, tol=8, reseed_check=True)
    assert res.feasible
    assert res.robustness_flag is False


def test_robustness_flag_fires_on_knife_edge():
    """A requirement at the edge flips across seed bases -> flag set."""
    catalog = make_catalog({"cheap": 1.0})

    def edge_ev(scenario, runs=1, base_seed=0):
        # Feasible at the base seed (p90 == tol), infeasible on the reseed.
        p90 = 2.0 if base_seed == 0 else 3.0
        return FakeResult(p90, {e.id: 1.0 for e in scenario.defense.effectors}, runs=runs)

    inv = {"cheap": mags(30)}
    res = _solve(inv, catalog, tol=2, evaluator=edge_ev, reseed_check=True)
    assert res.feasible  # the base-seed verdict
    assert res.robustness_flag is True
    assert _RESEED_OFFSET > 0


def test_solve_does_not_mutate_inputs():
    """solve() must not mutate the swarm or the inventory."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    swarm = make_swarm(30)
    inv_before = copy.deepcopy(inv)
    swarm_before = copy.deepcopy(swarm)
    solve(swarm, 60.0, Requirement(max_p90_armed_leakers=2), catalog,
          inventory=inv, evaluator=monotone_evaluator(), runs=1)
    assert inv == inv_before
    assert swarm == swarm_before


# ============================================================================
# TIER 5 - DEGENERATE INPUTS
# ============================================================================


def test_empty_inventory():
    """Empty inventory -> no candidates -> typed error, never a silent wrong answer."""
    with pytest.raises(ValueError):
        _solve({}, make_catalog({"cheap": 1.0}), tol=2)


def test_single_candidate_inventory():
    """A forced single candidate is returned when feasible."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": [{"magazine": 30}]}  # no 'None' -> exactly one posture
    res = _solve(inv, catalog, tol=2)
    assert res.candidates_evaluated == 1
    assert res.feasible
    assert {e.id: e.magazine for e in res.recommended.defense.effectors} == {"cheap": 30}


def test_trivially_met_tolerance():
    """Huge tolerance -> the constraint never binds -> globally cheapest posture wins."""
    catalog = make_catalog({"cheap": 1.0, "exp": 5.0})
    inv = {"cheap": mags(10, 20, 30), "exp": mags(10, 20, 30)}
    res = _solve(inv, catalog, tol=1000)
    assert res.feasible
    assert res.recommended.procurement_cost == 10  # cheap@10 is the globally cheapest


def test_impossible_tolerance():
    """Tolerance 0 against a leaky landscape -> infeasible, best_achievable = min-leak posture."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(10, 20)}
    res = _solve(inv, catalog, tol=0)
    assert res.feasible is False
    assert res.best_achievable.p90_armed_leakers == 10


def test_zero_swarm():
    """No inbounds -> 0 leakers; cheapest posture; ledger survives zero consumption (no crash)."""
    catalog = make_catalog({"cheap": 1.0})
    inv = {"cheap": mags(10, 20, 30)}
    res = _solve(inv, catalog, tol=2, evaluator=monotone_evaluator(threat=0.0), count=0)
    assert res.feasible
    assert res.recommended.p90_armed_leakers == 0
    # Zero consumption -> the layer never runs dry. The contract represents "never dry" as None
    # (inf is not valid JSON for the API); the pure helper still returns inf (pinned in Tier 3).
    assert res.recommended.waves_until_black is None
    assert all(ln.waves_until_black is None for ln in res.recommended_ledger)
    assert waves_until_black(10, 0) == math.inf


# ============================================================================
# TIER 6 - ACCEPTANCE / THESIS  (REAL engine - covered in test_requirements_acceptance.py)
# ============================================================================
# Pre-registration discipline: the inventory + grid are committed BEFORE these run.


@pytest.mark.integration
@pytest.mark.slow
def test_rediscovery_as_property_not_equality():
    """Solver meets the canonical tolerance at cost <= the hand-tuned layered_mix (see acceptance)."""
    pytest.skip("covered by test_requirements_acceptance.py at production run count")


@pytest.mark.integration
@pytest.mark.slow
def test_soft_kill_stripped_shifts_posture():
    """EW useless vs the autonomous fraction -> spend shifts to kinetic (thesis mechanism)."""
    pytest.skip("real-engine narrative test; not part of the fast spine")


# ============================================================================
# TIER 7 - STATISTICAL FOUNDATION  (REAL engine - run deliberately)
# ============================================================================


@pytest.mark.integration
@pytest.mark.slow
def test_verdict_stable_under_reseed():
    """A comfortably-feasible requirement holds feasible across ~10 seed bases at production runs."""
    pytest.skip("slow real-engine reseed sweep; run deliberately before a demo")
