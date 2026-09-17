import logging

import httpx
from app.config import settings

logger = logging.getLogger(__name__)


def chat(
    messages: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 512,
    timeout: float = 120,
    model: str | None = None,
) -> str:
    """Appel brut au ``/chat/completions`` d'Albert, sans prompt imposé.

    Extrait de ``generate`` pour que la ré-vérification puisse poser sa propre
    question au modèle — un verdict JSON, pas une réponse d'assistant — sans
    hériter du prompt système RAG ni de l'exigence d'un ``rerank_score`` sur
    chaque chunk. ``generate`` reste l'unique appelant côté pipeline RAG et son
    comportement est inchangé.
    """
    response = httpx.post(
        f"{settings.albert_llm_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.albert_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or settings.albert_llm_model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    content = (data["choices"][0]["message"]["content"] or "").strip()
    if not content:
        logger.warning("Réponse LLM vide — body complet : %s", data)
    return content


_HORS_DOMAINE_MARKER = "[HORS_DOMAINE]"


def generate(
    question: str,
    chunks: list[dict],
    historique: list[dict] | None = None,
) -> tuple[str, bool]:
    """
    Génère une réponse via LLM.

    Retourne ``(contenu, hors_domaine)`` où ``hors_domaine`` est True quand le LLM
    signale qu'il ne dispose pas du contexte pour répondre.

    `historique` (optionnel) : messages alternés {"role": "user"|"assistant",
    "content": ...} des tours précédents du fil. Fourni pour une précision
    (suivi) afin que le LLM interprète la question courante dans son contexte.
    """
    # Construction du contexte à partir des chunks rerankés.
    # `contenu_indexe` est le texte réellement encodé : le chunk précédé du
    # locateur qui le situe dans son document (cf. services/contextualisation.py).
    # Le montrer au modèle est ce qui rend exploitable un passage autrement opaque
    # (« les intéressés en sont exclus » — exclus de quoi ?). Le prompt système
    # interdit par ailleurs d'ajouter le moindre fait absent du contexte, et le
    # locateur est plafonné à 200 caractères : il situe, il n'affirme pas.
    # Repli sur `contenu` pour les points indexés avant ce champ.
    context = "\n\n---\n\n".join(
        [
            f"[pertinence={c['rerank_score']:.2f}]\n{c.get('contenu_indexe') or c['contenu']}"
            for c in sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        ]
    )

    prompt_system = """Tu es un assistant de support interne.
Réponds uniquement à partir des documents fournis dans le contexte.
Si l'information n'est pas dans le contexte fourni, commence ta réponse EXACTEMENT par \
"[HORS_DOMAINE]" puis explique brièvement à l'utilisateur ce que tu n'as pas pu trouver, \
sans mentionner le contexte ni les documents. N'invente rien.

Hiérarchie des règles : si le contexte contient à la fois une règle générale et une règle plus \
spécifique (exception, restriction ou condition visant une population, un statut ou un cas \
particulier), la règle spécifique l'emporte sur la générale. Énonce la règle générale, puis \
l'exception qui s'applique. Si la question vise explicitement un cas particulier et qu'aucun \
extrait ne le traite, dis-le au lieu d'appliquer la règle générale par défaut.

Appuie-toi en priorité sur les extraits dont la pertinence est la plus élevée.
Ne décris aucune étape, aucun champ de formulaire, aucune option d'interface et aucune pièce \
à fournir qui ne figure pas explicitement dans le contexte. Sur une procédure, un détail \
plausible mais absent des extraits est une erreur, pas une aide : reste au niveau de ce que \
le contexte affirme, quitte à être moins précis.

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

    texte = chat(messages, temperature=0.1, max_tokens=512, timeout=120)
    hors_domaine = texte.startswith(_HORS_DOMAINE_MARKER)
    if hors_domaine:
        texte = texte[len(_HORS_DOMAINE_MARKER):].lstrip()
    return texte, hors_domaine
