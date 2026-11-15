"""API routes for Prahari backend."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.api.case_service import (
    apply_case_action,
    get_case_detail,
    get_case_list,
    get_dashboard_data,
    update_case_detected_at,
)
from backend.api.engine_bridge import IS_FAKE, engine
from backend.demo_data.generate import generate_demo_alerts
from backend.reporting.report import (
    create_or_get_draft_report,
    get_report,
    mark_report_submitted,
    render_report_pdf,
    update_report,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["prahari"])


# ---------------------------------------------------------------------------
# Summary generation helper
# ---------------------------------------------------------------------------


def _trigger_summaries_for_unsummarised_cases() -> None:
    """Call generate_summary for every case without a summary and persist via save_summary.

    Works with both the fake in-memory store (IS_FAKE=True) and the real engine.
    Errors from summary generation are logged and swallowed so they never block ingestion.
    """
    from backend.reporting.summary import (  # local import avoids circular
        generate_summary,
    )

    if IS_FAKE:
        for case in list(engine.store.cases.values()):
            if case.summary:
                continue
            try:
                facts = get_case_detail(case_id=case.id) or {}
                result = generate_summary(facts)
                engine.cases.save_summary(
                    case.id,
                    result["summary"],
                    result["summary_source"],
                    result["recommended_actions"],
                )
            except Exception:  # noqa: BLE001
                logger.warning("Summary generation failed for case %s; skipping.", case.id)
    else:
        # Real engine path: iterate open cases via session
        try:
            session = engine.get_session()
            try:
                unsummarised_ids = [
                    c.id for c in session.query(engine.models.Case).filter(
                        engine.models.Case.summary.is_(None)
                    ).all()
                ]
            finally:
                session.close()

            for case_id in unsummarised_ids:
                try:
                    facts = get_case_detail(case_id=case_id) or {}
                    result = generate_summary(facts)
                    engine.cases.save_summary(
                        case_id,
                        result["summary"],
                        result["summary_source"],
                        result["recommended_actions"],
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("Summary generation failed for case %s; skipping.", case_id)
        except Exception:  # noqa: BLE001
            logger.warning("Could not query cases for summary generation; skipping.")


class CaseActionRequest(BaseModel):
    action: str
    note: str
    actor: str = "analyst"


class DetectedAtRequest(BaseModel):
    detected_at: str
    reason: str
    actor: str = "analyst"


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@router.post("/alerts/ingest")
async def ingest_alerts(request: Request) -> dict[str, Any]:
    """Ingest security alerts via JSON body or multipart file upload (.json or .csv).

    Then immediately runs the correlation and suppression pipeline.
    """
    content_type = request.headers.get("content-type", "").lower()
    alerts_data: list[dict[str, Any]] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if not (hasattr(upload, "filename") and hasattr(upload, "read")):
            for val in form.values():
                if hasattr(val, "filename") and hasattr(val, "read"):
                    upload = val
                    break

        if not (hasattr(upload, "filename") and hasattr(upload, "read")):
            raise HTTPException(
                status_code=400,
                detail="Missing uploaded file in multipart form-data (field 'file')",
            )

        filename = (upload.filename or "").lower()
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        if filename.endswith(".json"):
            try:
                parsed = json.loads(content.decode("utf-8"))
            except Exception as err:
                raise HTTPException(
                    status_code=400, detail=f"Invalid JSON file: {err}"
                ) from err

            if isinstance(parsed, list):
                alerts_data = parsed
            elif isinstance(parsed, dict) and "alerts" in parsed:
                alerts_data = parsed["alerts"]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="JSON file must be an array of alerts or contain 'alerts' key",
                )

        elif filename.endswith(".csv"):
            try:
                text = content.decode("utf-8")
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    # If extra column is present and formatted as JSON string, parse it
                    extra_val = row.get("extra")
                    if extra_val:
                        try:
                            row["extra"] = json.loads(extra_val)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    alerts_data.append(row)
            except Exception as err:
                raise HTTPException(
                    status_code=400, detail=f"Invalid CSV file: {err}"
                ) from err
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file extension. Only .json and .csv are supported",
            )

    else:
        # Handle direct JSON body
        try:
            body = await request.json()
        except Exception as err:
            raise HTTPException(
                status_code=400, detail=f"Malformed JSON body: {err}"
            ) from err

        if isinstance(body, list):
            alerts_data = body
        elif isinstance(body, dict) and "alerts" in body:
            alerts_data = body["alerts"]
        else:
            raise HTTPException(
                status_code=400,
                detail="JSON body must be an array of alerts or an object with 'alerts' array",
            )

    if not alerts_data or not isinstance(alerts_data, list):
        raise HTTPException(status_code=400, detail="No alert items found in input")

    # Validate required keys for raw alerts per section 7.1
    required_keys = {"source", "source_alert_id", "timestamp", "title"}
    for idx, alert in enumerate(alerts_data):
        if not isinstance(alert, dict):
            raise HTTPException(
                status_code=400, detail=f"Alert at index {idx} is not a valid object"
            )
        missing = required_keys - set(alert.keys())
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Alert at index {idx} missing required fields: {sorted(missing)}",
            )

    # Ingest alerts and trigger pipeline run
    try:
        ingest_result = engine.ingest.ingest_alerts(alerts_data, actor="api")
        pipeline_result = engine.pipeline.run_pipeline(actor="api")
    except Exception as err:
        raise HTTPException(
            status_code=500, detail=f"Engine pipeline error: {err}"
        ) from err

    _trigger_summaries_for_unsummarised_cases()
    return {"ingest": ingest_result, "pipeline": pipeline_result}


@router.post("/demo/load")
async def demo_load() -> dict[str, Any]:
    """Generate demo alert dataset, ingest, and execute detection pipeline."""
    alerts = generate_demo_alerts(seed=42)
    ingest_result = engine.ingest.ingest_alerts(alerts, actor="demo")
    pipeline_result = engine.pipeline.run_pipeline(actor="demo")

    _trigger_summaries_for_unsummarised_cases()
    return {"ingest": ingest_result, "pipeline": pipeline_result}


@router.post("/demo/reset")
async def demo_reset() -> dict[str, Any]:
    """Reset all storage state and database tables."""
    engine.reset_all()
    return {"ok": True}


# -----------------------------------------------------------------------------
# Cases & Dashboard Endpoints (Step 3)
# -----------------------------------------------------------------------------


@router.get("/cases")
async def list_cases(
    severity: str | None = Query(None, description="Filter by case severity (low, medium, high, critical)"),
    status: str | None = Query(None, description="Filter by case status (open, confirmed, dismissed, escalated, reported)"),
    pattern: str | None = Query(None, description="Filter by pattern"),
) -> list[dict[str, Any]]:
    """Get list of cases matching optional filters, sorted by score desc then deadline asc."""
    return get_case_list(severity=severity, status=status, pattern=pattern)


@router.get("/cases/{id}")
async def get_case(id: int) -> dict[str, Any]:
    """Get detailed view of a case with score breakdown, timeline, entities, and actions."""
    detail = get_case_detail(case_id=id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Case {id} not found")
    return detail


@router.post("/cases/{id}/action")
async def apply_action_to_case(
    id: int,
    payload: CaseActionRequest,
) -> dict[str, Any]:
    """Apply analyst action (confirm, dismiss, escalate) with required note."""
    if not payload.note or not payload.note.strip():
        raise HTTPException(status_code=400, detail="Note is required and cannot be empty")

    valid_actions = {"confirm", "dismiss", "escalate"}
    if payload.action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{payload.action}'. Must be one of: {sorted(valid_actions)}",
        )

    try:
        updated = apply_case_action(
            case_id=id,
            action=payload.action,
            note=payload.note.strip(),
            actor=payload.actor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case {id} not found") from None
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return updated


@router.patch("/cases/{id}/detected_at")
async def update_case_detected_timestamp(
    id: int,
    payload: DetectedAtRequest,
) -> dict[str, Any]:
    """Update detected_at timestamp for a case. Requires written reason."""
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Reason is required and cannot be empty")

    if not payload.detected_at or not payload.detected_at.strip():
        raise HTTPException(status_code=400, detail="detected_at cannot be empty")

    # Validate ISO-8601 format
    try:
        clean_iso = payload.detected_at.strip().replace("Z", "+00:00")
        datetime.fromisoformat(clean_iso)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ISO-8601 timestamp format for detected_at: '{payload.detected_at}'",
        ) from None

    try:
        updated = update_case_detected_at(
            case_id=id,
            new_dt_iso=payload.detected_at.strip(),
            reason=payload.reason.strip(),
            actor=payload.actor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case {id} not found") from None
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    return updated


@router.get("/dashboard")
async def get_dashboard() -> dict[str, Any]:
    """Get dashboard summary metrics, triage funnel, and open cases."""
    return get_dashboard_data()


# ---------------------------------------------------------------------------
# Alert restore endpoint (Step 4)
# ---------------------------------------------------------------------------


@router.post("/alerts/{id}/restore")
async def restore_alert(id: int) -> dict[str, Any]:
    """Restore a suppressed or merged alert back to 'new' status."""
    try:
        result = engine.alerts.restore(alert_id=id, actor="analyst")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Alert {id} not found") from None
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    _trigger_summaries_for_unsummarised_cases()
    return result
# ---------------------------------------------------------------------------
# CERT-In Report Endpoints (Step 5)
# ---------------------------------------------------------------------------


class ReportUpdateRequest(BaseModel):
    fields: dict[str, Any] | None = None
    narrative: str | None = None
    incident_type: str | None = None
    actor: str = "analyst"


class ReportSubmitRequest(BaseModel):
    reference_number: str
    submitted_by: str


@router.post("/cases/{id}/report")
async def create_case_report(id: int) -> dict[str, Any]:
    """Create (or return existing) draft CERT-In report for a case."""
    try:
        return create_or_get_draft_report(case_id=id, actor="analyst")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Case {id} not found") from None


@router.get("/reports/{id}")
async def fetch_report(id: int) -> dict[str, Any]:
    """Retrieve a report including its earlier version history."""
    report = get_report(report_id=id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report {id} not found")
    return report


@router.put("/reports/{id}")
async def edit_report(id: int, payload: ReportUpdateRequest) -> dict[str, Any]:
    """Edit report fields/narrative/incident_type, creating a new version."""
    try:
        return update_report(
            report_id=id,
            fields=payload.fields,
            narrative=payload.narrative,
            incident_type=payload.incident_type,
            actor=payload.actor,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Report {id} not found") from None
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/reports/{id}/pdf")
async def download_report_pdf(id: int) -> Response:
    """Export the CERT-In draft report as a downloadable PDF."""
    try:
        pdf_bytes = render_report_pdf(report_id=id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Report {id} not found") from None

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="certin-report-{id}.pdf"'
        },
    )


@router.post("/reports/{id}/submitted")
async def submit_report_manually(
    id: int, payload: ReportSubmitRequest
) -> dict[str, Any]:
    """Mark a report as manually submitted by an analyst with a reference number."""
    if not payload.reference_number or not payload.reference_number.strip():
        raise HTTPException(status_code=400, detail="reference_number is required")
    if not payload.submitted_by or not payload.submitted_by.strip():
        raise HTTPException(status_code=400, detail="submitted_by is required")

    try:
        return mark_report_submitted(
            report_id=id,
            reference_number=payload.reference_number,
            submitted_by=payload.submitted_by,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Report {id} not found") from None
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    # ---------------------------------------------------------------------------
# Alerts List, Audit Log & Settings Endpoints (Step 6)
# ---------------------------------------------------------------------------


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] | None = None
    rules_yaml: str | None = None
    actor: str = "analyst"


def _serialize_item(obj: Any) -> dict[str, Any]:
    """Convert an ORM object or plain dict to a serialisable dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    # Last resort: strip SQLAlchemy private attrs
    return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}


