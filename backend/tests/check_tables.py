"""Verify all tables exist and that env-var DB path override works correctly."""
import os, tempfile, sqlite3, sys

db = tempfile.mktemp(suffix='.db')
os.environ['PRAHARI_DB_PATH'] = db

import backend.engine as eng
eng.init_db()

conn = sqlite3.connect(db)
tables = sorted([t[0] for t in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
conn.close()
print('Tables:', tables)
expected = {'_settings','alerts','audit_events','case_alert_links','cases','reports'}
missing = expected - set(tables)
if missing:
    print('MISSING:', missing); sys.exit(1)
print('All tables present OK')
