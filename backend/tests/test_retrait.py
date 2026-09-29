"""Re-examination after a document deletion: only an explicit SOUTENUE puts a withdrawn response back into service.

Origin (29/09/2026): a response cites the five reranked passages of its context, used or not — deleting the télétravail
note withdrew the vélo canonical, which never relied on it.
"""

import uuid

import pytest
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.obsolescence import RAISON_SUPPRESSION, marquer_obsoletes

pytestmark = pytest.mark.integration


@pytest.fixture
def famille(db_session, monkeypatch):
    """A validated response citing the deleted document second (0.2) behind a live one (0.9), its human-validated
    SUGGESTION copy and a pending copy — all withdrawn by the deletion."""
    import app.services.obsolescence as obsolescence

    monkeypatch.setattr(obsolescence, "delete_response_point", lambda _id: None)
    supprime, autre = str(uuid.uuid4()), str(uuid.uuid4())
    for doc_id, statut in ((supprime, "SUPPRIMÉ"), (autre, "ACTIF")):
        db_session.add(Document(doc_id=doc_id, filename=f"{doc_id}.md", domaine="RH", statut=statut))
    db_session.commit()

    def reponse(source=None, statut="VALIDÉE", origine="LLM", cites=(), a_relire=False):
        ticket = Ticket(question="Quel est le forfait vélo ?", domaine="RH", statut_job="TERMINÉ")
        db_session.add(ticket)
        db_session.flush()
        r = Reponse(
            ticket_id=ticket.id,
            contenu="300 € par an.",
            source=origine,
            statut=statut,
            reponse_source_id=source.id if source else None,
            a_relire=a_relire,
        )
        db_session.add(r)
        db_session.flush()
        for doc_id, score in cites:
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, version=1, chunk_index=0, rerank_score=score))
        db_session.commit()
        return r

    def fabriquer(tete_supprimee=False, a_relire=False):
        cites = [(supprime, 0.9), (autre, 0.2)] if tete_supprimee else [(autre, 0.9), (supprime, 0.2)]
        racine = reponse(cites=cites, a_relire=a_relire)
        copie = reponse(source=racine, origine="SUGGESTION")
        brouillon = reponse(source=racine, statut="EN_ATTENTE", origine="SUGGESTION")
        return racine, copie, brouillon

    fabriquer.supprime, fabriquer.autre = supprime, autre
    return fabriquer


def _reexaminer(db_session, monkeypatch, famille, juge, avant_le_job=lambda: None):
    import app.workers.retrait as worker
    from app.services.retrait import candidats_au_reexamen

    examens = [
        {
            "reponse_id": str(r.id),
            "passages_retires": ["Télétravail : 2,88 € par jour."],
            "passages_restants": [{"doc_id": famille.autre, "version": 1, "texte": "Forfait vélo : 300 € par an."}],
        }
        for r in candidats_au_reexamen(db_session, famille.supprime)
    ]
    marquer_obsoletes(db_session, famille.supprime, RAISON_SUPPRESSION, version=1)
    avant_le_job()

    appels_juge, indexations = [], []

    def juger(*args):
        appels_juge.append(args)
        return juge()

    monkeypatch.setattr(worker, "juger_retrait", juger)
    monkeypatch.setattr(worker.feedback_job, "apply_async", lambda args, **_: indexations.append(tuple(args)))
    monkeypatch.setattr(worker, "broadcast_sync", lambda *_a, **_k: None)
    worker.reexamen_retrait_job.run(doc_id=famille.supprime, examens=examens)
    db_session.expire_all()
    return examens, appels_juge, indexations


def _panne():
    raise RuntimeError("Albert 503")


@pytest.mark.parametrize(
    ("juge", "remise"),
    [
        (lambda: ("SOUTENUE", "300 € figure dans le guide."), True),
        (lambda: ("DEPENDANTE", "Le montant ne figure que dans la note supprimée."), False),
        (lambda: ("INCERTAIN", "Impossible de trancher."), False),
        (_panne, False),
    ],
)
def test_seul_un_soutien_explicite_remet_en_service(db_session, monkeypatch, famille, juge, remise):
    racine, copie, brouillon = famille()

    _, appels_juge, indexations = _reexaminer(db_session, monkeypatch, famille, juge)

    assert len(appels_juge) == 1
    etats = {r.id: db_session.get(Reponse, r.id).obsolete for r in (racine, copie, brouillon)}
    if remise:
        assert etats == {racine.id: False, copie.id: False, brouillon.id: True}  # the draft was answered again
        assert sorted(indexations) == sorted([(str(racine.id),), (str(racine.id), str(copie.id))])
    else:
        assert all(etats.values())
        assert indexations == []
        assert db_session.get(Reponse, racine.id).analyse_justification  # the Obsolètes tab tells why


def test_source_principale_supprimee_reste_retiree_sans_appel(db_session, monkeypatch, famille):
    racine, _, _ = famille(tete_supprimee=True)

    _, appels_juge, _ = _reexaminer(db_session, monkeypatch, famille, lambda: ("SOUTENUE", ""))

    assert appels_juge == []
    assert db_session.get(Reponse, racine.id).obsolete is True


def test_une_source_restante_supprimee_entre_temps_ne_soutient_plus_rien(db_session, monkeypatch, famille):
    racine, _, _ = famille()

    def supprimer_l_autre():
        db_session.query(Document).filter(Document.doc_id == famille.autre).update({"statut": "SUPPRIMÉ"})
        db_session.commit()

    _, appels_juge, _ = _reexaminer(db_session, monkeypatch, famille, lambda: ("SOUTENUE", ""), supprimer_l_autre)

    assert appels_juge == []
    assert db_session.get(Reponse, racine.id).obsolete is True


def test_une_famille_deja_signalee_n_est_jamais_reexaminee(db_session, monkeypatch, famille):
    """The withdrawal clears review flags: without this exclusion a SOUTENUE would serve a response another pass had
    sent to human review."""
    racine, _, _ = famille(a_relire=True)

    examens, appels_juge, _ = _reexaminer(db_session, monkeypatch, famille, lambda: ("SOUTENUE", ""))

    assert examens == []
    assert appels_juge == []
    assert db_session.get(Reponse, racine.id).obsolete is True


@pytest.mark.parametrize(
    ("version_actuelle", "statut", "lu"),
    [
        (1, "ACTIF", "cité"),  # cited version still current: the cited passage itself
        (2, "ACTIF", "actuel"),  # updated since — citations are never re-pointed, the response survived its check
        (1, "SUPPRIMÉ", None),  # gone as well: no longer a source
    ],
)
def test_passages_restants_suivent_la_version_en_vigueur(
    db_session, monkeypatch, famille, version_actuelle, statut, lu
):
    import app.services.retrait as retrait

    racine, _, _ = famille()
    db_session.query(Document).filter(Document.doc_id == famille.autre).update(
        {"version": version_actuelle, "statut": statut}
    )
    db_session.commit()
    monkeypatch.setattr(retrait, "textes_chunks", lambda *_: {0: "cité"})
    monkeypatch.setattr(retrait, "passages_actuels", lambda *_: ["actuel"])

    passages = retrait.passages_restants(db_session, racine, famille.supprime)

    assert [p["texte"] for p in passages] == ([lu] if lu else [])
