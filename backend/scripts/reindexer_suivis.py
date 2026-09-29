"""Réécrit les points-réponses de suivi indexés sous leur précision nue.

Avant la reformulation (`services/reformulation.py`), une précision validée était
indexée sous son texte brut — « et pour un apprenti ? » — et répondait à tout fil
finissant de la même façon. Le service ne juge plus ces points
(`question_du_point_fiable` → SUGGESTION, jamais CANONIQUE) : ils sont neutralisés,
mais ne servent plus le cache. Ce script les fait réécrire par `feedback_job`,
qui calcule la question autonome, la stocke et réécrit le point sous le même id.

Deux producteurs à distinguer, parce que `feedback_job` ne se rappelle pas pareil :
  - point propre de la réponse (id = uuid5(reponse_id)) → `feedback_job(reponse_id)` ;
  - alias d'une copie SUGGESTION validée → `feedback_job(source_id, copie_id)`,
    qui re-juge l'alias avant de l'écrire.

Coût : un appel Albert (reformulation) par suivi, plus un appel du juge par alias.
Un point dont la reformulation est inexploitable, ou dont l'alias est refusé,
reste en place et neutralisé ; il est compté dans le bilan.

À lancer dans le conteneur (il porte la bonne configuration) :
    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/reindexer_suivis.py              # simulation
    ... python scripts/reindexer_suivis.py --appliquer
"""

import argparse
import uuid

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.services.qdrant import COLLECTION_NAME, client
from app.services.question_pipeline import question_du_point_fiable
from app.services.search import FILTRE_POINTS_REPONSE
from app.workers.feedback import feedback_job

LOT = 200


def points_reponses():
    decalage = None
    while True:
        points, decalage = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=FILTRE_POINTS_REPONSE,
            with_payload=["reponse_id", "question_indexee"],
            with_vectors=False,
            limit=LOT,
            offset=decalage,
        )
        yield from points
        if decalage is None:
            return


def a_reecrire(db) -> list[tuple[str, str | None, str]]:
    """(reponse_id, copie_id ou None, question indexée) des points de suivi sans contexte."""
    cibles = []
    for point in points_reponses():
        charge = point.payload or {}
        rid, question = charge.get("reponse_id"), charge.get("question_indexee")
        if not rid or not question:
            continue
        reponse = db.query(Reponse).filter(Reponse.id == uuid.UUID(str(rid))).first()
        if reponse is None or question_du_point_fiable(db, reponse, question):
            continue
        if str(point.id) == str(uuid.uuid5(uuid.NAMESPACE_DNS, str(rid))):
            cibles.append((str(rid), None, question))
            continue
        copie = (
            db.query(Reponse)
            .filter(Reponse.reponse_source_id == reponse.id, Reponse.question_suivi == question)
            .first()
        )
        if copie is not None:
            cibles.append((str(rid), str(copie.id), question))
    return cibles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--appliquer", action="store_true", help="réécrire (sinon : simulation)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        cibles = a_reecrire(db)
    finally:
        db.close()

    print(f"{len(cibles)} point(s) de suivi indexé(s) sans contexte")
    for rid, copie, question in cibles:
        print(f"  {rid}{f' (alias de {copie})' if copie else ''} : {question!r}")
    if not args.appliquer or not cibles:
        return

    echecs = 0
    for rid, copie, _ in cibles:
        resultat = feedback_job.apply(args=[rid, copie] if copie else [rid], throw=False)
        if resultat.failed():
            echecs += 1
            print(f"  échec {rid} : {resultat.result}")

    db = SessionLocal()
    try:
        restants = len(a_reecrire(db))
    finally:
        db.close()
    print(f"réécrits : {len(cibles) - restants}, restés neutralisés : {restants}, échecs : {echecs}")


if __name__ == "__main__":
    main()
