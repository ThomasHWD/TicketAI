import httpx
from app.config import settings

TEI_EMBEDDING_URL = f"http://{settings.qdrant_host}:{settings.qdrant_port}"


async def get_embedding(texts: list[str]) -> list[dict]:
    """
    Retourne une liste de { "dense": [...], "sparse": {"indices": [...], "values": [...]} }
    """
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{TEI_EMBEDDING_URL}/embed", json={"inputs": texts}
        )
        response.raise_for_status()
        return response.json()
