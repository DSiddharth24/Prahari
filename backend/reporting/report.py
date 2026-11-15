"""CERT-In incident report drafting, versioning, manual submission, and PDF export.

NOTE: The incident-type list and report fields in this module are a working template
that has not been verified against the official CERT-In directions or reporting form.
Prahari never submits reports externally; analysts review and submit manually.
"""

from __future__ import annotations

import copy
import io
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.api.case_service import get_case_detail
from backend.api.engine_bridge import IS_FAKE, engine

IST = timezone(timedelta(hours=5, minutes=30))

_CONFIG_PATH = Path(__file__).parent / "config" / "certin_incident_types.json"

PATTERN_TO_INCIDENT_TYPE: dict[str, str] = {
    "account_takeover_then_exfiltration": "Unauthorised access to IT systems/data",
    "ransomware_behaviour": "Malicious code/ransomware",
    "phishing_to_compromise": "Identity theft/spoofing/phishing",
    "recon_then_access": "Targeted scanning/probing",
}

DRAFT_BANNER = (
    "DRAFT — for analyst review. Verify against the official CERT-In form before submission."
)


def load_certin_incident_types() -> dict[str, Any]:
    """Load the working template list of CERT-In incident categories."""
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _to_ist_label(iso_ts: str | None) -> str:
    """Convert a UTC ISO-8601 timestamp string to an IST-labelled display string."""
    if not iso_ts:
        return "Unknown — IST (UTC+05:30)"
    try:
        clean = iso_ts.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        ist_dt = dt.astimezone(IST)
        return f"{ist_dt.strftime('%d/%m/%Y %H:%M:%S')} IST (UTC+05:30)"
    except ValueError:
        return f"{iso_ts} IST (UTC+05:30)"


def _now_utc_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _suggest_incident_type(pattern: str | None) -> str:
    if pattern and pattern in PATTERN_TO_INCIDENT_TYPE:
        return PATTERN_TO_INCIDENT_TYPE[pattern]
    return "Unauthorised access to IT systems/data"


def _build_narrative(case_detail: dict[str, Any]) -> str:
    summary = case_detail.get("summary") or (
        f"Suspected security incident ({case_detail.get('title', 'Untitled Case')}) "
        "requiring analyst verification."
    )
    lines = [
        summary,
        "",
        "Chronological Evidence Timeline (all times in IST (UTC+05:30)):",
    ]
    timeline = case_detail.get("timeline") or []
    for idx, alert in enumerate(timeline, start=1):
        ts_ist = _to_ist_label(alert.get("timestamp"))
        src = alert.get("source", "unknown")
        title = alert.get("title", "Alert")
        lines.append(f"{idx}. [{ts_ist}] ({src}) {title}")
    return "\n".join(lines)


def _collect_actions_taken(case_id: int) -> list[str]:
    events = engine.audit.list_events(target_type="case", target_id=case_id, limit=100)
    actions: list[str] = []
    for ev in events:
        ev_dict = ev.to_dict() if hasattr(ev, "to_dict") else ev.__dict__
        act = ev_dict.get("action", "")
        actor = ev_dict.get("actor", "system")
        ts_ist = _to_ist_label(ev_dict.get("timestamp"))
        details = ev_dict.get("details") or {}
        note = details.get("note") or details.get("reason") or ""
        suffix = f" — {note}" if note else ""
        actions.append(f"[{ts_ist}] {actor}: {act}{suffix}")
    return actions


def _report_to_dict(rep: Any) -> dict[str, Any]:
    if hasattr(rep, "to_dict"):
        data = rep.to_dict()
    else:
        data = {
            "id": rep.id,
            "case_id": rep.case_id,
            "incident_type": rep.incident_type,
            "fields": copy.deepcopy(rep.fields),
            "narrative": rep.narrative,
            "generated_at": rep.generated_at,
            "status": rep.status,
            "version": rep.version,
            "history": copy.deepcopy(getattr(rep, "history", []) or []),
        }
    data.setdefault("history", [])
    return data


