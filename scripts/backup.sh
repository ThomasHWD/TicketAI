#!/usr/bin/env bash
# Sauvegarde Postgres + Qdrant + documents uploadés
# Usage : ./scripts/backup.sh [répertoire-destination]
#
# Sans argument, crée les backups dans ./backups/YYYY-MM-DD/
# Requiert que la stack prod soit démarrée (docker compose -f docker-compose.prod.yml)

set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker-compose.prod.yml"
BACKUP_ROOT="${1:-$(dirname "$0")/../backups}"
DATE="$(date +%F)"
DEST="$BACKUP_ROOT/$DATE"

# Charge les variables du .env si disponible
ENV_FILE="$(dirname "$0")/../backend/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ticketai_db}"

mkdir -p "$DEST"

echo "=== Backup TicketAI — $DATE ==="
echo "Destination : $DEST"

# --- Postgres ----------------------------------------------------------------
echo ""
echo "[1/3] Dump Postgres ($POSTGRES_DB)..."
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$DEST/postgres_$DATE.sql.gz"
echo "      → $DEST/postgres_$DATE.sql.gz"

# --- Qdrant ------------------------------------------------------------------
echo ""
echo "[2/3] Snapshot Qdrant..."
# L'API REST de Qdrant crée un snapshot et renvoie son nom
SNAPSHOT_NAME=$(docker compose -f "$COMPOSE_FILE" exec -T qdrant \
  wget -qO- --post-data='' "http://localhost:6333/snapshots" \
  | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)

if [[ -z "$SNAPSHOT_NAME" ]]; then
  echo "  ERREUR : impossible de créer le snapshot Qdrant" >&2
  exit 1
fi

# Télécharge le snapshot depuis le conteneur
docker compose -f "$COMPOSE_FILE" exec -T qdrant \
  cat "/qdrant/storage/snapshots/$SNAPSHOT_NAME" \
  > "$DEST/qdrant_$DATE.snapshot"
echo "      → $DEST/qdrant_$DATE.snapshot"

# --- Documents uploadés ------------------------------------------------------
echo ""
echo "[3/3] Archivage des documents uploadés..."
docker compose -f "$COMPOSE_FILE" exec -T backend \
  tar -czf - /app/storage \
  > "$DEST/documents_$DATE.tar.gz"
echo "      → $DEST/documents_$DATE.tar.gz"

# --- Nettoyage : garde les 7 derniers jours ----------------------------------
echo ""
echo "[nettoyage] Suppression des backups de plus de 7 jours..."
find "$BACKUP_ROOT" -maxdepth 1 -type d -name "????-??-??" | sort | head -n -7 | while read -r dir; do
  echo "  Supprime $dir"
  rm -rf "$dir"
done

echo ""
echo "=== Backup terminé ==="
du -sh "$DEST"
