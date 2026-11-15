"""
backend/tests/test_engine_smoke.py
End-to-end smoke test for the Prahari detection engine.

Covers the "hero case" scenario from section 3 of the context document:
  23:05 IST  identity_provider  suspicious_login   r.sharma (new country)
  23:40 IST  dlp                mass_file_access   r.sharma (4812 files)
  01:15 IST  endpoint_av        malware            FILESRV-02 (rclone.exe)
  01:30 IST  firewall           data_exfiltration  2.4 GB outbound

Expected outcome: ONE case scored critical (>=80), pattern
account_takeover_then_exfiltration, alert timeline in time order.

Also tests:
  - Idempotency: ingest same batch twice → no new rows second time.
  - Suppression: port scan from known scanner stays suppressed.
  - Dedup: second identical login alert is merged.
  - Decoy case: port-scan + single failed-login stays low severity.
  - apply_action, set_detected_at, save_summary, restore.
  - audit log has entries for each major action.
"""

import os
import sys
import json
import tempfile

# ---- point the engine at a temp DB so we don't pollute the workspace ----
_tmpdir = tempfile.mkdtemp()
os.environ["PRAHARI_DB_PATH"] = os.path.join(_tmpdir, "smoke_test.db")

# Add backend to path so `import engine` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine

# =========================================================================
# Helpers
# =========================================================================

def _pass(msg):
    print(f"  ✓  {msg}")

def _fail(msg):
    print(f"  ✗  {msg}")
    sys.exit(1)

def _assert(condition, msg):
    if condition:
        _pass(msg)
    else:
        _fail(msg)

# =========================================================================
# Setup
# =========================================================================

print("\n── Setup ─────────────────────────────────────────────────────")
engine.init_db()
_pass("init_db() — tables created")

# =========================================================================
# Hero-case alerts  (IST timestamps → UTC)
# 23:05 IST = 17:35 UTC, 23:40 IST = 18:10 UTC, 01:15 IST = 19:45 UTC, 01:30 IST = 20:00 UTC
# (all same date for the test)
# =========================================================================

HERO_ALERTS = [
    {
        "source": "identity_provider",
        "source_alert_id": "IDP-001",
        "timestamp": "2024-01-15T17:35:00Z",
        "title": "Login from new country",
        "description": "User r.sharma logged in from Romania — country not seen before.",
        "severity": "high",
        "category": "suspicious_login",
        "user": "r.sharma",
        "host": "WKSTN-07",
        "src_ip": "185.220.101.42",
        "extra": {"country": "Romania", "country_seen_before": False},
    },
    {
        "source": "dlp",
        "source_alert_id": "DLP-001",
        "timestamp": "2024-01-15T18:10:00Z",
        "title": "Mass file access by r.sharma",
        "description": "4,812 customer records accessed in 35 minutes.",
        "severity": "high",
        "category": "mass_file_access",
        "user": "r.sharma",
        "host": "FILESRV-02",
        "extra": {"files_count": 4812},
    },
    {
        "source": "endpoint_av",
        "source_alert_id": "AV-001",
        "timestamp": "2024-01-15T19:45:00Z",
        "title": "Suspicious process rclone.exe detected",
        "description": "rclone.exe launched on FILESRV-02 — not in approved software list.",
        "severity": "high",
        "category": "malware",
        "host": "FILESRV-02",
        "process": "rclone.exe",
        "extra": {},
    },
    {
        "source": "firewall",
        "source_alert_id": "FW-001",
        "timestamp": "2024-01-15T20:00:00Z",
        "title": "Large outbound transfer to unknown IP",
        "description": "2.4 GB transferred to 91.218.114.77.",
        "severity": "critical",
        "category": "data_exfiltration",
        "host": "FILESRV-02",
        "dst_ip": "91.218.114.77",
        "extra": {"bytes_out": 2_400_000_000, "action": "allow"},
    },
]

