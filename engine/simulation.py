"""The simulation core -- the discrete-time engagement loop (ARCHITECTURE_AND_PLAN.md §7).

This is the single authoritative source of simulation logic. It consumes a `Scenario` and emits a
`Result` (the contract). It performs no I/O and knows nothing about how its output is rendered.
"""

from __future__ import annotations

from engine.assignment import assign
from engine.models import (
    EffectorState,
    Scenario,
    ThreatState,
)
from engine.rng import SeededRng
from schema.result import (
    Frame,
    Metrics,
    Result,
    RunTrace,
    ShotRecord,
    ThreatFrame,
)

# Hard ceiling so a misconfigured scenario can never loop forever. Threats always close on the
# asset, so a correct scenario terminates well before this.
_MAX_TICKS = 100_000


def simulate(scenario: Scenario) -> Result:
    """Run one deterministic engagement and return the emitted Result artifact."""
    rng = SeededRng(scenario.seed)
    sensor = scenario.defense.sensor
    det_mod = scenario.environment.detection_modifier

    threats = _spawn_threats(scenario)
    effectors = [
        EffectorState(spec=spec, ammo=spec.magazine) for spec in scenario.defense.effectors
    ]

    attacker_cost = sum(t.spec.cost for t in threats)
    defender_cost = 0.0
    shots_fired = 0
    defeated = 0
    leakers_armed = 0
    leakers_decoy = 0
    damage_to_asset = 0.0

    frames: list[Frame] = []
    tick = 0

    while _active(threats) and tick < _MAX_TICKS:
        tick += 1
        for eff in effectors:
            eff.begin_tick()

        # 1. Move
        for t in threats:
            if t.alive and not t.leaked:
                t.position = max(0.0, t.position - t.spec.speed)

        # 2. Detect (hard range gate; once tracked, stays tracked as it only closes)
        for t in threats:
            if t.alive and not t.leaked and not t.tracked:
                if t.position <= t.spec.detection_range * det_mod:
                    t.tracked = True

        tracked = [t for t in threats if t.tracked and t.alive and not t.leaked]

        # 3. Assign
        assignments = assign(effectors, tracked)

        # 4. Engage -- roll the remaining kill-chain stack: p_track * p_identify * p_kill
        shots: list[ShotRecord] = []
        kills: list[int] = []
        for eff, target in assignments:
            if not eff.available or eff.shots_remaining_this_tick <= 0:
                continue
            combined = sensor.p_track * sensor.p_identify * eff.spec.p_kill
            hit = rng.chance(combined)
            eff.fire()
            defender_cost += eff.spec.cost_per_shot
            shots_fired += 1
            shots.append(
                ShotRecord(
                    effector_id=eff.spec.id,
                    target_uid=target.uid,
                    hit=hit,
                    cost=eff.spec.cost_per_shot,
                )
            )
            if hit:
                target.alive = False
                defeated += 1
                kills.append(target.uid)

        # 5. Deplete & reload
        for eff in effectors:
            eff.tick_cooldown()

        # 6. Leak -- threats reaching the asset
        leaks: list[int] = []
        for t in threats:
            if t.alive and not t.leaked and t.position <= 0.0:
                t.leaked = True
                leaks.append(t.uid)
                if t.spec.is_decoy:
                    leakers_decoy += 1
                else:
                    leakers_armed += 1
                    damage_to_asset += t.spec.warhead

        frames.append(
            Frame(
                tick=tick,
                threats=[_frame_for(t) for t in threats],
                shots=shots,
                kills=kills,
                leaks=leaks,
            )
        )

    metrics = Metrics(
        total_threats=len(threats),
        defeated=defeated,
        leakers_armed=leakers_armed,
        leakers_decoy=leakers_decoy,
        damage_to_asset=damage_to_asset,
        attacker_cost=attacker_cost,
        defender_cost=defender_cost,
        shots_fired=shots_fired,
    )
    trace = RunTrace(seed=scenario.seed, ticks=tick, frames=frames)
    return Result(
        scenario_name=scenario.name,
        seed=scenario.seed,
        metrics=metrics,
        trace=trace,
    )


def _spawn_threats(scenario: Scenario) -> list[ThreatState]:
    threats: list[ThreatState] = []
    uid = 0
    for entry in scenario.swarm:
        for _ in range(entry.count):
            threats.append(
                ThreatState(uid=uid, spec=entry.spec, position=scenario.approach_distance)
            )
            uid += 1
    return threats


def _active(threats: list[ThreatState]) -> bool:
    return any(t.alive and not t.leaked for t in threats)


def _frame_for(t: ThreatState) -> ThreatFrame:
    return ThreatFrame(
        uid=t.uid,
        category=t.spec.category.value,
        position=t.position,
        alive=t.alive,
        tracked=t.tracked,
    )
