"""« Cache over-hit » : quand une question précisée est interceptée par le cache.

Un utilisateur pose une question générique. Elle est répondue, validée trois fois,
promue canonique, et le TEXTE DE SA QUESTION est indexé dans Qdrant avec le
payload `reponse_id`. Plus tard, quelqu'un pose la variante *précisée* — « …pour
un alternant ? », « …qui **ne sont pas** marqués Personnel ? ». Le delta lexical
est minuscule, le cosinus quasi identique : le cache intercepte et sert la réponse
**générique** en `statut=VALIDÉE`, sans aucune revue humaine.

**Le défaut décrit ci-dessus est corrigé.** Il l'est par le garde
(`app/services/garde_cache.py`) : deux juges LLM en conjonction stricte devant la
branche CANONIQUE, et un cosinus qui cesse de gouverner quoi que ce soit — mesuré
non informatif, AUC 0.000, avec un classement *inversé*. Les deux
`xfail(strict=True)` que portait ce module ont donc disparu : ils exigeaient qu'une
précision aille toujours en SUGGESTION, ce qui n'est plus la spécification. Une
précision est servie **si et seulement si** les juges l'approuvent. Voir
`Docs/garde-cache-canonique.md` avant de toucher aux seuils ou aux prompts.

Ce module couvre l'étage déterministe : zéro réseau, zéro base, session mockée —
le garde y est toujours mocké, ses propres tests sont dans `test_garde_cache.py`.

Les cellules `statut` / `obsolete` ne sont **pas** ici : elles sont filtrées par un
`WHERE` SQL et n'atteignent jamais le code Python testé. Une session mockée
renverrait ce qu'on lui a soufflé et prouverait zéro. Elles vivent dans
`test_cache_over_hit_db.py`, contre un vrai Postgres.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from app.models.reponse import Reponse
from app.services import question_pipeline as qp

from .helpers_cosinus import DIM, VECTEUR_REQUETE, chunk_factice, produit_scalaire, vecteur_a_cosinus
from .test_question_logic import make_db, make_reponse, make_ticket

SEUIL_CAND = qp.SEUIL_CANDIDAT_CANONIQUE  # 0.70 — plancher de candidature canonique
SEUIL_SUG = qp.SEUIL_SUGGESTION  # 0.85 — plancher de candidature non canonique

# Un score franchement haut, pour les tests où le score n'est plus ce qui décide.
# Il n'y a plus de « seuil canonique » : depuis le câblage du garde
# (`services/garde_cache.py`), c'est le verdict des juges qui ouvre la branche
# CANONIQUE. Le cosinus a été mesuré non informatif sur ce jeu (AUC 0.000) — il
# classait même les cas à servir SOUS les cas à envoyer au RAG.
SCORE_HAUT = 0.95


@pytest.fixture(autouse=True)
def _pas_de_reseau(monkeypatch):
    """Neutralise le SSE — sans quoi ces tests sont lents *et* faussement verts.

    `broadcast_sync` est lié au niveau module (`question_pipeline.py:16`) : c'est
    la seule cible efficace. Non neutralisé, il ouvre un `redis.from_url(...,
    socket_connect_timeout=2)` par appel et **avale l'échec dans son propre
    try/except** (`app/services/broadcast.py`). Les tests passeraient donc — à
    deux secondes pièce, sans que rien ne signale qu'ils parlent au réseau.
    """
    monkeypatch.setattr(qp, "broadcast_sync", lambda *a, **k: None)


def servir(score, *, canonique, autoriser, est_suivi=False, db=None, reponse=None):
    """Appelle `servir_reutilisation` et renvoie (résultat, db, réponse source)."""
    db = db or make_db()
    reponse = reponse or make_reponse(canonique=canonique, contenu="Réponse générique")
    resultat = qp.servir_reutilisation(
        db,
        uuid.uuid4(),  # job_id
        None,  # ticket_uuid → création d'un ticket neuf
        "Question posée ?",
        "IT",
        None,  # user_uuid None → pas de Notification à construire
        reponse,
        score,
        "précision" if est_suivi else None,
        est_suivi,
        0,
        autoriser,
        None,  # objet
        garde_verdict="SUFFISANTE_ETAYEE" if autoriser else None,
        garde_justification="verdict de test" if autoriser else None,
    )
    return resultat, db, reponse


def reponse_creee(db) -> Reponse:
    """La `Reponse` réellement passée à `db.add` par le pipeline."""
    ajoutees = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], Reponse)]
    assert ajoutees, "aucune Reponse ajoutée à la session"
    return ajoutees[-1]


# ══════════════════════════════════════════════════════════════════════════════
# Frontière de branche — `servir_reutilisation`
# Ce n'est plus le SCORE qui ouvre CANONIQUE, c'est le VERDICT du garde.
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("score", [0.20, 0.71, 0.849, SEUIL_SUG, 0.899, SCORE_HAUT, 1.0])
def test_le_score_ne_gouverne_plus_la_branche_canonique(score):
    """À verdict favorable, tout score sort CANONIQUE. À verdict défavorable, aucun.

    Inversion délibérée de l'invariant précédent, qui exigeait un cosinus au-dessus
    de 0.90. La mesure (`scripts/eval_accord_rag_cache.py`) a montré que ce cosinus
    ne porte **aucune** information de correction — AUC 0.000, avec un classement
    *inversé* : `nikon-mail-non-marque` (« les e-mails qui **ne sont pas** marqués
    Personnel ») scorait 0.9589 et devait partir au RAG, tandis que des
    reformulations parfaitement servables scoraient 0.71.

    Le garde est donc la seule condition ; le score n'est plus qu'un sélecteur de
    candidat, en amont, dans `trouver_reponse_reutilisable`.
    """
    autorise, _, _ = servir(score, canonique=True, autoriser=True)
    refuse, _, _ = servir(score, canonique=True, autoriser=False)

    assert autorise["branche"] == "CANONIQUE"
    assert refuse["branche"] == "SUGGESTION"


@pytest.mark.parametrize(
    ("canonique", "autoriser"),
    [(True, False), (False, True)],
    ids=["garde-refuse", "non-canonique"],
)
def test_les_deux_conditions_de_la_branche_canonique_sont_conjonctives(canonique, autoriser):
    """Il en reste deux, et il faut les deux : `autoriser_canonique AND canonique`.

    La troisième — `score_liee >= SEUIL_COSINUS` — a été retirée. Ce test tient la
    conjonction restante, pour qu'un futur `or` mal placé ne passe pas inaperçu.
    """
    resultat, _, _ = servir(SCORE_HAUT, canonique=canonique, autoriser=autoriser)
    assert resultat["branche"] == "SUGGESTION"


def test_un_verdict_favorable_designe_bien_la_reponse_source():
    resultat, _, source = servir(SCORE_HAUT, canonique=True, autoriser=True)
    assert resultat["branche"] == "CANONIQUE"
    assert resultat["reponse_source_id"] == str(source.id)


def test_la_branche_suggestion_n_a_toujours_aucun_garde_bas():
    """SUGGESTION reste la branche **par défaut**, quel que soit le cosinus.

    Tout ce qui n'entre pas dans le `if` y tombe. Appelée directement avec 0.20, la
    fonction propose donc à un validateur une réponse sans rapport avec la question.
    Le filtrage bas repose entièrement sur `trouver_reponse_reutilisable`
    (`SEUIL_SUGGESTION` pour les non-canoniques) : les deux fonctions sont couplées
    par une convention non écrite, pas par un contrat vérifié.

    Ce couplage n'a PAS été corrigé par le garde, et il faut le savoir : le garde ne
    s'interpose que devant CANONIQUE. La branche SUGGESTION reste sans juge — c'est
    assumé, elle passe par un validateur humain.

    Test de caractérisation : il documente le couplage, il ne le condamne pas.
    """
    resultat, _, _ = servir(0.20, canonique=True, autoriser=False)
    assert resultat["branche"] == "SUGGESTION"
    assert resultat["top_score_cosinus"] == 0.20


def test_contenu_corrige_prime_sur_le_contenu_original():
    """La correction d'un validateur est ce qui est resservi."""
    reponse = make_reponse(canonique=True, contenu="Version initiale", contenu_corrige="Version corrigée")
    resultat, _, _ = servir(SCORE_HAUT, canonique=True, autoriser=True, reponse=reponse)
    assert resultat["reponse"] == "Version corrigée"


