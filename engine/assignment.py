"""Defender shot-allocation policy (ARCHITECTURE_AND_PLAN.md §7 step 3).

This is a deliberately swappable seam: the simulation loop calls `assign()` and never knows how the
decision is made, so a smarter optimizer can replace this module later without touching the engine
(§12). The v1 policy is intentionally simple.

Honest information model (§7): the policy sees only sensor-visible state -- position and track
status. It does NOT read `is_decoy` or `warhead`, which is precisely why decoys draw shots.
"""

from __future__ import annotations

from engine.models import EffectorState, ThreatState

Assignment = tuple[EffectorState, ThreatState]


def assign(effectors: list[EffectorState], tracked: list[ThreatState]) -> list[Assignment]:
    """Greedy nearest-threat-first allocation.

    Priority is the most urgent (closest to the asset) tracked threat -- the only sensor-visible
    proxy for danger available to an honest defender. Each threat absorbs at most one shot per tick;
    each effector fires up to its remaining per-tick capacity, ammo permitting.
    """
    targets = sorted(
        (t for t in tracked if t.alive and not t.leaked),
        key=lambda t: t.position,
    )
    claimed: set[int] = set()
    assignments: list[Assignment] = []

    for eff in effectors:
        if not eff.available:
            continue
        shots = min(eff.shots_remaining_this_tick, eff.ammo)
        for target in targets:
            if shots <= 0:
                break
            if target.uid in claimed:
                continue
            if target.position > eff.spec.range:
                continue
            if not eff.spec.can_engage(target.spec):
                continue
            assignments.append((eff, target))
            claimed.add(target.uid)
            shots -= 1

    return assignments
