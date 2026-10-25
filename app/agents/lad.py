"""A1 Ład i zgodność: statutory deadlines, setup checklist, Companies House (read-only)."""
import base64
import json
import os
import urllib.request
from datetime import date

from .. import approvals, audit
from ..compliance import POST_INCORPORATION_TASKS, SETUP_TASKS, statutory_deadlines
from . import raise_alert, upsert_task

CODE = "A1"
CH_API = "https://api.company-information.service.gov.uk/company/"
FILINGS_NEEDING_SIGNOFF = ("accounts-", "confirmation-")


def companies_house_profile(number):
    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not (number and key):
        return None
    req = urllib.request.Request(CH_API + number)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{key}:".encode()).decode())
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def run(conn, cfg, today=None):
    today = today or date.today()
    if not cfg.incorporation_date:
        for key, title, owner in SETUP_TASKS:
            upsert_task(conn, key, CODE, title, owner)
        return {"etap": "przed rejestracją", "zadania": len(SETUP_TASKS)}

    for key, title, owner in POST_INCORPORATION_TASKS:
        upsert_task(conn, key, CODE, title, owner)

    items = statutory_deadlines(cfg, today)
    profile = None
    try:
        profile = companies_house_profile(cfg.company_number)
    except Exception as exc:  # noqa: BLE001
        raise_alert(conn, CODE, "średni", f"Nie udało się odczytać danych z Companies House: {exc}", key="ch-read")
    if profile:
        _apply_companies_house(conn, items, profile)

    for it in items:
        conn.execute(
            "INSERT INTO deadlines (key, title, due, who, source, note) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET title=excluded.title, due=excluded.due, who=excluded.who,"
            " source=excluded.source, note=excluded.note",
            (it["key"], it["title"], it["due"].isoformat(), it["who"], it["source"], it["note"]))

    warnings = []
    for row in conn.execute("SELECT * FROM deadlines WHERE done_at IS NULL ORDER BY due"):
        left = (date.fromisoformat(row["due"]) - today).days
        if left < 0:
            raise_alert(conn, CODE, "wysoki", f"Termin minął {-left} dni temu: {row['title']}",
                        key=f"overdue-{row['key']}")
        if left <= max(cfg.warnings_days):
            warnings.append({"key": row["key"], "title": row["title"], "due": row["due"], "days_left": left})
        if left <= 30 and row["key"].startswith(FILINGS_NEEDING_SIGNOFF):
            approvals.create(conn, CODE, "zgłoszenie_urzędowe", f"Złożyć: {row['title']}", level=3,
                             detail=f"Termin {row['due']}. Agent przygotowuje dane; składa dyrektor w Companies House.",
                             key=f"filing-{row['key']}")
    return {"terminy": len(items), "ostrzeżenia": warnings, "companies_house": bool(profile)}


def _apply_companies_house(conn, items, profile):
    """Companies House is authoritative for accounts and confirmation statement dates."""
    if profile.get("company_status") not in (None, "active"):
        raise_alert(conn, CODE, "wysoki", f"Status spółki w Companies House: {profile.get('company_status')}",
                    key="ch-status")
    ch = {
        "accounts-": (profile.get("accounts") or {}).get("next_due"),
        "confirmation-": (profile.get("confirmation_statement") or {}).get("next_due"),
    }
    for prefix, due in ch.items():
        if not due:
            continue
        upcoming = [it for it in items if it["key"].startswith(prefix)]
        if upcoming:
            first = upcoming[0]
            if first["due"].isoformat() != due:
                audit.record(conn, CODE, "termin poprawiony według Companies House",
                             details={"key": first["key"], "obliczony": first["due"].isoformat(), "ch": due})
            first["due"] = date.fromisoformat(due)
            first["source"] = "Companies House"