# ══════════════════════════════════════════════════════════════════════════════
# Sélection du candidat — `trouver_reponse_reutilisable` (parties pures)
# ══════════════════════════════════════════════════════════════════════════════


def test_sous_le_plancher_le_plus_bas_la_base_n_est_jamais_interrogee():
    """Le retour anticipé évite un aller-retour SQL par question sans candidat.

    Sans lui, chaque question du parc paierait une requête Postgres pour rien. Le
    plancher qui déclenche la requête est désormais le PLUS BAS des deux (0.70) :
    la canonicité d'un candidat n'est connue qu'après la requête.
    """
    db = make_db()
    chunks = [chunk_factice(0.6999, reponse_id=str(uuid.uuid4()))]

    assert qp.trouver_reponse_reutilisable(db, chunks) == (None, None)
    db.query.assert_not_called()


def test_les_deux_planchers_sont_decouples():
    """Ils ne dérivent plus l'un de l'autre, et c'est le cœur du correctif.

    L'ancien code écrivait `SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05`. Ce couplage
    rendait impossible d'abaisser le plancher de candidature sans abaisser du même
    coup la porte du service sans revue humaine — l'inverse du but recherché. Il
    était aussi arithmétiquement fragile : `0.90 - 0.05 == 0.85` est exact en
    float64, mais `0.85 - 0.05` vaut 0.7999999999999999.
    """
    assert SEUIL_CAND == 0.70
    assert SEUIL_SUG == 0.85
    assert not hasattr(qp, "SEUIL_COSINUS"), "constante retirée : elle ne gouverne plus rien"


