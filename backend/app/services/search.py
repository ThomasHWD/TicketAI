from app.services.embedding_mock import embed_texts_mock
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import SparseVector


def reciprocal_rank_fusion(dense_results, sparse_results, k: int = 60) -> list[dict]:
    """Fusion RRF manuelle des résultats dense et sparse."""
    scores = {}

    for rank, point in enumerate(dense_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)

    for rank, point in enumerate(sparse_results.points):
        pid = point.id
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)

    # Fusionne les payloads
    payloads = {}
    for point in list(dense_results.points) + list(sparse_results.points):
        if point.id not in payloads:
            payloads[point.id] = point.payload

    # Trie par score RRF décroissant
    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {
            "score": scores[pid],
            "contenu": payloads[pid].get("contenu"),
            "source": payloads[pid].get("source"),
            "domaine": payloads[pid].get("domaine"),
            "doc_id": payloads[pid].get("doc_id"),
            "chunk_index": payloads[pid].get("chunk_index"),
        }
        for pid in sorted_ids
    ]


def search_hybrid(question: str, domaine: str, top_k: int = 10) -> list[dict]:
    """
    Recherche hybride dense + sparse avec RRF manuel.
    Contourne la limite JSON de Qdrant 1.18 sur les Prefetch.
    """
    embeddings = embed_texts_mock([question])
    emb = embeddings[0]

    # Recherche dense
    dense_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=emb["dense"].tolist(),
        using="dense",
        limit=top_k,
        with_payload=True,
    )

    # Recherche sparse
    sparse_results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=SparseVector(
            indices=emb["sparse"]["indices"],
            values=emb["sparse"]["values"].tolist()
        ),
        using="sparse",
        limit=top_k,
        with_payload=True,
    )

    # Fusion RRF manuelle
    return reciprocal_rank_fusion(dense_results, sparse_results, k=60)[:top_k]
