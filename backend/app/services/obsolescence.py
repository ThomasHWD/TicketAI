"""Cycle de vie des réponses rendues obsolètes par un changement de document. La comparaison est document↔document"""

import logging
import uuid
from datetime import datetime, timezone

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.diff import (  # noqa: F401 — ré-exportés pour la compatibilité des imports existants
    MAX_EXTRAITS,
    Unite,
    analyser_changements,
    decouper_en_passages,
    deserialiser_unites,
    extrait,
    indices_modifies,
    passages_ajoutes,
    serialiser_unites,
    unites_de_changement,
)
from app.services.qdrant import delete_response_point
from sqlalchemy import or_
from sqlalchemy.orm import Session

# Raisons d'obsolescence stockées dans `Reponse.obsolete_raison`
RAISON_MAJ = "DOC_MIS_A_JOUR"
RAISON_SUPPRESSION = "DOC_SUPPRIMÉ"
RAISON_MANUELLE = "RETIRÉ_À_LA_MAIN"

# Raisons de relecture stockées dans `Reponse.a_relire_raison`
RAISON_MODIF = "DOC_MODIFIÉ"
RAISON_ILLISIBLE = "VERSION_SORTANTE_ILLISIBLE"

# Verdict de la ré-vérification (cf. `services/reverification.py`)
RAISON_CONTREDITE = "CONTREDITE_PAR_MAJ"  # obsolete_raison
RAISON_CONTREDITE_PROB = "CONTREDITE_PROBABLE"  # a_relire_raison
RAISON_ANALYSE = "ANALYSE_EN_COURS"  # a_relire_raison, transitoire
RAISON_INDISPONIBLE = "ANALYSE_INDISPONIBLE"  # a_relire_raison, repli
RAISON_PARTIELLE = "ANALYSE_PARTIELLE"  # a_relire_raison, budget épuisé
RAISON_MASSIVE = "REECRITURE_MASSIVE"  # a_relire_raison, document réécrit

# Distinct de RAISON_MODIF : document ajouté, pas modifié — le relecteur n'a pas de diff à consulter.
RAISON_NOUVEAU_DOC = "NOUVEAU_DOC"  # a_relire_raison, verdict INCERTAIN à l'ingestion


def fermeture_copies(db: Session, graines: set[uuid.UUID]) -> set[uuid.UUID]:
    """Descend des réponses-graines vers toutes leurs copies, transitivement. SUGGESTION/CANONIQUE copies only link"""
    vus = set(graines)
    frontiere = set(graines)
    while frontiere:
        copies = {r[0] for r in db.query(Reponse.id).filter(Reponse.reponse_source_id.in_(frontiere)).all()}
        frontiere = copies - vus
        vus |= frontiere
    return vus


def reponses_obsoletes(
    db: Session,
    doc_id: str,
    indices: set[int] | None = None,
    version: int | None = None,
) -> list[Reponse]:
    """Réponses indexées dans Qdrant qui s'appuient sur les chunks visés. `indices=None` = tout le document (cas de"""
    if indices is not None and not indices:
        return []

    q = db.query(ReponseChunk.reponse_id).filter(ReponseChunk.doc_id == doc_id)
    if indices is not None:
        q = q.filter(ReponseChunk.chunk_index.in_(sorted(indices)))
        if version is not None:
            # indices name passages of `version` — the same index in another version is another passage
            q = q.filter(or_(ReponseChunk.version == version, ReponseChunk.version.is_(None)))

    graines = {r[0] for r in q.distinct().all()}
    if not graines:
        return []

    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, graines)),
            Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def racines(reponses: list[Reponse]) -> list[Reponse]:
    """Réduit une famille aux réponses *distinctes* qu'elle représente. Ecarte les copies dont la source est dans"""
    ids = {r.id for r in reponses}
    return [r for r in reponses if r.reponse_source_id not in ids]


