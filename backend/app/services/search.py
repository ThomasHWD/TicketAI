from app.config import settings
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

# Les points écrits par `feedback_job` portent un `reponse_id` ; les chunks de
# documents n'ont pas cette clé du tout. `IsEmpty` couvre l'absence de clé, ce qui
# suffit à ne garder que les réponses indexées.
FILTRE_POINTS_REPONSE = Filter(must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))])

# Plancher du diviseur du score lexical par terme.
#
# Le score BM25 par terme divise la somme par **tous** les termes de la requête,
# appariés ou non — c'est voulu, l'appariement partiel doit coûter. Mais à un
# seul terme le diviseur vaut 1 et la normalisation ne fait plus rien : franchir
# `SEUIL_LEXICAL_PAR_TERME` (1,0) ne demande alors qu'un poids TF ≈ 1,56 fois un
# IDF ≥ 0,64, c'est-à-dire n'importe quel mot présent dans moins de la moitié du
# corpus. Toute requête d'un mot ouvrait donc la porte lexicale, et chaque
# ouverture coûte un appel au juge sur un quota Albert de 1 000 requêtes/jour.
#
# Plancher à 2 : une requête d'un seul mot doit apporter l'équivalent de deux
# termes de preuve. Un vrai terme rare passe toujours (« RGPD », IDF ≈ 3, donne
# ≈ 2,3 après division) ; un mot courant ne passe plus (IDF ≈ 0,7 donne ≈ 0,53).
# Aucun effet au-delà d'un terme, donc aucun effet sur les seuils calibrés.
DIVISEUR_MINIMAL = 2


def franchit_le_rappel(chunk: dict, seuil_cosinus: float) -> bool:
    """Le candidat mérite-t-il d'être examiné ? **Disjonction, pas mélange.**

    On ne seuille pas la fusion, on seuille chaque signal sur sa propre échelle —
    c'est la réponse habituelle à « comment couper sur une recherche hybride ».
    Aucun score de fusion n'est absolu : le RRF ne dépend que du rang (premier
    d'un lot inutile vaut premier d'un lot parfait), et une fusion par
    distribution normalise **par requête**, donc le meilleur vaut toujours ≈ 1.
    Les signaux bruts, eux, disent quelque chose.

    Cet étage est un filtre de **rappel**, pas de sûreté : il limite le nombre
    d'appels au juge, et c'est le juge qui décide ce qui peut être servi sans
    revue humaine (cf. `services/garde_cache.py`). Élargir la porte coûte donc des
    appels Albert, pas de la sûreté.

    La porte lexicale est ce qui rend BM25 utile : un sigle, une référence
    d'article, un nom propre que le modèle d'embedding ne connaît pas ont un
    cosinus médiocre et un recouvrement lexical parfait. Sans cette porte, le cas
    d'usage principal de BM25 resterait hors de portée.
    """
    if chunk.get("score_cosinus", 0.0) >= seuil_cosinus:
        return True
    if settings.seuil_lexical_par_terme <= 0:  # porte lexicale fermée
        return False
    return chunk.get("score_lexical", 0.0) >= settings.seuil_lexical_par_terme


def _completer_scores(vecteur, using: str, filtre: Filter, ids_manquants: list) -> dict:
    """Score réel, sur la branche `using`, des points que l'autre branche a seule retrouvés.

    **Les deux sens sont nécessaires, et l'oubli de l'un s'est vu en mesure.**

    Un point absent du top-k d'une branche hérite sinon d'un score `0.0` sur
    celle-ci, alors qu'il y aurait peut-être bien figuré avec un rang plus large.
    Côté dense, ce zéro le faisait écarter par tous les seuils du système — BM25
    n'aurait servi à rien. Côté lexical, il le privait de son bonus : mesuré, la
    question « Combien mesure une poire » passait ainsi devant « Combien fait une
    pomme en hauteur ? » pour la requête « combien mesure une pomme ? », la seconde
    ayant pourtant les deux mots en commun.

    Une requête Qdrant par sens, aucun appel Albert.

    **Le filtre d'origine est imbriqué, pas recopié clause par clause.** Un
    `Filter` Qdrant a quatre clauses — `must`, `must_not`, `should`, `min_should`
    — et la version précédente n'en reprenait que deux : un `should` se serait
    perdu en silence, et le rattrapage aurait alors noté des points que la
    recherche principale avait exclus. Chaque clause accepte en outre *soit* une
    liste *soit* une condition seule, si bien que déplier `filtre.must` lève une
    `ValidationError` pydantic sur la seconde forme. L'imbrication traite les
    deux problèmes d'un coup, et reste juste si Qdrant ajoute une clause demain.
    """
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
    """Fusion RRF des deux branches — pour **ordonner**, jamais pour décider.

    Les deux dictionnaires de rattrapage complètent le score qu'un point n'a pas
    obtenu faute d'être entré dans le top-k de l'autre branche (cf.
    `_completer_scores`). Ils sont appliqués ici, à l'endroit unique où les scores
    sont constitués, pour ne pas avoir à redériver l'ordre du tri ailleurs.

    `nb_termes_requete` sert à ramener le score BM25 au terme : un score brut est
    une somme sur les termes de la requête, donc incomparable d'une question à
    l'autre. C'est cette valeur normalisée que la porte lexicale seuille.
    """
    # Le diviseur est planché à `DIVISEUR_MINIMAL` : voir la constante.
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
        dense_scores[point.id] = point.score  # ← score cosinus brut
    for point in sparse_results.points:
        if point.id not in payloads:
            payloads[point.id] = point.payload
        sparse_scores[point.id] = point.score  # ← score BM25 (IDF appliqué par Qdrant)

    dense_scores.update(cosinus_rattrapes or {})
    sparse_scores.update(lexicaux_rattrapes or {})

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {
            # `score_rrf` ordonne. Les deux signaux bruts décident, chacun sur son
            # échelle — le cosinus reste par ailleurs la valeur auditée dans
            # `garde_decisions`, et `score_sparse` est conservé pour la mesure.
            "score_rrf": scores[pid],
            "score_cosinus": dense_scores.get(pid, 0.0),
            "score_sparse": sparse_scores.get(pid, 0.0),
            "score_lexical": sparse_scores.get(pid, 0.0) / diviseur,
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
        # Les indices du vecteur creux de la requête *sont* ses termes retenus,
        # élisions et mots-outils déjà écartés : pas besoin de retokeniser.
        nb_termes_requete=len(emb["sparse"]["indices"]),
    )[:top_k]


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
