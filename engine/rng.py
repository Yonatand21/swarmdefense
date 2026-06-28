"""Seeded randomness for the engine.

Determinism is a design non-negotiable (ARCHITECTURE_AND_PLAN.md §4.3): same seed -> same run.
All stochastic decisions in the simulation flow through a single SeededRng instance so the order of
random draws is fully reproducible.
"""

from __future__ import annotations

import random


class SeededRng:
    """A thin, explicit wrapper over random.Random.

    Kept deliberately small: the engine should only ever ask for the few primitives it needs, so the
    consumption order stays auditable and reproducible.
    """

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._rng = random.Random(seed)

    def chance(self, probability: float) -> bool:
        """Return True with the given probability (a single Bernoulli draw)."""
        return self._rng.random() < probability

    def random(self) -> float:
        """A uniform draw in [0, 1)."""
        return self._rng.random()

    def spawn(self, offset: int) -> "SeededRng":
        """Derive a child RNG deterministically (for independent Monte Carlo runs in Phase 1)."""
        return SeededRng(self.seed + offset)
