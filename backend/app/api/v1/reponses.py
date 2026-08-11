import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.permissions import check_domain_write, user_domaines
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.schemas.reponse import (
    ConfirmerLotRequest,
    CorrigerRequest,
    EditerCanoniqueRequest,
    RejeterRequest,
)
from app.services.broadcast import broadcast_async
from app.services.obsolescence import (
    RAISON_MANUELLE,
    confirmer_actualite,
    fermeture_copies,
    lever_a_relire,
    retirer_du_service,
)
from app.services.qdrant import delete_response_point
from app.workers.feedback import feedback_job

router = APIRouter()


def _notifier_employe(db, ticket: Ticket, reponse_id: str, validator_id: uuid.UUID) -> None:
    """Crée une notification pour l'employé propriétaire du ticket, sauf auto-validation."""
    if not ticket or not ticket.user_id:
        return
    if ticket.user_id == validator_id:
        return
    db.add(Notification(
        user_id=ticket.user_id,
        ticket_id=ticket.id,
        reponse_id=uuid.UUID(reponse_id),
        type="REPONSE_VALIDEE",
    ))

ETATS_FINAUX = {"REJETÉE", "CORRIGÉE", "CANONIQUE"}


def get_reponse_or_404(db, reponse_id: str) -> Reponse:
    reponse = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not reponse:
        raise HTTPException(404, f"Réponse {reponse_id} introuvable")
    return reponse


def check_reponse_write(db, reponse: Reponse, current_user) -> None:
    """Droit d'agir sur une réponse enregistrée : le domaine du ticket qui l'a produite.

    Même règle que la mise à jour d'un document. Les séparer reviendrait à dire
    qu'un validateur peut périmer une réponse en remplaçant le document dont elle
    découle, mais pas la corriger directement — alors que c'est la même matière,
    et que l'écran d'impact d'une mise à jour lui demande précisément d'aller les
    relire.

    ``check_domain_write`` n'exempte pas l'admin : lui aussi doit être membre du
    domaine. C'est la règle déjà appliquée à ``restaurer_reponse`` et à la mise à
    jour de document.

    Réponse orpheline (ticket disparu) : refusée à tout le monde, admin compris.
    Sans ticket, il n'y a aucun domaine à confronter — accorder le droit à l'admin
    reviendrait à rouvrir par la petite porte l'exception que cette règle refuse.
    Aucune route ne supprime de ticket : la branche est défensive.
    """
    ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
    if ticket is None:
        raise HTTPException(409, "Réponse sans ticket : aucun domaine ne s'y rattache.")
    check_domain_write(ticket.domaine, current_user)


def verifier_etat_initial(reponse: Reponse):
    if reponse.statut in ETATS_FINAUX:
        raise HTTPException(
            409,
            f"Réponse déjà traitée (statut={reponse.statut}). Seules les réponses EN_ATTENTE peuvent être traitées.",
        )


def verifier_auto_validation(reponse: Reponse, validator_id: uuid.UUID, ticket: Ticket):
    if ticket and ticket.user_id and ticket.user_id == validator_id:
        raise HTTPException(403, "Un validateur ne peut pas traiter ses propres tickets.")


def verifier_verrou(ticket: Ticket, validator_id: uuid.UUID):
    """Refuse l'écriture si le ticket est assigné à quelqu'un d'autre,
    ou verrouillé par un autre validateur (bail encore actif)."""
    if not ticket:
        return
    if ticket.assigned_to and ticket.assigned_to != validator_id:
        raise HTTPException(403, "Ce ticket est assigné à un autre validateur.")
    now = datetime.now(timezone.utc)
    if (
        ticket.locked_by
        and ticket.locked_by != validator_id
        and ticket.lock_expires_at
        and ticket.lock_expires_at > now
    ):
        raise HTTPException(409, "Ticket verrouillé par un autre validateur.")


def liberer_verrou(ticket: Ticket):
    """Libère le verrou après une transition terminale du ticket."""
    if ticket:
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None


