"""Four approval levels. Agents only prepare; people decide."""
import json

from . import audit
from .db import now_iso

REQUIRED = {0: 0, 1: 0, 2: 1, 3: 2}
LEVEL_NAMES = {0: "automat", 1: "automat z raportem", 2: "jeden dyrektor", 3: "dwóch dyrektorów"}


class ApprovalError(Exception):
    pass


def level_for_payment(amount_pence, cfg):
    return 2 if amount_pence <= cfg.single_director_limit_pence else 3


def create(conn, agent, kind, title, *, level, detail=None, amount_pence=None, payload=None, key=None):
    if level not in (2, 3):
        raise ApprovalError("Zatwierdzenia dotyczą tylko poziomów 2 i 3")
    if key:
        row = conn.execute("SELECT id FROM approvals WHERE key=?", (key,)).fetchone()
        if row:
            return row["id"]
    cur = conn.execute(
        "INSERT INTO approvals (key, created, agent, kind, title, detail, amount_pence, level, required, payload)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (key, now_iso(), agent, kind, title, detail, amount_pence, level, REQUIRED[level],
         json.dumps(payload, ensure_ascii=False) if payload else None),
    )
    audit.record(conn, agent, f"prośba o zatwierdzenie: {title}", level=level,
                 outcome="oczekuje", details={"approval_id": cur.lastrowid, "kind": kind})
    return cur.lastrowid


def vote(conn, cfg, approval_id, user, decision):
    if user not in cfg.directors:
        raise ApprovalError("Głosować mogą tylko dyrektorzy wpisani w konfiguracji")
    if decision not in ("tak", "nie"):
        raise ApprovalError("Decyzja musi być 'tak' albo 'nie'")
    ap = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not ap:
        raise ApprovalError("Nie ma takiej prośby")
    if ap["status"] != "oczekuje":
        raise ApprovalError("Ta prośba jest już rozstrzygnięta")
    if conn.execute("SELECT 1 FROM approval_votes WHERE approval_id=? AND user=?",
                    (approval_id, user)).fetchone():
        raise ApprovalError("Już głosowałeś w tej sprawie")
    conn.execute("INSERT INTO approval_votes (approval_id, user, vote, ts) VALUES (?,?,?,?)",
                 (approval_id, user, decision, now_iso()))
    status = "oczekuje"
    if decision == "nie":
        status = "odrzucone"
    else:
        yes = [r["user"] for r in conn.execute(
            "SELECT user FROM approval_votes WHERE approval_id=? AND vote='tak'", (approval_id,))]
        if len(yes) >= ap["required"] and _independence_ok(cfg, ap["level"], yes):
            status = "zatwierdzone"
    if status != "oczekuje":
        conn.execute("UPDATE approvals SET status=?, decided=? WHERE id=?", (status, now_iso(), approval_id))
    audit.record(conn, f"dyrektor:{user}", f"głos '{decision}': {ap['title']}", level=ap["level"],
                 outcome=status, details={"approval_id": approval_id})
    if status == "zatwierdzone":
        _execute_internal(conn, ap, user)
    return status


def _independence_ok(cfg, level, yes_voters):
    """Level 3 needs one independent director, once any director is marked independent."""
    if level < 3:
        return True
    independents = {k for k, d in cfg.directors.items() if d.get("independent")}
    return not independents or bool(independents & set(yes_voters))


def _execute_internal(conn, ap, user):
    """Only internal actions run automatically. Filings and payments are done by a person."""
    payload = json.loads(ap["payload"]) if ap["payload"] else {}
    if ap["kind"] == "wznowienie_agenta":
        code = payload["code"]
        conn.execute("UPDATE agent_state SET paused=0, paused_by=NULL, paused_at=NULL, reason=NULL WHERE code=?",
                     (code,))
        audit.record(conn, "system", f"wznowiono agenta {code}", level=3, outcome="wykonane",
                     details={"approval_id": ap["id"]})


def pending(conn):
    return conn.execute("SELECT * FROM approvals WHERE status='oczekuje' ORDER BY created").fetchall()
