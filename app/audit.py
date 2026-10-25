"""Hash-chained, append-only audit log."""
import hashlib
import json

from .db import now_iso

GENESIS = "0" * 64


def _digest(prev_hash, ts, actor, action, basis, level, outcome, details):
    payload = json.dumps([ts, actor, action, basis, level, outcome, details], ensure_ascii=False)
    return hashlib.sha256((prev_hash + payload).encode("utf-8")).hexdigest()


def record(conn, actor, action, *, basis=None, level=0, outcome=None, details=None):
    if details is not None and not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = row["hash"] if row else GENESIS
        ts = now_iso()
        h = _digest(prev_hash, ts, actor, action, basis, level, outcome, details)
        conn.execute(
            "INSERT INTO audit_log (ts, actor, action, basis, level, outcome, details, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, actor, action, basis, level, outcome, details, prev_hash, h),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return h


def verify(conn):
    """Return (ok, first_bad_id, count)."""
    prev_hash = GENESIS
    count = 0
    for r in conn.execute("SELECT * FROM audit_log ORDER BY id"):
        count += 1
        expected = _digest(prev_hash, r["ts"], r["actor"], r["action"], r["basis"],
                           r["level"], r["outcome"], r["details"])
        if r["prev_hash"] != prev_hash or r["hash"] != expected:
            return False, r["id"], count
        prev_hash = r["hash"]
    return True, None, count


def head(conn):
    row = conn.execute("SELECT id, hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return (row["id"], row["hash"]) if row else (0, GENESIS)