@router.post("/reponses/{reponse_id}/valider")
async def valider_reponse(reponse_id: str, current_user: BackofficeUser):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → VALIDÉE
        reponse.statut = "VALIDÉE"
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        reponse_source = None

        # Increment the number of validations
        if reponse.reponse_source_id:
            # Incrémenter sur la réponse SOURCE, pas sur la réponse courante
            reponse_source = db.query(Reponse).filter(Reponse.id == reponse.reponse_source_id).first()
            if reponse_source:
                reponse_source.nb_validations += 1
                if reponse_source.nb_validations >= settings.seuil_canonique:
                    reponse_source.canonique = True
        else:
            # Pas de source → c'est une réponse LLM originale
            reponse.nb_validations += 1
            if reponse.nb_validations >= settings.seuil_canonique:
                reponse.canonique = True

        _notifier_employe(db, ticket, reponse_id, current_user.id)
        db.commit()

        # Feedback job : réindexe la réponse validée dans Qdrant dès la 1re validation
        # (et pas seulement une fois canonique) pour qu'elle soit retrouvable comme
        # SUGGESTION sur des questions similaires. Réindexe la réponse SOURCE si la
        # réponse courante est une copie de suggestion, sinon la réponse elle-même.
        if reponse.reponse_source_id and reponse_source:
            feedback_job.apply_async(args=[str(reponse_source.id)], queue="queue_ingestion")
        elif not reponse.reponse_source_id:
            feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")

        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        user_id = str(ticket.user_id) if ticket and ticket.user_id else None
        result = {
            "reponse_id": reponse_id,
            "statut": "VALIDÉE",
            "nb_validations": reponse.nb_validations,
            "canonique": reponse.canonique,
            "validated_at": reponse.validated_at.isoformat(),
            "message": ("Réponse validée et indexée comme canonique." if reponse.canonique else "Réponse validée."),
        }
    finally:
        db.close()

    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_validated", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    if user_id:
        await broadcast_async(f"sse:user:{user_id}", "notification_created", {"ticket_id": ticket_id_str})
    return result


@router.post("/reponses/{reponse_id}/rejeter")
async def rejeter_reponse(
    reponse_id: str,
    payload: RejeterRequest,
    current_user: BackofficeUser,
):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → REJETÉE
        reponse.statut = "REJETÉE"
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "REJETÉ"
            liberer_verrou(ticket)

        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        db.commit()
    finally:
        db.close()

    print(f"[VALIDATION] ❌ Réponse {reponse_id} rejetée par {current_user.id}")
    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_rejected", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    return {
        "reponse_id": reponse_id,
        "statut": "REJETÉE",
        "raison": payload.raison,
        "message": "Réponse rejetée.",
    }


@router.put("/reponses/{reponse_id}/corriger")
async def corriger_reponse(
    reponse_id: str,
    payload: CorrigerRequest,
    current_user: BackofficeUser,
):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        if not payload.contenu_corrige.strip():
            raise HTTPException(400, "Le contenu corrigé ne peut pas être vide.")

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → CORRIGÉE
        reponse.statut = "CORRIGÉE"
        reponse.contenu_corrige = payload.contenu_corrige
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        # `reponses_obsoletes` ne retient que les VALIDÉE : une réponse signalée
        # puis corrigée sortirait du périmètre en gardant son drapeau, et
        # occuperait l'onglet À relire sans qu'aucune action ne l'en déloge.
        if reponse.a_relire:
            lever_a_relire(reponse)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        _notifier_employe(db, ticket, reponse_id, current_user.id)
        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        user_id = str(ticket.user_id) if ticket and ticket.user_id else None
        db.commit()
    finally:
        db.close()

    print(f"[CORRECTION] ✏️  Réponse {reponse_id} corrigée et en cours d'indexation dans Qdrant.")
    feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")
    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_corrected", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    if user_id:
        await broadcast_async(f"sse:user:{user_id}", "notification_created", {"ticket_id": ticket_id_str})
    return {
        "reponse_id": reponse_id,
        "statut": "CORRIGÉE",
        "contenu_corrige": payload.contenu_corrige,
        "message": "Réponse corrigée.",
    }


