"""Vecteurs à cosinus **exact** et chunks factices, pour tester les frontières de seuil.

Le pipeline retient un candidat du cache en comparant un cosinus à son plancher :
`SEUIL_CANDIDAT_CANONIQUE` (0.70) pour une réponse canonique, `SEUIL_SUGGESTION`
(0.85) sinon. Tester ces frontières suppose de pouvoir produire, à volonté, un
point dont le cosinus avec la requête vaut *précisément* 0.6999 ou 0.85 — pas
« à peu près ». Des vecteurs aléatoires ne le permettent pas ; une construction
analytique, si.

(Ces planchers ne décident plus du service *sans revue humaine* — c'est le garde
qui tranche, cf. `Docs/garde-cache-canonique.md`. Ils décident de la candidature,
et une frontière de candidature reste une frontière à tester.)

Le procédé : on fige la requête sur le premier vecteur de la base canonique,
``e0``, et on construit le candidat dans le plan ``(e0, e_k)`` ::

    v = c·e0 + sqrt(1 - c²)·e_k        avec k ≠ 0

``‖v‖ = c² + (1 - c²) = 1`` et ``<v, e0> = c``. Les deux vecteurs étant unitaires,
leur cosinus **est** leur produit scalaire, et vaut exactement ``c``.

Qdrant normalise les vecteurs COSINE à l'écriture comme à la requête : la
construction survit à l'aller-retour, à la précision du stockage float32 près
(cf. l'avertissement ci-dessous, qui n'est pas une note de bas de page).
"""

import math

# Dimension imposée par la collection (BGE-M3) — cf. app/services/qdrant.py.
DIM = 1024

# e0 : la requête de référence. Tous les cosinus de ce module sont relatifs à elle.
VECTEUR_REQUETE: list[float] = [1.0] + [0.0] * (DIM - 1)

# ── Pourquoi 0.9000001 et pas 0.90, à connaître avant tout test de frontière ──
#
# Qdrant stocke les vecteurs en float32, et 0.90 n'y est pas représentable :
#
#     float32(0.90) == 0.8999999761581421   →   >= 0.9 vaut False
#
# On en conclurait qu'un point construit pour 0.90 pile revient de Qdrant SOUS le
# seuil. **C'est faux avec le client en service**, et la mesure le montre : le
# score dépend du TRANSPORT, pas seulement du stockage.
#
#     REST  →  0.9                   >= 0.9 vaut True    ← transport de la prod
#     gRPC  →  0.8999999761581421    >= 0.9 vaut False
#
# En REST, Qdrant (Rust/serde_json) sérialise le f32 en la plus courte décimale
# qui round-trip en f32, soit "0.9" ; Python la relit en float64 et retrouve 0.90
# exact. En gRPC le f32 voyage en binaire et Python l'élargit tel quel.
#
# Un test de frontière calé sur 0.90 mesurerait donc le format de fil au lieu du
# pipeline, et changerait de verdict si quelqu'un ajoutait `prefer_grpc=True` à
# `app/services/qdrant.py:17`. D'où deux constantes :
#
#   * COSINUS_CANONIQUE — côté « doit franchir le seuil » dans les tests Qdrant ;
#     0.9000001 est au-dessus du seuil dans les DEUX transports (f32 →
#     0.9000000953…), donc insensible à ce réglage.
#   * 0.90 exact — réservé à l'étage pur Python, où le float64 est exact
#     (`0.90 - 0.05 == 0.85` est d'ailleurs vrai, contrairement à `0.85 - 0.05`).
#
# `test_a_0_90_pile_la_branche_depend_du_transport_qdrant` épingle le tout.
COSINUS_CANONIQUE = 0.9000001  # f32 → 0.9000000953…, >= 0.9 ✔ en REST comme en gRPC


def vecteur_a_cosinus(c: float, axe_orthogonal: int = 1, dim: int = DIM) -> list[float]:
    """Vecteur unitaire dont le cosinus avec `VECTEUR_REQUETE` vaut exactement `c`.

    `axe_orthogonal` (k) permet de construire plusieurs candidats simultanés :
    chacun garde le cosinus voulu avec la requête, et leur cosinus mutuel vaut
    ``c_i·c_j`` — donc strictement inférieur à chacun d'eux tant que ``c < 1``.
    Deux candidats ne peuvent donc pas se « rapprocher » l'un de l'autre au point
    de brouiller un classement.
    """
    if not 0.0 <= c <= 1.0:
        raise ValueError(f"Cosinus hors de [0, 1] : {c}")
    if not 1 <= axe_orthogonal < dim:
        raise ValueError(f"Axe orthogonal invalide : {axe_orthogonal} (attendu dans [1, {dim}[)")

    vecteur = [0.0] * dim
    vecteur[0] = c
    vecteur[axe_orthogonal] = math.sqrt(1.0 - c * c)
    return vecteur


def produit_scalaire(a: list[float], b: list[float]) -> float:
    """Cosinus de deux vecteurs unitaires — sert aux auto-tests du helper."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def chunk_factice(
    score_cosinus: float,
    *,
    reponse_id: str | None = None,
    contenu: str = "Texte factice",
    source: str = "doc.md",
    domaine: str = "TEST",
    doc_id: str | None = None,
    chunk_index: int = 0,
    score_rrf: float = 0.0164,
) -> dict:
    """Chunk au schéma **exact** de `reciprocal_rank_fusion` (search.py:29-40).

    C'est la forme que `trouver_reponse_reutilisable` consomme. Un test qui
    fabrique ce dict à la main dérive silencieusement le jour où quelqu'un ajoute
    une clé à la production ; `test_chunk_factice_suit_le_schema_de_production`
    verrouille l'équivalence.
    """
    return {
        "score_rrf": score_rrf,
        "score_cosinus": score_cosinus,
        "contenu": contenu,
        "source": source,
        "domaine": domaine,
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "reponse_id": reponse_id,
    }


def embeddings_factices(vecteur: list[float]) -> list[dict]:
    """Retour d'`embed_texts` pour un vecteur donné.

    Le vecteur sparse est vide : c'est ce que la production renvoie réellement
    (`app/services/embedding.py:31`). Ne pas le « corriger » ici — le harnais
    doit reproduire la prod, pas la prod souhaitée.
    """
    return [{"dense": vecteur, "sparse": {"indices": [], "values": []}}]
