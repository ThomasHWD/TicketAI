from app.workers.question import SEUIL_COSINUS


def test_seuil_valeur():
    assert 0.40 <= SEUIL_COSINUS <= 0.95, f"Seuil {SEUIL_COSINUS} hors de la plage attendue"


def test_seuil_type():
    assert isinstance(SEUIL_COSINUS, float)
