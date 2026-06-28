"""Phase 1: Monte Carlo aggregation + numeric validation of the canonical scenarios (§8, §9, §10)."""

from __future__ import annotations

from engine.montecarlo import run_montecarlo
from engine.simulation import simulate
from schema.loader import load_scenario

RUNS = 100


def _mc(name: str, runs: int = RUNS):
    return run_montecarlo(load_scenario(name), runs=runs)


def test_batch_is_deterministic():
    """Same scenario + N -> identical aggregate. Reproducible scaling (§4.3)."""
    a = _mc("layered_mix")
    b = _mc("layered_mix")
    assert a.model_dump_json() == b.model_dump_json()


def test_distribution_length_matches_runs():
    mc = _mc("layered_mix")
    assert len(mc.metrics.leakers_total.values) == RUNS


def test_representative_is_the_median_leaker_run():
    """The representative trace is the lower-median-leaker run, and its seed reproduces it (§5)."""
    mc = _mc("layered_mix")
    ordered = sorted(mc.metrics.leakers_total.values)
    lower_median = ordered[(len(ordered) - 1) // 2]

    rep = simulate(load_scenario("layered_mix").model_copy(update={"seed": mc.representative_seed}))
    assert rep.metrics.leakers_total == lower_median
    assert rep.trace.model_dump_json() == mc.representative.model_dump_json()


def test_all_ew_vs_autonomous_is_the_floor_case():
    """EW vs autonomous: every single run leaks everything, $0 spent (§9.1)."""
    mc = _mc("all_ew_vs_autonomous")
    total = load_scenario("all_ew_vs_autonomous")
    n_threats = sum(e.count for e in total.swarm)
    assert mc.metrics.leakers_total.min == mc.metrics.leakers_total.max == n_threats
    assert mc.metrics.defender_cost.max == 0


def test_kinetic_hits_the_cost_trap_and_runs_dry():
    """Kinetic vs mass+decoys: tens-to-one cost-exchange and the magazine empties (§9.2)."""
    mc = _mc("kinetic_vs_mass_and_decoys")
    assert mc.metrics.cost_exchange_ratio.median > 10
    kinetic = next(s for s in mc.magazine_timeline if s.effector_id == "kinetic")
    assert kinetic.dry_fraction > 0
    assert kinetic.mean_first_dry_tick is not None


def test_layered_beats_kinetic_on_cost_and_leakers():
    """The sustainable answer: layered improves both cost-exchange and armed leakers (§9.3)."""
    kinetic = _mc("kinetic_vs_mass_and_decoys")
    layered = _mc("layered_mix")
    assert layered.metrics.cost_exchange_ratio.median < kinetic.metrics.cost_exchange_ratio.median
    assert layered.metrics.leakers_armed.median < kinetic.metrics.leakers_armed.median


def test_attrition_curve_is_monotonic_nonincreasing():
    """Threats-alive can only fall over time within the averaged curve."""
    mc = _mc("layered_mix")
    means = [p.mean_alive for p in mc.attrition_curve]
    assert all(b <= a + 1e-9 for a, b in zip(means, means[1:]))
