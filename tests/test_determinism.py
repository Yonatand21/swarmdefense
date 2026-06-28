"""Phase 0 sanity: determinism and conservation (ARCHITECTURE_AND_PLAN.md §4.3, §10)."""

from __future__ import annotations

from engine.simulation import simulate
from schema.loader import load_scenario, load_scenarios


def test_same_seed_same_run():
    """Same seed -> byte-identical result. The determinism non-negotiable."""
    scenario = load_scenario("layered_mix")
    a = simulate(scenario)
    b = simulate(scenario)
    assert a.model_dump_json() == b.model_dump_json()


def test_every_threat_is_resolved():
    """Conservation: each threat ends up either defeated or leaked, exactly once."""
    for name, scenario in load_scenarios().items():
        result = simulate(scenario)
        m = result.metrics
        assert m.defeated + m.leakers_total == m.total_threats, name


def test_ew_is_useless_against_autonomous():
    """EW does nothing vs soft_kill_immune threats -> zero defeats, everything leaks (§9.1)."""
    result = simulate(load_scenario("all_ew_vs_autonomous"))
    m = result.metrics
    assert m.defeated == 0
    assert m.leakers_armed == m.total_threats
    assert m.defender_cost == 0  # EW shots are skipped entirely, so nothing is spent


def test_seed_override_changes_outcome_distribution():
    """Different seeds should generally produce different traces (probabilistic engine)."""
    base = load_scenario("kinetic_vs_mass_and_decoys")
    r0 = simulate(base.model_copy(update={"seed": 0}))
    r1 = simulate(base.model_copy(update={"seed": 1}))
    assert r0.trace.model_dump_json() != r1.trace.model_dump_json()
