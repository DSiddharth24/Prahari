"""Tests for Step 6: alerts list, audit log/export, and settings endpoints."""

from __future__ import annotations

import os

os.environ["PRAHARI_USE_FAKE_ENGINE"] = "1"

import pytest
from fastapi.testclient import TestClient

from backend.api.engine_bridge import engine
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state() -> None:
    engine.reset_all()


def test_list_alerts_by_status_and_restore() -> None:
    load_res = client.post("/api/demo/load")
    assert load_res.status_code == 200

    suppressed = client.get("/api/alerts?status=suppressed_benign").json()
    assert len(suppressed) > 0
    assert all(a["status"] == "suppressed_benign" for a in suppressed)

    merged = client.get("/api/alerts?status=merged_duplicate").json()
    assert all(a["status"] == "merged_duplicate" for a in merged)

    target_id = suppressed[0]["id"]
    restore_res = client.post(f"/api/alerts/{target_id}/restore")
    assert restore_res.status_code == 200
    assert restore_res.json()["ok"] is True


def test_audit_log_filters_and_exports() -> None:
    client.post("/api/demo/load")

    all_events = client.get("/api/audit").json()
    assert len(all_events) >= 2

    filtered = client.get("/api/audit?action=run_pipeline").json()
    assert len(filtered) >= 1
    assert all(e["action"] == "run_pipeline" for e in filtered)

    csv_res = client.get("/api/audit/export?format=csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "id,timestamp,actor,action,target_type,target_id,details" in csv_res.text

    json_res = client.get("/api/audit/export?format=json")
    assert json_res.status_code == 200
    assert json_res.headers["content-type"] == "application/json"
    assert isinstance(json_res.json(), list)


def test_get_and_put_settings_with_yaml_validation() -> None:
    res = client.get("/api/settings")
    assert res.status_code == 200
    body = res.json()
    assert "correlation_window_hours" in body["settings"]
    assert "suppression_rules" in body["rules_yaml"]

    # Invalid YAML returns 400
    bad = client.put(
        "/api/settings",
        json={"rules_yaml": "suppression_rules:\n  - id: [unclosed_bracket"},
    )
    assert bad.status_code == 400
    assert "detail" in bad.json()

    # Valid update persists
    ok = client.put(
        "/api/settings",
        json={
            "settings": {"minutes_saved_per_alert": 8},
            "rules_yaml": "suppression_rules: []\ncorrelation_rules: []\n",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["settings"]["minutes_saved_per_alert"] == 8
    assert ok.json()["rules_yaml"] == "suppression_rules: []\ncorrelation_rules: []\n"