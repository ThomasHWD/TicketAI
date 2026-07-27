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
# Seuil suggestion légèrement sous SEUIL_COSINUS : question très proche d'une validée.
SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05


def _upsert_ticket(db: Session, job_id: uuid.UUID, ticket_id: uuid.UUID | None = None, **fields) -> Ticket:
    # Mode suivi : on cible le ticket existant (par son id) au lieu de le retrouver
    # par job_id. On ne réécrit ni la question, ni le domaine, ni l'auteur d'origine.
    # En revanche `statut_ticket`/`canonique` suivent le DERNIER tour : une précision
    # en attente de validation doit rebasculer le ticket en « en cours » (badges).
    if ticket_id is not None:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        for key in ("question", "domaine", "user_id", "objet"):
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
    reponse = None if nouveau else db.query(Reponse).filter(Reponse.ticket_id == ticket.id).first()
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


def _charger_contexte_fil(ticket_id: uuid.UUID, precision: str) -> tuple[list[dict], str]:
    """Reconstitue le fil d'un ticket pour contextualiser une précision.

    Renvoie :
      - `historique` : messages alternés {"role", "content"} des tours passés
        (question d'origine + réponses, puis chaque précision + sa réponse),
        prêts à être passés au LLM ;
      - `requete_recherche` : concaténation des intentions utilisateur
        (question d'origine + précisions + précision courante) pour la
        recherche/rerank. On exclut les réponses (longues) pour ne pas diluer
        l'embedding.

    Les tours précédents sont validés avant qu'une nouvelle précision soit
    permise (garde front `suiviEnCours`) → on prend `contenu_corrige or contenu`.
    """
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            return [], precision

        reponses = db.query(Reponse).filter(Reponse.ticket_id == ticket_id).order_by(Reponse.created_at.asc()).all()

        historique: list[dict] = []
        questions_utilisateur: list[str] = [ticket.question]
        # Le premier tour utilisateur est la question d'origine ; les tours
        # suivants portent leur précision dans `question_suivi`.
        premier = True
        for r in reponses:
            if premier:
                historique.append({"role": "user", "content": ticket.question})
                premier = False
            elif r.question_suivi:
                historique.append({"role": "user", "content": r.question_suivi})
                questions_utilisateur.append(r.question_suivi)
            historique.append({"role": "assistant", "content": r.contenu_corrige or r.contenu})

        questions_utilisateur.append(precision)
        requete_recherche = "\n".join(questions_utilisateur)
        return historique, requete_recherche
    finally:
        db.close()


def _trouver_reponse_reutilisable(db: Session, chunks: list[dict]) -> tuple[Reponse | None, float | None]:
    """Cherche, parmi les chunks, une réponse VALIDÉE réutilisable (retrouvée via
    son `reponse_id` réindexé dans Qdrant), au-dessus de SEUIL_SUGGESTION.

    Plusieurs réponses validées peuvent matcher (doublons de tests, mêmes
    questions validées séparément) → on retient le meilleur score par
    `reponse_id`, puis on choisit de façon DÉTERMINISTE (canonique, plus validée,
    meilleur score, id) pour converger les validations vers une seule réponse.
    Renvoie `(reponse, score)` ou `(None, None)`.
    """
    scores_par_reponse: dict[str, float] = {}
    for c in chunks:
        rid = c.get("reponse_id")
        if rid and c["score_cosinus"] >= SEUIL_SUGGESTION:
            rid = str(rid)
            scores_par_reponse[rid] = max(scores_par_reponse.get(rid, 0.0), c["score_cosinus"])

    if not scores_par_reponse:
        return None, None

    candidats = (
        db.query(Reponse)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in scores_par_reponse]),
            Reponse.statut == "VALIDÉE",
        )
        .all()
    )
    if not candidats:
        return None, None

    reponse_liee = max(
        candidats,
        key=lambda r: (
            r.canonique,
            r.nb_validations,
            scores_par_reponse[str(r.id)],
            str(r.id),
        ),
    )
    return reponse_liee, scores_par_reponse[str(reponse_liee.id)]