@router.get("/alerts")
async def list_alerts(
    status: str | None = Query(
        None,
        description="Filter by status: suppressed_benign, merged_duplicate, unlinked_low_priority, in_case, new",
    ),
) -> list[dict[str, Any]]:
    """List alerts, optionally filtered by triage status."""
    if IS_FAKE:
        items = list(engine.store.alerts.values())
        if status:
            items = [a for a in items if a.status == status]
        items.sort(key=lambda a: a.timestamp, reverse=True)
        return [_serialize_item(a) for a in items]

    session = engine.get_session()
    try:
        q = session.query(engine.models.Alert)
        if status:
            q = q.filter(engine.models.Alert.status == status)
        items = q.order_by(engine.models.Alert.timestamp.desc()).all()
        return [a.to_dict() for a in items]
    finally:
        session.close()


@router.get("/audit")
async def get_audit_log(
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
) -> list[dict[str, Any]]:
    """Retrieve append-only audit log events with optional filters."""
    events = engine.audit.list_events(
        action=action,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    return [_serialize_item(e) for e in events]


@router.get("/audit/export")
async def export_audit_log(
    format: str = Query("json", pattern="^(csv|json)$"),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    target_id: str | None = Query(None),
    limit: int = Query(5000, ge=1, le=20000),
) -> Response:
    """Export audit log events as downloadable CSV or JSON."""
    events = engine.audit.list_events(
        action=action,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
    rows = [_serialize_item(e) for e in events]

    if format == "json":
        payload = json.dumps(rows, indent=2, default=str)
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="prahari-audit.json"'},
        )

    buf = io.StringIO()
    fieldnames = ["id", "timestamp", "actor", "action", "target_type", "target_id", "details"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        row_copy = dict(r)
        row_copy["details"] = json.dumps(row_copy.get("details") or {}, default=str)
        writer.writerow({k: row_copy.get(k) for k in fieldnames})

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="prahari-audit.csv"'},
    )


@router.get("/settings")
async def read_settings() -> dict[str, Any]:
    """Return current threshold settings and YAML correlation/suppression rules."""
    return {
        "settings": engine.settings.get_settings(),
        "rules_yaml": engine.settings.get_rules_yaml(),
    }


@router.put("/settings")
async def write_settings(payload: SettingsUpdateRequest) -> dict[str, Any]:
    """Update settings and/or YAML rules, returning HTTP 400 on invalid YAML."""
    if payload.rules_yaml is not None:
        try:
            import yaml

            parsed = yaml.safe_load(payload.rules_yaml)
            if parsed is not None and not isinstance(parsed, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid rules_yaml: top-level YAML structure must be a mapping",
                )
        except ModuleNotFoundError:
            if "\t" in payload.rules_yaml or payload.rules_yaml.strip().startswith(":"):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid YAML syntax in rules_yaml",
                ) from None
        except HTTPException:
            raise
        except Exception as err:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid YAML syntax: {err}",
            ) from err

        engine.settings.save_rules_yaml(payload.rules_yaml)
        engine.audit.record(
            actor=payload.actor,
            action="update_rules_yaml",
            target_type="settings",
            target_id="rules_yaml",
            details={"length": len(payload.rules_yaml)},
        )

    if payload.settings is not None:
        engine.settings.update_settings(payload.settings)
        engine.audit.record(
            actor=payload.actor,
            action="update_settings",
            target_type="settings",
            target_id="settings",
            details={"keys": sorted(payload.settings.keys())},
        )

    return {
        "settings": engine.settings.get_settings(),
        "rules_yaml": engine.settings.get_rules_yaml(),
    }
