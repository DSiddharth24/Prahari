"""API routes for Prahari backend."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.api.engine_bridge import engine
from backend.demo_data.generate import generate_demo_alerts

router = APIRouter(prefix="/api", tags=["prahari"])


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

  return {"ingest": ingest_result, "pipeline": pipeline_result}


@router.post("/demo/load")
async def demo_load() -> dict[str, Any]:
  """Generate demo alert dataset, ingest, and execute detection pipeline."""
  alerts = generate_demo_alerts(seed=42)
  ingest_result = engine.ingest.ingest_alerts(alerts, actor="demo")
  pipeline_result = engine.pipeline.run_pipeline(actor="demo")

  # Summary generation hook (stubbed until Step 4)
  return {"ingest": ingest_result, "pipeline": pipeline_result}


@router.post("/demo/reset")
async def demo_reset() -> dict[str, Any]:
  """Reset all storage state and database tables."""
  engine.reset_all()
  return {"ok": True}
