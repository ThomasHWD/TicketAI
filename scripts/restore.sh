#!/usr/bin/env bash
# Restaure un backup Postgres + Qdrant + documents produit par backup.sh
# Usage : ./scripts/restore.sh backups/YYYY-MM-DD
#
# ⚠️  Remplace intégralement les données existantes. Cible la prod par défaut ;
#     COMPOSE_FILE=docker-compose.dev.yml pour la dev. CONFIRMER=oui pour ne pas être interrogé.
#
# L'application (backend + workers) est arrêtée pendant la restauration et relancée à la fin.
# En cas d'échec, elle reste arrêtée : les données sont dans un état partiel, relancer la restauration.

set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$RACINE/docker-compose.prod.yml}"
BACKUP_DIR="${1:-}"
APPLI=(backend worker_ingestion worker_questions worker_beat)

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }
# conteneur jetable : curl et le volume des documents, sans que l'application tourne
outil() { dc run --rm --no-deps -T backend sh -c "$1"; }

if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Usage : $0 <répertoire-backup>" >&2
  echo "Exemple : $0 backups/2026-09-15" >&2
  exit 1
fi

# Tout ou rien : une restauration partielle laisse une base qui pointe vers des vecteurs ou des fichiers absents.
POSTGRES_DUMP="$BACKUP_DIR/postgres.dump"
DOCS_ARCHIVE="$BACKUP_DIR/documents.tar.gz"
shopt -s nullglob
QDRANT_SNAPS=("$BACKUP_DIR"/qdrant_*.snapshot)
shopt -u nullglob
for f in "$POSTGRES_DUMP" "$DOCS_ARCHIVE" "${QDRANT_SNAPS[@]}"; do
  [[ -s "$f" ]] || { echo "ERREUR : $f absent ou vide" >&2; exit 1; }
done
[[ ${#QDRANT_SNAPS[@]} -gt 0 ]] || { echo "ERREUR : aucun snapshot Qdrant dans $BACKUP_DIR" >&2; exit 1; }

echo "=== Restauration TicketAI — $BACKUP_DIR ==="
echo "Compose  : $COMPOSE_FILE"
echo "Postgres : $POSTGRES_DUMP"
for f in "${QDRANT_SNAPS[@]}"; do echo "Qdrant   : $f"; done
echo "Documents: $DOCS_ARCHIVE"
echo ""
if [[ "${CONFIRMER:-}" != "oui" ]]; then
  read -rp "Confirmer la restauration ? Les données actuelles seront écrasées. [oui/NON] " CONFIRM
  [[ "$CONFIRM" == "oui" ]] || { echo "Annulé."; exit 0; }
fi

trap 'echo "" >&2; echo "ÉCHEC : application laissée arrêtée, données partielles. Relancer la restauration." >&2' ERR

echo ""
echo "[0/4] Arrêt de l'application..."
dc stop "${APPLI[@]}"

# --- Postgres ----------------------------------------------------------------
# Schéma vidé puis rechargé : --clean seul laisserait les tables créées après le backup (migrations plus récentes),
# et le alembic upgrade du démarrage buterait dessus.
echo ""
echo "[1/4] Restauration Postgres..."
dc exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "DROP SCHEMA public CASCADE" -c "CREATE SCHEMA public"'
dc exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error --single-transaction' \
  < "$POSTGRES_DUMP"
echo "      Postgres restauré."

# --- Qdrant ------------------------------------------------------------------
echo ""
echo "[2/4] Restauration Qdrant..."
for f in "${QDRANT_SNAPS[@]}"; do
  c=$(basename "$f" .snapshot)
  c=${c#qdrant_}
  outil "curl -fsS -X POST \"http://\$QDRANT_HOST:\$QDRANT_PORT/collections/$c/snapshots/upload?priority=snapshot&wait=true\" \
    -F 'snapshot=@-;filename=$c.snapshot'" < "$f" > /dev/null
  # Qdrant garde le fichier envoyé après l'avoir chargé
  outil "curl -fsS -X DELETE \"http://\$QDRANT_HOST:\$QDRANT_PORT/collections/$c/snapshots/$c.snapshot\"" > /dev/null
  echo "      collection $c restaurée."
done

# --- Documents ---------------------------------------------------------------
echo ""
echo "[3/4] Restauration des documents uploadés..."
outil 'find "$DOCUMENTS_STORAGE_PATH" -mindepth 1 -delete && tar -C "$DOCUMENTS_STORAGE_PATH" -xzf -' < "$DOCS_ARCHIVE"
echo "      Documents restaurés."

trap - ERR

echo ""
echo "[4/4] Redémarrage de l'application..."
dc start "${APPLI[@]}"

echo ""
echo "=== Restauration terminée ==="
