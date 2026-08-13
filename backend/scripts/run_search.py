import random

from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.models import Fusion, FusionQuery, Prefetch

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

COLLECTION_NAME = "ticketai"


def test_hybrid_search():
    print("🔍 Préparation d'une requête de recherche hybride...")

    # 1. On simule un vecteur de recherche Dense (la question de l'utilisateur convertie en 1024 floats)
    query_dense = [random.uniform(-1, 1) for _ in range(1024)]

    # 2. On simule un vecteur de recherche Sparse (les mots importants de sa question)
    # On glisse l'indice 1024 (qu'on a inséré dans le script précédent) pour forcer Qdrant à trouver une correspondance
    query_sparse = {"indices": [1024, 9999], "values": [0.95, 0.05]}

    print("📡 Envoi de la requête hybride (Dense + Sparse + RRF) à Qdrant...")

    # 3. L'API moderne de Qdrant utilise query_points et le paramètre 'prefetch' pour l'hybride
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            # Étape A : Recherche sémantique pure sur le vecteur dense
            Prefetch(query=query_dense, using="dense", limit=5),
            # Étape B : Recherche par mots-clés pure sur le vecteur sparse
            Prefetch(query=query_sparse, using="sparse", limit=5),
        ],
        # Étape C : On demande à Qdrant de fusionner les rangs des étapes A et B avec RRF
        query=FusionQuery(fusion=Fusion.RRF),
        limit=5,
    )

    print(f"\n🎯 Résultats renvoyés par la fusion RRF : {len(response.points)} ticket(s) trouvé(s).")

    for point in response.points:
        print(f"\n📌 Point ID: {point.id} | Score de confiance RRF: {point.score:.4f}")
        print(f"📄 Contenu du ticket (Payload): {point.payload}")


if __name__ == "__main__":
    test_hybrid_search()
