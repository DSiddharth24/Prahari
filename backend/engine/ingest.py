"""
engine/ingest.py
Alert ingestion.  Accepts raw alert dicts (section 7.1 schema) and persists them.

Public interface (section 7.2):
    ingest_alerts(raw: list[dict], actor="system") -> {received, new, already_seen}

Idempotency: (source, source_alert_id) is a natural key.
Any alert already present is skipped (already_seen counter increments).

Required fields: source, source_alert_id, timestamp, title
Optional fields: description, severity, category, user, host,
                 src_ip, dst_ip, file, process, extra
"""

import json
from datetime import timezone
from dateutil.parser import parse as parse_dt

from .db import get_session
from .models import Alert
from . import audit as _audit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_ts(raw_ts):
    """Parse a timestamp string into a timezone-aware UTC datetime."""
    if raw_ts is None:
        from datetime import datetime
        return datetime.now(timezone.utc)
    if hasattr(raw_ts, "tzinfo"):          # already a datetime
        dt = raw_ts
    else:
        dt = parse_dt(str(raw_ts))
    if dt.tzinfo is None:                  # treat naive timestamps as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalise_severity(val: str | None) -> str | None:
    """Accept any capitalisation; return a canonical lower-case severity or None."""
    if val is None:
        return None
    v = str(val).strip().lower()
    if v in ("low", "medium", "high", "critical"):
        return v
    # common aliases
    mapping = {
        "info":        "low",
        "informational": "low",
        "warn":        "medium",
        "warning":     "medium",
        "error":       "high",
        "crit":        "critical",
    }
    return mapping.get(v)


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

def ingest_alerts(raw: list[dict], actor: str = "system") -> dict:
    """
    Persist a list of raw alert dicts.

    Returns
    -------
    {"received": int, "new": int, "already_seen": int}
    """
    received     = len(raw)
    new_count    = 0
    already_seen = 0

    session = get_session()
    try:
        for item in raw:
            source          = str(item.get("source", "")).strip()
            source_alert_id = str(item.get("source_alert_id", "")).strip()

            if not source or not source_alert_id:
                # skip malformed entries silently — no source or ID to key on
                received -= 1
                continue

            # idempotency check
            exists = (
                session.query(Alert)
                .filter(Alert.source == source,
                        Alert.source_alert_id == source_alert_id)
                .first()
            )
            if exists:
                already_seen += 1
                continue

            alert = Alert(
                source=source,
                source_alert_id=source_alert_id,
                timestamp=_parse_ts(item.get("timestamp")),
                title=str(item.get("title", "(no title)")),
                description=item.get("description"),
                severity_raw=_normalise_severity(item.get("severity")),
                category=item.get("category"),
                user=item.get("user"),
                host=item.get("host"),
                src_ip=item.get("src_ip"),
                dst_ip=item.get("dst_ip"),
                file=item.get("file"),
                process=item.get("process"),
                raw=json.dumps(item),   # preserve the full payload including extra
                status="new",
            )
            session.add(alert)
            new_count += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    _audit.record(
        actor=actor,
        action="ingest",
        target_type="alert_batch",
        target_id=None,
        details={"received": received, "new": new_count, "already_seen": already_seen},
    )

    return {"received": received, "new": new_count, "already_seen": already_seen}
