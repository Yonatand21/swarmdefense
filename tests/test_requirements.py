"""
tests/test_requirements.py

Test suite for the Requirements Solver (inverse-design outer loop).

DESIGN SPINE
------------
The solver takes an *injectable* evaluator:

    solve(swarm, inventory, requirement, objective, evaluator=run_montecarlo) -> SolverResult

Tiers 1-5 pass a SYNTHETIC evaluator with a hand-designed performance landscape,
so the correct answer is computable by hand and tests are fast + deterministic.
A red test there means "the search is broken" - never "the seed was unlucky."

Tiers 6-7 use the REAL engine. They are slow, marked, and run as a deliberate
handful. They validate the demo narrative and the statistical floor (is 500
runs enough to make the feasibility call stable).

STATUS: skeleton. Targets the API proposed in docs/PROPOSAL_requirements_solver.md.
The fast tests below encode real assertions and will run green once
`engine/requirements.py` + the schema additions exist with the contract below.

============================================================================
ASSUMED CONTRACT  (reconcile every name here against schema/result.py once locked)
============================================================================

MonteCarloResult (what the evaluator returns; solver only READS these):
    .p50_armed_leakers : float
    .p90_armed_leakers : float
    .leak_fraction     : float
    .cost_exchange_ratio : float
    .consumption_per_wave : dict[str, float]   # effector_id -> interceptors spent / wave
    .runs : int

CandidatePosture (a posture IS a Scenario.defense):
    .effectors : dict[str, EffectorConfig]      # EffectorConfig: .magazine_depth, .max_simultaneous,
                                                #   .unit_cost, .reserved_for (str | None)
    .procurement_cost : float                   # STRUCTURAL: sum(unit_cost * magazine_depth) (+ fixed)
    .id : str                                   # stable identifier for tie-breaks / frontier

Requirement:
    .max_p90_armed_leakers : float
    .max_cost_exchange     : float | None
    .max_procurement_cost  : float | None

SolverResult:
    .feasible            : bool
    .recommended         : CandidatePosture | None
    .recommended_result  : MonteCarloResult | None
    .best_achievable     : CandidatePosture            # ALWAYS set (== recommended when feasible)
    .binding_gap         : dict                          # {"constraint": str, "delta": float} when infeasible
    .frontier            : list[FrontierPoint]           # FrontierPoint: .posture, .result, .feasible
    .provenance          : Provenance                    # .catalog_version, .engine_version,
                                                        #   .base_seed, .runs, .candidates_evaluated
    .robustness_flag     : bool                          # True => verdict flipped on reseed (knife-edge)
    .ledger              : Ledger                         # .waves_until_black: dict[str,int]; .system: int

Engine helpers (logistics ledger):
    waves_until_black(magazine_depth: float, consumption_per_wave: float) -> int
    system_waves_until_black(ledger: dict[str, int]) -> int        # min across effectors

Scenario (built internally by solve, passed to evaluator):
    .swarm     (the threat picture)
    .defense   (the CandidatePosture)
============================================================================
"""

import math
import random
from dataclasses import dataclass, field

import pytest

# --- System under test (will exist once the spine is built) ------------------
from engine.requirements import (
    solve,
    waves_until_black,
    system_waves_until_black,
)
from schema.result import (
    Requirement,
    CandidatePosture,
    SolverResult,
)

# Objectives are strings/enums in the proposal; v1 ships minimize_cost only.
MINIMIZE_COST = "minimize_cost"


# ============================================================================
# SYNTHETIC EVALUATOR FIXTURES  (the spine - test the search, not the engine)
# ============================================================================
#
# An evaluator has the SAME signature as run_montecarlo:
#     evaluator(scenario, runs, base_seed) -> MonteCarloResult-like
# It reads scenario.defense (the posture) and scenario.swarm (the threat) and
# returns a performance result. Procurement COST is structural (on the posture),
# NOT returned here - the solver ranks minimize_cost by posture.procurement_cost
# among postures whose performance clears the requirement.

@dataclass
class FakeResult:
    """Duck-types MonteCarloResult for the fields the solver reads.

    If schema/result.py renames a field, change it HERE in one place.
    """
    p50_armed_leakers: float
    p90_armed_leakers: float
    leak_fraction: float
    cost_exchange_ratio: float
    consumption_per_wave: dict
    runs: int = 500


