"""Pipeline RAG : fonctions métier extraites de workers/question.py.

Aucun décorateur Celery ici : ce module est importé par le worker,
et non l'inverse, pour briser la dépendance circulaire.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.broadcast import broadcast_sync
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Deux planchers de candidature INDÉPENDANTS. Ils dérivaient auparavant l'un de
# l'autre (`SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05`), ce qui rendait impossible
# d'abaisser le plancher canonique sans abaisser du même coup la porte du service
# sans revue humaine — exactement le contraire du but.
#
# `SEUIL_COSINUS` a disparu de ce module : il ne gouverne plus aucune décision
# (AUC 0.000, mesuré). Une constante qui ne décide plus rien mais qui reste
# exportée est un piège pour le prochain lecteur.
SEUIL_CANDIDAT_CANONIQUE = settings.seuil_candidat_canonique
SEUIL_SUGGESTION = settings.seuil_suggestion


class TicketDisparu(Exception):
    """Le ticket ciblé n'existe plus en base : le job n'a plus d'objet.

    Ce n'est pas une panne, c'est une course perdue — une suppression, ou un
    retraitement enfilé sur un ticket effacé depuis. La distinguer d'une erreur
    ordinaire est indispensable : réessayer ne peut rien y changer, et chaque
    tentative repaie l'embedding, le rerank et la génération pour rien.
    """


def upsert_ticket(db: Session, job_id: uuid.UUID, ticket_id: uuid.UUID | None = None, **fields) -> Ticket:
    if ticket_id is not None:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            raise TicketDisparu(str(ticket_id))
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


def upsert_reponse(
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
    garde_verdict: str | None = None,
    garde_justification: str | None = None,
) -> Reponse:
    reponse = (
        None
        if nouveau
        else (db.query(Reponse).filter(Reponse.ticket_id == ticket.id, Reponse.obsolete.is_(False)).first())
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
            garde_verdict=garde_verdict,
            garde_justification=garde_justification,
        )
        db.add(reponse)
    else:
        reponse.contenu = contenu
        reponse.score_similarite = top_score
        # Réécrits même sur une réponse recyclée : un retraitement qui repasse en
        # CANONIQUE doit porter le verdict qui l'a autorisé, pas celui d'avant.
        reponse.garde_verdict = garde_verdict
        reponse.garde_justification = garde_justification
    db.flush()
    return reponse


def ticket_existe(ticket_id: uuid.UUID) -> bool:
    """Session courte et dédiée : on interroge avant d'ouvrir le pipeline."""
    db = SessionLocal()
    try:
        return db.query(Ticket.id).filter(Ticket.id == ticket_id).first() is not None
    finally:
        db.close()


def charger_contexte_fil(ticket_id: uuid.UUID, precision: str) -> tuple[list[dict], str]:
    """Reconstitue le fil d'un ticket pour contextualiser une précision.

    Renvoie :
      - `historique` : messages alternés {"role", "content"} des tours passés,
        prêts à être passés au LLM ;
      - `requete_recherche` : concaténation des intentions utilisateur pour la
        recherche/rerank.
    """
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            return [], precision

        reponses = db.query(Reponse).filter(Reponse.ticket_id == ticket_id).order_by(Reponse.created_at.asc()).all()

        historique: list[dict] = []
        questions_utilisateur: list[str] = [ticket.question]
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


