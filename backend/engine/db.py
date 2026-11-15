"""
engine/db.py
SQLite database setup.  All engine code imports get_session() from here.

The DB file location is controlled by the environment variable PRAHARI_DB_PATH.
Default: prahari.db in the working directory.

IMPORTANT — singleton reset behaviour
--------------------------------------
The SQLAlchemy engine and session factory are cached as module globals for
performance.  However, if PRAHARI_DB_PATH changes between calls (e.g. in tests
or after a demo reset) callers must call _reset_engine() to discard the cache.
init_db() does this automatically: it always rebuilds from the current env var.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_ENGINE = None
_SessionLocal = None
_CURRENT_DB_PATH: str | None = None   # tracks which path the cached engine uses


class Base(DeclarativeBase):
    pass


def _db_path() -> str:
    """Return the current DB path from env (re-read each call)."""
    return os.environ.get("PRAHARI_DB_PATH", "prahari.db")


def _reset_engine() -> None:
    """Discard the cached engine and session factory."""
    global _ENGINE, _SessionLocal, _CURRENT_DB_PATH
    if _ENGINE is not None:
        try:
            _ENGINE.dispose()
        except Exception:
            pass
    _ENGINE = None
    _SessionLocal = None
    _CURRENT_DB_PATH = None


def _get_engine():
    global _ENGINE, _SessionLocal, _CURRENT_DB_PATH
    path = _db_path()
    # Rebuild if the path has changed (e.g. env var changed between test cases)
    if _ENGINE is not None and _CURRENT_DB_PATH != path:
        _reset_engine()
    if _ENGINE is None:
        url = f"sqlite:///{path}"
        _ENGINE = create_engine(url, connect_args={"check_same_thread": False})
        _CURRENT_DB_PATH = path

        @event.listens_for(_ENGINE, "connect")
        def _set_sqlite_pragma(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=_ENGINE, autoflush=False, autocommit=False
        )
    return _ENGINE


def init_db():
    """
    Create all tables.  Safe to call multiple times (CREATE IF NOT EXISTS).

    Always re-checks PRAHARI_DB_PATH so the correct database is used even
    when the env var is set after the module is first imported.
    """
    # Import settings so _SettingsRow is registered against Base before create_all
    from . import models   # noqa: F401 — registers Alert, Case, CaseAlertLink, Report, AuditEvent
    from . import settings # noqa: F401 — registers _SettingsRow
    Base.metadata.create_all(bind=_get_engine())


def get_session():
    """
    Return a new SQLAlchemy Session.

    The returned session supports both explicit close() and the context-manager
    protocol ('with get_session() as s: ...').  Callers that use the context
    manager do NOT get auto-commit on exit — they must call session.commit()
    explicitly before the 'with' block ends.
    """
    _get_engine()   # ensure factory is built
    return _SessionLocal()


def reset_all():
    """
    Drop and recreate all tables.  Wipes every row.
    Used by POST /api/demo/reset.

    The cases ↔ reports circular FK requires FK enforcement to be disabled
    for the duration of the DROP.  We do this on a raw DBAPI connection so
    the PRAGMA and the DROPs are guaranteed to share the same connection.
    """
    from . import models   # noqa: F401
    from . import settings # noqa: F401

    eng = _get_engine()

    with eng.connect() as conn:
        raw = conn.connection          # underlying sqlite3.Connection
        raw.execute("PRAGMA foreign_keys=OFF")
        for tbl_name in [
            "case_alert_links",
            "audit_events",
            "_settings",
            "reports",
            "cases",
            "alerts",
        ]:
            raw.execute(f"DROP TABLE IF EXISTS {tbl_name}")
        raw.execute("PRAGMA foreign_keys=ON")
        raw.commit()

    Base.metadata.create_all(bind=eng)