def make_evaluator(perf_fn, jitter: float = 0.0):
    """Build a synthetic evaluator from a hand-designed performance function.

    perf_fn(swarm, posture) -> (p90, p50, cost_exchange, consumption_per_wave_dict)

    `jitter`: deterministic, seed-dependent perturbation added to p90 to simulate
    Monte-Carlo noise. Used only by the robustness / reseed-stability tests; keep
    it 0.0 everywhere else so the synthetic landscape stays exact.
    """
    def evaluator(scenario, runs=500, base_seed=0):
        posture = scenario.defense
        swarm = scenario.swarm
        p90, p50, cx, consumption = perf_fn(swarm, posture)
        if jitter:
            # Deterministic per-seed wobble in [-jitter, +jitter].
            rng = random.Random((base_seed, posture.id))
            p90 = max(0.0, p90 + rng.uniform(-jitter, jitter))
        leak_fraction = p90 / max(1, _swarm_size(swarm))
        return FakeResult(p50, p90, leak_fraction, cx, consumption, runs)
    return evaluator


def _swarm_size(swarm) -> int:
    """Total inbound count from the threat picture. Reconcile with Scenario.swarm."""
    # TODO: replace with the real swarm-size accessor once Scenario.swarm is locked.
    return getattr(swarm, "total_count", 0)


def _total_effective_magazine(posture) -> float:
    """Sum of magazine depths across the posture's effectors."""
    return sum(cfg.magazine_depth for cfg in posture.effectors.values())


# -- A monotone landscape: more magazine -> fewer leakers. Hand-computable, and
#    gives the Tier-2 invariants (monotone-in-tolerance, superset-never-hurts) for free.
def monotone_perf(threat: float, k: float = 1.0):
    """Return a perf_fn where p90 leakers = max(0, threat - k * total_magazine)."""
    def perf_fn(swarm, posture):
        mag = _total_effective_magazine(posture)
        p90 = max(0.0, threat - k * mag)
        p50 = max(0.0, p90 - 1.0)  # p50 a touch below p90, kept non-negative
        cx = posture.procurement_cost / max(1.0, threat)  # toy cost-exchange
        # Consumption: split expended interceptors across effectors that fired.
        fired = min(threat, k * mag)
        per = {eid: fired / len(posture.effectors) for eid in posture.effectors}
        return p90, p50, cx, per
    return perf_fn


# ----------------------------------------------------------------------------
# Posture / inventory / scenario builders for synthetic tests.
# Thin wrappers so tests read cleanly; reconcile constructors with the real schema.
# ----------------------------------------------------------------------------
@dataclass
class _Eff:
    magazine_depth: float
    unit_cost: float
    max_simultaneous: int = 4
    reserved_for: str | None = None


def make_posture(pid: str, effectors: dict[str, _Eff]) -> CandidatePosture:
    """Construct a CandidatePosture with derived procurement_cost.

    TODO: route through the real CandidatePosture constructor once it lands;
    for now this documents the shape the solver must produce.
    """
    procurement = sum(e.unit_cost * e.magazine_depth for e in effectors.values())
    return CandidatePosture(id=pid, effectors=effectors, procurement_cost=procurement)


def make_inventory(allowed: dict, magazine_steps: list[int]):
    """The procurable space: which effectors are allowed and the legal knob ranges.

    `allowed`: effector_id -> (unit_cost, max_simultaneous, reserved_for|None)
    `magazine_steps`: discrete magazine depths the search may choose per effector.
    Reconcile with the real Inventory type.
    """
    raise NotImplementedError("wire to schema Inventory")  # filled when schema lands


@pytest.fixture
def tiny_swarm():
    """A 30-inbound threat picture. Reconcile with Scenario.swarm constructor."""
    raise NotImplementedError("wire to schema Scenario.swarm")


# ============================================================================
# TIER 1 - SEARCH LOGIC  (synthetic evaluator, fast, the majority of the suite)
# ============================================================================

