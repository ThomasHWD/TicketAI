"""Le garde anti « cache over-hit » : sa logique de décision, sans réseau.

`chat` et `rerank` sont mockés partout. Ce module ne mesure PAS la qualité des
juges — cela demande le vrai Albert et se fait par `scripts/eval_accord_rag_cache.py`
(opt-in, tokens réels). Il vérifie l'autre moitié, celle qui ne se voit pas dans un
score : que **tout ce qui n'est pas une approbation explicite bloque**.

C'est la propriété qui compte. Un juge qui se trompe une fois sur dix laisse passer
une réponse fausse une fois sur dix ; un repli qui approuve par défaut en laisse
passer 100 % le jour où Albert renvoie des 429. La seconde panne est silencieuse,
et c'est celle que ces tests attrapent.
"""

from unittest.mock import patch

import pytest
from app.services import garde_cache as gc

QUESTION = "Quelle est l'indemnité de télétravail pour un alternant ?"
CACHEE = "L'indemnité de télétravail est de 2,50 € par jour."


def chunk(texte, **extra):
    """Un morceau de document tel que `search_hybrid` le renvoie."""
    base = {
        "contenu": texte,
        "source": "Accord_Teletravail.md",
        "domaine": "RH",
        "doc_id": "doc-1",
        "chunk_index": 0,
        "reponse_id": None,
        "score_cosinus": 0.8,
    }
    base.update(extra)
    return base


CHUNKS = [chunk("L'indemnité forfaitaire de télétravail s'élève à 2,50 € par journée travaillée.")]


def reponses_chat(*verdicts):
    """Fait rendre à `chat` les verdicts donnés, dans l'ordre des appels."""
    return [f'{{"verdict": "{v}"}}' for v in verdicts]


def appeler(*verdicts, chunks=None, rerank_retour=None, rerank_exc=None):
    """Exécute le garde avec des juges scriptés. Renvoie `(verdict, mock_chat)`."""
    chunks = CHUNKS if chunks is None else chunks
    kwargs = {"side_effect": rerank_exc} if rerank_exc else {"return_value": rerank_retour or []}
    with (
        patch.object(gc, "chat", side_effect=reponses_chat(*verdicts)) as faux_chat,
        patch.object(gc, "rerank", **kwargs),
    ):
        return gc.autoriser_service_canonique(QUESTION, CACHEE, chunks), faux_chat


# ══════════════════════════════════════════════════════════════════════════════
# Les deux juges, et leur conjonction
# ══════════════════════════════════════════════════════════════════════════════


def test_les_deux_juges_approuvent_donc_le_cache_sert():
    verdict, faux_chat = appeler("SUFFISANTE", "ETAYEE")

    assert verdict.autorise is True
    assert verdict.verdict == gc.VERDICT_APPROUVE
    assert faux_chat.call_count == 2


def test_le_juge_de_pertinence_refuse_donc_le_cache_ne_sert_pas():
    """[2] couvre la précision : la question ajoute une condition non couverte."""
    verdict, _ = appeler("INSUFFISANTE")

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_INSUFFISANTE


def test_le_juge_d_ancrage_refuse_donc_le_cache_ne_sert_pas():
    """[6] couvre le silence des documents : rien n'étaye le cas demandé."""
    verdict, _ = appeler("SUFFISANTE", "NON_ETAYEE")

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_NON_ETAYEE


def test_un_refus_de_pertinence_court_circuite_le_second_juge():
    """Ordre voulu : [2] d'abord, parce qu'il ne demande ni rerank ni extraits.

    Un refus de [2] épargne donc un appel de reranker ET un second appel LLM. Ce
    n'est pas une optimisation gratuite : [2] est le juge qui refuse le plus souvent
    sur le jeu adversarial, c'est-à-dire précisément dans le cas fréquent.
    """
    _, faux_chat = appeler("INSUFFISANTE")
    assert faux_chat.call_count == 1


def test_le_juge_de_pertinence_ne_voit_jamais_les_extraits():
    """[2] arbitre question ↔ réponse. Lui montrer les documents en ferait un [6] bis.

    Les deux signaux doivent rester indépendants : c'est ce qui rend leur conjonction
    plus sûre que chacun pris seul.
    """
    _, faux_chat = appeler("SUFFISANTE", "ETAYEE")
    invite_2 = faux_chat.call_args_list[0].args[0][0]["content"]

    assert QUESTION in invite_2
    assert CACHEE in invite_2
    assert CHUNKS[0]["contenu"] not in invite_2


# ══════════════════════════════════════════════════════════════════════════════
# Tout ce qui n'est pas une approbation explicite bloque
# ══════════════════════════════════════════════════════════════════════════════


