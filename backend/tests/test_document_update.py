"""Tests du job de mise à jour d'un document (`app/workers/document_update.py`).

Ce job est le seul endroit du code où l'ordre des opérations est une question de
correction et pas de style : capturer le texte sortant après l'avoir supprimé
rendrait la détection d'obsolescence aveugle, et supprimer avant d'écrire
ouvrirait un trou de service. Les tests d'ordonnancement ci-dessous portent donc
sur `mock_client.method_calls`, pas seulement sur l'état final.
"""

import os
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from qdrant_client.models import Range

TEXTE_V1 = (
    "Le télétravail est limité à 2 jours par semaine, sur accord du manager.\n\n"
    "La demande se fait via le portail RH, au moins 5 jours ouvrés à l'avance."
)
TEXTE_V2 = TEXTE_V1.replace("2 jours", "3 jours")


def _point(index: int, contenu: str):
    """Point Qdrant réduit à ce que lit `capturer_chunks`."""
    return SimpleNamespace(payload={"chunk_index": index, "contenu": contenu})


def _noms_appels(mock) -> list[str]:
    return [nom for nom, _, _ in mock.method_calls]


# ──────────────────────────────────────────────────────────────────────────────
# Le filtre de suppression — le piège le plus coûteux du job
# ──────────────────────────────────────────────────────────────────────────────


class TestFiltreAnciens:
    def test_cible_le_document_seul(self):
        """Les points de `feedback_job` (réponses canoniques) vivent dans la même
        collection : sans le `must` sur doc_id, la mise à jour d'un document
        effacerait des réponses enregistrées."""
        from app.services.qdrant import filtre_anciens

        f = filtre_anciens("doc-42", 2)

        assert [c.key for c in f.must] == ["doc_id"]
        assert f.must[0].match.value == "doc-42"

    def test_exclut_la_version_en_cours_par_must_not_pas_par_range(self):
        """Un `Range(lt=cible)` ne matcherait pas les points backfillés, qui n'ont
        aucune clé `version` : leurs chunks survivraient et le document resterait
        indexé en double. Assertion structurelle, car c'est la structure qui est
        le bug potentiel."""
        from app.services.qdrant import filtre_anciens

        f = filtre_anciens("doc-42", 2)

        assert [c.key for c in f.must_not] == ["version"]
        assert f.must_not[0].match.value == 2
        assert not any(isinstance(getattr(c, "range", None), Range) for c in f.must + f.must_not)

    @pytest.mark.integration
    def test_capture_et_suppression_partagent_le_filtre(self, qdrant_mock, scenario_maj):
        """Capturer un ensemble et en supprimer un autre laisserait des chunks
        orphelins ou fausserait la détection."""
        from app.services.qdrant import filtre_anciens
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        attendu = filtre_anciens(scenario_maj.doc_id, 2)
        assert qdrant_mock.scroll.call_args.kwargs["scroll_filter"] == attendu
        selector = qdrant_mock.delete.call_args.kwargs["points_selector"]
        assert selector.filter == attendu


# ──────────────────────────────────────────────────────────────────────────────
# capturer_chunks
# ──────────────────────────────────────────────────────────────────────────────


class TestCapturerChunks:
    def test_pagine_jusqu_au_bout(self, qdrant_mock):
        """Un document dépassant la taille de page laisserait sinon des passages
        hors du calcul, donc des réponses obsolètes non détectées."""
        from app.services.qdrant import capturer_chunks

        qdrant_mock.scroll.side_effect = [
            ([_point(0, "a"), _point(1, "b")], "curseur"),
            ([_point(2, "c")], None),
        ]

        assert capturer_chunks("doc-42", 2) == {0: "a", 1: "b", 2: "c"}

    def test_ignore_les_points_sans_index(self, qdrant_mock):
        from app.services.qdrant import capturer_chunks

        qdrant_mock.scroll.return_value = ([_point(0, "a"), SimpleNamespace(payload={})], None)

        assert capturer_chunks("doc-42", 2) == {0: "a"}


