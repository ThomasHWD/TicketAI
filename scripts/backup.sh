#!/usr/bin/env bash
# Sauvegarde Postgres + Qdrant + documents uploadés
# Usage : ./scripts/backup.sh [répertoire-destination]
#
# Sans argument, crée les backups dans ./backups/YYYY-MM-DD/
# Requiert que la stack soit démarrée. Cible la prod par défaut ; COMPOSE_FILE=docker-compose.dev.yml pour la dev.
#
# Code de sortie non nul au moindre échec : sous cron, rediriger la sortie vers un log et surveiller le code.
# Un backup n'apparaît sous son nom daté qu'une fois complet et vérifié (écrit d'abord dans <date>.partiel).

set -euo pipefail
# Dumps en clair : noms, e-mails et questions des agents (RGPD). Fichiers et répertoires lisibles du seul
# propriétaire — tout est écrit par redirection du shell, l'umask s'applique partout.
umask 077

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$RACINE/docker-compose.prod.yml}"
BACKUP_ROOT="${1:-$RACINE/backups}"
GARDER="${GARDER:-7}"
DATE="$(date +%F)"
DEST="$BACKUP_ROOT/$DATE"
PARTIEL="$DEST.partiel"

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

echec() {
  echo "  ERREUR : $*" >&2
  exit 1
}

non_vide() {
  [[ -s "$1" ]] || echec "$1 est vide"
}

rm -rf "$PARTIEL"
mkdir -p "$PARTIEL"
trap 'echo "Backup incomplet laissé dans $PARTIEL" >&2' ERR

echo "=== Backup TicketAI — $DATE ==="
echo "Compose     : $COMPOSE_FILE"
echo "Destination : $DEST"

# --- Postgres ----------------------------------------------------------------
# Identifiants lus dans le conteneur : backend/.env ne décrit pas forcément la stack visée.
# Format custom : restauré par pg_restore --clean, qui remplace les objets au lieu de s'ajouter à l'existant.
echo ""
echo "[1/3] Dump Postgres..."
dc exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$PARTIEL/postgres.dump"
non_vide "$PARTIEL/postgres.dump"
dc exec -T postgres pg_restore --list < "$PARTIEL/postgres.dump" > /dev/null \
  || echec "dump Postgres illisible par pg_restore"
echo "      → postgres.dump ($(du -h "$PARTIEL/postgres.dump" | cut -f1))"

# --- Qdrant ------------------------------------------------------------------
# L'image Qdrant n'a ni curl ni wget : l'API est appelée depuis le conteneur backend.
# Un snapshot par collection : c'est ce que /collections/{nom}/snapshots/upload sait restaurer.
echo ""
echo "[2/3] Snapshots Qdrant..."
qdrant() { dc exec -T backend sh -c "curl -fsS \"http://\$QDRANT_HOST:\$QDRANT_PORT$1\" $2"; }

COLLECTIONS=$(qdrant /collections "" | python3 -c 'import json,sys; print(" ".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))')
[[ -n "$COLLECTIONS" ]] || echec "aucune collection Qdrant"

for c in $COLLECTIONS; do
  NOM=$(qdrant "/collections/$c/snapshots" "-X POST" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')
  qdrant "/collections/$c/snapshots/$NOM" "" > "$PARTIEL/qdrant_$c.snapshot"
  # le snapshot reste sinon dans le conteneur Qdrant, un par jour
  qdrant "/collections/$c/snapshots/$NOM" "-X DELETE" > /dev/null
  non_vide "$PARTIEL/qdrant_$c.snapshot"
  tar -tf "$PARTIEL/qdrant_$c.snapshot" > /dev/null || echec "snapshot Qdrant $c illisible"
  echo "      → qdrant_$c.snapshot ($(du -h "$PARTIEL/qdrant_$c.snapshot" | cut -f1))"
done

# --- Documents uploadés ------------------------------------------------------
echo ""
echo "[3/3] Archivage des documents uploadés..."
dc exec -T backend sh -c 'tar -C "$DOCUMENTS_STORAGE_PATH" -czf - .' > "$PARTIEL/documents.tar.gz"
non_vide "$PARTIEL/documents.tar.gz"
NB_DOCS=$(tar -tzf "$PARTIEL/documents.tar.gz" | grep -cv '/$' || true)
echo "      → documents.tar.gz ($(du -h "$PARTIEL/documents.tar.gz" | cut -f1), $NB_DOCS fichiers)"

# --- Publication -------------------------------------------------------------
rm -rf "$DEST"
mv "$PARTIEL" "$DEST"
trap - ERR

# --- Nettoyage : garde les $GARDER derniers backups complets ------------------
echo ""
echo "[nettoyage] Conservation des $GARDER derniers backups..."
find "$BACKUP_ROOT" -maxdepth 1 -type d -name "????-??-??" | sort | head -n -"$GARDER" | while read -r dir; do
  echo "  Supprime $dir"
  rm -rf "$dir"
done

echo ""
echo "=== Backup terminé ==="
du -sh "$DEST"
