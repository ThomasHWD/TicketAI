from fastapi import APIRouter

from app.core.permissions import user_domaines
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.reponse_service import changements_allegees

router = APIRouter()


@router.get("/reponses/en-attente")
async def lister_reponses_en_attente(
    current_user: BackofficeUser,
    domaine: str | None = None,
    limit: int = 20,
):
    """Liste les réponses en attente de validation."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.statut == "EN_ATTENTE")
        )

        if domaine:
            d = domaine.upper()
            if current_user.role != "ADMIN" and d not in user_domaines(current_user):
                return []
            query = query.filter(Ticket.domaine == d)
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        resultats = query.order_by(Reponse.created_at.asc()).limit(limit).all()

        return [
            {
                "reponse_id": str(r.id),
                "ticket_id": str(r.ticket_id),
                "question": t.question,
                "domaine": t.domaine,
                "reponse": r.contenu,
                "source": r.source,
                "score_similarite": r.score_similarite,
                "created_at": r.created_at.isoformat(),
            }
            for r, t in resultats
        ]
    finally:
        db.close()


@router.get("/reponses/canoniques")
async def lister_reponses_canoniques(
    current_user: BackofficeUser,
    domaine: str | None = None,
    q: str | None = None,
    tag: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Liste paginée des réponses canoniques — seules les sources."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.canonique.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
            .filter(Reponse.obsolete.is_(False))
        )

        if domaine:
            d = domaine.upper()
            if current_user.role != "ADMIN" and d not in user_domaines(current_user):
                return {"total": 0, "page": page, "limit": limit, "items": []}
            query = query.filter(Ticket.domaine == d)
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        if q:
            terme = f"%{q}%"
            query = query.filter(
                Ticket.question.ilike(terme) | Reponse.question_suivi.ilike(terme)
            )

        if tag:
            query = query.filter(Reponse.tag == tag)

        total = query.count()
        resultats = (
            query.order_by(Reponse.validated_at.desc().nullslast()).offset((page - 1) * limit).limit(limit).all()
        )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "reponse_id": str(r.id),
                    "ticket_id": str(r.ticket_id),
                    "question": r.question_suivi or t.question,
                    "domaine": t.domaine,
                    "contenu": r.contenu,
                    "contenu_corrige": r.contenu_corrige,
                    "nb_validations": r.nb_validations,
                    "occurence": t.occurence,
                    "a_relire": r.a_relire,
                    "validated_at": r.validated_at.isoformat() if r.validated_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "tag": r.tag,
                }
                for r, t in resultats
            ],
        }
    finally:
        db.close()


@router.get("/reponses/obsoletes")
async def lister_reponses_obsoletes(
    current_user: BackofficeUser,
    domaine: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Liste paginée des réponses retirées du service."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket, Document)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .outerjoin(Document, Document.doc_id == Reponse.obsolete_doc_id)
            .filter(Reponse.obsolete.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
            .filter(Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]))
        )

        if domaine:
            d = domaine.upper()
            if current_user.role != "ADMIN" and d not in user_domaines(current_user):
                return {"total": 0, "page": page, "limit": limit, "items": []}
            query = query.filter(Ticket.domaine == d)
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        if q:
            terme = f"%{q}%"
            query = query.filter(
                Ticket.question.ilike(terme) | Reponse.question_suivi.ilike(terme)
            )

        total = query.count()
        resultats = query.order_by(Reponse.obsolete_at.desc().nullslast()).offset((page - 1) * limit).limit(limit).all()

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "reponse_id": str(r.id),
                    "ticket_id": str(r.ticket_id),
                    "question": r.question_suivi or t.question,
                    "domaine": t.domaine,
                    "contenu": r.contenu,
                    "contenu_corrige": r.contenu_corrige,
                    "nb_validations": r.nb_validations,
                    "canonique": r.canonique,
                    "obsolete_raison": r.obsolete_raison,
                    "obsolete_version": r.obsolete_version,
                    "obsolete_at": r.obsolete_at.isoformat() if r.obsolete_at else None,
                    "analyse_justification": r.analyse_justification,
                    "analyse_extraits": (r.analyse_extraits or {}).get("unites") or [],
                    "doc_id": r.obsolete_doc_id,
                    "document_filename": d.filename if d else None,
                    "document_supprime": d is None or d.statut == "SUPPRIMÉ",
                }
                for r, t, d in resultats
            ],
        }
    finally:
        db.close()


@router.get("/reponses/a-relire")
async def lister_reponses_a_relire(
    current_user: BackofficeUser,
    domaine: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Réponses toujours servies dont le document source a changé de contenu."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket, Document, DocumentVersion)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .outerjoin(Document, Document.doc_id == Reponse.a_relire_doc_id)
            .outerjoin(
                DocumentVersion,
                (DocumentVersion.doc_id == Reponse.a_relire_doc_id)
                & (DocumentVersion.version == Reponse.a_relire_version),
            )
            .filter(Reponse.a_relire.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
        )

        if domaine:
            d = domaine.upper()
            if current_user.role != "ADMIN" and d not in user_domaines(current_user):
                return {"total": 0, "nb_documents": 0, "page": page, "limit": limit, "items": []}
            query = query.filter(Ticket.domaine == d)
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        if q:
            terme = f"%{q}%"
            query = query.filter(
                Ticket.question.ilike(terme) | Reponse.question_suivi.ilike(terme)
            )

        total = query.count()
        resultats = (
            query.order_by(
                Reponse.a_relire_doc_id,
                Reponse.a_relire_at.desc().nullslast(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        nb_documents = query.with_entities(Reponse.a_relire_doc_id).distinct().count()

        return {
            "total": total,
            "nb_documents": nb_documents,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "reponse_id": str(r.id),
                    "ticket_id": str(r.ticket_id),
                    "question": r.question_suivi or t.question,
                    "domaine": t.domaine,
                    "contenu": r.contenu,
                    "contenu_corrige": r.contenu_corrige,
                    "correction_suggeree": r.correction_suggeree,
                    "passages_pertinents_ajoutes": (r.passages_pertinents or {}).get("ajoutes", []),
                    "passages_pertinents_retires": (r.passages_pertinents or {}).get("retires", []),
                    "nb_validations": r.nb_validations,
                    "canonique": r.canonique,
                    "a_relire_raison": r.a_relire_raison,
                    "a_relire_version": r.a_relire_version,
                    "a_relire_at": r.a_relire_at.isoformat() if r.a_relire_at else None,
                    "analyse_justification": r.analyse_justification,
                    "analyse_extraits": (r.analyse_extraits or {}).get("unites") or [],
                    "doc_id": r.a_relire_doc_id,
                    "document_filename": d.filename if d else None,
                    "document_supprime": d is None or d.statut == "SUPPRIMÉ",
                    "changements": changements_allegees(v.changements if v else None),
                }
                for r, t, d, v in resultats
            ],
        }
    finally:
        db.close()
