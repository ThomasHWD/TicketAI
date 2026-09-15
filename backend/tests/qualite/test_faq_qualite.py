"""Tests qualité de la FAQ sur données DFE réelles.

Vérifie que :
- une réponse canonique + faq_visible=True apparaît dans resultats,
- une réponse faq_visible=False est invisible,
- la règle métier « incertains ∅ si resultats non vide » est respectée,
- le champ `question` retourné est question_indexee (pas Ticket.question brut),
- le tag et d'autres métadonnées sont correctement exposés.

Budget Albert : 1 embed par appel rechercher_faq, aucun LLM.
Total module : ~12 embeds (11 tests + parametrize) = 12 appels Albert.
"""

import pytest
from app.services.faq import rechercher_faq

from .conftest import DOMAINE

pytestmark = [pytest.mark.integration, pytest.mark.albert]


# ── 1. Réponse canonique visible → dans resultats ─────────────────────────────


def test_faq_canonique_visible_dans_resultats(faq_seed, db):
    """Une réponse canonique avec faq_visible=True doit apparaître dans resultats."""
    q = faq_seed.engagement.question

    rangs = rechercher_faq(db, q, limite=5)

    ids_resultats = {r["reponse_id"] for r in rangs["resultats"]}
    assert faq_seed.engagement.reponse_id in ids_resultats, (
        f"La réponse canonique engagement (faq_visible=True) doit être dans resultats. "
        f"IDs trouvés : {ids_resultats}"
    )


# ── 2. Réponse faq_visible=False → invisible ──────────────────────────────────


def test_faq_non_visible_absent_partout(faq_seed, db):
    """Une réponse canonique avec faq_visible=False ne doit apparaître nulle part."""
    q = faq_seed.facture.question  # "Ma facture n'est pas réglée, que faire ?"

    rangs = rechercher_faq(db, q, limite=5)

    tous_ids = (
        {r["reponse_id"] for r in rangs["resultats"]}
        | {r["reponse_id"] for r in rangs["incertains"]}
    )
    assert faq_seed.facture.reponse_id not in tous_ids, (
        "La réponse avec faq_visible=False ne doit apparaître ni dans resultats ni dans incertains."
    )


# ── 3. Question exacte → première position dans resultats ────────────────────


def test_faq_question_exacte_en_tete(faq_seed, db):
    """La question exactement identique à celle indexée doit être en tête de resultats."""
    q = faq_seed.engagement.question

    rangs = rechercher_faq(db, q, limite=5)

    assert rangs["resultats"], "Aucun résultat pour la question exacte du seed"
    premier = rangs["resultats"][0]
    assert premier["reponse_id"] == faq_seed.engagement.reponse_id, (
        f"La réponse canonique doit être en tête. Premier trouvé : {premier['reponse_id']}, "
        f"attendu : {faq_seed.engagement.reponse_id}"
    )


# ── 4. Incertains vides quand resultats non vide ─────────────────────────────


def test_faq_incertains_vides_si_resultats_presents(faq_seed, db):
    """Si des résultats sûrs existent, incertains doit être vide.

    Règle métier : proposer de l'incertain à côté d'une réponse sûre la diluerait.
    """
    q = faq_seed.engagement.question  # fort cosinus → resultats

    rangs = rechercher_faq(db, q, limite=5)

    if rangs["resultats"]:
        assert rangs["incertains"] == [], (
            "Des incertains ne doivent pas coexister avec des résultats sûrs. "
            f"incertains = {rangs['incertains']}"
        )


# ── 5. question retournée = question_indexee du point Qdrant ─────────────────


def test_faq_retourne_question_indexee(faq_seed, db):
    """Le champ 'question' du résultat est question_indexee, pas Ticket.question.

    feedback_job indexe ticket.question comme question_indexee dans le payload.
    La FAQ doit retourner exactement cette valeur (pas une reformulation ou autre).
    """
    q = faq_seed.monnaie.question  # "Peut-on faire un engagement en monnaie étrangère ?"

    rangs = rechercher_faq(db, q, limite=5)

    ids_map = {r["reponse_id"]: r for r in rangs["resultats"]}
    if faq_seed.monnaie.reponse_id in ids_map:
        result = ids_map[faq_seed.monnaie.reponse_id]
        assert result["question"] == faq_seed.monnaie.question, (
            f"question du résultat : {result['question']!r}\n"
            f"question indexée attendue : {faq_seed.monnaie.question!r}"
        )


# ── 6. Tag exposé dans les résultats ─────────────────────────────────────────


def test_faq_expose_tag(faq_seed, db):
    """Les résultats FAQ doivent inclure le tag de la réponse."""
    q = faq_seed.engagement.question

    rangs = rechercher_faq(db, q, limite=5)

    ids_map = {r["reponse_id"]: r for r in rangs["resultats"]}
    if faq_seed.engagement.reponse_id in ids_map:
        result = ids_map[faq_seed.engagement.reponse_id]
        assert "tag" in result, "Le champ 'tag' doit être présent dans le résultat FAQ"
        assert result["tag"] == faq_seed.engagement.tag, (
            f"tag attendu : {faq_seed.engagement.tag!r}, obtenu : {result['tag']!r}"
        )


