"""
engine/audit.py
Append-only audit log.  Every state change in the system writes one AuditEvent row.
Rows are never updated or deleted (section 7.3 / section 8).

Public interface (section 7.2):
    record(actor, action, target_type, target_id, details=None, session=None)
    list_events(action=None, target_type=None, target_id=None, limit=500) -> list[dict]

The optional `session` parameter lets callers (e.g. the pipeline) reuse their
existing open transaction.  When a session is supplied the function only calls
flush(); the caller is responsible for the final commit.  When no session is
supplied a new one is opened, committed, and closed automatically.
"""

import json
from .db import get_session
from .models import AuditEvent


def record(
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
    session=None,
) -> AuditEvent:
    """
    Write one audit event.

    Parameters
    ----------
    actor       : who triggered the event (e.g. "system", "analyst", a username)
    action      : what happened  (e.g. "ingest", "case_confirmed", "pipeline_run")
    target_type : type of the affected object  (e.g. "alert", "case", "report")
    target_id   : str representation of the PK / ID of the affected object
    details     : optional free-form dict for extra context
    session     : if supplied, flush into this session; otherwise open/commit/close own session
    """
    ev = AuditEvent(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details_raw=json.dumps(details) if details is not None else None,
    )

    if session is not None:
        # Caller owns the transaction — just flush so the row is visible in the session
        session.add(ev)
        session.flush()
        return ev

    # Standalone call — open a fresh session, commit, close
    own_session = get_session()
    try:
        own_session.add(ev)
        own_session.commit()
        own_session.refresh(ev)
        return ev
    except Exception:
        own_session.rollback()
        raise
    finally:
        own_session.close()


def list_events(
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """
    Return audit events as a list of dicts, newest first.
    All filter parameters are optional.
    """
    session = get_session()
    try:
        q = session.query(AuditEvent)
        if action:
            q = q.filter(AuditEvent.action == action)
        if target_type:
            q = q.filter(AuditEvent.target_type == target_type)
        if target_id is not None:
            q = q.filter(AuditEvent.target_id == str(target_id))
        rows = q.order_by(AuditEvent.timestamp.desc()).limit(limit).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()