def test_un_candidat_canonique_est_retenu_des_0_70():
    """Le plancher bas est la raison d'être du correctif.

    Les trois reformulations légitimes mesurées scorent 0.7116 / 0.7510 / 0.7822 :
    sous l'ancien plancher de 0.85, elles n'étaient jamais candidates et le garde ne
    les voyait **jamais**. Elles partaient au RAG et attendaient un validateur.
    """
    reponse = make_reponse(canonique=True)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    trouvee, score = qp.trouver_reponse_reutilisable(db, [chunk_factice(SEUIL_CAND, reponse_id=str(reponse.id))])
    assert trouvee is reponse
    assert score == SEUIL_CAND


def test_un_candidat_non_canonique_reste_ecarte_sous_0_85():
    """Le plancher bas ne s'applique QU'aux canoniques.

    Une réponse validée non canonique sort en SUGGESTION, sans passer devant le
    garde — aucun juge ne filtre cette branche. Lui appliquer le plancher de 0.70
    mettrait sous les yeux du validateur une masse de réponses génériques hors sujet
    à la place d'une réponse RAG ciblée.

    Le candidat franchit bien le plancher bas (la requête SQL a lieu), et c'est
    l'écartage postérieur qui le rejette.
    """
    reponse = make_reponse(canonique=False)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    assert qp.trouver_reponse_reutilisable(db, [chunk_factice(0.75, reponse_id=str(reponse.id))]) == (None, None)
    db.query.assert_called()


def test_au_seuil_suggestion_exact_le_candidat_non_canonique_est_retenu():
    """0.85 pile est retenu — la comparaison est `>=`, pas `>`."""
    reponse = make_reponse(canonique=False)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    trouvee, score = qp.trouver_reponse_reutilisable(db, [chunk_factice(SEUIL_SUG, reponse_id=str(reponse.id))])
    assert trouvee is reponse
    assert score == SEUIL_SUG


