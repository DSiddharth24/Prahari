"""Trace exactly when and how the engine gets initialized during TestClient startup."""
import os, tempfile, sqlite3
db = tempfile.mktemp(suffix='_tc.db')
os.environ['PRAHARI_DB_PATH'] = db
print('DB path:', db)

# Monkey-patch _get_engine to report when it's first called
import traceback as _tb

from backend.engine import db as _db
_orig_get_engine = _db._get_engine

def _traced_get_engine():
    if _db._ENGINE is None:
        print('\n[TRACE] _get_engine() called with _ENGINE=None, path will be:', _db._db_path())
        _tb.print_stack(limit=6)
    return _orig_get_engine()

_db._get_engine = _traced_get_engine

# Now import and start the app
from fastapi.testclient import TestClient
from backend.main import app

print('\n[TRACE] About to create TestClient (triggers lifespan)')
with TestClient(app) as client:
    print('[TRACE] Inside TestClient context — lifespan has run')
    print('[TRACE] _CURRENT_DB_PATH:', _db._CURRENT_DB_PATH)
    r = client.get('/api/health')
    print('[TRACE] /health:', r.status_code)
