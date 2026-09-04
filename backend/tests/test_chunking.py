from app.services.text_processing import chunk_text, clean_text


def test_chunk_text_it():
    pages = ["Mot " * 200]
    chunks = chunk_text(pages)
    assert len(chunks) > 0
    assert all(len(c) > 0 for c in chunks)


def test_clean_text():
    texte = "Bonjour\n\n\n\nMonde   test"
    resultat = clean_text(texte)
    assert "\n\n\n" not in resultat
    assert "   " not in resultat
