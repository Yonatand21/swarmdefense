"""The engine <-> consumer contract (ARCHITECTURE_AND_PLAN.md §5).

These pydantic models are the *entire* interface between the simulation engine and any consumer
(metrics view, animation frontend, future API). The engine emits them; consumers only read them.
Nothing here knows how the simulation works.

Phase 0 ships a single-run Result. Phase 1 adds Monte Carlo aggregation on top of the same trace.
"""

from __future__ import annotations

import math
import statistics
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ShotRecord(BaseModel):
    """One effector engagement in one tick."""

    effector_id: str
    target_uid: int
    hit: bool
    cost: float


class EffectorFrame(BaseModel):
    """Ammo/reload state of one effector at one tick -- feeds the magazine timeline (§8)."""

    effector_id: str
    ammo: int
    reloading: bool


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
    effectors: list[EffectorFrame] = Field(default_factory=list)
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


# --------------------------------------------------------------------------------------------------
# Monte Carlo aggregation (Phase 1) -- "one run lies; the distribution tells the truth" (§8)
# --------------------------------------------------------------------------------------------------


class Distribution(BaseModel):
    """Summary of one metric across many runs, with the raw values kept for histograms."""

    values: list[float]
    mean: float
    median: float
    std: float
    min: float
    max: float
    p10: float
    p90: float

    @classmethod
    def from_values(cls, values: list[float]) -> "Distribution":
        ordered = sorted(values)
        return cls(
            values=values,
            mean=statistics.fmean(ordered),
            median=statistics.median(ordered),
            std=statistics.pstdev(ordered) if len(ordered) > 1 else 0.0,
            min=ordered[0],
            max=ordered[-1],
            p10=_percentile(ordered, 0.10),
            p90=_percentile(ordered, 0.90),
        )


class MonteCarloMetrics(BaseModel):
    """A distribution per headline metric (§8)."""

    leakers_total: Distribution
    leakers_armed: Distribution
    leakers_decoy: Distribution
    defeated: Distribution
    cost_exchange_ratio: Distribution
    defender_cost: Distribution
    damage_to_asset: Distribution
    shots_fired: Distribution


class AttritionPoint(BaseModel):
    """Mean threats-alive at a tick, averaged across runs (§8 attrition curve)."""

    tick: int
    mean_alive: float


class MagazineStat(BaseModel):
    """When an effector layer runs dry (§8 magazine timeline)."""

    effector_id: str
    dry_fraction: float = Field(description="Fraction of runs in which this layer ran dry at all.")
    mean_first_dry_tick: Optional[float] = Field(
        default=None, description="Mean tick of first depletion, over runs where it ran dry."
    )


class MonteCarloResult(BaseModel):
    """The aggregate artifact: distributions + curves + one representative trace."""

    scenario_name: str
    runs: int
    base_seed: int
    total_threats: int
    armed_threats: int
    metrics: MonteCarloMetrics
    attrition_curve: list[AttritionPoint]
    magazine_timeline: list[MagazineStat]
    representative_seed: int
    representative: RunTrace


def _percentile(ordered: list[float], q: float) -> float:
    """Linear-interpolation percentile on an already-sorted list."""
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