def test_un_canonique_faible_ne_masque_pas_un_non_canonique_fort():
    """L'écartage par plancher précède le départage, il ne le contourne pas.

    Un canonique à 0.72 est un candidat légitime (il ira devant le garde) et
    `canonique` étant la première clé de tri, il bat un non-canonique à 0.99. C'est
    volontaire : si le garde l'approuve, la réponse est servie sans revue ; s'il le
    refuse, le flux part au RAG — jamais vers le non-canonique.
    """
    cano = make_reponse(canonique=True)
    autre = make_reponse(canonique=False)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [cano, autre]

    trouvee, score = qp.trouver_reponse_reutilisable(
        db,
        [chunk_factice(0.72, reponse_id=str(cano.id)), chunk_factice(0.99, reponse_id=str(autre.id))],
    )
    assert trouvee is cano
    assert score == 0.72


def test_un_chunk_documentaire_sans_reponse_id_n_est_jamais_un_candidat():
    """Un chunk de document brut, même à 0.99, n'est pas une réponse validée.

    Seuls les points réindexés par `feedback_job` portent un `reponse_id`.
    """
    db = make_db()
    assert qp.trouver_reponse_reutilisable(db, [chunk_factice(0.99, reponse_id=None)]) == (None, None)
    db.query.assert_not_called()


def test_le_score_retenu_est_le_max_sur_tous_les_chunks_de_la_reponse():
    """Le score qui décide n'est pas celui du top-1 : c'est un `max` sur les 15 chunks.

    Conséquence directe sur l'over-hit : plus le corpus canonique grossit, plus ce
    maximum monte à seuil constant. Un cache sûr à 50 réponses ne l'est pas à 5 000
    — c'est une statistique d'extremum, pas une similarité.
    """
    reponse = make_reponse()
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [reponse]
    rid = str(reponse.id)

    _, score = qp.trouver_reponse_reutilisable(
        db,
        [chunk_factice(0.86, reponse_id=rid), chunk_factice(0.93, reponse_id=rid), chunk_factice(0.88, reponse_id=rid)],
    )
    assert score == 0.93


def test_le_canonique_bat_le_mieux_note():
    """`canonique` est la première clé de tri (L172) : il prime sur le score."""
    a = make_reponse(canonique=True, nb_validations=3)
    b = make_reponse(canonique=False, nb_validations=99)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [a, b]

    trouvee, _ = qp.trouver_reponse_reutilisable(
        db,
        [chunk_factice(0.86, reponse_id=str(a.id)), chunk_factice(0.99, reponse_id=str(b.id))],
    )
    assert trouvee is a


def test_nb_validations_prime_sur_la_similarite():
    """À canonicité égale, la réponse la plus validée gagne — même moins pertinente.

    **Second fond du problème d'over-hit.** Une réponse générique validée cinq fois
    bat une réponse spécifique à 0.99 de similarité. Relever `SEUIL_COSINUS` ne
    corrige pas cet ordre : le seuil décide *si* on sert depuis le cache, ce tri
    décide *quoi*. Deux leviers distincts, dont un seul est configurable.
    """
    populaire = make_reponse(canonique=True, nb_validations=5)
    pertinente = make_reponse(canonique=True, nb_validations=1)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [populaire, pertinente]

    trouvee, score = qp.trouver_reponse_reutilisable(
        db,
        [chunk_factice(0.86, reponse_id=str(populaire.id)), chunk_factice(0.99, reponse_id=str(pertinente.id))],
    )
    assert trouvee is populaire
    assert score == 0.86


