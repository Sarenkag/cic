"""Daily schedule in UK time."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import agents

JOBS = [("A1", "lad", "07:30"), ("A8", "straznik", "07:45"), ("A0", "koordynator", "08:00")]


def start(cfg):
    sched = BackgroundScheduler(timezone=cfg.timezone)
    for code, slug, default in JOBS:
        hh, mm = (cfg.schedule.get(slug) or default).split(":")
        sched.add_job(agents.run, CronTrigger(hour=int(hh), minute=int(mm), timezone=cfg.timezone),
                      args=[code], id=slug, misfire_grace_time=3600, coalesce=True)
    sched.start()
    return sched
