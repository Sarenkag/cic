"""Configuration: YAML file plus environment overrides."""
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(os.environ.get("CIC_CONFIG", "/app/config/cic.yaml"))
DATA_DIR = Path(os.environ.get("CIC_DATA", "/data"))


def _date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class Config:
    def __init__(self, raw: dict):
        self.raw = raw
        cic = raw.get("cic") or {}
        company = raw.get("company") or {}
        self.name = cic.get("name") or "CIC (nazwa do ustalenia)"
        self.region = cic.get("region") or ""
        self.timezone = cic.get("timezone") or "Europe/London"
        self.company_number = os.environ.get("CIC_COMPANY_NUMBER") or company.get("number") or ""
        self.incorporation_date = _date(company.get("incorporation_date"))
        self.trading_start = _date(company.get("trading_start")) or self.incorporation_date
        self.ard = company.get("accounting_reference_date") or ""
        self.last_confirmation_date = _date(company.get("last_confirmation_date"))
        self.ico_registration_date = _date((raw.get("ico") or {}).get("registration_date"))
        self.directors = raw.get("directors") or {}
        appr = raw.get("approvals") or {}
        self.single_director_limit_pence = int(float(appr.get("single_director_limit_gbp", 250)) * 100)
        self.warnings_days = sorted(raw.get("warnings_days") or [60, 30, 14, 7], reverse=True)
        self.schedule = raw.get("schedule") or {}
        llm = raw.get("llm") or {}
        self.model = os.environ.get("CIC_MODEL") or llm.get("model") or "claude-opus-5-5"
        self.effort = llm.get("effort") or "low"

    def director_emails(self):
        return [d["email"] for d in self.directors.values() if d.get("email")]

    def director_name(self, login):
        return (self.directors.get(login) or {}).get("name") or login


@lru_cache(maxsize=1)
def get() -> Config:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return Config(yaml.safe_load(fh) or {})


def load_from(path) -> Config:
    with open(path, encoding="utf-8") as fh:
        return Config(yaml.safe_load(fh) or {})
