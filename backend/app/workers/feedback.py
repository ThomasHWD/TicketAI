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
def feedback_job(self, responde_id: str, formulation_id: str | None = None):
    """Indexe une réponse validée sous le vecteur d'une question.

    `formulation_id` (optionnel) est l'id d'une **copie SUGGESTION validée** de
    cette réponse. Il désigne alors une *formulation supplémentaire* : la
    question de cette copie, qu'un humain vient de valider comme appelant cette
    réponse-là. On l'indexe sous son propre point, en plus de la question
    d'origine.

    Sans ça, une réponse promue canonique à trois validations n'était atteignable
    que depuis une seule formulation : les deux autres — pourtant validées
    explicitement par un humain — étaient perdues. C'est un signal plus fort que
    celui sur lequel tranche le garde (jugement LLM), pas plus faible.
    """
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

        if formulation_id:
            # Formulation supplémentaire : la question de la copie validée.
            copie = get_response(db, formulation_id)
            ticket_copie = db.query(Ticket).filter(Ticket.id == copie.ticket_id).first()
            texte_a_indexer = copie.question_suivi or (ticket_copie.question if ticket_copie else None)
            if not texte_a_indexer:
                return  # rien d'exploitable : on n'indexe pas le texte de la réponse sous un alias
            # Point distinct, dérivé de la copie : idempotent, et laisse intact
            # le point de la question d'origine.
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{r.id}:{copie.id}"))
        elif r.question_suivi:
            texte_a_indexer = r.question_suivi
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))
        elif ticket and ticket.question:
            texte_a_indexer = ticket.question
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))
        else:
            texte_a_indexer = r_content
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))

        embeddings = embed_texts([texte_a_indexer])

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
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
                        # Question sous laquelle CE point est indexé. Le garde doit
                        # juger la paire réellement retrouvée : avec plusieurs
                        # formulations par réponse, la redériver de `Ticket.question`
                        # donnerait la mauvaise question B.
                        "question_indexee": texte_a_indexer,
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
