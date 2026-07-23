import httpx
from app.config import settings


def generate(
    question: str,
    chunks: list[dict],
    historique: list[dict] | None = None,
) -> str:
    """
    Génère une réponse via LLM.

    `historique` (optionnel) : messages alternés {"role": "user"|"assistant",
    "content": ...} des tours précédents du fil. Fourni pour une précision
    (suivi) afin que le LLM interprète la question courante dans son contexte.
    """
    # Construction du contexte à partir des chunks rerankés
    context = "\n\n---\n\n".join(
        [f"Source : {c['source']} (score={c['rerank_score']:.3f})\n{c['contenu']}" for c in chunks]
    )

    prompt_system = """Tu es un assistant de support interne.
Réponds uniquement à partir des documents fournis dans le contexte.
Si l'information n'est pas dans le contexte, dis-le explicitement.
Ne génère jamais d'information qui ne figure pas dans les sources.
Réponds de manière formelle en français, de façon concise et précise."""

    if historique:
        prompt_system += (
            "\nUn historique de conversation précède la question ; tiens-en "
            "compte pour interpréter la question courante et les références "
            "implicites (« et pour… », « dans ce cas… »)."
        )

    prompt_user = f"""Contexte :
{context}

Question : {question}

Réponse :"""

    messages = [
        {"role": "system", "content": prompt_system},
        *(historique or []),
        {"role": "user", "content": prompt_user},
    ]

    response = httpx.post(
        f"{settings.albert_llm_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.albert_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.albert_llm_model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 512,
        },
        timeout=120,
    )
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()