def test_une_sortie_illisible_bloque():
    """Un modèle bavard ou tronqué ne doit jamais valoir approbation.

    `gpt-oss-120b` consomme son budget de sortie dans un champ `reasoning` avant
    d'émettre le moindre `content` : à `max_tokens=64`, il rendait 8 verdicts VIDES
    sur 8. Si le vide était lu comme un feu vert, le cache aurait servi 100 % des
    cas ce jour-là.
    """
    with patch.object(gc, "chat", return_value="Je pense que oui, sans doute."):
        verdict = gc.autoriser_service_canonique(QUESTION, CACHEE, CHUNKS)

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_INDISPONIBLE


def test_un_verdict_hors_vocabulaire_bloque():
    """« PEUT_ETRE » n'est pas dans l'ensemble attendu — donc pas une approbation."""
    with patch.object(gc, "chat", return_value='{"verdict": "PEUT_ETRE"}'):
        verdict = gc.autoriser_service_canonique(QUESTION, CACHEE, CHUNKS)

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_INDISPONIBLE


def test_le_verdict_du_mauvais_juge_ne_passe_pas():
    """« ETAYEE » rendu par [2] n'est pas « SUFFISANTE ».

    Chaque juge a son vocabulaire propre ; les confondre reviendrait à accepter un
    verdict rendu sur une autre question que celle posée.
    """
    with patch.object(gc, "chat", return_value='{"verdict": "ETAYEE"}'):
        verdict = gc.autoriser_service_canonique(QUESTION, CACHEE, CHUNKS)

    assert verdict.autorise is False


@pytest.mark.parametrize(
    "panne",
    [Exception("429 Too Many Requests"), TimeoutError("délai dépassé"), Exception("500 Internal Server Error")],
    ids=["quota", "timeout", "erreur-serveur"],
)
def test_une_panne_albert_bloque_sans_faire_echouer_le_job(panne):
    """Un 429 ne doit JAMAIS être recyclé en approbation.

    Ce serait déguiser une panne de quota en feu vert — le pire mode de défaillance
    possible, puisqu'il frappe massivement et sans trace. Le garde bloque, la
    question part au RAG, et le job continue : la panne coûte un appel LLM de plus,
    pas une réponse fausse servie sans relecture.
    """
    with patch.object(gc, "chat", side_effect=panne):
        verdict = gc.autoriser_service_canonique(QUESTION, CACHEE, CHUNKS)

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_INDISPONIBLE


def test_aucun_extrait_bloque_sans_appeler_le_juge_d_ancrage():
    """Sans document, il n'y a rien pour étayer : le refus est déterministe et gratuit.

    C'est aussi ce qu'imposerait la consigne de [6] (« le silence des documents
    n'autorise JAMAIS à servir »), mais l'obtenir sans appel LLM le rend insensible
    à l'humeur du modèle.
    """
    verdict, faux_chat = appeler("SUFFISANTE", chunks=[])

    assert verdict.autorise is False
    assert verdict.verdict == gc.VERDICT_SANS_SOURCE
    assert faux_chat.call_count == 1  # [2] seulement


def test_une_reponse_en_cache_vide_bloque_sans_aucun_appel():
    """Rien à servir, donc rien à juger — et surtout, rien à payer."""
    with patch.object(gc, "chat") as jamais:
        vide = gc.autoriser_service_canonique(QUESTION, "   ", CHUNKS)

    assert vide.autorise is False
    assert vide.verdict == gc.VERDICT_SANS_SOURCE
    jamais.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# Les extraits soumis au juge d'ancrage
# ══════════════════════════════════════════════════════════════════════════════


def test_les_points_de_reponse_ne_servent_jamais_de_source():
    """Une réponse ne peut pas être sa propre preuve.

    Qdrant contient deux espèces de points : des morceaux de documents, et les
    réponses validées réindexées par `workers/feedback.py`. Ces dernières portent un
    `reponse_id` et, dans leur `contenu`, LE TEXTE DE LA RÉPONSE. Les laisser entrer
    dans les extraits donnerait au juge d'ancrage la réponse en cache comme preuve
    d'elle-même — et d'autant plus sûrement que le point de la réponse candidate est,
    par construction de l'étape 2, le mieux classé de la recherche.

    Ici il ne reste aucun vrai document : le garde doit donc conclure SANS_SOURCE, et
    non interroger [6] sur un extrait auto-confirmant.
    """
    points_reponse = [chunk(CACHEE, reponse_id="11111111-1111-1111-1111-111111111111", doc_id=None)]
    verdict, faux_chat = appeler("SUFFISANTE", chunks=points_reponse)

    assert verdict.verdict == gc.VERDICT_SANS_SOURCE
    assert faux_chat.call_count == 1


