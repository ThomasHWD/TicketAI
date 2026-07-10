import httpx
from app.config import settings


def generate(question: str, chunks: list[dict]) -> str:
    """
    Génère une réponse via LLM.
    """
    # Construction du contexte à partir des chunks rerankés
    context = "\n\n---\n\n".join([
        f"Source : {c['source']} (score={c['rerank_score']:.3f})\n{c['contenu']}"
        for c in chunks
    ])

    prompt_system = """Tu es un assistant de support interne.
Réponds uniquement à partir des documents fournis dans le contexte.
Si l'information n'est pas dans le contexte, dis-le explicitement.
Ne génère jamais d'information qui ne figure pas dans les sources.
Réponds de manière formelle en français, de façon concise et précise."""

    prompt_user = f"""Contexte :
{context}

Question : {question}

Réponse :"""

    response = httpx.post(
        f"{settings.albert_llm_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.albert_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.albert_llm_model_name,
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": prompt_user}
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        },
        timeout=120
    )
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()