# ──────────────────────────────────────────────────────────────────────────────
# Le job complet
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def qdrant_mock(monkeypatch):
    import app.services.qdrant as qdrant_module
    import app.workers.document_update as maj

    mock = MagicMock()
    mock.scroll.return_value = ([], None)
    monkeypatch.setattr(qdrant_module, "client", mock)
    monkeypatch.setattr(maj, "client", mock)
    return mock


@pytest.fixture
def scenario_maj(tmp_path, monkeypatch, qdrant_mock, db_session):
    """Document v1 en base + fichier v2 sur disque, prêt à passer dans le job.

    Qdrant, l'embedding et le chunking sont mockés ; le reste (Postgres, disque,
    calcul du diff) est réel — c'est là que sont les bugs.

    L'enfilement de la ré-vérification est capturé plutôt qu'exécuté :
    ``scenario_maj.enfilees`` donne les kwargs de chaque ``apply_async``. Sans
    cette interception, chaque test parlerait au broker et le job d'analyse
    tournerait pour de bon, avec ses appels Albert.
    """
    import app.workers.document_update as maj
    import app.workers.reverification as reverif
    from app.config import settings
    from app.models.document import Document
    from app.models.document_version import DocumentVersion

    enfilees: list[dict] = []
    monkeypatch.setattr(reverif.reverification_job, "apply_async", lambda **kw: enfilees.append(kw))

    monkeypatch.setattr(settings, "documents_storage_path", str(tmp_path / "storage"))
    monkeypatch.setattr(maj, "chunk_text", lambda pages: "\n\n".join(pages).split("\n\n"))
    monkeypatch.setattr(
        maj,
        "embed_texts",
        lambda chunks, is_query=False: [
            {"dense": [0.1] * 1024, "sparse": {"indices": [1], "values": [0.5]}} for _ in chunks
        ],
    )

    doc_id = str(uuid.uuid4())

    # Le fichier de la v1 sur disque, et pas seulement la ligne en base : c'est
    # lui que le job relit pour comparer les contenus. Sans lui, tous les tests
    # partiraient dans la branche dégradée `VERSION_SORTANTE_ILLISIBLE` en
    # donnant l'illusion de couvrir la détection.
    dossier_v1 = tmp_path / "storage" / doc_id / "v1"
    dossier_v1.mkdir(parents=True)
    fichier_v1 = dossier_v1 / "charte.md"
    fichier_v1.write_text(TEXTE_V1, encoding="utf-8")

    db_session.add(
        Document(
            doc_id=doc_id,
            filename="charte.md",
            domaine="RH",
            version=1,
            nb_chunks=2,
            stored_path=str(fichier_v1),
        )
    )
    db_session.add(
        DocumentVersion(
            doc_id=doc_id,
            version=1,
            filename="charte.md",
            nb_chunks=2,
            stored_path=str(fichier_v1),
        )
    )
    db_session.commit()

    # La version sortante, telle que Qdrant la conserve
    qdrant_mock.scroll.return_value = ([_point(i, t) for i, t in enumerate(TEXTE_V1.split("\n\n"))], None)

    fichier = tmp_path / "charte.md"
    fichier.write_text(TEXTE_V2, encoding="utf-8")

    return SimpleNamespace(
        doc_id=doc_id,
        db=db_session,
        fichier=fichier,
        fichier_v1=fichier_v1,
        enfilees=enfilees,
        kwargs={
            "doc_id": doc_id,
            "new_version": 2,
            "file_path": str(fichier),
            "filename": "charte.md",
            "description": "Charte télétravail",
            "content_hash": "hash-v2",
            "uploaded_by": None,
        },
    )