def test_un_rerank_vide_ne_vaut_pas_absence_d_extraits():
    """`rerank` renvoie `[]` **sans lever** sur une forme d'API inattendue.

    `services/reranker.py` n'a pas de `else` après `if "results" in predictions`. Lire
    ce vide comme « aucun extrait » ferait refuser TOUT le cache le jour où Albert
    change son format de réponse — une panne totale déguisée en prudence, invisible
    dans les métriques puisque le produit continuerait de répondre. On se rabat donc
    sur les meilleurs chunks de la recherche, comme le fait le script de mesure.
    """
    verdict, faux_chat = appeler("SUFFISANTE", "ETAYEE", rerank_retour=[])

    assert verdict.autorise is True
    assert CHUNKS[0]["contenu"] in faux_chat.call_args_list[1].args[0][0]["content"]


def test_un_reranker_en_panne_ne_condamne_pas_le_cache():
    """Même raisonnement, pour l'exception plutôt que la liste vide."""
    verdict, faux_chat = appeler("SUFFISANTE", "ETAYEE", rerank_exc=Exception("503"))

    assert verdict.autorise is True
    assert CHUNKS[0]["contenu"] in faux_chat.call_args_list[1].args[0][0]["content"]


def test_les_extraits_sont_bornes_a_cinq():
    """Cinq, comme dans la mesure — et comme l'étape de rerank du pipeline RAG.

    Le juge voit ainsi ce que le générateur aurait vu. Au-delà, le prompt se dilue.
    """
    beaucoup = [chunk(f"Paragraphe numéro {i}.") for i in range(15)]
    _, faux_chat = appeler("SUFFISANTE", "ETAYEE", chunks=beaucoup)
    sources = faux_chat.call_args_list[1].args[0][0]["content"]

    assert "[extrait 5]" in sources
    assert "[extrait 6]" not in sources


def test_le_juge_d_ancrage_recoit_la_question_les_sources_et_la_reponse():
    """Les trois termes de [6]. Il n'y a AUCUN texte généré parmi eux.

    C'est la propriété qui a fait passer cette conception de 5/8 à 8/8 : mesuré deux
    fois, le RAG frais hallucine le cas particulier demandé (« y compris un alternant
    en contrat d'apprentissage », absent des documents), et un juge qui arbitre sur un
    texte généré est donc plafonné par le taux d'hallucination du RAG — précisément
    sur les cas qui comptent.
    """
    _, faux_chat = appeler("SUFFISANTE", "ETAYEE")
    invite_6 = faux_chat.call_args_list[1].args[0][0]["content"]

    assert QUESTION in invite_6
    assert CACHEE in invite_6
    assert CHUNKS[0]["contenu"] in invite_6


# ══════════════════════════════════════════════════════════════════════════════
# Réglages d'appel — mesurés, pas décoratifs
# ══════════════════════════════════════════════════════════════════════════════


def test_les_juges_sont_appeles_a_temperature_nulle_et_avec_un_budget_large():
    """`max_tokens=2000` est un résultat de mesure, pas une valeur de confort.

    Le modèle en service est un modèle À RAISONNEMENT : il consomme son budget dans
    un champ `reasoning` avant d'émettre `content`. À 64 tokens, 8 verdicts vides
    sur 8. Baisser ce nombre pour « économiser » rendrait le garde muet — donc
    bloquant à 100 %, donc le cache mort, sans qu'aucune erreur ne soit levée.
    """
    _, faux_chat = appeler("SUFFISANTE", "ETAYEE")

    for appel in faux_chat.call_args_list:
        assert appel.kwargs["temperature"] == 0
        assert appel.kwargs["max_tokens"] >= 2000


def test_les_invites_sont_celles_qui_ont_ete_mesurees():
    """Verrou anti-dérive sur les deux consignes.

    Elles sont reprises mot pour mot de `scripts/eval_accord_rag_cache.py` : ce sont
    les textes exacts qui ont produit le 8/8 avec 0 erreur dangereuse. Les reformuler
    invalide la mesure. Ce test épingle les deux phrases qui portent le comportement
    décisif — le refus sur cas particulier, et le refus sur silence des documents.
    """
    ancrage = " ".join(gc.INVITE_SOURCES.split())
    pertinence = " ".join(gc.INVITE_PERTINENCE.split())

    assert "Le silence des documents n'autorise JAMAIS à servir" in ancrage
    assert "N'utilise aucune connaissance extérieure aux extraits" in ancrage
    assert "une condition, une restriction, une négation ou un cas particulier" in pertinence
    assert "Réponds SUFFISANTE seulement si servir cette réponse telle quelle est sans risque" in pertinence