def test_finds_unique_optimum():
    """One cheapest-feasible posture exists; solver returns exactly it.

    Build an inventory whose grid yields a single posture with min procurement_cost
    among those clearing the tolerance. Assert solve(...).recommended.id == that id.
    """
    # ev = make_evaluator(monotone_perf(threat=30, k=1.0))
    # result = solve(swarm, inventory, Requirement(max_p90_armed_leakers=2),
    #                MINIMIZE_COST, evaluator=ev)
    # assert result.feasible
    # assert result.recommended.id == "<hand-computed cheapest feasible id>"
    pytest.skip("fill once inventory/scenario constructors are wired")


def test_cheapest_among_many_feasible():
    """Several postures clear the tolerance; solver must return MIN-cost.

    Guards against 'returns first-found' or 'returns most-protective'.
    Assert recommended.procurement_cost == min over the feasible set.
    """
    pytest.skip("fill once constructors are wired")


def test_strict_boundary_rejected():
    """A cheaper posture that misses by epsilon (p90=2.01 vs tol=2.0) is rejected.

    Catches <= vs < and float-comparison sloppiness at the constraint edge.
    Engineer two postures: one at p90=2.0 (cost 10), one at p90=2.01 (cost 9).
    Assert the cost-9 posture is NOT recommended; the cost-10 one is.
    """
    pytest.skip("fill once constructors are wired")


def test_deterministic_tie_break():
    """Two feasible postures at identical procurement_cost -> stable winner.

    Define the rule (more protective, then lexicographic id) and assert the SAME
    winner across repeated solve() calls. Catches dict/set-ordering nondeterminism.
    """
    # r1 = solve(...); r2 = solve(...)
    # assert r1.recommended.id == r2.recommended.id
    pytest.skip("fill once constructors are wired")


def test_infeasible_returns_best_achievable():
    """Nothing clears tolerance -> feasible=False, best_achievable = MIN-p90 posture.

    best_achievable is the CLOSEST MISS (min leakers), NOT the cheapest posture.
    binding_gap reports the right delta (best p90 - tolerance).
    """
    # result = solve(swarm, inventory, Requirement(max_p90_armed_leakers=0),
    #                MINIMIZE_COST, evaluator=ev)
    # assert result.feasible is False
    # assert result.best_achievable.id == "<min-p90 posture id>"
    # assert result.binding_gap["constraint"] == "p90_armed_leakers"
    # assert result.binding_gap["delta"] == pytest.approx(<best_p90 - 0>)
    pytest.skip("fill once constructors are wired")


# ============================================================================
# TIER 2 - INVARIANTS  (synthetic; ideal for fuzzing over random landscapes)
# ============================================================================
# These hold for ANY landscape, so generate many and assert. (hypothesis would be
# a cleaner driver than the hand-rolled loop below - note it as an optional dep.)

def _random_inventory_and_swarm(seed: int):
    """Generate a random-but-valid (swarm, inventory) pair for fuzzing."""
    pytest.skip("fill: random effector costs, magazine steps, threat size")


def test_winner_is_non_dominated():
    """No evaluated posture is BOTH cheaper AND feasible than the recommendation.

    The core correctness property. Checkable post-hoc against result.frontier.
    Loop over ~100 random landscapes; for each, assert no frontier point dominates
    the winner on (cost down, feasible).
    """
    # for seed in range(100):
    #     swarm, inventory = _random_inventory_and_swarm(seed)
    #     r = solve(swarm, inventory, req, MINIMIZE_COST, evaluator=ev)
    #     if r.feasible:
    #         for fp in r.frontier:
    #             assert not (fp.feasible and
    #                         fp.posture.procurement_cost < r.recommended.procurement_cost)
    pytest.skip("fill once fuzz generator is wired")


def test_frontier_is_pareto():
    """No frontier point is strictly worse on BOTH cost and protection than another.

    Catches a 'frontier' that's just whatever postures we happened to evaluate.
    """
    pytest.skip("fill once fuzz generator is wired")


def test_monotone_in_tolerance():
    """Loosen tolerance -> recommended cost <= tighter case; tighten -> >=.

    Strong, cheap property catching a whole class of search bugs.
    Solve the same landscape at tol in [1, 2, 4]; assert recommended costs are
    non-increasing as tolerance loosens.
    """
    # costs = [solve(swarm, inv, Requirement(max_p90_armed_leakers=t),
    #                MINIMIZE_COST, evaluator=ev).recommended.procurement_cost
    #          for t in (1, 2, 4)]
    # assert costs[0] >= costs[1] >= costs[2]
    pytest.skip("fill once constructors are wired")


