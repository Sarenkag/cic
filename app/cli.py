"""Command line: `python -m app.cli run A1`, `verify`, `hash-password`."""
import getpass
import sys

from . import agents, audit, auth, db
from .main import bootstrap


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print("Użycie: python -m app.cli run A0|A1|A8 | run-all | verify | hash-password | resume KOD")
        return 0
    cmd = argv[0]
    if cmd == "hash-password":
        pw = getpass.getpass("Hasło: ")
        if pw != getpass.getpass("Powtórz: "):
            print("Hasła się różnią.")
            return 1
        print(auth.hash_password(pw))
        return 0
    bootstrap()
    if cmd == "run":
        print(agents.run(argv[1], trigger="cli"))
    elif cmd == "run-all":
        for code in ("A1", "A8", "A0"):
            print(code, agents.run(code, trigger="cli"))
    elif cmd == "resume":
        # Break-glass for a board that has only one director so far; still logged.
        with db.session() as conn:
            conn.execute("UPDATE agent_state SET paused=0, paused_by=NULL, paused_at=NULL, reason=NULL WHERE code=?",
                         (argv[1],))
            audit.record(conn, "konsola-serwera", f"wznowiono agenta {argv[1]} z konsoli", level=3,
                         outcome="wykonane", details="awaryjnie, poza panelem")
        print(f"Wznowiono {argv[1]} (wpis w dzienniku).")
    elif cmd == "verify":
        with db.session() as conn:
            ok, bad, count = audit.verify(conn)
        print(f"Dziennik: {'OK' if ok else f'NARUSZONY od wpisu {bad}'} ({count} wpisów)")
        return 0 if ok else 2
    else:
        print(f"Nieznane polecenie: {cmd}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