def test_egalite_parfaite_tranchee_par_l_uuid_donc_deterministe():
    """Dernière clé de tri : `str(id)`. Aucun départage aléatoire (L176).

    Sans elle, deux réponses ex æquo donneraient une réponse différente à chaque
    appel pour une même question — un cache non déterministe.
    """
    a = make_reponse(canonique=True, nb_validations=2)
    b = make_reponse(canonique=True, nb_validations=2)
    db = make_db()
    db.query.return_value.filter.return_value.all.return_value = [a, b]

    attendue = max([a, b], key=lambda r: str(r.id))
    trouvee, _ = qp.trouver_reponse_reutilisable(
        db,
        [chunk_factice(0.95, reponse_id=str(a.id)), chunk_factice(0.95, reponse_id=str(b.id))],
    )
    assert trouvee is attendue


# ══════════════════════════════════════════════════════════════════════════════
# Le câblage du garde dans le worker — questions initiales ET précisions
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def worker_isole(monkeypatch):
    """Isole `question_job` de la base et du réseau, sans toucher sa logique.

    Tout ce que le worker importe au niveau module est rebindé dans
    `app.workers.question` — pas dans le module d'origine, qui ne serait pas relu.
    """
    import app.workers.question as wq

    def _session():
        # `first()` doit rendre un ticket : quand le garde refuse, le flux continue
        # jusqu'à `upsert_ticket`, qui lève `TicketDisparu` sur un `None` — le job
        # serait alors « IGNORÉ » et le test lirait une absence de branche au lieu
        # du repli au RAG qu'il prétend vérifier.
        db = make_db()
        db.query.return_value.filter.return_value.first.return_value = make_ticket()
        return db

    monkeypatch.setattr(wq, "ticket_existe", lambda _: True)
    monkeypatch.setattr(wq, "charger_contexte_fil", lambda tid, q: ([], q))
    monkeypatch.setattr(wq, "SessionLocal", _session)
    return wq


def _verdict(autorise, nom="SUFFISANTE_ETAYEE"):
    from app.services.garde_cache import Verdict

    return Verdict(autorise, nom if autorise else "INSUFFISANTE", "justification de test")


def _lancer(worker, question, *, reponse, verdict, ticket_id=None):
    """Fait tourner `question_job` jusqu'à la décision, et capture ce qu'elle vaut.

    Renvoie `(appels_servir, verdict_garde)` : la liste des appels reçus par
    `servir_reutilisation` — vide si le flux est parti au RAG — et le `Verdict`
    passé au worker.
    """
    appels = []

    def _capturer(*args, **kwargs):
        appels.append((args, kwargs))
        return {"branche": "CANONIQUE"}

    with (
        patch.object(worker, "search_hybrid", return_value=[chunk_factice(0.95, reponse_id=str(reponse.id))]),
        patch.object(worker, "trouver_reponse_reutilisable", return_value=(reponse, 0.95)),
        patch.object(worker, "autoriser_service_canonique", return_value=verdict) as juge,
        patch.object(worker, "servir_reutilisation", side_effect=_capturer),
        patch.object(worker, "rerank", return_value=[]),
        patch.object(worker, "generate", return_value=("réponse fraîche du RAG", False)),
    ):
        kwargs = {"ticket_id": ticket_id} if ticket_id else {}
        resultat = worker.question_job.apply(args=[question, "RH", None], kwargs=kwargs, throw=True).get()

    return appels, juge, resultat


def test_une_question_initiale_approuvee_par_le_garde_sort_canonique(worker_isole):
    """Le cas nominal : le cache sert sans revue humaine quand les juges approuvent."""
    reponse = make_reponse(canonique=True)
    appels, juge, _ = _lancer(worker_isole, "Question initiale ?", reponse=reponse, verdict=_verdict(True))

    juge.assert_called_once()
    assert appels, "servir_reutilisation aurait dû être appelée"
    args, kwargs = appels[0]
    assert args[11] is True  # autoriser_canonique
    assert kwargs["garde_verdict"] == "SUFFISANTE_ETAYEE"


