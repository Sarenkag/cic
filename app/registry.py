"""The ten agents from the plan. Only phase-0 agents have an implementation yet."""

AGENTS = [
    {"code": "A0", "slug": "koordynator", "name": "Koordynator", "phase": 0,
     "role": "Raport poranny, rejestr zadań, kolejka zatwierdzeń."},
    {"code": "A1", "slug": "lad", "name": "Ład i zgodność", "phase": 0,
     "role": "Terminy ustawowe, rejestry spółki, Companies House (tylko odczyt)."},
    {"code": "A2", "slug": "finanse", "name": "Finanse i księgowość", "phase": 1,
     "role": "Uzgadnianie banku, budżet, granty celowe, prognoza gotówki."},
    {"code": "A3", "slug": "granty", "name": "Granty i finansowanie", "phase": 1,
     "role": "Konkursy, wnioski, rejestr zobowiązań wobec grantodawców."},
    {"code": "A4", "slug": "wsparcie", "name": "Wsparcie podopiecznych", "phase": 2,
     "role": "Pierwszy kontakt, zapisy, przekazanie spraw człowiekowi."},
    {"code": "A5", "slug": "szkolenia", "name": "Szkolenia i wpływ", "phase": 2,
     "role": "Zajęcia, materiały dostępne, pomiar wpływu."},
    {"code": "A6", "slug": "marketing", "name": "Marketing i komunikacja", "phase": 2,
     "role": "Plan treści, strona, newsletter."},
    {"code": "A7", "slug": "dostepnosc", "name": "Dostępność", "phase": 2,
     "role": "Bramka WCAG 2.2 AA przed każdą publikacją."},
    {"code": "A8", "slug": "straznik", "name": "Strażnik bezpieczeństwa", "phase": 0,
     "role": "Integralność dziennika, kopie zapasowe, wyłącznik awaryjny."},
    {"code": "A9", "slug": "strategia", "name": "Strategia i rozwój", "phase": 3,
     "role": "Wskaźniki, rejestr ryzyk, pakiet dla zarządu."},
]

BY_CODE = {a["code"]: a for a in AGENTS}
BY_SLUG = {a["slug"]: a for a in AGENTS}
IMPLEMENTED = {"A0", "A1", "A8"}
