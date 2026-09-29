"""Tests de la ré-vérification des réponses (`app/services/reverification.py`).

C'est l'étage qui décide qu'une réponse cesse d'être servie. Deux familles de
propriétés y sont vérifiées, et elles ne se compensent pas :

* **la table de décision** — qui peut être retirée, qui ne peut que l'être à
  moitié. L'asymétrie citante / non-citante est le garde-fou central du dispositif ;
* **les replis** — reranker muet, LLM en panne, sortie illisible. Aucun de ces
  cas ne doit se traduire par « on laisse en service sans avoir vérifié », ni par
  un retrait automatique.

Albert (embedding, reranker, LLM) et Qdrant sont toujours bouchonnés : ces tests
fixent la logique, pas la qualité des modèles.
"""

import uuid

import pytest
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.obsolescence import Unite
from app.services.reverification import (
    ACTION_A_RELIRE,
    ACTION_INTACTE,
    ACTION_RETIREE,
    MAX_UNITES_PAR_REPONSE,
    VERDICT_CONTREDITE,
    VERDICT_INCERTAIN,
    VERDICT_INTACTE,
    Candidate,
    decider,
    juger,
    signaler_sans_juger,
    unites_pertinentes,
)
from app.services.reverification_scoring import _lire_verdict

# Valeurs épinglées volontairement plutôt qu'importées : ces chaînes sont écrites
# telles quelles en base (`String(30)`) et lues par le front pour choisir un badge.
# Les renommer sans migration laisserait des lignes orphelines et un onglet muet ;
# le test doit donc casser sur un renommage, pas le suivre.
RAISON_CONTREDITE = "CONTREDITE_PAR_MAJ"
RAISON_MODIF = "DOC_MODIFIÉ"
RAISON_CONTREDITE_PROB = "CONTREDITE_PROBABLE"

UNITE = Unite(
    "REECRITURE",
    "Le teletravail est limite a 2 jours par semaine.",
    "Le teletravail est limite a 3 jours par semaine.",
)
AUTRE = Unite("AJOUT", None, "Les frais de transport sont rembourses a 50 pour cent.")


# ──────────────────────────────────────────────────────────────────────────────
# Étage 2 — le tri des unités, et surtout ce qu'il fait quand il échoue
# ──────────────────────────────────────────────────────────────────────────────


class TestUnitesPertinentes:
    def test_une_seule_unite_n_appelle_pas_le_reranker(self, monkeypatch):
        """Trier un élément n'apprend rien et coûte un aller-retour réseau."""
        import app.services.reverification_scoring as module

        monkeypatch.setattr(module, "rerank", _interdit)

        assert unites_pertinentes("Q ?", [UNITE]) == ([UNITE], True)

    def test_ecarte_les_unites_sous_le_seuil(self, monkeypatch):
        import app.services.reverification_scoring as module

        monkeypatch.setattr(
            module,
            "rerank",
            lambda q, docs, top_k: [
                {**docs[0], "rerank_score": 0.9},
                {**docs[1], "rerank_score": 0.01},
            ],
        )

        retenues, fiable = unites_pertinentes("Q ?", [UNITE, AUTRE])

        assert retenues == [UNITE]
        assert fiable is True

    def test_reranker_qui_leve_fait_juger_quand_meme(self, monkeypatch):
        """Une panne du trieur ne doit pas ressembler à « rien à signaler »."""
        import app.services.reverification_scoring as module

        def _casse(*a, **k):
            raise RuntimeError("502 Bad Gateway")

        monkeypatch.setattr(module, "rerank", _casse)

        retenues, fiable = unites_pertinentes("Q ?", [UNITE, AUTRE])

        assert retenues == [UNITE, AUTRE]
        assert fiable is False, "le second membre doit dire que le tri n'a pas eu lieu"

    def test_reranker_muet_fait_juger_quand_meme(self, monkeypatch):
        """La panne qui ne se voit pas : `rerank` renvoie `[]` **sans lever** quand
        la réponse d'Albert n'a pas la forme attendue (`services/reranker.py` n'a
        pas de branche `else`). Lue comme « aucune unité pertinente », cette liste
        vide sortirait silencieusement toute la base du pipeline le jour d'un
        changement de format d'API."""
        import app.services.reverification_scoring as module

        monkeypatch.setattr(module, "rerank", lambda q, docs, top_k: [])

        retenues, fiable = unites_pertinentes("Q ?", [UNITE, AUTRE])

        assert retenues == [UNITE, AUTRE]
        assert fiable is False

    def test_repli_plafonne_le_nombre_d_unites(self, monkeypatch):
        """Sans tri, on ne peut pas choisir — mais on ne dilue pas le prompt."""
        import app.services.reverification_scoring as module

        monkeypatch.setattr(module, "rerank", lambda q, docs, top_k: [])
        beaucoup = [Unite("AJOUT", None, f"Article {i} du reglement interieur.") for i in range(10)]

        retenues, fiable = unites_pertinentes("Q ?", beaucoup)

        assert len(retenues) == MAX_UNITES_PAR_REPONSE
        assert fiable is False