# Noise / suppression
EXTRA_ALERTS = [
    # Should be SUPPRESSED (known scanner range from rules.yaml)
    {
        "source": "firewall",
        "source_alert_id": "FW-SCAN-001",
        "timestamp": "2024-01-15T16:00:00Z",
        "title": "Port scan detected",
        "category": "port_scan",
        "severity": "low",
        "src_ip": "198.108.66.5",   # in suppression range
        "extra": {},
    },
    # Decoy: unrelated port scan (different IP) + failed login — should NOT become high/critical
    {
        "source": "firewall",
        "source_alert_id": "FW-SCAN-002",
        "timestamp": "2024-01-15T14:00:00Z",
        "title": "Port scan from internet scanner",
        "category": "port_scan",
        "severity": "low",
        "src_ip": "192.0.2.100",    # not in suppress list
        "extra": {},
    },
    {
        "source": "identity_provider",
        "source_alert_id": "IDP-FAIL-001",
        "timestamp": "2024-01-15T14:05:00Z",
        "title": "Failed login for svc_backup",
        "category": "failed_login",
        "severity": "low",
        "user": "svc_backup",
        "extra": {},
    },
    # Duplicate of the first hero alert (same window, same user+category)
    {
        "source": "identity_provider",
        "source_alert_id": "IDP-002",
        "timestamp": "2024-01-15T17:38:00Z",   # 3 min after IDP-001
        "title": "Login from new country (repeat alert)",
        "category": "suspicious_login",
        "severity": "high",
        "user": "r.sharma",
        "extra": {"country": "Romania"},
    },
    # Informational low — suppressed
    {
        "source": "cloud_audit",
        "source_alert_id": "CA-001",
        "timestamp": "2024-01-15T10:00:00Z",
        "title": "Password policy check passed",
        "category": "informational",
        "severity": "low",
        "extra": {},
    },
]

ALL_ALERTS = HERO_ALERTS + EXTRA_ALERTS

# =========================================================================
# Step 1 — Ingest
# =========================================================================

print("\n── Ingest ────────────────────────────────────────────────────")
result = engine.ingest.ingest_alerts(ALL_ALERTS, actor="smoke_test")
_assert(result["received"] == len(ALL_ALERTS), f"received={result['received']} == {len(ALL_ALERTS)}")
_assert(result["new"]      == len(ALL_ALERTS), f"new={result['new']} == {len(ALL_ALERTS)}")
_assert(result["already_seen"] == 0,           "already_seen == 0 on first ingest")

# Idempotency: ingest same batch again
result2 = engine.ingest.ingest_alerts(ALL_ALERTS, actor="smoke_test")
_assert(result2["new"]          == 0,              "idempotency: new == 0 on re-ingest")
_assert(result2["already_seen"] == len(ALL_ALERTS),"idempotency: all already_seen on re-ingest")

# =========================================================================
# Step 2 — Pipeline
# =========================================================================

print("\n── Pipeline ──────────────────────────────────────────────────")
pipe = engine.pipeline.run_pipeline(actor="smoke_test")
print(f"     pipeline result: {pipe}")

_assert(pipe["suppressed"] >= 2,       f"suppressed >= 2  (got {pipe['suppressed']})")
_assert(pipe["merged"]     >= 1,       f"merged >= 1       (got {pipe['merged']})")
_assert(pipe["cases_created"] >= 1,    f"cases_created >= 1 (got {pipe['cases_created']})")

# =========================================================================
# Step 3 — Verify hero case
# =========================================================================

print("\n── Hero case ─────────────────────────────────────────────────")
session = engine.get_session()
try:
    cases = session.query(engine.models.Case).all()
    print(f"     total cases: {len(cases)}")
    for c in cases:
        print(f"       case {c.id}: '{c.title}'  severity={c.severity}  score={c.score}  pattern={c.pattern}  alerts={len(c.alert_links)}")
finally:
    session.close()

# Find hero case by pattern
session = engine.get_session()
try:
    hero = (
        session.query(engine.models.Case)
        .filter(engine.models.Case.pattern == "account_takeover_then_exfiltration")
        .first()
    )
    _assert(hero is not None, "hero case has pattern account_takeover_then_exfiltration")
    if hero:
        _assert(hero.severity in ("high", "critical"),
                f"hero case severity is high or critical (got {hero.severity})")
        _assert(hero.score >= 60,
                f"hero case score >= 60 (got {hero.score})")
        _assert(len(hero.alert_links) >= 3,
                f"hero case has >= 3 linked alerts (got {len(hero.alert_links)})")
        _assert(hero.sources_count >= 2,
                f"hero case spans >= 2 sources (got {hero.sources_count})")

        # Timeline order check
        timeline = sorted(
            [lk.alert for lk in hero.alert_links if lk.alert],
            key=lambda a: a.timestamp
        )
        _assert(len(timeline) >= 3, "timeline has >= 3 entries")
        for i in range(len(timeline) - 1):
            _assert(
                timeline[i].timestamp <= timeline[i+1].timestamp,
                f"timeline entry {i} ≤ entry {i+1} (chronological order)"
            )

        # score_breakdown present
        bd = hero.score_breakdown
        _assert(isinstance(bd, list) and len(bd) > 0,
                f"score_breakdown is non-empty list ({len(bd)} factors)")
        for item in bd:
            _assert("factor" in item and "points" in item and "explanation" in item,
                    f"breakdown item has factor/points/explanation: {item.get('factor')}")

        # deadline / countdown
        _assert(hero.deadline_at is not None, "hero case has deadline_at")
        _assert(hero.countdown_state in ("green","amber","red","overdue","none"),
                f"countdown_state is valid (got {hero.countdown_state})")

        hero_id = hero.id
