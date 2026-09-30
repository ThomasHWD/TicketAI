"""Tests de la confrontation d'un document neuf aux réponses déjà servies.

Ce chemin existe parce que l'entonnoir de ré-vérification ne se déclenche que sur
un **remplacement de version** : il lui faut un diff AVANT/APRÈS. Ingérer un
document pour la première fois ne touchait donc aucune réponse existante — y
compris une canonique que ce document contredit désormais, et qui continuait
d'être servie sans revue humaine.

Une seule propriété est vraiment porteuse ici, et c'est elle que la majorité des
tests ci-dessous épingle :

    **Aucune réponse ne devient jamais obsolète sur ce chemin.**

Elle est structurelle — ``decider`` ne retire que sur ``CONTREDITE`` *et*
``citante``, et rien ne peut citer un document qui n'existait pas — mais
structurel ne veut pas dire durable : il suffirait qu'un jour ``_candidates``
construise ses ``Candidate`` autrement pour qu'une canonique à douze validations
soit détruite sur un cosinus à 0,35. Les tests la vérifient donc au niveau du
*worker*, pas de ``decider`` (déjà couvert par ``test_reverification.py``).

Second invariant, hérité de la ré-vérification et vérifié dans chaque test
d'intégration : ``ANALYSE_EN_COURS`` est transitoire et le job a l'obligation de
le résoudre. Un état transitoire qui survit est un bug silencieux.

Albert et Qdrant sont toujours bouchonnés ; Postgres est réel.
"""

import shutil
import uuid
from types import SimpleNamespace

import pytest
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.confrontation import (
    MAX_CHUNKS_PAR_REPONSE,
    cibles_confrontation,
    resume_ajout,
)
from app.services.obsolescence import RAISON_ANALYSE, poser_a_relire
from app.workers.confrontation import confrontation_job
from app.workers.reverification import restees_en_analyse

DOMAINE = "RH"

# Épinglées plutôt qu'importées : ces chaînes partent en base (`String(30)`) et
# sont lues par le front pour choisir un badge. Un renommage sans migration
# laisserait des lignes orphelines et un onglet muet — le test doit casser
# dessus, pas le suivre.
RAISON_CONTREDITE_PROB = "CONTREDITE_PROBABLE"
RAISON_NOUVEAU_DOC = "NOUVEAU_DOC"
RAISON_INDISPONIBLE = "ANALYSE_INDISPONIBLE"

GENERALE = "Le teletravail est autorise du lundi au mercredi."
EXCEPTION = "Les alternants ne beneficient pas du teletravail."


# ──────────────────────────────────────────────────────────────────────────────
# Étage 1 — la détection, qui ne coûte aucun appel Albert
# ──────────────────────────────────────────────────────────────────────────────


def _point(reponse_id, score):
    return SimpleNamespace(score=score, payload={"reponse_id": reponse_id})


def _qdrant(par_chunk: list[list], monkeypatch):
    """Bouchonne `query_points` : une entrée de `par_chunk` par chunk ingéré."""
    import app.services.confrontation as module

    appels = iter(par_chunk)
    monkeypatch.setattr(
        module,
        "client",
        SimpleNamespace(query_points=lambda **k: SimpleNamespace(points=next(appels))),
    )


def _embeddings(n: int) -> list[dict]:
    return [{"dense": [0.1] * 8, "sparse": {"indices": [1], "values": [1.0]}} for _ in range(n)]


class TestDetection:
    def test_conserve_l_association_chunk_reponse(self, monkeypatch):
        """Rendre un simple ensemble de réponses obligerait à reranker le document
        entier une fois par réponse. L'association permet de ne juger que les
        quelques passages qui ont réellement apparié cette réponse."""
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        _qdrant([[_point(a, 0.8)], [_point(b, 0.7)], [_point(a, 0.6), _point(b, 0.5)]], monkeypatch)

        assert cibles_confrontation(_embeddings(3), DOMAINE) == {a: [0, 2], b: [1, 2]}

    def test_ecarte_les_points_sous_le_seuil(self, monkeypatch):
        loin = str(uuid.uuid4())
        _qdrant([[_point(loin, 0.34)]], monkeypatch)

        assert cibles_confrontation(_embeddings(1), DOMAINE) == {}

    def test_plafonne_les_chunks_par_reponse(self, monkeypatch):
        """Ces indices deviennent un argument de tâche Celery : ils transitent par
        le broker, et le reranker n'en montrera de toute façon que trois."""
        r = str(uuid.uuid4())
        n = MAX_CHUNKS_PAR_REPONSE + 4
        _qdrant([[_point(r, 0.9)] for _ in range(n)], monkeypatch)

        assert len(cibles_confrontation(_embeddings(n), DOMAINE)[r]) == MAX_CHUNKS_PAR_REPONSE

    def test_panne_qdrant_ne_fait_pas_echouer_l_ingestion(self, monkeypatch):
        """La confrontation est un effet de bord de l'ingestion : elle n'a pas le
        droit de faire échouer un document par ailleurs correctement indexé."""
        import app.services.confrontation as module

        def _casse(**k):
            raise RuntimeError("503 Service Unavailable")

        monkeypatch.setattr(module, "client", SimpleNamespace(query_points=_casse))

        assert cibles_confrontation(_embeddings(2), DOMAINE) == {}


