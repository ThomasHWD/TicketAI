import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.llm import generate
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

SEUIL_COSINUS = 0.48


def _upsert_ticket(db: Session, job_id: uuid.UUID, **fields) -> Ticket:
    """Crée ou met à jour le ticket lié à ce job.

    Idempotent : au retry Celery, self.request.id est identique — on met à jour
    le ticket existant au lieu de violer la contrainte UNIQUE sur job_id.
    """
    ticket = db.query(Ticket).filter(Ticket.job_id == job_id).first()
    if ticket is None:
        ticket = Ticket(id=uuid.uuid4(), job_id=job_id, **fields)
        db.add(ticket)
    else:
        for key, value in fields.items():
            setattr(ticket, key, value)
    db.flush()
    return ticket


def _upsert_reponse(db: Session, ticket: Ticket, contenu: str, top_score: float) -> Reponse:
    """Crée ou met à jour la réponse LLM du ticket (idempotent au retry)."""
    reponse = db.query(Reponse).filter(Reponse.ticket_id == ticket.id).first()
    if reponse is None:
        reponse = Reponse(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            contenu=contenu,
            statut="EN_ATTENTE",
            source="LLM",
            score_similarite=top_score,
        )
        db.add(reponse)
    else:
        reponse.contenu = contenu
        reponse.score_similarite = top_score
    db.flush()
    return reponse


@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions"
)
def question_job(self, question: str, domaine: str, user_id: str | None = None):
    try:
        print("❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        job_id = uuid.UUID(self.request.id)
        user_uuid = uuid.UUID(user_id) if user_id else None

        # Étape 1 — Embedding + recherche hybride
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(f"[QUESTION] #{i+1} score_cosinus={chunk['score_cosinus']:.4f} source={chunk['source']}")

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Branche canonique
        # Le chunk qui franchit le seuil doit porter la référence de SA réponse
        # validée (payload reponse_id, écrit lors de la réindexation Phase 4).
        # Sans ce lien, on ne renvoie rien de canonique : on tombe dans le RAG.
        reponse_id_canonique = chunks[0].get("reponse_id") if chunks else None
        if top_score >= SEUIL_COSINUS and reponse_id_canonique:
            print(f"[QUESTION] Score {top_score:.4f} ≥ seuil {SEUIL_COSINUS} → lookup réponse {reponse_id_canonique}")
            db = SessionLocal()
            try:
                reponse_canonique = db.query(Reponse).filter(
                    Reponse.id == uuid.UUID(str(reponse_id_canonique)),
                    Reponse.statut == "VALIDÉE",
                ).first()

                if reponse_canonique:
                    print("[QUESTION] ✅ Réponse canonique trouvée")
                    # Une correction humaine prime sur le contenu d'origine
                    contenu_canonique = reponse_canonique.contenu_corrige or reponse_canonique.contenu

                    ticket = _upsert_ticket(
                        db, job_id,
                        question=question,
                        domaine=domaine,
                        user_id=user_uuid,
                        statut_job="TERMINÉ",
                        statut_ticket="RÉPONDU",
                        score_similarite=top_score,
                        canonique=True,
                        nb_retries=self.request.retries,
                        erreur=None,
                        processed_at=datetime.now(timezone.utc),
                    )
                    ticket_id = str(ticket.id)

                    # ADD OCCURENCE +1
                    ticket_source = db.query(Ticket).filter(
                    Ticket.id == reponse_canonique.ticket_id
                    ).first()

                    if ticket_source:
                        ticket_source.occurence += 1
                    db.commit()

                    return {
                        "statut": "OK",
                        "branche": "CANONIQUE",
                        "question": question,
                        "domaine": domaine,
                        "reponse": contenu_canonique,
                        "ticket_id": ticket_id,
                        "reponse_id": str(reponse_id_canonique),
                        "top_score_cosinus": top_score,
                    }
            finally:
                db.close()

        # Étape 3 — Reranking
        print("[QUESTION] Reranking des chunks...")
        chunks_rerankes = rerank(question, chunks, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            print(f"[QUESTION] Rerank #{i+1} score={chunk['rerank_score']:.4f} source={chunk['source']}")

        # Étape 4 — Génération LLM
        print("[QUESTION] Génération LLM...")
        try:
            reponse_texte = generate(question, chunks_rerankes)
            print(f"[QUESTION] ✅ Réponse générée ({len(reponse_texte)} caractères)")
            statut_job = "TERMINÉ"
            erreur = None
        except Exception as llm_exc:
            print(f"[QUESTION] ❌ Erreur LLM : {llm_exc}")
            reponse_texte = None
            statut_job = "ÉCHOUÉ"
            erreur = str(llm_exc)

        # Étape 5 — Sauvegarde PostgreSQL (idempotente au retry via job_id)
        db = SessionLocal()
        try:
            ticket = _upsert_ticket(
                db, job_id,
                question=question,
                domaine=domaine,
                user_id=user_uuid,
                statut_job=statut_job,
                statut_ticket="RÉPONDU" if reponse_texte else "NOUVEAU",
                score_similarite=top_score,
                canonique=False,
                nb_retries=self.request.retries,
                erreur=erreur,
                processed_at=datetime.now(timezone.utc),
            )

            reponse_id = None
            if reponse_texte:
                reponse = _upsert_reponse(db, ticket, reponse_texte, top_score)
                reponse_id = str(reponse.id)

            ticket_id = str(ticket.id)
            db.commit()
        finally:
            db.close()

        print(f"[QUESTION] Ticket créé (id={ticket_id})")

        # Si LLM a échoué après sauvegarde → retry
        if statut_job == "ÉCHOUÉ":
            raise self.retry(
                exc=Exception(erreur),
                countdown=60
            )

        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "reponse": reponse_texte,
            "ticket_id": ticket_id,
            "reponse_id": reponse_id,
            "top_score_cosinus": top_score,
        }

    except Retry:
        # self.retry() a déjà été appelé plus haut — ne pas le ré-encapsuler
        raise
    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
