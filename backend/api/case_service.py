"""Case and dashboard service layer for Prahari API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.api.engine_bridge import IS_FAKE, engine, get_session, models
from backend.api.engine_bridge import cases as engine_cases
from backend.api.engine_bridge import settings as engine_settings


def compute_countdown(
    detected_at: str | datetime | None,
    status: str,
    now: datetime | None = None,
) -> tuple[str | None, int | None, str]:
    """Compute 6-hour CERT-In countdown state.

    Rules:
      - deadline_at = detected_at + 6 hours (UTC ISO-8601 string)
      - seconds_remaining = (deadline_at - now).total_seconds() (can be negative)
      - countdown_state:
          * "none" if status in ("dismissed", "reported")
          * "overdue" if seconds_remaining < 0
          * "red" if 0 <= seconds_remaining < 3600 (under 1h)
          * "amber" if 3600 <= seconds_remaining <= 10800 (1-3h)
          * "green" if seconds_remaining > 10800 (more than 3h)
    """
    if not detected_at:
        return None, None, "none"

    if isinstance(detected_at, str):
        # Support UTC strings with 'Z' or offset
        clean_str = detected_at.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_str)
        except ValueError:
            return None, None, "none"
    else:
        dt = detected_at

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    deadline_dt = dt + timedelta(hours=6)
    deadline_at_iso = deadline_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)

    seconds_remaining = int((deadline_dt - now).total_seconds())

    if status in ("dismissed", "reported"):
        return deadline_at_iso, seconds_remaining, "none"
    if seconds_remaining < 0:
        return deadline_at_iso, seconds_remaining, "overdue"
    if 0 <= seconds_remaining < 3600:
        return deadline_at_iso, seconds_remaining, "red"
    if 3600 <= seconds_remaining <= 10800:
        return deadline_at_iso, seconds_remaining, "amber"
    return deadline_at_iso, seconds_remaining, "green"


def _format_case_list_item(
    case_data: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Format raw case fields into CaseListItem response shape."""
    detected_at = case_data.get("detected_at")
    status = case_data.get("status", "open")
    deadline_at, seconds_remaining, countdown_state = compute_countdown(
        detected_at, status, now=now
    )

    return {
        "id": case_data["id"],
        "title": case_data["title"],
        "score": case_data["score"],
        "severity": case_data["severity"],
        "status": status,
        "pattern": case_data.get("pattern"),
        "sources_count": case_data.get("sources_count", 1),
        "first_alert_at": case_data.get("first_alert_at"),
        "detected_at": detected_at,
        "deadline_at": deadline_at,
        "seconds_remaining": seconds_remaining,
        "countdown_state": countdown_state,
    }


def _get_raw_cases() -> list[dict[str, Any]]:
    """Retrieve all case records from storage (fake or real DB)."""
    if IS_FAKE:
        raw_list: list[dict[str, Any]] = []
        for case in engine.store.cases.values():
            d = case.to_dict()
            raw_list.append(d)
        return raw_list

    session = get_session()
    try:
        cases_orm = session.query(models.Case).all()
        return [c.to_detail() for c in cases_orm]
    finally:
        session.close()


def _get_raw_case_by_id(case_id: int) -> dict[str, Any] | None:
    """Retrieve a single raw case by ID."""
    if IS_FAKE:
        case = engine.store.cases.get(case_id)
        if not case:
            return None
        return case.to_dict()

    session = get_session()
    try:
        case = session.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            return None
        return case.to_detail()
    finally:
        session.close()


def _get_case_timeline(case_id: int) -> list[dict[str, Any]]:
    """Retrieve full alerts in chronological order for a case."""
    if IS_FAKE:
        case = engine.store.cases.get(case_id)
        if not case:
            return []
        alerts_list: list[dict[str, Any]] = []
        for aid in case.alert_ids:
            a = engine.store.alerts.get(aid)
            if a:
                alerts_list.append(a.to_dict())
        alerts_list.sort(key=lambda a: a["timestamp"])
        return alerts_list

    session = get_session()
    try:
        case = session.query(models.Case).filter(models.Case.id == case_id).first()
        if not case:
            return []
        timeline: list[dict[str, Any]] = []
        for link in case.alert_links:
            if link.alert:
                timeline.append(link.alert.to_dict())
        timeline.sort(key=lambda a: a["timestamp"])
        return timeline
    finally:
        session.close()


