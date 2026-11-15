"""API routes for Prahari backend."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
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
            with engine.get_session() as session:
                unsummarised = session.query(engine.models.Case).filter(
                    engine.models.Case.summary.is_(None)
                ).all()
            for case in unsummarised:
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
    """Restore a suppressed or merged alert back to 'new' status.

    After restore, triggers summary generation for any cases that now lack a summary.
    Returns 404 if alert does not exist.
    """
    try:
        result = engine.alerts.restore(alert_id=id, actor="analyst")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Alert {id} not found") from None

    _trigger_summaries_for_unsummarised_cases()
    return result
