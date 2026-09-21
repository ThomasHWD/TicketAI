"""Gestion du cycle de vie des réponses rendues obsolètes par un changement de document.

**La comparaison est document ↔ document : le texte de la réponse n'y participe
jamais.** Le LLM reformule (« 2 jours » devient « deux jours hebdomadaires ») ;
chercher ses phrases dans le document n'aurait aucun sens. Ce qu'on exploite,
c'est que ``reponse_chunks`` mémorise *quels passages* ont servi, et que Qdrant
conserve leur texte brut dans le payload : il suffit de vérifier si ces passages
figurent encore dans la nouvelle version.

La logique de diff textuel (``Unite``, ``unites_de_changement``, etc.) vit dans
``services/diff.py``. Ce module s'occupe uniquement du cycle de vie : marquer
obsolètes, signaler à relire, lever les drapeaux.
"""

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

# Confrontation à l'ingestion (cf. `services/confrontation.py`). Distinct de
# `RAISON_MODIF` parce que le document n'a pas été modifié : il vient d'arriver.
# Le relecteur n'a donc pas de version précédente à consulter, et le dire évite
# qu'il cherche un diff qui n'existe pas.
RAISON_NOUVEAU_DOC = "NOUVEAU_DOC"  # a_relire_raison, verdict INCERTAIN à l'ingestion


def fermeture_copies(db: Session, graines: set[uuid.UUID]) -> set[uuid.UUID]:
    """Descend des réponses-graines vers toutes leurs copies, transitivement.

    ``reponse_chunks`` n'est peuplé que sur la branche RAG : les copies
    SUGGESTION/CANONIQUE ne citent aucun chunk et ne se rattachent à leur origine
    que par ``reponse_source_id``. Et comme ``corriger_reponse`` réindexe la
    *copie* dans Qdrant, une copie peut à son tour être source — d'où la descente
    transitive. L'ensemble des visités garantit la terminaison même sur un cycle
    (``A.source = B`` et ``B.source = A``).
    """
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
) -> list[Reponse]:
    """Réponses indexées dans Qdrant qui s'appuient sur les chunks visés.

    ``indices=None`` → tout le document est concerné (cas de la suppression).
    VALIDÉE et CORRIGÉE sont retenues : les deux sont indexées dans Qdrant par
    ``feedback_job``, les deux sont réutilisables par
    ``trouver_reponse_reutilisable``, et les deux doivent donc être retirées de
    l'index à la suppression du document source.
    """
    if indices is not None and not indices:
        return []

    q = db.query(ReponseChunk.reponse_id).filter(ReponseChunk.doc_id == doc_id)
    if indices is not None:
        q = q.filter(ReponseChunk.chunk_index.in_(sorted(indices)))

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
    """Réduit une famille aux réponses *distinctes* qu'elle représente.

    ``reponses_obsoletes`` remonte les copies SUGGESTION/CANONIQUE : une réponse
    réutilisée cinq fois apparaît six fois. Compter ces lignes gonflerait
    l'annonce « N réponses vont devenir obsolètes » d'un facteur arbitraire.

    On écarte donc les copies **dont la source est elle-même dans l'ensemble** —
    et non toutes les copies : une copie VALIDÉE dont la source a été rejetée
    n'est représentée par personne d'autre, et doit rester comptée.
    """
    ids = {r.id for r in reponses}
    return [r for r in reponses if r.reponse_source_id not in ids]


def marquer_obsoletes(
    db: Session,
    doc_id: str,
    raison: str,
    version: int | None = None,
    indices: set[int] | None = None,
) -> tuple[list[Reponse], list[Reponse]]:
    """Retire de Qdrant puis marque obsolètes les réponses concernées.

    Le point Qdrant supprimé est la garantie principale : la réponse n'est plus
    jamais retrouvée. Le drapeau assure la traçabilité et l'onglet « Obsolètes ».
    Idempotent : un second passage ne retrouve rien (filtre ``obsolete is False``)
    et ``delete_response_point`` sur un id absent est un no-op.

    Les réponses EN_ATTENTE liées au document sont également obsolètes : elles ont
    été générées sur l'ancienne version et n'ont pas encore été validées. Elles
    n'ont pas de point Qdrant (indexé seulement après validation) ; l'appel
    ``delete_response_point`` est donc un no-op pour elles.
    """
    reponses = reponses_obsoletes(db, doc_id, indices)
    retirer_du_service(db, reponses, raison, doc_id, version)
    return reponses, perimer_en_attente(db, doc_id, raison, version)


def perimer_en_attente(db: Session, doc_id: str, raison: str, version: int | None) -> list[Reponse]:
    """Périme les réponses EN_ATTENTE bâties sur le document, quel que soit le chunk cité.

    Aucun jugement n'est requis pour celles-là : elles n'ont jamais été servies,
    ne sont pas indexées, et les valider plus tard reviendrait à publier une
    réponse construite sur une version qui n'existe plus. Les repasser au RAG
    (``requeuer_en_attente``) coûte un ticket retraité et rend une réponse à jour
    — c'est strictement moins cher que de faire trancher un humain ou un modèle.

    Extrait de ``marquer_obsoletes`` parce que la mise à jour n'appelle plus que
    cette moitié : depuis que le verdict revient à la ré-vérification, faire
    prononcer une obsolescence à ``indices_modifies`` seul n'a plus lieu d'être.
    """
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


