"""Garde anti « cache over-hit » : deux juges LLM avant tout service CANONIQUE.

Une réponse servie en branche CANONIQUE part chez l'employé avec
``statut="VALIDÉE"`` et **aucun validateur humain**. Jusqu'ici, la seule condition
était un score cosinus élevé. La campagne de mesure (cf.
``Docs/garde-cache-canonique.md``) a montré que ce critère est **non informatif** :
AUC 0.000 sur le jeu adversarial, les cas qui doivent partir au RAG scorant *plus
haut* que les cas servables. Le mécanisme est structurel — une paraphrase légitime
change beaucoup de surface (cosinus bas), une négation change trois mots-outils
(cosinus haut). Le classement est *inversé* par rapport à ce qu'on veut.

Deux juges, conjonction stricte, dans cet ordre :

[2] **pertinence** — question ↔ réponse en cache. Couvre la mésattribution et les
    précisions : « la question ajoute-t-elle une condition que la réponse ne
    couvre pas ? » Ne demande aucun extrait, donc s'exécute en premier.
[6] **ancrage** — question ↔ extraits sources ↔ réponse en cache. Vérifie que la
    réponse est *étayée par les documents*, pour la question exactement posée.

**Aucun texte généré n'entre dans le chemin de sécurité**, et ce n'est pas un
détail d'implémentation : mesuré deux fois, le RAG frais HALLUCINE le cas
particulier demandé (« y compris un alternant en contrat d'apprentissage »,
absent des documents). Un juge qui arbitre sur un texte généré est donc plafonné
par le taux d'hallucination du RAG, précisément sur les cas qui comptent.

Les deux invites sont **reprises mot pour mot** de
``scripts/eval_accord_rag_cache.py``. Ce sont les textes exacts qui ont produit le
8/8 avec 0 erreur dangereuse ; les reformuler invaliderait la mesure. Toute
modification doit être remesurée par ce script avant d'être conservée.
"""

import logging
import re
from dataclasses import dataclass

from app.services.llm import chat
from app.services.reranker import rerank

logger = logging.getLogger(__name__)

# Extraits soumis au juge d'ancrage. Cinq, comme dans la mesure — et comme dans
# l'étape de rerank du pipeline RAG, pour que le juge voie ce que le générateur
# aurait vu.
MAX_EXTRAITS = 5

# `max_tokens` est large à dessein : le modèle en service est un modèle À
# RAISONNEMENT, il consomme son budget de sortie dans un champ `reasoning` avant
# d'émettre le moindre `content`. À 64 tokens il rendait 8 verdicts vides sur 8.
MAX_TOKENS_JUGE = 2000
TIMEOUT_JUGE = 60

VERDICT_APPROUVE = "SUFFISANTE_ETAYEE"
VERDICT_INSUFFISANTE = "INSUFFISANTE"
VERDICT_NON_ETAYEE = "NON_ETAYEE"
VERDICT_INDISPONIBLE = "INDISPONIBLE"
VERDICT_SANS_SOURCE = "SANS_SOURCE"

LONGUEUR_JUSTIFICATION = 200

INVITE_PERTINENCE = """Tu es un contrôleur qualité d'un support interne.

On s'apprête à servir à un employé une réponse DÉJÀ VALIDÉE, tirée d'un cache,
sans qu'aucun humain ne la relise. Ton rôle est d'autoriser ou de bloquer.

QUESTION POSÉE :
{question}

RÉPONSE QUE L'ON S'APPRÊTE À SERVIR :
{reponse}

Cette réponse traite-t-elle correctement et complètement CETTE question précise ?

Réponds INSUFFISANTE si la question ajoute une condition, une restriction, une
négation ou un cas particulier que la réponse ne couvre pas — ou si la réponse
serait trompeuse pour cette question précise, même en étant vraie en général.

Réponds SUFFISANTE seulement si servir cette réponse telle quelle est sans risque.

Ne rédige aucune correction. Réponds uniquement par un objet JSON :
{{"verdict": "SUFFISANTE"}} ou {{"verdict": "INSUFFISANTE"}}"""

