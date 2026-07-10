import requests
from app.config import settings

# from sentence_transformers import CrossEncoder
# _reranker = None
# def get_reranker() -> CrossEncoder:
#     global _reranker
#     if _reranker is None:
#         print("[RERANKER] Chargement bge-reranker-v2-m3...")
#         _reranker = CrossEncoder(
#             'BAAI/bge-reranker-v2-m3',
#             max_length=512
#         )
#         print("[RERANKER] Reranker prêt")
#     return _reranker


def rerank(question: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
    if not chunks:
        return []

    print(f"[RERANKER] Envoi de {len(chunks)} chunks à l'API Albert...")

    # 1. On extrait le texte de chaque chunk
    documents = [chunk["contenu"] for chunk in chunks]

    # 2. Appel à l'API Albert Rerank avec le bon schéma de payload
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
    )

    # Sécurité pour voir le détail de la validation
    if response.status_code == 422:
        print("❌ Erreur détaillée de validation Albert :", response.json())

    response.raise_for_status()
    predictions = response.json()

    results = []

    # 3. Extraction selon la réponse officielle d'Albert
    # Format reçu : {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
    if isinstance(predictions, dict) and "results" in predictions:
        for item in predictions["results"]:
            idx = item["index"]
            score = item["relevance_score"]  # ✅ Albert utilise 'relevance_score'

            # On reconstruit le chunk d'origine avec son score
            chunk_copy = chunks[idx].copy()
            chunk_copy["rerank_score"] = float(score)
            results.append(chunk_copy)

    return results
