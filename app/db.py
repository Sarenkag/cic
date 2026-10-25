"""SQLite storage. The audit log is append-only, enforced by triggers."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  basis TEXT,
  level INTEGER NOT NULL DEFAULT 0,
  outcome TEXT,
  details TEXT,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE IF NOT EXISTS deadlines (
  key TEXT PRIMARY KEY, title TEXT NOT NULL, due TEXT NOT NULL, who TEXT,
  source TEXT, note TEXT, done_at TEXT, done_by TEXT
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, created TEXT NOT NULL,
  agent TEXT, title TEXT NOT NULL, detail TEXT, owner TEXT, due TEXT,
  status TEXT NOT NULL DEFAULT 'otwarte'
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, created TEXT NOT NULL,
  agent TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT,
  amount_pence INTEGER, level INTEGER NOT NULL, required INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'oczekuje', payload TEXT, decided TEXT
);
CREATE TABLE IF NOT EXISTS approval_votes (
  approval_id INTEGER NOT NULL REFERENCES approvals(id), user TEXT NOT NULL,
  vote TEXT NOT NULL, ts TEXT NOT NULL, PRIMARY KEY (approval_id, user)
);
CREATE TABLE IF NOT EXISTS agent_state (
  code TEXT PRIMARY KEY, paused INTEGER NOT NULL DEFAULT 0, paused_by TEXT,
  paused_at TEXT, reason TEXT, last_run TEXT, last_status TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, agent TEXT NOT NULL,
  kind TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, created TEXT NOT NULL,
  agent TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
  resolved_at TEXT, resolved_by TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path():
    return config.DATA_DIR / "cic.db"


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session(path=None):
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init(conn):
    conn.executescript(SCHEMA)