def test_superset_inventory_never_hurts():
    """More allowed options -> recommended cost can only stay equal or drop.

    The old optimum is still in the larger space. If adding an option RAISES cost,
    the search is skipping candidates. Solve with inventory A and A + {extra};
    assert cost(A + extra) <= cost(A).
    """
    pytest.skip("fill once constructors are wired")


# ============================================================================
# TIER 3 - THE LEDGER METRIC  (waves_until_black - the logistics race)
# ============================================================================

def test_waves_until_black_arithmetic():
    """magazine 20, consumption/wave 5 -> 4. Hand-checked."""
    assert waves_until_black(20, 5) == 4


def test_waves_until_black_floor_convention():
    """magazine 20, consumption 7 -> 2.857 -> floor 2.

    You survive 2 full waves and deplete mid-third; the honest planning number
    is floor. Pin the convention.
    """
    assert waves_until_black(20, 7) == 2


def test_waves_until_black_binding_across_effectors():
    """System endurance is the MIN across effectors, not avg or sum.

    Interceptors last 3 waves, EW lasts 10 -> system answer is 3 (whichever runs
    dry first ends you).
    """
    ledger = {"interceptor": waves_until_black(15, 5),   # 3
              "ew": waves_until_black(100, 10)}          # 10
    assert system_waves_until_black(ledger) == 3


def test_waves_until_black_divide_by_zero_guard():
    """Zero expected consumption -> sentinel (inf), never a crash.

    Pick the sentinel convention (inf chosen here) and pin it.
    """
    assert waves_until_black(20, 0) == math.inf


def test_ledger_consumption_is_single_source_of_truth():
    """The per-wave consumption feeding the ledger == the value feeding cost-exchange.

    Catches silent drift between the two headline numbers. Assert the ledger's
    consumption-per-wave equals the result's consumption_per_wave used for
    cost_exchange_ratio (same dict, not recomputed).
    """
    pytest.skip("fill: assert result.ledger draws from result.consumption_per_wave")


# ============================================================================
# TIER 4 - DETERMINISM & PROVENANCE
# ============================================================================

def test_bit_identical_reruns():
    """Same inputs + same base seed -> equal SolverResult (modulo timestamp).

    Run solve() twice; assert recommended.id, cost, frontier ids, and ledger equal.
    """
    pytest.skip("fill once constructors are wired")


def test_provenance_candidate_count_matches_grid():
    """candidates_evaluated == cartesian product of knob ranges minus pruned-illegal.

    Catches a grid generator silently skipping combinations. Compute the expected
    count by hand from the inventory and assert equality. Also assert catalog/engine
    version, base_seed, runs are all populated.
    """
    pytest.skip("fill once Inventory + Provenance are wired")


def test_robustness_flag_clear_when_comfortable():
    """A comfortably-feasible requirement is STABLE across seed bases -> flag clear.

    Use make_evaluator(..., jitter=small); a generous tolerance should not flip.
    """
    # ev = make_evaluator(monotone_perf(threat=30, k=1.0), jitter=0.3)
    # r = solve(swarm, inv, Requirement(max_p90_armed_leakers=8), MINIMIZE_COST, evaluator=ev)
    # assert r.robustness_flag is False
    pytest.skip("fill once constructors are wired")


def test_robustness_flag_fires_on_knife_edge():
    """A requirement set right at the edge FLIPS across seed bases -> flag set.

    The flip case people forget to construct; it's the only thing that proves the
    flag works. Tolerance pinned exactly where jitter pushes p90 over/under.
    """
    # ev = make_evaluator(monotone_perf(threat=30, k=1.0), jitter=0.5)
    # r = solve(swarm, inv, Requirement(max_p90_armed_leakers=<edge>), MINIMIZE_COST, evaluator=ev)
    # assert r.robustness_flag is True
    pytest.skip("fill once constructors are wired")


def test_solve_does_not_mutate_inputs():
    """solve() must not mutate swarm / inventory / requirement.

    Catches aliasing where a candidate posture shares a reference with the inventory.
    Snapshot inputs (deepcopy or recorded fields), run solve() twice, assert the
    originals are unchanged.
    """
    pytest.skip("fill once constructors are wired")