def marquer_obsoletes(
    db: Session,
    doc_id: str,
    raison: str,
    version: int | None = None,
    indices: set[int] | None = None,
) -> tuple[list[Reponse], list[Reponse]]:
    """Retire de Qdrant puis marque obsolètes les réponses concernées. Idempotent. Second élément : les EN_ATTENTE
    retirées, à renvoyer au pipeline par l'appelant — brouillons citants ET copies SUGGESTION des réponses retirées
    (sans citation, `perimer_en_attente` ne les voit pas : elles restaient validables sur un document supprimé)."""
    reponses = reponses_obsoletes(db, doc_id, indices)
    brouillons = (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, {r.id for r in reponses})),
            Reponse.statut == "EN_ATTENTE",
            Reponse.obsolete.is_(False),
        )
        .all()
        if reponses
        else []
    )
    retirer_du_service(db, reponses + brouillons, raison, doc_id, version)
    citants = perimer_en_attente(db, doc_id, raison, version)
    return reponses, brouillons + [r for r in citants if r not in brouillons]


def perimer_en_attente(db: Session, doc_id: str, raison: str, version: int | None) -> list[Reponse]:
    """Périme les réponses EN_ATTENTE bâties sur le document. Elles n'ont jamais été servies ; les valider plus tard"""
    ids = {
        r[0]
        for r in db.query(Reponse.id)
        .join(ReponseChunk, ReponseChunk.reponse_id == Reponse.id)
        .filter(
            ReponseChunk.doc_id == doc_id,
            Reponse.statut == "EN_ATTENTE",
            Reponse.obsolete.is_(False),
        )
        .distinct()
        .all()
    }
    en_attente = db.query(Reponse).filter(Reponse.id.in_(ids)).all() if ids else []
    retirer_du_service(db, en_attente, raison, doc_id, version)
    return en_attente


def indexation_d_origine(r: Reponse) -> list[str] | None:
    """`feedback_job` args rebuilding the point this response had before it was withdrawn — nothing more.
    A copy is not a source: indexed on its own it served its frozen text, blind to later edits of the source
    (29/09/2026: source edited to 400 €, the question came back as a SUGGESTION of a copy still saying 300 €)."""
    if r.statut not in ("VALIDÉE", "CORRIGÉE"):
        return None
    if r.reponse_source_id is None or r.statut == "CORRIGÉE":
        return [str(r.id)]  # a source, or a corrected copy — « Corriger » indexes it under its own question
    if r.source == "SUGGESTION":
        return [str(r.reponse_source_id), str(r.id)]  # human-validated formulation: alias of its source, re-judged
    return None  # CANONIQUE served without review — never had a point of its own


def retirer_du_service(
    db: Session,
    reponses: list[Reponse],
    raison: str,
    doc_id: str | None,
    version: int | None,
) -> None:
    """Retire de Qdrant et pose les drapeaux d'obsolescence."""
    maintenant = datetime.now(timezone.utc)

    for r in reponses:
        delete_response_point(str(r.id))
        r.obsolete = True
        r.obsolete_raison = raison
        r.obsolete_doc_id = doc_id
        r.obsolete_version = version
        r.obsolete_at = maintenant
        # obsolescence tranche la question que la relecture posait — le signal n'a plus lieu d'être
        lever_a_relire(r)

    db.commit()


def lever_a_relire(r: Reponse) -> None:
    """Efface les colonnes de relecture et la suggestion LLM. Ne touche pas à analyse_justification/analyse_extraits"""
    r.a_relire = False
    r.a_relire_raison = None
    r.a_relire_doc_id = None
    r.a_relire_version = None
    r.a_relire_at = None
    r.correction_suggeree = None
    r.passages_pertinents = None


def poser_a_relire(reponses: list[Reponse], raison: str, doc_id: str, version: int) -> None:
    """Pose le drapeau de relecture, sans commit ni Qdrant. La réponse reste servie."""
    maintenant = datetime.now(timezone.utc)
    for r in reponses:
        r.a_relire = True
        r.a_relire_raison = raison
        r.a_relire_doc_id = doc_id
        r.a_relire_version = version
        r.a_relire_at = maintenant


