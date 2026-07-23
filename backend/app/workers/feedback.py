import uuid

from celery.exceptions import Retry
from qdrant_client.models import PointStruct, SparseVector

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app


def get_response(db, reponse_id: str):
    response = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not response:
        raise ValueError(f"Réponse {reponse_id} introuvable")
    return response


@celery_app.task(
    name="feedback_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def feedback_job(self, responde_id: str):
    db = SessionLocal()

    try:
        # Load response from the database
        r = get_response(db, responde_id)

        # Upsert embeddings into Qdrant
        ticket = db.query(Ticket).filter(Ticket.id == r.ticket_id).first()
        domaine = ticket.domaine if ticket else "NONE"

        # On indexe le vecteur de la QUESTION, PAS le texte de la réponse.
        # Le lookup (CANONIQUE/SUGGESTION) compare une nouvelle question à ce point :
        # question↔question donne un cosinus élevé pour des questions proches, alors que
        # question↔réponse plafonnait vers ~0.50 et n'atteignait jamais le seuil (0.60).
        #
        # Un tour de suivi porte sa PROPRE question (la précision, dans `question_suivi`) :
        # on l'indexe sous cette précision — et non sous la question initiale du ticket —
        # pour qu'une future question proche de la précision la retrouve, et que la
        # précision puisse converger vers une réponse canonique à part entière.
        # Fallback sur le contenu de la réponse si aucune question n'est disponible.
        r_content = r.contenu_corrige if r.contenu_corrige else r.contenu
        if r.question_suivi:
            texte_a_indexer = r.question_suivi
        elif ticket and ticket.question:
            texte_a_indexer = ticket.question
        else:
            texte_a_indexer = r_content
        embeddings = embed_texts([texte_a_indexer])

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id))),
                    vector={
                        "dense": embeddings[0]["dense"],
                        "sparse": SparseVector(
                            indices=embeddings[0]["sparse"]["indices"],
                            values=embeddings[0]["sparse"]["values"],
                        ),
                    },
                    payload={
                        "reponse_id": str(r.id),
                        "ticket_id": str(r.ticket_id),
                        "contenu": r_content,
                        "domaine": domaine,
                    },
                )
            ],
        )
    except Retry:
        raise
    except Exception as e:
        raise self.retry(exc=e) from e

    finally:
        db.close()