@pytest.mark.integration
class TestOrdonnancement:
    def test_capture_avant_toute_suppression(self, qdrant_mock, scenario_maj):
        """Le test décisif : Qdrant est la **seule** source du texte sortant.
        Supprimer avant de capturer rendrait la détection d'obsolescence aveugle,
        silencieusement — aucune réponse ne serait jamais marquée."""
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        appels = _noms_appels(qdrant_mock)
        assert appels.index("scroll") < appels.index("delete")

    def test_upsert_avant_delete(self, qdrant_mock, scenario_maj):
        """Zéro trou de service : l'ordre inverse laisserait le document sans
        aucun chunk pendant toute la durée de l'embedding."""
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        appels = _noms_appels(qdrant_mock)
        # Le dernier `delete` — le premier est la purge défensive d'un retry partiel.
        dernier_delete = len(appels) - 1 - appels[::-1].index("delete")
        assert appels.index("upsert") < dernier_delete


@pytest.mark.integration
class TestJobComplet:
    def test_bascule_la_version(self, scenario_maj):
        from app.models.document import Document
        from app.workers.document_update import document_update_job

        resultat = document_update_job(**scenario_maj.kwargs)

        doc = scenario_maj.db.query(Document).filter(Document.doc_id == scenario_maj.doc_id).first()
        scenario_maj.db.refresh(doc)
        assert doc.version == 2
        assert doc.statut == "ACTIF"
        assert doc.update_job_id is None
        assert resultat["version"] == 2

    def test_archive_la_version_sortante(self, scenario_maj):
        """`remplacee_at IS NULL` identifie la version courante : deux lignes nulles
        rendraient l'historique inexploitable."""
        from app.models.document_version import DocumentVersion
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        lignes = (
            scenario_maj.db.query(DocumentVersion)
            .filter(DocumentVersion.doc_id == scenario_maj.doc_id)
            .order_by(DocumentVersion.version)
            .all()
        )
        for ligne in lignes:
            scenario_maj.db.refresh(ligne)
        assert [ligne.version for ligne in lignes] == [1, 2]
        assert lignes[0].remplacee_at is not None
        assert lignes[1].remplacee_at is None

    def test_fichier_range_sous_la_nouvelle_version(self, scenario_maj):
        from app.workers.document_update import document_update_job

        resultat = document_update_job(**scenario_maj.kwargs)

        assert resultat["stored_path"].endswith(f"{scenario_maj.doc_id}/v2/charte.md")
        assert os.path.isfile(resultat["stored_path"])

    def test_temporaire_supprime(self, scenario_maj):
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        assert not scenario_maj.fichier.exists()

    def test_points_portent_la_nouvelle_version(self, qdrant_mock, scenario_maj):
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        points = qdrant_mock.upsert.call_args.kwargs["points"]
        assert {p.payload["version"] for p in points} == {2}
        assert {p.payload["doc_id"] for p in points} == {scenario_maj.doc_id}
        # stored_path renseigné dès l'upsert : pas de set_payload correctif, donc
        # pas de fenêtre où les points portent stored_path: None.
        assert all(p.payload["stored_path"] for p in points)

    def test_ids_de_points_deterministes(self, qdrant_mock, scenario_maj):
        """Un retry après un upsert partiel doit réécrire les mêmes points plutôt
        que d'en créer de nouveaux — sinon chaque tentative double l'indexation."""
        from app.workers.document_update import document_update_job
        from app.workers.ingestion import point_id

        document_update_job(**scenario_maj.kwargs)

        ids = [p.id for p in qdrant_mock.upsert.call_args.kwargs["points"]]
        assert ids == [point_id(scenario_maj.doc_id, 2, i) for i in range(len(ids))]

    def test_reprise_idempotente(self, scenario_maj):
        """Un retry après un job abouti ne doit pas rejouer une seconde bascule."""
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)
        scenario_maj.db.expire_all()
        scenario_maj.fichier.write_text(TEXTE_V2, encoding="utf-8")

        second = document_update_job(**scenario_maj.kwargs)

        assert second["nb_a_analyser"] == 0
        assert scenario_maj.fichier.exists()  # le job n'est pas allé jusqu'au ménage