def marquer_a_relire(
    db: Session,
    doc_id: str,
    version: int,
    raison: str = RAISON_MODIF,
) -> list[Reponse]:
    """Signale en bloc toutes les réponses encore servies du document. Flague la famille entière (pas seulement les"""
    reponses = reponses_obsoletes(db, doc_id, indices=None)
    poser_a_relire(reponses, raison, doc_id, version)
    db.commit()
    return reponses


def mettre_en_analyse(reponses: list[Reponse], doc_id: str, version: int) -> None:
    """Pose ANALYSE_EN_COURS, sans commit. Never over a flag already raised: it would take that flag's doc/version,
    and this pass's INTACTE would then lift a signal it never judged — a CONTREDITE_PROBABLE from another document
    went back to unreviewed serving that way. An already-flagged response is not served unreviewed anyway."""
    poser_a_relire([r for r in reponses if not r.a_relire], RAISON_ANALYSE, doc_id, version)


def flaguer_en_analyse(db: Session, doc_id: str, version: int) -> list[Reponse]:
    """Met sous analyse les réponses citant le document et les renvoie toutes (déjà signalées comprises — elles
    seront jugées aussi). Sans commit : posé dans la transaction même de la bascule de version."""
    reponses = reponses_obsoletes(db, doc_id, indices=None)
    mettre_en_analyse(reponses, doc_id, version)
    return reponses


def confirmer_actualite(db: Session, reponses: list[Reponse]) -> None:
    """Lève le signalement : un humain a relu et jugé la réponse toujours juste."""
    for r in reponses:
        lever_a_relire(r)
    db.commit()


def retirer_et_requeuer(
    db: Session,
    reponses: list[Reponse],
    raison: str,
    doc_id: str | None,
    version: int | None,
) -> None:
    """Retire une famille et renvoie au pipeline ses brouillons EN_ATTENTE. Sans le renvoi, la copie SUGGESTION
    en attente devient obsolète, disparaît du fil (detail.py masque les obsolètes non validées) et le ticket reste
    RÉPONDU sans réponse visible."""
    en_attente = [r for r in reponses if r.statut == "EN_ATTENTE" and not r.obsolete]
    retirer_du_service(db, reponses, raison, doc_id, version)
    requeuer_en_attente(db, en_attente)


def requeuer_en_attente(db: Session, reponses: list[Reponse]) -> None:
    """Re-soumet au pipeline chaque réponse EN_ATTENTE rendue obsolète, sous SA question : une précision repart en
    mode suivi (nouvelle réponse, contexte du fil) — la re-soumettre sous la question initiale écrasait la réponse
    initiale du ticket. Import différé anti-circulaire."""
    if not reponses:
        return

    from app.workers.question import question_job  # noqa: PLC0415 — import différé anti-circulaire

    questions_par_ticket: dict[uuid.UUID, set[str | None]] = {}
    for r in reponses:
        if r.ticket_id is not None:
            questions_par_ticket.setdefault(r.ticket_id, set()).add(r.question_suivi)
    if not questions_par_ticket:
        return

    tickets = db.query(Ticket).filter(Ticket.id.in_(questions_par_ticket)).all()
    for ticket in tickets:
        ticket.statut_job = "EN_ATTENTE"
        ticket.statut_ticket = "NOUVEAU"
        ticket.erreur = None
    db.commit()

    for ticket in tickets:
        for question_suivi in questions_par_ticket[ticket.id]:
            question_job.delay(
                question=question_suivi or ticket.question,
                domaine=ticket.domaine,
                user_id=str(ticket.user_id) if ticket.user_id else None,
                ticket_id=str(ticket.id),
                objet=ticket.objet,
                retraiter=question_suivi is None,
            )
            logging.getLogger(__name__).info("Ticket %s re-soumis au pipeline RAG", ticket.id)
