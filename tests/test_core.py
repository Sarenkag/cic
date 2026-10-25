import sqlite3
from datetime import date

import pytest

from app import agents, approvals, audit, config, db
from app.compliance import statutory_deadlines

CFG_YAML = """
cic: {name: Test CIC}
company: {incorporation_date: "2026-11-15"}
directors:
  anna: {name: Anna, independent: false}
  ben: {name: Ben, independent: true}
  cara: {name: Cara, independent: false}
approvals: {single_director_limit_gbp: 250}
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "cic.yaml").write_text(CFG_YAML)
    cfg = config.load_from(tmp_path / "cic.yaml")
    conn = db.connect(tmp_path / "cic.db")
    db.init(conn)
    agents.ensure_state(conn)
    yield cfg, conn
    conn.close()


def test_audit_is_append_only_and_chained(env):
    _, conn = env
    audit.record(conn, "A0", "a")
    audit.record(conn, "A1", "b", details={"x": 1})
    assert audit.verify(conn)[0]
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET action='zmiana' WHERE id=1")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log")


def test_tampering_is_detected(env):
    _, conn = env
    audit.record(conn, "A0", "a")
    audit.record(conn, "A0", "b")
    conn.execute("DROP TRIGGER audit_no_update")
    conn.execute("UPDATE audit_log SET action='podmiana' WHERE id=1")
    ok, bad, _ = audit.verify(conn)
    assert not ok and bad == 1


def test_first_deadlines(env):
    cfg, _ = env
    keys = [d["key"] for d in statutory_deadlines(cfg, date(2027, 6, 1))]
    assert "accounts-2027-11-30" in keys
    acc = next(d for d in statutory_deadlines(cfg, date(2027, 6, 1)) if d["key"] == "accounts-2027-11-30")
    assert acc["due"] == date(2028, 8, 15)          # 21 months after incorporation
    conf = next(d for d in statutory_deadlines(cfg, date(2027, 6, 1)) if d["key"].startswith("confirmation-"))
    assert conf["due"] == date(2027, 11, 29)        # review 15.11.2027 + 14 days
    reg = next(d for d in statutory_deadlines(cfg, date(2027, 1, 1)) if d["key"] == "ct-register")
    assert reg["due"] == date(2027, 2, 15)
    ct = [d for d in statutory_deadlines(cfg, date(2027, 6, 1)) if d["key"].startswith("ct-pay-")]
    assert ct[0]["key"] == "ct-pay-2027-11-14"      # first CT period is at most 12 months


def test_payment_needs_two_directors_including_independent(env):
    cfg, conn = env
    level = approvals.level_for_payment(42000, cfg)
    assert level == 3
    ap = approvals.create(conn, "A2", "płatność", "Sprzęt", level=level, amount_pence=42000)
    assert approvals.vote(conn, cfg, ap, "anna", "tak") == "oczekuje"
    assert approvals.vote(conn, cfg, ap, "cara", "tak") == "oczekuje"   # no independent yet
    assert approvals.vote(conn, cfg, ap, "ben", "tak") == "zatwierdzone"
    with pytest.raises(approvals.ApprovalError):
        approvals.vote(conn, cfg, ap, "ben", "tak")


def test_small_payment_one_director_and_outsider_rejected(env):
    cfg, conn = env
    ap = approvals.create(conn, "A2", "płatność", "Kawa", level=approvals.level_for_payment(1200, cfg))
    with pytest.raises(approvals.ApprovalError):
        approvals.vote(conn, cfg, ap, "agent", "tak")
    assert approvals.vote(conn, cfg, ap, "anna", "tak") == "zatwierdzone"


def test_pause_skips_runs_and_resume_needs_two(env):
    cfg, conn = env
    agents.pause(conn, "A1", "dyrektor:anna", "test")
    assert agents.run("A1", cfg=cfg, conn=conn) == "wstrzymany"
    ap = approvals.create(conn, "dyrektor:anna", "wznowienie_agenta", "Wznowić", level=3, payload={"code": "A1"})
    approvals.vote(conn, cfg, ap, "anna", "tak")
    assert conn.execute("SELECT paused FROM agent_state WHERE code='A1'").fetchone()[0] == 1
    approvals.vote(conn, cfg, ap, "ben", "tak")
    assert conn.execute("SELECT paused FROM agent_state WHERE code='A1'").fetchone()[0] == 0


def test_phase0_run_without_api_key(env, monkeypatch):
    cfg, conn = env
    monkeypatch.setattr(db, "db_path", lambda: config.DATA_DIR / "cic.db")
    assert agents.run("A1", cfg=cfg, conn=conn) == "ok"
    assert agents.run("A8", cfg=cfg, conn=conn) == "ok"
    assert agents.run("A0", cfg=cfg, conn=conn) == "ok"
    body = conn.execute("SELECT body FROM reports ORDER BY id DESC").fetchone()[0]
    assert body.startswith("Raport poranny dla Test CIC")
    assert audit.verify(conn)[0]
    assert list((config.DATA_DIR / "backups").glob("cic-*.db"))
