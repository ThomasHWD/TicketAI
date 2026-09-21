import logging
import uuid

from celery.exceptions import Retry
from qdrant_client.models import PointStruct, SparseVector

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.garde_cache import statuer
from app.services.qdrant import COLLECTION_NAME, client
from app.services.question_pipeline import journaliser_garde
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_response(db, reponse_id: str):
    response = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not response:
        raise ValueError(f"Réponse {reponse_id} introuvable")
    return response


def _alias_juge(tache, source, copie, nouvelle_question: str, ticket_source, domaine: str) -> bool:
    """Un humain a-t-il validé « la même demande », ou seulement « ça me va » ?

    Écrire un alias, c'est déclarer que `nouvelle_question` appelle la réponse de
    `source` — et cette déclaration est **plus forte que tout ce que le garde
    tranche ensuite** : le point porte la question spécifique et le `reponse_id`
    de la réponse générale, si bien qu'à la question suivante le cosinus vaut ~1,0,
    le court-circuit typographique s'enclenche, et la réponse part en CANONIQUE
    **sans qu'aucun juge ne soit appelé**. Un alias faux court-circuite donc le
    garde, il ne lui est pas soumis.

    Or rien ne le vérifiait. Il suffisait qu'un relecteur clique « Valider »
    plutôt que « Corriger » sur une SUGGESTION *plausible mais pas la bonne
    réponse* — la réponse générale n'est pas fausse, elle est seulement à côté de
    la question posée — et le bouton vert est le chemin le moins cher de l'écran.

    On soumet donc la paire au même juge, avant d'écrire quoi que ce soit. Trois
    issues distinctes, et `Decision.erreur` existe exactement pour les séparer :

    - **OUI** → l'alias est écrit ;
    - **NON jugé** → pas d'alias. La réponse reste atteignable depuis ses
      formulations existantes : on retombe sur le comportement d'avant
      l'indexation multi-formulations, pas sur une perte ;
    - **Albert injoignable** → `retry`. Un refus par défaut perdrait en silence
      une formulation légitime qu'un humain a validée, et la table d'audit ne
      dirait pas la différence.

    Coût : un appel juge par **validation humaine** de SUGGESTION — un événement
    rare, pas une question — et zéro quand les deux formulations sont
    typographiquement identiques (court-circuit).

    Portée délibérément limitée à l'alias : `nb_validations` sur la source
    continue d'être incrémenté par l'endpoint HTTP. Le bloquer demanderait un
    appel LLM synchrone sur une requête web, pour un signal qui *promeut* sans
    *servir*. C'est l'alias qui crée le cosinus à 1,0.
    """
    question_source = source.question_suivi or (ticket_source.question if ticket_source else None)
    if not question_source:
        # Pas de question B : il ne reste que le texte de la réponse, et juger une
        # question contre une réponse n'a pas de sens. Sans paire jugeable, on
        # n'accorde pas l'alias — même prudence que le garde lui-même.
        logger.warning("Alias refusé : la réponse %s n'a aucune question indexable", source.id)
        return False

    decision = statuer(nouvelle_question, question_source)
    journaliser_garde(
        decision,
        job_id=None,
        ticket_id=copie.ticket_id,
        domaine=domaine,
        est_suivi=False,
        question_posee=nouvelle_question,
        question_indexee=question_source,
        reponse_id=source.id,
        # Aucun score : cette paire ne vient pas d'une recherche mais d'un geste
        # humain. `NULL` le dit ; un `0.0` se lirait comme un candidat très loin.
        score_cosinus=None,
        score_lexical=None,
    )

    if decision.erreur:
        raise tache.retry(exc=RuntimeError(f"garde injoignable pour l'alias : {decision.erreur}"))
    if not decision.verdict:
        logger.info("Alias refusé par le garde : %r ≠ %r", nouvelle_question, question_source)
    return decision.verdict


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
            if not _alias_juge(self, r, copie, texte_a_indexer, ticket, domaine):
                return
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
