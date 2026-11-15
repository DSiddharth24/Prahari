"""Engine bridge: imports real engine if available, or falls back to fakes."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Set PRAHARI_USE_FAKE_ENGINE=1 to force using in-memory fake engine
_force_fake = os.environ.get("PRAHARI_USE_FAKE_ENGINE", "0") == "1"

engine: Any = None
IS_FAKE = False

if not _force_fake:
    try:
        from backend import engine as _real_engine

        # Verify real engine can be accessed
        if hasattr(_real_engine, "init_db") and hasattr(_real_engine, "ingest"):
            engine = _real_engine
    except Exception as exc:  # noqa: BLE001
        logger.debug("Falling back to fake engine: %s", exc)

if engine is None:
    from backend.api.tests import fakes as _fake_engine

    engine = _fake_engine
    IS_FAKE = True

# Direct attribute exports for convenience
init_db = engine.init_db
get_session = engine.get_session
reset_all = engine.reset_all
models = engine.models
ingest = engine.ingest
pipeline = engine.pipeline
audit = engine.audit
cases = engine.cases
alerts = engine.alerts
settings = engine.settings