def _interdit(*a, **k):
    raise AssertionError("le reranker ne devait pas être appelé")


# ──────────────────────────────────────────────────────────────────────────────
# Étage 3 — la lecture du verdict
# ──────────────────────────────────────────────────────────────────────────────


class TestLireVerdict:
    def test_json_nu(self):
        assert _lire_verdict('{"verdict": "CONTREDITE", "justification": "2 jours -> 3 jours"}') == (
            VERDICT_CONTREDITE,
            "2 jours -> 3 jours",
        )

    def test_bloc_de_code_et_bavardage(self):
        """Les modèles encadrent malgré la consigne ; refuser serait se punir
        soi-même en transformant une réponse correcte en INCERTAIN."""
        brut = 'Voici mon analyse :\n```json\n{"verdict": "INTACTE", "justification": "Sans effet."}\n```\nVoilà.'

        assert _lire_verdict(brut) == (VERDICT_INTACTE, "Sans effet.")

    @pytest.mark.parametrize(
        "brut",
        [
            "CONTREDITE",  # pas de JSON du tout
            "{verdict: CONTREDITE}",  # JSON invalide
            '{"verdict": "PEUT-ETRE", "justification": "?"}',  # verdict inconnu
            '{"justification": "sans verdict"}',
            "",
        ],
    )
    def test_sortie_illisible_vaut_incertain_jamais_intacte(self, brut):
        """Le seul repli acceptable est celui qui fait relire un humain. Retomber
        sur INTACTE laisserait en service une réponse qu'on n'a pas vérifiée."""
        verdict, justification = _lire_verdict(brut)

        assert verdict == VERDICT_INCERTAIN
        assert justification

    def test_justification_tronquee(self):
        verdict, justification = _lire_verdict('{"verdict": "INTACTE", "justification": "%s"}' % ("a" * 500))

        assert verdict == VERDICT_INTACTE
        assert len(justification) == 200

    def test_justification_normalisee(self):
        brut = '{"verdict": "INTACTE", "justification": "deux   lignes\\n  espacees"}'

        assert _lire_verdict(brut)[1] == "deux lignes espacees"


