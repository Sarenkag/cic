"""A8 Strażnik: audit-chain integrity, backups, stale agents, failed logins."""
import sqlite3
from datetime import datetime, timedelta, timezone

from .. import audit, config, notify
from ..db import db_path
from ..registry import IMPLEMENTED
from . import pause, raise_alert

CODE = "A8"
KEEP_BACKUPS = 30


def backup(conn):
    target_dir = config.DATA_DIR / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target = target_dir / f"cic-{stamp}.db"
    dest = sqlite3.connect(str(target))
    with dest:
        conn.backup(dest)
    dest.close()
    head_id, head_hash = audit.head(conn)
    (target_dir / "audit-head.txt").write_text(f"{stamp} {head_id} {head_hash}\n", encoding="utf-8")
    old = sorted(target_dir.glob("cic-*.db"))[:-KEEP_BACKUPS]
    for f in old:
        f.unlink()
    return target.name


def run(conn, cfg):
    findings = []
    ok, bad_id, count = audit.verify(conn)
    if not ok:
        msg = f"Dziennik audytowy został naruszony (wpis {bad_id}). Wstrzymuję wszystkich agentów."
        for code in IMPLEMENTED - {CODE}:
            pause(conn, code, CODE, msg)
        raise_alert(conn, CODE, "krytyczny", msg, key="audit-broken")
        notify.send(cfg.director_emails(), "[Strażnik] Naruszony dziennik audytowy", msg)
        findings.append(msg)

    name = backup(conn) if db_path().exists() else None

    now = datetime.now(timezone.utc)
    for row in conn.execute("SELECT * FROM agent_state"):
        if row["code"] not in IMPLEMENTED or row["code"] == CODE or row["paused"]:
            continue
        if not row["last_run"]:
            continue
        key = f"stale-{row['code']}"
        if now - datetime.fromisoformat(row["last_run"]) > timedelta(hours=26):
            raise_alert(conn, CODE, "średni", f"Agent {row['code']} nie działał od ponad doby.", key=key)
        else:
            conn.execute("UPDATE alerts SET resolved_at=?, resolved_by=? WHERE key=? AND resolved_at IS NULL",
                         (now.replace(microsecond=0).isoformat(), CODE, key))

    since = (now - timedelta(hours=24)).isoformat()
    failed = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='nieudane logowanie' AND ts>=?",
                          (since,)).fetchone()[0]
    if failed >= 10:
        msg = f"{failed} nieudanych logowań do panelu w ciągu doby."
        raise_alert(conn, CODE, "wysoki", msg, key=f"logins-{now:%Y-%m-%d}")
        notify.send(cfg.director_emails(), "[Strażnik] Próby logowania", msg)
    return {"dziennik_ok": ok, "wpisów": count, "kopia": name, "nieudane_logowania": failed, "uwagi": findings}
