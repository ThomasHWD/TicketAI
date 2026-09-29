"""Confronte les réponses déjà servies au document qu'on vient d'ingérer. Invariant : aucune réponse n'y devient"""

import logging
import uuid

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.diff import MAX_EXTRAITS, decouper_en_passages, extrait
from app.services.obsolescence import fermeture_copies
from app.services.qdrant import COLLECTION_NAME, client
from app.services.reverification_candidates import SEUIL_RAPPEL, TOP_K_UNITE
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchAny,
    MatchValue,
    PayloadField,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Bounds the Celery task argument size (broker transit); reranker will only show MAX_UNITES_PAR_REPONSE anyway.
MAX_CHUNKS_PAR_REPONSE = 8

MAX_EXTRAITS_SOURCE = 4  # passages du document d'origine montrés au juge


def cibles_confrontation(embeddings: list[dict], domaine: str) -> dict[str, list[int]]:
    """`{reponse_id: [chunk_index, …]}` — affected responses. Zero Albert calls (reuses ingestion vectors)"""
    if not embeddings:
        return {}

    filtre = Filter(
        must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))],
        must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))],
    )

    # {reponse_id: {chunk_index: best score}} — score used to keep top-MAX_CHUNKS_PAR_REPONSE when many chunks match
    scores: dict[str, dict[int, float]] = {}

    for index, emb in enumerate(embeddings):
        try:
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=emb["dense"],
                using="dense",
                query_filter=filtre,
                limit=TOP_K_UNITE,
                with_payload=["reponse_id"],
            )
        except Exception as exc:
            logger.warning("confrontation : rappel Qdrant impossible (%s) — détection abandonnée", exc)
            return {}

        for point in res.points:
            if point.score < SEUIL_RAPPEL:
                continue
            brut = (point.payload or {}).get("reponse_id")
            if not brut:
                continue
            par_chunk = scores.setdefault(str(brut), {})
            if point.score > par_chunk.get(index, 0.0):
                par_chunk[index] = point.score

    return {
        reponse_id: sorted(
            sorted(par_chunk, key=lambda i: par_chunk[i], reverse=True)[:MAX_CHUNKS_PAR_REPONSE]
        )
        for reponse_id, par_chunk in scores.items()
    }


def hors_domaine_canoniques(db: Session, domaine: str) -> list[uuid.UUID]:
    """IDs des réponses HORS_DOMAINE canoniques encore servies dans ce domaine.

    Qdrant ne peut pas les atteindre par similarité (la question portait sur un sujet absent de
    la base à l'époque — aucun point existant ne ressemblera aux chunks d'un nouveau document sur
    ce même sujet). On les injecte manuellement dans les cibles pour que le reranker décide.
    """
    return [
        r[0]
        for r in (
            db.query(Reponse.id)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(
                Reponse.source == "HORS_DOMAINE",
                Reponse.canonique.is_(True),
                Reponse.obsolete.is_(False),
                Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                Ticket.domaine == domaine,
            )
            .all()
        )
    ]


def familles_servies(db: Session, ids: set[uuid.UUID]) -> list[Reponse]:
    """La famille complète des réponses visées, restreinte à ce qui est encore servi. fermeture_copies"""
    if not ids:
        return []
    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, ids)),
            Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def identifiants(cibles: dict[str, list[int]]) -> set[uuid.UUID]:
    """Les reponse_id exploitables d'un dictionnaire de cibles. Illisibles ignorés plutôt que de faire échouer le"""
    ids: set[uuid.UUID] = set()
    for brut in cibles:
        try:
            ids.add(uuid.UUID(str(brut)))
        except ValueError:
            logger.warning("confrontation : reponse_id illisible dans le payload (%r)", brut)
    return ids


def textes_chunks(doc_id: str, version: int, indices: set[int]) -> dict[int, str]:
    """`{chunk_index: contenu}` brut (pas le texte indexé — le juge voit ce que le document affirme, pas le"""
    if not indices:
        return {}

    points, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="version", match=MatchValue(value=version)),
                FieldCondition(key="chunk_index", match=MatchAny(any=sorted(indices))),
            ]
        ),
        with_payload=["chunk_index", "contenu"],
        with_vectors=False,
        limit=len(indices),
    )
    return {
        p.payload["chunk_index"]: p.payload.get("contenu") or ""
        for p in points
        if p.payload and p.payload.get("chunk_index") is not None
    }


def contexte_source(db: Session, reponse: Reponse) -> list[str]:
    """Passages sur lesquels la réponse a été construite (version courante). Lets the judge distinguish false from"""
    try:
        lignes = (
            db.query(ReponseChunk.doc_id, ReponseChunk.version, ReponseChunk.chunk_index)
            .filter(ReponseChunk.reponse_id.in_(_lignee(db, reponse)))
            .order_by(ReponseChunk.rerank_score.desc().nullslast())
            .limit(MAX_EXTRAITS_SOURCE)
            .all()
        )
    except Exception as exc:
        logger.warning("contexte source illisible pour %s (%s)", reponse.id, exc)
        return []

    # grouped by version: after an update the same index names another passage — a cited version no longer in
    # Qdrant yields nothing rather than the wrong text. NULL (legacy row) = unknown version, read by index.
    par_document: dict[tuple[str, int | None], set[int]] = {}
    for doc_id, version, chunk_index in lignes:
        par_document.setdefault((doc_id, version), set()).add(chunk_index)

    textes: list[str] = []
    for (doc_id, version), indices in par_document.items():
        conditions = [
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
            FieldCondition(key="chunk_index", match=MatchAny(any=sorted(indices))),
        ]
        if version is not None:
            conditions.append(FieldCondition(key="version", match=MatchValue(value=version)))
        try:
            points, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(must=conditions),
                with_payload=["contenu"],
                with_vectors=False,
                limit=len(indices),
            )
        except Exception as exc:
            logger.warning("chunks source introuvables pour %s (%s)", doc_id, exc)
            continue
        textes += [(p.payload or {}).get("contenu") or "" for p in points]

    return [t for t in textes if t][:MAX_EXTRAITS_SOURCE]


def _lignee(db: Session, reponse: Reponse) -> set[uuid.UUID]:
    """La réponse et ses sources successives (les seules à citer des chunks). Visited set prevents cycles."""
    ids = {reponse.id}
    courant = reponse.reponse_source_id
    while courant is not None and courant not in ids:
        ids.add(courant)
        courant = db.query(Reponse.reponse_source_id).filter(Reponse.id == courant).scalar()
    return ids


def resume_ajout(texte: str) -> dict:
    """Le « diff » d'un document neuf : tout est ajouté, rien n'est retiré. `unites` est vide délibérément"""
    passages = decouper_en_passages(texte)
    return {
        "nb_unites": len(passages),
        "nb_ajoutes": len(passages),
        "nb_retires": 0,
        "extraits_ajoutes": [extrait(p) for p in passages[:MAX_EXTRAITS]],
        "extraits_retires": [],
        "unites": [],
        "unites_tronquees": bool(passages),
    }