@pytest.mark.integration
class TestMiseSousAnalyse:
    @staticmethod
    def _reponse_sur(db, doc_id, chunk_index):
        from app.models.reponse import Reponse
        from app.models.reponse_chunk import ReponseChunk
        from app.models.ticket import Ticket

        ticket = Ticket(question="Combien de jours de télétravail ?", domaine="RH", statut_job="TERMINÉ")
        db.add(ticket)
        db.flush()
        r = Reponse(ticket_id=ticket.id, contenu="Deux jours.", source="LLM", statut="VALIDÉE", canonique=True)
        db.add(r)
        db.flush()
        db.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, chunk_index=chunk_index))
        db.commit()
        return r

    def test_passage_cite_modifie_ne_perime_plus_rien(self, scenario_maj):
        """Le correctif du défaut n° 1, exprimé comme test.

        Un chunk fait 384 tokens : y corriger un chiffre le rend introuvable en
        sous-chaîne, et cela suffisait à détruire la réponse. Le job ne prononce
        plus ce verdict — il met la réponse sous analyse et laisse
        ``reverification_job`` la lire avant de trancher."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 0)

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert r.obsolete is False  # toujours servie tant que personne n'a jugé
        assert r.a_relire is True
        assert r.a_relire_raison == "ANALYSE_EN_COURS"
        assert r.a_relire_version == 2
        assert resultat["nb_a_analyser"] == 1

    def test_chunk_cite_disparu_transmis_comme_suspicion(self, scenario_maj):
        """`indices_modifies` est rétrogradé de verdict à signal de rappel : il
        ne périme plus, il désigne les réponses à juger en premier."""
        from app.workers.document_update import document_update_job

        self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 0)

        document_update_job(**scenario_maj.kwargs)

        assert len(scenario_maj.enfilees) == 1
        kwargs = scenario_maj.enfilees[0]["kwargs"]
        assert kwargs["doc_id"] == scenario_maj.doc_id
        assert kwargs["version"] == 2
        assert kwargs["domaine"] == "RH"
        assert kwargs["indices_disparus"] == [0]  # le 1er paragraphe a été réécrit
        assert scenario_maj.enfilees[0]["queue"] == "queue_questions"

    def test_reponse_sur_passage_intact_part_aussi_en_analyse(self, scenario_maj):
        """Le correctif du défaut n° 2 : le périmètre est le document entier.

        Cibler « près de la zone modifiée » raterait précisément le cas visé —
        un article ajouté ailleurs qui contredit une réponse bâtie sur un passage
        resté intact."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert r.obsolete is False
        assert r.a_relire is True
        assert resultat["nb_a_analyser"] == 1

    def test_reformatage_ne_declenche_rien(self, scenario_maj):
        """Le correctif du défaut n° 3 : zéro unité de changement ⇒ zéro action.

        Ni obsolescence, ni relecture, ni même job d'analyse — le redépôt du
        même contenu ne doit rien coûter et ne rien salir."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 0)
        scenario_maj.fichier.write_text(TEXTE_V1.replace(" ", "  "), encoding="utf-8")

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert r.obsolete is False
        assert r.a_relire is False
        assert resultat["nb_a_analyser"] == 0
        assert scenario_maj.enfilees == []

    def test_en_attente_marquee_obsolete(self, scenario_maj):
        """Une réponse EN_ATTENTE liée au document devient obsolète même si aucune
        réponse VALIDÉE n'est impactée : indexer une réponse bâtie sur l'ancienne
        version introduirait une information périmée dès la première validation."""
        from app.models.reponse import Reponse
        from app.models.reponse_chunk import ReponseChunk
        from app.models.ticket import Ticket
        from app.workers.document_update import document_update_job

        ticket = Ticket(question="Q?", domaine="RH", statut_job="TERMINÉ")
        scenario_maj.db.add(ticket)
        scenario_maj.db.flush()
        r = Reponse(ticket_id=ticket.id, contenu="R.", source="LLM", statut="EN_ATTENTE")
        scenario_maj.db.add(r)
        scenario_maj.db.flush()
        scenario_maj.db.add(ReponseChunk(reponse_id=r.id, doc_id=scenario_maj.doc_id, chunk_index=0))
        scenario_maj.db.commit()

        document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert r.obsolete is True
        assert r.obsolete_raison == "DOC_MIS_A_JOUR"


@pytest.mark.integration
class TestSignalementARelire:
    """Le repli, pour les seuls cas où aucun diff n'est calculable.

    Signaler tout le document sans filtre était la règle ; c'est désormais
    l'exception — la version sortante illisible. Partout ailleurs le tri revient
    à ``reverification_job``, qui juge réponse par réponse.
    """

    _reponse_sur = staticmethod(TestMiseSousAnalyse._reponse_sur)

    def test_ajout_ailleurs_met_en_analyse(self, scenario_maj):
        """Le scénario de référence : l'article ajouté ne touche aucun passage
        cité. Rien ne peut être prononcé sans lire la réponse — elle part donc
        en analyse, et continue d'être servie en attendant."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)
        scenario_maj.fichier.write_text(
            TEXTE_V1 + "\n\nArticle 7 bis : le télétravail est suspendu en période de forte activité.",
            encoding="utf-8",
        )

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert resultat["nb_a_analyser"] == 1
        assert resultat["nb_a_relire"] == 0
        assert r.obsolete is False  # toujours servie
        assert r.a_relire is True
        assert r.a_relire_raison == "ANALYSE_EN_COURS"
        assert r.a_relire_doc_id == scenario_maj.doc_id
        assert r.a_relire_version == 2

    def test_passage_retire_ailleurs_met_en_analyse(self, scenario_maj):
        """Une règle abrogée, rien d'inséré : le sens inverse est le seul à voir."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 0)
        scenario_maj.fichier.write_text(TEXTE_V1.split("\n\n")[0], encoding="utf-8")

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert resultat["nb_a_analyser"] == 1
        assert r.a_relire is True

    def test_reformatage_ne_signale_rien(self, scenario_maj):
        """La propriété anti-inondation, côté job. Sans elle, redéposer le même
        contenu mettrait toute la base de connaissances du document en relecture."""
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)
        scenario_maj.fichier.write_text(TEXTE_V1.replace(" ", "  "), encoding="utf-8")

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert resultat["nb_a_relire"] == 0
        assert r.a_relire is False

    def test_illisible_signale_sans_enfiler_d_analyse(self, scenario_maj):
        """Sans texte sortant il n'y a aucune unité à faire juger : enfiler le
        job ferait tourner un analyseur qui n'a rien à lire, et le retour
        « 0 contredite » se lirait comme un feu vert."""
        from app.workers.document_update import document_update_job

        self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)
        scenario_maj.fichier_v1.unlink()

        resultat = document_update_job(**scenario_maj.kwargs)

        assert resultat["nb_a_analyser"] == 0
        assert scenario_maj.enfilees == []

    def test_version_sortante_illisible_signale_avec_sa_raison(self, scenario_maj):
        """Document backfillé ou archive disparue : on ne peut plus comparer.

        Se taire laisserait passer un changement réel ; réutiliser la raison du
        signal normal ferait croire à une détection qui n'a pas eu lieu. La
        liste dit donc elle-même pourquoi elle est bruyante.
        """
        from app.workers.document_update import document_update_job

        r = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)
        scenario_maj.fichier_v1.unlink()

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert resultat["nb_a_relire"] == 1
        assert r.a_relire_raison == "VERSION_SORTANTE_ILLISIBLE"

    def test_toutes_les_validees_partent_en_analyse_aucune_perimee(self, scenario_maj):
        """La règle centrale, après renversement : le job ne détruit plus rien.

        r0 cite le chunk 0 (réécrit), r1 le chunk 1 (intact). Les deux restent
        servies et passent sous analyse ; c'est le verdict de ``juger`` qui les
        départagera, pas la présence d'une sous-chaîne."""
        from app.workers.document_update import document_update_job

        r0 = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 0)
        r1 = self._reponse_sur(scenario_maj.db, scenario_maj.doc_id, 1)

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r0)
        scenario_maj.db.refresh(r1)
        assert (r0.obsolete, r1.obsolete) == (False, False)
        assert (r0.a_relire, r1.a_relire) == (True, True)
        assert resultat["nb_a_analyser"] == 2
        assert resultat["nb_a_relire"] == 0

    def test_en_attente_obsolete_pas_a_relire(self, scenario_maj):
        """EN_ATTENTE : obsolète immédiatement, jamais dans l'onglet À relire.

        La signaler pour relecture n'aurait aucun sens : elle n'est pas encore
        indexée et ne sera jamais servie telle quelle."""
        from app.models.reponse import Reponse
        from app.models.reponse_chunk import ReponseChunk
        from app.models.ticket import Ticket
        from app.workers.document_update import document_update_job

        ticket = Ticket(question="Q?", domaine="RH", statut_job="TERMINÉ")
        scenario_maj.db.add(ticket)
        scenario_maj.db.flush()
        r = Reponse(ticket_id=ticket.id, contenu="R.", source="LLM", statut="EN_ATTENTE")
        scenario_maj.db.add(r)
        scenario_maj.db.flush()
        scenario_maj.db.add(ReponseChunk(reponse_id=r.id, doc_id=scenario_maj.doc_id, chunk_index=1))
        scenario_maj.db.commit()
        scenario_maj.fichier.write_text(
            TEXTE_V1 + "\n\nArticle 7 bis : le télétravail est suspendu en période de forte activité.",
            encoding="utf-8",
        )

        resultat = document_update_job(**scenario_maj.kwargs)

        scenario_maj.db.refresh(r)
        assert r.obsolete is True
        assert r.a_relire is False
        assert resultat["nb_a_relire"] == 0

    def test_changements_ecrits_sur_la_version(self, scenario_maj):
        """Les extraits sont figés à la mise à jour : la liste se consulte des
        jours plus tard, quand l'archive sortante peut avoir été purgée."""
        from app.models.document_version import DocumentVersion
        from app.workers.document_update import document_update_job

        document_update_job(**scenario_maj.kwargs)

        ligne = (
            scenario_maj.db.query(DocumentVersion)
            .filter(
                DocumentVersion.doc_id == scenario_maj.doc_id,
                DocumentVersion.version == 2,
            )
            .first()
        )
        scenario_maj.db.refresh(ligne)
        # TEXTE_V2 réécrit le 1er paragraphe : il est à la fois ajouté et retiré.
        assert ligne.changements["nb_ajoutes"] == 1
        assert ligne.changements["nb_retires"] == 1
        assert "3 jours" in ligne.changements["extraits_ajoutes"][0]
        assert "2 jours" in ligne.changements["extraits_retires"][0]


@pytest.mark.integration
class TestOnFailure:
    def test_libere_le_verrou(self, scenario_maj):
        """Sans ce filet, un échec laisserait le document `EN_MAJ` à vie : plus
        aucune mise à jour ni suppression possible."""
        from app.models.document import Document
        from app.workers.document_update import document_update_job

        doc = scenario_maj.db.query(Document).filter(Document.doc_id == scenario_maj.doc_id).first()
        doc.statut = "EN_MAJ"
        doc.update_job_id = "job-mort"
        scenario_maj.db.commit()

        document_update_job.on_failure(RuntimeError("boom"), "job-mort", (), scenario_maj.kwargs, None)

        scenario_maj.db.expire_all()
        doc = scenario_maj.db.query(Document).filter(Document.doc_id == scenario_maj.doc_id).first()
        assert doc.statut == "ACTIF"
        assert doc.update_job_id is None
        assert doc.version == 1  # l'ancienne indexation est toujours en place

    def test_nettoie_le_fichier_de_staging(self, scenario_maj):
        from app.workers.document_update import document_update_job

        document_update_job.on_failure(RuntimeError("boom"), "job-mort", (), scenario_maj.kwargs, None)

        assert not scenario_maj.fichier.exists()
