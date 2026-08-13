import uuid
from unittest.mock import MagicMock

import pytest

REPONSE_ID = str(uuid.uuid4())
VALIDATOR_ID = "00000000-0000-0000-0000-000000000001"


def make_reponse(statut="EN_ATTENTE"):
    r = MagicMock()
    r.id = uuid.UUID(REPONSE_ID)
    r.statut = statut
    r.ticket_id = uuid.uuid4()
    r.contenu = "Réponse test"
    r.contenu_corrige = None
    r.validator_id = None
    r.validated_at = None
    return r


def make_ticket():
    t = MagicMock()
    t.user_id = uuid.uuid4()  # différent du validator
    t.statut_ticket = "RÉPONDU"
    return t


def test_verifier_etat_initial_bloque_etat_final():
    from app.api.v1.reponses import verifier_etat_initial
    from fastapi import HTTPException

    # MODIFICATION : "VALIDÉE" -> "CANONIQUE"
    reponse = make_reponse(statut="CANONIQUE")
    with pytest.raises(HTTPException) as exc:
        verifier_etat_initial(reponse)
    assert exc.value.status_code == 409


def test_verifier_etat_initial_autorise_en_attente():
    from app.api.v1.reponses import verifier_etat_initial

    reponse = make_reponse(statut="EN_ATTENTE")
    verifier_etat_initial(reponse)  # ne doit pas lever


def test_verifier_auto_validation_bloque_si_meme_user():
    from app.api.v1.reponses import verifier_auto_validation
    from fastapi import HTTPException

    validator_id = uuid.uuid4()
    reponse = make_reponse()
    ticket = MagicMock()
    ticket.user_id = validator_id
    with pytest.raises(HTTPException) as exc:
        verifier_auto_validation(reponse, validator_id, ticket)
    assert exc.value.status_code == 403


def test_verifier_auto_validation_autorise_si_user_different():
    from app.api.v1.reponses import verifier_auto_validation

    reponse = make_reponse()
    ticket = make_ticket()
    verifier_auto_validation(reponse, uuid.uuid4(), ticket)  # ne doit pas lever


def _db_sans_ticket():
    """Session dont la recherche de ticket ne trouve rien."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def test_check_reponse_write_sans_ticket_renvoie_409():
    """Sans ticket, il n'y a aucun domaine à confronter : personne ne passe.

    L'admin non plus — lui accorder ce cas rouvrirait par la petite porte
    l'exception que `check_domain_write` refuse partout ailleurs.
    """
    from app.api.v1.reponses import check_reponse_write
    from fastapi import HTTPException

    admin = MagicMock()
    admin.role = "ADMIN"

    with pytest.raises(HTTPException) as exc:
        check_reponse_write(_db_sans_ticket(), make_reponse(), admin)

    assert exc.value.status_code == 409


def test_etats_finaux_complets():
    from app.api.v1.reponses import ETATS_FINAUX

    # MODIFICATION : "VALIDÉE" -> "CANONIQUE"
    assert "CANONIQUE" in ETATS_FINAUX
    assert "REJETÉE" in ETATS_FINAUX
    assert "CORRIGÉE" in ETATS_FINAUX
    assert "EN_ATTENTE" not in ETATS_FINAUX
