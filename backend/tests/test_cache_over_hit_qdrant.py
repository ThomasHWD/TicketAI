"""Le cache de bout en bout : vrai Qdrant, vrai Postgres, vraie décision de branche.

`test_cache_over_hit.py` prouve où se prend la décision (l'argument que le worker
passe à `servir_reutilisation`). Ce module prouve qu'elle **survit à toute la
pile** : indexation réelle par `feedback_job`, recherche réelle dans Qdrant,
décision réelle du pipeline. Les deux sont nécessaires — le premier localise, le
second constate.

Le garde (`app/services/garde_cache.py`) y est mocké et pilotable : ses juges
appellent Albert, et il est désormais la **seule** condition d'ouverture de la
branche CANONIQUE. Ce qu'on vérifie ici, c'est que son verdict gouverne bien la
branche de bout en bout — pas la qualité de ce verdict, qui se mesure par
`scripts/eval_accord_rag_cache.py` contre le vrai Albert.

**Isolation par `domaine` aléatoire.** Chaque test tire un
`TEST-OVERHIT-<uuid>` et l'utilise comme domaine du ticket. `search_hybrid`
applique un `Filter(must=[FieldCondition(key="domaine", ...)])` aux deux requêtes
(`search.py:53-54`), donc la collection partagée est invisible depuis le test, et
le test invisible depuis le reste de la suite. Bénéfice moins évident mais décisif :
la cardinalité filtrée tombe très en dessous du `full_scan_threshold` de Qdrant,
qui bascule alors en recherche **exacte** — aucun aléa de rappel HNSW, donc aucun
test instable.

**Ce qui n'est pas mocké** : Qdrant et Postgres. **Ce qui l'est** : Albert
(embeddings, rerank, LLM), remplacé par des vecteurs à cosinus exact. Un cosinus
choisi est le seul moyen de tester une frontière de seuil ; un vrai embedding
donnerait un nombre qu'on ne contrôle pas, et le test ne prouverait plus rien de
précis. La mesure sur de vrais embeddings est le travail de
`scripts/eval_cache_over_hit.py`, qui est un instrument, pas un test.
"""

import struct
import uuid

import pytest
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services import question_pipeline as qp
from app.services.qdrant import COLLECTION_NAME, client, init_collection
from app.workers.feedback import feedback_job
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

from .helpers_cosinus import COSINUS_CANONIQUE, VECTEUR_REQUETE, embeddings_factices, vecteur_a_cosinus
from .helpers_reponses import seed_ticket_reponse

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def collection_qdrant():
    """Assure la collection, sans dépendre d'un autre module de test.

    `test_search.py` a bien une fixture `autouse` qui crée la collection, mais elle
    est déclarée *dans ce module* : elle ne se déclenche que pour ses propres tests.
    Or ce fichier passe avant lui dans l'ordre alphabétique, et la CI démarre un
    conteneur Qdrant vide. Sans cette fixture, le test échouerait en CI et
    passerait en local — le pire des deux mondes.

    `init_collection` est idempotente ; le mock `autouse` de `conftest.py` ne
    rebinde que `app.main.init_collection`, pas la fonction réelle importée ici.
    """
    init_collection()


@pytest.fixture
def domaine():
    """Domaine privé, purgé de Qdrant en sortie — y compris si le test échoue."""
    nom = f"TEST-OVERHIT-{uuid.uuid4()}"
    yield nom
    client.delete(
        collection_name=COLLECTION_NAME,
        wait=True,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=nom))])
        ),
    )


@pytest.fixture(autouse=True)
def _albert_neutralise(monkeypatch):
    """Coupe les trois appels Albert, chacun à son point de liaison propre.

    Les modules importent `embed_texts` par `from ... import`, donc chaque module
    en détient sa **propre** référence : patcher `app.services.embedding.embed_texts`
    ne toucherait ni `search` ni `feedback`. Oublier le côté indexation est l'erreur
    la plus coûteuse — le test partirait appeler la vraie API Albert en silence.

    `rerank` et `generate` doivent l'être aussi : pour vérifier qu'une question
    *part bien au RAG*, il faut atteindre la branche RAG (`question.py:109-124`),
    qui appelle le reranker et le LLM.
    """
    import app.services.search as search_module
    import app.workers.feedback as feedback_module
    import app.workers.question as question_module

    monkeypatch.setattr(
        search_module, "embed_texts", lambda textes, is_query=False: embeddings_factices(VECTEUR_REQUETE)
    )
    monkeypatch.setattr(
        question_module, "rerank", lambda q, chunks, top_k=5: [{**c, "rerank_score": 1.0} for c in chunks[:top_k]]
    )
    monkeypatch.setattr(
        question_module, "generate", lambda q, chunks, historique=None: ("Réponse produite par le RAG.", False)
    )
    monkeypatch.setattr(qp, "broadcast_sync", lambda *a, **k: None)
    return feedback_module


