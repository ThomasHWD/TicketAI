"""Backfill de la table `documents` depuis Qdrant.

À exécuter une fois après `alembic upgrade head` : les documents ingérés avant
l'introduction des tables `documents` / `document_versions` n'existent que sous forme
de points Qdrant, et resteraient invisibles de tout ce qui lira désormais Postgres.

Idempotent — rejouable sans risque. Le même travail est exposé en
`POST /api/v1/admin/documents/reconcile`.

Usage :
    python -m scripts.backfill_documents
"""

from app.database import SessionLocal
from app.services.document_backfill import reconcilier_documents


def main() -> None:
    db = SessionLocal()
    try:
        stats = reconcilier_documents(db)
    finally:
        db.close()

    print(f"Documents trouvés dans Qdrant : {stats['documents_qdrant']}")
    print(f"  → créés            : {stats['documents_crees']}")
    print(f"  → déjà présents    : {stats['documents_existants']}")
    print(f"  → versions créées  : {stats['versions_creees']}")


if __name__ == "__main__":
    main()
