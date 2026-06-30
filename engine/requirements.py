"""Requirements solver -- inverse design (docs/PROPOSAL_requirements_solver.md).

Given a threat picture and a required outcome, search a PRE-REGISTERED space of procurable postures
and return the cheapest one that meets the requirement, framed as a logistics ledger
(waves-until-black). This is a pure outer loop: it builds Scenarios and calls run_montecarlo. It does
NOT touch the simulation.

Single-stage brute force over a small committed grid (no cheap-rank-then-confirm). One objective:
minimize procurement cost subject to the protection tolerance.
"""

from __future__ import annotations

import itertools
import math
from typing import Callable, Optional

from engine.models import (
    DefenseSpec,
    EffectorSpec,
    Environment,
    Scenario,
    SensorSpec,
    SwarmEntry,
)
from engine.montecarlo import DEFAULT_RUNS, run_montecarlo
from schema.result import MonteCarloResult
from schema.solver import (
    CandidatePosture,
    LedgerLine,
    Requirement,
    SolverResult,
)

# An evaluator has run_montecarlo's signature: evaluator(scenario, runs, base_seed) -> result.
# Injectable so the search can be tested against a synthetic, hand-computable performance landscape
# (fast + deterministic) without invoking the real engine. The result need only expose the flat
# read-accessors the solver uses (p90_armed_leakers, cost_exchange_ratio, consumption_per_wave).
Evaluator = Callable[..., object]


def waves_until_black(magazine_depth: float, consumption_per_wave: float) -> float:
    """How many full waves a magazine sustains before depletion (the logistics-race metric).

    Floor convention: you survive N full waves and deplete mid-(N+1); the honest planning number is
    the floor. Zero expected consumption -> inf (this layer never runs dry), never a divide error.
    """
    if consumption_per_wave <= 0:
        return math.inf
    return math.floor(magazine_depth / consumption_per_wave)


def system_waves_until_black(ledger: dict[str, float]) -> float:
    """System endurance is the MIN across effectors -- whichever layer runs dry first ends you."""
    return min(ledger.values()) if ledger else math.inf

# --------------------------------------------------------------------------------------------------
# PRE-REGISTERED decision space (committed before looking at layered_mix; see proposal §4).
# Each effector has buy levels; None = not fielded. Levels are overrides onto the catalog archetype.
# The reservation trick (per-category `engages`) is deliberately NOT a decision variable in v1.
# --------------------------------------------------------------------------------------------------

# An Inventory maps an effector id -> the buy levels the search may field (None = not fielded).
# Each non-None level is an override dict applied to the catalog archetype.
Inventory = dict[str, list[Optional[dict]]]

GRID: Inventory = {
    "ew": [None, {"max_simultaneous": 4}, {"max_simultaneous": 8}],
    "directed_energy": [None, {"max_simultaneous": 2}, {"max_simultaneous": 4}],
    "interceptor_drone": [
        None,
        {"magazine": 8, "max_simultaneous": 2},
        {"magazine": 16, "max_simultaneous": 3},
        {"magazine": 24, "max_simultaneous": 4},
    ],
    "kinetic": [
        None,
        {"magazine": 8, "max_simultaneous": 1},
        {"magazine": 16, "max_simultaneous": 2},
        {"magazine": 24, "max_simultaneous": 3},
    ],
}

DEFAULT_SENSOR = SensorSpec(p_track=0.95, p_identify=0.85)

# Seed offset for the reseed robustness check -- larger than any plausible run count so the two
# seeded Monte Carlo batches do not overlap.
_RESEED_OFFSET = 1_000_000


def is_consumable(spec: EffectorSpec) -> bool:
    """A munition you must restock (finite magazine that depletes), vs a reusable platform."""
    return spec.reload_time > 0


def procurement_cost(effectors: list[EffectorSpec]) -> float:
    """Cost to stock the consumable rounds. Reusable platforms (EW/DE) carry no per-round cost (v1)."""
    return sum(e.magazine * e.cost_per_shot for e in effectors if is_consumable(e))


