"""Smoke + contract tests for the localhost engine bridge (server.py)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from server import app  # noqa: E402

client = TestClient(app)


def test_catalog_lists_building_blocks_and_presets():
    res = client.get("/api/catalog")
    assert res.status_code == 200
    body = res.json()
    assert {t["id"] for t in body["threats"]} >= {"shahed", "decoy", "autonomous"}
    assert {e["id"] for e in body["effectors"]} >= {"ew", "kinetic", "interceptor_drone"}
    assert {p["name"] for p in body["presets"]} == {
        "all_ew_vs_autonomous",
        "kinetic_vs_mass_and_decoys",
        "layered_mix",
    }


def test_run_a_preset_returns_a_distribution():
    catalog = client.get("/api/catalog").json()
    preset = next(p for p in catalog["presets"] if p["name"] == "layered_mix")

    res = client.post("/api/run", json={"scenario": preset, "runs": 50})
    assert res.status_code == 200
    mc = res.json()
    assert mc["runs"] == 50
    assert mc["armed_threats"] == 26  # 18 shahed + 8 autonomous
    assert mc["total_threats"] == 36
    assert len(mc["metrics"]["leakers_total"]["values"]) == 50


def test_run_is_deterministic_over_the_api():
    catalog = client.get("/api/catalog").json()
    preset = next(p for p in catalog["presets"] if p["name"] == "kinetic_vs_mass_and_decoys")
    a = client.post("/api/run", json={"scenario": preset, "runs": 40}).json()
    b = client.post("/api/run", json={"scenario": preset, "runs": 40}).json()
    assert a["metrics"] == b["metrics"]


def test_run_rejects_empty_swarm():
    catalog = client.get("/api/catalog").json()
    preset = {**catalog["presets"][0], "swarm": []}
    res = client.post("/api/run", json={"scenario": preset, "runs": 10})
    assert res.status_code == 422


def test_run_rejects_invalid_field():
    catalog = client.get("/api/catalog").json()
    preset = next(p for p in catalog["presets"] if p["name"] == "layered_mix")
    bad = {
        **preset,
        "defense": {
            **preset["defense"],
            "effectors": [{**preset["defense"]["effectors"][0], "p_kill": 5.0}],
        },
    }
    res = client.post("/api/run", json={"scenario": bad, "runs": 10})
    assert res.status_code == 422
