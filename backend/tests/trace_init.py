import os, tempfile, sqlite3
db = tempfile.mktemp(suffix='_trace.db')
os.environ['PRAHARI_DB_PATH'] = db
print('env set to', db)

from backend.engine import db as _db
print('After import _ENGINE:', _db._ENGINE)
print('_CURRENT_DB_PATH:', _db._CURRENT_DB_PATH)

_db.init_db()
print('After init_db _CURRENT_DB_PATH:', _db._CURRENT_DB_PATH)

import os as _os
if _os.path.exists(db):
    conn = sqlite3.connect(db)
    tables = sorted(t[0] for t in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    conn.close()
    print('Tables:', tables)
else:
    print('DB file NOT created at', db)

# Now simulate what happens when engine_bridge imports and caches init_db
from backend.api.engine_bridge import init_db as bridge_init_db
print('bridge init_db is same as _db.init_db:', bridge_init_db is _db.init_db)
