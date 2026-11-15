"""Unit tests for Step 2: app skeleton, health, ingest, demo load/reset."""

from __future__ import annotations

import csv
import io
import json

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    """GET /api/health must return status ok."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_reset():
    """POST /api/demo/reset must reset storage and return ok."""
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_alerts_ingest_json_list():
    """POST /api/alerts/ingest accepts a raw JSON array."""
    client.post("/api/demo/reset")

    payload = [
        {
            "source": "firewall",
            "source_alert_id": "fw-unit-001",
            "timestamp": "2026-11-14T10:00:00Z",
            "title": "Port scan from known scanner",
            "category": "port_scan",
            "severity": "low",
            "extra": {"known_scanner": True},
        },
        {
            "source": "identity_provider",
            "source_alert_id": "idp-unit-002",
            "timestamp": "2026-11-14T10:05:00Z",
            "title": "Failed login attempt",
            "category": "failed_login",
            "severity": "low",
        },
    ]

    response = client.post("/api/alerts/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "ingest" in data
    assert "pipeline" in data
    assert data["ingest"]["received"] == 2
    assert data["ingest"]["new"] == 2


def test_alerts_ingest_json_dict():
    """POST /api/alerts/ingest accepts an object with 'alerts' key."""
    client.post("/api/demo/reset")

    payload = {
        "alerts": [
            {
                "source": "endpoint_av",
                "source_alert_id": "av-unit-003",
                "timestamp": "2026-11-14T11:00:00Z",
                "title": "Routine definition update",
                "category": "informational",
                "severity": "low",
                "extra": {"benign_type": "edr_info"},
            }
        ]
    }

    response = client.post("/api/alerts/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ingest"]["received"] == 1
    assert data["ingest"]["new"] == 1


def test_alerts_ingest_json_file_upload():
    """POST /api/alerts/ingest accepts a multipart uploaded .json file."""
    client.post("/api/demo/reset")

    alerts = [
        {
            "source": "cloud_audit",
            "source_alert_id": "cloud-unit-004",
            "timestamp": "2026-11-14T12:00:00Z",
            "title": "Scheduled backup job",
            "category": "backup_activity",
            "severity": "low",
            "extra": {"scheduled": True},
        }
    ]
    file_bytes = json.dumps(alerts).encode("utf-8")
    files = {"file": ("batch_alerts.json", io.BytesIO(file_bytes), "application/json")}

    response = client.post("/api/alerts/ingest", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["ingest"]["received"] == 1
    assert data["ingest"]["new"] == 1


def test_alerts_ingest_csv_file_upload():
    """POST /api/alerts/ingest accepts a multipart uploaded .csv file."""
    client.post("/api/demo/reset")

    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=["source", "source_alert_id", "timestamp", "title", "severity", "category", "extra"],
    )
    writer.writeheader()
    writer.writerow(
        {
            "source": "dlp",
            "source_alert_id": "dlp-unit-005",
            "timestamp": "2026-11-14T13:00:00Z",
            "title": "Mass file read on test host",
            "severity": "low",
            "category": "mass_file_access",
            "extra": json.dumps({"test_run": True}),
        }
    )

    file_bytes = csv_buffer.getvalue().encode("utf-8")
    files = {"file": ("alerts.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/api/alerts/ingest", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["ingest"]["received"] == 1
    assert data["ingest"]["new"] == 1


def test_alerts_ingest_validation_errors():
    """Malformed input must return 400 with detail message."""
    # 1. Missing required field 'timestamp'
    bad_payload = [
        {
            "source": "firewall",
            "source_alert_id": "bad-001",
            "title": "Missing timestamp",
        }
    ]
    resp = client.post("/api/alerts/ingest", json=bad_payload)
    assert resp.status_code == 400
    assert "missing required fields" in resp.json()["detail"].lower()

    # 2. Empty list
    resp = client.post("/api/alerts/ingest", json=[])
    assert resp.status_code == 400
    assert "no alert items found" in resp.json()["detail"].lower()

    # 3. Unsupported file extension
    files = {"file": ("data.txt", io.BytesIO(b"unsupported content"), "text/plain")}
    resp = client.post("/api/alerts/ingest", files=files)
    assert resp.status_code == 400
    assert "unsupported file extension" in resp.json()["detail"].lower()


def test_demo_load():
    """POST /api/demo/load populates demo alerts and runs detection pipeline."""
    client.post("/api/demo/reset")

    response = client.post("/api/demo/load")
    assert response.status_code == 200
    data = response.json()
    assert "ingest" in data
    assert "pipeline" in data

    ingest_res = data["ingest"]
    pipe_res = data["pipeline"]

    assert ingest_res["received"] >= 380
    assert ingest_res["new"] >= 380
    assert pipe_res["cases_created"] >= 3
    assert pipe_res["suppressed"] > 100
    assert pipe_res["in_cases"] >= 10
