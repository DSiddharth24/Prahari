"""
engine/alerts.py
Alert-level operations available to the API layer.

Public interface (section 7.2):
    restore(alert_id, actor)
        Revert a suppressed_benign or unlinked_low_priority alert back to "new"
        so the pipeline can reprocess it.  Drops suppression_reason.
"""

from .db import get_session
from .models import Alert
from . import audit as _audit

_RESTORABLE_STATUSES = {"suppressed_benign", "unlinked_low_priority", "merged_duplicate"}


def restore(alert_id: int, actor: str = "analyst") -> dict:
    """
    Restore an alert to status 'new'.

    Parameters
    ----------
    alert_id : int
    actor    : username or "analyst"

    Returns the updated alert dict.

    Raises ValueError if the alert does not exist or its status is not restorable.
    """
    session = get_session()
    try:
        alert = session.query(Alert).filter(Alert.id == alert_id).first()
        if alert is None:
            raise ValueError(f"Alert {alert_id} not found.")
        if alert.status not in _RESTORABLE_STATUSES:
            raise ValueError(
                f"Alert {alert_id} has status '{alert.status}' and cannot be restored. "
                f"Only {sorted(_RESTORABLE_STATUSES)} are restorable."
            )

        old_status = alert.status
        alert.status             = "new"
        alert.suppression_reason = None
        alert.duplicate_of       = None

        session.commit()

        _audit.record(
            actor=actor,
            action="alert_restored",
            target_type="alert",
            target_id=str(alert_id),
            details={"old_status": old_status},
        )

        session.refresh(alert)
        return alert.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
