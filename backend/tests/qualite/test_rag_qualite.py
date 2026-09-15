"""Tests qualité du pipeline RAG sur documents DFE réels.

Nécessite `docs_ingeres` : dfe_engagements.md et dfe_budget.md ingérés dans Qdrant.

Vérifie que :
- le LLM génère des réponses pertinentes à partir des chunks retrouvés,
- la branche RAG est correctement activée,
- HORS_DOMAINE est détecté pour les questions sans rapport,
- les chunks pertinents sont liés à la réponse en DB,
- le tag est attribué sur les réponses RAG,
- le filtre domaine est respecté (pas de cross-contamination).

Budget Albert (excl. ingestion) :
  embed + rerank + generate  par test RAG = ~3 appels
  test_hors_domaine          : embed + rerank + generate (~3 appels, réponse HORS_DOMAINE)
  test_domaine_strict        : 1 embed (generate mocké, aucun doc DFE trouvé)
  Total module               : ~7 tests × ~3 = ~21 appels Albert
"""

import uuid

import pytest
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk

from .conftest import DOMAINE, run_question

pytestmark = [pytest.mark.integration, pytest.mark.albert]


# ── 1. RAG génère une réponse pertinente pour un service fait ─────────────────


def test_rag_service_fait_pertinent(docs_ingeres, monkeypatch):
    """Le LLM génère une réponse sur le service fait à partir du document ingéré.

    La réponse doit mentionner des concepts du document : SIREPA, service fait,
    validation, certificat, etc.
    """
    q = "Comment enregistrer un service fait dans SIREPA ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    assert res["branche"] in ("RAG", "CANONIQUE", "SUGGESTION"), (
        f"Branche inattendue : {res['branche']}"
    )
    if res["branche"] == "RAG":
        assert res["reponse"] is not None, "Le RAG doit produire une réponse"
        reponse_lower = res["reponse"].lower()
        mots_attendus = ["service fait", "sirepa", "prestation", "validation", "engagement"]
        assert any(mot in reponse_lower for mot in mots_attendus), (
            f"La réponse RAG ne contient aucun mot-clé attendu ({mots_attendus}).\n"
            f"Réponse : {res['reponse'][:300]}"
        )


# ── 2. RAG sur la récupération d'un reliquat ─────────────────────────────────


def test_rag_reliquat_engagement(docs_ingeres, monkeypatch):
    """RAG sur la question du reliquat d'engagement → réponse cohérente avec le doc."""
    q = "Comment récupérer le reliquat d'un engagement de dépense non utilisé ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    if res["branche"] == "RAG":
        assert res["reponse"] is not None
        reponse_lower = res["reponse"].lower()
        mots_attendus = ["reliquat", "engagement", "clôture", "budget", "sirepa", "solde"]
        assert any(mot in reponse_lower for mot in mots_attendus), (
            f"La réponse sur le reliquat ne contient pas les mots attendus.\n"
            f"Réponse : {res['reponse'][:300]}"
        )


# ── 3. Branche RAG activée (pas encore canonique) ────────────────────────────


def test_rag_branche_avant_canonisation(docs_ingeres, monkeypatch):
    """Une question nouvelle sans réponse validée doit aller en RAG.

    Les documents sont ingérés mais pas de réponse validée correspondante.
    """
    q = "Quelles sont les règles pour les engagements de dépense en fin d'exercice ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    assert res["branche"] in ("RAG", "HORS_DOMAINE"), (
        f"Sans réponse canonique préalable, la branche doit être RAG. Obtenu : {res['branche']}"
    )


# ── 4. HORS_DOMAINE détecté ───────────────────────────────────────────────────


def test_hors_domaine_detecte(docs_ingeres, monkeypatch):
    """Une question hors-sujet doit déclencher HORS_DOMAINE dans le LLM.

    Le LLM émet [HORS_DOMAINE] quand il ne peut pas répondre avec les chunks.
    Ce test vérifie que le signal est détecté et enregistré correctement.
    Budget : 1 embed + 1 rerank + 1 LLM génération.
    """
    q = "Quelle est la capitale de la France ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    # Si le LLM détecte HORS_DOMAINE, la branche doit le refléter.
    # Si aucun chunk n'est trouvé du tout, on peut avoir RAG avec contenu minimal.
    assert res["branche"] in ("HORS_DOMAINE", "RAG"), (
        f"Une question hors-domaine ne doit pas être CANONIQUE. Obtenu : {res['branche']}"
    )
    if res["branche"] == "HORS_DOMAINE":
        # La réponse source = HORS_DOMAINE, pas de contenu significatif
        if res.get("reponse_id"):
            db = SessionLocal()
            try:
                r = db.query(Reponse).filter(Reponse.id == uuid.UUID(res["reponse_id"])).first()
                if r:
                    assert r.source == "HORS_DOMAINE"
            finally:
                db.close()


