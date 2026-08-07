"""Tests de la détection d'obsolescence (`app/services/obsolescence.py`).

Unitaires (pas d'infra) : `indices_modifies` — la brique la plus critique, et
celle qui décide si une réponse validée cesse d'être servie.

Intégration (@pytest.mark.integration) : `reponses_obsoletes` / `marquer_obsoletes`,
qui remontent des chunks aux réponses et à leurs copies.
"""

import uuid

import pytest
from app.services.obsolescence import (
    RAISON_MAJ,
    decouper_en_passages,
    indices_modifies,
    marquer_obsoletes,
    passages_ajoutes,
    reponses_obsoletes,
)

TEXTE = (
    "Le télétravail est limité à 2 jours par semaine, sur accord du manager.\n\n"
    "La demande se fait via le portail RH, au moins 5 jours ouvrés à l'avance.\n\n"
    "Les frais d'équipement sont pris en charge à hauteur de 200 euros."
)


def _decouper(texte: str, taille: int) -> dict[int, str]:
    """Découpage naïf en tranches de `taille` caractères — suffisant ici : la
    méthode ne doit justement dépendre d'aucune stratégie de découpage."""
    return {i: texte[d : d + taille] for i, d in enumerate(range(0, len(texte), taille))}


# ──────────────────────────────────────────────────────────────────────────────
# indices_modifies
# ──────────────────────────────────────────────────────────────────────────────


class TestIndicesModifies:
    def test_chunk_inchange_non_detecte(self):
        anciens = {0: "Le télétravail est limité à 2 jours par semaine"}
        assert indices_modifies(anciens, TEXTE) == set()

    def test_redecoupage_sans_modification_ne_detecte_rien(self):
        """Le test décisif : même texte, frontières de chunks totalement différentes.

        Comparer par index produirait des faux positifs en masse ; la recherche de
        sous-chaîne doit n'en produire aucun.
        """
        anciens = _decouper(TEXTE, 40)

        assert indices_modifies(anciens, TEXTE) == set()

    def test_modification_locale_ne_touche_que_les_chunks_concernes(self):
        anciens = {
            0: "Le télétravail est limité à 2 jours par semaine",
            1: "La demande se fait via le portail RH",
            2: "Les frais d'équipement sont pris en charge",
        }
        nouveau = TEXTE.replace("2 jours", "3 jours")

        assert indices_modifies(anciens, nouveau) == {0}

    def test_chiffre_modifie_detecte(self):
        anciens = {0: "pris en charge à hauteur de 200 euros"}
        nouveau = TEXTE.replace("200 euros", "300 euros")

        assert indices_modifies(anciens, nouveau) == {0}

    def test_suppression_de_passage_detectee(self):
        anciens = {0: "Les frais d'équipement sont pris en charge à hauteur de 200 euros."}
        nouveau = TEXTE.split("\n\n")[0]

        assert indices_modifies(anciens, nouveau) == {0}

    def test_normalisation_espaces(self):
        """Retours à la ligne, espaces doubles et insécables ne sont pas des
        modifications : le document a été reformaté, pas changé."""
        anciens = {0: "limité à 2 jours\npar   semaine"}
        nouveau = "Le télétravail est limité à 2 jours par semaine, sur accord."

        assert indices_modifies(anciens, nouveau) == set()

    def test_bordures_rognees_par_le_splitter(self):
        anciens = {0: "  Le télétravail est limité à 2 jours par semaine  "}
        assert indices_modifies(anciens, TEXTE) == set()

    def test_chunk_vide_ignore(self):
        assert indices_modifies({0: "", 1: None}, TEXTE) == set()

    def test_nouveau_texte_vide_marque_tout(self):
        anciens = _decouper(TEXTE, 40)
        assert indices_modifies(anciens, "") == set(anciens)


# ──────────────────────────────────────────────────────────────────────────────
# passages_ajoutes — la détection en miroir
# ──────────────────────────────────────────────────────────────────────────────


AJOUT = "Article 7 bis : le télétravail est suspendu en période de forte activité."


class TestDecouperEnPassages:
    def test_un_passage_par_paragraphe(self):
        assert len(decouper_en_passages(TEXTE)) == 3

    def test_ecarte_titres_et_numeros_de_page(self):
        """Un PDF produit des dizaines de fragments courts. Les compter comme des
        ajouts noierait le seul passage qui compte sous du bruit de mise en page."""
        avec_bruit = "## Article 3\n\n" + TEXTE + "\n\n4"

        assert decouper_en_passages(avec_bruit) == decouper_en_passages(TEXTE)