@router.get("/reponses/en-attente")
async def lister_reponses_en_attente(
    current_user: BackofficeUser,
    domaine: str | None = None,
    limit: int = 20,
):
    """Liste les réponses en attente de validation — utile pour l'interface back-office."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.statut == "EN_ATTENTE")
        )

        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        elif current_user.role != "ADMIN":
            # Backoffice : limité à ses domaines
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
    page: int = 1,
    limit: int = 20,
):
    """Liste paginée des réponses canoniques — une entrée par réponse canonique.

    On ne retourne que les réponses **sources** (`reponse_source_id IS NULL`) : chaque
    question ré-servie via la branche CANONIQUE crée une copie (`canonique=True` mais
    `reponse_source_id` renseigné) qu'il ne faut pas afficher, sinon la même réponse
    apparaîtrait autant de fois qu'elle a été réutilisée. `Ticket.occurence` porte le
    nombre de réutilisations. Sert la page de gestion « Réponses Enregistrées »."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.canonique.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
            # Les obsolètes ont leur propre onglet : les laisser ici les ferait
            # passer pour actives alors qu'elles ne sont plus servies.
            .filter(Reponse.obsolete.is_(False))
        )

        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        elif current_user.role != "ADMIN":
            # Backoffice : limité à ses domaines
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

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
                    # Une réponse issue d'un tour de suivi porte sa propre question
                    # (la précision) : on l'affiche à la place de la question initiale
                    # du ticket, cohérent avec ce qui est indexé dans Qdrant.
                    "question": r.question_suivi or t.question,
                    "domaine": t.domaine,
                    "contenu": r.contenu,
                    "contenu_corrige": r.contenu_corrige,
                    "nb_validations": r.nb_validations,
                    "occurence": t.occurence,
                    # Une réponse signalée continue d'être servie : elle siège donc
                    # ici, et pas seulement dans l'onglet « À relire ». Sans cette
                    # pastille, cet écran la présenterait comme acquise alors qu'un
                    # humain doit encore trancher.
                    "a_relire": r.a_relire,
                    "validated_at": r.validated_at.isoformat() if r.validated_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
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
    page: int = 1,
    limit: int = 20,
):
    """Liste paginée des réponses retirées du service par un changement de document.

    Comme pour les canoniques, seules les **sources** sont listées : afficher aussi
    les copies montrerait la même réponse autant de fois qu'elle a été réutilisée.
    Pas de filtre sur `canonique` en revanche — une VALIDÉE pas encore promue peut
    devenir obsolète et doit rester visible pour être restaurée.

    Jointure **externe** sur `documents` : le document déclencheur peut lui-même
    avoir été supprimé, la réponse doit rester listée.
    """
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket, Document)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .outerjoin(Document, Document.doc_id == Reponse.obsolete_doc_id)
            .filter(Reponse.obsolete.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
        )

        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        total = query.count()
        resultats = (
            query.order_by(Reponse.obsolete_at.desc().nullslast()).offset((page - 1) * limit).limit(limit).all()
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
                    "canonique": r.canonique,
                    "obsolete_raison": r.obsolete_raison,
                    "obsolete_version": r.obsolete_version,
                    "obsolete_at": r.obsolete_at.isoformat() if r.obsolete_at else None,
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
    page: int = 1,
    limit: int = 20,
):
    """Réponses toujours servies dont le document source a changé de contenu.

    Ce que l'onglet Obsolètes ne peut pas dire : la détection verbatim ne voit
    que les passages *cités* par une réponse. Un article ajouté ailleurs dans la
    charte peut la contredire sans qu'aucun de ces passages bouge — personne
    n'est prévenu et la branche CANONIQUE continue de servir. Cette liste est le
    filet : elle ne décide rien, elle demande une relecture.

    Deux jointures externes : `documents` pour le nom (le document a pu être
    supprimé depuis) et `document_versions` sur **(doc_id, version)** pour
    remonter `changements` — sans les extraits de ce qui a changé, « cette
    réponse est liée à Charte_RH v3 » ne permet de juger de rien.

    Comme les autres onglets, seules les **sources** sont listées.
    """
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
            query = query.filter(Ticket.domaine == domaine.upper())
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        total = query.count()
        # Groupé par document dans l'interface : trier d'abord par document garde
        # les membres d'un même groupe sur la même page.
        resultats = (
            query.order_by(
                Reponse.a_relire_doc_id,
                Reponse.a_relire_at.desc().nullslast(),
            )
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        # Le compteur de la sidebar compte les **documents**, pas les réponses :
        # « 2 documents à relire » se traite, « 39 réponses » se subit. Compté sur
        # toute la requête et non sur la page.
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
                    "doc_id": r.a_relire_doc_id,
                    "document_filename": d.filename if d else None,
                    "document_supprime": d is None or d.statut == "SUPPRIMÉ",
                    "changements": v.changements if v else None,
                }
                for r, t, d, v in resultats
            ],
        }
    finally:
        db.close()


