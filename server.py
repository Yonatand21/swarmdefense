"""Thin localhost bridge between the engine and the mission-builder UI.

A stateless FastAPI process (ARCHITECTURE_AND_PLAN.md §11/§12 amendment): it validates a composed
scenario and returns its Monte Carlo result. The engine is untouched -- this is just another consumer
of the same contract, the input surface that turns the tool into something an operator drives.

Run it:  uvicorn server:app --reload   (or: python server.py)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.models import EffectorSpec, Scenario, ThreatSpec
from engine.montecarlo import run_montecarlo
from engine.requirements import solve
from schema.loader import (
    DEFAULT_SCENARIO_DIR,
    load_effectors,
    load_scenarios,
    load_threats,
)
from schema.result import MonteCarloResult
from schema.solver import Requirement, SolverResult

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except ImportError as exc:  # pragma: no cover - helpful message if extra not installed
    raise SystemExit(
        "FastAPI is not installed. Install the server extra:\n"
        "  pip install -e '.[server]'"
    ) from exc

MAX_RUNS = 2000


class Catalog(BaseModel):
    """The building blocks an operator composes a mission from, plus the canonical presets."""

    threats: list[ThreatSpec]
    effectors: list[EffectorSpec]
    presets: list[Scenario]


class RunRequest(BaseModel):
    scenario: Scenario
    runs: int = Field(default=200, ge=1, le=MAX_RUNS)


class SolveRequest(BaseModel):
    """Inverse design: hold the swarm/approach from `scenario`, search postures to meet `requirement`."""

    scenario: Scenario
    requirement: Requirement
    runs: int = Field(default=200, ge=1, le=MAX_RUNS)


app = FastAPI(title="Counter-Swarm Sandbox bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/catalog", response_model=Catalog)
def get_catalog() -> Catalog:
    """Threat/effector archetypes (the building blocks) + the canonical scenarios as starting points."""
    threats = list(load_threats(DEFAULT_SCENARIO_DIR / "threats.yaml").values())
    effectors = list(load_effectors(DEFAULT_SCENARIO_DIR / "effectors.yaml").values())
    presets = list(load_scenarios().values())
    return Catalog(threats=threats, effectors=effectors, presets=presets)


@app.post("/api/run", response_model=MonteCarloResult)
def post_run(req: RunRequest) -> MonteCarloResult:
    """Validate a composed scenario and return its Monte Carlo distribution."""
    if not req.scenario.swarm:
        raise HTTPException(status_code=422, detail="Swarm is empty: add at least one threat.")
    if not req.scenario.defense.effectors:
        raise HTTPException(status_code=422, detail="Defense is empty: add at least one effector.")
    return run_montecarlo(req.scenario, runs=req.runs)


@app.post("/api/requirements", response_model=SolverResult)
def post_requirements(req: SolveRequest) -> SolverResult:
    """Find the cheapest pre-registered posture that meets the requirement for this threat picture."""
    if not req.scenario.swarm:
        raise HTTPException(status_code=422, detail="Swarm is empty: add at least one threat.")
    catalog = load_effectors(DEFAULT_SCENARIO_DIR / "effectors.yaml")
    return solve(
        req.scenario.swarm,
        req.scenario.approach_distance,
        req.requirement,
        catalog,
        base_seed=req.scenario.seed,
        runs=req.runs,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
