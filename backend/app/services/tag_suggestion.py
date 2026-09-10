import logging
import re

from app.config import settings
from app.services.llm import chat
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PROMPT_SYSTEME_BASE = (
    "Tu es un assistant de classification pour un helpdesk interne (RH, IT, Légal). "
    "On te donne une question et une réponse. "
    "Propose un tag généraliste en français (1 à 3 mots) qui désigne le thème principal. "
    "Règles :\n"
    "- Le tag doit nommer la CATÉGORIE thématique, pas l'objet précis de la question.\n"
    "- Choisis le terme le plus court et le plus large possible.\n"
    "- Mauvais exemples (trop spécifiques) : « Carte Swile », « heures supplémentaires », "
    "« télétravail matériel » — ces termes décrivent la question, pas le thème.\n"
    "- Bons exemples : « ticket restaurant », « horaires », « télétravail », "
    "« congés », « transport », « paie », « mutuelle ».\n"
    "- Pas de caractère spécial, uniquement des lettres et des espaces.\n"
    "- Réponds uniquement avec le tag, rien d'autre."
)


def _construire_prompt(tags_existants: list[str] | None) -> str:
    if not tags_existants:
        return _PROMPT_SYSTEME_BASE
    liste = ", ".join(f"« {t} »" for t in tags_existants)
    return (
        _PROMPT_SYSTEME_BASE
        + f"\n\nTags déjà utilisés dans ce domaine : {liste}. "
        "Si l'un d'eux couvre déjà ce thème, utilise-le tel quel. "
        "N'en crée un nouveau que si aucun ne convient."
    )


def suggerer_tag(
    question: str,
    contenu: str,
    db: Session,
    tags_existants: list[str] | None = None,
) -> str | None:
    try:
        prompt = _construire_prompt(tags_existants)
        message_user = f"Question : {question}\n\nRéponse : {contenu[:800]}"
        tag = chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message_user},
            ],
            temperature=0,
            max_tokens=20,
            timeout=15,
            model=settings.albert_tag_model_name,
        )
        tag = re.sub(r"[\"'`_\-/\\|«»]", " ", tag)
        tag = re.sub(r"\s+", " ", tag).strip()
        return tag[:100] if tag else None
    except Exception as exc:
        logger.warning("Échec suggestion de tag : %s", exc)
        return None