class TestJuger:
    def test_le_prompt_montre_l_avant_et_l_apres(self, monkeypatch):
        """Le modèle juge le diff, pas l'état du document : c'est ce qui rend la
        question fermée et vérifiable."""
        import app.services.reverification_scoring as module

        vus = {}

        def _chat(messages, **kwargs):
            vus["messages"] = messages
            vus["kwargs"] = kwargs
            return '{"verdict": "CONTREDITE", "justification": "La duree passe de 2 a 3 jours."}'

        monkeypatch.setattr(module, "chat", _chat)

        verdict, justification = juger("Combien de jours ?", "Deux jours.", [UNITE])

        assert verdict == VERDICT_CONTREDITE
        assert justification == "La duree passe de 2 a 3 jours."
        contenu = vus["messages"][1]["content"]
        assert "AVANT : Le teletravail est limite a 2 jours" in contenu
        assert "APRÈS : Le teletravail est limite a 3 jours" in contenu
        assert "Deux jours." in contenu
        assert vus["kwargs"]["temperature"] == 0, "un verdict ne se tire pas au sort"

    def test_le_prompt_interdit_de_rediger_une_correction(self):
        """Arbitrage produit : le retrait est sec. Une correction rédigée par le
        modèle serait relue comme une proposition validée par la machine."""
        import app.services.reverification_scoring as module

        assert "Ne rédige jamais de correction" in module.PROMPT_SYSTEME

    def test_panne_http_remonte(self, monkeypatch):
        """`juger` ne décide pas quoi faire d'une panne : l'appelant a des options
        qu'une simple hésitation du modèle n'appelle pas (réessayer, s'arrêter)."""
        import app.services.reverification_scoring as module

        def _casse(*a, **k):
            raise RuntimeError("timeout")

        monkeypatch.setattr(module, "chat", _casse)

        with pytest.raises(RuntimeError):
            juger("Q ?", "R.", [UNITE])


# ──────────────────────────────────────────────────────────────────────────────
# Étage 4 — la table de décision
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def famille(db_session, monkeypatch):
    """Une graine citant le document, sa copie CANONIQUE, et un Qdrant bouchonné."""
    import app.services.obsolescence as obso

    retires: list[str] = []
    monkeypatch.setattr(obso, "delete_response_point", retires.append)

    doc_id = str(uuid.uuid4())

    def _reponse(*, cite=True, source=None, canonique=False, nb_validations=1):
        ticket = Ticket(question="Combien de jours de teletravail ?", domaine="RH", statut_job="TERMINÉ")
        db_session.add(ticket)
        db_session.flush()
        r = Reponse(
            ticket_id=ticket.id,
            contenu="Deux jours par semaine.",
            source="LLM",
            statut="VALIDÉE",
            canonique=canonique,
            nb_validations=nb_validations,
            reponse_source_id=source.id if source is not None else None,
        )
        db_session.add(r)
        db_session.flush()
        if cite:
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, chunk_index=0))
        db_session.commit()
        return r

    _reponse.db = db_session
    _reponse.doc_id = doc_id
    _reponse.retires = retires
    return _reponse


def _candidate(reponse, *, citante, question="Combien de jours de teletravail ?"):
    return Candidate(reponse=reponse, question=question, citante=citante)