@pytest.fixture(autouse=True)
def garde(monkeypatch):
    """Le garde du cache, neutralisé et pilotable — il approuve par défaut.

    Ses deux juges appellent Albert : non mocké, ce module partirait sur le réseau
    à chaque question. Et comme le garde est désormais la **seule** condition
    d'ouverture de la branche CANONIQUE, le laisser non déterministe rendrait
    instables tous les tests de branche de ce fichier.

    La qualité des verdicts ne se mesure pas ici : elle demande le vrai Albert et
    se fait par `scripts/eval_accord_rag_cache.py`. Ce qu'on vérifie ici, c'est que
    le verdict — quel qu'il soit — gouverne bien la branche à travers toute la pile.

    Renvoie une fabrique : `garde(False)` fait refuser les juges.
    """
    import app.workers.question as question_module
    from app.services.garde_cache import Verdict

    def _regler(autorise=True):
        verdict = Verdict(
            autorise,
            "SUFFISANTE_ETAYEE" if autorise else "NON_ETAYEE",
            "verdict de test",
        )
        monkeypatch.setattr(question_module, "autoriser_service_canonique", lambda *a, **k: verdict)
        return verdict

    _regler(True)
    return _regler


def indexer(feedback_module, monkeypatch, reponse, cosinus):
    """Indexe une réponse validée par le **vrai** chemin de `feedback_job`.

    On passe par la tâche plutôt que par un `client.upsert` à la main, parce que
    c'est précisément le contrat qu'on veut vérifier : l'identifiant déterministe
    `uuid5(NAMESPACE_DNS, reponse.id)`, les clés de payload, et la dérivation du
    domaine depuis le ticket. Un upsert manuel réécrirait ce contrat dans le test
    et ne pourrait donc pas en détecter la régression — or `feedback_job` est le
    seul maillon qui rend le cache possible.

    `.apply()` contourne l'`apply_async` neutralisé par la fixture `autouse` de
    `conftest.py` : c'est bien la tâche réelle qui s'exécute, en synchrone.
    """
    monkeypatch.setattr(
        feedback_module, "embed_texts", lambda textes, is_query=False: embeddings_factices(vecteur_a_cosinus(cosinus))
    )
    feedback_job.apply(args=[str(reponse.id)], throw=True)


def poser_question(question, domaine, ticket_id=None):
    """Exécute `question_job` en synchrone et renvoie son résultat."""
    from app.workers.question import question_job

    kwargs = {"ticket_id": ticket_id} if ticket_id else {}
    return question_job.apply(args=[question, domaine, None], kwargs=kwargs, throw=True).get()


@pytest.fixture
def source_canonique(db_session, domaine, _albert_neutralise, monkeypatch):
    """Une réponse validée, canonique, indexée — le contenu du « cache ».

    Renvoie une fabrique : le cosinus est choisi par le test, puisque c'est la
    variable expliquée.
    """

    def _fabriquer(cosinus):
        ticket, reponse = seed_ticket_reponse(
            db_session,
            statut="VALIDÉE",
            ticket_statut="VALIDÉ",
            canonique=True,
            nb_validations=3,
            domaine=domaine,
            question="Quel est le montant de l'indemnité de télétravail ?",
            contenu="OmniCorp verse une indemnité forfaitaire mensuelle de 15 €.",
        )
        indexer(_albert_neutralise, monkeypatch, reponse, cosinus)
        return ticket, reponse

    return _fabriquer


# ══════════════════════════════════════════════════════════════════════════════
# Les trois branches, à travers toute la pile
# ══════════════════════════════════════════════════════════════════════════════


