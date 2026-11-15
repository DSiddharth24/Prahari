"""
engine/__init__.py
Public surface of the Prahari detection engine consumed by Part 2 (API layer).

Interface contract: section 7.2 of the project context document.

Exposed names
-------------
init_db()           Create all tables (safe to call multiple times).
get_session()       Return a new SQLAlchemy Session (caller closes it).
reset_all()         Drop and recreate all tables (used by demo reset).

models              ORM classes: Alert, Case, CaseAlertLink, Report, AuditEvent

audit.record(actor, action, target_type, target_id, details=None)
audit.list_events(action, target_type, target_id, limit=500) -> list[dict]

ingest.ingest_alerts(raw, actor="system") -> {received, new, already_seen}

pipeline.run_pipeline(actor="system")
    -> {suppressed, merged, in_cases, cases_created, unlinked_low_priority}

cases.apply_action(case_id, action, note, actor)   # confirm|dismiss|escalate
cases.set_detected_at(case_id, new_dt_iso, reason, actor)
cases.save_summary(case_id, summary, source, actions)

alerts.restore(alert_id, actor)

settings.get_settings()          -> dict
settings.update_settings(d)      -> dict
settings.get_rules_yaml()        -> str
settings.save_rules_yaml(text)   -> None
"""

from .db import init_db, get_session, reset_all
from . import models, audit, ingest, pipeline, cases, alerts, settings

__all__ = [
    # DB lifecycle
    "init_db",
    "get_session",
    "reset_all",
    # submodules
    "models",
    "audit",
    "ingest",
    "pipeline",
    "cases",
    "alerts",
    "settings",
]
