"""Confronte les réponses déjà servies au document qu'on vient d'ingérer.

L'entonnoir de ``services/reverification.py`` ne se déclenche que sur un
**remplacement de version** : il lui faut un diff AVANT/APRÈS. Ingérer un
document pour la *première* fois ne touchait donc aucune réponse existante —
y compris une canonique que ce document contredit désormais, et qui continuait
d'être servie **sans revue humaine** indéfiniment.

C'est le cas « règle générale puis exception » : le document A dit « le
télétravail est autorisé du lundi au mercredi », une réponse canonique en
découle, puis le document B arrive et dit « les alternants n'ont pas de
télétravail ». Rien ne reliait B à la réponse bâtie sur A.

Ce module fournit les briques du rattrapage, toutes **sans un seul appel
Albert** : ``ingestion_job`` détient déjà les vecteurs des chunks qu'il vient
d'écrire, la détection ne coûte donc que des requêtes Qdrant. Le verdict, lui,
est rendu par ``workers/confrontation.py``.

**Invariant de ce chemin : aucune réponse n'y devient jamais obsolète.**
``decider`` ne retire du service que sur ``CONTREDITE`` **et** ``citante``, et
``citante`` vient de ``reponse_chunks`` : un document qui n'existait pas à la
génération de la réponse n'y a aucune ligne. Le plafond à ``a_relire`` est une
conséquence du modèle de données, pas un drapeau qu'on pourrait lever — et
c'est le bon plafond, parce qu'une réponse *incomplète* ne se détruit pas, elle
s'amende (« Modifier » dans l'onglet « À relire »), là où un retrait coûterait
``SEUIL_CANONIQUE`` revalidations pour un état final identique.
"""

import logging
import uuid

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
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

# Chunks retenus par réponse. Le reranker n'en montrera de toute façon que
# `MAX_UNITES_PAR_REPONSE` au modèle ; ce plafond-ci borne surtout la taille des
# arguments de la tâche Celery, qui transitent par le broker.
MAX_CHUNKS_PAR_REPONSE = 8

# Passages du document d'origine montrés au juge (cf. `juger_confrontation`).
MAX_EXTRAITS_SOURCE = 4


def cibles_confrontation(embeddings: list[dict], domaine: str) -> dict[str, list[int]]:
    """``{reponse_id: [chunk_index, …]}`` — quelles réponses ce document interpelle.

    Une requête Qdrant dense par chunk, **aucun appel Albert** : les vecteurs
    sont ceux que l'ingestion vient de payer. Le filtre et le seuil sont ceux de
    ``_voisines`` (``reverification_candidates.py``) — même question posée à
    l'envers, donc même calibration : là-bas on cherche les réponses proches
    d'un changement, ici les réponses proches d'un chunk neuf.

    On **conserve l'association** (chunk → réponse) plutôt que de rendre un
    simple ensemble de réponses : elle permet de juger chaque réponse contre les
    quelques passages qui l'ont réellement appariée, au lieu de reranker le
    document entier une fois par réponse.

    Dense seulement, pour la raison exposée dans ``_voisines`` : le recouvrement
    lexical d'un paragraphe et d'une question est dominé par le vocabulaire
    commun au domaine, et aucun étage en aval ne rattraperait un candidat entré
    par les seuls mots.

    Une réponse porte un point par formulation validée : le même chunk peut donc
    la remonter plusieurs fois. C'est la réponse qu'on juge, pas la formulation,
    d'où la déduplication par ``reponse_id``.

    Ne lève jamais : une panne de détection ne doit pas faire échouer une
    ingestion par ailleurs réussie.
    """
    if not embeddings:
        return {}

    filtre = Filter(
        must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))],
        must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))],
    )

    # {reponse_id: {chunk_index: meilleur score}} — le score ne sert qu'à choisir
    # lesquels garder quand un document interpelle une réponse par dix passages.
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