@pytest.mark.integration
class TestDecider:
    def test_citante_contredite_est_retiree(self, famille):
        r = famille(canonique=True, nb_validations=5)

        action = decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_CONTREDITE,
            "La duree passe de 2 a 3 jours.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert action == ACTION_RETIREE
        assert r.obsolete is True
        assert r.obsolete_raison == RAISON_CONTREDITE
        assert r.obsolete_version == 2
        assert str(r.id) in famille.retires, "le point Qdrant doit partir avec la réponse"
        assert r.analyse_justification == "La duree passe de 2 a 3 jours."
        assert r.analyse_extraits["unites"][0]["apres"] == UNITE.apres

    def test_non_citante_contredite_plafonne_a_la_relecture(self, famille):
        """**Le garde-fou central.** Cette réponse n'a été rapprochée du changement
        que par similarité entre un paragraphe de document et une question — deux
        objets de nature différente, indexés pour autre chose. Détruire à tort une
        canonique à douze validations coûte bien plus cher que vingt relectures.
        """
        r = famille(cite=False, canonique=True, nb_validations=12)

        action = decider(
            famille.db,
            _candidate(r, citante=False),
            VERDICT_CONTREDITE,
            "Le nouvel article 7 bis suspend le dispositif.",
            [AUTRE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert action == ACTION_A_RELIRE
        assert r.obsolete is False, "une non-citante ne peut jamais être retirée automatiquement"
        assert r.a_relire is True
        assert r.a_relire_raison == RAISON_CONTREDITE_PROB
        assert famille.retires == [], "et son point Qdrant reste en place : elle est toujours servie"

    def test_intacte_leve_le_signalement(self, famille):
        r = famille()
        decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INCERTAIN,
            "Doute.",
            [UNITE],
            famille.doc_id,
            2,
        )
        famille.db.refresh(r)
        assert r.a_relire is True

        action = decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INTACTE,
            "Sans effet.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert action == ACTION_INTACTE
        assert r.a_relire is False
        assert r.obsolete is False
        assert r.analyse_justification is None, "plus rien à justifier une fois la réponse blanchie"

    def test_intacte_ne_leve_pas_le_signalement_d_un_autre_document(self, famille):
        """Sans cette garde, la mise à jour d'un document effacerait la relecture
        posée par la mise à jour d'un autre — que ce job n'a pas instruite."""
        r = famille()
        autre_doc = str(uuid.uuid4())
        decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INCERTAIN,
            "Doute ailleurs.",
            [UNITE],
            autre_doc,
            7,
        )
        famille.db.refresh(r)
        assert r.a_relire_doc_id == autre_doc

        decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INTACTE,
            "Sans effet.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert r.a_relire is True
        assert r.a_relire_doc_id == autre_doc

    def test_intacte_ne_leve_pas_le_signalement_d_une_autre_passe(self, famille):
        """Même document, autre passe : le verdict n'instruit pas le même motif.

        La confrontation à l'arrivée de doc B v1 signale une réponse incomplète ;
        la ré-vérification de doc B v2 ne juge que le diff v1→v2. La trouver
        INTACTE ne dit rien de l'incomplétude — la blanchir rendrait servable sans
        revue une réponse qui omet toujours l'exception.
        """
        r = famille()
        decider(
            famille.db,
            _candidate(r, citante=False),
            VERDICT_CONTREDITE,
            "Incomplète : elle omet l'exception introduite par ce document.",
            [UNITE],
            famille.doc_id,
            1,
        )
        famille.db.refresh(r)
        assert r.a_relire is True and r.a_relire_version == 1

        action = decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INTACTE,
            "Le diff 45 € → 60 € est sans effet sur cette réponse.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert action == ACTION_INTACTE
        assert r.a_relire is True, "un verdict sur le diff v1→v2 ne clôt pas un motif posé à la v1"
        assert r.a_relire_raison == RAISON_CONTREDITE_PROB
        assert r.a_relire_version == 1

    def test_incertain_envoie_en_relecture_sans_retirer(self, famille):
        r = famille()

        action = decider(
            famille.db,
            _candidate(r, citante=True),
            VERDICT_INCERTAIN,
            "Impossible de trancher.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(r)
        assert action == ACTION_A_RELIRE
        assert r.obsolete is False
        assert r.a_relire is True
        assert r.a_relire_raison == RAISON_MODIF
        assert famille.retires == []

    def test_la_copie_canonique_part_avec_la_graine(self, famille):
        """Les copies ne citent aucun chunk : elles ne tiennent à leur origine que
        par `reponse_source_id`. Décider sur la seule graine laisserait la copie
        indexée dans Qdrant, donc resservie — la réponse retirée continuerait de
        sortir, sous un autre identifiant."""
        graine = famille(canonique=True)
        copie = famille(cite=False, source=graine, canonique=True)

        decider(
            famille.db,
            _candidate(graine, citante=True),
            VERDICT_CONTREDITE,
            "Contredite.",
            [UNITE],
            famille.doc_id,
            2,
        )

        famille.db.refresh(copie)
        assert copie.obsolete is True
        assert str(copie.id) in famille.retires

    @pytest.mark.parametrize("question_suivi", [None, "Et pour un apprenti ?"])
    def test_la_copie_en_attente_retiree_repart_au_pipeline_sous_sa_question(
        self, famille, monkeypatch, question_suivi
    ):
        """Retirée sans renvoi, la SUGGESTION en attente disparaît du fil (obsolète non
        validée) et le ticket reste RÉPONDU sans réponse. Une précision doit repartir en
        mode suivi — sous la question initiale, elle écrasait la réponse initiale."""
        import app.workers.question as q

        envois = []
        monkeypatch.setattr(q.question_job, "delay", lambda **kw: envois.append(kw))
        graine = famille(canonique=True)
        copie = famille(cite=False, source=graine)
        copie.statut, copie.question_suivi = "EN_ATTENTE", question_suivi
        famille.db.commit()

        decider(famille.db, _candidate(graine, citante=True), VERDICT_CONTREDITE, "Contredite.", [UNITE],
                famille.doc_id, 2)

        assert [(e["ticket_id"], e["question"], e["retraiter"]) for e in envois] == [
            (str(copie.ticket_id), question_suivi or "Combien de jours de teletravail ?", question_suivi is None)
        ]

    def test_signaler_sans_juger_marque_toute_la_famille(self, famille):
        graine = famille()
        copie = famille(cite=False, source=graine)

        nb = signaler_sans_juger(
            famille.db,
            [_candidate(graine, citante=True)],
            "ANALYSE_INDISPONIBLE",
            "Le service d'analyse n'a pas repondu.",
            famille.doc_id,
            2,
        )

        famille.db.refresh(graine)
        famille.db.refresh(copie)
        assert nb == 1, "le comptage porte sur les candidates, pas sur les copies"
        assert (graine.a_relire, copie.a_relire) == (True, True)
        assert graine.a_relire_raison == "ANALYSE_INDISPONIBLE"
        assert graine.obsolete is False, "une panne ne détruit jamais"
        assert famille.retires == []


@pytest.mark.integration
def test_une_canonique_corrigee_a_la_main_est_atteinte_par_les_voisines(famille, monkeypatch):
    """Une HORS_DOMAINE corrigée à la main ne cite aucun chunk : les voisines sont son
    seul chemin vers la ré-vérification, et elles excluaient `CORRIGÉE`."""
    from types import SimpleNamespace

    import app.services.reverification_candidates as candidates

    r = famille(cite=False, canonique=True, nb_validations=3)
    r.statut, r.source = "CORRIGÉE", "HORS_DOMAINE"
    famille.db.commit()
    monkeypatch.setattr(candidates, "embed_texts", lambda textes, is_query: [{"dense": [0.1]}])
    point = SimpleNamespace(score=0.9, payload={"reponse_id": str(r.id)})
    monkeypatch.setattr(candidates.client, "query_points", lambda **kw: SimpleNamespace(points=[point]))

    assert [v.id for v in candidates._voisines(famille.db, "RH", [UNITE])] == [r.id]


@pytest.mark.integration
@pytest.mark.parametrize("version_citee, rapprochee", [(1, False), (2, True), (None, True)])
def test_un_index_ne_rapproche_que_les_citations_de_sa_version(famille, version_citee, rapprochee):
    """Après une mise à jour, l'index 0 désigne un autre passage : rapprocher une citation de
    la v1 des indices modifiés de la v2 accusait une réponse d'un texte qu'elle n'a jamais lu.
    Version inconnue (ligne héritée) : rapprochée comme avant, faute de mieux."""
    from app.services.obsolescence import reponses_obsoletes

    r = famille(cite=False)
    famille.db.add(ReponseChunk(reponse_id=r.id, doc_id=famille.doc_id, chunk_index=0, version=version_citee))
    famille.db.commit()

    assert (r in reponses_obsoletes(famille.db, famille.doc_id, {0}, version=2)) is rapprochee