def _find_report_by_case(case_id: int) -> Any | None:
    if IS_FAKE:
        for rep in engine.store.reports.values():
            if rep.case_id == case_id:
                return rep
        return None
    with engine.get_session() as session:
        return (
            session.query(engine.models.Report)
            .filter(engine.models.Report.case_id == case_id)
            .first()
        )


def _get_report_obj(report_id: int) -> Any | None:
    if IS_FAKE:
        return engine.store.reports.get(report_id)
    with engine.get_session() as session:
        return (
            session.query(engine.models.Report)
            .filter(engine.models.Report.id == report_id)
            .first()
        )


def create_or_get_draft_report(case_id: int, actor: str = "analyst") -> dict[str, Any]:
    """Create a draft CERT-In report for a case, or return existing draft if one exists."""
    case_detail = get_case_detail(case_id=case_id)
    if case_detail is None:
        raise KeyError(f"Case {case_id} not found")

    existing = _find_report_by_case(case_id)
    if existing is not None:
        return _report_to_dict(existing)

    incident_type = _suggest_incident_type(case_detail.get("pattern"))
    detected_utc = case_detail.get("detected_at") or _now_utc_iso()
    first_activity_utc = case_detail.get("first_alert_at") or detected_utc
    timeline = case_detail.get("timeline") or []

    evidence = [
        {
            "id": a.get("id"),
            "source": a.get("source"),
            "timestamp": _to_ist_label(a.get("timestamp")),
            "title": a.get("title"),
        }
        for a in timeline
    ]

    fields: dict[str, Any] = {
        "organisation_name": "Demo NBFC Ltd",
        "reporter_name": "",
        "reporter_role": "",
        "reporter_contact": "",
        "incident_type": incident_type,
        "detected_at_ist": _to_ist_label(detected_utc),
        "detected_at_utc": detected_utc,
        "first_activity_at_ist": _to_ist_label(first_activity_utc),
        "affected_systems": case_detail.get("entities") or {"users": [], "hosts": [], "ips": []},
        "description": case_detail.get("summary") or case_detail.get("title", ""),
        "impact_assessment": "Under assessment",
        "actions_taken": _collect_actions_taken(case_id),
        "evidence": evidence,
        "logs_preserved": False,
    }
    narrative = _build_narrative(case_detail)
    now_utc = _now_utc_iso()

    if IS_FAKE:
        report_id = engine.store.report_seq
        engine.store.report_seq += 1
        rep = engine.models.Report(
            id=report_id,
            case_id=case_id,
            incident_type=incident_type,
            fields=fields,
            narrative=narrative,
            generated_at=now_utc,
            status="draft",
            version=1,
            history=[],
        )
        engine.store.reports[report_id] = rep
        case_obj = engine.store.cases.get(case_id)
        if case_obj is not None:
            case_obj.report_id = report_id
    else:
        with engine.get_session() as session:
            rep = engine.models.Report(
                case_id=case_id,
                incident_type=incident_type,
                fields=fields,
                narrative=narrative,
                generated_at=now_utc,
                status="draft",
                version=1,
            )
            session.add(rep)
            session.flush()
            case_obj = session.query(engine.models.Case).filter_by(id=case_id).first()
            if case_obj is not None:
                case_obj.report_id = rep.id
            session.commit()
            session.refresh(rep)

    engine.audit.record(
        actor=actor,
        action="report_generated",
        target_type="report",
        target_id=rep.id,
        details={"case_id": case_id, "version": 1, "incident_type": incident_type},
    )
    return _report_to_dict(rep)


def get_report(report_id: int) -> dict[str, Any] | None:
    """Fetch a report by ID including its version history."""
    rep = _get_report_obj(report_id)
    if rep is None:
        return None
    return _report_to_dict(rep)


