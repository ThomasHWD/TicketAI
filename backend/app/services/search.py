from app.services.embedding import embed_texts
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
    SparseVector,
)

# Les points écrits par `feedback_job` portent un `reponse_id` ; les chunks de
# documents n'ont pas cette clé du tout. `IsEmpty` couvre l'absence de clé, ce qui
# suffit à ne garder que les réponses indexées.
FILTRE_POINTS_REPONSE = Filter(must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))])


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
            # Question sous laquelle ce point est indexé. Une réponse peut en avoir
            # plusieurs (une par formulation humainement validée) : c'est celle-ci
            # que le garde doit juger, pas celle du ticket d'origine.
            "question_indexee": payloads[pid].get("question_indexee"),
        }
        for pid in sorted_ids
    ]


def _rechercher(question: str, filtre: Filter, top_k: int) -> list[dict]:
    """Corps commun : un embedding de la question, deux interrogations, fusion RRF.

    Seul le filtre change d'un appelant à l'autre. L'embedding est calculé **une
    seule fois** — c'est un appel Albert, et son quota est compté par requête.
    """
    # NOTE : Prefetch + Fusion.RRF natif Qdrant 1.18 bugué avec vecteurs 1024d
    # RRF implémenté manuellement — comportement identique
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

    return reciprocal_rank_fusion(dense_results, sparse_results, k=60)[:top_k]


def search_hybrid(question: str, domaine: str, top_k: int = 10) -> list[dict]:
    # Filtre strict par domaine : pas de fuite inter-domaines (IT / RH / JURIDIQUE)
    domaine_filter = Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])
    return _rechercher(question, domaine_filter, top_k)


def rechercher_points_reponses(question: str, top_k: int) -> list[dict]:
    """Réponses déjà indexées, **tous domaines confondus**.

    Sert la FAQ, qui montre à l'utilisateur ce qu'un humain a déjà validé. Le
    cloisonnement par domaine n'a pas lieu d'être ici : un utilisateur lambda
    n'appartient à aucun groupe, et le contenu exposé en aval est restreint aux
    réponses canoniques (cf. `services/faq.py`).
    """
    return _rechercher(question, FILTRE_POINTS_REPONSE, top_k)