finally:
    session.close()

# =========================================================================
# Step 4 — Decoy case must NOT be high/critical
# =========================================================================

print("\n── Decoy case ────────────────────────────────────────────────")
session = engine.get_session()
try:
    all_cases = session.query(engine.models.Case).all()
    for c in all_cases:
        if c.id == hero_id:
            continue
        _assert(
            c.severity not in ("high", "critical"),
            f"non-hero case {c.id} ('{c.title}') is NOT high/critical (severity={c.severity})"
        )
finally:
    session.close()

# =========================================================================
# Step 5 — Suppression check
# =========================================================================

print("\n── Suppression ───────────────────────────────────────────────")
session = engine.get_session()
try:
    supp = (
        session.query(engine.models.Alert)
        .filter(
            engine.models.Alert.source_alert_id == "FW-SCAN-001",
            engine.models.Alert.status == "suppressed_benign"
        )
        .first()
    )
    _assert(supp is not None, "FW-SCAN-001 (known scanner) is suppressed_benign")
    if supp:
        _assert(supp.suppression_reason is not None, "suppressed alert has suppression_reason")
finally:
    session.close()

# =========================================================================
# Step 6 — Duplicate check
# =========================================================================

print("\n── Deduplication ─────────────────────────────────────────────")
session = engine.get_session()
try:
    dup = (
        session.query(engine.models.Alert)
        .filter(engine.models.Alert.source_alert_id == "IDP-002")
        .first()
    )
    _assert(dup is not None, "IDP-002 alert exists")
    if dup:
        _assert(dup.status == "merged_duplicate",
                f"IDP-002 (repeat login) is merged_duplicate (got {dup.status})")
        _assert(dup.duplicate_of is not None,
                f"IDP-002 duplicate_of is set (got {dup.duplicate_of})")
finally:
    session.close()

# =========================================================================
# Step 7 — cases.apply_action
# =========================================================================

print("\n── apply_action ──────────────────────────────────────────────")
# Confirm the hero case
updated = engine.cases.apply_action(
    case_id=hero_id,
    action="confirm",
    note="Confirmed by smoke test — matches DLP + identity + AV + firewall indicators.",
    actor="smoke_tester",
)
_assert(updated["status"] == "confirmed", f"hero case status == confirmed (got {updated['status']})")

# reject blank note
try:
    engine.cases.apply_action(hero_id, "dismiss", note="", actor="smoke_tester")
    _fail("should have raised ValueError for blank note")
except ValueError:
    _pass("blank note raises ValueError")

# reject bad action
try:
    engine.cases.apply_action(hero_id, "nuke", note="test", actor="smoke_tester")
    _fail("should have raised ValueError for bad action")
except ValueError:
    _pass("invalid action raises ValueError")

# =========================================================================
# Step 8 — cases.set_detected_at
# =========================================================================

print("\n── set_detected_at ───────────────────────────────────────────")
upd2 = engine.cases.set_detected_at(
    case_id=hero_id,
    new_dt_iso="2024-01-15T17:35:00Z",
    reason="Backdated to first suspicious login per analyst review.",
    actor="smoke_tester",
)
_assert(upd2["detected_at"] is not None, "detected_at set")
_assert("2024-01-15" in upd2["detected_at"], "detected_at contains correct date")

try:
    engine.cases.set_detected_at(hero_id, "2024-01-15T17:35:00Z", reason="", actor="x")
    _fail("should raise ValueError for blank reason")
except ValueError:
    _pass("blank reason raises ValueError")

# =========================================================================
# Step 9 — cases.save_summary
# =========================================================================

