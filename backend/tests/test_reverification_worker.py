"""Tests du worker de ré-vérification (`app/workers/reverification.py`).

Le service décide ; ce module-ci ne porte que la **politique** : les plafonds,
l'ordre de dépense du budget, les replis et le bilan. C'est là que se joue la
propriété la plus importante du dispositif :

    ``ANALYSE_EN_COURS`` est le seul état transitoire du modèle de données, et le
    job a l'obligation de le résoudre pour chaque réponse qu'il a reçue.

Un état transitoire qui survit est un bug silencieux : la réponse reste servie,
l'interface annonce une analyse qui n'aura jamais lieu, et personne n'est
sollicité. Chaque test ci-dessous vérifie donc, en plus de son objet propre,
qu'il ne reste rien en analyse à la fin.

Albert est toujours bouchonné ; Postgres est réel.
"""

import uuid

import pytest
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.obsolescence import RAISON_ANALYSE, flaguer_en_analyse
from app.workers.reverification import (
    MAX_ECHECS,
    rabattre,
    restees_en_analyse,
    reverification_job,
)

DOMAINE = "RH"

# Ces chaînes partent en base et sont lues par le front pour choisir un badge :
# elles doivent casser un test si on les renomme, pas suivre le renommage.
RAISON_INDISPONIBLE = "ANALYSE_INDISPONIBLE"
RAISON_PARTIELLE = "ANALYSE_PARTIELLE"
RAISON_MASSIVE = "REECRITURE_MASSIVE"


def _unite(i: int) -> dict:
    return {
        "sens": "REECRITURE",
        "avant": f"L'article {i} fixe le plafond a 200 euros par mois.",
        "apres": f"L'article {i} fixe le plafond a 300 euros par mois.",
    }


@pytest.fixture
def lot(db_session, monkeypatch):
    """Un document en v2, ses unités figées, et N réponses validées qui le citent.

    Reproduit l'état exact dans lequel `document_update_job` laisse la base :
    version basculée, `changements` écrits, réponses flaguées `ANALYSE_EN_COURS`.
    """
    import app.services.obsolescence as obso
    import app.services.reverification as services_reverif
    import app.services.reverification_candidates as candidates
    import app.workers.reverification as worker

    monkeypatch.setattr(obso, "delete_response_point", lambda _id: None)
    monkeypatch.setattr(worker, "broadcast_sync", lambda *a, **k: None)
    # Le rappel vectoriel est hors sujet ici : on teste la politique du worker sur
    # un lot connu, pas la capacité de Qdrant à élargir le périmètre.
    monkeypatch.setattr(candidates, "_voisines", lambda db, domaine, unites: [])
    monkeypatch.setattr(services_reverif, "voisines_du_document", lambda db, doc_id, version, domaine: [])

    doc_id = str(uuid.uuid4())

    def _monter(*, nb_reponses=1, nb_unites=1, version=2, unites=None):
        db_session.add(
            Document(
                doc_id=doc_id,
                filename="charte.md",
                domaine=DOMAINE,
                version=version,
                statut="ACTIF",
                nb_chunks=2,
            )
        )
        brutes = unites if unites is not None else [_unite(i) for i in range(nb_unites)]
        db_session.add(
            DocumentVersion(
                doc_id=doc_id,
                version=version,
                filename="charte.md",
                changements={"nb_unites": len(brutes), "unites": brutes},
            )
        )
        db_session.flush()

        reponses = []
        for i in range(nb_reponses):
            ticket = Ticket(question=f"Quel est le plafond {i} ?", domaine=DOMAINE, statut_job="TERMINÉ")
            db_session.add(ticket)
            db_session.flush()
            r = Reponse(
                ticket_id=ticket.id,
                contenu="Le plafond est de 200 euros.",
                source="LLM",
                statut="VALIDÉE",
                canonique=True,
                nb_validations=3,
            )
            db_session.add(r)
            db_session.flush()
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, chunk_index=0))
            reponses.append(r)
        db_session.commit()

        flaguer_en_analyse(db_session, doc_id, version)
        db_session.commit()
        return reponses

    _monter.db = db_session
    _monter.doc_id = doc_id
    return _monter


