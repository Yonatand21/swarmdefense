"""Domain model for the engagement sandbox.

Two layers live here:

1. Config models (pydantic, frozen) -- the data-driven, validated definitions a user authors as
   YAML (ARCHITECTURE_AND_PLAN.md §4.4, §6). These never mutate.
2. Runtime state (dataclasses) -- the mutable per-run state the simulation loop advances. Kept
   separate from config so the loop can churn cheaply without fighting immutable models.

Every field traces back to a force in §2; see §6 for the mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ThreatCategory(str, Enum):
    CHEAP_MASS = "cheap_mass"
    DECOY = "decoy"
    AUTONOMOUS = "autonomous"
    TERRAIN_HUGGER = "terrain_hugger"


class EffectorType(str, Enum):
    SOFT_KILL = "soft_kill"
    KINETIC = "kinetic"
    INTERCEPTOR_DRONE = "interceptor_drone"
    DIRECTED_ENERGY = "directed_energy"


# --------------------------------------------------------------------------------------------------
# Config models (data-driven, validated, immutable)
# --------------------------------------------------------------------------------------------------


class ThreatSpec(BaseModel):
    """A drone archetype. See §6 'Threat'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    category: ThreatCategory
    cost: float = Field(ge=0, description="Acquisition cost; feeds cost-exchange (attacker side).")
    speed: float = Field(gt=0, description="Closing rate in length-units per tick.")
    detection_range: float = Field(
        gt=0,
        description="Range at which this threat becomes trackable. Small => 'seen too late'.",
    )
    soft_kill_immune: bool = Field(
        default=False, description="Autonomous / GPS-denied: ignores the EW (soft-kill) layer."
    )
    is_decoy: bool = Field(
        default=False,
        description="No warhead, but still draws a shot. The defender never reads this field "
        "directly (see §7 information model).",
    )
    warhead: float = Field(
        default=1.0, ge=0, description="Damage dealt if it leaks. Decoys should set this to 0."
    )


class EffectorSpec(BaseModel):
    """A defensive layer. See §6 'Effector'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: EffectorType
    cost_per_shot: float = Field(ge=0, description="Feeds cost-exchange (defender side).")
    range: float = Field(gt=0, description="How far out it can engage.")
    magazine: int = Field(gt=0, description="Ready shots before a reload is required.")
    reload_time: int = Field(ge=0, description="Ticks to refill an empty magazine.")
    p_kill: float = Field(
        ge=0, le=1, description="Defeat-stage probability only (one factor in the kill chain)."
    )
    engages: Optional[list[ThreatCategory]] = Field(
        default=None, description="Threat categories this works against. None => all categories."
    )
    max_simultaneous: int = Field(
        default=1, gt=0, description="Targets engageable per tick (e.g. directed energy = 1)."
    )
    max_target_speed: Optional[float] = Field(
        default=None,
        gt=0,
        description="Speed ceiling above which this effector cannot engage (e.g. DE vs slow only).",
    )

    def can_engage(self, threat: "ThreatSpec") -> bool:
        """Type/immunity/speed eligibility (range and ammo are checked at runtime)."""
        if self.type == EffectorType.SOFT_KILL and threat.soft_kill_immune:
            return False
        if self.engages is not None and threat.category not in self.engages:
            return False
        if self.max_target_speed is not None and threat.speed > self.max_target_speed:
            return False
        return True


class SensorSpec(BaseModel):
    """Deliberately abstract sensing/C2 suite. See §6 'Sensor'.

    Detection itself is a hard range gate (threat.detection_range). The remaining non-defeat stages
    of the kill chain live here as probabilities.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    p_track: float = Field(default=1.0, ge=0, le=1, description="Hold a stable track once detected.")
    p_identify: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Correctly classify a track. Why decoys cost shots (defender lacks ground truth).",
    )


class DefenseSpec(BaseModel):
    """A layered defense: a sensor suite plus a loadout of effectors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sensor: SensorSpec = Field(default_factory=SensorSpec)
    effectors: list[EffectorSpec]


class SwarmEntry(BaseModel):
    """A count of one threat archetype within a wave (the loader resolves the id into `spec`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: ThreatSpec
    count: int = Field(gt=0)


class Environment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    detection_modifier: float = Field(
        default=1.0, gt=0, description="Scales every threat's detection_range (weather, terrain)."
    )


class Scenario(BaseModel):
    """A named, runnable bundle: swarm + defense + environment + seed. See §6 'Scenario'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str = ""
    seed: int = 0
    approach_distance: float = Field(
        gt=0, description="Distance from which threats begin their run toward the asset (at 0)."
    )
    swarm: list[SwarmEntry]
    defense: DefenseSpec
    environment: Environment = Field(default_factory=Environment)


# --------------------------------------------------------------------------------------------------
# Runtime state (mutable, advanced by the simulation loop)
# --------------------------------------------------------------------------------------------------


@dataclass
class ThreatState:
    """Live state of a single threat in flight."""

    uid: int
    spec: ThreatSpec
    position: float
    alive: bool = True
    tracked: bool = False
    leaked: bool = False


@dataclass
class EffectorState:
    """Live state of a single effector (ammo + reload bookkeeping)."""

    spec: EffectorSpec
    ammo: int
    cooldown: int = 0
    shots_remaining_this_tick: int = field(default=0)

    @property
    def available(self) -> bool:
        return self.cooldown == 0 and self.ammo > 0

    def begin_tick(self) -> None:
        self.shots_remaining_this_tick = self.spec.max_simultaneous

    def fire(self) -> None:
        self.ammo -= 1
        self.shots_remaining_this_tick -= 1
        if self.ammo == 0:
            if self.spec.reload_time == 0:
                self.ammo = self.spec.magazine
            else:
                # Magazine just ran dry: start the reload clock; ammo refills when it elapses.
                self.cooldown = self.spec.reload_time

    def tick_cooldown(self) -> None:
        if self.cooldown > 0:
            self.cooldown -= 1
            if self.cooldown == 0:
                self.ammo = self.spec.magazine