INVITE_SOURCES = """Tu contrôles le cache de réponses d'un support interne.

Une réponse DÉJÀ VALIDÉE va être servie à un employé sans qu'aucun humain ne la
relise. Tu dois vérifier qu'elle est ENTIÈREMENT ÉTAYÉE par les documents de
référence POUR LA QUESTION EXACTEMENT POSÉE.

QUESTION POSÉE :
{question}

EXTRAITS DES DOCUMENTS DE RÉFÉRENCE (seule source de vérité admise) :
{sources}

RÉPONSE EN CACHE, celle qu'on servirait :
{cachee}

Réponds NON_ETAYEE si l'un de ces points est vrai :
- un élément de la réponse en cache n'apparaît pas dans les extraits ;
- les extraits contredisent la réponse en cache, même partiellement, et en
  particulier sur la polarité (oui / non, autorisé / interdit) ;
- la question porte sur un cas particulier, une condition, une population, une
  période ou une entité dont les extraits ne disent rien. Le silence des documents
  n'autorise JAMAIS à servir : c'est une réponse à donner, pas une lacune à combler.

Réponds ETAYEE seulement si les extraits suffisent à établir que la réponse en cache
répond correctement et complètement à cette question précise.

N'utilise aucune connaissance extérieure aux extraits. Ne rédige aucune correction.
Réponds uniquement par un objet JSON :
{{"verdict": "ETAYEE"}} ou {{"verdict": "NON_ETAYEE"}}"""


@dataclass(frozen=True)
class Verdict:
    """Décision du garde, destinée à être servie ET tracée en base.

    `verdict` et `justification` sont persistés sur la réponse : sans eux, rien
    ne distingue en base une validation humaine d'un service automatique, et le
    taux d'erreur des juges en production reste immesurable.
    """

    autorise: bool
    verdict: str
    justification: str


def autoriser_service_canonique(question: str, reponse_cachee: str, chunks: list[dict]) -> Verdict:
    """Autorise-t-on à servir cette réponse en cache, sans relecture humaine ?

    Conjonction stricte de [2] et [6], court-circuitée au premier refus. Le ET
    (et pas le OU) est imposé par l'asymétrie des coûts : servir à tort expose
    une réponse fausse estampillée VALIDÉE, tandis que bloquer à tort ne fait que
    rendre la main au RAG — c'est-à-dire au comportement actuel du produit.

    **Tout ce qui n'est pas une approbation explicite est un refus** : panne HTTP,
    délai dépassé, JSON illisible, verdict inconnu. Un 429 d'Albert ne doit
    jamais être recyclé en approbation — ça déguiserait une panne de quota en
    feu vert. On ne réessaie pas non plus : le repli (RAG frais) est sûr, et
    réessayer sur un quota saturé ne ferait que retarder ce repli.
    """
    if not reponse_cachee or not reponse_cachee.strip():
        return Verdict(False, VERDICT_SANS_SOURCE, "Réponse en cache vide.")

    # [2] d'abord : il ne demande ni rerank ni extraits. Un refus ici épargne
    # l'appel de rerank et le second appel LLM.
    verdict_2 = _juger(
        INVITE_PERTINENCE,
        {"SUFFISANTE", "INSUFFISANTE"},
        question=question,
        reponse=reponse_cachee,
    )
    if verdict_2 is None:
        return Verdict(False, VERDICT_INDISPONIBLE, "Juge de pertinence indisponible.")
    if verdict_2 != "SUFFISANTE":
        return Verdict(
            False,
            VERDICT_INSUFFISANTE,
            "La réponse en cache ne couvre pas cette question précise.",
        )

    # Garde déterministe et gratuit : sans extrait, il n'y a rien pour étayer.
    # Interroger [6] dans ce cas reviendrait à lui demander de juger sur du vide,
    # et sa consigne (« le silence des documents n'autorise jamais à servir »)
    # impose de toute façon le refus.
    sources = _extraits(question, chunks)
    if not sources:
        return Verdict(False, VERDICT_SANS_SOURCE, "Aucun extrait source pour étayer la réponse.")

    verdict_6 = _juger(
        INVITE_SOURCES,
        {"ETAYEE", "NON_ETAYEE"},
        question=question,
        sources=sources,
        cachee=reponse_cachee,
    )
    if verdict_6 is None:
        return Verdict(False, VERDICT_INDISPONIBLE, "Juge d'ancrage indisponible.")
    if verdict_6 != "ETAYEE":
        return Verdict(
            False,
            VERDICT_NON_ETAYEE,
            "Les documents de référence n'étayent pas la réponse pour cette question.",
        )

    return Verdict(True, VERDICT_APPROUVE, "Réponse pertinente et étayée par les documents.")


