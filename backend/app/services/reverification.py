"""Verdicts for existing responses against a document update. Funnel: diff → candidates → reranker → LLM. False"""

from app.models.reponse import Reponse
from app.services.obsolescence import (
    RAISON_CONTREDITE,
    RAISON_CONTREDITE_PROB,
    RAISON_MODIF,
    fermeture_copies,
    lever_a_relire,
    poser_a_relire,
    retirer_et_requeuer,
    serialiser_unites,
)
from app.services.reverification_candidates import (  # noqa: F401
    Candidate,
    passages_actuels,
    questions_des_reponses,
    rassembler_candidates,
)
from app.services.reverification_scoring import (  # noqa: F401
    MAX_UNITES_PAR_REPONSE,
    SEUIL_RERANK,
    VERDICT_CONTREDITE,
    VERDICT_INCERTAIN,
    VERDICT_INTACTE,
    VERDICTS,
    juger,
    juger_confrontation,
    unites_pertinentes,
)
from sqlalchemy.orm import Session

__all__ = [
    "MAX_UNITES",
    "MAX_JUGEMENTS",
    "MAX_UNITES_PAR_REPONSE",
    "SEUIL_RERANK",
    "VERDICT_CONTREDITE",
    "VERDICT_INTACTE",
    "VERDICT_INCERTAIN",
    "VERDICTS",
    "ACTION_RETIREE",
    "ACTION_A_RELIRE",
    "ACTION_INTACTE",
    "Candidate",
    "rassembler_candidates",
    "questions_des_reponses",
    "unites_pertinentes",
    "juger",
    "juger_confrontation",
    "passages_actuels",
    "decider",
    "signaler_sans_juger",
    "tracer",
]

# Above this, the document was rewritten not modified — no model call would discriminate; go straight to human review.
MAX_UNITES = 40

# LLM call budget per update. Surplus goes to human review with its own reason — truncation is never silent.
MAX_JUGEMENTS = 25

ACTION_RETIREE = "retiree"
ACTION_A_RELIRE = "a_relire"
ACTION_INTACTE = "intacte"


def decider(
    db: Session,
    candidate: Candidate,
    verdict: str,
    justification: str,
    unites: list,
    doc_id: str,
    version: int,
    raison_incertain: str = RAISON_MODIF,
) -> str:
    """Apply the verdict. Non-citing response can never be auto-withdrawn — vector similarity ≠ citation"""
    famille = _famille(db, candidate.reponse)
    extraits = serialiser_unites(unites)["unites"]

    if verdict == VERDICT_CONTREDITE and candidate.citante:
        retirer_et_requeuer(db, famille, RAISON_CONTREDITE, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_RETIREE

    if verdict == VERDICT_CONTREDITE:
        poser_a_relire(famille, RAISON_CONTREDITE_PROB, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_A_RELIRE

    if verdict == VERDICT_INTACTE:
        for r in famille:
            # lift only the flag raised by this exact pass: doc_id AND version — another pass's signal waits for a
            if r.a_relire_doc_id == doc_id and r.a_relire_version == version:
                lever_a_relire(r)
                r.analyse_justification = None
                r.analyse_extraits = None
        db.commit()
        return ACTION_INTACTE

    poser_a_relire(famille, raison_incertain, doc_id, version)
    tracer(db, famille, justification, extraits)
    return ACTION_A_RELIRE


def signaler_sans_juger(
    db: Session,
    candidates: list[Candidate],
    raison: str,
    justification: str,
    doc_id: str,
    version: int,
) -> int:
    """Send unjudged responses to human review with an explicit reason. Budget exhausted, document rewritten, or"""
    for candidate in candidates:
        famille = _famille(db, candidate.reponse)
        poser_a_relire(famille, raison, doc_id, version)
        tracer(db, famille, justification, None)
    db.commit()
    return len(candidates)


def _famille(db: Session, reponse: Reponse) -> list[Reponse]:
    """Response and all active copies. Copies don't cite chunks — they'd stay indexed if only the root was decided."""
    return db.query(Reponse).filter(Reponse.id.in_(fermeture_copies(db, {reponse.id}))).all()


def tracer(db: Session, reponses: list[Reponse], justification: str, extraits: list[dict] | None) -> None:
    for r in reponses:
        r.analyse_justification = justification or None
        r.analyse_extraits = {"unites": extraits} if extraits else None
    db.commit()
