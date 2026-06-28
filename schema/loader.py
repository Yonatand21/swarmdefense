"""YAML -> pydantic loader (ARCHITECTURE_AND_PLAN.md §13).

Threats, effectors, and scenarios are authored as data. This module parses the three YAML files,
resolves the id references (a scenario names threats and effectors; we splice in the full specs),
and returns validated `Scenario` objects. All validation errors surface here, early.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from engine.models import (
    DefenseSpec,
    EffectorSpec,
    Environment,
    Scenario,
    SensorSpec,
    SwarmEntry,
    ThreatSpec,
)

DEFAULT_SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_threats(path: Path) -> dict[str, ThreatSpec]:
    raw = _read_yaml(path)
    specs = [ThreatSpec(**entry) for entry in raw["threats"]]
    return {spec.id: spec for spec in specs}


def load_effectors(path: Path) -> dict[str, EffectorSpec]:
    raw = _read_yaml(path)
    specs = [EffectorSpec(**entry) for entry in raw["effectors"]]
    return {spec.id: spec for spec in specs}


def load_scenarios(scenario_dir: Path | str = DEFAULT_SCENARIO_DIR) -> dict[str, Scenario]:
    """Load every scenario, resolving threat/effector ids into full specs."""
    scenario_dir = Path(scenario_dir)
    threats = load_threats(scenario_dir / "threats.yaml")
    effectors = load_effectors(scenario_dir / "effectors.yaml")
    raw = _read_yaml(scenario_dir / "scenarios.yaml")

    scenarios: dict[str, Scenario] = {}
    for entry in raw["scenarios"]:
        scenarios[entry["name"]] = _build_scenario(entry, threats, effectors)
    return scenarios


def load_scenario(name: str, scenario_dir: Path | str = DEFAULT_SCENARIO_DIR) -> Scenario:
    scenarios = load_scenarios(scenario_dir)
    if name not in scenarios:
        available = ", ".join(sorted(scenarios)) or "(none)"
        raise KeyError(f"Unknown scenario {name!r}. Available: {available}")
    return scenarios[name]


def _build_scenario(
    entry: dict[str, Any],
    threats: dict[str, ThreatSpec],
    effectors: dict[str, EffectorSpec],
) -> Scenario:
    swarm = [
        SwarmEntry(spec=_resolve(threats, item["threat"], "threat"), count=item["count"])
        for item in entry["swarm"]
    ]

    defense_raw = entry["defense"]
    sensor = SensorSpec(**defense_raw.get("sensor", {}))
    defense_effectors = [
        _resolve(effectors, eid, "effector") for eid in defense_raw["effectors"]
    ]
    defense = DefenseSpec(sensor=sensor, effectors=defense_effectors)

    environment = Environment(**entry.get("environment", {}))

    return Scenario(
        name=entry["name"],
        description=entry.get("description", ""),
        seed=entry.get("seed", 0),
        approach_distance=entry["approach_distance"],
        swarm=swarm,
        defense=defense,
        environment=environment,
    )


def _resolve(registry: dict[str, Any], key: str, kind: str) -> Any:
    if key not in registry:
        available = ", ".join(sorted(registry)) or "(none)"
        raise KeyError(f"Unknown {kind} id {key!r}. Defined {kind}s: {available}")
    return registry[key]