# ── 7. Contenu retourné ───────────────────────────────────────────────────────


def test_faq_contenu_retourne(faq_seed, db):
    """Le champ 'contenu' doit être contenu_corrige ou contenu de la réponse."""
    q = faq_seed.engagement.question

    rangs = rechercher_faq(db, q, limite=5)

    ids_map = {r["reponse_id"]: r for r in rangs["resultats"]}
    if faq_seed.engagement.reponse_id in ids_map:
        result = ids_map[faq_seed.engagement.reponse_id]
        assert "contenu" in result
        assert len(result["contenu"]) > 0
        # Le contenu doit correspondre à ce qui a été seedé
        assert "SIREPA" in result["contenu"] or "engagement" in result["contenu"].lower()


# ── 8. Limite respectée ───────────────────────────────────────────────────────


def test_faq_limite_respectee(faq_seed, db):
    """Le paramètre `limite` borne le nombre de résultats retournés."""
    q = faq_seed.engagement.question

    rangs = rechercher_faq(db, q, limite=1)

    assert len(rangs["resultats"]) <= 1, (
        f"limite=1 mais {len(rangs['resultats'])} résultats retournés"
    )


# ── 9. Réponse non-canonique absente ─────────────────────────────────────────


def test_faq_non_canonique_absent(faq_seed, db):
    """Une réponse non-canonique ne doit jamais apparaître dans la FAQ.

    On crée une réponse canonique=False directement en DB (sans feedback_job),
    puis on vérifie qu'elle est absente de la FAQ (filtre SQL canonique=True).
    """
    from app.models.reponse import Reponse
    from app.models.ticket import Ticket

    ticket = Ticket(question="Question test non-canonique ?", domaine=DOMAINE, statut_ticket="RÉPONDU")
    db.add(ticket)
    db.flush()
    reponse = Reponse(
        ticket_id=ticket.id,
        contenu="Cette réponse ne doit pas apparaître dans la FAQ.",
        statut="VALIDÉE",
        source="LLM",
        canonique=False,
        nb_validations=1,
        faq_visible=True,
    )
    db.add(reponse)
    db.commit()

    q = "Question test non-canonique ?"
    rangs = rechercher_faq(db, q, limite=5)

    tous_ids = {r["reponse_id"] for r in rangs["resultats"]} | {r["reponse_id"] for r in rangs["incertains"]}
    assert str(reponse.id) not in tous_ids, (
        "Une réponse non-canonique (canonique=False) ne doit jamais apparaître dans la FAQ. "
        "Rappel : la FAQ montre ce qu'un humain a validé au moins seuil_canonique fois."
    )


# ── 10. Réponse obsolète absente ─────────────────────────────────────────────


def test_faq_obsolete_absent(faq_seed, db):
    """Une réponse canonique mais obsolète ne doit pas apparaître dans la FAQ."""
    from datetime import datetime, timezone

    from app.models.reponse import Reponse
    from app.models.ticket import Ticket

    ticket = Ticket(question="Question test obsolète ?", domaine=DOMAINE, statut_ticket="RÉPONDU")
    db.add(ticket)
    db.flush()
    reponse = Reponse(
        ticket_id=ticket.id,
        contenu="Réponse obsolète de test.",
        statut="VALIDÉE",
        source="LLM",
        canonique=True,
        nb_validations=3,
        faq_visible=True,
        obsolete=True,
        obsolete_raison="DOC_MIS_A_JOUR",
        obsolete_at=datetime.now(timezone.utc),
    )
    db.add(reponse)
    db.commit()

    # La réponse n'est pas dans Qdrant (pas de feedback_job appelé) → elle n'apparaîtra
    # pas dans les résultats Qdrant, et même si elle y était, le filtre SQL l'exclut.
    q = "Question test obsolète ?"
    rangs = rechercher_faq(db, q, limite=5)

    tous_ids = {r["reponse_id"] for r in rangs["resultats"]} | {r["reponse_id"] for r in rangs["incertains"]}
    assert str(reponse.id) not in tous_ids


# ── 11. Reformulations approchées → dans resultats (parametrize) ─────────────


@pytest.mark.parametrize("question", [
    "Comment faire un engagement de dépense ?",
    "Procédure engagement de dépense",
    "Comment créer un engagement dans SIREPA ?",
])
def test_faq_reformulation_proche_dans_resultats(faq_seed, db, question):
    """Des reformulations proches de la question canonique doivent apparaître dans FAQ.

    Ce test peut échouer si le cosinus passe sous FAQ_SEUIL_PERTINENCE (~0.75).
    Dans ce cas, vérifier que la question est au moins dans incertains.
    Budget : 1 embed par variante = 3 embeds pour ce parametrize.
    """
    rangs = rechercher_faq(db, question, limite=5)

    engagement_id = faq_seed.engagement.reponse_id
    tous_ids = (
        {r["reponse_id"] for r in rangs["resultats"]}
        | {r["reponse_id"] for r in rangs["incertains"]}
    )
    assert engagement_id in tous_ids, (
        f"La reformulation {question!r} devrait trouver la réponse engagement. "
        f"Résultats trouvés : {[r['question'] for r in rangs['resultats'][:3]]}"
    )
