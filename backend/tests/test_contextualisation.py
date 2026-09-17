"""Tests de la contextualisation des chunks (Contextual Retrieval).

Deux propriétés, et rien d'autre :

1. **``texte_indexe`` est la définition unique du texte encodé.** Trois appelants
   la partagent — les deux producteurs de points et le script de ré-encodage des
   vecteurs creux. S'ils divergeaient, la prochaine recalibration BM25
   réécrirait les vecteurs à partir d'un texte que personne n'a jamais indexé,
   sans que rien ne lève.
2. **Une panne rend ``""``, jamais une exception ni un décalage.** La
   contextualisation est un bonus de rappel greffé sur le chemin critique de
   l'ingestion : elle doit pouvoir échouer entièrement sans que l'ingestion s'en
   aperçoive. Et la liste rendue fait toujours la longueur de ``chunks``, parce
   qu'un décalage d'un rang préfixerait chaque passage du sujet de son voisin —
   pire que l'absence de contexte, puisque ça fait trouver le mauvais chunk.

Aucun appel réseau : ``chat`` est remplacé.
"""

import json

import app.services.contextualisation as ctx
import pytest

RESUME = "Note de service sur le télétravail."
GENERALE = "Le télétravail est autorisé du lundi au mercredi."
EXCEPTION = "Les alternants n'en bénéficient pas."


def _chat(reponses, appels: list | None = None):
    """Un faux ``chat`` qui déroule ``reponses`` ; une exception est levée telle quelle."""
    suite = iter(reponses)

    def _appel(messages, **kwargs):
        if appels is not None:
            appels.append(messages)
        valeur = next(suite)
        if isinstance(valeur, Exception):
            raise valeur
        return valeur

    return _appel


# ── 1. La définition unique du texte encodé ────────────────────────────


@pytest.mark.parametrize(
    "contexte, attendu",
    [
        ("Politique de télétravail — exception alternants.",
         "Politique de télétravail — exception alternants.\n\n" + EXCEPTION),
        # Sans locateur, le texte encodé est le chunk **inchangé**, caractère pour
        # caractère : c'est ce qui rend les points antérieurs à ce module exacts.
        ("", EXCEPTION),
        (None, EXCEPTION),
    ],
)
def test_texte_indexe_prefixe_ou_restitue_tel_quel(contexte, attendu):
    assert ctx.texte_indexe(EXCEPTION, contexte) == attendu


def test_le_script_de_reencodage_recompose_ce_que_l_ingestion_a_encode():
    """Le garde-fou du silence : sans lui, réécrire les creux retirerait le contexte.

    ``scripts/reencoder_vecteurs_creux.py`` recalcule les vecteurs creux à partir
    du payload. S'il lisait ``contenu`` seul, chaque recalibration BM25 déferait
    la contextualisation de tout le corpus — et rien ne le signalerait, puisque
    le dense, lui, resterait juste.
    """
    from scripts.reencoder_vecteurs_creux import texte_indexe as depuis_payload

    locateur = "Politique de télétravail — exception alternants."
    charge = {"doc_id": "d1", "contenu": EXCEPTION, "contexte": locateur}
    assert depuis_payload(charge) == ctx.texte_indexe(EXCEPTION, locateur)

    # Un point-réponse est indexé sous sa question, pas sous son contenu : la
    # branche document ne doit pas l'avaler.
    reponse = {"reponse_id": "r1", "contenu": "Oui.", "question_indexee": "Télétravail autorisé ?"}
    assert depuis_payload(reponse) == "Télétravail autorisé ?"


# ── 2. Toute panne rend "", sans lever et sans décaler ─────────────────