def solve(
    swarm: list[SwarmEntry],
    approach_distance: float,
    requirement: Requirement,
    effector_catalog: dict[str, EffectorSpec],
    *,
    base_seed: int = 0,
    runs: int = DEFAULT_RUNS,
    environment: Optional[Environment] = None,
    sensor: Optional[SensorSpec] = None,
    evaluator: Evaluator = run_montecarlo,
    inventory: Optional[Inventory] = None,
    reseed_check: bool = True,
) -> SolverResult:
    env = environment or Environment()
    sns = sensor or DEFAULT_SENSOR
    inv = inventory if inventory is not None else GRID
    tol = requirement.max_p90_armed_leakers

    def evaluate(effectors: list[EffectorSpec], seed: int):
        scenario = Scenario(
            name="candidate",
            seed=seed,
            approach_distance=approach_distance,
            swarm=swarm,
            defense=DefenseSpec(sensor=sns, effectors=effectors),
            environment=env,
        )
        return evaluator(scenario, runs=runs, base_seed=seed)

    candidates: list[CandidatePosture] = []
    posture_effectors: dict[str, list[EffectorSpec]] = {}
    for effectors in _enumerate_postures(effector_catalog, inv):
        cand = _summarize(effectors, evaluate(effectors, base_seed), requirement)
        candidates.append(cand)
        posture_effectors[cand.id] = effectors

    if not candidates:
        raise ValueError("Inventory produced no candidate postures.")

    feasible = [c for c in candidates if c.feasible]
    recommended = (
        min(feasible, key=lambda c: (c.procurement_cost, c.p90_armed_leakers, c.id))
        if feasible
        else None
    )
    best_achievable = min(candidates, key=lambda c: (c.p90_armed_leakers, c.procurement_cost, c.id))

    binding_gap = (
        None
        if recommended is not None
        else {"constraint": "p90_armed_leakers", "delta": best_achievable.p90_armed_leakers - tol}
    )

    recommended_result = None
    recommended_ledger: list[LedgerLine] = []
    robustness_flag = False
    if recommended is not None:
        effectors = posture_effectors[recommended.id]
        rec_eval = evaluate(effectors, base_seed)
        recommended_ledger = _ledger(effectors, rec_eval)
        # The contract embeds the full MC artifact (for replay/dashboard). A synthetic evaluator
        # returns a duck-typed result that the solver reads but does not embed; store None then.
        recommended_result = rec_eval if isinstance(rec_eval, MonteCarloResult) else None
        if reseed_check:
            reseed = evaluate(effectors, base_seed + _RESEED_OFFSET)
            robustness_flag = reseed.p90_armed_leakers > tol
    elif reseed_check:
        reseed = evaluate(posture_effectors[best_achievable.id], base_seed + _RESEED_OFFSET)
        robustness_flag = reseed.p90_armed_leakers <= tol

    return SolverResult(
        requirement=requirement,
        feasible=recommended is not None,
        recommended=recommended,
        recommended_result=recommended_result,
        recommended_ledger=recommended_ledger,
        best_achievable=best_achievable,
        binding_gap=binding_gap,
        robustness_flag=robustness_flag,
        frontier=_pareto(candidates),
        candidates_evaluated=len(candidates),
        base_seed=base_seed,
        runs=runs,
    )


def _enumerate_postures(
    catalog: dict[str, EffectorSpec], inventory: Inventory
) -> list[list[EffectorSpec]]:
    """Expand the inventory into concrete effector loadouts (skipping the empty posture)."""
    ids = [eid for eid in inventory if eid in catalog]
    postures: list[list[EffectorSpec]] = []
    for combo in itertools.product(*(inventory[eid] for eid in ids)):
        effectors: list[EffectorSpec] = []
        for eid, override in zip(ids, combo):
            if override is None:
                continue
            base = catalog[eid]
            effectors.append(EffectorSpec(**{**base.model_dump(), **override}))
        if effectors:
            postures.append(effectors)
    return postures


def _label(effectors: list[EffectorSpec]) -> str:
    return " + ".join(f"{e.id}(mag{e.magazine},x{e.max_simultaneous})" for e in effectors)


def _summarize(effectors, mc, requirement: Requirement) -> CandidatePosture:
    p90_armed = mc.p90_armed_leakers
    ledger = _ledger(effectors, mc)
    finite = {
        ln.effector_id: ln.waves_until_black
        for ln in ledger
        if ln.consumable and ln.waves_until_black is not None
    }
    system = system_waves_until_black(finite) if finite else None
    label = _label(effectors)
    return CandidatePosture(
        id=label,
        label=label,
        defense=DefenseSpec(sensor=DEFAULT_SENSOR, effectors=effectors),
        procurement_cost=procurement_cost(effectors),
        feasible=p90_armed <= requirement.max_p90_armed_leakers,
        p90_armed_leakers=p90_armed,
        cost_exchange_median=mc.cost_exchange_ratio,
        waves_until_black=system,
    )


def _ledger(effectors: list[EffectorSpec], mc) -> list[LedgerLine]:
    consumption = mc.consumption_per_wave
    lines: list[LedgerLine] = []
    for e in effectors:
        rounds = consumption.get(e.id, 0.0)
        consumable = is_consumable(e)
        wub: Optional[float] = None
        if consumable:
            raw = waves_until_black(e.magazine, rounds)
            wub = None if raw == math.inf else raw  # None = never runs dry (keeps JSON valid)
        lines.append(
            LedgerLine(
                effector_id=e.id,
                consumable=consumable,
                rounds_per_wave=rounds,
                magazine=e.magazine,
                waves_until_black=wub,
            )
        )
    return lines


def _pareto(candidates: list[CandidatePosture]) -> list[CandidatePosture]:
    """Pareto frontier: cheaper procurement should buy fewer leakers. Sorted by cost ascending."""
    ordered = sorted(candidates, key=lambda c: (c.procurement_cost, c.p90_armed_leakers))
    frontier: list[CandidatePosture] = []
    best_leak = float("inf")
    for c in ordered:
        if c.p90_armed_leakers < best_leak:
            frontier.append(c)
            best_leak = c.p90_armed_leakers
    return frontier