def _repondre(monkeypatch, verdict: str, justification: str = "Le plafond passe de 200 a 300 euros."):
    """Bouchonne le tri et le jugement : toutes les réponses reçoivent `verdict`."""
    import app.services.reverification_scoring as scoring

    monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
    monkeypatch.setattr(
        scoring,
        "chat",
        lambda messages, **k: '{"verdict": "%s", "justification": "%s"}' % (verdict, justification),
    )


@pytest.mark.integration
class TestVerdictsAppliques:
    def test_contredite_retire_et_resout_le_drapeau(self, lot, monkeypatch):
        [r] = lot()
        _repondre(monkeypatch, "CONTREDITE")

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE, indices_disparus=[0])

        lot.db.expire_all()
        assert bilan["statut"] == "OK"
        assert bilan["nb_contredites"] == 1
        assert r.obsolete is True
        assert r.obsolete_raison == "CONTREDITE_PAR_MAJ"
        assert r.analyse_justification == "Le plafond passe de 200 a 300 euros."
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_le_juge_voit_le_texte_actuel_du_document(self, lot, monkeypatch):
        """Le diff seul cachait l'exception inchangée : « apprentis : 28 j » jugée
        CONTREDITE 3/3 quand seule la règle générale bougeait (mesuré le 28/09/2026)."""
        import app.services.reverification_scoring as scoring
        import app.workers.reverification as worker
        from app.workers.reverification import reverification_job

        [r] = lot()
        vus = []
        _repondre(monkeypatch, "INTACTE")
        monkeypatch.setattr(scoring, "chat", lambda messages, **k: vus.append(messages[1]["content"])
                            or '{"verdict": "INTACTE", "justification": "Exception inchangee."}')
        monkeypatch.setattr(worker, "passages_actuels",
                            lambda reponse, doc_id, version: ["Les apprentis gardent 28 jours."]
                            if (reponse.id, doc_id, version) == (r.id, lot.doc_id, 2) else [])

        reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        assert "Les apprentis gardent 28 jours." in vus[0]

    def test_intacte_leve_le_drapeau_et_laisse_servie(self, lot, monkeypatch):
        [r] = lot()
        _repondre(monkeypatch, "INTACTE", "Sans effet sur cette reponse.")

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["nb_intactes"] == 1
        assert (r.obsolete, r.a_relire) == (False, False)
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []


@pytest.mark.integration
class TestPlafonds:
    def test_reecriture_massive_ne_coute_aucun_appel(self, lot, monkeypatch):
        """Quand tout a changé, il n'y a plus rien à discriminer : juger 200
        réponses contre 300 changements coûterait une fortune pour conclure « tout
        est suspect », ce qu'on sait déjà en comptant les unités."""
        import app.services.reverification_scoring as scoring

        reponses = lot(nb_reponses=3, nb_unites=41)
        monkeypatch.setattr(scoring, "chat", _interdit)
        monkeypatch.setattr(scoring, "rerank", _interdit)

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["nb_a_relire"] == 3
        assert bilan["nb_contredites"] == 0
        assert all(r.a_relire and r.a_relire_raison == RAISON_MASSIVE for r in reponses)
        assert all(r.obsolete is False for r in reponses), "une réécriture massive ne détruit rien"
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_reecriture_massive_signale_aussi_les_voisines(self, lot, monkeypatch):
        """Une réécriture est précisément le moment où une canonique bâtie sur un autre
        document, ou écrite à la main, se fait contredire. Seules les citantes partaient
        en relecture : la voisine restait servie sans revue. Rappel sur les vecteurs déjà
        stockés des passages — zéro appel Albert. Une voisine déjà signalée garde son motif."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        import app.services.reverification as services_reverif
        import app.services.reverification_candidates as candidates
        import app.services.reverification_scoring as scoring

        lot(nb_reponses=1, nb_unites=41)
        voisines = []
        for signalee in (False, True):
            ticket = Ticket(question="Plafond des frais ?", domaine=DOMAINE, statut_job="TERMINÉ")
            lot.db.add(ticket)
            lot.db.flush()
            r = Reponse(ticket_id=ticket.id, contenu="200 euros.", source="HORS_DOMAINE", statut="CORRIGÉE",
                        canonique=True, nb_validations=3, a_relire=signalee,
                        a_relire_raison="CONTREDITE_PROBABLE" if signalee else None)
            lot.db.add(r)
            voisines.append(r)
        lot.db.commit()

        qdrant = MagicMock()
        qdrant.scroll.return_value = ([SimpleNamespace(vector={"dense": [0.1] * 1024})], None)
        qdrant.query_points.return_value = SimpleNamespace(
            points=[SimpleNamespace(score=0.6, payload={"reponse_id": str(r.id)}) for r in voisines]
        )
        monkeypatch.setattr(candidates, "client", qdrant)
        monkeypatch.setattr(services_reverif, "voisines_du_document", candidates.voisines_du_document)
        monkeypatch.setattr(scoring, "chat", _interdit)

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        libre, deja = voisines
        assert (libre.a_relire, libre.a_relire_raison) == (True, RAISON_MASSIVE)
        assert deja.a_relire_raison == "CONTREDITE_PROBABLE"
        assert bilan["nb_a_relire"] == 2  # la citante et la voisine libre

    def test_budget_epuise_ne_perd_aucune_reponse(self, lot, monkeypatch):
        """Le surplus n'est jamais tronqué en silence — c'est exactement ce que
        faisait l'ancien système, et la raison pour laquelle il n'était pas
        exploitable. Il part en relecture, avec sa propre raison."""
        import app.workers.reverification as worker

        monkeypatch.setattr(worker, "MAX_JUGEMENTS", 4)
        reponses = lot(nb_reponses=10)
        _repondre(monkeypatch, "INTACTE")

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["nb_intactes"] == 4
        assert bilan["nb_indisponibles"] == 6
        assert bilan["nb_intactes"] + bilan["nb_indisponibles"] == len(reponses), "aucune perdue"
        surplus = [r for r in reponses if r.a_relire_raison == RAISON_PARTIELLE]
        assert len(surplus) == 6
        assert all(r.obsolete is False for r in surplus)
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []


@pytest.mark.integration
class TestReplis:
    def test_panne_albert_laisse_la_reponse_servie(self, lot, monkeypatch):
        """L'arbitrage produit, vérifié de bout en bout : sur panne, la réponse
        reste servie et part en relecture. Jamais de destruction automatique."""
        import app.services.reverification_scoring as scoring

        [r] = lot()
        monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
        monkeypatch.setattr(scoring, "chat", _casse)

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["nb_indisponibles"] == 1
        assert bilan["nb_contredites"] == 0
        assert r.obsolete is False, "une panne ne doit jamais retirer une réponse du service"
        assert r.a_relire_raison == RAISON_INDISPONIBLE
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_albert_injoignable_arrete_d_insister(self, lot, monkeypatch):
        """Après `MAX_ECHECS` échecs consécutifs, insister coûterait un timeout de
        60 s par candidate restante pour un résultat connu d'avance."""
        import app.services.reverification_scoring as scoring

        reponses = lot(nb_reponses=8)
        appels = []

        def _compte(messages, **k):
            appels.append(1)
            raise RuntimeError("timeout")

        monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
        monkeypatch.setattr(scoring, "chat", _compte)

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert len(appels) == MAX_ECHECS, "le reliquat ne doit pas être retenté une par une"
        assert bilan["nb_indisponibles"] == len(reponses)
        assert all(r.a_relire_raison == RAISON_INDISPONIBLE for r in reponses)
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_version_depassee_abandonne_sans_juger(self, lot, monkeypatch):
        """Une v3 est passée entre-temps : elle a reflagué le même périmètre à son
        propre numéro et porte son propre job. Juger sur un diff périmé
        prononcerait des verdicts sur un texte qui n'est plus servi."""
        import app.services.reverification_scoring as scoring

        [r] = lot()
        monkeypatch.setattr(scoring, "chat", _interdit)
        doc = lot.db.query(Document).filter(Document.doc_id == lot.doc_id).one()
        doc.version = 3
        lot.db.commit()

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["statut"] == "DEPASSE"
        assert r.obsolete is False
        assert r.a_relire_raison == RAISON_INDISPONIBLE
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_unites_perdues_ne_passent_pas_pour_un_reformatage(self, lot, monkeypatch):
        """`document_update_job` n'enfile qu'avec au moins une unité. Arriver ici
        sans unité signale une ligne de version tronquée, pas un document
        inchangé : se taire laisserait les réponses en analyse pour toujours."""
        import app.services.reverification_scoring as scoring

        [r] = lot(unites=[])
        monkeypatch.setattr(scoring, "chat", _interdit)

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE)

        lot.db.expire_all()
        assert bilan["nb_indisponibles"] == 1
        assert r.a_relire_raison == RAISON_INDISPONIBLE
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []


@pytest.mark.integration
class TestFiletDeDernierRecours:
    def test_rabattre_resout_ce_que_le_job_n_a_pas_vu(self, lot):
        """Le filet du `on_failure` : un worker tué net (OOM, SIGKILL) n'exécute
        aucun `finally`. Sans rabattement, ses réponses restent servies, marquées
        douteuses, et ne sont jamais présentées à personne."""
        reponses = lot(nb_reponses=3)
        assert len(restees_en_analyse(lot.db, lot.doc_id, 2)) == 3

        nb = rabattre(lot.db, lot.doc_id, 2, RAISON_INDISPONIBLE, "Le service n'a pas repondu.")

        lot.db.expire_all()
        assert nb == 3
        assert all(r.a_relire_raison == RAISON_INDISPONIBLE for r in reponses)
        assert all(r.obsolete is False for r in reponses)
        assert restees_en_analyse(lot.db, lot.doc_id, 2) == []

    def test_rabattre_est_idempotent(self, lot):
        lot(nb_reponses=2)
        rabattre(lot.db, lot.doc_id, 2, RAISON_INDISPONIBLE, "Panne.")

        assert rabattre(lot.db, lot.doc_id, 2, RAISON_INDISPONIBLE, "Panne.") == 0

    def test_rabattre_ignore_les_autres_lots(self, lot):
        """Le drapeau porte un `(doc_id, version)` : rabattre le lot d'un document
        ne doit pas clore l'analyse en cours d'un autre."""
        reponses = lot(nb_reponses=1)
        autre_doc = str(uuid.uuid4())
        reponses[0].a_relire_doc_id = autre_doc
        lot.db.commit()

        assert rabattre(lot.db, lot.doc_id, 2, RAISON_INDISPONIBLE, "Panne.") == 0
        lot.db.expire_all()
        assert reponses[0].a_relire_raison == RAISON_ANALYSE


def _interdit(*a, **k):
    raise AssertionError("aucun appel à Albert ne devait avoir lieu")


def _casse(*a, **k):
    raise RuntimeError("503 Service Unavailable")


