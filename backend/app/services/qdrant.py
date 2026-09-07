import logging

from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

COLLECTION_NAME = "ticketai"


def init_collection():
    if client.collection_exists(collection_name=COLLECTION_NAME):
        logger.info("Collection '%s' existe déjà.", COLLECTION_NAME)
    else:
        try:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(
                        size=1024,  # BGE-M3
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
            )
            logger.info("Collection '%s' créée.", COLLECTION_NAME)
        except UnexpectedResponse as exc:
            # collection_exists() puis create_collection() n'est pas atomique :
            # avec `uvicorn --workers N`, le lifespan tourne dans chaque process
            # et deux workers peuvent créer la collection en même temps. Le
            # perdant reçoit un 409 et doit converger, pas tuer le démarrage.
            if exc.status_code != 409:
                raise
            logger.info("Collection '%s' créée en parallèle par un autre worker.", COLLECTION_NAME)

    # Index payload pour le filtrage par domaine (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="domaine",
        field_schema="keyword",
    )
    logger.debug("Index payload 'domaine' assuré.")

    # Index payload pour la détection de doublons par hash (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="content_hash",
        field_schema="keyword",
    )
    logger.debug("Index payload 'content_hash' assuré.")

    # Index payload pour cibler un document et une version — sans eux, les filtres
    # (doc_id, version) de la mise à jour dégénèrent en scan complet de la collection.
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="doc_id",
        field_schema="keyword",
    )
    logger.debug("Index payload 'doc_id' assuré.")

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="version",
        field_schema="integer",
    )
    logger.debug("Index payload 'version' assuré.")


def filtre_anciens(doc_id: str, version_cible: int) -> Filter:
    """Les points du document qui ne sont pas ceux de la version en cours d'écriture.

    Utilisé pour la capture *et* pour la suppression afin de porter sur exactement
    le même ensemble, y compris en présence d'un retry partiel.
    Les documents backfillés n'ont pas de clé ``version`` dans leur payload :
    un ``Range`` sur clé absente ne matche pas, d'où le ``must_not`` par valeur.
    """
    return Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))],
        must_not=[FieldCondition(key="version", match=MatchValue(value=version_cible))],
    )


def capturer_chunks(doc_id: str, version_cible: int) -> dict[int, str]:
    """``{chunk_index: contenu}`` de la version sortante, lu dans Qdrant.

    À appeler **avant toute suppression** : c'est la seule source du texte sortant.
    """
    anciens: dict[int, str] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=filtre_anciens(doc_id, version_cible),
            with_payload=["chunk_index", "contenu"],
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for p in points:
            if p.payload and p.payload.get("chunk_index") is not None:
                anciens[p.payload["chunk_index"]] = p.payload.get("contenu") or ""
        if offset is None:
            break
    return anciens


def delete_response_point(reponse_id: str) -> None:
    """Supprime de Qdrant **tous** les points associés à une réponse.

    Sélection par le payload `reponse_id`, et non par l'id déterministe du point.
    C'est ce qui rend le retrait complet : une réponse porte un point par
    formulation validée (`feedback_job(..., formulation_id=...)`), et non plus un
    seul. Supprimer par id ne retirerait que la question d'origine et laisserait
    la réponse servable depuis ses alias — un retrait pour obsolescence ou
    contradiction serait alors sans effet.

    Filtrer sur le payload couvre aussi les points écrits avant l'introduction
    des formulations multiples.
    """
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="reponse_id", match=MatchValue(value=str(reponse_id)))]
        ),
    )


if __name__ == "__main__":
    init_collection()