def trouver_reponse_reutilisable(db: Session, chunks: list[dict]) -> tuple[Reponse | None, float | None]:
    """Cherche, parmi les chunks, une réponse VALIDÉE réutilisable.

    Deux planchers, selon la nature du candidat :
      - **canonique** : `SEUIL_CANDIDAT_CANONIQUE` (bas). Ces réponses passeront
        devant les juges du garde avant d'être servies, le plancher n'a donc plus
        à porter la sûreté — il ne fait que borner le coût.
      - **non canonique** : `SEUIL_SUGGESTION` (haut, inchangé). Aucun juge ne
        filtre la branche SUGGESTION ; abaisser ce plancher mettrait sous les yeux
        du validateur des réponses génériques hors sujet à la place d'une réponse
        RAG ciblée.

    La nature du candidat n'étant connue qu'après la requête SQL, on retient
    d'abord au plancher le plus bas des deux, puis on écarte.

    Plusieurs réponses validées peuvent matcher → on retient le meilleur score par
    `reponse_id`, puis on choisit de façon déterministe (canonique, plus validée,
    meilleur score, id). Renvoie `(reponse, score)` ou `(None, None)`.
    """
    plancher_bas = min(SEUIL_CANDIDAT_CANONIQUE, SEUIL_SUGGESTION)
    scores_par_reponse: dict[str, float] = {}
    for c in chunks:
        rid = c.get("reponse_id")
        if rid and c["score_cosinus"] >= plancher_bas:
            rid = str(rid)
            scores_par_reponse[rid] = max(scores_par_reponse.get(rid, 0.0), c["score_cosinus"])

    if not scores_par_reponse:
        return None, None

    candidats = (
        db.query(Reponse)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in scores_par_reponse]),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )
    candidats = [
        r
        for r in candidats
        if scores_par_reponse[str(r.id)] >= (SEUIL_CANDIDAT_CANONIQUE if r.canonique else SEUIL_SUGGESTION)
    ]
    if not candidats:
        return None, None

    # Le départage est conservé tel quel : `nb_validations` prime toujours sur le
    # score. Ce n'est plus un risque comme avant — un mauvais choix de candidat
    # canonique est désormais rattrapé par le garde, qui refusera de le servir.
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


def servir_reutilisation(
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
    garde_verdict: str | None = None,
    garde_justification: str | None = None,
) -> dict:
    """Persiste et renvoie la réutilisation d'une réponse validée.

    `autoriser_canonique` porte désormais le verdict du garde
    (`services/garde_cache.py`) : la branche CANONIQUE — servie à l'employé sans
    qu'aucun humain ne la relise — n'est ouverte que si les deux juges ont
    approuvé. Le score cosinus ne conditionne plus rien ici : mesuré non
    informatif (AUC 0.000), il classait même les cas à l'envers.

    `garde_verdict` / `garde_justification` sont tracés en base sur la réponse
    servie. Sans eux, une réponse CANONIQUE et une réponse validée à la main sont
    indiscernables (`statut="VALIDÉE"`, `validator_id=None`), et le taux d'erreur
    des juges en production reste immesurable.
    """
    contenu = reponse_liee.contenu_corrige or reponse_liee.contenu

    if autoriser_canonique and reponse_liee.canonique:
        logger.info(
            "Réponse canonique servie : %s (score=%.3f, garde=%s)",
            reponse_liee.id,
            score_liee,
            garde_verdict,
        )
        ticket = upsert_ticket(
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

        reponse = upsert_reponse(
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
            garde_verdict=garde_verdict,
            garde_justification=garde_justification,
        )

        ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
        if ticket_source:
            ticket_source.occurence += 1

        if ticket.user_id:
            db.add(
                Notification(
                    user_id=ticket.user_id,
                    ticket_id=ticket.id,
                    reponse_id=reponse.id,
                    type="REPONSE_VALIDEE",
                )
            )
        db.commit()

        event = "ticket_followup" if est_suivi else "ticket_answered"
        broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str, "domaine": domaine})
        if ticket.user_id:
            broadcast_sync(f"sse:user:{ticket.user_id}", "notification_created", {"ticket_id": ticket_id_str})

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

    logger.info("Suggestion via réponse validée %s (score=%.3f)", reponse_liee.id, score_liee)
    ticket = upsert_ticket(
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
    reponse = upsert_reponse(
        db,
        ticket,
        contenu,
        score_liee,
        source="SUGGESTION",
        reponse_source_id=reponse_liee.id,
        question_suivi=question_suivi,
        nouveau=est_suivi,
    )
    ticket_id_str_sug = str(ticket.id)
    db.commit()

    event = "ticket_followup" if est_suivi else "ticket_answered"
    broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str_sug, "domaine": domaine})
    if user_uuid:
        broadcast_sync(f"sse:user:{user_uuid}", event, {"ticket_id": ticket_id_str_sug, "domaine": domaine})

    return {
        "statut": "OK",
        "branche": "SUGGESTION",
        "question": question,
        "domaine": domaine,
        "reponse": contenu,
        "ticket_id": ticket_id_str_sug,
        "reponse_id": str(reponse.id),
        "reponse_source_id": str(reponse_liee.id),
        "top_score_cosinus": score_liee,
    }