def test_un_verdict_favorable_sert_la_reponse_canonique_sans_revue(db_session, domaine, source_canonique):
    """Cas nominal du cache : question quasi identique, réponse servie directement."""
    ticket_source, source = source_canonique(COSINUS_CANONIQUE)

    resultat = poser_question("Quel est le montant de l'indemnité de télétravail ?", domaine)

    assert resultat["branche"] == "CANONIQUE"
    assert resultat["reponse_source_id"] == str(source.id)

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie.statut == "VALIDÉE"
    assert copie.source == "CANONIQUE"

    ticket = db_session.query(Ticket).filter(Ticket.id == uuid.UUID(resultat["ticket_id"])).first()
    assert ticket.canonique is True

    db_session.refresh(ticket_source)
    assert ticket_source.occurence == 1

    copie_relue = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie_relue.garde_verdict == "SUFFISANTE_ETAYEE"


def test_un_verdict_defavorable_renvoie_au_rag_et_non_en_suggestion(db_session, domaine, source_canonique, garde):
    """Un refus rend la main au RAG — c'est la décision de conception centrale.

    Le garde vient de constater que cette réponse en cache ne traite pas correctement
    cette question. La dégrader en SUGGESTION placerait sous les yeux du validateur
    une réponse connue pour être inadaptée, à la place d'une réponse fraîche et
    ciblée. C'est aussi la sémantique exacte des scripts de mesure (« SERT » vs
    « rag ») : toute autre lecture invaliderait le 8/8 mesuré.
    """
    garde(False)
    source_canonique(COSINUS_CANONIQUE)

    resultat = poser_question("Quel est le montant de l'indemnité de télétravail ?", domaine)

    assert resultat["branche"] == "RAG"
    assert resultat["reponse"] == "Réponse produite par le RAG."

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie.statut == "EN_ATTENTE"
    assert copie.reponse_source_id is None

    # La réponse repart en revue humaine — mais le refus qui l'a provoquée est
    # écrit, à travers un vrai Postgres. Sans lui, un blocage à tort produirait
    # une réponse RAG en tout point ordinaire : c'est la moitié de l'audit qu'on
    # ne peut pas reconstituer après coup. `source` reste le discriminant du
    # service sans relecture, pas la présence d'un verdict.
    assert copie.source == "LLM"
    assert copie.garde_verdict == "NON_ETAYEE"
    assert copie.garde_justification


def test_une_reponse_validee_non_canonique_passe_en_suggestion(db_session, domaine, _albert_neutralise, monkeypatch):
    """La branche SUGGESTION est inchangée : plancher 0.85, aucun juge.

    Elle passe par un validateur humain ; le risque que le garde couvre — servir sans
    relecture — n'y existe pas, et deux appels LLM y seraient payés pour rien.
    """
    _, source = seed_ticket_reponse(
        db_session,
        statut="VALIDÉE",
        ticket_statut="VALIDÉ",
        canonique=False,
        nb_validations=1,
        domaine=domaine,
        question="Quel est le montant de l'indemnité de télétravail ?",
        contenu="OmniCorp verse une indemnité forfaitaire mensuelle de 15 €.",
    )
    indexer(_albert_neutralise, monkeypatch, source, 0.87)

    resultat = poser_question("Combien vaut la prime de télétravail ?", domaine)

    assert resultat["branche"] == "SUGGESTION"

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie.statut == "EN_ATTENTE"
    assert copie.source == "SUGGESTION"
    assert copie.reponse_source_id == source.id
    assert copie.garde_verdict is None, "garde_verdict doit rester réservé aux services sans relecture"


def test_sous_le_plancher_de_candidature_la_question_part_au_rag(db_session, domaine, source_canonique):
    """Le cache s'efface avant même le garde : aucun candidat ne se qualifie.

    0.65 est sous le plancher canonique (0.70), donc aucun juge n'est interrogé —
    le plancher borne le coût, il ne porte plus la sûreté.
    """
    source_canonique(0.65)

    resultat = poser_question("Quelles sont les règles de sécurité du poste de travail ?", domaine)

    assert resultat["branche"] == "RAG"
    assert resultat["reponse"] == "Réponse produite par le RAG."

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie.statut == "EN_ATTENTE"
    assert copie.reponse_source_id is None