class TestResumeAjout:
    def test_extraits_peuples_mais_unites_vides(self):
        """`unites` vide est délibéré : y recopier le document entier coûterait
        jusqu'à 256 Ko de JSON par ingestion pour un contenu que personne ne lit —
        la confrontation juge sur les chunks relus dans Qdrant, et `unites_figees`
        n'est appelé que par la ré-vérification, qui ne voit jamais une v1."""
        resume = resume_ajout(f"{GENERALE}\n\n{EXCEPTION}")

        assert resume["nb_ajoutes"] == 2
        assert resume["nb_retires"] == 0
        assert resume["extraits_ajoutes"], "l'onglet « À relire » doit montrer ce que le document dit"
        assert resume["unites"] == []


# ──────────────────────────────────────────────────────────────────────────────
# L'invariant, vérifié sur le worker
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def lot(db_session, monkeypatch):
    """Une canonique bâtie sur le document A, et un document B qui vient d'arriver.

    Reproduit l'état exact dans lequel `ingestion_job` laisse la base : lignes de
    document écrites, réponses appariées flaguées `ANALYSE_EN_COURS` dans le même
    commit. La canonique cite A et **ne cite pas B** — c'est le fait, pas la
    convention, qui plafonne le verdict.
    """
    import app.services.confrontation as confront
    import app.workers.confrontation as worker
    import app.workers.reverification as reverif

    monkeypatch.setattr(worker, "broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(reverif, "broadcast_sync", lambda *a, **k: None)

    doc_a, doc_b = str(uuid.uuid4()), str(uuid.uuid4())
    # `textes_chunks` relit le nouveau document, `contexte_source` relit l'ancien :
    # un seul bouchon de scroll sert les deux, chacun filtrant sur son doc_id.
    textes = {doc_a: {0: GENERALE}, doc_b: {0: EXCEPTION, 1: EXCEPTION}}

    def _scroll(*, scroll_filter, **k):
        conditions = {c.key: c.match for c in scroll_filter.must}
        vus = textes.get(getattr(conditions["doc_id"], "value", None), {})
        voulus = getattr(conditions["chunk_index"], "any", [])
        return ([SimpleNamespace(payload={"chunk_index": i, "contenu": vus[i]}) for i in voulus if i in vus], None)

    monkeypatch.setattr(confront, "client", SimpleNamespace(scroll=_scroll))

    def _monter(*, nb_reponses=1, nb_validations=3):
        db_session.add(
            Document(doc_id=doc_b, filename="alternants.md", domaine=DOMAINE, version=1, statut="ACTIF", nb_chunks=2)
        )
        db_session.flush()

        reponses = []
        for i in range(nb_reponses):
            ticket = Ticket(question=f"Le teletravail est-il autorise {i} ?", domaine=DOMAINE, statut_job="TERMINÉ")
            db_session.add(ticket)
            db_session.flush()
            r = Reponse(
                ticket_id=ticket.id,
                contenu=GENERALE,
                source="CANONIQUE",
                statut="VALIDÉE",
                canonique=True,
                nb_validations=nb_validations,
            )
            db_session.add(r)
            db_session.flush()
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_a, chunk_index=0))
            reponses.append(r)

        poser_a_relire(reponses, RAISON_ANALYSE, doc_b, 1)
        db_session.commit()
        return reponses

    _monter.db = db_session
    _monter.doc_id = doc_b
    _monter.cibles = lambda reponses: {str(r.id): [0] for r in reponses}
    return _monter


def _repondre(monkeypatch, verdict: str, justification: str = "Les alternants sont exclus du dispositif."):
    import app.services.reverification_scoring as scoring

    monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
    monkeypatch.setattr(
        scoring,
        "chat",
        lambda messages, **k: '{"verdict": "%s", "justification": "%s"}' % (verdict, justification),
    )


def _lancer(lot, reponses):
    return confrontation_job(
        doc_id=lot.doc_id, version=1, domaine=DOMAINE, cibles=lot.cibles(reponses)
    )


