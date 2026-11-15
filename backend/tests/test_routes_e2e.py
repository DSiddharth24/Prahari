"""
backend/tests/test_routes_e2e.py
Full end-to-end route verification via FastAPI TestClient.

Checks every endpoint listed in section 7.4 of the context document.
Exits with code 0 if all pass, non-zero on first failure.
"""
import io
import json
import os
import sys
import tempfile

# Point at a fresh temp DB BEFORE any backend import
_tmp_db = tempfile.mktemp(suffix="_e2e.db")
os.environ["PRAHARI_DB_PATH"] = _tmp_db

# ── imports ────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("PRAHARI_USE_FAKE_ENGINE", "0")

from backend.main import app  # noqa: E402

# Use context manager so the FastAPI lifespan (init_db) runs before any request
_tc = TestClient(app, raise_server_exceptions=True)
_tc.__enter__()
client = _tc

# ── helpers ────────────────────────────────────────────────────────────────
PASS, FAIL = "✓", "✗"
_failures = []

def check(label: str, resp, expected: int = 200, body_check=None):
    ok = resp.status_code == expected
    if ok and body_check:
        try:
            data = resp.json()
            ok = body_check(data)
        except Exception as e:
            ok = False
            print(f"  {FAIL}  {label}: body_check raised {e}")
    sym = PASS if ok else FAIL
    print(f"  {sym}  {label}: HTTP {resp.status_code}", end="")
    if not ok:
        _failures.append(label)
        try:
            print(f"\n       {resp.text[:300]}", end="")
        except Exception:
            pass
    print()
    return resp

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 1. Health ─────────────────────────────────────────────────────")
check("GET /api/health", client.get("/api/health"),
      body_check=lambda d: d.get("status") == "ok")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 2. Demo load ──────────────────────────────────────────────────")
r = check("POST /api/demo/load", client.post("/api/demo/load"),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) > 0)
load_data = r.json()
print(f"       ingest={load_data.get('ingest')}  pipeline={load_data.get('pipeline')}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 3. Dashboard ──────────────────────────────────────────────────")
r = check("GET /api/dashboard", client.get("/api/dashboard"),
          body_check=lambda d: "funnel" in d and "open_cases" in d)
dash = r.json()
funnel = dash.get("funnel", {})
print(f"       funnel={funnel}")
print(f"       time_saved_minutes={dash.get('time_saved_minutes')}  cases_by_severity={dash.get('cases_by_severity')}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 4. Cases list ─────────────────────────────────────────────────")
r = check("GET /api/cases", client.get("/api/cases"),
          body_check=lambda d: isinstance(d, list) and len(d) > 0)
cases = r.json()
print(f"       {len(cases)} cases returned")

# Highest score first
hero = cases[0]
hero_id = hero["id"]
print(f"       hero case id={hero_id}  title='{hero['title'][:55]}'")
print(f"       severity={hero['severity']}  score={hero['score']}  pattern={hero['pattern']}")

# Filter by severity
r2 = check("GET /api/cases?severity=critical", client.get("/api/cases?severity=critical"),
           body_check=lambda d: all(c["severity"] == "critical" for c in d))
# Filter by status
check("GET /api/cases?status=open", client.get("/api/cases?status=open"),
      body_check=lambda d: all(c["status"] == "open" for c in d))

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 5. Case detail ────────────────────────────────────────────────")
r = check(f"GET /api/cases/{hero_id}", client.get(f"/api/cases/{hero_id}"),
          body_check=lambda d: "timeline" in d and "score_breakdown" in d)
detail = r.json()
print(f"       timeline events={len(detail.get('timeline', []))}")
print(f"       score_breakdown factors={len(detail.get('score_breakdown', []))}")
print(f"       entities={detail.get('entities')}")
print(f"       countdown_state={detail.get('countdown_state')}  deadline_at={detail.get('deadline_at')}")

