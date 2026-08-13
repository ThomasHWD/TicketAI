"""Le filtre de suppression de la mise à jour, exercé contre un **vrai** Qdrant.

`test_document_update.py` n'assertait que la *structure* du `Filter` : « il y a
bien un `must_not` et pas un `Range` ». C'est une paraphrase du code, pas une
preuve — si l'hypothèse sous-jacente est fausse, l'assertion structurelle reste
verte et la production indexe le document en double sans que rien ne le signale.

L'hypothèse en question est précise et non triviale :

    un `must_not=[version == N]` exclut les points dont le payload **ne porte pas
    du tout** la clé `version`.

C'est exactement l'inverse d'un `Range(lt=N)`, qui ne matche pas une clé absente
et laisserait donc survivre tous les chunks des documents backfillés. Seul un
Qdrant réel peut trancher, d'où ce module.

Chaque test travaille sur un `doc_id` tiré au hasard et nettoie ses points : la
collection `ticketai` est partagée avec le reste de la suite.
"""

import uuid

import pytest
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.document_update import capturer_chunks, filtre_anciens
from qdrant_client.models import FilterSelector, PointStruct, SparseVector

pytestmark = pytest.mark.integration

VERSION_CIBLE = 3


def _vecteur():
    """Vecteur minimal accepté par la collection (dense 1024 + sparse nommés)."""
    return {
        "dense": [0.01] * 1024,
        "sparse": SparseVector(indices=[1], values=[1.0]),
    }


def _point(payload: dict) -> PointStruct:
    return PointStruct(id=str(uuid.uuid4()), vector=_vecteur(), payload=payload)


def _ids_presents(ids: list[str]) -> set[str]:
    """Sous-ensemble des ids encore présents dans la collection."""
    trouves = client.retrieve(collection_name=COLLECTION_NAME, ids=ids, with_payload=False)
    return {str(p.id) for p in trouves}


@pytest.fixture
def doc_id():
    """`doc_id` isolé, dont tous les points sont purgés en sortie de test."""
    identifiant = f"test-maj-{uuid.uuid4()}"
    yield identifiant
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=filtre_anciens(identifiant, version_cible=-1)  # -1 n'existe pas → tout
        ),
    )


def _semer(points: list[PointStruct]) -> list[str]:
    client.upsert(collection_name=COLLECTION_NAME, points=points, wait=True)
    return [str(p.id) for p in points]


class TestSuppressionDesAnciens:
    """Ce que `client.delete(filtre_anciens(...))` efface réellement."""

    def test_supprime_les_points_sans_cle_version(self, doc_id):
        """Le piège des documents backfillés : payload **sans** clé `version`.

        C'est le test qui justifie tout ce module. Avec un `Range(lt=cible)` à la
        place du `must_not`, ce point survivrait et le document se retrouverait
        indexé en deux exemplaires — l'ancienne et la nouvelle version répondant
        toutes les deux, avec des contenus contradictoires.
        """
        [backfille] = _semer([_point({"doc_id": doc_id, "chunk_index": 0, "contenu": "v1"})])

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=filtre_anciens(doc_id, VERSION_CIBLE)),
            wait=True,
        )

        assert _ids_presents([backfille]) == set()

    def test_supprime_les_versions_anterieures(self, doc_id):
        ids = _semer([_point({"doc_id": doc_id, "version": v, "chunk_index": 0, "contenu": f"v{v}"}) for v in (1, 2)])

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=filtre_anciens(doc_id, VERSION_CIBLE)),
            wait=True,
        )

        assert _ids_presents(ids) == set()

    def test_conserve_la_version_en_cours_d_ecriture(self, doc_id):
        """Les points fraîchement upsertés ne doivent pas être emportés par le delete
        qui les suit — c'est toute la raison d'être du `must_not`."""
        [nouveau] = _semer([_point({"doc_id": doc_id, "version": VERSION_CIBLE, "chunk_index": 0, "contenu": "v3"})])

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=filtre_anciens(doc_id, VERSION_CIBLE)),
            wait=True,
        )

        assert _ids_presents([nouveau]) == {nouveau}

    def test_epargne_les_autres_documents(self, doc_id):
        autre = f"test-maj-{uuid.uuid4()}"
        [voisin] = _semer([_point({"doc_id": autre, "version": 1, "chunk_index": 0})])
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=FilterSelector(filter=filtre_anciens(doc_id, VERSION_CIBLE)),
                wait=True,
            )
            assert _ids_presents([voisin]) == {voisin}
        finally:
            client.delete(collection_name=COLLECTION_NAME, points_selector=[voisin], wait=True)

    def test_epargne_les_points_de_feedback(self, doc_id):
        """Les réponses canoniques vivent dans la même collection et n'ont **aucune**
        clé `doc_id`. Sans le `must=[doc_id]`, le delete les emporterait toutes."""
        [reponse] = _semer([_point({"reponse_id": str(uuid.uuid4()), "ticket_id": str(uuid.uuid4()), "domaine": "RH"})])
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=FilterSelector(filter=filtre_anciens(doc_id, VERSION_CIBLE)),
                wait=True,
            )
            assert _ids_presents([reponse]) == {reponse}
        finally:
            client.delete(collection_name=COLLECTION_NAME, points_selector=[reponse], wait=True)


class TestCapturerChunks:
    """La capture doit voir exactement ce que la suppression va effacer."""

    def test_capture_le_texte_de_la_version_sortante(self, doc_id):
        _semer(
            [
                _point({"doc_id": doc_id, "version": 2, "chunk_index": 0, "contenu": "Alpha"}),
                _point({"doc_id": doc_id, "chunk_index": 1, "contenu": "Beta"}),  # backfillé
                _point({"doc_id": doc_id, "version": VERSION_CIBLE, "chunk_index": 9, "contenu": "Neuf"}),
            ]
        )

        assert capturer_chunks(doc_id, VERSION_CIBLE) == {0: "Alpha", 1: "Beta"}

    def test_pagine_au_dela_de_la_limite_de_scroll(self, doc_id):
        """`capturer_chunks` scrolle par lots de 256. Un document réel dépasse
        couramment ce seuil ; s'arrêter au premier lot rendrait la détection
        aveugle sur tout ce qui suit — donc silencieusement incomplète."""
        total = 300
        _semer(
            [_point({"doc_id": doc_id, "version": 2, "chunk_index": i, "contenu": f"chunk {i}"}) for i in range(total)]
        )

        anciens = capturer_chunks(doc_id, VERSION_CIBLE)

        assert len(anciens) == total
        assert anciens[0] == "chunk 0"
        assert anciens[total - 1] == f"chunk {total - 1}"
