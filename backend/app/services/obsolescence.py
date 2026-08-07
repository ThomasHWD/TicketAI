"""Détection des réponses rendues obsolètes par un changement de document.

**La comparaison est document ↔ document : le texte de la réponse n'y participe
jamais.** Le LLM reformule (« 2 jours » devient « deux jours hebdomadaires ») ;
chercher ses phrases dans le document n'aurait aucun sens. Ce qu'on exploite,
c'est que ``reponse_chunks`` mémorise *quels passages* ont servi, et que Qdrant
conserve leur texte brut dans le payload : il suffit de vérifier si ces passages
figurent encore dans la nouvelle version.

::

    DOCUMENT v1, chunk #7 (payload Qdrant `contenu`)
      « Le télétravail est limité à 2 jours par semaine, sur accord du manager. »
            │  reponse_chunks (doc_id=X, chunk_index=7)
            ↓
    RÉPONSE CANONIQUE — texte du LLM, JAMAIS comparé
      « Vous pouvez télétravailler jusqu'à deux jours hebdomadaires… »

    v2 : « …limité à 3 jours par semaine… » → passage absent → réponse obsolète

Insensible au re-découpage : ``chunk_text()`` produit des sous-chaînes du texte
complet (``RecursiveCharacterTextSplitter`` sur ``"\\n\\n".join(pages)``), donc
« ce passage existe-t-il encore ? » se répond par une recherche de sous-chaîne,
sans jamais comparer des frontières de chunks — lesquelles se décalent dès la
première modification et ne veulent rien dire d'une version à l'autre.
"""

import re
import uuid
from datetime import datetime, timezone

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.services.qdrant import delete_response_point
from sqlalchemy.orm import Session

# Raisons d'obsolescence stockées dans `Reponse.obsolete_raison`
RAISON_MAJ = "DOC_MIS_A_JOUR"
RAISON_SUPPRESSION = "DOC_SUPPRIMÉ"

_ESPACES = re.compile(r"\s+")


def _normaliser(texte: str) -> str:
    """Espaces compactés, insécables normalisés, strip.

    Les deux textes sont déjà passés par ``clean_text`` : cette normalisation ne
    couvre que le rognage de bordure du splitter et les insécables des PDF.
    La classe d'espaces est unicode par défaut sur une chaîne : elle couvre
    donc aussi l'espace insécable des PDF, sans traitement dédié.
    """
    return _ESPACES.sub(" ", texte).strip()


def indices_modifies(anciens_chunks: dict[int, str], nouveau_texte: str) -> set[int]:
    """Indices des chunks de la version sortante absents de la nouvelle version.

    ``anciens_chunks`` : ``{chunk_index: contenu}`` capturé dans Qdrant **avant**
    toute suppression — c'est la seule source du texte de la version sortante.
    """
    ref = _normaliser(nouveau_texte)
    return {i for i, txt in anciens_chunks.items() if _normaliser(txt or "") not in ref}


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
        copies = {
            r[0]
            for r in db.query(Reponse.id).filter(Reponse.reponse_source_id.in_(frontiere)).all()
        }
        frontiere = copies - vus
        vus |= frontiere
    return vus


def reponses_obsoletes(
    db: Session,
    doc_id: str,
    indices: set[int] | None = None,
) -> list[Reponse]:
    """Réponses encore réutilisables qui s'appuient sur les chunks visés.

    ``indices=None`` → tout le document est concerné (cas de la suppression).
    Seules les ``VALIDÉE`` non déjà obsolètes sont retenues : ce sont les seules
    que ``_trouver_reponse_reutilisable`` peut resservir.
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
            Reponse.statut == "VALIDÉE",
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
) -> list[Reponse]:
    """Retire de Qdrant puis marque obsolètes les réponses concernées.

    Le point Qdrant supprimé est la garantie principale : la réponse n'est plus
    jamais retrouvée. Le drapeau assure la traçabilité et l'onglet « Obsolètes ».
    Idempotent : un second passage ne retrouve rien (filtre ``obsolete is False``)
    et ``delete_response_point`` sur un id absent est un no-op.
    """
    reponses = reponses_obsoletes(db, doc_id, indices)
    maintenant = datetime.now(timezone.utc)

    for r in reponses:
        delete_response_point(str(r.id))
        r.obsolete = True
        r.obsolete_raison = raison
        r.obsolete_doc_id = doc_id
        r.obsolete_version = version
        r.obsolete_at = maintenant

    db.commit()
    return reponses
