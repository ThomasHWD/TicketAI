"""Profil de la recherche FAQ : dans quel rang tombe chaque requête ?

Usage : PYTHONPATH=. python scripts/diag_faq_seuil.py

Un appel d'embedding Albert par requête listée ci-dessous.
"""

import os

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.faq import rechercher_faq  # noqa: E402

REQUETES = [
    "hauteur fruit",
    "combien mesure une pomme ?",
    "quelle est la capitale de la Mongolie ?",
]

print(f"seuil pertinence = {settings.faq_seuil_pertinence} · seuil incertain = {settings.faq_seuil_incertain}\n")

db = SessionLocal()
try:
    for q in REQUETES:
        rangs = rechercher_faq(db, q, settings.faq_max_resultats)
        if rangs["resultats"]:
            rang = "RÉPONSE"
            items = rangs["resultats"]
        elif rangs["incertains"]:
            rang = "piste incertaine"
            items = rangs["incertains"]
        else:
            rang = "rien"
            items = []
        print(f"« {q} »  →  {rang}")
        for item in items:
            print(f"      {item['question']}")
        print()
finally:
    db.close()
