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
        [
            f"[pertinence={c['rerank_score']:.2f}]\n{c['contenu']}"
            for c in sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        ]
    )

    prompt_system = """Tu es un assistant de support interne.
Réponds uniquement à partir des documents fournis dans le contexte.
Si l'information n'est pas dans le contexte, dis-le explicitement sans inventer.
Appuie-toi en priorité sur les extraits dont la pertinence est la plus élevée.

Règles de format :
- Réponds en français, de manière formelle et concise.
- Utilise des listes à puces (- item) pour énumérer des étapes ou des éléments distincts.
- Utilise des paragraphes courts séparés d'une ligne vide pour les explications.
- N'ajoute pas de titre ni de section si la réponse est courte (1-2 points).
- Ne dépasse pas 300 mots sauf si la question l'exige.
- N'inclus JAMAIS de référence à une source, un fichier, un document ou une citation
  (pas de 【…】, [Source:…], (doc.pdf), etc.).
- Ne mentionne jamais les documents ou extraits dans ta réponse
  (pas de « selon les documents », « d'après les extraits fournis », « dans le contexte », etc.).
  Formule une réponse directe et autonome, comme si tu répondais de toi-même."""

    if historique:
        prompt_system += (
            "\n\nUn historique de conversation est fourni avant la question courante. "
            "Tiens-en compte pour résoudre les références implicites "
            "(« et pour… », « dans ce cas… », pronoms anaphoriques, etc.)."
        )

    historique_block = ""
    if historique:
        lines = "\n".join(f"{m['role'].capitalize()} : {m['content']}" for m in historique)
        historique_block = f"Historique :\n{lines}\n\n"

    prompt_user = f"""Contexte :
{context}

{historique_block}Question : {question}

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


