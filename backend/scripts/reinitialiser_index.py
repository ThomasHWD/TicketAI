"""Recrée la collection Qdrant et réindexe tout, depuis Postgres et le disque.

À lancer après tout changement qui invalide les vecteurs déjà écrits — l'arrivée
de BM25 en est un : `Modifier.IDF` se fixe **à la création** de la collection, et
les points existants portent un vecteur creux vide.

Usage :
    PYTHONPATH=. python scripts/reinitialiser_index.py [--documents-seulement]

Ce que le script rejoue :
  1. les documents, depuis les fichiers conservés sous DOCUMENTS_STORAGE_PATH ;
  2. les réponses validées, **une entrée par formulation humainement validée**
     (cf. `workers/feedback.py` : une réponse promue canonique à trois validations
     est atteignable depuis trois questions distinctes, pas une seule).

Le script est synchrone : il appelle les jobs directement plutôt que via Celery,
pour que l'échec d'une pièce soit visible immédiatement plutôt que dilué dans une
file. Prévoir plusieurs minutes — chaque lot de textes est un appel Albert.

**Limite à connaître** : tout se rejoue depuis Postgres. Si la base est vidée elle
aussi, le `domaine` et la `description` de chaque document sont perdus — ils ne
figurent nulle part sur le disque, où seul `{doc_id}/v{n}/{fichier}` subsiste. Les
documents doivent alors être redéposés par l'interface. Vider Qdrant seul est donc
préférable quand on veut pouvoir comparer un avant et un après.
"""

import argparse
import os
import shutil
import sys
import tempfile

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.reponse import Reponse  # noqa: E402
from app.services.qdrant import COLLECTION_NAME, client, init_collection  # noqa: E402


def recreer_collection() -> None:
    """Supprime puis recrée : `Modifier.IDF` ne peut pas être ajouté après coup."""
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
        print(f"collection « {COLLECTION_NAME} » supprimée")
    init_collection()
    sparse = client.get_collection(COLLECTION_NAME).config.params.sparse_vectors
    print(f"collection recréée — modifier = {sparse['sparse'].modifier}")


def reindexer_documents(db) -> tuple[int, int]:
    """Rejoue l'ingestion de la version courante de chaque document actif.

    **Le fichier est copié dans un temporaire avant d'être passé au job.**
    `ingestion_job` copie sa source vers le stockage permanent puis *supprime*
    cette source : lui donner `stored_path` directement lèverait `SameFileError`,
    et dans le cas contraire effacerait le fichier permanent. Le corpus y
    passerait.
    """
    from app.workers.ingestion import ingestion_job

    documents = db.query(Document).filter(Document.statut != "SUPPRIMÉ").all()
    ok = 0
    for doc in documents:
        chemin = doc.stored_path
        if not chemin or not os.path.exists(chemin):
            print(f"  ! fichier introuvable, ignoré : {doc.filename} ({doc.doc_id})")
            continue

        with tempfile.TemporaryDirectory() as temporaire:
            copie = os.path.join(temporaire, doc.filename)
            shutil.copy2(chemin, copie)
            try:
                ingestion_job.run(
                    file_path=copie,
                    filename=doc.filename,
                    domaine=doc.domaine,
                    doc_id=doc.doc_id,
                    description=doc.description or "",
                )
                ok += 1
                print(f"  · [{doc.domaine}] {doc.filename}")
            except Exception as exc:  # noqa: BLE001 — on veut continuer sur les autres
                print(f"  ! échec sur {doc.filename} : {exc}")
    return ok, len(documents)


def reindexer_reponses(db) -> int:
    """Rejoue `feedback_job` pour chaque réponse servie et chacune de ses formulations.

    Les deux appels ne sont pas redondants : `feedback_job(source)` indexe la
    question d'origine, `feedback_job(source, copie)` indexe la reformulation
    qu'un humain a validée comme appelant la même réponse. Ne rejouer que le
    premier rendrait la réponse atteignable depuis une seule question.
    """
    from app.workers.feedback import feedback_job

    sources = (
        db.query(Reponse)
        .filter(
            Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
            Reponse.obsolete.is_(False),
            Reponse.reponse_source_id.is_(None),
        )
        .all()
    )

    points = 0
    for source in sources:
        try:
            feedback_job.run(str(source.id))
            points += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  ! échec sur la réponse {source.id} : {exc}")
            continue

        copies = (
            db.query(Reponse)
            .filter(
                Reponse.reponse_source_id == source.id,
                Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                Reponse.obsolete.is_(False),
            )
            .all()
        )
        for copie in copies:
            try:
                feedback_job.run(str(source.id), str(copie.id))
                points += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  ! échec sur la formulation {copie.id} : {exc}")
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    portee = parser.add_mutually_exclusive_group()
    portee.add_argument("--documents-seulement", action="store_true")
    portee.add_argument(
        "--reponses-seulement",
        action="store_true",
        help=(
            "Saute les documents. Utile lorsque le découpage est indisponible : il "
            "charge le tokenizer BGE-M3 depuis HuggingFace, ce qui exige un réseau "
            "ou un cache. `feedback_job`, lui, embarque la question telle quelle."
        ),
    )
    parser.add_argument(
        "--garder-collection",
        action="store_true",
        help="N'efface pas la collection — pour compléter une réindexation partielle.",
    )
    args = parser.parse_args()

    print(f"stockage : {settings.documents_storage_path}\n")
    if args.garder_collection:
        print("collection conservée")
    else:
        recreer_collection()

    db = SessionLocal()
    try:
        if not args.reponses_seulement:
            print("\nDocuments…")
            ok, total = reindexer_documents(db)
            print(f"  → {ok}/{total} réindexés")

        if not args.documents_seulement:
            print("\nRéponses validées…")
            points = reindexer_reponses(db)
            print(f"  → {points} points écrits")
    finally:
        db.close()

    total_points = client.get_collection(COLLECTION_NAME).points_count
    print(f"\ncollection : {total_points} points")
    if total_points == 0:
        print("! la collection est vide — rien n'a pu être rejoué", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
