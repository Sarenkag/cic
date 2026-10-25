"""Accessible web panel for directors."""
import secrets
import threading
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import agents, approvals, audit, auth, config, db
from .approvals import LEVEL_NAMES
from .db import now_iso
from .registry import AGENTS, BY_CODE, IMPLEMENTED

HERE = Path(__file__).parent
app = FastAPI(title="Panel CIC", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["todate"] = date.fromisoformat
security = HTTPBasic(realm="Panel CIC")


def current_user(creds: HTTPBasicCredentials = Depends(security)) -> str:
    stored = auth.users().get(creds.username)
    if not stored or not auth.check_password(creds.password, stored):
        with db.session() as conn:
            audit.record(conn, "panel", "nieudane logowanie", details={"login": creds.username[:40]})
        raise HTTPException(401, "Nieprawidłowy login lub hasło", headers={"WWW-Authenticate": 'Basic realm="Panel CIC"'})
    return creds.username


def check_csrf(user, token):
    if not secrets.compare_digest(token or "", auth.csrf_token(user)):
        raise HTTPException(403, "Nieprawidłowy formularz. Odśwież stronę i spróbuj ponownie.")


def render(request, name, user, **ctx):
    cfg = config.get()
    with db.session() as conn:
        counts = {
            "zatwierdzenia": conn.execute("SELECT COUNT(*) FROM approvals WHERE status='oczekuje'").fetchone()[0],
            "alarmy": conn.execute("SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL").fetchone()[0],
        }
    return templates.TemplateResponse(request, name, {
        "user": user, "user_name": cfg.director_name(user), "cic": cfg, "csrf": auth.csrf_token(user),
        "counts": counts, "msg": request.query_params.get("msg"), "LEVEL_NAMES": LEVEL_NAMES, **ctx})


def back(path, msg):
    return RedirectResponse(f"{path}?msg={quote(msg)}", status_code=303)


@app.get("/zdrowie")
def health():
    return JSONResponse({"ok": True})


@app.get("/")
def home(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        report = conn.execute("SELECT * FROM reports WHERE kind='poranny' ORDER BY id DESC LIMIT 1").fetchone()
        deadlines = conn.execute("SELECT * FROM deadlines WHERE done_at IS NULL ORDER BY due LIMIT 5").fetchall()
    return render(request, "home.html", user, report=report, deadlines=deadlines, today=date.today())


@app.get("/zatwierdzenia")
def approvals_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        pend = conn.execute("SELECT * FROM approvals WHERE status='oczekuje' ORDER BY created").fetchall()
        done = conn.execute("SELECT * FROM approvals WHERE status!='oczekuje' ORDER BY decided DESC LIMIT 30").fetchall()
        votes = {}
        for r in conn.execute("SELECT * FROM approval_votes"):
            votes.setdefault(r["approval_id"], []).append(r)
    return render(request, "approvals.html", user, pending=pend, done=done, votes=votes)


@app.post("/zatwierdzenia/{approval_id}")
def approvals_vote(approval_id: int, decision: str = Form(...), csrf: str = Form(...),
                   user: str = Depends(current_user)):
    check_csrf(user, csrf)
    with db.session() as conn:
        try:
            status = approvals.vote(conn, config.get(), approval_id, user, decision)
        except approvals.ApprovalError as exc:
            return back("/zatwierdzenia", f"Nie zapisano: {exc}")
    return back("/zatwierdzenia", f"Zapisano głos. Status sprawy: {status}.")


@app.get("/terminy")
def deadlines_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM deadlines ORDER BY done_at IS NOT NULL, due").fetchall()
    return render(request, "deadlines.html", user, rows=rows, today=date.today())


@app.post("/terminy/{key}/wykonane")
def deadline_done(key: str, csrf: str = Form(...), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    with db.session() as conn:
        row = conn.execute("SELECT title FROM deadlines WHERE key=?", (key,)).fetchone()
        if not row:
            return back("/terminy", "Nie ma takiego terminu.")
        conn.execute("UPDATE deadlines SET done_at=?, done_by=? WHERE key=?", (now_iso(), user, key))
        conn.execute("UPDATE alerts SET resolved_at=?, resolved_by=? WHERE key=? AND resolved_at IS NULL",
                     (now_iso(), user, f"overdue-{key}"))
        audit.record(conn, f"dyrektor:{user}", f"oznaczono jako wykonane: {row['title']}")
    return back("/terminy", f"Oznaczono jako wykonane: {row['title']}.")


@app.get("/zadania")
def tasks_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY status='zrobione', COALESCE(due,'9999'), id").fetchall()
    return render(request, "tasks.html", user, rows=rows)


@app.post("/zadania/{task_id}")
def task_update(task_id: int, status: str = Form(...), csrf: str = Form(...), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    if status not in ("otwarte", "zrobione"):
        return back("/zadania", "Nieznany status.")
    with db.session() as conn:
        row = conn.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return back("/zadania", "Nie ma takiego zadania.")
        conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        audit.record(conn, f"dyrektor:{user}", f"zadanie '{row['title']}': {status}")
    return back("/zadania", f"Zadanie „{row['title']}”: {status}.")


@app.get("/alarmy")
def alerts_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY resolved_at IS NOT NULL, id DESC LIMIT 100").fetchall()
    return render(request, "alerts.html", user, rows=rows)


@app.post("/alarmy/{alert_id}")
def alert_resolve(alert_id: int, csrf: str = Form(...), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    with db.session() as conn:
        row = conn.execute("SELECT message FROM alerts WHERE id=?", (alert_id,)).fetchone()
        if not row:
            return back("/alarmy", "Nie ma takiego alarmu.")
        conn.execute("UPDATE alerts SET resolved_at=?, resolved_by=? WHERE id=?", (now_iso(), user, alert_id))
        audit.record(conn, f"dyrektor:{user}", "zamknięto alarm", details=row["message"])
    return back("/alarmy", "Alarm zamknięty.")


@app.get("/agenci")
def agents_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        agents.ensure_state(conn)
        state = {r["code"]: r for r in conn.execute("SELECT * FROM agent_state")}
    return render(request, "agents.html", user, agents=AGENTS, state=state, implemented=IMPLEMENTED)


@app.post("/agenci/{code}/wstrzymaj")
def agent_pause(code: str, csrf: str = Form(...), reason: str = Form(""), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    codes = [a["code"] for a in AGENTS] if code == "wszyscy" else [code]
    if any(c not in BY_CODE for c in codes):
        return back("/agenci", "Nieznany agent.")
    with db.session() as conn:
        agents.ensure_state(conn)
        for c in codes:
            agents.pause(conn, c, f"dyrektor:{user}", reason or "wyłącznik w panelu")
    return back("/agenci", "Wstrzymano: " + ("wszystkich agentów" if code == "wszyscy" else BY_CODE[code]["name"]) + ".")


@app.post("/agenci/{code}/wznow")
def agent_resume(code: str, csrf: str = Form(...), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    if code not in BY_CODE:
        return back("/agenci", "Nieznany agent.")
    with db.session() as conn:
        approvals.create(conn, f"dyrektor:{user}", "wznowienie_agenta", f"Wznowić agenta {BY_CODE[code]['name']}",
                         level=3, payload={"code": code}, detail="Wznowienie wymaga dwóch dyrektorów.")
    return back("/agenci", "Utworzono prośbę o wznowienie. Potrzebne są głosy dwóch dyrektorów.")


@app.post("/agenci/{code}/uruchom")
def agent_run_now(code: str, csrf: str = Form(...), user: str = Depends(current_user)):
    check_csrf(user, csrf)
    if code not in IMPLEMENTED:
        return back("/agenci", "Ten agent nie jest jeszcze wdrożony.")
    threading.Thread(target=agents.run, args=(code,), kwargs={"trigger": f"panel:{user}"}, daemon=True).start()
    return back("/agenci", f"Uruchomiono agenta {BY_CODE[code]['name']}. Wynik pojawi się w dzienniku.")


@app.get("/dziennik")
def audit_page(request: Request, user: str = Depends(current_user)):
    with db.session() as conn:
        ok, bad_id, count = audit.verify(conn)
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
    return render(request, "audit.html", user, rows=rows, ok=ok, bad_id=bad_id, count=count)
