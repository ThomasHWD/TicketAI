"""L'encodeur BM25.

Les risques de cet encodeur ne sont pas dans la formule — elle est standard et
sa moitié difficile (l'IDF) est déléguée à Qdrant. Ils sont dans la tokenisation
du français et dans la stabilité des indices. Ce sont donc les deux seules choses
que ces tests verrouillent.
"""

import subprocess
import sys

import pytest
from app.services.bm25 import encoder, index_du_token, tokeniser


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        # Élision : un découpage naïf produirait un token « l », bruit fréquent.
        ("l'abonnement", ["abon"]),
        ("jusqu'à quand", []),
        # Diacritiques repliés : une faute d'accent ne doit pas manquer le document.
        ("télétravail", ["teletravail"]),
        ("teletravail", ["teletravail"]),
        # Mots-outils écartés.
        ("les et des pour", []),
        # Ponctuation ignorée ; le nombre, lui, est une valeur et reste indexé.
        ("hauteur ?! 42", ["hauteur", "42"]),
    ],
    ids=["élision", "élision tout-outil", "accents", "sans accents", "mots-outils", "ponctuation"],
)
def test_tokenisation(texte, attendu):
    assert tokeniser(texte) == attendu


def test_meme_radical_pour_singulier_et_pluriel():
    """La radicalisation est ce qui fait qu'« abonnements » retrouve « abonnement »."""
    assert tokeniser("abonnement") == tokeniser("abonnements")


def test_recouvrement_sur_le_cas_qui_motive_le_chantier():
    """« hauteur fruit » partage le mot exact « hauteur » avec la question indexée.

    C'est précisément ce que la recherche dense ne voyait pas (0,6706).
    """
    requete = encoder("hauteur fruit", est_requete=True)
    document = encoder("Combien fait une pomme en hauteur ?")
    assert set(requete["indices"]) & set(document["indices"])


def test_indices_stables_entre_processus():
    """`hash()` est randomisé par PYTHONHASHSEED ; `xxhash` ne l'est pas.

    Sans cette propriété, un index écrit par le worker d'ingestion serait
    introuvable depuis l'API : une recherche lexicale muette, sans la moindre
    erreur pour le signaler.
    """
    ici = index_du_token("hauteur")
    ailleurs = subprocess.run(
        [sys.executable, "-c", "from app.services.bm25 import index_du_token; print(index_du_token('hauteur'))"],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONHASHSEED": "random", "PATH": "/usr/bin:/bin", "PYTHONPATH": "."},
    )
    assert int(ailleurs.stdout.strip()) == ici


def test_requete_sans_ponderation_tf():
    """Côté requête les termes valent 1 : l'IDF de Qdrant fait le reste."""
    assert encoder("congés congés congés", est_requete=True)["values"] == [1.0]


def test_document_sature_la_frequence():
    """Un mot répété ne vaut pas n fois un mot vu une fois."""
    une_fois = encoder("congés")["values"][0]
    dix_fois = encoder(" ".join(["congés"] * 10))["values"][0]
    assert dix_fois > une_fois
    assert dix_fois < 10 * une_fois


def test_texte_sans_token_signifiant():
    assert encoder("les et des") == {"indices": [], "values": []}


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("35 heures", ["35", "heur"]),  # une valeur : elle discrimine
        ("50 %", ["50"]),
        ("31 mai", ["31", "mai"]),
        ("chambre forte 713", ["chambr", "fort", "713"]),
    ],
)
def test_les_nombres_sont_indexes(texte, attendu):
    """Un nombre est une valeur, et c'est souvent le terme le plus discriminant.

    Mesuré le 11/09/2026 : « 35 heures par semaine » notait 3,83/terme contre un
    bruit à 3,35 — 1,14× de séparation. En indexant « 35 », 5,43 contre 2,18, soit
    2,5×. C'est précisément ce que BM25 est là pour faire.
    """
    assert tokeniser(texte) == attendu


@pytest.mark.parametrize("texte", ["L3262-1", "0,25 €", "article 7"])
def test_les_chiffres_isoles_restent_ecartes(texte):
    """Un chiffre seul est du bruit, et arrive surtout comme débris de découpage.

    Tout indexer régressait sur « article L3262-1 » : le `1` extrait de la
    référence hissait un passage sans aucun rapport au rang 2. D'où
    `LONGUEUR_MIN_NOMBRE`. Ce test rougit si quelqu'un l'abaisse à 1.
    """
    assert not any(t.isdigit() and len(t) == 1 for t in tokeniser(texte))


def test_la_reference_d_article_perd_son_suffixe():
    """`L3262-1` et `L3262-5` donnent le même token — limite connue.

    Latente sur ce corpus : deux articles de même préfixe n'y coexistent pas.
    Elle mordrait sur un corpus juridique dense.
    """
    assert tokeniser("L3262-1") == tokeniser("L3262-5") == ["l3262"]
