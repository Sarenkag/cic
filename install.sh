#!/usr/bin/env bash
# Instalacja kontenera "cic" w projekcie "protosystem". Bezpieczne do ponownego uruchomienia.
# Nie dotyka innych kontenerów. Użycie: ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n== %s\n' "$*"; }
set_env() {  # set_env KLUCZ WARTOŚĆ
  local tmp; tmp=$(mktemp)
  grep -v "^$1=" .env > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > .env && rm -f "$tmp"
}
get_env() { grep "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

command -v docker >/dev/null || { echo "Brak Dockera. Zainstaluj go i uruchom skrypt ponownie."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Brak 'docker compose'. Zainstaluj wtyczkę Compose."; exit 1; }

[ -f .env ] || { cp .env.example .env; }
chmod 600 .env

say "Port panelu"
port=$(get_env CIC_PORT); port=${port:-8080}
in_use() { (echo > "/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
mine=$(docker ps -q --filter name='^cic$' 2>/dev/null || true)
if [ -z "$mine" ] && in_use "$port"; then
  for p in 8090 8091 8092 8093 8094 8095; do in_use "$p" || { port=$p; break; }; done
fi
set_env CIC_PORT "$port"
echo "Panel będzie na 127.0.0.1:$port"

say "Budowanie obrazu"
[ "${CIC_SKIP_BUILD:-}" = 1 ] || docker compose build

if [ -z "$(get_env CIC_SECRET)" ]; then
  set_env CIC_SECRET "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi

if [ -z "$(get_env CIC_USERS)" ]; then
  say "Hasło do panelu (login: grzegorz)"
  pw=${CIC_PANEL_PASSWORD:-}
  if [ -z "$pw" ] && [ ! -t 0 ]; then
    echo "UWAGA: brak hasła (CIC_PANEL_PASSWORD). Agenci działają, ale do panelu nie da się zalogować."
    pw=SKIP
  fi
  while [ -z "$pw" ]; do
    read -rsp "Nowe hasło (min. 12 znaków): " a; echo
    read -rsp "Powtórz hasło: " b; echo
    if [ "$a" != "$b" ]; then echo "Hasła się różnią."; elif [ ${#a} -lt 12 ]; then echo "Za krótkie."; else pw=$a; fi
  done
  [ "$pw" = SKIP ] || hash=$(P="$pw" docker compose run --rm --no-deps -T -e P cic \
    python -c "import os;from app.auth import hash_password;print(hash_password(os.environ['P']))")
  [ "$pw" = SKIP ] || set_env CIC_USERS "grzegorz:$hash"
  unset pw a b
fi

if [ -z "$(get_env ANTHROPIC_API_KEY)" ] && [ -n "${ANTHROPIC_API_KEY_INIT:-}" ]; then
  set_env ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY_INIT"
elif [ -z "$(get_env ANTHROPIC_API_KEY)" ] && [ -t 0 ]; then
  say "Klucz Anthropic (opcjonalny, Enter = pomiń; bez niego raport powstaje z szablonu)"
  read -rsp "ANTHROPIC_API_KEY: " key; echo
  [ -n "$key" ] && set_env ANTHROPIC_API_KEY "$key"
  unset key
fi

say "Uruchamianie kontenera cic"
docker compose up -d cic
for _ in $(seq 1 30); do
  state=$(docker inspect -f '{{.State.Health.Status}}' cic 2>/dev/null || echo starting)
  [ "$state" = healthy ] && break
  sleep 2
done
echo "Stan: $state"

say "Pierwsze uruchomienie agentów"
docker exec cic python -m app.cli run-all
docker exec cic python -m app.cli verify

say "Gotowe"
cat <<MSG
Panel: http://127.0.0.1:$port na serwerze (login: grzegorz).
Z telefonu lub komputera otwórz go przez tunel SSH, np. w aplikacji SSH ustaw
przekierowanie portu lokalnego $port na 127.0.0.1:$port, albo:
  ssh -L $port:127.0.0.1:$port uzytkownik@ten-serwer
i wejdź na http://localhost:$port
Konfiguracja CIC: $(pwd)/config/cic.yaml (po zmianie: docker compose restart cic)
MSG
