"""Tests for CERT-In draft report generation, versioning, manual submission, and PDF export."""

from __future__ import annotations

import os

os.environ["PRAHARI_USE_FAKE_ENGINE"] = "1"

import pytest
from fastapi.testclient import TestClient

from backend.api.engine_bridge import engine
from backend.main import app
from backend.reporting.report import load_certin_incident_types

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_state() -> None:
    engine.reset_all()


def _seed_demo_and_get_hero_case_id() -> int:
    res = client.post("/api/demo/load")
    assert res.status_code == 200
    cases = client.get("/api/cases").json()
    assert len(cases) > 0
    return cases[0]["id"]


def test_certin_config_has_disclaimer_note() -> None:
    cfg = load_certin_incident_types()
    assert "_note" in cfg
    assert "working template" in cfg["_note"].lower()
    assert len(cfg["incident_types"]) >= 5


def test_create_draft_report_and_idempotency() -> None:
    case_id = _seed_demo_and_get_hero_case_id()

    res1 = client.post(f"/api/cases/{case_id}/report")
    assert res1.status_code == 200
    rep1 = res1.json()
    assert rep1["case_id"] == case_id
    assert rep1["status"] == "draft"
    assert rep1["version"] == 1
    assert "IST (UTC+05:30)" in rep1["fields"]["detected_at_ist"]
    assert rep1["fields"]["organisation_name"] == "Demo NBFC Ltd"

    # Calling again returns the same existing draft
    res2 = client.post(f"/api/cases/{case_id}/report")
    assert res2.status_code == 200
    assert res2.json()["id"] == rep1["id"]
    assert res2.json()["version"] == 1


def test_report_versioning_and_history() -> None:
    case_id = _seed_demo_and_get_hero_case_id()
    rep = client.post(f"/api/cases/{case_id}/report").json()
    rep_id = rep["id"]

    edit_res = client.put(
        f"/api/reports/{rep_id}",
        json={
            "fields": {
                "reporter_name": "C. Choudhary",
                "reporter_role": "SOC Lead",
                "logs_preserved": True,
            },
            "narrative": "Updated analyst narrative with verified IP logs.",
        },
    )
    assert edit_res.status_code == 200
    updated = edit_res.json()
    assert updated["version"] == 2
    assert updated["fields"]["reporter_name"] == "C. Choudhary"
    assert updated["fields"]["logs_preserved"] is True
    assert len(updated["history"]) == 1
    assert updated["history"][0]["version"] == 1
    assert updated["history"][0]["fields"]["reporter_name"] == ""

    get_res = client.get(f"/api/reports/{rep_id}")
    assert get_res.status_code == 200
    assert get_res.json()["version"] == 2
    assert len(get_res.json()["history"]) == 1


def test_manual_submission_and_validation() -> None:
    case_id = _seed_demo_and_get_hero_case_id()
    rep_id = client.post(f"/api/cases/{case_id}/report").json()["id"]

    bad = client.post(
        f"/api/reports/{rep_id}/submitted",
        json={"reference_number": "   ", "submitted_by": "C. Choudhary"},
    )
    assert bad.status_code == 400

    ok = client.post(
        f"/api/reports/{rep_id}/submitted",
        json={"reference_number": "CERTIN-2026-9981", "submitted_by": "C. Choudhary"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["status"] == "submitted_manually"
    assert body["fields"]["manual_submission"]["reference_number"] == "CERTIN-2026-9981"

    # Case status transitions to reported
    case_detail = client.get(f"/api/cases/{case_id}").json()
    assert case_detail["status"] == "reported"
    assert case_detail["countdown_state"] == "none"


def test_report_pdf_export_valid_header() -> None:
    case_id = _seed_demo_and_get_hero_case_id()
    rep_id = client.post(f"/api/cases/{case_id}/report").json()["id"]

    pdf_res = client.get(f"/api/reports/{rep_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF")
    assert len(pdf_res.content) > 500