@pytest.mark.integration
class TestInvariant:
    def test_contredite_signale_mais_ne_retire_jamais(self, lot, monkeypatch, mock_side_effects):
        """**Le test central.** Le juge dit « contredite » et la réponse reste
        servie : elle n'a été rapprochée du nouveau document que par un cosinus
        entre un paragraphe et une question. Et une réponse *incomplète* ne se
        détruit pas, elle s'amende — « Modifier » dans l'onglet « À relire »
        conserve ses validations, un retrait en exigerait trois de plus."""
        [r] = lot(nb_validations=12)
        _repondre(monkeypatch, "CONTREDITE")

        bilan = _lancer(lot, [r])

        lot.db.expire_all()
        assert bilan["nb_a_relire"] == 1
        assert bilan["nb_contredites"] == 0
        assert r.obsolete is False, "jamais d'obsolescence automatique sur un document neuf"
        assert r.a_relire is True
        assert r.a_relire_raison == RAISON_CONTREDITE_PROB
        assert r.analyse_justification == "Les alternants sont exclus du dispositif."
        mock_side_effects.delete_point.assert_not_called()
        assert restees_en_analyse(lot.db, lot.doc_id, 1) == []

    def test_incertain_dit_qu_il_s_agit_d_un_document_neuf(self, lot, monkeypatch):
        """`DOC_MODIFIÉ` enverrait le relecteur chercher un diff qui n'existe pas :
        ce document n'a pas de version précédente à comparer."""
        [r] = lot()
        _repondre(monkeypatch, "INCERTAIN", "Impossible de trancher.")

        _lancer(lot, [r])

        lot.db.expire_all()
        assert r.a_relire_raison == RAISON_NOUVEAU_DOC
        assert r.obsolete is False
        assert restees_en_analyse(lot.db, lot.doc_id, 1) == []

    def test_intacte_leve_le_drapeau_pose_a_l_ingestion(self, lot, monkeypatch):
        """Le cas majoritaire : la plupart des documents ingérés ne concernent
        aucune réponse servie. Sans cette levée, chaque ingestion laisserait
        derrière elle un onglet « À relire » qui ne se vide jamais."""
        [r] = lot()
        _repondre(monkeypatch, "INTACTE", "Sans rapport avec cette reponse.")

        bilan = _lancer(lot, [r])

        lot.db.expire_all()
        assert bilan["nb_intactes"] == 1
        assert (r.obsolete, r.a_relire) == (False, False)
        assert restees_en_analyse(lot.db, lot.doc_id, 1) == []

    def test_panne_albert_laisse_la_reponse_servie(self, lot, monkeypatch, mock_side_effects):
        import app.services.reverification_scoring as scoring

        [r] = lot()
        monkeypatch.setattr(scoring, "rerank", lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}])
        monkeypatch.setattr(scoring, "chat", _casse)

        bilan = _lancer(lot, [r])

        lot.db.expire_all()
        assert bilan["nb_indisponibles"] == 1
        assert r.obsolete is False
        assert r.a_relire_raison == RAISON_INDISPONIBLE
        mock_side_effects.delete_point.assert_not_called()
        assert restees_en_analyse(lot.db, lot.doc_id, 1) == []

    def test_version_depassee_abandonne_sans_juger(self, lot, monkeypatch):
        """Le document a été remplacé entre l'ingestion et le jugement : `cibles`
        désigne des chunks qui ne sont plus indexés, et la mise à jour porte son
        propre job sur son propre périmètre."""
        import app.services.reverification_scoring as scoring

        [r] = lot()
        monkeypatch.setattr(scoring, "chat", _interdit)
        lot.db.query(Document).filter(Document.doc_id == lot.doc_id).one().version = 2
        lot.db.commit()

        bilan = _lancer(lot, [r])

        lot.db.expire_all()
        assert bilan["statut"] == "DEPASSE"
        assert r.obsolete is False
        assert r.a_relire_raison == RAISON_INDISPONIBLE
        assert restees_en_analyse(lot.db, lot.doc_id, 1) == []


def _interdit(*a, **k):
    raise AssertionError("aucun appel à Albert ne devait avoir lieu")


def _casse(*a, **k):
    raise RuntimeError("503 Service Unavailable")


