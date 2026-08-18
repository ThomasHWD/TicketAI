"""Tests pour preview/confirm, historique des versions et statut de job."""

import os
import uuid
from unittest.mock import patch

import pytest

from .helpers import (
    _ARTICLE_ABROGE,
    _ARTICLE_AJOUTE,
    _TEXTE_V1,
    _TEXTE_V2,
    API,
    _admin_id,
    _doc_avec_fichier,
    _doc_en_base,
    _preview,
    _reponse_sur_chunk,
    _version_en_base,
)


@pytest.mark.integration
class TestPreviewMaj:
    def test_404_document_inconnu(self, client, db_reelle, staging_tmp, qdrant_maj):
        assert _preview(client, str(uuid.uuid4())).status_code == 404

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")

        assert _preview(client, doc.doc_id).status_code == 403

    def test_409_si_maj_en_cours(self, client, db_reelle, staging_tmp, qdrant_maj):
        from datetime import datetime, timezone

        doc = _doc_en_base(
            db_reelle,
            content_hash="hash-v1",
            statut="EN_MAJ",
            update_started_at=datetime.now(timezone.utc),
        )

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "en cours" in r.json()["detail"]

    def test_verrou_perime_ne_bloque_plus(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Un worker tué net n'exécute pas `on_failure` : sans péremption, le
        document resterait verrouillé à vie."""
        from datetime import datetime, timedelta, timezone

        doc = _doc_en_base(
            db_reelle,
            content_hash="hash-v1",
            statut="EN_MAJ",
            update_started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        assert _preview(client, doc.doc_id).status_code == 200

    def test_409_fichier_identique(self, client, db_reelle, staging_tmp, qdrant_maj):
        import hashlib

        doc = _doc_en_base(db_reelle, content_hash=hashlib.sha256(_TEXTE_V2).hexdigest())

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "identique" in r.json()["detail"]

    def test_hash_null_autorise_et_renseigne(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Document backfillé : on ne peut pas prouver l'identité, donc on ne
        l'interdit pas — et on en profite pour renseigner le hash manquant."""
        doc = _doc_en_base(db_reelle, content_hash=None)

        assert _preview(client, doc.doc_id).status_code == 200

        db_reelle.refresh(doc)
        assert doc.content_hash is not None

    def test_409_contenu_deja_indexe_ailleurs(self, client, db_reelle, staging_tmp, qdrant_maj):
        import hashlib

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        _doc_en_base(db_reelle, filename="autre.md", content_hash=hashlib.sha256(_TEXTE_V2).hexdigest())

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "autre.md" in r.json()["detail"]

    def test_impact_exact(self, client, db_reelle, staging_tmp, qdrant_maj):
        """L'aperçu doit nommer les réponses dont un passage cité a bougé, pas les
        estimer : annoncer 12 impactées puis n'en juger que 2 serait pire qu'inutile."""
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id).json()

        assert body["version_cible"] == 2
        assert body["nb_total_chunks"] == 2
        assert body["nb_chunks_modifies"] == 1
        assert body["nb_prioritaires"] == 1
        item = body["items"][0]
        assert item["reponse_id"] == str(reponse.id)
        assert item["chunks_modifies"] == [0]
        assert "2 jours" in item["extraits"][0]

    def test_ne_modifie_rien(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from app.models.document import Document

        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        _preview(client, doc.doc_id)

        db_reelle.refresh(reponse)
        db_reelle.refresh(doc)
        assert reponse.obsolete is False
        assert doc.statut == "ACTIF"
        assert db_reelle.query(Document).filter(Document.doc_id == doc.doc_id).first().version == 1
        mock_maj_job.apply_async.assert_not_called()

    def test_passage_intact_zero_obsolete(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH")

        body = _preview(client, doc.doc_id).json()

        assert body["nb_chunks_modifies"] == 1
        assert body["nb_prioritaires"] == 0

    def test_purge_les_apercus_expires(self, client, db_reelle, staging_tmp, qdrant_maj):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        vieux_fichier = staging_tmp / "abandonne.md"
        vieux_fichier.write_bytes(_TEXTE_V1)
        db_reelle.add(
            DocumentStaging(
                doc_id=doc.doc_id,
                stored_path=str(vieux_fichier),
                filename="abandonne.md",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        db_reelle.commit()

        _preview(client, doc.doc_id)

        assert not vieux_fichier.exists()
        assert db_reelle.query(DocumentStaging).filter(DocumentStaging.filename == "abandonne.md").first() is None


@pytest.mark.integration
class TestAjoutsSignales:
    """Ce que la nouvelle version dit de neuf, et que les chunks cités ne voient pas.

    L'aperçu ne condamne rien : il compte les unités de changement et annonce
    combien de réponses seront jugées après confirmation. Sans ce second signal,
    une charte enrichie d'un « article 7 bis » qui contredit une réponse ne
    toucherait aucun passage cité et passerait entièrement inaperçue.
    """

    def test_signale_un_ajout_qui_ne_rend_rien_obsolete(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_chunks_modifies"] == 0
        assert body["nb_prioritaires"] == 0
        assert body["diff_analysable"] is True
        assert body["nb_ajoutes"] == 1
        assert "Article 7 bis" in body["extraits_ajoutes"][0]
        assert body["nb_a_analyser"] == 1

    def test_nomme_les_reponses_a_relire(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Un compte seul n'est pas actionnable : « 4 réponses n'en tiennent pas
        compte » oblige à les retrouver à la main, donc personne ne le fait.
        L'aperçu doit livrer de quoi ouvrir chacune, `ticket_id` compris."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_a_analyser"] == 1
        [item] = body["a_analyser"]
        assert item["reponse_id"] == str(reponse.id)
        assert item["ticket_id"] == str(reponse.ticket_id)
        assert item["question"] == "Combien de jours de télétravail ?"
        assert item["canonique"] is True
        assert item["nb_validations"] == 3

    def test_les_plus_servies_en_tete(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Une canonique à 12 validations part sur tous les tickets similaires ;
        une VALIDÉE isolée ne ressort presque jamais. L'ordre de relecture doit
        suivre le risque réel, pas l'ordre d'insertion en base."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH", nb_validations=1)
        forte = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH", nb_validations=12)

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert [i["nb_validations"] for i in body["a_analyser"]] == [12, 1]
        assert body["a_analyser"][0]["reponse_id"] == str(forte.id)

    def test_plafonne_la_liste_sans_fausser_le_compte(self, client, db_reelle, staging_tmp, qdrant_maj):
        """La modale amorce le tri, elle ne le porte pas. Mais tronquer le *compte*
        minimiserait la charge annoncée : seule la liste est plafonnée."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        for _ in range(12):
            _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_a_analyser"] == 12
        assert len(body["a_analyser"]) == 10

    def test_aucun_ajout_sur_un_simple_reformatage(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Le panneau doit rester silencieux quand rien n'a été écrit : sinon il
        s'affiche à chaque mise à jour et cesse d'être lu."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reformate = _TEXTE_V1.replace(b"\n\n", b"\n\n\n").replace(b" par ", b"  par ")

        body = _preview(client, doc.doc_id, content=reformate).json()

        assert body["diff_analysable"] is True
        assert body["nb_ajoutes"] == 0
        assert body["extraits_ajoutes"] == []

    def test_le_chunk_cite_modifie_est_une_priorite_pas_une_condamnation(
        self, client, db_reelle, staging_tmp, qdrant_maj
    ):
        """Les deux compteurs ne se retranchent pas : ils se superposent.

        `nb_prioritaires` désigne les réponses dont un passage cité a bougé — elles
        seront jugées **d'abord**, pas supprimées d'office. `nb_a_analyser` couvre
        toutes les survivantes du document, y compris celles dont les passages
        cités sont intacts : la contradiction peut venir de l'article ajouté.
        """
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")  # passage réécrit
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH")  # passage intact

        body = _preview(client, doc.doc_id, content=_TEXTE_V2 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_prioritaires"] == 1
        assert body["nb_ajoutes"] >= 1
        assert body["nb_a_analyser"] == 2
        assert body["nb_canoniques"] == 2
        assert body["a_analyser"][0]["reponse_id"] == body["items"][0]["reponse_id"]

    def test_document_backfille_tait_le_panneau(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Sans fichier courant sur disque, il n'y a rien à comparer. Renvoyer
        « 0 passage ajouté » se lirait comme une garantie ; on ne dit rien."""
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1", stored_path=None)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["diff_analysable"] is False
        assert body["nb_ajoutes"] == 0
        assert body["nb_a_analyser"] == 0

    def test_archive_illisible_ne_fait_pas_echouer_l_apercu(self, client, db_reelle, staging_tmp, qdrant_maj):
        """L'obsolescence, elle, est déjà calculée : perdre le signal secondaire ne
        doit pas coûter le signal principal."""
        corrompu = staging_tmp / "corrompu.pdf"
        corrompu.write_bytes(b"%PDF-1.4 ceci n'est pas un PDF")
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1", stored_path=str(corrompu))
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        r = _preview(client, doc.doc_id)

        assert r.status_code == 200
        assert r.json()["nb_prioritaires"] == 1
        assert r.json()["diff_analysable"] is False


@pytest.mark.integration
class TestRetraitsSignales:
    """L'autre sens : ce que la nouvelle version ne dit plus.

    Le seul cas qu'un compte d'ajouts ne peut pas voir — une règle **abrogée**
    sans que rien ne soit inséré à la place. Aucun passage cité ne bouge, aucun
    passage n'apparaît, et pourtant une réponse qui s'appuyait sur l'existence de
    cette règle est peut-être devenue fausse. Sans ce sens, elle continuerait
    d'être servie sans jamais être soumise au jugement.
    """

    def test_signale_un_passage_retire_ailleurs(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_avec_fichier(db_reelle, staging_tmp, contenu=_TEXTE_V1 + b"\n\n" + _ARTICLE_ABROGE)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1).json()

        assert body["nb_chunks_modifies"] == 0
        assert body["nb_prioritaires"] == 0
        assert body["nb_ajoutes"] == 0
        assert body["nb_retires"] == 1
        assert "Article 9" in body["extraits_retires"][0]
        assert body["nb_a_analyser"] == 1

    def test_reformatage_ne_tire_dans_aucun_sens(self, client, db_reelle, staging_tmp, qdrant_maj):
        """La propriété anti-inondation, vérifiée sur les deux sens à la fois :
        un second compteur toujours non nul rendrait le panneau permanent."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reformate = _TEXTE_V1.replace(b"\n\n", b"\n\n\n").replace(b" par ", b"  par ")

        body = _preview(client, doc.doc_id, content=reformate).json()

        assert body["nb_ajoutes"] == 0
        assert body["nb_retires"] == 0
        assert body["extraits_retires"] == []
        assert body["nb_a_analyser"] == 0

    def test_document_backfille_tait_les_deux_sens(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1", stored_path=None)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1).json()

        assert body["diff_analysable"] is False
        assert body["nb_retires"] == 0
        assert body["extraits_retires"] == []


@pytest.mark.integration
class TestConfirmMaj:
    def test_lance_le_job_et_pose_le_verrou(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        staging_id = _preview(client, doc.doc_id).json()["staging_id"]

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id})

        body = r.json()
        assert r.status_code == 200
        assert set(body) == {"job_id", "doc_id", "filename", "version", "statut"}
        assert body["version"] == 2
        assert body["statut"] == "EN_ATTENTE"

        db_reelle.refresh(doc)
        assert doc.statut == "EN_MAJ"
        assert doc.update_job_id == body["job_id"]

        envoyes = mock_maj_job.apply_async.call_args.kwargs["kwargs"]
        assert envoyes["new_version"] == 2
        assert envoyes["doc_id"] == doc.doc_id
        assert os.path.isfile(envoyes["file_path"])

    def test_consomme_l_apercu(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        """Rejouer la même confirmation ne doit pas relancer un second job."""
        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        staging_id = _preview(client, doc.doc_id).json()["staging_id"]
        client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id})

        assert db_reelle.query(DocumentStaging).count() == 0

    def test_404_apercu_inconnu(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        doc = _doc_en_base(db_reelle, content_hash="hash-v1")

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(uuid.uuid4())})

        assert r.status_code == 404

    def test_403_apercu_d_un_autre_utilisateur(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging
        from app.models.user import User

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        autre = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
        db_reelle.add(autre)
        db_reelle.commit()
        staging = DocumentStaging(
            doc_id=doc.doc_id,
            user_id=autre.id,
            stored_path=str(staging_tmp / "x.md"),
            filename="x.md",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_reelle.add(staging)
        db_reelle.commit()

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(staging.id)})

        assert r.status_code == 403

    def test_409_apercu_expire(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        fichier = staging_tmp / "expire.md"
        fichier.write_bytes(_TEXTE_V2)
        staging = DocumentStaging(
            doc_id=doc.doc_id,
            user_id=_admin_id(db_reelle),
            stored_path=str(fichier),
            filename="expire.md",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db_reelle.add(staging)
        db_reelle.commit()

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(staging.id)})

        assert r.status_code == 409
        assert "expiré" in r.json()["detail"]


@pytest.mark.integration
class TestListerVersions:
    def test_liste_decroissante_avec_la_courante_marquee(self, client, db_reelle, tmp_path):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 1, racine=tmp_path)
        _version_en_base(db_reelle, doc, 2, racine=tmp_path, restauree_depuis=1)

        body = client.get(f"{API}/documents/{doc.doc_id}/versions").json()

        assert body["version_courante"] == 2
        assert [v["version"] for v in body["items"]] == [2, 1]
        assert [v["courante"] for v in body["items"]] == [True, False]
        assert body["items"][0]["restauree_depuis"] == 1

    def test_signale_un_fichier_archive_manquant(self, client, db_reelle, tmp_path, monkeypatch):
        """Sans ce drapeau, l'UI proposerait un téléchargement voué au 404."""
        import app.api.v1.documents.core as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)
        _version_en_base(db_reelle, doc, 1, stored_path="/introuvable/charte.md")

        body = client.get(f"{API}/documents/{doc.doc_id}/versions").json()

        assert body["items"][0]["fichier_disponible"] is False

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it):
        doc = _doc_en_base(db_reelle, domaine="RH")

        assert client.get(f"{API}/documents/{doc.doc_id}/versions").status_code == 403


@pytest.mark.integration
class TestTelechargerVersion:
    def test_renvoie_le_fichier_archive(self, client, db_reelle, tmp_path):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 1, contenu=_TEXTE_V1, racine=tmp_path)
        _version_en_base(db_reelle, doc, 2, contenu=_TEXTE_V2, racine=tmp_path)

        r = client.get(f"{API}/documents/{doc.doc_id}/versions/1/download")

        assert r.status_code == 200
        assert r.content == _TEXTE_V1

    def test_404_version_inconnue(self, client, db_reelle):
        doc = _doc_en_base(db_reelle)

        assert client.get(f"{API}/documents/{doc.doc_id}/versions/9/download").status_code == 404


@pytest.mark.integration
class TestRestaurerVersion:
    """Restaurer emprunte le flux de mise à jour : aperçu d'impact, puis `confirm`."""

    def test_apercu_avec_restauree_depuis(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, contenu=_TEXTE_V1, racine=tmp_path, content_hash="hash-v1")
        _version_en_base(db_reelle, doc, 2, contenu=_TEXTE_V2, racine=tmp_path, content_hash="hash-v2")

        body = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()

        assert body["restauree_depuis"] == 1
        assert body["version_cible"] == 3
        assert body["nb_chunks_modifies"] == 0
        assert body["nb_prioritaires"] == 0

    def test_impact_calcule_comme_une_maj(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        """Restaurer peut à son tour rendre des réponses obsolètes — c'est le point."""
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0)
        _version_en_base(
            db_reelle, doc, 1, contenu=b"Texte totalement different.", racine=tmp_path, content_hash="hash-v1"
        )

        body = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()

        assert body["nb_prioritaires"] == 1
        assert body["items"][0]["chunks_modifies"] == [0]

    def test_la_confirmation_transmet_restauree_depuis(
        self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj, mock_maj_job
    ):
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, racine=tmp_path, content_hash="hash-v1")
        staging_id = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()["staging_id"]

        client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id})

        assert mock_maj_job.apply_async.call_args.kwargs["kwargs"]["restauree_depuis"] == 1

    def test_409_version_courante(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 2, racine=tmp_path)

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/2/restaurer")

        assert r.status_code == 409
        assert "déjà la version actuelle" in r.json()["detail"]

    def test_409_contenu_identique_a_la_courante(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        """Numéro différent, contenu identique : la restauration n'apporterait rien."""
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-commun")
        _version_en_base(db_reelle, doc, 1, racine=tmp_path, content_hash="hash-commun")

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer")

        assert r.status_code == 409
        assert "même contenu" in r.json()["detail"]

    def test_409_fichier_archive_absent(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj, monkeypatch):
        import app.api.v1.documents.core as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, stored_path="/introuvable/charte.md", content_hash="hash-v1")

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer")

        assert r.status_code == 409
        assert "n'est plus disponible" in r.json()["detail"]

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it, tmp_path, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", version=2)
        _version_en_base(db_reelle, doc, 1, racine=tmp_path)

        assert client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").status_code == 403


class TestDocumentStatus:
    def test_statut_pending(self, client):
        with patch("app.api.v1.documents.core.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "PENDING"
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        assert r.status_code == 200
        assert r.json()["statut"] == "PENDING"

    def test_statut_success_inclut_resultat(self, client):
        with patch("app.api.v1.documents.core.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "SUCCESS"
            mock_ar.return_value.result = {
                "filename": "doc.md",
                "doc_id": str(uuid.uuid4()),
                "stored_path": "/storage/doc.md",
                "nb_chunks": 5,
            }
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        body = r.json()
        assert body["statut"] == "SUCCESS"
        assert body["resultat"]["nb_chunks"] == 5

    def test_statut_failure_inclut_erreur(self, client):
        with patch("app.api.v1.documents.core.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "FAILURE"
            mock_ar.return_value.result = RuntimeError("Echec embedding")
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        body = r.json()
        assert body["statut"] == "FAILURE"
        assert "erreur" in body