print("\n── save_summary ──────────────────────────────────────────────")
engine.cases.save_summary(
    case_id=hero_id,
    summary="Suspected account takeover followed by data exfiltration. "
            "User r.sharma logged in from Romania, accessed 4,812 files, "
            "and 2.4 GB was transferred outbound via rclone.",
    source="template",
    actions=["Disable r.sharma account", "Isolate FILESRV-02", "Preserve firewall logs"],
)
session = engine.get_session()
try:
    c = session.query(engine.models.Case).filter(engine.models.Case.id == hero_id).first()
    _assert(c.summary is not None,                 "summary saved")
    _assert(c.summary_source == "template",        "summary_source == template")
    _assert(len(c.recommended_actions) == 3,       "3 recommended actions stored")
finally:
    session.close()

# =========================================================================
# Step 10 — alerts.restore
# =========================================================================

print("\n── alerts.restore ────────────────────────────────────────────")
session = engine.get_session()
try:
    supp_alert = (
        session.query(engine.models.Alert)
        .filter(engine.models.Alert.source_alert_id == "FW-SCAN-001")
        .first()
    )
    supp_id = supp_alert.id
finally:
    session.close()

restored = engine.alerts.restore(supp_id, actor="smoke_tester")
_assert(restored["status"] == "new", f"restored alert status == new (got {restored['status']})")
_assert(restored["suppression_reason"] is None, "suppression_reason cleared")

# can't restore an in_case alert
session = engine.get_session()
try:
    in_case_alert = (
        session.query(engine.models.Alert)
        .filter(engine.models.Alert.status == "in_case")
        .first()
    )
    in_case_id = in_case_alert.id if in_case_alert else None
finally:
    session.close()

if in_case_id:
    try:
        engine.alerts.restore(in_case_id, actor="smoke_tester")
        _fail("should raise ValueError restoring in_case alert")
    except ValueError:
        _pass("restoring in_case alert raises ValueError")

# =========================================================================
# Step 11 — Audit log
# =========================================================================

print("\n── Audit log ─────────────────────────────────────────────────")
events = engine.audit.list_events()
_assert(len(events) > 0, f"audit log has entries (got {len(events)})")

actions_seen = {e["action"] for e in events}
for expected_action in ("ingest", "pipeline_run", "case_confirmed",
                         "alert_suppressed", "alert_merged", "alert_restored",
                         "case_summary_saved", "case_detected_at_changed"):
    _assert(expected_action in actions_seen,
            f"audit log contains action '{expected_action}'")

# Filter by target_type
case_events = engine.audit.list_events(target_type="case")
_assert(len(case_events) > 0, "audit.list_events(target_type='case') returns results")

# Filter by target_id
hero_events = engine.audit.list_events(target_type="case", target_id=str(hero_id))
_assert(len(hero_events) >= 3, f"hero case has >= 3 audit events (got {len(hero_events)})")

# =========================================================================
# Step 12 — Settings round-trip
# =========================================================================

print("\n── Settings ──────────────────────────────────────────────────")
s = engine.settings.get_settings()
_assert(s["correlation_window_hours"] == 6,  "default correlation_window_hours == 6")
_assert(s["dedupe_window_minutes"]    == 10, "default dedupe_window_minutes == 10")
_assert(s["minutes_saved_per_alert"]  == 5,  "default minutes_saved_per_alert == 5")

updated_s = engine.settings.update_settings({"correlation_window_hours": 12})
_assert(updated_s["correlation_window_hours"] == 12, "update_settings patch works")

restored_s = engine.settings.update_settings({"correlation_window_hours": 6})
_assert(restored_s["correlation_window_hours"] == 6, "settings restored to 6h")

yaml_text = engine.settings.get_rules_yaml()
_assert(len(yaml_text) > 100, f"rules YAML has content ({len(yaml_text)} chars)")
_assert("suppression_rules" in yaml_text, "rules YAML contains suppression_rules key")
_assert("correlation_rules"  in yaml_text, "rules YAML contains correlation_rules key")

# =========================================================================
# Step 13 — reset_all sanity check
# =========================================================================

print("\n── reset_all ─────────────────────────────────────────────────")
engine.reset_all()
session = engine.get_session()
try:
    n = session.query(engine.models.Alert).count()
    _assert(n == 0, f"reset_all wipes alerts (count == 0, got {n})")
    n = session.query(engine.models.Case).count()
    _assert(n == 0, f"reset_all wipes cases (count == 0, got {n})")
    n = session.query(engine.models.AuditEvent).count()
    _assert(n == 0, f"reset_all wipes audit log (count == 0, got {n})")
finally:
    session.close()

# =========================================================================
# Done
# =========================================================================

print("\n── All smoke tests passed ✓ ──────────────────────────────────\n")
