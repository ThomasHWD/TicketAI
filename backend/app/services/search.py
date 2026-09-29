from app.config import settings
from app.services.contextualisation import texte_indexe
from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import (
    FieldCondition,
    Filter,
    HasIdCondition,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
    SparseVector,
)

# feedback_job points carry a reponse_id; document chunks don't have the key at all. IsEmpty covers absence.
FILTRE_POINTS_REPONSE = Filter(must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))])

# Floor at 2: a single-term query gets divisor 1, meaning any rare word opens the lexical gate and burns an Albert call.
DIVISEUR_MINIMAL = 2


def franchit_le_rappel(chunk: dict, seuil_cosinus: float) -> bool:
    """Recall gate, not safety: widening costs Albert calls, not correctness. Lexical gate makes BM25 useful for"""
    if chunk.get("score_cosinus", 0.0) >= seuil_cosinus:
        return True
    if settings.seuil_lexical_par_terme <= 0:  # lexical gate disabled
        return False
    return chunk.get("score_lexical", 0.0) >= settings.seuil_lexical_par_terme


def _completer_scores(vecteur, using: str, filtre: Filter, ids_manquants: list) -> dict:
    """Fetch the real score for cross-branch points; without this, a 0.0 default was measured to flip ranking."""
    if not ids_manquants:
        return {}

    cible = Filter(must=[filtre, HasIdCondition(has_id=ids_manquants)])
    res = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vecteur,
        using=using,
        query_filter=cible,
        limit=len(ids_manquants),
        with_payload=False,
    )
    return {point.id: point.score for point in res.points}


def reciprocal_rank_fusion(
    dense_results,
    sparse_results,
    k: int = 60,
    cosinus_rattrapes: dict | None = None,
    lexicaux_rattrapes: dict | None = None,
    nb_termes_requete: int = 1,
) -> list[dict]:
    """RRF fusion for ordering only — never for thresholding. Rattrapage dicts carry scores for points absent from"""
    diviseur = max(nb_termes_requete, DIVISEUR_MINIMAL)
    scores = {}
    for rank, point in enumerate(dense_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)
    for rank, point in enumerate(sparse_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)

    payloads = {}
    dense_scores = {}
    sparse_scores = {}
    for point in dense_results.points:
        if point.id not in payloads:
            payloads[point.id] = point.payload
        dense_scores[point.id] = point.score
    for point in sparse_results.points:
        if point.id not in payloads:
            payloads[point.id] = point.payload
        sparse_scores[point.id] = point.score

    dense_scores.update(cosinus_rattrapes or {})
    sparse_scores.update(lexicaux_rattrapes or {})

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {
            "score_rrf": scores[pid],
            "score_cosinus": dense_scores.get(pid, 0.0),
            "score_sparse": sparse_scores.get(pid, 0.0),
            "score_lexical": sparse_scores.get(pid, 0.0) / diviseur,
            "contenu": payloads[pid].get("contenu"),
            # reranker and generation work on contenu_indexe — without it a passage found via its locator would be
            "contexte": payloads[pid].get("contexte"),
            "contenu_indexe": texte_indexe(payloads[pid].get("contenu") or "", payloads[pid].get("contexte")),
            "source": payloads[pid].get("source"),
            "domaine": payloads[pid].get("domaine"),
            "doc_id": payloads[pid].get("doc_id"),
            "chunk_index": payloads[pid].get("chunk_index"),
            "version": payloads[pid].get("version"),
            "reponse_id": payloads[pid].get("reponse_id"),
            # indexed question for this point — a response has one point per validated formulation; guard must judge
            "question_indexee": payloads[pid].get("question_indexee"),
        }
        for pid in sorted_ids
    ]


def _rechercher(question: str, filtre: Filter, top_k: int) -> list[dict]:
    """Shared body: one embedding, two queries, RRF fusion. The embedding is computed once — it's an Albert call"""
    # NOTE: Prefetch + Fusion.RRF native Qdrant 1.18 buggy with 1024d vectors — RRF implemented manually.
    embeddings = embed_texts([question], is_query=True)
    emb = embeddings[0]

    dense_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=emb["dense"],
        using="dense",
        query_filter=filtre,
        limit=top_k,
        with_payload=True,
    )

    sparse_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=SparseVector(indices=emb["sparse"]["indices"], values=emb["sparse"]["values"]),
        using="sparse",
        query_filter=filtre,
        limit=top_k,
        with_payload=True,
    )

    vus_en_dense = {point.id for point in dense_results.points}
    vus_en_creux = {point.id for point in sparse_results.points}

    vecteur_creux = SparseVector(indices=emb["sparse"]["indices"], values=emb["sparse"]["values"])
    cosinus_rattrapes = _completer_scores(
        emb["dense"], "dense", filtre, [pid for pid in vus_en_creux if pid not in vus_en_dense]
    )
    lexicaux_rattrapes = _completer_scores(
        vecteur_creux, "sparse", filtre, [pid for pid in vus_en_dense if pid not in vus_en_creux]
    )

    return reciprocal_rank_fusion(
        dense_results,
        sparse_results,
        k=60,
        cosinus_rattrapes=cosinus_rattrapes,
        lexicaux_rattrapes=lexicaux_rattrapes,
        # sparse indices are already the retained query terms — no need to re-tokenize.
        nb_termes_requete=len(emb["sparse"]["indices"]),
    )[:top_k]


def search_hybrid(question: str, domaine: str, top_k: int = 10) -> list[dict]:
    domaine_filter = Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])
    return _rechercher(question, domaine_filter, top_k)


def rechercher_points_reponses(question: str, top_k: int) -> list[dict]:
    """All-domain response-point search. No domain filter — a regular user belongs to no group; content is already"""
    return _rechercher(question, FILTRE_POINTS_REPONSE, top_k)
