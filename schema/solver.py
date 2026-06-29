"""Requirements-solver contract.

The models now live in `schema.result` so they are importable from there alongside the rest of the
contract. This module re-exports them for the engine/server call sites that import `schema.solver`.
"""

from __future__ import annotations

from schema.result import (
    CandidatePosture,
    LedgerLine,
    Requirement,
    SolverResult,
)

__all__ = ["CandidatePosture", "LedgerLine", "Requirement", "SolverResult"]
