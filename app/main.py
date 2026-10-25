"""Entry point: create the database, start the schedule, serve the panel."""
import os

import uvicorn

from . import agents, audit, config, db, scheduler


def bootstrap():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg = config.get()
    with db.session() as conn:
        db.init(conn)
        agents.ensure_state(conn)
        audit.record(conn, "system", "start kontenera", details={"cic": cfg.name, "model": cfg.model})
    return cfg


def main():
    cfg = bootstrap()
    if not os.environ.get("CIC_SECRET"):
        raise SystemExit("Ustaw CIC_SECRET w pliku .env")
    scheduler.start(cfg)
    uvicorn.run("app.web:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=True, log_level="info")


if __name__ == "__main__":
    main()