@pytest.mark.parametrize(
    "sortie",
    [
        pytest.param("je ne peux pas faire ça", id="pas-de-tableau"),
        pytest.param('["a", "b"', id="json-invalide"),
        pytest.param('["un seul"]', id="longueur-incoherente"),
        pytest.param('{"1": "a", "2": "b"}', id="objet-au-lieu-du-tableau"),
        pytest.param(RuntimeError("429 Too Many Requests"), id="panne-albert"),
    ],
)
def test_un_lot_illisible_rend_des_contextes_vides_sans_lever(sortie, monkeypatch):
    monkeypatch.setattr(ctx, "chat", _chat([sortie]))

    assert ctx.contextualiser([GENERALE, EXCEPTION], RESUME) == ["", ""]


def test_les_locateurs_suivent_l_ordre_des_chunks_et_sont_plafonnes(monkeypatch):
    long = "x" * (ctx.MAX_CARACTERES_CONTEXTE + 50)
    monkeypatch.setattr(ctx, "chat", _chat([json.dumps(["règle générale", long])]))

    obtenus = ctx.contextualiser([GENERALE, EXCEPTION], RESUME)

    assert obtenus[0] == "règle générale"
    assert obtenus[1] == "x" * ctx.MAX_CARACTERES_CONTEXTE


def test_un_lot_en_echec_ne_condamne_que_ses_chunks(monkeypatch):
    """L'isolement par lot : sinon un hoquet sur cinq chunks coûterait tout le document."""
    chunks = [f"chunk {i}" for i in range(2 * ctx.TAILLE_LOT)]
    monkeypatch.setattr(
        ctx,
        "chat",
        _chat([RuntimeError("timeout"), json.dumps([f"loc {i}" for i in range(ctx.TAILLE_LOT)])]),
    )

    obtenus = ctx.contextualiser(chunks, RESUME)

    assert obtenus[: ctx.TAILLE_LOT] == [""] * ctx.TAILLE_LOT
    assert obtenus[ctx.TAILLE_LOT :] == [f"loc {i}" for i in range(ctx.TAILLE_LOT)]


def test_albert_indisponible_cesse_d_appeler_apres_max_echecs(monkeypatch):
    """Un 429 vaut pour la journée : insister ferait attendre le réseau une fois par lot.

    Sans ce coupe-circuit, un quota épuisé transformerait chaque ingestion en
    autant d'attentes réseau qu'il y a de lots — au milieu du chemin critique.
    """
    appels: list = []
    chunks = [f"chunk {i}" for i in range((ctx.MAX_ECHECS + 3) * ctx.TAILLE_LOT)]
    monkeypatch.setattr(ctx, "chat", _chat([RuntimeError("429")] * len(chunks), appels))

    obtenus = ctx.contextualiser(chunks, RESUME)

    assert obtenus == [""] * len(chunks)
    assert len(appels) == ctx.MAX_ECHECS


def test_le_coupe_circuit_n_appelle_pas_albert_du_tout(monkeypatch):
    """`contextualisation_active = false` doit restituer exactement l'état antérieur."""
    appels: list = []
    monkeypatch.setattr(ctx, "chat", _chat(["jamais atteint"] * 5, appels))
    monkeypatch.setattr(ctx.settings, "contextualisation_active", False)

    assert ctx.synopsis("un document", "f.pdf") == ""
    assert ctx.contextualiser([GENERALE, EXCEPTION], "") == ["", ""]
    assert appels == []


def test_synopsis_en_panne_laisse_la_contextualisation_tourner(monkeypatch):
    """Sans ancrage documentaire le locateur est plus pauvre, mais il reste possible.

    Le prompt prévoit le cas (« si un extrait ne se rattache à rien
    d'identifiable, rends une chaîne vide ») : abandonner ici perdrait les
    chunks que leur propre texte suffit à situer.
    """
    appels: list = []
    monkeypatch.setattr(ctx, "chat", _chat([RuntimeError("500"), json.dumps(["loc"])], appels))

    resume = ctx.synopsis("un document", "charte.pdf")

    assert resume == ""
    assert ctx.contextualiser([EXCEPTION], resume) == ["loc"]
    assert "(indisponible)" in appels[1][1]["content"]