def test_une_question_initiale_refusee_par_le_garde_part_au_rag(worker_isole):
    """Un refus rend la main au RAG — il ne dégrade PAS en SUGGESTION.

    Le garde vient de constater que cette réponse ne traite pas correctement cette
    question. La proposer en SUGGESTION mettrait sous les yeux du validateur une
    réponse connue pour être inadaptée, à la place d'une réponse fraîche et ciblée.
    C'est aussi la sémantique exacte des scripts de mesure (« SERT » vs « rag ») :
    toute autre lecture invaliderait le 8/8 mesuré.
    """
    reponse = make_reponse(canonique=True)
    appels, juge, resultat = _lancer(
        worker_isole, "Les e-mails non marqués Personnel ?", reponse=reponse, verdict=_verdict(False)
    )

    juge.assert_called_once()
    assert appels == [], "un refus ne doit pas passer par servir_reutilisation"
    assert resultat["branche"] == "RAG"


def test_une_precision_approuvee_par_le_garde_sort_canonique(worker_isole):
    """Une précision n'est plus condamnée d'office à la revue humaine.

    C'est le cœur de la demande. L'ancien correctif envisagé — interdire CANONIQUE
    dès que `est_suivi` — aurait vidé la fonctionnalité de son intérêt : toute
    reformulation légitime aurait attendu un validateur. Le traitement est donc
    strictement identique à celui d'une question initiale, seul le texte soumis aux
    juges diffère (le fil concaténé, et non la seule précision).
    """
    reponse = make_reponse(canonique=True)
    appels, juge, _ = _lancer(
        worker_isole,
        "Et le montant, c'est combien ?",
        reponse=reponse,
        verdict=_verdict(True),
        ticket_id=str(uuid.uuid4()),
    )

    juge.assert_called_once()
    assert appels and appels[0][0][11] is True


def test_une_precision_refusee_par_le_garde_part_au_rag(worker_isole):
    """Le défaut historique, corrigé : `workers/question.py` passait `True` en dur.

    Une précision dont le cosinus dépassait 0.90 — « Et pour un alternant ? » sur une
    réponse générique — sortait CANONIQUE/VALIDÉE sans revue humaine. Ce test est le
    jumeau unitaire de `test_cache_over_hit_qdrant.py`, qui vérifie la branche
    réellement rendue à travers un vrai Qdrant et un vrai Postgres.
    """
    reponse = make_reponse(canonique=True)
    appels, _, resultat = _lancer(
        worker_isole,
        "Et pour un alternant ?",
        reponse=reponse,
        verdict=_verdict(False),
        ticket_id=str(uuid.uuid4()),
    )

    assert appels == []
    assert resultat["branche"] == "RAG"


def test_un_candidat_non_canonique_ne_reveille_jamais_le_garde(worker_isole):
    """Deux appels LLM par SUGGESTION seraient payés pour rien.

    La branche SUGGESTION passe par un validateur humain : le risque que le garde
    couvre — servir sans relecture — n'y existe pas.
    """
    reponse = make_reponse(canonique=False)
    appels, juge, _ = _lancer(worker_isole, "Question ?", reponse=reponse, verdict=_verdict(True))

    juge.assert_not_called()
    assert appels and appels[0][0][11] is False


def test_le_garde_juge_le_fil_complet_et_non_la_seule_precision(worker_isole, monkeypatch):
    """« Et pour un alternant ? » est intelligible dans le fil, insensé isolé.

    `charger_contexte_fil` concatène les intentions utilisateur du ticket. C'est
    cette concaténation — et non la précision brute — qui doit être soumise aux
    juges : sans elle, [2] ne peut que refuser, et le cache serait mort sur tous
    les suivis.
    """
    monkeypatch.setattr(
        worker_isole,
        "charger_contexte_fil",
        lambda tid, q: ([], f"Quelle indemnité de télétravail ?\n{q}"),
    )
    reponse = make_reponse(canonique=True)
    _, juge, _ = _lancer(
        worker_isole,
        "Et pour un alternant ?",
        reponse=reponse,
        verdict=_verdict(True),
        ticket_id=str(uuid.uuid4()),
    )

    question_jugee = juge.call_args.args[0]
    assert "Quelle indemnité de télétravail ?" in question_jugee
    assert "Et pour un alternant ?" in question_jugee


