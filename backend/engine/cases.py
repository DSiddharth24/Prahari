"""
engine/cases.py
Human-analyst actions on cases.

Public interface (section 7.2):
    apply_action(case_id, action, note, actor)
        # action in {"confirm", "dismiss", "escalate"}  — note required
    set_detected_at(case_id, new_dt_iso, reason, actor)
        # reason required
    save_summary(case_id, summary, source, actions)
        # source: "llm" | "template"
"""

import json
from datetime import timezone
from dateutil.parser import parse as parse_dt

from .db import get_session
from .models import Case
from . import audit as _audit

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"confirm", "dismiss", "escalate"}

# Map action verb → new case status
_ACTION_TO_STATUS = {
    "confirm":  "confirmed",
    "dismiss":  "dismissed",
    "escalate": "escalated",
}


def _get_case_or_raise(session, case_id: int) -> Case:
    case = session.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise ValueError(f"Case {case_id} not found")
    return case


# ---------------------------------------------------------------------------
# public
# ---------------------------------------------------------------------------

def apply_action(case_id: int, action: str, note: str, actor: str = "analyst") -> dict:
    """
    Apply a human analyst action to a case.

    Parameters
    ----------
    case_id : int
    action  : "confirm" | "dismiss" | "escalate"
    note    : required free-text reason (enforced — raises ValueError if blank)
    actor   : username or "analyst"

    Returns the updated CaseListItem dict.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid action '{action}'. Must be one of: {sorted(_VALID_ACTIONS)}")
    if not note or not str(note).strip():
        raise ValueError("A note is required for confirm/dismiss/escalate actions.")

    session = get_session()
    try:
        case = _get_case_or_raise(session, case_id)
        old_status = case.status
        new_status = _ACTION_TO_STATUS[action]
        case.status = new_status

        session.commit()

        _audit.record(
            actor=actor,
            action=f"case_{action}ed",          # e.g. "case_confirmed"
            target_type="case",
            target_id=str(case_id),
            details={"note": note, "old_status": old_status, "new_status": new_status},
        )

        session.refresh(case)
        return case.to_list_item()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_detected_at(
    case_id: int,
    new_dt_iso: str,
    reason: str,
    actor: str = "analyst",
) -> dict:
    """
    Change the detected_at timestamp on a case.
    A written reason is mandatory (audit-logged, section 8).

    Parameters
    ----------
    case_id    : int
    new_dt_iso : ISO-8601 string; naive timestamps assumed UTC
    reason     : required explanation
    actor      : username or "analyst"

    Returns the updated CaseListItem dict.
    """
    if not reason or not str(reason).strip():
        raise ValueError("A reason is required when changing detected_at.")

    # Parse and ensure UTC-aware
    dt = parse_dt(str(new_dt_iso))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)

    session = get_session()
    try:
        case = _get_case_or_raise(session, case_id)
        old_dt = case.detected_at.isoformat() if case.detected_at else None
        case.detected_at = dt

        session.commit()

        _audit.record(
            actor=actor,
            action="case_detected_at_changed",
            target_type="case",
            target_id=str(case_id),
            details={
                "old_detected_at": old_dt,
                "new_detected_at": dt.isoformat(),
                "reason": reason,
            },
        )

        session.refresh(case)
        return case.to_list_item()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_summary(
    case_id: int,
    summary: str,
    source: str,
    actions: list[str],
) -> dict:
    """
    Persist a case summary (from LLM or template).

    Parameters
    ----------
    case_id : int
    summary : plain-English narrative
    source  : "llm" | "template"
    actions : list of recommended action strings

    Returns the updated CaseListItem dict.
    """
    if source not in ("llm", "template"):
        raise ValueError("source must be 'llm' or 'template'.")

    session = get_session()
    try:
        case = _get_case_or_raise(session, case_id)
        case.summary              = summary
        case.summary_source       = source
        case.recommended_actions  = actions   # uses the property setter → JSON

        session.commit()

        _audit.record(
            actor="system",
            action="case_summary_saved",
            target_type="case",
            target_id=str(case_id),
            details={"source": source, "actions_count": len(actions)},
        )

        session.refresh(case)
        return case.to_list_item()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
