"""In-memory fake engine implementing the exact Section 7.2 interface.

Allows running API tests and development offline without database/ORM dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Self

# Default settings matching Section 7.2
DEFAULT_SETTINGS: dict[str, Any] = {
    "correlation_window_hours": 6,
    "dedupe_window_minutes": 10,
    "minutes_saved_per_alert": 5,
    "critical_assets": ["FILESRV-02", "CORE-BANK-DB", "VAULT-SRV-01"],
    "outbound_bytes_threshold": 1_000_000_000,
}

DEFAULT_RULES_YAML = """# Default suppression and correlation rules
suppression_rules:
  - id: benign_scanners
    reason: "Known security research scanner"
    condition:
      known_scanner: true
  - id: scheduled_backups
    reason: "Routine scheduled backup activity"
    condition:
      category: backup_activity
      scheduled: true
  - id: seen_countries
    reason: "Login from verified recognized location"
    condition:
      category: suspicious_login
      country_seen_before: true
  - id: test_hosts
    reason: "Test/sandbox environment"
    condition:
      host_prefix: "TEST-"

correlation_rules:
  - pattern: account_takeover_then_exfiltration
    description: "Suspicious login followed by mass file access and data exfiltration"
  - pattern: ransomware_behaviour
    description: "Suspicious process with mass file renaming and backup deletion"
  - pattern: phishing_to_compromise
    description: "Phishing lure followed by new device login and mailbox forwarding"