def test_une_reponse_canonique_porte_desormais_la_trace_de_son_verdict():
    """Le trou d'audit est comblé — partiellement, et il faut savoir jusqu'où.

    La branche CANONIQUE écrit toujours `statut="VALIDÉE"` sans `validator_id` ni
    `validated_at` : sur ces trois colonnes, une réponse servie par le cache reste
    indiscernable d'une validation humaine. Ce qui la distingue désormais, ce sont
    `garde_verdict` / `garde_justification`, non nuls pour elle seule. Sans eux, le
    taux d'erreur des juges en production était immesurable.
    """
    _, db, _ = servir(SCORE_HAUT, canonique=True, autoriser=True)
    reponse = reponse_creee(db)

    assert reponse.statut == "VALIDÉE"
    assert reponse.source == "CANONIQUE"
    assert reponse.validator_id is None
    assert reponse.validated_at is None
    assert reponse.garde_verdict == "SUFFISANTE_ETAYEE"
    assert reponse.garde_justification


def test_une_suggestion_ne_porte_aucune_trace_de_garde():
    """Aucun juge ne tourne sur cette branche : il n'y a rien à tracer.

    `garde_verdict` enregistre une **décision du garde**, pas un mode de service —
    c'est `source == "CANONIQUE"` qui identifie un service sans relecture humaine,
    et lui seul. Confondre les deux rôles reviendrait à refuser d'enregistrer les
    refus (cf. `test_un_refus_du_garde_est_trace_sur_la_reponse_rag`), donc à
    renoncer à mesurer les blocages à tort.
    """
    _, db, _ = servir(SCORE_HAUT, canonique=True, autoriser=False)
    reponse = reponse_creee(db)

    assert reponse.source == "SUGGESTION"
    assert reponse.garde_verdict is None


def test_un_refus_du_garde_est_trace_sur_la_reponse_rag(worker_isole):
    """Un blocage doit se lire en base, sinon seule la moitié de l'audit existe.

    Une approbation à tort se voit — c'est une réponse fausse servie en VALIDÉE.
    Un blocage à tort ne se voit pas : il produit une réponse RAG parfaitement
    ordinaire, indiscernable de celles qu'aucun candidat n'a précédées. Sans le
    verdict porté jusqu'à l'étape 5, le taux de blocage à tort du garde reste
    structurellement immesurable en production.
    """
    reponse = make_reponse(canonique=True)
    with patch.object(worker_isole, "upsert_reponse") as sauvegarde:
        _lancer(
            worker_isole,
            "Les e-mails non marqués Personnel ?",
            reponse=reponse,
            verdict=_verdict(False),
        )

    kwargs = sauvegarde.call_args.kwargs
    assert kwargs["source"] == "LLM", "c'est bien une réponse RAG fraîche"
    assert kwargs["garde_verdict"] == "INSUFFISANTE"
    assert kwargs["garde_justification"]


def test_une_reponse_rag_sans_candidat_ne_porte_aucun_verdict(worker_isole):
    """Le pendant du test précédent : distinguer « refusé » de « rien à refuser ».

    Si les deux cas laissaient `garde_verdict` nul, la colonne ne dirait plus rien ;
    s'ils le renseignaient tous les deux, elle mentirait sur le nombre de blocages.
    """
    with (
        patch.object(worker_isole, "search_hybrid", return_value=[chunk_factice(0.95)]),
        patch.object(worker_isole, "trouver_reponse_reutilisable", return_value=(None, None)),
        patch.object(worker_isole, "autoriser_service_canonique") as juge,
        patch.object(worker_isole, "rerank", return_value=[]),
        patch.object(worker_isole, "generate", return_value=("réponse fraîche", False)),
        patch.object(worker_isole, "upsert_reponse") as sauvegarde,
    ):
        worker_isole.question_job.apply(args=["Question inédite ?", "RH", None], throw=True).get()

    juge.assert_not_called()
    assert sauvegarde.call_args.kwargs["garde_verdict"] is None