check("GET /api/cases/999999 → 404", client.get("/api/cases/999999"), expected=404)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 6. Report create / read / edit / pdf / submit ─────────────────")
r = check(f"POST /api/cases/{hero_id}/report",
          client.post(f"/api/cases/{hero_id}/report"),
          body_check=lambda d: d.get("status") == "draft" and d.get("version") == 1)
report = r.json()
rid = report["id"]
print(f"       report id={rid}  incident_type='{report.get('incident_type')}'")
print(f"       fields keys={sorted(report.get('fields', {}).keys())}")

# Idempotent: second call returns same report
r2 = check(f"POST /api/cases/{hero_id}/report (idempotent)",
           client.post(f"/api/cases/{hero_id}/report"),
           body_check=lambda d: d["id"] == rid)

# GET report
r = check(f"GET /api/reports/{rid}", client.get(f"/api/reports/{rid}"),
          body_check=lambda d: d["id"] == rid)

# PUT edit (bumps version)
r = check(f"PUT /api/reports/{rid}",
          client.put(f"/api/reports/{rid}",
                     json={"fields": {"reporter_name": "A. Kapoor",
                                      "reporter_role": "CISO",
                                      "reporter_contact": "kapoor@nbfc.in"},
                           "actor": "analyst"}),
          body_check=lambda d: d.get("version") == 2)
rep2 = r.json()
print(f"       version after edit={rep2['version']}")
print(f"       reporter_name={rep2.get('fields', {}).get('reporter_name')}")

# History preserved
check(f"PUT /api/reports/{rid} history len>=1",
      client.put(f"/api/reports/{rid}",
                 json={"narrative": "Updated narrative v3.", "actor": "analyst"}),
      body_check=lambda d: d.get("version") == 3)

# GET with history
r = check(f"GET /api/reports/{rid} history",
          client.get(f"/api/reports/{rid}"),
          body_check=lambda d: len(d.get("history", [])) >= 1)
print(f"       history entries={len(r.json().get('history', []))}")

# PDF export
r = check(f"GET /api/reports/{rid}/pdf",
          client.get(f"/api/reports/{rid}/pdf"))
print(f"       PDF bytes={len(r.content)}")
assert r.headers.get("content-type", "").startswith("application/pdf"), \
    f"Expected PDF content-type, got {r.headers.get('content-type')}"
print(f"       content-type=application/pdf ✓")

# Mark submitted
r = check(f"POST /api/reports/{rid}/submitted",
          client.post(f"/api/reports/{rid}/submitted",
                      json={"reference_number": "CERTIN-2026-001",
                            "submitted_by": "analyst"}),
          body_check=lambda d: d.get("status") == "submitted_manually")
print(f"       submission reference={r.json().get('fields', {}).get('manual_submission', {}).get('reference_number')}")

check("GET /api/reports/999999 → 404", client.get("/api/reports/999999"), expected=404)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 7. Case actions ───────────────────────────────────────────────")
# Pick an open case that isn't the hero (which may now be in reported state)
open_cases = [c for c in client.get("/api/cases?status=open").json()]
if not open_cases:
    # hero might still be open — reset load a fresh one
    open_cases = client.get("/api/cases").json()

action_case_id = open_cases[0]["id"] if open_cases else hero_id

check("POST /action confirm",
      client.post(f"/api/cases/{action_case_id}/action",
                  json={"action": "confirm", "note": "Verified indicators of compromise.", "actor": "analyst"}),
      body_check=lambda d: d.get("status") == "confirmed")

# Blank note → 400
check("POST /action blank note → 400",
      client.post(f"/api/cases/{action_case_id}/action",
                  json={"action": "confirm", "note": "", "actor": "analyst"}),
      expected=400)

# Bad action → 400
check("POST /action invalid → 400",
      client.post(f"/api/cases/{action_case_id}/action",
                  json={"action": "nuke", "note": "test", "actor": "analyst"}),
      expected=400)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 8. Detected-at patch ──────────────────────────────────────────")