def update_report(
    report_id: int,
    fields: dict[str, Any] | None = None,
    narrative: str | None = None,
    incident_type: str | None = None,
    actor: str = "analyst",
) -> dict[str, Any]:
    """Update a report, archiving the previous snapshot into history and bumping version."""
    rep = _get_report_obj(report_id)
    if rep is None:
        raise KeyError(f"Report {report_id} not found")

    if fields is None and narrative is None and incident_type is None:
        raise ValueError("At least one of fields, narrative, or incident_type must be provided")

    prior_snapshot = {
        "version": rep.version,
        "incident_type": rep.incident_type,
        "fields": copy.deepcopy(rep.fields),
        "narrative": rep.narrative,
        "generated_at": rep.generated_at,
        "status": rep.status,
    }

    current_history = list(getattr(rep, "history", []) or [])
    current_history.append(prior_snapshot)

    merged_fields = copy.deepcopy(rep.fields)
    if fields is not None:
        merged_fields.update(fields)
    if incident_type is not None:
        rep.incident_type = incident_type
        merged_fields["incident_type"] = incident_type
    elif "incident_type" in merged_fields:
        rep.incident_type = merged_fields["incident_type"]

    if narrative is not None:
        rep.narrative = narrative

    rep.fields = merged_fields
    rep.version = rep.version + 1
    rep.generated_at = _now_utc_iso()

    if IS_FAKE:
        rep.history = current_history
    else:
        with engine.get_session() as session:
            db_rep = session.query(engine.models.Report).filter_by(id=report_id).first()
            if db_rep is not None:
                db_rep.incident_type = rep.incident_type
                db_rep.fields = rep.fields
                db_rep.narrative = rep.narrative
                db_rep.version = rep.version
                db_rep.generated_at = rep.generated_at
                if hasattr(db_rep, "history"):
                    db_rep.history = current_history
                session.commit()
                session.refresh(db_rep)
                rep = db_rep

    engine.audit.record(
        actor=actor,
        action="report_edited",
        target_type="report",
        target_id=report_id,
        details={"new_version": rep.version},
    )
    return _report_to_dict(rep)


def mark_report_submitted(
    report_id: int,
    reference_number: str,
    submitted_by: str,
) -> dict[str, Any]:
    """Record manual submission metadata without transmitting anything externally."""
    if not reference_number or not reference_number.strip():
        raise ValueError("reference_number is required")
    if not submitted_by or not submitted_by.strip():
        raise ValueError("submitted_by is required")

    rep = _get_report_obj(report_id)
    if rep is None:
        raise KeyError(f"Report {report_id} not found")

    submitted_at_utc = _now_utc_iso()
    rep.status = "submitted_manually"
    updated_fields = copy.deepcopy(rep.fields)
    updated_fields["manual_submission"] = {
        "reference_number": reference_number.strip(),
        "submitted_by": submitted_by.strip(),
        "submitted_at_ist": _to_ist_label(submitted_at_utc),
        "submitted_at_utc": submitted_at_utc,
    }
    rep.fields = updated_fields

    if IS_FAKE:
        case_obj = engine.store.cases.get(rep.case_id)
        if case_obj is not None:
            case_obj.status = "reported"
    else:
        with engine.get_session() as session:
            db_rep = session.query(engine.models.Report).filter_by(id=report_id).first()
            if db_rep is not None:
                db_rep.status = "submitted_manually"
                db_rep.fields = updated_fields
            case_obj = session.query(engine.models.Case).filter_by(id=rep.case_id).first()
            if case_obj is not None:
                case_obj.status = "reported"
            session.commit()

    engine.audit.record(
        actor=submitted_by.strip(),
        action="report_submitted_manually",
        target_type="report",
        target_id=report_id,
        details={
            "reference_number": reference_number.strip(),
            "submitted_by": submitted_by.strip(),
            "submitted_at_utc": submitted_at_utc,
        },
    )
    return _report_to_dict(rep)