# ──────────────────────────────────────────────────────────────────────────────
# Le test qui démontre que les trois défauts d'origine sont réglés
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestBoutEnBout:
    """v1 → v2 : un chiffre change dans un article cité, un article est ajouté ailleurs.

    Les trois défauts de l'ancien pipeline apparaissent tous dans ce seul scénario :

    1. **faux positifs** — la canonique dont le chunk cité a été retouché était
       détruite d'office ; ici elle n'est retirée que parce qu'un modèle a lu sa
       question, son texte et le diff, et a conclu qu'elle était fausse. La
       jumelle, dont le passage cité a bougé mais dont le fond tient, survit.
    2. **faux négatifs** — l'article ajouté ne touche aucun chunk cité ; l'ancien
       pipeline ne pouvait pas le voir, et la réponse concernée continuait d'être
       servie automatiquement.
    3. **inondation** — les dix autres réponses du domaine, qu'aucun changement ne
       concerne, ne bougent pas. L'ancien `marquer_a_relire` les flaguait toutes.
    """

    @staticmethod
    def _verdicts(monkeypatch, table: dict[str, str]):
        """Le modèle répond selon la question posée — comme il le ferait vraiment."""
        import app.services.reverification_scoring as scoring

        def _chat(messages, **k):
            contenu = messages[1]["content"]
            for motif, verdict in table.items():
                if motif in contenu:
                    return '{"verdict": "%s", "justification": "Verdict sur %s."}' % (verdict, motif)
            return '{"verdict": "INTACTE", "justification": "Sans rapport."}'

        monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
        monkeypatch.setattr(scoring, "chat", _chat)

    def test_une_obsolete_justifiee_une_relecture_zero_faux_positif(self, lot, monkeypatch, db_session):
        import app.services.reverification_candidates as candidates

        # Deux citantes : celle dont le plafond est faux, et une voisine de texte
        # dont le passage cité a bougé sans que le fond en souffre.
        contredite, epargnee = lot(nb_reponses=2)
        contredite.contenu = "Le plafond de remboursement est de 200 euros par mois."
        db_session.query(Ticket).filter(
            Ticket.id == contredite.ticket_id
        ).one().question = "Quel est le plafond de remboursement ?"
        epargnee.contenu = "La demande se fait via le portail RH."
        db_session.query(Ticket).filter(Ticket.id == epargnee.ticket_id).one().question = "Comment faire ma demande ?"

        # Une non-citante : elle répond sur un autre document, mais l'article ajouté
        # la contredit. Aucun chunk cité ne bouge — l'ancien pipeline était aveugle.
        ticket = Ticket(question="Le teletravail est-il suspendu ?", domaine=DOMAINE, statut_job="TERMINÉ")
        db_session.add(ticket)
        db_session.flush()
        non_citante = Reponse(
            ticket_id=ticket.id,
            contenu="Non, le teletravail n'est jamais suspendu.",
            source="LLM",
            statut="VALIDÉE",
            canonique=True,
            nb_validations=12,
        )
        db_session.add(non_citante)

        # Dix réponses du domaine que rien ne concerne.
        temoins = []
        for i in range(10):
            t = Ticket(question=f"Question temoin {i} ?", domaine=DOMAINE, statut_job="TERMINÉ")
            db_session.add(t)
            db_session.flush()
            r = Reponse(ticket_id=t.id, contenu=f"Reponse temoin {i}.", source="LLM", statut="VALIDÉE")
            db_session.add(r)
            temoins.append(r)
        db_session.commit()

        # Le rappel vectoriel ne ramène que la non-citante : c'est ce que ferait
        # Qdrant sur l'article ajouté, et c'est le seul rapprochement pertinent.
        monkeypatch.setattr(candidates, "_voisines", lambda db, domaine, unites: [non_citante])
        self._verdicts(
            monkeypatch,
            {
                "plafond de remboursement": "CONTREDITE",
                "portail RH": "INTACTE",
                "jamais suspendu": "CONTREDITE",
            },
        )

        bilan = reverification_job(doc_id=lot.doc_id, version=2, domaine=DOMAINE, indices_disparus=[0])

        db_session.expire_all()
        # 1. La citante contredite est retirée du service, avec sa justification.
        assert contredite.obsolete is True
        assert contredite.obsolete_raison == "CONTREDITE_PAR_MAJ"
        assert contredite.analyse_justification
        # 1 bis. Sa jumelle, dont le passage cité a pourtant bougé, est épargnée.
        assert (epargnee.obsolete, epargnee.a_relire) == (False, False)
        # 2. La non-citante est signalée mais reste servie : le rapprochement
        #    vectoriel paragraphe↔question ne suffit pas à détruire 12 validations.
        assert non_citante.obsolete is False
        assert non_citante.a_relire is True
        assert non_citante.a_relire_raison == "CONTREDITE_PROBABLE"
        # 3. Les dix témoins n'ont pas bougé d'un pouce.
        assert all((r.obsolete, r.a_relire) == (False, False) for r in temoins)

        assert (bilan["nb_contredites"], bilan["nb_a_relire"], bilan["nb_intactes"]) == (1, 1, 1)
        assert restees_en_analyse(db_session, lot.doc_id, 2) == []
