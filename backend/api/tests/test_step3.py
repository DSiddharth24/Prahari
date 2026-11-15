"""Unit tests for Step 3: cases, dashboard, and countdown logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from backend.api.case_service import compute_countdown
from backend.main import app

client = TestClient(app)


def setup_function():
    """Reset and load demo data before each test."""
    client.post("/api/demo/reset")
    client.post("/api/demo/load")


def test_countdown_boundary_conditions():
    """Verify exact CERT-In 6-hour countdown logic and boundary states."""
    ref_now = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)

    # 1. > 3 hours remaining (> 10800 seconds) -> green
    # 6 hours deadline from detected_at. If detected_at is 2h ago, deadline is in 4h (14400s > 10800s)
    t_green = (ref_now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_green, status="open", now=ref_now)
    assert secs == 14400
    assert state == "green"

    # Exactly 10801s -> green
    t_10801 = (ref_now + timedelta(seconds=10801 - 6 * 3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_10801, status="open", now=ref_now)
    assert secs == 10801
    assert state == "green"

    # 2. Exactly 3 hours remaining (10800 seconds) -> amber
    t_amber_max = (ref_now + timedelta(seconds=10800 - 6 * 3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_amber_max, status="open", now=ref_now)
    assert secs == 10800
    assert state == "amber"

    # Exactly 1 hour remaining (3600 seconds) -> amber
    t_amber_min = (ref_now + timedelta(seconds=3600 - 6 * 3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_amber_min, status="open", now=ref_now)
    assert secs == 3600
    assert state == "amber"

    # 3. Under 1 hour remaining (0 <= seconds < 3600) -> red
    t_red_3599 = (ref_now + timedelta(seconds=3599 - 6 * 3600)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_red_3599, status="open", now=ref_now)
    assert secs == 3599
    assert state == "red"

    # Exactly 0 seconds remaining -> red
    t_red_zero = (ref_now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_red_zero, status="open", now=ref_now)
    assert secs == 0
    assert state == "red"

    # 4. Past deadline (< 0 seconds) -> overdue
    t_overdue = (ref_now - timedelta(hours=6, seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, secs, state = compute_countdown(t_overdue, status="open", now=ref_now)
    assert secs == -10
    assert state == "overdue"

    # 5. Dismissed or reported case -> none (even if overdue)
    _, _, state_dismissed = compute_countdown(t_overdue, status="dismissed", now=ref_now)
    assert state_dismissed == "none"

    _, _, state_reported = compute_countdown(t_green, status="reported", now=ref_now)
    assert state_reported == "none"


def test_list_cases_and_sorting():
    """GET /api/cases returns cases sorted by score desc, then deadline asc."""
    response = client.get("/api/cases")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) >= 3

    # Validate CaseListItem fields
    required_fields = {
        "id",
        "title",
        "score",
        "severity",
        "status",
        "pattern",
        "sources_count",
        "first_alert_at",
        "detected_at",
        "deadline_at",
        "seconds_remaining",
        "countdown_state",
    }
    for c in cases:
        assert required_fields.issubset(c.keys())

    # Check sort order: score descending
    scores = [c["score"] for c in cases]
    assert scores == sorted(scores, reverse=True)


def test_list_cases_filtering():
    """GET /api/cases filters by severity, status, and pattern."""
    # Filter by severity
    resp_crit = client.get("/api/cases?severity=critical")
    assert resp_crit.status_code == 200
    for c in resp_crit.json():
        assert c["severity"] == "critical"

    # Filter by status
    resp_open = client.get("/api/cases?status=open")
    assert resp_open.status_code == 200
    for c in resp_open.json():
        assert c["status"] == "open"

    # Filter by pattern
    resp_hero = client.get("/api/cases?pattern=account_takeover_then_exfiltration")
    assert resp_hero.status_code == 200
    assert len(resp_hero.json()) == 1
    assert resp_hero.json()[0]["pattern"] == "account_takeover_then_exfiltration"


def test_get_case_detail_success():
    """GET /api/cases/{id} returns CaseDetail with timeline and score breakdown."""
    cases_resp = client.get("/api/cases")
    hero_case = next(c for c in cases_resp.json() if c["pattern"] == "account_takeover_then_exfiltration")
    case_id = hero_case["id"]

    resp = client.get(f"/api/cases/{case_id}")
    assert resp.status_code == 200
    detail = resp.json()

    # Check detail-specific keys
    assert "timeline" in detail
    assert "score_breakdown" in detail
    assert "entities" in detail
    assert "recommended_actions" in detail

    # Hero timeline has 4 full alerts in chronological order
    timeline = detail["timeline"]
    assert len(timeline) == 4
    timestamps = [a["timestamp"] for a in timeline]
    assert timestamps == sorted(timestamps)

    # Check alert fields
    for a in timeline:
        assert "source" in a
        assert "source_alert_id" in a
        assert "title" in a
        assert "severity_raw" in a


def test_get_case_detail_not_found():
    """GET /api/cases/{id} returns 404 for nonexistent case."""
    resp = client.get("/api/cases/99999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_case_action_confirm_dismiss_escalate():
    """POST /api/cases/{id}/action applies confirm/dismiss/escalate with note."""
    cases = client.get("/api/cases").json()
    case_id = cases[0]["id"]

    # 1. Confirm
    resp_conf = client.post(
        f"/api/cases/{case_id}/action",
        json={"action": "confirm", "note": "Verified anomalous IP with user", "actor": "sr_analyst"},
    )
    assert resp_conf.status_code == 200
    assert resp_conf.json()["status"] == "confirmed"

    # 2. Escalate
    resp_esc = client.post(
        f"/api/cases/{case_id}/action",
        json={"action": "escalate", "note": "Escalating to CISO for CERT-In coordination", "actor": "sr_analyst"},
    )
    assert resp_esc.status_code == 200
    assert resp_esc.json()["status"] == "escalated"

    # 3. Dismiss (countdown_state should become 'none')
    resp_dis = client.post(
        f"/api/cases/{case_id}/action",
        json={"action": "dismiss", "note": "False positive test exercise", "actor": "sr_analyst"},
    )
    assert resp_dis.status_code == 200
    assert resp_dis.json()["status"] == "dismissed"
    assert resp_dis.json()["countdown_state"] == "none"


def test_case_action_validation_errors():
    """POST /api/cases/{id}/action returns 400 on empty note or invalid action."""
    cases = client.get("/api/cases").json()
    case_id = cases[0]["id"]

    # Empty note
    resp_empty_note = client.post(
        f"/api/cases/{case_id}/action",
        json={"action": "confirm", "note": "   "},
    )
    assert resp_empty_note.status_code == 400
    assert "note is required" in resp_empty_note.json()["detail"].lower()

    # Invalid action
    resp_bad_act = client.post(
        f"/api/cases/{case_id}/action",
        json={"action": "invalid_action", "note": "Valid note"},
    )
    assert resp_bad_act.status_code == 400
    assert "invalid action" in resp_bad_act.json()["detail"].lower()

    # Nonexistent case
    resp_404 = client.post(
        "/api/cases/88888/action",
        json={"action": "confirm", "note": "Valid note"},
    )
    assert resp_404.status_code == 404


def test_patch_detected_at():
    """PATCH /api/cases/{id}/detected_at updates detected_at and recalculates deadline."""
    cases = client.get("/api/cases").json()
    case_id = cases[0]["id"]

    new_ts = "2026-11-15T02:00:00Z"
    resp = client.patch(
        f"/api/cases/{case_id}/detected_at",
        json={"detected_at": new_ts, "reason": "Analyst determined actual initial compromise was at 02:00 UTC"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detected_at"] == new_ts
    assert data["deadline_at"] == "2026-11-15T08:00:00Z"  # exactly 6h later


def test_patch_detected_at_validation_errors():
    """PATCH /api/cases/{id}/detected_at returns 400 for empty reason or bad date."""
    cases = client.get("/api/cases").json()
    case_id = cases[0]["id"]

    # Empty reason
    resp_no_reason = client.patch(
        f"/api/cases/{case_id}/detected_at",
        json={"detected_at": "2026-11-15T02:00:00Z", "reason": "  "},
    )
    assert resp_no_reason.status_code == 400
    assert "reason is required" in resp_no_reason.json()["detail"].lower()

    # Malformed ISO timestamp
    resp_bad_ts = client.patch(
        f"/api/cases/{case_id}/detected_at",
        json={"detected_at": "not-a-timestamp", "reason": "Reason provided"},
    )
    assert resp_bad_ts.status_code == 400
    assert "invalid iso-8601 timestamp" in resp_bad_ts.json()["detail"].lower()

    # Nonexistent case
    resp_404 = client.patch(
        "/api/cases/77777/detected_at",
        json={"detected_at": "2026-11-15T02:00:00Z", "reason": "Reason provided"},
    )
    assert resp_404.status_code == 404


def test_dashboard_endpoint():
    """GET /api/dashboard returns funnel, time saved estimate, severity breakdown, and open cases."""
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    # Check top-level keys
    assert "funnel" in data
    assert "time_saved_minutes" in data
    assert "time_saved_note" in data
    assert "cases_by_severity" in data
    assert "open_cases" in data

    # Funnel counts
    funnel = data["funnel"]
    assert funnel["ingested"] >= 380
    assert funnel["suppressed"] > 100
    assert funnel["merged"] > 10
    assert funnel["in_cases"] >= 10
    assert funnel["cases"] >= 3

    # Time saved
    assert data["time_saved_minutes"] > 0
    assert "minutes saved" in data["time_saved_note"].lower()

    # Severity counts
    sev = data["cases_by_severity"]
    assert "low" in sev
    assert "medium" in sev
    assert "high" in sev
    assert "critical" in sev
    assert sev["critical"] >= 2  # Hero and Ransomware

    # Open cases
    open_cases = data["open_cases"]
    assert len(open_cases) >= 3
    for c in open_cases:
        assert c["status"] == "open"
