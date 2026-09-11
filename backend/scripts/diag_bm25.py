"""Décompose le score hybride : cosinus, BM25 brut, saturation, bonus effectif.

Usage : PYTHONPATH=. python scripts/diag_bm25.py

Un appel d'embedding Albert par requête. Sert à calibrer `bonus_lexical` et
`k_saturation_bm25` : sans cette décomposition, on règle à l'aveugle.
"""

import os

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.config import settings  # noqa: E402
from app.services.bm25 import tokeniser  # noqa: E402
from app.services.search import rechercher_points_reponses  # noqa: E402

REQUETES = [
    "hauteur fruit",
    "combien mesure une pomme ?",
    "quelle est la capitale de la Mongolie ?",
]

print(
    f"porte lexicale ≥ {settings.seuil_lexical_par_terme}/terme · seuil cosinus FAQ = {settings.faq_seuil_pertinence}\n"
)

for q in REQUETES:
    print(f"« {q} »   tokens={tokeniser(q)}")
    for c in rechercher_points_reponses(q, top_k=3):
        cos, brut, par_terme = c["score_cosinus"], c["score_sparse"], c["score_lexical"]
        portes = []
        if cos >= settings.faq_seuil_pertinence:
            portes.append("cosinus")
        if settings.seuil_lexical_par_terme > 0 and par_terme >= settings.seuil_lexical_par_terme:
            portes.append("lexical")
        print(
            f"   cos={cos:.4f}  bm25={brut:7.4f}  par terme={par_terme:6.3f}  "
            f"porte: {'+'.join(portes) or '—':14} {str(c['question_indexee'])[:38]}"
        )
    print()