# ══════════════════════════════════════════════════════════════════════════════
# Cause racine : la jambe lexicale de la recherche « hybride » est morte
# ══════════════════════════════════════════════════════════════════════════════


def test_le_vecteur_sparse_est_toujours_vide():
    """`embed_texts` ne produit aucun vecteur creux (`embedding.py:31`).

    La recherche dite « hybride » est donc dense pure, et `score_rrf` ne porte
    aucune information : la fusion RRF somme les rangs d'une seule liste. Or le
    signal lexical est précisément celui qui repérerait un token rare ajouté
    (« alternant », « pare-feu ») — c'est-à-dire la signature d'une précision.

    FIL-PIÈGE INVERSÉ : quand quelqu'un réparera l'embedder, ce test rougira et
    pointera droit sur ce harnais. C'est exactement le couplage recherché — la
    correction doit être mesurée ici avant d'être déclarée bonne. Attention
    toutefois : `dataset_precision.json::logs-parefeu` démontre que ressusciter le
    sparse est nécessaire mais **pas suffisant**.
    """
    with patch("app.services.embedding.client") as faux_client:
        item = MagicMock()
        item.embedding = [0.1] * DIM
        faux_client.embeddings.create.return_value = MagicMock(data=[item])

        from app.services.embedding import embed_texts

        resultat = embed_texts(["une question quelconque"])

    assert resultat[0]["sparse"] == {"indices": [], "values": []}


# ══════════════════════════════════════════════════════════════════════════════
# Auto-tests du helper de cosinus
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("c", [0.0, 0.5, SEUIL_CAND, 0.849, SEUIL_SUG, 0.899, SCORE_HAUT, 1.0])
def test_vecteur_a_cosinus_donne_le_cosinus_demande(c):
    """La construction analytique est exacte à la précision machine près."""
    v = vecteur_a_cosinus(c)
    assert abs(produit_scalaire(v, v) - 1.0) < 1e-12, "vecteur non unitaire"
    assert abs(produit_scalaire(VECTEUR_REQUETE, v) - c) < 1e-12


def test_deux_candidats_sur_des_axes_distincts_n_interferent_pas():
    """Leur cosinus mutuel vaut `c_i·c_j`, donc strictement sous chacun d'eux."""
    a = vecteur_a_cosinus(0.95, axe_orthogonal=1)
    b = vecteur_a_cosinus(0.92, axe_orthogonal=2)
    assert abs(produit_scalaire(a, b) - 0.95 * 0.92) < 1e-12


@pytest.mark.parametrize("c", [-0.1, 1.1])
def test_vecteur_a_cosinus_refuse_un_cosinus_hors_bornes(c):
    with pytest.raises(ValueError):
        vecteur_a_cosinus(c)


def test_vecteur_a_cosinus_refuse_l_axe_de_la_requete():
    """k = 0 écraserait la composante portant le cosinus."""
    with pytest.raises(ValueError):
        vecteur_a_cosinus(0.9, axe_orthogonal=0)


def test_chunk_factice_suit_le_schema_de_production():
    """Verrou anti-dérive : le faux chunk doit avoir les clés du vrai.

    Sans ce test, `chunk_factice` dérive le jour où quelqu'un ajoute une clé à
    `reciprocal_rank_fusion` (search.py:29-40), et tout l'étage unitaire continue
    de tester une forme que la production ne produit plus — vert, et sans objet.
    """
    from types import SimpleNamespace

    from app.services.search import reciprocal_rank_fusion

    point = SimpleNamespace(
        id=1,
        score=0.9,
        payload={
            "contenu": "c",
            "source": "s",
            "domaine": "d",
            "doc_id": "doc",
            "chunk_index": 0,
            "reponse_id": None,
        },
    )
    reel = reciprocal_rank_fusion(SimpleNamespace(points=[point]), SimpleNamespace(points=[]))

    assert set(reel[0]) == set(chunk_factice(0.9))
