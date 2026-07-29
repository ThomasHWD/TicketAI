from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import FieldCondition, Filter, MatchValue, SparseVector


def reciprocal_rank_fusion(dense_results, sparse_results, k: int = 60) -> list[dict]:
    scores = {}
    for rank, point in enumerate(dense_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)
    for rank, point in enumerate(sparse_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)

    payloads = {}
    dense_scores = {}
    for point in dense_results.points:
        if point.id not in payloads:
            payloads[point.id] = point.payload
            dense_scores[point.id] = point.score  # ← score cosinus brut
    for point in sparse_results.points:
        if point.id not in payloads:
            payloads[point.id] = point.payload

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {
            "score_rrf": scores[pid],
            "score_cosinus": dense_scores.get(pid, 0.0),  # ← exposé
            "contenu": payloads[pid].get("contenu"),
            "source": payloads[pid].get("source"),
            "domaine": payloads[pid].get("domaine"),
            "doc_id": payloads[pid].get("doc_id"),
            "chunk_index": payloads[pid].get("chunk_index"),
            "reponse_id": payloads[pid].get("reponse_id"),  # ← réponse canonique liée (Phase 4)
        }
        for pid in sorted_ids
    ]


def search_hybrid(question: str, domaine: str, top_k: int = 10) -> list[dict]:
    # NOTE : Prefetch + Fusion.RRF natif Qdrant 1.18 bugué avec vecteurs 1024d
    # RRF implémenté manuellement — comportement identique
    embeddings = embed_texts([question], is_query=True)
    emb = embeddings[0]

    # Filtre strict par domaine : pas de fuite inter-domaines (IT / RH / JURIDIQUE)
    domaine_filter = Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])

    dense_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=emb["dense"],
        using="dense",
        query_filter=domaine_filter,
        limit=top_k,
        with_payload=True,
    )

    sparse_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=SparseVector(indices=emb["sparse"]["indices"], values=emb["sparse"]["values"]),
        using="sparse",
        query_filter=domaine_filter,
        limit=top_k,
        with_payload=True,
    )

    return reciprocal_rank_fusion(dense_results, sparse_results, k=60)[:top_k]
