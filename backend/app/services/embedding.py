from app.config import settings
from openai import OpenAI

# Initialisation du client configuré pour Albert
client = OpenAI(base_url=settings.albert_llm_url, api_key=settings.albert_api_key)


def embed_texts(texts: list[str], is_query: bool = False) -> list[dict]:
    # Limite imposée par l'API Albert
    MAX_BATCH_SIZE = 64
    results = []

    # On découpe la liste 'texts' en morceaux de 64
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i : i + MAX_BATCH_SIZE]

        print(f"[EMBEDDING] Envoi d'un lot de {len(batch)} textes à l'API Albert ({i + len(batch)}/{len(texts)})...")

        response = client.embeddings.create(
            model=settings.albert_embeddings_model_name,
            input=batch,  # On envoie uniquement le lot courant
        )

        # On extrait les embeddings de ce lot et on les ajoute à nos résultats globaux
        for item in response.data:
            results.append({"dense": item.embedding, "sparse": {"indices": [], "values": []}})

    return results