def test_une_reformulation_legitime_a_0_78_redevient_candidate(db_session, domaine, source_canonique):
    """Ce que l'ancien plancher de 0.85 rendait impossible.

    Les trois reformulations légitimes du jeu adversarial scorent 0.7116 / 0.7510 /
    0.7822 : sous 0.85, elles n'étaient jamais candidates, le garde ne les voyait
    **jamais**, et elles partaient au RAG attendre un validateur. C'est précisément
    l'intérêt du cache qu'elles perdaient.
    """
    _, source = source_canonique(0.78)

    resultat = poser_question("Combien touche-t-on pour le télétravail ?", domaine)

    assert resultat["branche"] == "CANONIQUE"
    assert resultat["reponse_source_id"] == str(source.id)


# ══════════════════════════════════════════════════════════════════════════════
# Les précisions : servies si et seulement si les juges approuvent
# ══════════════════════════════════════════════════════════════════════════════


def test_une_precision_refusee_par_le_garde_n_est_pas_servie_sans_revue(db_session, domaine, source_canonique, garde):
    """Le défaut historique, constaté de bout en bout puis corrigé.

    `workers/question.py` passait `autoriser_canonique=True` en dur, y compris sur un
    suivi : une précision dont le cosinus dépassait 0.90 ressortait CANONIQUE/VALIDÉE
    avec la réponse à la question GÉNÉRIQUE, sans qu'aucun validateur ne l'ait lue.

    Le lien entre la précision et la réponse cachée n'est qu'une similarité
    vectorielle entre deux questions. Elle ne prouve rien sur le cas particulier
    ajouté — cf. `dataset_precision.json`, où la variante « e-mails qui **ne sont
    pas** marqués Personnel » appelle la réponse exactement inverse de la générique.
    """
    garde(False)
    source_canonique(COSINUS_CANONIQUE)
    ticket_fil, _ = seed_ticket_reponse(
        db_session,
        statut="VALIDÉE",
        domaine=domaine,
        question="Quel est le montant de l'indemnité de télétravail ?",
    )

    resultat = poser_question(
        "Et pour un alternant en contrat d'apprentissage ?", domaine, ticket_id=str(ticket_fil.id)
    )

    assert resultat["branche"] == "RAG"


def test_une_precision_approuvee_par_le_garde_est_servie_sans_revue(db_session, domaine, source_canonique):
    """L'objectif du correctif, et sa contrepartie assumée.

    Une précision légitime — une reformulation, une demande de détail que la réponse
    validée couvre déjà — n'a plus à attendre un validateur. Sans cela, le cache
    perdrait tout intérêt dès qu'un fil compte plus d'un tour.
    """
    source_canonique(COSINUS_CANONIQUE)
    ticket_fil, _ = seed_ticket_reponse(
        db_session,
        statut="VALIDÉE",
        domaine=domaine,
        question="Quel est le montant de l'indemnité de télétravail ?",
    )

    resultat = poser_question("Et c'est bien un montant mensuel ?", domaine, ticket_id=str(ticket_fil.id))

    assert resultat["branche"] == "CANONIQUE"

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()
    assert copie.statut == "VALIDÉE"
    assert copie.garde_verdict == "SUFFISANTE_ETAYEE"


# ══════════════════════════════════════════════════════════════════════════════
# Auto-test du helper : le cosinus survit-il à l'aller-retour Qdrant ?
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("cosinus", [0.80, 0.849, 0.85, 0.899, COSINUS_CANONIQUE, 0.95])
def test_qdrant_restitue_le_cosinus_construit(domaine, cosinus):
    """Sans cette preuve, tous les tests de frontière reposent sur une hypothèse.

    Qdrant normalise les vecteurs COSINE à l'écriture comme à la requête ; les
    nôtres étant déjà unitaires, le score renvoyé doit être le produit scalaire,
    dégradé seulement par le stockage float32. La tolérance de 1e-5 laisse ~250×
    de marge sur l'erreur observée (~4e-8) tout en restant assez serrée pour
    attraper une vraie erreur de construction.
    """
    from qdrant_client.models import PointStruct, SparseVector

    client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector={"dense": vecteur_a_cosinus(cosinus), "sparse": SparseVector(indices=[1], values=[1.0])},
                payload={"domaine": domaine, "contenu": "x", "source": "x"},
            )
        ],
    )

    points = client.query_points(
        collection_name=COLLECTION_NAME,
        query=VECTEUR_REQUETE,
        using="dense",
        query_filter=Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))]),
        limit=1,
    ).points

    assert abs(points[0].score - cosinus) < 1e-5


