import logging

from app.config import settings
from app.services import bm25
from openai import OpenAI

logger = logging.getLogger(__name__)

client = OpenAI(base_url=settings.albert_llm_url, api_key=settings.albert_api_key)


def embed_texts(texts: list[str], is_query: bool = False) -> list[dict]:
    """Dense (Albert) + sparse BM25 vector pair per text. `is_query` controls TF saturation."""
    # BM25 before the network call — local and free; fails fast on missing deps before spending Albert quota
    creux = [bm25.encoder(texte, est_requete=is_query) for texte in texts]

    MAX_BATCH_SIZE = 64  # Albert API limit
    denses = []

    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i : i + MAX_BATCH_SIZE]

        logger.debug("Envoi d'un lot de %d textes à l'API Albert (%d/%d)", len(batch), i + len(batch), len(texts))

        response = client.embeddings.create(
            model=settings.albert_embeddings_model_name,
            input=batch,
        )

        # response.data is not guaranteed ordered — sort by index to avoid pairing wrong sparse↔dense vectors
        for item in sorted(response.data, key=lambda d: d.index):
            denses.append(item.embedding)

    if len(denses) != len(texts):
        raise ValueError(f"Albert a renvoyé {len(denses)} vecteurs pour {len(texts)} textes")

    return [{"dense": dense, "sparse": sparse} for dense, sparse in zip(denses, creux, strict=True)]
