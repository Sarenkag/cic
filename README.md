# CIC: sieć agentów, faza 0

Kontener `cic` w projekcie Docker Compose `protosystem`. Wdraża fazę 0 z planu
„Sieć agentów AI prowadzących CIC”:

- **A0 Koordynator**: codziennie o 8:00 raport poranny do odsłuchu (w panelu i opcjonalnie e-mailem).
- **A1 Ład i zgodność**: o 7:30 przelicza terminy ustawowe (sprawozdania + CIC34, confirmation
  statement, Corporation Tax, CT600, ICO), ostrzega na 60/30/14/7 dni, przed rejestracją prowadzi
  listę zadań przygotowawczych. Z numerem spółki i kluczem API czyta daty z Companies House.
  Na 30 dni przed zgłoszeniem tworzy prośbę o zatwierdzenie dla dwóch dyrektorów.
- **A8 Strażnik**: o 7:45 sprawdza nienaruszalność dziennika audytowego, robi kopię bazy,
  pilnuje, czy agenci działają, liczy nieudane logowania. Przy naruszeniu dziennika wstrzymuje agentów.

Panel dla dyrektorów (dostępny dla czytników ekranu): raport, zatwierdzenia, terminy, zadania,
alarmy, agenci (wyłącznik awaryjny), dziennik audytowy. Agenci A2–A9 są widoczne jako planowane.

Zasady wbudowane w kod:
- dziennik audytowy tylko do dopisywania (blokada w bazie + łańcuch skrótów SHA-256);
- żaden agent nie wysyła pieniędzy ani nie składa zgłoszeń; robi to dyrektor po zatwierdzeniu;
- poziom 3 (płatność powyżej limitu, zgłoszenia, wznowienie agenta) wymaga dwóch dyrektorów,
  w tym niezależnego, gdy taki jest wpisany w konfiguracji;
- wstrzymać agenta może każdy dyrektor od razu, wznowić tylko dwóch.

## Wymagania na VPS

Docker z wtyczką Compose (`docker compose version`). Około 200 MB miejsca i 512 MB RAM.

## Instalacja jednym poleceniem

Na VPS, w katalogu z kodem: `./install.sh`. Skrypt pyta o hasło do panelu i (opcjonalnie) klucz Anthropic,
sam wybiera wolny port, buduje obraz, uruchamia kontener i agentów. Można go uruchamiać ponownie.

## Instalacja krok po kroku

```bash
# na swoim komputerze
scp cic-kontener.tar.gz uzytkownik@twoj-vps:~

# na VPS
mkdir -p ~/protosystem && tar xzf ~/cic-kontener.tar.gz -C ~/protosystem
cd ~/protosystem/cic
cp .env.example .env
chmod 600 .env
docker compose build

# sekret formularzy, wklej do .env jako CIC_SECRET=
python3 -c "import secrets;print(secrets.token_hex(32))"

# skrót hasła do panelu, wklej do .env jako CIC_USERS=grzegorz:<skrót>
docker compose run --rm --no-deps cic python -m app.cli hash-password

# klucz Anthropic do .env (ANTHROPIC_API_KEY=), opcjonalnie SMTP i Companies House
nano .env
nano config/cic.yaml        # e-mail dyrektora, później nazwa, numer spółki, daty

docker compose up -d
docker exec cic python -m app.cli run-all     # pierwsze uruchomienie agentów od razu
docker exec cic python -m app.cli verify      # kontrola dziennika
```

Jeśli w `~/protosystem` masz już inne usługi z tym samym `name: protosystem`, kontener `cic`
dołączy do tego samego projektu i sieci. Nie używaj wtedy `--remove-orphans`.

## Dostęp do panelu

Panel nasłuchuje tylko na `127.0.0.1:8080` serwera. Najprościej przez tunel SSH:

```bash
ssh -L 8080:127.0.0.1:8080 uzytkownik@twoj-vps
# potem w przeglądarce: http://localhost:8080
```

Na stałe: reverse proxy z HTTPS, np. Caddy:

```
panel.twoja-domena.org {
    reverse_proxy 127.0.0.1:8080
}
```

## Codzienna obsługa

| Co | Polecenie |
|---|---|
| Logi | `docker logs -f cic` |
| Uruchom agenta teraz | `docker exec cic python -m app.cli run A0` (A0, A1, A8) |
| Kontrola dziennika | `docker exec cic python -m app.cli verify` |
| Kopie zapasowe na komputer | `docker cp cic:/data/backups ./cic-backups` |
| Aktualizacja | rozpakuj nową paczkę, `docker compose up -d --build` |
| Awaryjne wznowienie (gdy jest jeden dyrektor) | `docker exec cic python -m app.cli resume A1` (zapisuje się w dzienniku) |

Kopie z `/data/backups` (30 dni) warto co tydzień kopiować poza serwer.

## Po rejestracji CIC

W `config/cic.yaml` wpisz `company.number`, `company.incorporation_date`, a po rejestracji w ICO
`ico.registration_date`. Dodaj drugiego dyrektora w `directors` (z `independent: true`, jeśli jest
niezależny) i jego login w `CIC_USERS`. Potem `docker compose restart cic`.

## Model i koszty

Raport poranny pisze `claude-opus-5-5` z niskim wysiłkiem (`llm.effort: low`), z automatycznym
modelem zapasowym przy odmowie. To jedno krótkie wywołanie dziennie. Bez klucza API raport
powstaje z szablonu, reszta działa bez zmian.

## Testy

```bash
pip install -r requirements.txt pytest && python -m pytest -q
```