# Use an open case
open2 = [c for c in client.get("/api/cases").json() if c["status"] == "open"]
if open2:
    patch_id = open2[0]["id"]
    check(f"PATCH /api/cases/{patch_id}/detected_at",
          client.patch(f"/api/cases/{patch_id}/detected_at",
                       json={"detected_at": "2026-11-14T17:35:00Z",
                             "reason": "Backdated to first login event per analyst review."}),
          body_check=lambda d: "2026-11-14" in (d.get("detected_at") or ""))
    # Missing reason → 400
    check("PATCH detected_at no reason → 400",
          client.patch(f"/api/cases/{patch_id}/detected_at",
                       json={"detected_at": "2026-11-14T17:35:00Z", "reason": ""}),
          expected=400)
else:
    print("  (skipped — no open cases remain)")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 9. Alert restore ──────────────────────────────────────────────")
supp = client.get("/api/alerts?status=suppressed_benign").json()
print(f"       suppressed alerts: {len(supp)}")
if supp:
    aid = supp[0]["id"]
    check(f"POST /api/alerts/{aid}/restore",
          client.post(f"/api/alerts/{aid}/restore"),
          body_check=lambda d: d.get("status") == "new")
    # Restoring again (now 'new') → 400
    check(f"POST /api/alerts/{aid}/restore again → 400",
          client.post(f"/api/alerts/{aid}/restore"),
          expected=400)

check("POST /api/alerts/999999/restore → 404",
      client.post("/api/alerts/999999/restore"),
      expected=404)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 10. Alerts list ───────────────────────────────────────────────")
r = check("GET /api/alerts", client.get("/api/alerts"),
          body_check=lambda d: isinstance(d, list) and len(d) > 0)
print(f"       total alerts: {len(r.json())}")
r2 = check("GET /api/alerts?status=merged_duplicate",
           client.get("/api/alerts?status=merged_duplicate"),
           body_check=lambda d: all(a["status"] == "merged_duplicate" for a in d))
print(f"       merged_duplicate: {len(r2.json())}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 11. Audit log ─────────────────────────────────────────────────")
r = check("GET /api/audit", client.get("/api/audit"),
          body_check=lambda d: isinstance(d, list) and len(d) > 0)
events = r.json()
print(f"       {len(events)} audit events")
actions_seen = {e["action"] for e in events}
for expected_action in ("ingest", "pipeline_run", "report_generated",
                         "alert_suppressed", "alert_merged", "case_confirmed"):
    if expected_action in actions_seen:
        print(f"       {PASS} action '{expected_action}' present")
    else:
        print(f"       {FAIL} action '{expected_action}' MISSING")
        _failures.append(f"audit action '{expected_action}'")

r = check("GET /api/audit?action=ingest", client.get("/api/audit?action=ingest"),
          body_check=lambda d: all(e["action"] == "ingest" for e in d))
r = check("GET /api/audit/export?format=json",
          client.get("/api/audit/export?format=json"))
assert "attachment" in r.headers.get("content-disposition", ""), \
    "Missing Content-Disposition header on export"
r = check("GET /api/audit/export?format=csv",
          client.get("/api/audit/export?format=csv"))
assert r.headers.get("content-type", "").startswith("text/csv"), \
    f"Expected text/csv, got {r.headers.get('content-type')}"

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 12. Settings ──────────────────────────────────────────────────")
r = check("GET /api/settings", client.get("/api/settings"),
          body_check=lambda d: "settings" in d and "rules_yaml" in d)
s = r.json()
print(f"       settings keys={sorted(s['settings'].keys())}")
assert s["settings"]["correlation_window_hours"] == 6, "Default correlation window wrong"
assert len(s["rules_yaml"]) > 100, "rules_yaml too short"

r = check("PUT /api/settings (patch)",
          client.put("/api/settings",
                     json={"settings": {"dedupe_window_minutes": 20}, "actor": "analyst"}),
          body_check=lambda d: d["settings"]["dedupe_window_minutes"] == 20)
# Restore
check("PUT /api/settings (restore)",
      client.put("/api/settings",
                 json={"settings": {"dedupe_window_minutes": 10}, "actor": "analyst"}))

