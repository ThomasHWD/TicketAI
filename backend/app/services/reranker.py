from sentence_transformers import CrossEncoder

_reranker = None

def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        print("[RERANKER] Chargement bge-reranker-v2-m3...")
        _reranker = CrossEncoder(
            'BAAI/bge-reranker-v2-m3',
            max_length=512
        )
        print("[RERANKER] Reranker prêt")
    return _reranker


def rerank(question: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    if not chunks:
        return []

    reranker = get_reranker()
    pairs = [[question, chunk["contenu"]] for chunk in chunks]
    scores = reranker.predict(pairs)

    ranked = sorted(
        zip(chunks, scores, strict=False),
        key=lambda x: x[1],
        reverse=True
    )

    results = []
    for chunk, score in ranked[:top_k]:
        chunk_copy = chunk.copy()
        chunk_copy["rerank_score"] = float(score)
        results.append(chunk_copy)

    return results