def render_report_pdf(report_id: int) -> bytes:
    """Render a CERT-In draft report to PDF bytes using ReportLab."""
    rep = get_report(report_id)
    if rep is None:
        raise KeyError(f"Report {report_id} not found")

    buf = io.BytesIO()
    generated_ist = _to_ist_label(rep.get("generated_at"))
    version = rep.get("version", 1)

    def _draw_header_footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, height = A4
        # Top draft warning banner
        canvas.setFillColor(colors.HexColor("#991B1B"))
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(18 * mm, height - 12 * mm, DRAFT_BANNER)
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.line(18 * mm, height - 14.5 * mm, width - 18 * mm, height - 14.5 * mm)

        # Footer with IST timestamp and version
        canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            18 * mm,
            9.5 * mm,
            f"Generated: {generated_ist} | Version {version} | Prahari Incident Draft",
        )
        canvas.drawRightString(width - 18 * mm, 9.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=15,
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=11,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "BodyTextIST",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=13,
    )

    fields = rep.get("fields") or {}
    affected = fields.get("affected_systems") or {}
    affected_str = (
        f"Users: {', '.join(affected.get('users') or ['None'])} | "
        f"Hosts: {', '.join(affected.get('hosts') or ['None'])} | "
        f"IPs: {', '.join(affected.get('ips') or ['None'])}"
    )

    story: list[Any] = [
        Paragraph(
            f"CERT-In Cyber Security Incident Report (Draft v{version})",
            title_style,
        ),
        Paragraph(
            f"<b>Status:</b> {rep.get('status', 'draft')} &nbsp;|&nbsp; "
            f"<b>Report ID:</b> {rep.get('id')} &nbsp;|&nbsp; "
            f"<b>Case ID:</b> {rep.get('case_id')}",
            body_style,
        ),
        Spacer(1, 6),
        Paragraph("1. Organisation & Incident Metadata", section_style),
    ]

    meta_rows = [
        ["Organisation Name", str(fields.get("organisation_name", ""))],
        ["Reporter Name / Role", f"{fields.get('reporter_name', '')} ({fields.get('reporter_role', '')})"],
        ["Reporter Contact", str(fields.get("reporter_contact", ""))],
        ["Incident Type", str(rep.get("incident_type", ""))],
        ["First Activity Time", str(fields.get("first_activity_at_ist", ""))],
        ["Detected Time (IST)", str(fields.get("detected_at_ist", ""))],
        ["Detected Time (UTC)", str(fields.get("detected_at_utc", ""))],
        ["Affected Systems", affected_str],
        ["Impact Assessment", str(fields.get("impact_assessment", ""))],
        ["Logs Preserved", "Yes" if fields.get("logs_preserved") else "No"],
    ]
    meta_table = Table(meta_rows, colWidths=[48 * mm, 124 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("2. Incident Narrative & Chronology", section_style))
    for line in (rep.get("narrative") or "").splitlines():
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe_line or "&nbsp;", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("3. Linked Evidence Alerts", section_style))
    evidence = fields.get("evidence") or []
    if evidence:
        ev_rows = [["ID", "Source", "Timestamp (IST)", "Alert Title"]]
        for item in evidence:
            ev_rows.append(
                [
                    str(item.get("id", "")),
                    str(item.get("source", "")),
                    str(item.get("timestamp", "")),
                    str(item.get("title", "")),
                ]
            )
        ev_table = Table(ev_rows, colWidths=[12 * mm, 32 * mm, 48 * mm, 80 * mm])
        ev_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 3.5),
                ]
            )
        )
        story.append(ev_table)
    else:
        story.append(Paragraph("No linked alerts recorded.", body_style))

    doc.build(story, onFirstPage=_draw_header_footer, onLaterPages=_draw_header_footer)
    return buf.getvalue()