def _f32(x: float) -> float:
    """La valeur que Qdrant stocke réellement — il conserve les vecteurs en float32."""
    return struct.unpack("f", struct.pack("f", x))[0]


def test_le_regime_d_arrondi_f32_differe_entre_les_deux_planchers():
    """Les deux planchers ne se comportent PAS pareil à la frontière exacte, et le
    savoir est la condition pour lire le test suivant.

    ``float32`` n'arrondit pas dans le même sens selon la constante :

    * ``float32(0.70) == 0.699999988...`` — **sous** le seuil ;
    * ``float32(0.85) == 0.850000023...`` — **au-dessus** du seuil.

    Conséquence : à 0.70 pile, la candidature dépend du transport Qdrant (cf. test
    suivant) ; à 0.85 pile, elle n'en dépend pas — les deux transports franchissent.
    Un déplacement de l'un ou l'autre plancher peut donc changer de régime en
    silence. Si ce test rougit, c'est qu'une constante a bougé : relire les
    frontières avant de conclure quoi que ce soit sur les branches.
    """
    assert _f32(qp.SEUIL_CANDIDAT_CANONIQUE) < qp.SEUIL_CANDIDAT_CANONIQUE
    assert _f32(qp.SEUIL_SUGGESTION) > qp.SEUIL_SUGGESTION


def test_au_plancher_canonique_pile_la_candidature_depend_du_transport_qdrant(domaine):
    """À la frontière exacte, être candidat ou non dépend du **transport** Qdrant.

    Le seuil éprouvé ici est `SEUIL_CANDIDAT_CANONIQUE` (0.70), plancher des réponses
    canoniques — celui des deux dont l'arrondi f32 tombe *sous* la constante, donc le
    seul où le phénomène existe (cf. test précédent).

    Qdrant stocke les vecteurs en float32, et `float32(0.70) == 0.699999988...` —
    donc `>= 0.70` devrait être faux. On s'attendrait donc à ce qu'un point construit
    pour 0.70 pile revienne sous le seuil. **C'est faux en REST**, et la raison tient
    au format de fil, pas au calcul :

    * **REST** — Qdrant (Rust/`serde_json`) sérialise le f32 en la plus courte
      décimale qui round-trip *en f32*, soit ``"0.7"``. Python la relit en float64
      et obtient ``0.70`` **exactement**. Le seuil est franchi.
    * **gRPC** — le f32 voyage en binaire et Python l'élargit tel quel, soit
      ``0.699999988...``. Le seuil n'est **pas** franchi.

    La conséquence dépasse ce test. `app/services/qdrant.py` construit
    ``QdrantClient(host=..., port=...)``, donc REST. Ajouter ``prefer_grpc=True``
    ressemble à un réglage de performance sans effet fonctionnel : ce n'en est pas
    un. Il déplace la frontière de candidature d'un ULP et fait sortir du cache des
    réponses aujourd'hui servies — sans qu'aucun seuil n'ait bougé.

    Le test épingle le transport réellement en service. S'il rougit, c'est que
    quelqu'un est passé en gRPC. `COSINUS_CANONIQUE` (0.9000001) reste, lui, au-dessus
    des deux planchers dans les **deux** transports : c'est pourquoi les tests de
    branche s'appuient dessus plutôt que sur une frontière.
    """
    from qdrant_client.models import PointStruct, SparseVector

    client.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": vecteur_a_cosinus(qp.SEUIL_CANDIDAT_CANONIQUE),
                    "sparse": SparseVector(indices=[1], values=[1.0]),
                },
                payload={"domaine": domaine, "contenu": "x", "source": "x"},
            )
        ],
    )

    points = client.query_points(
        collection_name=COLLECTION_NAME,
        query=VECTEUR_REQUETE,
        using="dense",
        query_filter=Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))]),
        limit=1,
    ).points

    # Le transport en service est REST — la décimale courte restaure 0.70 exact.
    assert points[0].score == qp.SEUIL_CANDIDAT_CANONIQUE
    assert points[0].score >= qp.SEUIL_CANDIDAT_CANONIQUE

    # Le f32 sous-jacent, lui, est bien sous le seuil : c'est ce que verrait gRPC.
    assert _f32(qp.SEUIL_CANDIDAT_CANONIQUE) < qp.SEUIL_CANDIDAT_CANONIQUE