class TestPassagesAjoutes:
    def test_document_inchange_n_ajoute_rien(self):
        """Le pendant du test décisif ci-dessus : sans cette propriété, le panneau
        crierait « passages ajoutés » à chaque reformatage."""
        assert passages_ajoutes(decouper_en_passages(TEXTE), TEXTE) == []

    def test_paragraphe_refusionne_n_est_pas_un_ajout(self):
        """Reflowing : deux paragraphes réunis en un seul. Le texte n'a pas bougé,
        seule la mise en page — et la recherche porte sur le texte complet
        normalisé, où le saut de paragraphe est devenu une simple espace."""
        fusionne = TEXTE.replace("\n\n", " ", 1)

        assert passages_ajoutes(decouper_en_passages(fusionne), TEXTE) == []

    def test_passage_insere_ailleurs_est_signale(self):
        """Le cas que `indices_modifies` ne voit pas, et la raison d'être de tout ceci.

        L'article ajouté ne touche aucun passage cité par une réponse : rien ne
        devient obsolète, et sans ce signal la contradiction resterait invisible.
        """
        nouveau = TEXTE + "\n\n" + AJOUT

        assert indices_modifies(_decouper(TEXTE, 40), nouveau) == set()
        assert passages_ajoutes(decouper_en_passages(nouveau), TEXTE) == [AJOUT]

    def test_reformulation_compte_comme_ajout(self):
        """Une phrase réécrite est à la fois « passage disparu » et « passage
        ajouté » : le doublon est assumé, les deux lectures sont vraies."""
        nouveau = TEXTE.replace("2 jours", "3 jours")

        assert passages_ajoutes(decouper_en_passages(nouveau), TEXTE) == [
            nouveau.split("\n\n")[0]
        ]

    def test_normalisation_partagee_avec_la_detection(self):
        nouveaux = ["Le télétravail est limité\nà 2 jours   par semaine, sur accord du manager."]

        assert passages_ajoutes(nouveaux, TEXTE) == []

    def test_passage_vide_ignore(self):
        assert passages_ajoutes(["", None], TEXTE) == []

    def test_ancien_texte_absent_marque_tout(self):
        """Fichier de la version courante illisible : *tout* paraît ajouté. C'est
        exactement pourquoi l'API tait le panneau au lieu de le remplir."""
        nouveaux = decouper_en_passages(TEXTE)

        assert passages_ajoutes(nouveaux, "") == nouveaux


# ──────────────────────────────────────────────────────────────────────────────
# reponses_obsoletes / marquer_obsoletes
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def scenario(db_session):
    """Fabrique de tickets/réponses/chunks sur la base de test."""
    from app.models.reponse import Reponse
    from app.models.reponse_chunk import ReponseChunk
    from app.models.ticket import Ticket

    doc_id = str(uuid.uuid4())

    def _reponse(*, chunks=(), source=None, statut="VALIDÉE", canonique=False, obsolete=False):
        ticket = Ticket(question="Combien de jours de télétravail ?", domaine="RH", statut_job="TERMINÉ")
        db_session.add(ticket)
        db_session.flush()

        r = Reponse(
            ticket_id=ticket.id,
            contenu="Deux jours hebdomadaires.",
            source="LLM",
            statut=statut,
            canonique=canonique,
            obsolete=obsolete,
            reponse_source_id=source.id if source is not None else None,
        )
        db_session.add(r)
        db_session.flush()

        for i in chunks:
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, chunk_index=i))
        db_session.commit()
        return r

    _reponse.doc_id = doc_id
    _reponse.db = db_session
    return _reponse


@pytest.fixture
def _qdrant_muet(monkeypatch):
    """`marquer_obsoletes` supprime des points : on n'a pas besoin d'un vrai Qdrant."""
    import app.services.obsolescence as module

    appels = []
    monkeypatch.setattr(module, "delete_response_point", appels.append)
    return appels


