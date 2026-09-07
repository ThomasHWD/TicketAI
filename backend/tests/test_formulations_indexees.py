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
         "question_indexee": "Comment poser un congé ?"},
        {"reponse_id": str(reponse.id), "score_cosinus": SEUIL_SUGGESTION + 0.10,
         "question_indexee": "Quelle démarche pour un congé ?"},
    ]

    _, score, question = trouver_reponse_reutilisable(db, chunks)

    assert score == pytest.approx(SEUIL_SUGGESTION + 0.10)
    assert question == "Quelle démarche pour un congé ?"


def test_question_indexee_absente_du_payload_ne_casse_pas():
    """Les points écrits avant les formulations multiples n'ont pas la clé.
    L'appelant doit recevoir `None` et retomber sur `Ticket.question`.
    """
    from app.services.question_pipeline import SEUIL_SUGGESTION, trouver_reponse_reutilisable

    reponse = SimpleNamespace(id=uuid.uuid4(), canonique=True, nb_validations=3)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [reponse]

    _, _, question = trouver_reponse_reutilisable(
        db, [{"reponse_id": str(reponse.id), "score_cosinus": SEUIL_SUGGESTION + 0.1}]
    )

    assert question is None


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
        id=uuid.uuid4(), ticket_id=uuid.uuid4(), canonique=True, nb_validations=3
    )

    question_job.push_request(id=str(uuid.uuid4()), retries=0)
    try:
        with (
            patch("app.workers.question._ticket_existe", return_value=True),
            patch("app.workers.question.search_hybrid", return_value=[]),
            patch(
                "app.workers.question.trouver_reponse_reutilisable",
                return_value=(reponse, SEUIL_COSINUS + 0.05, "Comment poser un congé ?"),
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