def _extraits(question: str, chunks: list[dict]) -> str:
    """Les passages soumis au juge d'ancrage, dans le format mesuré.

    `rerank` renvoie une liste **vide sans lever** quand la réponse d'Albert n'a
    pas la forme attendue (``services/reranker.py``, la branche ``if "results" in
    predictions`` n'a pas de ``else``). Lire ce vide comme « aucun extrait »
    ferait refuser tout le cache le jour où le format de l'API change — une panne
    silencieuse déguisée en prudence. On se rabat donc sur les meilleurs chunks
    de la recherche, exactement comme le fait le script de mesure
    (``rerank(...) or chunks[:5]``).

    Les points de RÉPONSE sont écartés. Qdrant en contient deux espèces : les
    morceaux de documents, et les réponses validées réindexées par
    ``workers/feedback.py`` — ces dernières portent un ``reponse_id`` et, dans
    leur ``contenu``, **le texte de la réponse elle-même**. Les laisser passer
    donnerait au juge d'ancrage la réponse en cache comme preuve d'elle-même :
    une boucle d'auto-confirmation qui viderait [6] de tout contenu, et d'autant
    plus sûrement que le point de la réponse candidate est, par construction,
    le mieux classé de la recherche.
    """
    utiles = [c for c in chunks if c.get("contenu") and not c.get("reponse_id")]
    if not utiles:
        return ""

    try:
        classes = rerank(question, utiles, top_k=MAX_EXTRAITS)
    except Exception as exc:  # noqa: BLE001 — un reranker en panne ne doit pas condamner le cache
        logger.warning("[GARDE] reranker indisponible (%s) — extraits non triés", exc)
        classes = []

    retenus = classes or utiles[:MAX_EXTRAITS]
    return "\n\n".join(f"[extrait {i + 1}] {c['contenu']}" for i, c in enumerate(retenus))


def _juger(invite: str, attendus: set[str], **champs) -> str | None:
    """Un appel à température 0. Renvoie ``None`` sur toute sortie inexploitable.

    Le ``None`` est distinct d'un verdict de refus à dessein : l'appelant le
    trace comme `INDISPONIBLE`, ce qui permet de séparer plus tard, dans les
    données de production, « le juge a refusé » de « le juge n'a pas répondu ».
    Les deux bloquent, mais seul le second est un incident.
    """
    try:
        brut = chat(
            [{"role": "user", "content": invite.format(**champs)}],
            temperature=0,
            max_tokens=MAX_TOKENS_JUGE,
            timeout=TIMEOUT_JUGE,
        )
    except Exception as exc:  # noqa: BLE001 — une panne Albert bloque le cache, elle ne plante pas le job
        logger.warning("[GARDE] échec Albert : %s", str(exc)[:200])
        return None

    trouve = re.search(r'"verdict"\s*:\s*"(\w+)"', brut or "")
    if trouve and trouve.group(1).upper() in attendus:
        return trouve.group(1).upper()

    logger.warning("[GARDE] verdict illisible : %r", (brut or "")[:200])
    return None
