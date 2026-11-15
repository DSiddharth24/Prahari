"""
engine/settings.py
Persistent settings stored as a single JSON row in SQLite,
plus a YAML rules file on disk.

Public interface (section 7.2):
    get_settings()          -> dict
    update_settings(d)      -> dict   (merged patch; returns updated settings)
    get_rules_yaml()        -> str
    save_rules_yaml(text)   -> None

Settings keys (section 7.2 defaults):
    correlation_window_hours    int     6
    dedupe_window_minutes       int     10
    minutes_saved_per_alert     int     5
    critical_assets             list    []
    outbound_bytes_threshold    int     1_000_000_000  (1 GB)
"""

import json
import os
from pathlib import Path

from sqlalchemy import Column, Integer, String, Text
from .db import Base, get_session

# ---------------------------------------------------------------------------
# tiny ORM model for key-value settings storage
# ---------------------------------------------------------------------------

class _SettingsRow(Base):
    __tablename__ = "_settings"
    id    = Column(Integer, primary_key=True)          # always row id=1
    data  = Column(Text, nullable=False, default="{}")


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------

_DEFAULTS: dict = {
    "correlation_window_hours":  6,
    "dedupe_window_minutes":     10,
    "minutes_saved_per_alert":   5,
    "critical_assets":           [],
    "outbound_bytes_threshold":  1_000_000_000,
}

# Rules YAML lives next to the engine package so it can be edited and version-controlled.
_RULES_PATH = Path(__file__).parent.parent / "rules" / "rules.yaml"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _get_or_create_row(session) -> "_SettingsRow":
    row = session.query(_SettingsRow).filter(_SettingsRow.id == 1).first()
    if row is None:
        row = _SettingsRow(id=1, data=json.dumps(_DEFAULTS))
        session.add(row)
        session.flush()
    return row


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def get_settings() -> dict:
    """Return current settings merged over defaults."""
    session = get_session()
    try:
        row = _get_or_create_row(session)
        session.commit()
        stored = json.loads(row.data) if row.data else {}
        result = {**_DEFAULTS, **stored}
        return result
    finally:
        session.close()


def update_settings(d: dict) -> dict:
    """
    Patch settings with the keys in *d*.  Unknown keys are accepted (forward compat).
    Returns the full updated settings dict.
    """
    session = get_session()
    try:
        row = _get_or_create_row(session)
        current = json.loads(row.data) if row.data else {}
        current.update(d)
        row.data = json.dumps(current)
        session.commit()
        return {**_DEFAULTS, **current}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_rules_yaml() -> str:
    """Return the contents of rules/rules.yaml as a string."""
    if not _RULES_PATH.exists():
        return ""
    return _RULES_PATH.read_text(encoding="utf-8")


def save_rules_yaml(text: str) -> None:
    """Overwrite rules/rules.yaml with *text*."""
    _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RULES_PATH.write_text(text, encoding="utf-8")