@router.post("/reponses/confirmer-actualite")
async def confirmer_actualite_lot(payload: ConfirmerLotRequest, current_user: BackofficeUser):
    """Confirme en lot toutes les réponses signalées par une version de document.

    La sortie normale quand une phrase réécrite dans une charte très exploitée en
    signale trente-neuf : on lit le diff une fois, on juge les trente-neuf
    ensuite. Sans elle, la liste serait techniquement correcte et pratiquement
    abandonnée dès la première mise à jour d'ampleur.

    Le domaine est vérifié réponse par réponse : un lot mélangeant deux domaines
    (le même document peut avoir servi à des tickets de domaines différents) ne
    confirme que ce qui relève de l'appelant, sans échouer sur le reste.
    """
    db = SessionLocal()
    try:
        candidates = (
            db.query(Reponse)
            .filter(
                Reponse.a_relire.is_(True),
                Reponse.a_relire_doc_id == payload.doc_id,
                Reponse.a_relire_version == payload.version,
            )
            .all()
        )

        autorisees = [r for r in candidates if _domaine_autorise(db, r, current_user)]
        familles = fermeture_copies(db, {r.id for r in autorisees}) if autorisees else set()
        a_lever = (
            db.query(Reponse).filter(Reponse.id.in_(familles)).all() if familles else []
        )
        confirmer_actualite(db, a_lever)
        nb = len(autorisees)
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"doc_id": payload.doc_id})
    return {
        "doc_id": payload.doc_id,
        "version": payload.version,
        "nb_confirmees": nb,
        "message": f"{nb} réponse(s) confirmée(s) comme toujours d'actualité.",
    }


def _domaine_autorise(db, reponse: Reponse, current_user) -> bool:
    """`check_reponse_write` en forme booléenne, pour les traitements en lot."""
    try:
        check_reponse_write(db, reponse, current_user)
    except HTTPException:
        return False
    return True


@router.post("/reponses/{reponse_id}/confirmer-actualite")
async def confirmer_actualite_reponse(reponse_id: str, current_user: BackofficeUser):
    """Un humain a relu et juge la réponse toujours juste : le signalement tombe.

    Rien d'autre ne change — la réponse n'a jamais cessé d'être servie, c'est la
    différence avec l'obsolescence. Le drapeau est levé sur toute la famille,
    comme il y avait été posé.
    """
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.a_relire:
            raise HTTPException(409, "Cette réponse n'est pas signalée à relire.")

        famille = fermeture_copies(db, {reponse.id})
        confirmer_actualite(db, db.query(Reponse).filter(Reponse.id.in_(famille)).all())
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "message": "Réponse confirmée comme toujours d'actualité.",
    }


@router.post("/reponses/{reponse_id}/retirer")
async def retirer_reponse(reponse_id: str, current_user: BackofficeUser):
    """Retire du service une réponse relue et jugée dépassée.

    Troisième issue du signalement, entre « toujours d'actualité » et « je la
    réécris » : la réponse n'a plus lieu d'être mais mérite de rester
    consultable. Elle bascule dans l'onglet Obsolètes, d'où elle reste
    restaurable.

    Le `doc_id`/`version` du signalement est repris comme origine de
    l'obsolescence : sans lui, l'onglet Obsolètes afficherait « document
    supprimé » (jointure externe sans correspondance) pour une réponse retirée à
    la main sur un document bien vivant.
    """
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.a_relire:
            raise HTTPException(409, "Cette réponse n'est pas signalée à relire.")

        doc_id, version = reponse.a_relire_doc_id, reponse.a_relire_version
        famille = fermeture_copies(db, {reponse.id})
        cibles = db.query(Reponse).filter(Reponse.id.in_(famille), Reponse.obsolete.is_(False)).all()
        retirer_du_service(db, cibles, RAISON_MANUELLE, doc_id, version)
        nb = len(cibles)
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "nb_retirees": nb,
        "message": "Réponse retirée du service. Elle reste restaurable depuis l'onglet Obsolètes.",
    }