def retirer_du_service(
    db: Session,
    reponses: list[Reponse],
    raison: str,
    doc_id: str | None,
    version: int | None,
) -> None:
    """Retire de Qdrant et pose les drapeaux, sur une liste déjà constituée.

    Extrait de ``marquer_obsoletes`` pour servir aussi le retrait à la main
    (``POST /reponses/{id}/retirer``), qui part d'une famille précise et non
    d'un document.
    """
    maintenant = datetime.now(timezone.utc)

    for r in reponses:
        delete_response_point(str(r.id))
        r.obsolete = True
        r.obsolete_raison = raison
        r.obsolete_doc_id = doc_id
        r.obsolete_version = version
        r.obsolete_at = maintenant
        # Une réponse signalée à la v3 puis périmée à la v4 siégerait dans les
        # deux onglets. L'obsolescence tranche la question que la relecture
        # posait : le signal n'a plus lieu d'être.
        lever_a_relire(r)

    db.commit()


def lever_a_relire(r: Reponse) -> None:
    """Efface les colonnes de relecture, la suggestion LLM et les passages associés.

    Ne touche **pas** à ``analyse_justification`` / ``analyse_extraits`` :
    ``retirer_du_service`` passe par ici avant de poser une obsolescence, et
    effacer la justification en chemin priverait l'onglet « Obsolètes » de la
    seule chose qui rend un retrait sec compréhensible. Les deux colonnes sont
    remises à zéro explicitement par le verdict ``INTACTE``, qui est le seul cas
    où plus rien n'est à expliquer.
    """
    r.a_relire = False
    r.a_relire_raison = None
    r.a_relire_doc_id = None
    r.a_relire_version = None
    r.a_relire_at = None
    r.correction_suggeree = None
    r.passages_pertinents = None


def poser_a_relire(reponses: list[Reponse], raison: str, doc_id: str, version: int) -> None:
    """Pose le drapeau de relecture, sans commit ni Qdrant.

    Ne touche pas à Qdrant : c'est toute la différence avec l'obsolescence. La
    réponse continue d'être servie tant que personne n'a tranché.
    """
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
    """Signale en bloc toutes les réponses encore servies du document.

    Périmètre volontairement large — tout le document — parce qu'aucune
    information ne permet de faire mieux dans les deux cas qui en restent
    tributaires : la version sortante illisible (``RAISON_ILLISIBLE``, pas de
    diff calculable) et le document réécrit au-delà du plafond
    (``RAISON_MASSIVE``, plus rien à discriminer).

    Flague la **famille entière** et non les seules ``racines`` : ``racines``
    conserve les copies dont la source est hors ensemble, qu'un futur filtre
    ``reponse_source_id IS NULL`` rendrait invisibles — donc indéboulonnables.
    Seul le *comptage* passe par ``racines``.

    Les réponses déjà obsolètes sont hors jeu : ``reponses_obsoletes`` les filtre,
    et ``marquer_obsoletes`` commite avant qu'on arrive ici.
    """
    reponses = reponses_obsoletes(db, doc_id, indices=None)
    poser_a_relire(reponses, raison, doc_id, version)
    db.commit()
    return reponses


def flaguer_en_analyse(db: Session, doc_id: str, version: int) -> list[Reponse]:
    """Marque « analyse en cours » les réponses que la ré-vérification va juger.

    Posé **dans la foulée de la bascule de version**, avant que le job d'analyse
    ne démarre. Celui-ci met de trente secondes à quelques minutes ; sans ce
    drapeau, il existerait une fenêtre pendant laquelle le document dit une chose,
    les réponses canoniques en disent une autre, et rien nulle part ne le signale.

    Le drapeau n'est pas une demande de relecture : c'est un état transitoire que
    le job résout — il le lève (``INTACTE``), l'aggrave en obsolescence
    (``CONTREDITE``) ou le requalifie (``INCERTAIN``, budget, panne). Le front le
    présente donc comme un badge neutre et non comme une tâche à traiter. S'il
    survit à la fin du job, c'est que le worker est mort : le ``on_failure``
    le rabat alors en ``RAISON_INDISPONIBLE``.
    """
    return marquer_a_relire(db, doc_id, version, RAISON_ANALYSE)


def confirmer_actualite(db: Session, reponses: list[Reponse]) -> None:
    """Lève le signalement : un humain a relu et jugé la réponse toujours juste."""
    for r in reponses:
        lever_a_relire(r)
    db.commit()


def requeuer_en_attente(db: Session, reponses: list[Reponse]) -> None:
    """Re-soumet au pipeline RAG les tickets dont la réponse EN_ATTENTE vient d'être rendue obsolète.

    Import différé de ``question_job`` pour briser la dépendance circulaire :
    ``obsolescence`` ← importe ← ``question``, et ``question`` importe ce module.
    On ne l'importe qu'au moment de l'appel, pas au chargement du module.
    """
    if not reponses:
        return

    from app.workers.question import question_job  # noqa: PLC0415 — import différé anti-circulaire

    ids_tickets = {r.ticket_id for r in reponses if r.ticket_id is not None}
    if not ids_tickets:
        return

    tickets = db.query(Ticket).filter(Ticket.id.in_(ids_tickets)).all()
    for ticket in tickets:
        ticket.statut_job = "EN_ATTENTE"
        ticket.statut_ticket = "NOUVEAU"
        ticket.erreur = None
    db.commit()

    for ticket in tickets:
        question_job.delay(
            question=ticket.question,
            domaine=ticket.domaine,
            user_id=str(ticket.user_id) if ticket.user_id else None,
            ticket_id=str(ticket.id),
            objet=ticket.objet,
            retraiter=True,
        )
        logging.getLogger(__name__).info("Ticket %s re-soumis au pipeline RAG", ticket.id)