# ──────────────────────────────────────────────────────────────────────────────
# Le raccordement à l'ingestion
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def ingerer(db_session, monkeypatch, tmp_path):
    """Exécute `ingestion_job` avec Albert, Qdrant et le stockage bouchonnés.

    Tout ce qui précède l'étape 6 est hors sujet ici : ce qu'on vérifie est le
    raccordement entre la détection et le job de confrontation.
    """
    import app.workers.confrontation as worker
    import app.workers.ingestion as ingestion

    monkeypatch.setattr(ingestion, "extract_text", lambda p: [EXCEPTION])
    monkeypatch.setattr(ingestion, "chunk_text", lambda pages: [EXCEPTION])
    monkeypatch.setattr(ingestion, "embed_texts", lambda c, is_query: _embeddings(len(c)))
    monkeypatch.setattr(ingestion, "client", SimpleNamespace(upsert=lambda **k: None))
    monkeypatch.setattr(ingestion, "broadcast_sync", lambda *a, **k: None)
    stockage = tmp_path / "stockage"
    stockage.mkdir()
    monkeypatch.setattr(
        ingestion,
        "store_file",
        lambda tmp, doc_id, filename, version=1: str(shutil.copy2(tmp, stockage / filename)),
    )

    enfiles: list[dict] = []
    monkeypatch.setattr(worker.confrontation_job, "apply_async", lambda **k: enfiles.append(k))

    def _lancer(cibles: dict):
        monkeypatch.setattr(ingestion, "cibles_confrontation", lambda embeddings, domaine: cibles)
        fichier = tmp_path / "alternants.md"
        fichier.write_text(EXCEPTION, encoding="utf-8")
        return ingestion.ingestion_job(
            file_path=str(fichier),
            filename="alternants.md",
            domaine=DOMAINE,
            doc_id=str(uuid.uuid4()),
        )

    _lancer.db = db_session
    _lancer.enfiles = enfiles
    return _lancer


def _canonique(db, *, question="Le teletravail est-il autorise ?") -> Reponse:
    ticket = Ticket(question=question, domaine=DOMAINE, statut_job="TERMINÉ")
    db.add(ticket)
    db.flush()
    r = Reponse(
        ticket_id=ticket.id, contenu=GENERALE, source="CANONIQUE", statut="VALIDÉE", canonique=True, nb_validations=3
    )
    db.add(r)
    db.commit()
    return r


@pytest.mark.integration
class TestRaccordementIngestion:
    def test_aucune_cible_n_enfile_rien_et_ne_flague_personne(self, ingerer):
        """Le cas de loin le plus fréquent. Enfiler quand même ferait tourner un
        job qui n'a rien à résoudre, et dont le `rabattre` final balaierait un lot
        vide ; flaguer quand même remplirait l'onglet « À relire » de bruit."""
        r = _canonique(ingerer.db)

        resultat = ingerer({})

        ingerer.db.expire_all()
        assert resultat["nb_a_analyser"] == 0
        assert ingerer.enfiles == []
        assert (r.a_relire, r.obsolete) == (False, False)

    def test_cible_flaguee_dans_le_meme_commit_que_le_document(self, ingerer):
        """La fenêtre de course : entre la publication du document et le verdict il
        s'écoule de trente secondes à quelques minutes, pendant lesquelles la
        réponse continue d'être servie. Elle l'est — mais plus jamais sans que
        l'interface le dise."""
        r = _canonique(ingerer.db)

        resultat = ingerer({str(r.id): [0]})

        ingerer.db.expire_all()
        assert resultat["nb_a_analyser"] == 1
        assert r.a_relire is True
        assert r.a_relire_raison == RAISON_ANALYSE
        assert r.obsolete is False, "l'ingestion elle-même ne retire jamais rien"

        [appel] = ingerer.enfiles
        assert appel["queue"] == "queue_questions"
        assert appel["kwargs"]["cibles"] == {str(r.id): [0]}
        assert appel["kwargs"]["doc_id"] == resultat["doc_id"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "contenu_corrige, rerank_score, obsolete, a_relire",
    [
        pytest.param(None, 0.9, True, False, id="pas-d-info-contredite-retiree"),
        pytest.param(None, 0.01, False, False, id="pas-d-info-document-sans-rapport-intacte"),
        pytest.param("Le préavis est d'un mois.", 0.9, False, True, id="corrigee-a-la-main-jamais-retiree"),
    ],
)
def test_hors_domaine_passe_par_la_pertinence_et_le_juge(
    lot, monkeypatch, mock_side_effects, contenu_corrige, rerank_score, obsolete, a_relire
):
    """Tout document ajouté retirait toutes les canoniques HORS_DOMAINE du domaine, avant
    le reranker (observé : une note mutuelle a retiré « préavis de démission »). Seule une
    « pas d'information » contredite est retirée ; une réponse écrite à la main suit la
    règle commune."""
    import app.services.reverification_scoring as scoring

    [r] = lot()
    r.source, r.contenu, r.contenu_corrige = "HORS_DOMAINE", "Aucune information sur ce sujet.", contenu_corrige
    r.statut = "CORRIGÉE" if contenu_corrige else "VALIDÉE"
    lot.db.commit()
    monkeypatch.setattr(scoring, "rerank",
                        lambda q, docs, top_k: [{**d, "rerank_score": rerank_score} for d in docs[:top_k]])
    monkeypatch.setattr(scoring, "chat",
                        lambda messages, **k: '{"verdict": "CONTREDITE", "justification": "Le document en traite."}')

    confrontation_job(doc_id=lot.doc_id, version=1, domaine=DOMAINE, cibles={str(r.id): [0, 1]})

    lot.db.expire_all()
    assert (r.obsolete, r.a_relire) == (obsolete, a_relire)