def _servir_reutilisation(
    db: Session,
    job_id: uuid.UUID,
    ticket_uuid: uuid.UUID | None,
    question: str,
    domaine: str,
    user_uuid: uuid.UUID | None,
    reponse_liee: Reponse,
    score_liee: float,
    question_suivi: str | None,
    est_suivi: bool,
    nb_retries: int,
    autoriser_canonique: bool,
    objet: str | None = None,
) -> dict:
    """Persiste et renvoie la réutilisation d'une réponse validée.

    `autoriser_canonique` : n'autorise la branche CANONIQUE (servie sans revue
    humaine) que si le match provient de la question/précision BRUTE. Un match
    obtenu par contextualisation du fil ressort toujours en SUGGESTION (revue
    humaine), pour ne jamais resservir automatiquement une réponse à une précision
    qui apporte une nuance nouvelle.
    """
    contenu = reponse_liee.contenu_corrige or reponse_liee.contenu

    # Branche CANONIQUE : réponse promue canonique (nb_validations ≥ seuil) ET
    # score ≥ seuil, uniquement sur un match brut → aucune revue humaine.
    if autoriser_canonique and reponse_liee.canonique and score_liee >= SEUIL_COSINUS:
        print(f"[QUESTION] ✅ Réponse canonique {reponse_liee.id}")
        ticket = _upsert_ticket(
            db,
            job_id,
            ticket_id=ticket_uuid,
            question=question,
            objet=objet,
            domaine=domaine,
            user_id=user_uuid,
            statut_job="TERMINÉ",
            statut_ticket="RÉPONDU",
            score_similarite=score_liee,
            canonique=True,
            nb_retries=nb_retries,
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

        ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
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

    # Branche SUGGESTION : réponse validée réutilisée, revue humaine requise
    # (canonique sous le seuil, non encore canonique, ou match contextuel).
    print(f"[QUESTION] 💡 Suggestion via réponse validée {reponse_liee.id}")
    ticket = _upsert_ticket(
        db,
        job_id,
        ticket_id=ticket_uuid,
        question=question,
        objet=objet,
        domaine=domaine,
        user_id=user_uuid,
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
        score_similarite=score_liee,
        canonique=False,
        nb_retries=nb_retries,
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
    objet: str | None = None,
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

        # Étape 0 (suivi) — Charger le fil pour contextualiser recherche et LLM.
        # `historique` : messages alternés user/assistant des tours précédents,
        # passés au LLM. `requete_recherche` : intentions utilisateur concaténées
        # (question d'origine + précisions), pour une recherche/rerank pertinents
        # sur une précision courte (« Et pour un CDD ? »).
        historique: list[dict] | None = None
        requete_recherche = question
        if est_suivi:
            historique, requete_recherche = _charger_contexte_fil(ticket_uuid, question)

        # Étape 1 — Embedding + recherche hybride
        # La recherche initiale reste sur la question/précision BRUTE : elle
        # alimente la lookup de réutilisation (CANONIQUE/SUGGESTION) et top_score.
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(f"[QUESTION] #{i + 1} score_cosinus={chunk['score_cosinus']:.4f} source={chunk['source']}")

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Réponse déjà validée, retrouvée DIRECTEMENT via son reponse_id.
        # feedback_job réindexe dans Qdrant chaque réponse validée (payload `reponse_id`).
        # On récupère donc LA réponse liée sémantiquement à la question — et non une réponse
        # qui partagerait seulement un document source (ancien matching par doc_id, trop large
        # et à l'origine des suggestions sans rapport).
        #
        # En mode suivi : on tente d'abord la réutilisation sur la précision BRUTE
        # (peut servir une CANONIQUE sans revue). Si rien ne matche, on retente sur
        # la requête CONTEXTUALISÉE du fil — mais un match contextuel ne peut sortir
        # qu'en SUGGESTION (revue humaine), jamais servi automatiquement. Ainsi une
        # reformulation (« Même question ») réutilise la réponse d'origine (en
        # suggestion), sans qu'une précision nuancée (« Et pour un CDD ? ») ne
        # resserve à tort la canonique de la question initiale.
        chunks_ctx: list[dict] | None = None
        db = SessionLocal()
        try:
            reponse_liee, score_liee = _trouver_reponse_reutilisable(db, chunks)

            if reponse_liee is not None:
                print(f"[QUESTION] Score {score_liee:.4f} → réponse validée {reponse_liee.id}")
                return _servir_reutilisation(
                    db,
                    job_id,
                    ticket_uuid,
                    question,
                    domaine,
                    user_uuid,
                    reponse_liee,
                    score_liee,
                    question_suivi,
                    est_suivi,
                    self.request.retries,
                    True,
                    objet,
                )

            # En mode suivi, si la précision brute ne matche rien, on retente sur
            # la requête contextualisée. Un match contextuel sort toujours en
            # SUGGESTION (autoriser_canonique=False), jamais servi automatiquement.
            if est_suivi:
                chunks_ctx = search_hybrid(requete_recherche, domaine, top_k=15)
                reponse_liee_ctx, score_liee_ctx = _trouver_reponse_reutilisable(db, chunks_ctx)
                if reponse_liee_ctx is not None:
                    print(f"[QUESTION] Score contextuel {score_liee_ctx:.4f} → réponse validée {reponse_liee_ctx.id}"
                          f" (SUGGESTION forcée)")
                    return _servir_reutilisation(
                        db,
                        job_id,
                        ticket_uuid,
                        question,
                        domaine,
                        user_uuid,
                        reponse_liee_ctx,
                        score_liee_ctx,
                        question_suivi,
                        est_suivi,
                        self.request.retries,
                        False,
                        objet,
                    )
        finally:
            db.close()

        # Étape 3 — Reranking
        # Branche RAG : pour un suivi, on rerank/génère sur les chunks
        # CONTEXTUALISÉS (déjà récupérés ci-dessus) afin de retrouver les bons
        # documents malgré une précision courte. Le chemin standalone est inchangé.
        if est_suivi:
            if chunks_ctx is None:
                chunks_ctx = search_hybrid(requete_recherche, domaine, top_k=15)
            chunks_rag = chunks_ctx
        else:
            chunks_rag = chunks
        print("[QUESTION] Reranking des chunks...")
        chunks_rerankes = rerank(requete_recherche, chunks_rag, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            print(f"[QUESTION] Rerank #{i + 1} score={chunk['rerank_score']:.4f} source={chunk['source']}")

        # Étape 4 — Génération LLM (avec l'historique du fil pour un suivi)
        print("[QUESTION] Génération LLM...")
        try:
            reponse_texte = generate(question, chunks_rerankes, historique=historique)
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
                objet=objet,
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