@pytest.mark.integration
class TestReponsesObsoletes:
    def test_un_seul_chunk_modifie_suffit(self, scenario):
        r = scenario(chunks=[1, 2, 3, 4, 5])

        touchees = reponses_obsoletes(scenario.db, scenario.doc_id, {3})

        assert [x.id for x in touchees] == [r.id]

    def test_chunk_intact_non_touche(self, scenario):
        scenario(chunks=[1, 2])

        assert reponses_obsoletes(scenario.db, scenario.doc_id, {7}) == []

    def test_aucun_indice_modifie_ne_touche_rien(self, scenario):
        scenario(chunks=[1, 2])

        assert reponses_obsoletes(scenario.db, scenario.doc_id, set()) == []

    def test_sans_indices_tout_le_document_est_concerne(self, scenario):
        """Cas de la suppression du document : plus aucun chunk ne survit."""
        r = scenario(chunks=[1])

        touchees = reponses_obsoletes(scenario.db, scenario.doc_id, None)

        assert [x.id for x in touchees] == [r.id]

    def test_autre_document_non_touche(self, scenario):
        scenario(chunks=[1])

        assert reponses_obsoletes(scenario.db, str(uuid.uuid4()), {1}) == []

    def test_remonte_les_copies(self, scenario):
        """Une copie SUGGESTION/CANONIQUE n'a aucun chunk : sans la descente par
        `reponse_source_id`, elle resterait servie après la mise à jour."""
        source = scenario(chunks=[1])
        copie = scenario(source=source)

        touchees = {x.id for x in reponses_obsoletes(scenario.db, scenario.doc_id, {1})}

        assert touchees == {source.id, copie.id}

    def test_transitif_profondeur_2(self, scenario):
        """A ← B ← C : `corriger_reponse` réindexe la copie, une copie peut donc
        être à son tour source."""
        a = scenario(chunks=[1])
        b = scenario(source=a)
        c = scenario(source=b)

        touchees = {x.id for x in reponses_obsoletes(scenario.db, scenario.doc_id, {1})}

        assert touchees == {a.id, b.id, c.id}

    def test_ignore_les_cycles(self, scenario):
        a = scenario(chunks=[1])
        b = scenario(source=a)
        a.reponse_source_id = b.id
        scenario.db.commit()

        touchees = {x.id for x in reponses_obsoletes(scenario.db, scenario.doc_id, {1})}

        assert touchees == {a.id, b.id}

    def test_ne_marque_que_les_validees(self, scenario):
        """Seules les VALIDÉE sont réutilisables par `_trouver_reponse_reutilisable`."""
        scenario(chunks=[1], statut="EN_ATTENTE")
        scenario(chunks=[1], statut="REJETÉE")
        validee = scenario(chunks=[1])

        touchees = reponses_obsoletes(scenario.db, scenario.doc_id, {1})

        assert [x.id for x in touchees] == [validee.id]

    def test_ignore_les_deja_obsoletes(self, scenario):
        scenario(chunks=[1], obsolete=True)

        assert reponses_obsoletes(scenario.db, scenario.doc_id, {1}) == []


@pytest.mark.integration
class TestMarquerObsoletes:
    def test_marque_et_horodate(self, scenario, _qdrant_muet):
        r = scenario(chunks=[1], canonique=True)

        marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=2, indices={1})

        scenario.db.refresh(r)
        assert r.obsolete is True
        assert r.obsolete_raison == RAISON_MAJ
        assert r.obsolete_doc_id == scenario.doc_id
        assert r.obsolete_version == 2
        assert r.obsolete_at is not None

    def test_point_qdrant_supprime_pour_chaque_obsolete(self, scenario, _qdrant_muet):
        source = scenario(chunks=[1])
        copie = scenario(source=source)

        marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=2, indices={1})

        assert set(_qdrant_muet) == {str(source.id), str(copie.id)}

    def test_nb_validations_conserve(self, scenario, _qdrant_muet):
        """Restaurer doit rendre la réponse à son état exact : ses validations
        acquises ne sont pas remises en cause par un changement de document."""
        r = scenario(chunks=[1])
        r.nb_validations = 5
        scenario.db.commit()

        marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=2, indices={1})

        scenario.db.refresh(r)
        assert r.nb_validations == 5

    def test_marquage_idempotent(self, scenario, _qdrant_muet):
        scenario(chunks=[1])

        premier = marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=2, indices={1})
        second = marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=3, indices={1})

        assert len(premier) == 1
        assert second == []


# ──────────────────────────────────────────────────────────────────────────────
# Effet sur le pipeline de questions
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestReutilisationBloquee:
    """Ceinture de sécurité de `_trouver_reponse_reutilisable`.

    Le point Qdrant supprimé est la garantie principale ; ce filtre couvre la
    fenêtre avant sa disparition effective de l'index, et les jobs de mise à jour
    partiellement échoués.
    """

    @staticmethod
    def _chunks(reponse):
        from app.workers.question import SEUIL_COSINUS

        return [{"reponse_id": str(reponse.id), "score_cosinus": SEUIL_COSINUS + 0.1}]

    def test_reponse_validee_est_reutilisee(self, scenario):
        from app.workers.question import _trouver_reponse_reutilisable

        r = scenario(chunks=[1], canonique=True)

        trouvee, score = _trouver_reponse_reutilisable(scenario.db, self._chunks(r))

        assert trouvee is not None
        assert trouvee.id == r.id
        assert score is not None

    def test_reponse_obsolete_jamais_reutilisee(self, scenario, _qdrant_muet):
        from app.workers.question import _trouver_reponse_reutilisable

        r = scenario(chunks=[1], canonique=True)
        marquer_obsoletes(scenario.db, scenario.doc_id, RAISON_MAJ, version=2, indices={1})

        assert _trouver_reponse_reutilisable(scenario.db, self._chunks(r)) == (None, None)