# ============================================================================
# TIER 5 - DEGENERATE INPUTS  (synthetic)
# ============================================================================

def test_empty_inventory():
    """Empty inventory -> clean infeasible with empty frontier OR typed error. Never a crash."""
    pytest.skip("fill once constructors are wired")


def test_single_candidate_inventory():
    """One candidate -> returns it if feasible, else infeasible with it as best_achievable."""
    pytest.skip("fill once constructors are wired")


def test_trivially_met_tolerance():
    """Huge tolerance -> returns the globally cheapest posture (constraint never binds)."""
    pytest.skip("fill once constructors are wired")


def test_impossible_tolerance():
    """Tolerance 0 against a leaky kill-chain -> infeasible, best_achievable = min-leak posture."""
    pytest.skip("fill once constructors are wired")


def test_zero_swarm():
    """No inbounds -> all postures 0 leakers; returns cheapest; ledger handles no-consumption.

    Asserts cost-exchange and waves_until_black survive the divide-by-zero path.
    """
    pytest.skip("fill once constructors are wired")


# ============================================================================
# TIER 6 - ACCEPTANCE / THESIS  (REAL engine - slow, run a handful)
# ============================================================================
# Pre-registration discipline: the inventory + grid are committed BEFORE these run.
# Register the markers in conftest.py / pyproject:  slow, integration.

@pytest.mark.integration
@pytest.mark.slow
def test_rediscovery_as_property_not_equality():
    """Solver returns a posture meeting the canonical tolerance at cost <= layered_mix.

    Do NOT assert == layered_mix - exact equality bakes in the circularity we're
    avoiding. 'Cheaper than the hand-tune' is a STRONGER pass than 'agrees with it'.
    """
    # from engine.simulation import run_montecarlo
    # r = solve(canonical_swarm, committed_inventory, canonical_requirement, MINIMIZE_COST,
    #           evaluator=run_montecarlo)
    # assert r.feasible
    # assert r.recommended.procurement_cost <= LAYERED_MIX_COST
    pytest.skip("requires built engine + committed catalog/grid")


@pytest.mark.integration
@pytest.mark.slow
def test_kinetic_only_infeasible():
    """Restrict inventory to kinetic interceptors vs the canonical picture -> infeasible + gap.

    Criterion 2, end to end. Assert feasible is False and binding_gap is populated.
    """
    pytest.skip("requires built engine + committed catalog")


@pytest.mark.integration
@pytest.mark.slow
def test_soft_kill_stripped_shifts_posture():
    """EW made useless vs the autonomous fraction (immunity flag) -> spend shifts to kinetic.

    Tests that the solver RESPONDS to a kill-chain structural change - the thesis
    mechanism, not just arithmetic. Assert the recommended posture allocates more
    kinetic to the autonomous fraction (or goes infeasible) vs the EW-effective run.
    """
    pytest.skip("requires built engine")


# ============================================================================
# TIER 7 - STATISTICAL FOUNDATION  (REAL engine - two careful tests)
# ============================================================================
# The question the tool's credibility rests on: is 500 runs enough to make the
# feasibility call stable? If verdict-stability fails on a clear pass, RAISE the
# run count BEFORE the demo - don't discover it on camera.

@pytest.mark.integration
@pytest.mark.slow
def test_p90_estimator_accuracy():
    """Solver's p90 lands within CI of a KNOWN true p90 at the chosen run count.

    Inject a synthetic evaluator drawing from a known leak distribution (so the
    true p90 is analytic), run at production run count, assert |est - true| < CI.
    """
    pytest.skip("fill: known-distribution evaluator + CI bound")


@pytest.mark.integration
@pytest.mark.slow
def test_verdict_stable_under_reseed():
    """A comfortably-feasible requirement holds feasible across ~10 seed bases.

    If it flips on something that should clearly pass, the run count is too low.
    Loop base_seed over 10 values; assert all 10 verdicts agree.
    """
    # verdicts = [solve(swarm, inv, comfortable_req, MINIMIZE_COST,
    #                   evaluator=run_montecarlo, base_seed=s).feasible
    #             for s in range(10)]
    # assert all(verdicts) or not any(verdicts)
    pytest.skip("requires built engine")