"""


@dataclass
class Alert:
    id: int
    source: str
    source_alert_id: str
    timestamp: str
    title: str
    description: str | None = None
    severity_raw: str = "low"
    category: str = "informational"
    user: str | None = None
    host: str | None = None
    src_ip: str | None = None
    dst_ip: str | None = None
    file: str | None = None
    process: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    status: str = "new"  # new, suppressed_benign, merged_duplicate, in_case, unlinked_low_priority
    suppression_reason: str | None = None
    duplicate_of: int | None = None
    duplicate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Case:
    id: int
    title: str
    created_at: str
    first_alert_at: str
    last_alert_at: str
    detected_at: str
    pattern: str | None = None
    score: int = 50
    score_breakdown: list[dict[str, Any]] = field(default_factory=list)
    severity: str = "medium"  # low <35, medium 35-59, high 60-79, critical >=80
    summary: str | None = None
    summary_source: str | None = None  # "llm" | "template"
    recommended_actions: list[str] = field(default_factory=list)
    status: str = "open"  # open, confirmed, dismissed, escalated, reported
    report_id: int | None = None
    entities: dict[str, list[str]] = field(
        default_factory=lambda: {"users": [], "hosts": [], "ips": []}
    )
    sources_count: int = 1
    alert_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseAlertLink:
    id: int
    case_id: int
    alert_id: int


@dataclass
class Report:
    id: int
    case_id: int
    incident_type: str
    fields: dict[str, Any]
    narrative: str
    generated_at: str
    status: str = "draft"  # draft, approved, submitted_manually
    version: int = 1
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEvent:
    id: int
    timestamp: str
    actor: str
    action: str
    target_type: str
    target_id: str | int | None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# In-memory storage state
class FakeStore:
    def __init__(self) -> None:
        self.alerts: dict[int, Alert] = {}
        self.cases: dict[int, Case] = {}
        self.reports: dict[int, Report] = {}
        self.audit_events: list[AuditEvent] = []
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.rules_yaml: str = DEFAULT_RULES_YAML
        self.alert_seq: int = 1
        self.case_seq: int = 1
        self.report_seq: int = 1
        self.audit_seq: int = 1

    def reset(self) -> None:
        self.alerts.clear()
        self.cases.clear()
        self.reports.clear()
        self.audit_events.clear()
        self.settings = dict(DEFAULT_SETTINGS)
        self.rules_yaml = DEFAULT_RULES_YAML
        self.alert_seq = 1
        self.case_seq = 1
        self.report_seq = 1
        self.audit_seq = 1


store = FakeStore()


def init_db() -> None:
    """Ensure database state is initialized."""
    # In-memory store is always ready


class _FakeSession:
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        pass

    def close(self) -> None:
        pass


def get_session() -> _FakeSession:
    """Return a session-like context manager."""
    return _FakeSession()


def reset_all() -> None:
    """Reset all tables and storage."""
    store.reset()


# Submodules container objects
class _Models:
    Alert = Alert
    Case = Case
    CaseAlertLink = CaseAlertLink
    Report = Report
    AuditEvent = AuditEvent


models = _Models()


class IngestModule:
    @staticmethod
    def ingest_alerts(
        raw: list[dict[str, Any]], actor: str = "system"
    ) -> dict[str, int]:
        received = len(raw)
        new = 0
        already_seen = 0

        # Existing (source, source_alert_id) keys
        existing_keys = {
            (a.source, a.source_alert_id) for a in store.alerts.values()
        }

        for item in raw:
            key = (item["source"], item["source_alert_id"])
            if key in existing_keys:
                already_seen += 1
                continue

            alert_id = store.alert_seq
            store.alert_seq += 1

            alert = Alert(
                id=alert_id,
                source=item["source"],
                source_alert_id=item["source_alert_id"],
                timestamp=item["timestamp"],
                title=item["title"],
                description=item.get("description"),
                severity_raw=item.get("severity", "low"),
                category=item.get("category", "informational"),
                user=item.get("user"),
                host=item.get("host"),
                src_ip=item.get("src_ip"),
                dst_ip=item.get("dst_ip"),
                file=item.get("file"),
                process=item.get("process"),
                raw=item.get("extra", {}),
                status="new",
            )
            store.alerts[alert_id] = alert
            existing_keys.add(key)
            new += 1

        audit.record(
            actor=actor,
            action="ingest_alerts",
            target_type="alerts",
            target_id=None,
            details={"received": received, "new": new, "already_seen": already_seen},
        )
        return {"received": received, "new": new, "already_seen": already_seen}


ingest = IngestModule()


class PipelineModule:
    @staticmethod
    def run_pipeline(actor: str = "system") -> dict[str, int]:
        suppressed = 0
        merged = 0
        in_cases = 0
        cases_created = 0
        unlinked_low_priority = 0

        # Process alerts in time order
        alerts = sorted(store.alerts.values(), key=lambda a: a.timestamp)

        # 1. Suppression of benign alerts
        for a in alerts:
            if a.status != "new":
                continue

            extra = a.raw or {}
            # Check suppression conditions
            if extra.get("known_scanner") or extra.get("scanner") in ("shodan", "censys", "shadowserver"):
                a.status = "suppressed_benign"
                a.suppression_reason = "Known security research scanner"
                suppressed += 1
            elif extra.get("scheduled") and a.category == "backup_activity":
                a.status = "suppressed_benign"
                a.suppression_reason = "Routine scheduled backup activity"
                suppressed += 1
            elif extra.get("country_seen_before") is True:
                a.status = "suppressed_benign"
                a.suppression_reason = "Login from verified recognized location"
                suppressed += 1
            elif a.host and a.host.startswith("TEST-"):
                a.status = "suppressed_benign"
                a.suppression_reason = "Test/sandbox environment"
                suppressed += 1
            elif extra.get("benign_type") == "edr_info":
                a.status = "suppressed_benign"
                a.suppression_reason = "Routine informational endpoint telemetry"
                suppressed += 1

        # 2. De-duplication (merge duplicate repeats)
        seen_repeats: dict[str, Alert] = {}
        for a in alerts:
            if a.status != "new":
                continue
            dedupe_key = f"{a.source}:{a.title}:{a.host}:{a.src_ip}"
            if dedupe_key in seen_repeats:
                primary = seen_repeats[dedupe_key]
                a.status = "merged_duplicate"
                a.duplicate_of = primary.id
                primary.duplicate_count += 1
                merged += 1
            else:
                seen_repeats[dedupe_key] = a

        # 3. Correlation into Cases for attack scenarios
        # Scenario A (Hero): r.sharma
        hero_alerts = [
            a for a in alerts if a.status == "new" and a.raw.get("scenario") == "hero"
        ]
        if hero_alerts:
            case_id = store.case_seq
            store.case_seq += 1
            users = list({a.user for a in hero_alerts if a.user})
            hosts = list({a.host for a in hero_alerts if a.host})
            ips = list({a.src_ip for a in hero_alerts if a.src_ip})
            created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

            case = Case(
                id=case_id,
                title="Account takeover followed by data exfiltration",
                created_at=created_at,
                first_alert_at=hero_alerts[0].timestamp,
                last_alert_at=hero_alerts[-1].timestamp,
                detected_at=hero_alerts[0].timestamp,
                pattern="account_takeover_then_exfiltration",
                score=85,
                score_breakdown=[
                    {"factor": "Multiple distinct data sources", "points": 25, "explanation": "Events from 4 security sources"},
                    {"factor": "Critical asset involvement", "points": 30, "explanation": "Target host FILESRV-02"},
                    {"factor": "Anomalous geographic origin", "points": 15, "explanation": "Login from Romania"},
                    {"factor": "Large outbound volume", "points": 15, "explanation": "Over 2 GB transferred outbound"},
                ],
                severity="critical",
                status="open",
                entities={"users": users, "hosts": hosts, "ips": ips},
                sources_count=len({a.source for a in hero_alerts}),
                alert_ids=[a.id for a in hero_alerts],
            )
            store.cases[case_id] = case
            for a in hero_alerts:
                a.status = "in_case"
                in_cases += 1
            cases_created += 1

        # Scenario B: a.menon phishing
        phish_alerts = [
            a for a in alerts if a.status == "new" and a.raw.get("scenario") == "phishing"
        ]
        if phish_alerts:
            case_id = store.case_seq
            store.case_seq += 1
            created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            case = Case(
                id=case_id,
                title="Phishing email leading to mailbox forwarding compromise",
                created_at=created_at,
                first_alert_at=phish_alerts[0].timestamp,
                last_alert_at=phish_alerts[-1].timestamp,
                detected_at=phish_alerts[0].timestamp,
                pattern="phishing_to_compromise",
                score=72,
                score_breakdown=[
                    {"factor": "Phishing lure clicked", "points": 30, "explanation": "Credential harvester accessed"},
                    {"factor": "Mailbox auto-forwarding rule", "points": 42, "explanation": "External exfiltration rule configured"},
                ],
                severity="high",
                status="open",
                entities={"users": ["a.menon"], "hosts": [], "ips": ["197.210.64.12"]},
                sources_count=len({a.source for a in phish_alerts}),
                alert_ids=[a.id for a in phish_alerts],
            )
            store.cases[case_id] = case
            for a in phish_alerts:
                a.status = "in_case"
                in_cases += 1
            cases_created += 1

        # Scenario C: WS-ACCTS-07 ransomware
        rw_alerts = [
            a for a in alerts if a.status == "new" and a.raw.get("scenario") == "ransomware"
        ]
        if rw_alerts:
            case_id = store.case_seq
            store.case_seq += 1
            created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            case = Case(
                id=case_id,
                title="Ransomware execution and shadow copy tampering",
                created_at=created_at,
                first_alert_at=rw_alerts[0].timestamp,
                last_alert_at=rw_alerts[-1].timestamp,
                detected_at=rw_alerts[0].timestamp,
                pattern="ransomware_behaviour",
                score=92,
                score_breakdown=[
                    {"factor": "Mass file encryption", "points": 50, "explanation": "1,250 files renamed with .locked extension"},
                    {"factor": "Backup deletion attempt", "points": 42, "explanation": "vssadmin shadow deletion requested"},
                ],
                severity="critical",
                status="open",
                entities={"users": ["v.patel"], "hosts": ["WS-ACCTS-07"], "ips": []},
                sources_count=len({a.source for a in rw_alerts}),
                alert_ids=[a.id for a in rw_alerts],
            )
            store.cases[case_id] = case
            for a in rw_alerts:
                a.status = "in_case"
                in_cases += 1
            cases_created += 1

        # 4. Remaining new alerts become unlinked_low_priority
        for a in alerts:
            if a.status == "new":
                a.status = "unlinked_low_priority"
                unlinked_low_priority += 1

        audit.record(
            actor=actor,
            action="run_pipeline",
            target_type="pipeline",
            target_id=None,
            details={
                "suppressed": suppressed,
                "merged": merged,
                "in_cases": in_cases,
                "cases_created": cases_created,
                "unlinked_low_priority": unlinked_low_priority,
            },
        )
        return {
            "suppressed": suppressed,
            "merged": merged,
            "in_cases": in_cases,
            "cases_created": cases_created,
            "unlinked_low_priority": unlinked_low_priority,
        }


pipeline = PipelineModule()


class AuditModule:
    @staticmethod
    def record(
        actor: str,
        action: str,
        target_type: str,
        target_id: str | int | None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event_id = store.audit_seq
        store.audit_seq += 1
        now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = AuditEvent(
            id=event_id,
            timestamp=now_utc,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
        )
        store.audit_events.append(event)
        return event

    @staticmethod
    def list_events(
        action: str | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        limit: int = 500,
    ) -> list[AuditEvent]:
        res = list(store.audit_events)
        if action:
            res = [e for e in res if e.action == action]
        if target_type:
            res = [e for e in res if e.target_type == target_type]
        if target_id is not None:
            res = [e for e in res if str(e.target_id) == str(target_id)]
        return res[-limit:]


audit = AuditModule()


class CasesModule:
    @staticmethod
    def apply_action(
        case_id: int, action: str, note: str, actor: str = "analyst"
    ) -> Case:
        if not note or not note.strip():
            raise ValueError("Note is required for case action")
        if action not in ("confirm", "dismiss", "escalate"):
            raise ValueError(f"Invalid case action: {action}")

        case = store.cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        status_map = {
            "confirm": "confirmed",
            "dismiss": "dismissed",
            "escalate": "escalated",
        }
        case.status = status_map[action]

        audit.record(
            actor=actor,
            action=f"case_{action}",
            target_type="case",
            target_id=case_id,
            details={"note": note, "new_status": case.status},
        )
        return case

    @staticmethod
    def set_detected_at(
        case_id: int, new_dt_iso: str, reason: str, actor: str = "analyst"
    ) -> Case:
        if not reason or not reason.strip():
            raise ValueError("Reason is required to update detected_at")

        case = store.cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        old_dt = case.detected_at
        case.detected_at = new_dt_iso

        audit.record(
            actor=actor,
            action="case_set_detected_at",
            target_type="case",
            target_id=case_id,
            details={"old_detected_at": old_dt, "new_detected_at": new_dt_iso, "reason": reason},
        )
        return case

    @staticmethod
    def save_summary(
        case_id: int,
        summary: str,
        source: str,
        actions: list[str],
    ) -> Case:
        case = store.cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        case.summary = summary
        case.summary_source = source
        case.recommended_actions = actions
        return case


cases = CasesModule()


class AlertsModule:
    @staticmethod
    def restore(alert_id: int, actor: str = "analyst") -> dict[str, Any]:
        alert = store.alerts.get(alert_id)
        if not alert:
            raise KeyError(f"Alert {alert_id} not found")

        prev_status = alert.status
        alert.status = "new"
        alert.suppression_reason = None
        alert.duplicate_of = None

        audit.record(
            actor=actor,
            action="restore_alert",
            target_type="alert",
            target_id=alert_id,
            details={"previous_status": prev_status},
        )
        return {"ok": True, "alert_id": alert_id}


alerts = AlertsModule()


class SettingsModule:
    @staticmethod
    def get_settings() -> dict[str, Any]:
        return dict(store.settings)

    @staticmethod
    def update_settings(d: dict[str, Any]) -> dict[str, Any]:
        store.settings.update(d)
        return dict(store.settings)

    @staticmethod
    def get_rules_yaml() -> str:
        return store.rules_yaml

    @staticmethod
    def save_rules_yaml(text: str) -> None:
        store.rules_yaml = text


settings = SettingsModule()