def familles_servies(db: Session, ids: set[uuid.UUID]) -> list[Reponse]:
    """La famille complète des réponses visées, restreinte à ce qui est encore servi.

    ``fermeture_copies`` descend vers les copies SUGGESTION/CANONIQUE : elles ne
    portent pas de point Qdrant à elles et n'ont donc pas pu être retrouvées par
    la détection, mais ce sont elles qui s'affichent sur les tickets. Les laisser
    hors du lot poserait le drapeau sur la graine et le tairait sur ce que
    l'utilisateur voit.
    """
    if not ids:
        return []
    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, ids)),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def identifiants(cibles: dict[str, list[int]]) -> set[uuid.UUID]:
    """Les ``reponse_id`` exploitables d'un dictionnaire de cibles.

    Le payload Qdrant est du texte libre : un identifiant illisible est ignoré
    plutôt que de faire échouer tout le lot.
    """
    ids: set[uuid.UUID] = set()
    for brut in cibles:
        try:
            ids.add(uuid.UUID(str(brut)))
        except ValueError:
            logger.warning("confrontation : reponse_id illisible dans le payload (%r)", brut)
    return ids


def textes_chunks(doc_id: str, version: int, indices: set[int]) -> dict[int, str]:
    """``{chunk_index: contenu}`` pour les chunks retenus de la version courante.

    Lit le ``contenu`` brut et non le texte indexé : c'est ce qu'affirme le
    document qu'on soumet au juge, pas le locateur que la contextualisation lui a
    préfixé pour la recherche.
    """
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
    """Les passages sur lesquels la réponse a été construite, tels qu'ils sont aujourd'hui.

    Sans eux, le juge voit un paragraphe et une réponse, et « CONTREDITE » ne
    peut vouloir dire que « ces deux textes se contredisent ». Avec eux, il peut
    distinguer une réponse *fausse* d'une réponse *incomplète* — ce qui n'est pas
    la même correction pour le relecteur — et écarter les faux appariements d'un
    rappel à 0,35 en constatant que les textes n'ont rien à voir.

    Deux approximations assumées. ``reponse_chunks`` ne mémorise pas la version :
    on lit donc le chunk **à cet indice dans la version courante**, qui peut avoir
    bougé depuis. Et seules les réponses nées du RAG citent des chunks : une copie
    SUGGESTION/CANONIQUE n'en a pas, d'où la remontée par ``reponse_source_id``.

    Rend une liste vide plutôt que de lever : le jugement sans contexte source
    reste meilleur que pas de jugement du tout.
    """
    try:
        lignes = (
            db.query(ReponseChunk.doc_id, ReponseChunk.chunk_index)
            .filter(ReponseChunk.reponse_id.in_(_lignee(db, reponse)))
            .order_by(ReponseChunk.rerank_score.desc().nullslast())
            .limit(MAX_EXTRAITS_SOURCE)
            .all()
        )
    except Exception as exc:
        logger.warning("contexte source illisible pour %s (%s)", reponse.id, exc)
        return []

    par_document: dict[str, set[int]] = {}
    for doc_id, chunk_index in lignes:
        par_document.setdefault(doc_id, set()).add(chunk_index)

    textes: list[str] = []
    for doc_id, indices in par_document.items():
        try:
            points, _ = client.scroll(
                collection_name=COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        FieldCondition(key="chunk_index", match=MatchAny(any=sorted(indices))),
                    ]
                ),
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
    """La réponse et ses sources successives — les seules à citer des chunks.

    ``fermeture_copies`` descend (source → copies) ; ici il faut remonter. Le
    garde-fou sur les visités assure la terminaison même si deux réponses se
    désignent mutuellement comme source, ce que ``corriger_reponse`` rend
    possible en réindexant la copie.
    """
    ids = {reponse.id}
    courant = reponse.reponse_source_id
    while courant is not None and courant not in ids:
        ids.add(courant)
        courant = db.query(Reponse.reponse_source_id).filter(Reponse.id == courant).scalar()
    return ids


def resume_ajout(texte: str) -> dict:
    """Le « diff » d'un document neuf : tout est ajouté, rien n'est retiré.

    Figé sur la ligne ``DocumentVersion`` de la v1 pour que l'onglet « À relire »
    montre ce que le nouveau document dit, au lieu d'afficher « le détail de cette
    mise à jour n'a pas été conservé » — ce qui serait faux, il n'y a pas eu de
    mise à jour.

    ``unites`` est délibérément **vide** : y recopier le document entier coûterait
    jusqu'à 256 Ko de JSON par ingestion pour un contenu que personne ne lit. La
    confrontation juge sur les chunks réellement appariés, relus dans Qdrant
    (``textes_chunks``), et ``unites_figees`` n'est appelé que par la
    ré-vérification, qui ne passe jamais par une v1.
    """
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