# Bad YAML → 400
check("PUT /api/settings bad YAML → 400",
      client.put("/api/settings",
                 json={"rules_yaml": "key: [\nbad yaml{{{\n", "actor": "analyst"}),
      expected=400)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 13. Alert ingest (JSON body) ──────────────────────────────────")
new_alerts = [
    {"source": "firewall", "source_alert_id": "E2E-FW-001",
     "timestamp": "2026-11-15T10:00:00Z", "title": "E2E test alert",
     "severity": "low", "category": "port_scan", "extra": {}},
]
r = check("POST /api/alerts/ingest (json array)",
          client.post("/api/alerts/ingest", json=new_alerts),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) >= 1)
print(f"       result: {r.json()}")

# Dict with 'alerts' key
r = check("POST /api/alerts/ingest (dict with alerts key)",
          client.post("/api/alerts/ingest",
                      json={"alerts": [
                          {"source": "endpoint_av", "source_alert_id": "E2E-AV-001",
                           "timestamp": "2026-11-15T10:01:00Z", "title": "E2E AV alert",
                           "severity": "medium", "category": "malware", "extra": {}}
                      ]}),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) >= 1)

# Missing required field → 400
check("POST /api/alerts/ingest missing field → 400",
      client.post("/api/alerts/ingest",
                  json=[{"source": "firewall", "title": "no id"}]),
      expected=400)

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 14. Alert ingest (file upload — JSON) ─────────────────────────")
json_file_data = json.dumps([
    {"source": "dlp", "source_alert_id": "UPLOAD-JSON-001",
     "timestamp": "2026-11-15T11:00:00Z", "title": "Upload JSON test",
     "severity": "high", "category": "data_exfiltration",
     "user": "upload_user", "extra": {"bytes_out": 500000}}
]).encode()
r = check("POST /api/alerts/ingest (multipart JSON file)",
          client.post("/api/alerts/ingest",
                      files={"file": ("alerts.json", io.BytesIO(json_file_data),
                                      "application/json")}),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) >= 1)
print(f"       result: {r.json()}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 15. Alert ingest (file upload — CSV) ──────────────────────────")
csv_data = (
    "source,source_alert_id,timestamp,title,severity,category,user,extra\n"
    'identity_provider,UPLOAD-CSV-001,2026-11-15T12:00:00Z,CSV upload test,high,'
    'suspicious_login,csv_user,"{""country"":""Romania""}"\n'
).encode()
r = check("POST /api/alerts/ingest (multipart CSV file)",
          client.post("/api/alerts/ingest",
                      files={"file": ("alerts.csv", io.BytesIO(csv_data),
                                      "text/csv")}),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) >= 1)
print(f"       result: {r.json()}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 16. Demo reset ────────────────────────────────────────────────")
r = check("POST /api/demo/reset", client.post("/api/demo/reset"),
          body_check=lambda d: d.get("ok") is True)

# After reset everything should be empty
r = check("GET /api/cases after reset",
          client.get("/api/cases"),
          body_check=lambda d: len(d) == 0)
r = check("GET /api/alerts after reset",
          client.get("/api/alerts"),
          body_check=lambda d: len(d) == 0)
dash2 = client.get("/api/dashboard").json()
assert dash2["funnel"]["ingested"] == 0, "Funnel ingested not 0 after reset"
print(f"       funnel after reset={dash2['funnel']}")

# ═══════════════════════════════════════════════════════════════════════════
print("\n── 17. Reload after reset works ──────────────────────────────────")
r = check("POST /api/demo/load after reset",
          client.post("/api/demo/load"),
          body_check=lambda d: d.get("ingest", {}).get("new", 0) > 0)
print(f"       re-loaded: {r.json()['ingest']}")

# ═══════════════════════════════════════════════════════════════════════════
print()
if _failures:
    print(f"═══ {len(_failures)} FAILURE(S) ═══")
    for f in _failures:
        print(f"  ✗  {f}")
    sys.exit(1)
else:
    print("═══ All route checks passed ✓ ═══")
    sys.exit(0)
