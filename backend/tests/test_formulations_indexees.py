"""Une réponse validée est atteignable depuis *chaque* formulation qu'un humain a
validée pour elle — et disparaît entièrement quand on la retire.

Les quatre propriétés testées ici cassent en silence : rien ne lève, la recherche
continue de répondre, et le défaut ne se voit qu'en production sur une réponse
servie à tort ou devenue introuvable.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.services.garde_cache import Decision
from app.services.question_pipeline import Candidat
from celery.exceptions import Retry

# ── Retrait complet ───────────────────────────────────────────────────────────


def test_retrait_supprime_tous_les_points_de_la_reponse():
    """Sélection par payload, jamais par id de point.

    Une réponse porte un point par formulation validée. Supprimer par l'id
    déterministe ne retirerait que la question d'origine : la réponse resterait
    servable depuis ses alias, et un retrait pour obsolescence ou contradiction
    serait sans effet.
    """
    from app.services import qdrant as module
    from qdrant_client.models import Filter

    rid = str(uuid.uuid4())
    with patch.object(module.client, "delete") as suppression:
        module.delete_response_point(rid)

    selecteur = suppression.call_args.kwargs["points_selector"]
    assert isinstance(selecteur, Filter), "un sélecteur par id laisserait vivre les alias"
    condition = selecteur.must[0]
    assert (condition.key, condition.match.value) == ("reponse_id", rid)


# ── Indexation d'une formulation supplémentaire ───────────────────────────────


def _db_factice(reponses, tickets):
    """Session factice qui aiguille `query(Model)` sur la bonne collection."""
    from app.models.reponse import Reponse
    from app.models.ticket import Ticket

    par_modele = {Reponse: reponses, Ticket: tickets}

    def query(modele):
        objets = par_modele[modele]
        chaine = MagicMock()
        chaine.filter.return_value = chaine
        chaine.first.side_effect = lambda: objets.pop(0) if objets else None
        return chaine

    db = MagicMock()
    db.query.side_effect = query
    return db


@pytest.fixture
def _albert_muet():
    faux_vecteur = {"dense": [0.0] * 4, "sparse": {"indices": [], "values": []}}
    with patch("app.workers.feedback.embed_texts", return_value=[faux_vecteur]) as embed:
        yield embed


def test_formulation_supplementaire_ecrit_un_point_distinct(_albert_muet):
    """Le point de la formulation ne doit pas écraser celui de la question d'origine.

    Même id ⇒ l'upsert remplacerait la question sous laquelle la réponse était
    indexée : on perdrait une formulation en croyant en gagner une.
    """
    from app.workers import feedback as module

    source = SimpleNamespace(
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), contenu="réponse", contenu_corrige=None,
        question_suivi=None,
    )
    copie = SimpleNamespace(
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), contenu="réponse", contenu_corrige=None,
        question_suivi=None,
    )
    ticket_source = SimpleNamespace(domaine="RH", question="Comment poser un congé ?")
    ticket_copie = SimpleNamespace(domaine="RH", question="Quelle démarche pour un congé ?")

    def lancer(formulation_id):
        db = _db_factice([source, copie], [ticket_source, ticket_copie])
        with (
            patch.object(module, "SessionLocal", return_value=db),
            # Le juge approuve : ce test porte sur l'id et la charge du point,
            # pas sur la décision — celle-ci a son propre test plus bas.
            patch.object(module, "statuer", return_value=Decision(verdict=True)),
            patch.object(module, "journaliser_garde"),
            patch.object(module.client, "upsert") as upsert,
        ):
            module.feedback_job.run(str(source.id), formulation_id)
        return upsert.call_args.kwargs["points"][0]

    point_origine = lancer(None)
    point_alias = lancer(str(copie.id))

    assert point_origine.id != point_alias.id
    assert point_alias.payload["reponse_id"] == str(source.id), "l'alias pointe la source"
    assert point_alias.payload["question_indexee"] == "Quelle démarche pour un congé ?"
    assert point_origine.payload["question_indexee"] == "Comment poser un congé ?"


@pytest.mark.parametrize(
    ("decision", "alias_ecrit", "retente"),
    [
        pytest.param(Decision(verdict=True), True, False, id="oui-alias-ecrit"),
        pytest.param(Decision(verdict=False), False, False, id="non-juge-aucun-alias"),
        pytest.param(Decision(verdict=False, erreur="503"), False, True, id="albert-en-panne-retry"),
    ],
)
def test_l_alias_est_soumis_au_garde_avant_d_etre_ecrit(_albert_muet, decision, alias_ecrit, retente):
    """Écrire un alias est plus fort que tout ce que le garde tranche ensuite.

    Le point porte la question de la copie et le `reponse_id` de la source : à la
    question suivante le cosinus vaut ~1,0, le court-circuit typographique
    s'enclenche, et la réponse part en CANONIQUE **sans juge**. Un alias faux ne
    passe donc pas devant le garde, il le contourne. Il suffisait d'un relecteur
    cliquant « Valider » plutôt que « Corriger » sur une SUGGESTION plausible mais
    à côté de la question — et le bouton vert est le chemin le moins cher.

    Les trois issues doivent rester distinctes. Confondre le refus jugé et la
    panne Albert perdrait en silence une formulation qu'un humain a validée : le
    premier est une décision, le second une indisponibilité.
    """
    from app.workers import feedback as module

    source = SimpleNamespace(
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), contenu="réponse", contenu_corrige=None,
        question_suivi=None,
    )
    copie = SimpleNamespace(
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), contenu="réponse", contenu_corrige=None,
        question_suivi=None,
    )
    ticket_source = SimpleNamespace(domaine="RH", question="Le télétravail est-il autorisé ?")
    ticket_copie = SimpleNamespace(domaine="RH", question="Le télétravail est-il possible pour les alternants ?")

    db = _db_factice([source, copie], [ticket_source, ticket_copie])
    # `called_directly=False` : sans lui Celery relève l'exception au lieu de
    # signaler `Retry`, et le test observerait autre chose que la production.
    module.feedback_job.push_request(id=str(uuid.uuid4()), retries=0, called_directly=False)
    try:
        with (
            patch.object(module, "SessionLocal", return_value=db),
            patch.object(module, "statuer", return_value=decision) as juge,
            patch.object(module, "journaliser_garde") as journal,
            patch.object(module.client, "upsert") as upsert,
        ):
            if retente:
                with pytest.raises(Retry):
                    module.feedback_job.run(str(source.id), str(copie.id))
            else:
                module.feedback_job.run(str(source.id), str(copie.id))
    finally:
        module.feedback_job.pop_request()

    assert upsert.called is alias_ecrit
    # Jugé avant d'écrire : un refus ne doit même pas coûter l'embedding.
    juge.assert_called_once_with(
        "Le télétravail est-il possible pour les alternants ?", "Le télétravail est-il autorisé ?"
    )
    if not alias_ecrit:
        _albert_muet.assert_not_called()
    # La table d'audit doit dire pourquoi un alias a été refusé, comme elle dit
    # déjà pourquoi une réponse a été servie sans revue.
    journal.assert_called_once()


# ── Régression BM25 : formulation dominante par RRF à cosinus faible ─────────


def test_servable_utilise_le_meilleur_cosinus_pas_le_meilleur_rrf():
    """Quand une formulation domine le RRF (BM25) mais a un cosinus faible,
    une autre formulation du même reponse_id peut avoir un cosinus élevé.
    La réponse doit rester servable (→ SUGGESTION) grâce à cette formulation,
    même si c'est la formulation lexicale qui arrive en tête du classement.

    Sans score_cosinus_max, le candidat héritait du cosinus du chunk dominant RRF
    et devenait non-servable, renvoyant toutes les questions au RAG : nb_validations
    n'atteignait jamais le seuil et la promotion canonique était bloquée.
    """
    from app.services.question_pipeline import SEUIL_COSINUS, SEUIL_SUGGESTION, trouver_reponse_reutilisable

    reponse = SimpleNamespace(id=uuid.uuid4(), canonique=False, nb_validations=2)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    chunks = [
        # Formulation 1 : domine le RRF (score_rrf élevé) mais cosinus < SEUIL_SUGGESTION
        {
            "reponse_id": str(reponse.id),
            "score_cosinus": SEUIL_SUGGESTION - 0.05,
            "score_lexical": 2.0,
            "score_rrf": 0.02,
            "question_indexee": "Quelle démarche pour un congé ?",
        },
        # Formulation 2 : cosinus élevé mais RRF inférieur
        {
            "reponse_id": str(reponse.id),
            "score_cosinus": SEUIL_COSINUS + 0.01,
            "score_lexical": 0.3,
            "score_rrf": 0.01,
            "question_indexee": "Comment poser un congé ?",
        },
    ]

    candidat = trouver_reponse_reutilisable(db, chunks)

    # Le chunk dominant par RRF fixe question_indexee et score_cosinus d'audit
    assert candidat.question_indexee == "Quelle démarche pour un congé ?"
    assert candidat.score_cosinus == pytest.approx(SEUIL_SUGGESTION - 0.05)
    # Mais servable doit être True : une formulation a un bon cosinus
    assert candidat.servable is True, (
        "La réponse doit rester servable quand une formulation a un cosinus élevé, "
        "même si la formulation BM25-dominante a un cosinus faible"
    )


# ── Deux canoniques distinctes : la pertinence prime sur le statut ────────────


def test_la_specifique_pertinente_bat_la_canonique_generale_lointaine():
    """La famine structurelle qui rendait les canoniques distinctes impossibles.

    `r.canonique` était la clé **primaire** du `max()`, la pertinence n'arrivant
    qu'en troisième : une canonique générale à RRF faible battait une réponse
    spécifique validée à RRF fort. La spécifique n'était donc jamais proposée,
    donc jamais validée, donc jamais canonique — et une question spécifique
    recevait indéfiniment la réponse générale.

    C'est le cœur de « jamais générique quand la question est spécifique ». La
    canonique ne disparaît pas de la clé, elle départage à pertinence égale.
    """
    from app.services.question_pipeline import SEUIL_COSINUS, trouver_reponse_reutilisable

    generale = SimpleNamespace(id=uuid.uuid4(), canonique=True, nb_validations=3)
    specifique = SimpleNamespace(id=uuid.uuid4(), canonique=False, nb_validations=1)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [generale, specifique]

    def point(reponse, cosinus, rrf, question):
        return {
            "reponse_id": str(reponse.id),
            "score_cosinus": cosinus,
            "score_lexical": 0.0,
            "score_rrf": rrf,
            "question_indexee": question,
        }

    candidat = trouver_reponse_reutilisable(
        db,
        [
            point(generale, SEUIL_COSINUS + 0.01, 0.010, "Le télétravail est-il autorisé ?"),
            point(specifique, SEUIL_COSINUS + 0.15, 0.030,
                  "Le télétravail est-il possible pour les alternants ?"),
        ],
    )

    assert candidat.reponse is specifique
    assert candidat.question_indexee == "Le télétravail est-il possible pour les alternants ?"


def test_une_reponse_corrigee_est_reutilisable():
    """« Corriger » est le bon geste du relecteur : il ne doit pas être stérile.

    Le filtre `statut == "VALIDÉE"` excluait CORRIGÉE — le texte qu'un humain a
    écrit lui-même parce que la réponse proposée ne convenait pas. Il partait
    dans Qdrant, servait de matière au contexte RAG, et n'était jamais resservi :
    il ne pouvait donc pas accumuler de validations, donc jamais devenir
    canonique. C'est ce correctif qui **fait naître** la canonique spécifique.
    """
    from app.services.question_pipeline import SEUIL_COSINUS, trouver_reponse_reutilisable

    corrigee = SimpleNamespace(id=uuid.uuid4(), canonique=False, nb_validations=0)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [corrigee]

    candidat = trouver_reponse_reutilisable(
        db, [{"reponse_id": str(corrigee.id), "score_cosinus": SEUIL_COSINUS + 0.1}]
    )

    assert candidat.reponse is corrigee
    # Jamais canonique pour autant : `corriger_reponse` n'incrémente pas
    # `nb_validations`. Elle ressort en SUGGESTION et monte au seuil par le
    # chemin normal — une copie validée incrémente la source.
    assert candidat.reponse.canonique is False

    # Et le filtre SQL demande bien les deux statuts : sans ça l'assertion
    # ci-dessus passerait sur un mock qui rend tout ce qu'on lui demande.
    clause = str(db.query.return_value.filter.call_args.args[1])
    assert "IN" in clause.upper(), f"le statut doit être filtré par appartenance, pas par égalité : {clause}"


# ── La question jugée par le garde est celle du point retrouvé ────────────────


def test_le_garde_juge_la_question_du_point_qui_a_matche():
    """Avec plusieurs formulations par réponse, prendre la question du ticket
    d'origine ferait juger au garde une paire qui n'est pas celle retrouvée —
    il pourrait approuver sur une équivalence qu'il n'a pas constatée.
    """
    from app.services.question_pipeline import SEUIL_SUGGESTION, trouver_reponse_reutilisable

    reponse = SimpleNamespace(id=uuid.uuid4(), canonique=True, nb_validations=3)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    chunks = [
        {"reponse_id": str(reponse.id), "score_cosinus": SEUIL_SUGGESTION + 0.01,
         "score_rrf": 0.01, "question_indexee": "Comment poser un congé ?"},
        {"reponse_id": str(reponse.id), "score_cosinus": SEUIL_SUGGESTION + 0.10,
         "score_rrf": 0.02, "question_indexee": "Quelle démarche pour un congé ?"},
    ]

    candidat = trouver_reponse_reutilisable(db, chunks)

    assert candidat.score_cosinus == pytest.approx(SEUIL_SUGGESTION + 0.10)
    assert candidat.question_indexee == "Quelle démarche pour un congé ?"


def test_question_indexee_absente_du_payload_ne_casse_pas():
    """Les points écrits avant les formulations multiples n'ont pas la clé.
    L'appelant doit recevoir `None` et retomber sur `Ticket.question`.
    """
    from app.services.question_pipeline import SEUIL_SUGGESTION, trouver_reponse_reutilisable

    reponse = SimpleNamespace(id=uuid.uuid4(), canonique=True, nb_validations=3)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    candidat = trouver_reponse_reutilisable(
        db, [{"reponse_id": str(reponse.id), "score_cosinus": SEUIL_SUGGESTION + 0.1}]
    )

    assert candidat.question_indexee is None


# ── Refus du garde : SUGGESTION, pas RAG ──────────────────────────────────────


def test_refus_du_garde_sert_une_suggestion_sans_relancer_le_rag():
    """Le garde dit « pas la même demande », ce qui disqualifie le service sans
    revue — pas la proposition au relecteur.

    Sans ce repli, franchir SEUIL_COSINUS *dégradait* l'issue : un candidat à
    0,84 sortait en SUGGESTION sans être jugé, le même à 0,86 partait au RAG
    complet sur refus, et le relecteur ne voyait plus aucun candidat.
    """
    from app.services.garde_cache import Decision
    from app.workers.question import SEUIL_COSINUS, question_job

    reponse = SimpleNamespace(
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), canonique=True, a_relire=False, nb_validations=3
    )

    question_job.push_request(id=str(uuid.uuid4()), retries=0)
    try:
        with (
            patch("app.workers.question._ticket_existe", return_value=True),
            patch("app.workers.question.search_hybrid", return_value=[]),
            patch(
                "app.workers.question.trouver_reponse_reutilisable",
                return_value=Candidat(
                    reponse, SEUIL_COSINUS + 0.05, SEUIL_COSINUS + 0.05, "Comment poser un congé ?"
                ),
            ),
            patch("app.workers.question.statuer", return_value=Decision(verdict=False)),
            patch("app.workers.question.journaliser_garde"),
            patch("app.workers.question.servir_reutilisation", return_value={}) as servir,
            patch("app.workers.question.rerank") as reranker,
            patch("app.workers.question.generate") as generation,
        ):
            question_job.run(question="Comment poser des congés ?", domaine="RH")
    finally:
        question_job.pop_request()

    servir.assert_called_once()
    assert servir.call_args.args[11] is False, "servie en SUGGESTION, jamais en CANONIQUE"
    reranker.assert_not_called()
    generation.assert_not_called()
