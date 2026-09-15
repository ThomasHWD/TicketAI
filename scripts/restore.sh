#!/usr/bin/env bash
# Restaure un backup Postgres + Qdrant + documents
# Usage : ./scripts/restore.sh backups/YYYY-MM-DD
#
# ⚠️  Écrase les données existantes. La stack prod doit être démarrée.

set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker-compose.prod.yml"
BACKUP_DIR="${1:-}"

if [[ -z "$BACKUP_DIR" || ! -d "$BACKUP_DIR" ]]; then
  echo "Usage : $0 <répertoire-backup>" >&2
  echo "Exemple : $0 backups/2026-09-15" >&2
  exit 1
fi

# Charge .env
ENV_FILE="$(dirname "$0")/../backend/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ticketai_db}"

POSTGRES_DUMP=$(ls "$BACKUP_DIR"/postgres_*.sql.gz 2>/dev/null | head -1)
QDRANT_SNAP=$(ls "$BACKUP_DIR"/qdrant_*.snapshot 2>/dev/null | head -1)
DOCS_ARCHIVE=$(ls "$BACKUP_DIR"/documents_*.tar.gz 2>/dev/null | head -1)

echo "=== Restauration TicketAI — $BACKUP_DIR ==="
echo ""
echo "Fichiers trouvés :"
echo "  Postgres : ${POSTGRES_DUMP:-ABSENT}"
echo "  Qdrant   : ${QDRANT_SNAP:-ABSENT}"
echo "  Documents: ${DOCS_ARCHIVE:-ABSENT}"
echo ""
read -rp "Confirmer la restauration ? Les données actuelles seront écrasées. [oui/NON] " CONFIRM
[[ "$CONFIRM" == "oui" ]] || { echo "Annulé."; exit 0; }

# --- Postgres ----------------------------------------------------------------
if [[ -n "$POSTGRES_DUMP" ]]; then
  echo ""
  echo "[1/3] Restauration Postgres..."
  gunzip -c "$POSTGRES_DUMP" | docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  echo "      Postgres restauré."
else
  echo "[1/3] Pas de dump Postgres trouvé — ignoré."
fi

# --- Qdrant ------------------------------------------------------------------
if [[ -n "$QDRANT_SNAP" ]]; then
  echo ""
  echo "[2/3] Restauration Qdrant..."
  SNAP_BASENAME=$(basename "$QDRANT_SNAP")
  # Copie le snapshot dans le conteneur
  docker compose -f "$COMPOSE_FILE" cp "$QDRANT_SNAP" "qdrant:/qdrant/storage/snapshots/$SNAP_BASENAME"
  # Restaure via l'API REST
  docker compose -f "$COMPOSE_FILE" exec -T qdrant \
    wget -qO- --method=PUT "http://localhost:6333/snapshots/recover" \
    --header="Content-Type: application/json" \
    --body-data="{\"location\": \"/qdrant/storage/snapshots/$SNAP_BASENAME\"}"
  echo ""
  echo "      Qdrant restauré."
else
  echo "[2/3] Pas de snapshot Qdrant trouvé — ignoré."
fi

# --- Documents ---------------------------------------------------------------
if [[ -n "$DOCS_ARCHIVE" ]]; then
  echo ""
  echo "[3/3] Restauration des documents uploadés..."
  docker compose -f "$COMPOSE_FILE" exec -T backend \
    tar -xzf - -C / < "$DOCS_ARCHIVE"
  echo "      Documents restaurés."
else
  echo "[3/3] Pas d'archive documents trouvée — ignoré."
fi

echo ""
echo "=== Restauration terminée ==="
