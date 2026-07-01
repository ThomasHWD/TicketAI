"""
Script de calibration du seuil cosinus.
Lance avec : PYTHONPATH=. python scripts/calibrate_threshold.py
"""
import json
import sys

sys.path.insert(0, '.')

from app.services.search import search_hybrid

with open("scripts/dataset_calibration.json") as f:
    dataset = json.load(f)

print(f"\n{'='*65}")
print("CALIBRATION DU SEUIL COSINUS — BGE-M3 réel")
print(f"{'='*65}\n")

scores_pertinents = []
scores_hors_sujet = []

for item in dataset:
    question = item["question"]
    domaine = item["domaine"]
    pertinent = item["pertinent"]

    chunks = search_hybrid(question, domaine, top_k=5)
    top_cosinus = chunks[0]["score_cosinus"] if chunks else 0.0

    label = "✅ PERTINENT  " if pertinent else "❌ HORS SUJET"

    print(f"{label} | score={top_cosinus:.4f} | {question[:55]}")

    if pertinent:
        scores_pertinents.append(top_cosinus)
    else:
        scores_hors_sujet.append(top_cosinus)

print(f"\n{'='*65}")
print(f"Score cosinus moyen — pertinents  : {sum(scores_pertinents)/len(scores_pertinents):.4f}")
print(f"Score cosinus moyen — hors sujet  : {sum(scores_hors_sujet)/len(scores_hors_sujet):.4f}")
print(f"Score cosinus min   — pertinents  : {min(scores_pertinents):.4f}")
print(f"Score cosinus max   — hors sujet  : {max(scores_hors_sujet):.4f}")
print(f"\n{'='*65}")

# Le seuil idéal se situe entre max(hors_sujet) et min(pertinents)
seuil_recommande = (min(scores_pertinents) + max(scores_hors_sujet)) / 2
print(f"SEUIL RECOMMANDÉ : {seuil_recommande:.4f}")
print("  (moyenne entre min pertinent et max hors sujet)")
print(f"{'='*65}\n")
