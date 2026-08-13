import random

from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

COLLECTION_NAME = "ticketai"


def run_test_upsert():
    print("🚀 Génération de faux vecteurs pour le test...")

    # 1. On simule un vecteur Dense (1024 nombres décimaux au hasard)
    dummy_dense = [random.uniform(-1, 1) for _ in range(1024)]

    # 2. On simule un vecteur Sparse (SPLADE)
    # Dans la vraie vie, ce sont les identifiants des mots importants du dictionnaire et leur poids
    dummy_sparse = {
        "indices": [12, 405, 1024, 8943],  # Identifiants de mots clés
        "values": [0.85, 0.42, 0.91, 0.15],  # Importance de ces mots dans la phrase
    }

    print(f"📥 Insertion du point dans la collection '{COLLECTION_NAME}'...")

    # 3. On pousse le point dans Qdrant
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=1,  # Identifiant unique du point (un entier ou un UUID)
                vector={"dense": dummy_dense, "sparse": dummy_sparse},
                payload={
                    "ticket_id": "TK-101",
                    "question": "Mon écran de PC reste noir après la mise à jour Windows.",
                    "domaine": "IT",
                    "statut": "En attente",
                },
            )
        ],
    )

    print("✅ Upsert réussi ! Le faux ticket a bien été stocké de manière hybride. 🎉")


if __name__ == "__main__":
    run_test_upsert()
