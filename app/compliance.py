"""UK statutory deadlines for a CIC (company limited by guarantee).

Rules per gov.uk / Companies House, checked October 2026. When a company number is
configured, agent A1 replaces computed dates with the dates Companies House holds.
"""
import calendar
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

HORIZON_DAYS = 800


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def first_ard(cfg) -> date:
    inc = cfg.incorporation_date
    if cfg.ard:
        m, d = (int(x) for x in cfg.ard.split("-"))
        candidate = date(inc.year, m, d)
        while candidate <= inc:
            candidate = candidate.replace(year=candidate.year + 1)
        return candidate
    return month_end(inc + relativedelta(years=1))


def statutory_deadlines(cfg, today: date):
    inc = cfg.incorporation_date
    if not inc:
        return []
    out = []
    horizon = today + timedelta(days=HORIZON_DAYS)
    keep_from = today - timedelta(days=90)

    def add(key, title, due, who, note, source="obliczone"):
        if keep_from <= due <= horizon:
            out.append({"key": key, "title": title, "due": due, "who": who, "note": note, "source": source})

    ard = first_ard(cfg)
    n = 1
    while ard <= horizon:
        due = inc + relativedelta(months=21) if n == 1 else ard + relativedelta(months=9)
        add(f"accounts-{ard.isoformat()}", f"Sprawozdanie roczne i raport CIC34 za rok do {ard:%d.%m.%Y}",
            due, "Dyrektor (dane od A2 i księgowego)", "Opłata £15. Spóźnienie: kara od £150.")
        ard = ard + relativedelta(years=1)
        ard = month_end(ard) if cfg.ard == "" else ard
        n += 1

    review = cfg.last_confirmation_date + relativedelta(years=1) if cfg.last_confirmation_date \
        else inc + relativedelta(years=1)
    while review <= horizon:
        add(f"confirmation-{review.isoformat()}", "Confirmation statement",
            review + timedelta(days=14), "Dyrektor", f"Data przeglądu {review:%d.%m.%Y}, 14 dni na złożenie. Opłata £50.")
        review = review + relativedelta(years=1)

    start = cfg.trading_start or inc
    add("ct-register", "Rejestracja do Corporation Tax w HMRC", start + relativedelta(months=3),
        "Dyrektor", "3 miesiące od rozpoczęcia działalności. Także gdy CIC nie ma zysku.")

    ard = first_ard(cfg)
    period_start = start
    while period_start <= horizon:
        period_end = min(period_start + relativedelta(years=1) - timedelta(days=1), ard)
        add(f"ct-pay-{period_end.isoformat()}", f"Zapłata Corporation Tax za okres do {period_end:%d.%m.%Y}",
            period_end + relativedelta(months=9) + timedelta(days=1), "Dyrektor (płatność poziomu 3)",
            "Do potwierdzenia z księgowym.")
        add(f"ct600-{period_end.isoformat()}", f"Zeznanie CT600 za okres do {period_end:%d.%m.%Y}",
            period_end + relativedelta(months=12), "Dyrektor lub księgowy", "Do potwierdzenia z księgowym.")
        period_start = period_end + timedelta(days=1)
        if period_end == ard:
            ard = ard + relativedelta(years=1)
            ard = month_end(ard) if cfg.ard == "" else ard

    if cfg.ico_registration_date:
        renew = cfg.ico_registration_date + relativedelta(years=1)
        while renew <= horizon:
            add(f"ico-{renew.isoformat()}", "Odnowienie opłaty ochrony danych (ICO)", renew, "Dyrektor",
                "Opłata roczna za rejestrację w ICO.")
            renew = renew + relativedelta(years=1)

    return sorted(out, key=lambda d: d["due"])


SETUP_TASKS = [
    ("setup-name", "Wybrać nazwę CIC i sprawdzić dostępność w Companies House", "Ludzie"),
    ("setup-region", "Ustalić region działania (wpis do CIC36)", "Ludzie"),
    ("setup-director2", "Znaleźć drugiego, niezależnego dyrektora", "Ludzie"),
    ("setup-safeguarding", "Wyznaczyć osobę odpowiedzialną za safeguarding", "Ludzie"),
    ("setup-idv", "Weryfikacja tożsamości dyrektorów (GOV.UK One Login)", "Każdy dyrektor"),
    ("setup-incorporate", "Złożyć wniosek o rejestrację CIC (IN01 + CIC36), £115", "Dyrektor"),
    ("setup-mfa", "Włączyć MFA na poczcie, panelu i koncie Anthropic", "Każdy dyrektor"),
    ("setup-resolution", "Uchwała zarządu: zasady pracy agentów i poziomy zatwierdzeń", "Zarząd"),
]

POST_INCORPORATION_TASKS = [
    ("post-bank", "Konto bankowe z podwójną autoryzacją przelewów", "Dyrektorzy"),
    ("post-ico", "Rejestracja w ICO i opłata roczna", "Dyrektor"),
    ("post-config", "Wpisać numer spółki i daty do config/cic.yaml", "Dyrektor"),
    ("post-policies", "Polityki: prywatność, safeguarding, konflikty interesów", "Zarząd"),
]
