import logging

import requests
from app.config import settings

logger = logging.getLogger(__name__)


def rerank(question: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    if not chunks:
        return []

    logger.debug("Envoi de %d chunks à l'API Albert pour reranking", len(chunks))

    # contenu_indexe includes the locator — without it, opaque passages are re-scored without context and ranked last
    documents = [chunk.get("contenu_indexe") or chunk["contenu"] for chunk in chunks]

    response = requests.post(
        settings.albert_reranker_url,
        headers={
            "Authorization": f"Bearer {settings.albert_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.albert_reranker_model_name,
            "query": question,
            "documents": documents,
            "top_n": top_k,
        },
        timeout=15,
    )

    if response.status_code == 422:
        logger.error("Erreur de validation Albert (422): %s", response.json())

    response.raise_for_status()
    predictions = response.json()

    results = []

    if isinstance(predictions, dict) and "results" in predictions:
        for item in predictions["results"]:
            idx = item["index"]
            score = item["relevance_score"]
            chunk_copy = chunks[idx].copy()
            chunk_copy["rerank_score"] = float(score)
            results.append(chunk_copy)

    return results