@router.post("/reponses/{reponse_id}/restaurer")
async def restaurer_reponse(reponse_id: str, current_user: BackofficeUser):
    """Remet en service une réponse déclarée obsolète.

    Soupape de la détection verbatim : une reformulation cosmétique du document
    périme une réponse dont le fond n'a pas bougé ; le validateur le constate et
    la restaure en un clic.

    Le drapeau est levé sur toute la famille (source + copies transitives) et
    chacune est réindexée — symétrique de `marquer_obsoletes`, qui avait retiré
    les points de la famille entière. Réindexer une copie qui n'avait pas de point
    est sans conséquence : le lookup regroupe par `reponse_id` et privilégie de
    façon déterministe la source (plus validée) ; à l'inverse, un point manquant
    laisserait la question sans réponse servie.
    """
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        if not reponse.obsolete:
            raise HTTPException(409, "Cette réponse n'est pas obsolète.")

        check_reponse_write(db, reponse, current_user)

        famille = fermeture_copies(db, {reponse.id})
        a_reindexer = [
            str(r[0])
            for r in db.query(Reponse.id).filter(Reponse.id.in_(famille), Reponse.obsolete.is_(True)).all()
        ]
        db.query(Reponse).filter(Reponse.id.in_(famille)).update(
            {
                "obsolete": False,
                "obsolete_raison": None,
                "obsolete_doc_id": None,
                "obsolete_version": None,
                "obsolete_at": None,
                # Restaurer *est* le jugement humain que le signalement réclamait :
                # le reposer renverrait aussitôt la réponse dans l'onglet À relire.
                "a_relire": False,
                "a_relire_raison": None,
                "a_relire_doc_id": None,
                "a_relire_version": None,
                "a_relire_at": None,
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    for rid in a_reindexer:
        feedback_job.apply_async(args=[rid], queue="queue_ingestion")

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "nb_restaurees": len(a_reindexer),
        "message": "Réponse restaurée et en cours de réindexation.",
    }


@router.put("/reponses/{reponse_id}/editer")
async def editer_reponse_canonique(
    reponse_id: str,
    payload: EditerCanoniqueRequest,
    current_user: BackofficeUser,
):
    """Édite le contenu servi d'une réponse canonique puis la réindexe dans Qdrant,
    afin que les futures questions renvoient le nouveau texte. Le nouveau contenu est
    stocké dans `contenu_corrige` (champ privilégié par le feedback_job).

    Ouvert au back-office ayant le domaine, et non au seul admin : c'est la voie de
    sortie de l'avertissement « passages ajoutés » de l'écran d'impact, qui s'adresse
    à celui qui met le document à jour."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        # Une VALIDÉE pas encore promue peut être signalée à relire : « corriger »
        # est l'une des trois issues qu'on lui propose, la refuser ici ne
        # laisserait que confirmer ou retirer.
        if not reponse.canonique and not reponse.a_relire:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être éditées ici.")

        if not payload.contenu.strip():
            raise HTTPException(400, "Le contenu ne peut pas être vide.")

        reponse.contenu_corrige = payload.contenu
        # Réécrire la réponse *est* la relecture qu'on demandait.
        if reponse.a_relire:
            confirmer_actualite(db, db.query(Reponse).filter(
                Reponse.id.in_(fermeture_copies(db, {reponse.id}))
            ).all())
        db.commit()
    finally:
        db.close()

    feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")
    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "contenu_corrige": payload.contenu,
        "message": "Réponse canonique éditée et en cours de réindexation.",
    }


@router.delete("/reponses/{reponse_id}")
async def supprimer_reponse_canonique(reponse_id: str, current_user: BackofficeUser):
    """Supprime définitivement une réponse canonique : retrait du point Qdrant et de
    la ligne en base. Les futures questions similaires repassent par le pipeline RAG
    normal. Aucune cascade n'étant déclarée sur les FK, on nettoie manuellement les
    chunks liés et on détache les copies (réutilisations CANONIQUE) avant la suppression.

    Même droit que l'édition : le domaine du ticket d'origine (`check_reponse_write`)."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        # Une réponse devenue obsolète a pu ne jamais être canonique : l'onglet
        # Obsolètes doit tout de même permettre de la purger définitivement.
        if not reponse.canonique and not reponse.obsolete:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être supprimées ici.")

        # 1. Retrait du point Qdrant (plus de match CANONIQUE/SUGGESTION).
        delete_response_point(reponse_id)

        # 2. Chunks liés (pas de cascade en base).
        db.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse.id).delete(synchronize_session=False)

        # 3. Détacher les copies (réutilisations) qui pointent sur cette source.
        #    On retire aussi leur flag `canonique` : sinon, une fois orphelines
        #    (reponse_source_id NULL), elles réapparaîtraient comme des sources
        #    dans la liste des réponses canoniques. Même raison pour le drapeau
        #    d'obsolescence et pour celui de relecture, qui les feraient rester
        #    éternellement dans leur onglet sans que rien ne puisse plus les en
        #    sortir : les deux listes ne montrent que les sources.
        db.query(Reponse).filter(Reponse.reponse_source_id == reponse.id).update(
            {
                "reponse_source_id": None,
                "canonique": False,
                "obsolete": False,
                "obsolete_raison": None,
                "obsolete_doc_id": None,
                "obsolete_version": None,
                "obsolete_at": None,
                "a_relire": False,
                "a_relire_raison": None,
                "a_relire_doc_id": None,
                "a_relire_version": None,
                "a_relire_at": None,
            },
            synchronize_session=False,
        )

        # 4. Suppression de la réponse elle-même.
        db.delete(reponse)
        db.commit()
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "message": "Réponse canonique supprimée.",
    }
