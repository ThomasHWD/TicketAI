import logging

from app.config import settings
from app.services import bm25
from openai import OpenAI

logger = logging.getLogger(__name__)

# Initialisation du client configuré pour Albert
client = OpenAI(base_url=settings.albert_llm_url, api_key=settings.albert_api_key)


def embed_texts(texts: list[str], is_query: bool = False) -> list[dict]:
    """Vecteur dense (Albert) et vecteur creux BM25 (local) pour chaque texte.

    Le creux est calculé **hors** du découpage en lots : le lot de 64 est une
    limite de l'API Albert, alors que l'encodage BM25 est local et gratuit.

    `is_query` n'est plus ignoré — il distingue les deux côtés de BM25, un
    document étant pondéré par la saturation TF là où une requête ne l'est pas.
    """
    # Le creux AVANT l'appel réseau, délibérément. Il est local et gratuit : s'il
    # doit échouer (dépendance manquante, texte aberrant), autant que ce soit
    # avant d'avoir payé des appels Albert. Constaté en vrai le 11/09/2026 —
    # `snowballstemmer` absent d'un conteneur a fait facturer deux lots
    # d'embeddings d'un document de 560 chunks avant que l'erreur ne remonte.
    creux = [bm25.encoder(texte, est_requete=is_query) for texte in texts]

    # Limite imposée par l'API Albert
    MAX_BATCH_SIZE = 64
    denses = []

    # On découpe la liste 'texts' en morceaux de 64
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i : i + MAX_BATCH_SIZE]

        logger.debug("Envoi d'un lot de %d textes à l'API Albert (%d/%d)", len(batch), i + len(batch), len(texts))

        response = client.embeddings.create(
            model=settings.albert_embeddings_model_name,
            input=batch,  # On envoie uniquement le lot courant
        )

        # `response.data` n'est pas garanti ordonné : chaque entrée porte son
        # `index` dans le lot. S'y fier plutôt qu'à l'ordre d'itération, sous
        # peine d'apparier le vecteur creux d'un texte au dense d'un autre.
        for item in sorted(response.data, key=lambda d: d.index):
            denses.append(item.embedding)

    if len(denses) != len(texts):
        raise ValueError(f"Albert a renvoyé {len(denses)} vecteurs pour {len(texts)} textes")

    return [{"dense": dense, "sparse": sparse} for dense, sparse in zip(denses, creux, strict=True)]