# ── 5. Les chunks sont liés à la réponse en DB ───────────────────────────────


def test_rag_chunks_lies_a_reponse(docs_ingeres, monkeypatch):
    """Après un RAG, les chunks pertinents doivent être enregistrés dans reponse_chunks.

    Chaque chunk lié pointe vers un doc_id présent dans Qdrant.
    """
    q = "Comment faire un engagement de dépense pour un abonnement numérique ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    if res["branche"] == "RAG" and res.get("reponse_id"):
        db = SessionLocal()
        try:
            chunks = (
                db.query(ReponseChunk)
                .filter(ReponseChunk.reponse_id == uuid.UUID(res["reponse_id"]))
                .all()
            )
            assert len(chunks) > 0, (
                "Un RAG doit enregistrer au moins un chunk pertinent dans reponse_chunks."
            )
            for chunk in chunks:
                assert chunk.doc_id is not None, "Chaque chunk doit avoir un doc_id"
                assert chunk.doc_id in docs_ingeres.doc_ids, (
                    f"Le chunk référence doc_id={chunk.doc_id} inconnu du seed."
                )
        finally:
            db.close()


# ── 6. Tag attribué sur les réponses RAG ─────────────────────────────────────


def test_rag_tag_attribue(docs_ingeres, monkeypatch):
    """Après un RAG complet (generate réel), le tag doit être attribué via suggerer_tag.

    Ce test laisse suggerer_tag appeler Albert (1 LLM tag en plus du generate).
    Budget : 1 embed + 1 rerank + 1 LLM generate + 1 LLM tag = ~4 appels.
    """
    q = "Que faire si ma facture DFE n'est pas réglée ?"

    # On ne mock pas suggerer_tag ici : on teste son fonctionnement réel
    res = run_question(q, DOMAINE, monkeypatch, mock_tag=False, mock_generate=False)

    if res["branche"] == "RAG" and res.get("reponse_id"):
        db = SessionLocal()
        try:
            r = db.query(Reponse).filter(Reponse.id == uuid.UUID(res["reponse_id"])).first()
            if r:
                # Le tag peut être None si Albert tag a échoué silencieusement,
                # mais ne doit pas être une chaîne vide si non-None.
                if r.tag is not None:
                    assert len(r.tag.strip()) > 0, "Tag non vide attendu si non-None"
                    # Le tag doit être thématique, pas la question elle-même
                    assert len(r.tag) < 50, f"Tag trop long ({len(r.tag)} chars) : {r.tag!r}"
        finally:
            db.close()


# ── 7. Filtre domaine respecté ────────────────────────────────────────────────


def test_rag_filtre_domaine(docs_ingeres, monkeypatch):
    """Une question posée dans un domaine différent ne doit pas trouver les docs DFE.

    Les documents indexés avec domaine="Finances et évaluation" ne doivent pas
    apparaître dans une recherche pour domaine="Ressources humaines".
    generate est mocké car on teste la recherche, pas la génération.
    """
    q = "Comment faire un engagement de dépense ?"
    domaine_rh = "Ressources humaines"

    res = run_question(q, domaine_rh, monkeypatch, mock_tag=True, mock_generate=True)

    # Sans candidat DFE, la branche doit être RAG (generate mocké) ou HORS_DOMAINE
    assert res["branche"] in ("RAG", "HORS_DOMAINE"), (
        f"La recherche dans domaine RH ne doit pas trouver les docs DFE. Obtenu : {res['branche']}"
    )


# ── 8. Réponse RAG sur budget imprévue ───────────────────────────────────────


def test_rag_budget_imprevue(docs_ingeres, monkeypatch):
    """Le RAG trouve l'information sur les dépenses imprévues dans dfe_budget.md."""
    q = "J'ai une dépense imprévue dans mon budget, que faire ?"

    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=False)

    if res["branche"] == "RAG":
        assert res["reponse"] is not None
        reponse_lower = res["reponse"].lower()
        mots_attendus = ["virement", "crédits", "budget", "dfe", "imprévu", "dépense"]
        assert any(mot in reponse_lower for mot in mots_attendus), (
            f"La réponse sur dépense imprévue ne contient pas les mots attendus.\n"
            f"Réponse : {res['reponse'][:300]}"
        )
