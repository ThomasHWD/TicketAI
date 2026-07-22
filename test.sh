#!/usr/bin/env bash
#
# Lanceur de tests TicketAI.
#
#   ./test.sh [commande] [args pytest/vitest supplémentaires...]
#
# Commandes :
#   unit         Backend — tests unitaires seulement (aucune infra, rapide).  [défaut si rien]
#   back         Backend — suite complète (unitaires + intégration). Démarre l'infra si besoin.
#   cov          Backend — suite complète + rapport de couverture HTML (htmlcov/index.html).
#   front        Frontend — tests vitest (une passe).
#   watch        Frontend — vitest en mode watch.
#   all          Backend complet + frontend.
#
# Tout argument après la commande est transmis tel quel au runner sous-jacent :
#   ./test.sh unit -k chunking          # filtre pytest
#   ./test.sh back tests/test_search.py # un fichier précis
#   ./test.sh front src/lib             # un dossier vitest
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

TEST_DB="ticketai_test"
PG_CONTAINER="ticketAI-postgres"

# Affiche le bloc de commentaires d'en-tête (après le shebang), sans les '#'.
print_help() {
  awk 'NR>1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print } else exit }' "${BASH_SOURCE[0]}"
}

c_info()  { printf '\033[1;34m→ %s\033[0m\n' "$*"; }
c_ok()    { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
c_err()   { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

# --- Infra ---------------------------------------------------------------- #
infra_up() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${PG_CONTAINER}$"
}

ensure_infra() {
  if ! infra_up; then
    c_info "Infra non démarrée — lancement de 'make up'…"
    make -C "$ROOT" up
    c_info "Attente de Postgres…"
    sleep 3
  fi
}

ensure_test_db() {
  local pguser
  pguser="$(grep -E '^POSTGRES_USER=' "$BACKEND/.env" | cut -d= -f2)"
  if ! docker exec "$PG_CONTAINER" psql -U "$pguser" -d postgres -tc \
        "SELECT 1 FROM pg_database WHERE datname='${TEST_DB}'" | grep -q 1; then
    c_info "Création de la base de test '${TEST_DB}'…"
    docker exec "$PG_CONTAINER" psql -U "$pguser" -d postgres -c \
        "CREATE DATABASE ${TEST_DB}" >/dev/null
  fi
}

# --- Runners -------------------------------------------------------------- #
backend_unit() {
  cd "$BACKEND"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  c_info "Backend — tests unitaires (sans infra)"
  PYTHONPATH=. pytest -m "not integration" "$@"
}

backend_full() {
  local extra_cov=("$@")
  ensure_infra
  ensure_test_db
  cd "$BACKEND"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  c_info "Backend — suite complète (base '${TEST_DB}')"
  POSTGRES_DB="$TEST_DB" PYTHONPATH=. pytest "${extra_cov[@]}"
}

frontend_run() {
  cd "$FRONTEND"
  c_info "Frontend — vitest"
  npx vitest run "$@"
}

frontend_watch() {
  cd "$FRONTEND"
  c_info "Frontend — vitest (watch)"
  npx vitest "$@"
}

# --- Dispatch ------------------------------------------------------------- #
cmd="${1:-unit}"
[ $# -gt 0 ] && shift || true

case "$cmd" in
  unit)        backend_unit "$@" ;;
  back)        backend_full "$@" ;;
  cov)         backend_full --cov-report=html "$@"
               c_ok "Rapport de couverture : $BACKEND/htmlcov/index.html" ;;
  front)       frontend_run "$@" ;;
  watch)       frontend_watch "$@" ;;
  all)         backend_full "$@"; ( frontend_run ) ;;
  -h|--help|help)
               print_help ;;
  *)
               c_err "Commande inconnue : '$cmd'"
               print_help
               exit 1 ;;
esac
