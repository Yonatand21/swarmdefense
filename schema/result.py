"""The engine <-> consumer contract (ARCHITECTURE_AND_PLAN.md §5).

These pydantic models are the *entire* interface between the simulation engine and any consumer
(metrics view, animation frontend, future API). The engine emits them; consumers only read them.
Nothing here knows how the simulation works.

Phase 0 ships a single-run Result. Phase 1 adds Monte Carlo aggregation on top of the same trace.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ShotRecord(BaseModel):
    """One effector engagement in one tick."""

    effector_id: str
    target_uid: int
    hit: bool
    cost: float


class ThreatFrame(BaseModel):
    """Position/state of one threat at one tick (for replay)."""

    uid: int
    category: str
    position: float
    alive: bool
    tracked: bool


class Frame(BaseModel):
    """A single timestep of one run -- the unit the animation replays (§5)."""

    tick: int
    threats: list[ThreatFrame]
    shots: list[ShotRecord] = Field(default_factory=list)
    kills: list[int] = Field(default_factory=list)
    leaks: list[int] = Field(default_factory=list)


class Metrics(BaseModel):
    """Aggregate outcomes of a run -- what 'winning' means (§8)."""

    total_threats: int
    defeated: int
    leakers_armed: int
    leakers_decoy: int
    damage_to_asset: float
    attacker_cost: float
    defender_cost: float
    shots_fired: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leakers_total(self) -> int:
        return self.leakers_armed + self.leakers_decoy

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_exchange_ratio(self) -> Optional[float]:
        """Defender $ / attacker $. None when the attacker spent nothing (undefined)."""
        if self.attacker_cost == 0:
            return None
        return self.defender_cost / self.attacker_cost


class RunTrace(BaseModel):
    """Per-tick state of one representative run (§5)."""

    seed: int
    ticks: int
    frames: list[Frame]


class Result(BaseModel):
    """The complete emitted artifact for a single run."""

    scenario_name: str
    seed: int
    metrics: Metrics
    trace: RunTrace
