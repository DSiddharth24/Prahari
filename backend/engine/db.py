"""
engine/db.py
SQLite database setup.  All engine code imports get_session() from here.

The DB file location is controlled by the environment variable PRAHARI_DB_PATH.
Default: prahari.db in the working directory.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_DB_PATH = os.environ.get("PRAHARI_DB_PATH", "prahari.db")
_ENGINE = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        url = f"sqlite:///{_DB_PATH}"
        _ENGINE = create_engine(url, connect_args={"check_same_thread": False})
        # Enable WAL mode and foreign keys for SQLite
        @event.listens_for(_ENGINE, "connect")
        def _set_sqlite_pragma(dbapi_conn, _rec):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return _ENGINE


def init_db():
    """Create all tables.  Safe to call multiple times (CREATE IF NOT EXISTS)."""
    from . import models  # noqa: F401 — registers ORM classes against Base
    Base.metadata.create_all(bind=_get_engine())


def get_session():
    """Return a new SQLAlchemy Session.  Caller is responsible for closing it."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()


def reset_all():
    """
    Drop and recreate all tables.  Wipes every row.
    Used by POST /api/demo/reset.

    The cases ↔ reports circular FK requires FK enforcement to be disabled
    for the duration of the DROP.  We do this on a raw DBAPI connection so
    the PRAGMA and the DROPs are guaranteed to share the same connection.
    """
    from . import models  # noqa: F401
    import sqlalchemy as sa

    eng = _get_engine()

    # Use a raw DBAPI connection so PRAGMA foreign_keys=OFF applies to the
    # exact same connection that runs the DROP statements.
    with eng.connect() as conn:
        raw = conn.connection  # underlying sqlite3.Connection
        raw.execute("PRAGMA foreign_keys=OFF")
        # Drop tables in a safe order that avoids FK issues
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

    # Re-create everything through SQLAlchemy
    Base.metadata.create_all(bind=eng)