def get_case_list(
    severity: str | None = None,
    status: str | None = None,
    pattern: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return list of CaseListItem sorted by score desc, then deadline_at asc."""
    raw_cases = _get_raw_cases()
    items: list[dict[str, Any]] = []

    for c in raw_cases:
        if severity and c.get("severity") != severity:
            continue
        if status and c.get("status") != status:
            continue
        if pattern and c.get("pattern") != pattern:
            continue
        items.append(_format_case_list_item(c, now=now))

    # Sort by score desc, then deadline_at asc
    items.sort(key=lambda item: (-item["score"], item["deadline_at"] or ""))
    return items


def get_case_detail(
    case_id: int,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return full CaseDetail response shape or None if not found."""
    raw_case = _get_raw_case_by_id(case_id)
    if not raw_case:
        return None

    list_item = _format_case_list_item(raw_case, now=now)
    timeline = _get_case_timeline(case_id)

    detail = dict(list_item)
    detail.update(
        {
            "summary": raw_case.get("summary"),
            "summary_source": raw_case.get("summary_source"),
            "recommended_actions": raw_case.get("recommended_actions") or [],
            "score_breakdown": raw_case.get("score_breakdown") or [],
            "timeline": timeline,
            "entities": raw_case.get("entities")
            or {"users": [], "hosts": [], "ips": []},
            "report_id": raw_case.get("report_id"),
        }
    )
    return detail


def apply_case_action(
    case_id: int,
    action: str,
    note: str,
    actor: str = "analyst",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply analyst action (confirm, dismiss, escalate) and return updated CaseDetail."""
    engine_cases.apply_action(
        case_id=case_id, action=action, note=note, actor=actor
    )
    detail = get_case_detail(case_id, now=now)
    if detail is None:
        raise KeyError(f"Case {case_id} not found after applying action")
    return detail


def update_case_detected_at(
    case_id: int,
    new_dt_iso: str,
    reason: str,
    actor: str = "analyst",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Change case detected_at with mandatory written reason."""
    engine_cases.set_detected_at(
        case_id=case_id, new_dt_iso=new_dt_iso, reason=reason, actor=actor
    )
    detail = get_case_detail(case_id, now=now)
    if detail is None:
        raise KeyError(f"Case {case_id} not found after updating detected_at")
    return detail


def get_dashboard_data(now: datetime | None = None) -> dict[str, Any]:
    """Compute and return dashboard metrics and open cases."""
    settings = engine_settings.get_settings()
    minutes_saved_per_alert = int(settings.get("minutes_saved_per_alert", 5))

    raw_cases = _get_raw_cases()
    total_cases = len(raw_cases)

    # Ingested and alert statuses counts
    if IS_FAKE:
        all_alerts = list(engine.store.alerts.values())
        ingested = len(all_alerts)
        suppressed = sum(1 for a in all_alerts if a.status == "suppressed_benign")
        merged = sum(1 for a in all_alerts if a.status == "merged_duplicate")
        in_cases = sum(1 for a in all_alerts if a.status == "in_case")
    else:
        session = get_session()
        try:
            all_alerts_orm = session.query(models.Alert).all()
            ingested = len(all_alerts_orm)
            suppressed = sum(
                1 for a in all_alerts_orm if a.status == "suppressed_benign"
            )
            merged = sum(
                1 for a in all_alerts_orm if a.status == "merged_duplicate"
            )
            in_cases = sum(1 for a in all_alerts_orm if a.status == "in_case")
        finally:
            session.close()

    # Time saved calculation per Section 3
    alerts_beyond_first = max(0, in_cases - total_cases)
    time_saved_minutes = (
        suppressed + merged + alerts_beyond_first
    ) * minutes_saved_per_alert

    time_saved_note = (
        f"Estimated {time_saved_minutes} minutes saved based on {minutes_saved_per_alert} mins "
        f"saved per suppressed ({suppressed}), duplicate ({merged}), and correlated case alerts beyond first ({alerts_beyond_first})."
    )

    # Cases by severity
    cases_by_severity = {
        "low": sum(1 for c in raw_cases if c.get("severity") == "low"),
        "medium": sum(1 for c in raw_cases if c.get("severity") == "medium"),
        "high": sum(1 for c in raw_cases if c.get("severity") == "high"),
        "critical": sum(1 for c in raw_cases if c.get("severity") == "critical"),
    }

    # Open cases
    open_cases = [
        _format_case_list_item(c, now=now)
        for c in raw_cases
        if c.get("status") == "open"
    ]
    open_cases.sort(key=lambda item: (-item["score"], item["deadline_at"] or ""))

    return {
        "funnel": {
            "ingested": ingested,
            "suppressed": suppressed,
            "merged": merged,
            "in_cases": in_cases,
            "cases": total_cases,
        },
        "time_saved_minutes": time_saved_minutes,
        "time_saved_note": time_saved_note,
        "cases_by_severity": cases_by_severity,
        "open_cases": open_cases,
    }
