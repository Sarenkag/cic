"""Agent runner: every run checks the kill switch and leaves an audit entry."""
import traceback

from .. import audit, config, db
from ..db import now_iso
from ..registry import AGENTS


def ensure_state(conn):
    for a in AGENTS:
        conn.execute("INSERT OR IGNORE INTO agent_state (code) VALUES (?)", (a["code"],))


def raise_alert(conn, agent, severity, message, key=None):
    if key and conn.execute("SELECT 1 FROM alerts WHERE key=? AND resolved_at IS NULL", (key,)).fetchone():
        return
    if key:
        conn.execute("DELETE FROM alerts WHERE key=? AND resolved_at IS NOT NULL", (key,))
    conn.execute("INSERT INTO alerts (key, created, agent, severity, message) VALUES (?,?,?,?,?)",
                 (key, now_iso(), agent, severity, message))
    audit.record(conn, agent, "alarm", outcome=severity, details=message)


def upsert_task(conn, key, agent, title, owner, detail=None, due=None):
    conn.execute(
        "INSERT INTO tasks (key, created, agent, title, detail, owner, due) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(key) DO UPDATE SET title=excluded.title, detail=excluded.detail, due=excluded.due",
        (key, now_iso(), agent, title, detail, owner, due))


def run(code, *, cfg=None, conn=None, trigger="harmonogram"):
    from . import koordynator, lad, straznik
    impl = {"A0": koordynator.run, "A1": lad.run, "A8": straznik.run}.get(code)
    cfg = cfg or config.get()
    own = conn is None
    conn = conn or db.connect()
    try:
        ensure_state(conn)
        if impl is None:
            return "nie wdrożony"
        state = conn.execute("SELECT * FROM agent_state WHERE code=?", (code,)).fetchone()
        # A8 keeps running when others are paused, unless it was paused itself.
        if state["paused"]:
            audit.record(conn, code, "pominięto uruchomienie", outcome="wstrzymany",
                         details={"trigger": trigger, "reason": state["reason"]})
            return "wstrzymany"
        try:
            summary = impl(conn, cfg)
            status = "ok"
            audit.record(conn, code, "uruchomienie", outcome="ok", details={"trigger": trigger, "summary": summary})
        except Exception as exc:  # noqa: BLE001 - every failure must reach the log and the directors
            status = f"błąd: {exc}"
            audit.record(conn, code, "uruchomienie", outcome="błąd",
                         details={"trigger": trigger, "error": traceback.format_exc(limit=5)})
            raise_alert(conn, code, "wysoki", f"Agent {code} zakończył się błędem: {exc}", key=f"run-fail-{code}")
        conn.execute("UPDATE agent_state SET last_run=?, last_status=? WHERE code=?", (now_iso(), status, code))
        return status
    finally:
        if own:
            conn.close()


def pause(conn, code, by, reason):
    conn.execute("UPDATE agent_state SET paused=1, paused_by=?, paused_at=?, reason=? WHERE code=?",
                 (by, now_iso(), reason, code))
    audit.record(conn, by, f"wstrzymano agenta {code}", level=0, outcome="wstrzymany", details=reason)
