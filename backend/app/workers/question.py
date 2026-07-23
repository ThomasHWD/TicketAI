import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.llm import generate
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

SEUIL_COSINUS = settings.seuil_cosinus


def _upsert_ticket(
    db: Session, job_id: uuid.UUID, ticket_id: uuid.UUID | None = None, **fields
) -> Ticket:
    # Mode suivi : on cible le ticket existant (par son id) au lieu de le retrouver
    # par job_id. On ne réécrit ni la question, ni le domaine, ni l'auteur d'origine.
    # En revanche `statut_ticket`/`canonique` suivent le DERNIER tour : une précision
    # en attente de validation doit rebasculer le ticket en « en cours » (badges).
    if ticket_id is not None:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        for key in ("question", "domaine", "user_id"):
            fields.pop(key, None)
        for key, value in fields.items():
            setattr(ticket, key, value)
        db.flush()
        return ticket

    ticket = db.query(Ticket).filter(Ticket.job_id == job_id).first()
    if ticket is None:
        ticket = Ticket(id=uuid.uuid4(), job_id=job_id, **fields)
        db.add(ticket)
    else:
        for key, value in fields.items():
            setattr(ticket, key, value)
    db.flush()
    return ticket


def _upsert_reponse(
    db: Session,
    ticket: Ticket,
    contenu: str,
    top_score: float,
    source: str = "LLM",
    reponse_source_id: uuid.UUID | None = None,
    statut: str = "EN_ATTENTE",
    canonique: bool = False,
    question_suivi: str | None = None,
    nouveau: bool = False,
) -> Reponse:
    # Mode suivi (`nouveau`) : on ajoute TOUJOURS une nouvelle réponse au fil, sans
    # écraser la précédente, et on mémorise le texte de la précision (`question_suivi`).
    reponse = (
        None if nouveau
        else db.query(Reponse).filter(Reponse.ticket_id == ticket.id).first()
    )
    if reponse is None:
        reponse = Reponse(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            contenu=contenu,
            statut=statut,
            source=source,
            score_similarite=top_score,
            reponse_source_id=reponse_source_id,
            canonique=canonique,
            question_suivi=question_suivi,
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
    queue="queue_questions",
)
def question_job(
    self,
    question: str,
    domaine: str,
    user_id: str | None = None,
    ticket_id: str | None = None,
):
    try:
        print("❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        job_id = uuid.UUID(self.request.id)
        user_uuid = uuid.UUID(user_id) if user_id else None

        # Mode suivi : la question est une précision ajoutée à un ticket existant.
        # On la mémorise comme `question_suivi` du nouveau tour et on rattache la
        # réponse au ticket d'origine plutôt que d'en créer un nouveau.
        ticket_uuid = uuid.UUID(ticket_id) if ticket_id else None
        est_suivi = ticket_uuid is not None
        question_suivi = question if est_suivi else None

        # Étape 1 — Embedding + recherche hybride
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(
                f"[QUESTION] #{i+1} score_cosinus={chunk['score_cosinus']:.4f} source={chunk['source']}"
            )

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Réponse déjà validée, retrouvée DIRECTEMENT via son reponse_id.
        # feedback_job réindexe dans Qdrant chaque réponse validée (payload `reponse_id`).
        # On récupère donc LA réponse liée sémantiquement à la question — et non une réponse
        # qui partagerait seulement un document source (ancien matching par doc_id, trop large
        # et à l'origine des suggestions sans rapport).
        # Seuil suggestion légèrement sous SEUIL_COSINUS : question très proche d'une validée.
        SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05

        # Plusieurs réponses validées peuvent matcher la même question (doublons de tests,
        # mêmes questions posées et validées séparément) → toutes au même score. On collecte
        # les candidates (meilleur score par reponse_id) puis on choisit de façon DÉTERMINISTE
        # la meilleure, pour rester cohérent d'un appel à l'autre et faire converger les
        # validations vers une seule réponse (sinon aucune n'atteint jamais le seuil canonique).
        scores_par_reponse: dict[str, float] = {}
        for c in chunks:
            rid = c.get("reponse_id")
            if rid and c["score_cosinus"] >= SEUIL_SUGGESTION:
                rid = str(rid)
                scores_par_reponse[rid] = max(
                    scores_par_reponse.get(rid, 0.0), c["score_cosinus"]
                )

        if scores_par_reponse:
            db = SessionLocal()
            try:
                candidats = (
                    db.query(Reponse)
                    .filter(
                        Reponse.id.in_([uuid.UUID(r) for r in scores_par_reponse]),
                        Reponse.statut == "VALIDÉE",
                    )
                    .all()
                )
                # Priorité : canonique, puis la plus validée, puis meilleur score,
                # puis id (départage stable → strictement déterministe).
                reponse_liee = (
                    max(
                        candidats,
                        key=lambda r: (
                            r.canonique,
                            r.nb_validations,
                            scores_par_reponse[str(r.id)],
                            str(r.id),
                        ),
                    )
                    if candidats
                    else None
                )
                if reponse_liee:
                    score_liee = scores_par_reponse[str(reponse_liee.id)]
                    print(
                        f"[QUESTION] Score {score_liee:.4f} → réponse validée {reponse_liee.id}"
                    )
                    contenu = reponse_liee.contenu_corrige or reponse_liee.contenu

                    # Étape 2.1 — Branche CANONIQUE : réponse promue canonique
                    # (nb_validations ≥ seuil_canonique) ET score ≥ seuil → aucune revue humaine.
                    if reponse_liee.canonique and score_liee >= SEUIL_COSINUS:
                        print(f"[QUESTION] ✅ Réponse canonique {reponse_liee.id}")
                        ticket = _upsert_ticket(
                            db,
                            job_id,
                            ticket_id=ticket_uuid,
                            question=question,
                            domaine=domaine,
                            user_id=user_uuid,
                            statut_job="TERMINÉ",
                            statut_ticket="RÉPONDU",
                            score_similarite=score_liee,
                            canonique=True,
                            nb_retries=self.request.retries,
                            erreur=None,
                            processed_at=datetime.now(timezone.utc),
                        )
                        ticket_id_str = str(ticket.id)

                        # Persiste une réponse (déjà validée / canonique) pour qu'elle
                        # s'affiche dans le back-office — sans revue humaine à faire.
                        reponse = _upsert_reponse(
                            db,
                            ticket,
                            contenu,
                            score_liee,
                            source="CANONIQUE",
                            reponse_source_id=reponse_liee.id,
                            statut="VALIDÉE",
                            canonique=True,
                            question_suivi=question_suivi,
                            nouveau=est_suivi,
                        )

                        ticket_source = (
                            db.query(Ticket)
                            .filter(Ticket.id == reponse_liee.ticket_id)
                            .first()
                        )
                        if ticket_source:
                            ticket_source.occurence += 1
                        db.commit()

                        return {
                            "statut": "OK",
                            "branche": "CANONIQUE",
                            "question": question,
                            "domaine": domaine,
                            "reponse": contenu,
                            "ticket_id": ticket_id_str,
                            "reponse_id": str(reponse.id),
                            "reponse_source_id": str(reponse_liee.id),
                            "top_score_cosinus": score_liee,
                        }

                    # Étape 2.2 — Branche SUGGESTION : réponse validée au moins une fois
                    # mais pas encore canonique (ou canonique sous le seuil de confiance)
                    # → on propose CETTE réponse précise, revue humaine requise.
                    print(f"[QUESTION] 💡 Suggestion via réponse validée {reponse_liee.id}")
                    ticket = _upsert_ticket(
                        db,
                        job_id,
                        ticket_id=ticket_uuid,
                        question=question,
                        domaine=domaine,
                        user_id=user_uuid,
                        statut_job="TERMINÉ",
                        statut_ticket="RÉPONDU",
                        score_similarite=score_liee,
                        canonique=False,
                        nb_retries=self.request.retries,
                        erreur=None,
                        processed_at=datetime.now(timezone.utc),
                    )
                    reponse = _upsert_reponse(
                        db,
                        ticket,
                        contenu,
                        score_liee,
                        source="SUGGESTION",
                        reponse_source_id=reponse_liee.id,
                        question_suivi=question_suivi,
                        nouveau=est_suivi,
                    )
                    db.commit()

                    return {
                        "statut": "OK",
                        "branche": "SUGGESTION",
                        "question": question,
                        "domaine": domaine,
                        "reponse": contenu,
                        "ticket_id": str(ticket.id),
                        "reponse_id": str(reponse.id),
                        "reponse_source_id": str(reponse_liee.id),
                        "top_score_cosinus": score_liee,
                    }
            finally:
                db.close()

        # Étape 3 — Reranking
        print("[QUESTION] Reranking des chunks...")
        chunks_rerankes = rerank(question, chunks, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            print(
                f"[QUESTION] Rerank #{i+1} score={chunk['rerank_score']:.4f} source={chunk['source']}"
            )

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

        # Étape 5 — Sauvegarde PostgreSQL + enregistrement chunks
        db = SessionLocal()
        try:
            ticket = _upsert_ticket(
                db,
                job_id,
                ticket_id=ticket_uuid,
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
                reponse = _upsert_reponse(
                    db,
                    ticket,
                    reponse_texte,
                    top_score,
                    question_suivi=question_suivi,
                    nouveau=est_suivi,
                )
                reponse_id = str(reponse.id)

                # Enregistre les chunks utilisés pour la génération
                for chunk in chunks_rerankes:
                    if not chunk.get("doc_id"):
                        continue
                    rc = ReponseChunk(
                        id=uuid.uuid4(),
                        reponse_id=reponse.id,
                        doc_id=chunk.get("doc_id"),
                        chunk_index=chunk.get("chunk_index", 0),
                        score_cosinus=chunk.get("score_cosinus"),
                        rerank_score=chunk.get("rerank_score"),
                    )
                    db.add(rc)

            ticket_id_str = str(ticket.id)
            db.commit()
        finally:
            db.close()

        print(f"[QUESTION] Ticket créé (id={ticket_id_str})")

        if statut_job == "ÉCHOUÉ":
            raise self.retry(exc=Exception(erreur), countdown=60)

        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "reponse": reponse_texte,
            "ticket_id": ticket_id_str,
            "reponse_id": reponse_id,
            "top_score_cosinus": top_score,
        }

    except Retry:
        raise
    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
