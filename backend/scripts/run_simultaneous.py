"""
Test de charge légère — 5 questions simultanées
Lance avec : PYTHONPATH=. python scripts/load_test.py
"""

import concurrent.futures
import sys
import time

import httpx

sys.path.insert(0, ".")

BASE_URL = "http://localhost:8000/api/v1"

QUESTIONS = [
    "Quel algorithme mathématique popularisé au milieu des années 80 a permis les avancées en deep learning ?",
    "Qui a proposé le test de Turing et en quoi consiste-t-il ?",
    "Qu'est-ce que le premier hiver de l'IA et quand s'est-il produit ?",
    "Comment AlphaGo a-t-il battu le champion du monde de Go ?",
    "Quelle est la différence entre l'IA symbolique et l'IA connexionniste ?",
]


def soumettre_question(question: str) -> dict:
    response = httpx.post(
        f"{BASE_URL}/tickets", json={"question": question, "domaine": "IT"}, timeout=10
    )
    response.raise_for_status()
    return response.json()


def poller_statut(job_id: str, timeout: int = 120) -> dict:
    debut = time.time()
    while time.time() - debut < timeout:
        response = httpx.get(f"{BASE_URL}/tickets/{job_id}/status", timeout=10)
        data = response.json()
        if data["statut_job"] in ("SUCCESS", "FAILURE"):
            return data
        time.sleep(5)
    return {"statut_job": "TIMEOUT", "job_id": job_id}


print(f"\n{'='*60}")
print("TEST DE CHARGE — 5 questions simultanées")
print(f"{'='*60}\n")

# Soumission simultanée
print("Soumission des 5 questions en parallèle...")
job_ids = []
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(soumettre_question, q) for q in QUESTIONS]
    for f in concurrent.futures.as_completed(futures):
        result = f.result()
        job_ids.append(result["job_id"])
        print(f"  ✓ job_id={result['job_id'][:8]}... soumis")

print(f"\n{len(job_ids)} jobs soumis. Attente des résultats...\n")

# Polling des résultats
resultats = []
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(poller_statut, job_id) for job_id in job_ids]
    for f in concurrent.futures.as_completed(futures):
        result = f.result()
        resultats.append(result)

print(f"{'='*60}")
print("RÉSULTATS")
print(f"{'='*60}")

succes = 0
echecs = 0
timeouts = 0

for r in resultats:
    statut = r["statut_job"]
    if statut == "SUCCESS":
        succes += 1
        reponse = r.get("reponse", "")[:60]
        print(f"  ✅ SUCCESS | {reponse}...")
    elif statut == "FAILURE":
        echecs += 1
        print(f"  ❌ FAILURE | {r.get('erreur', '')[:60]}")
    else:
        timeouts += 1
        print(f"  ⏱  TIMEOUT | job_id={r['job_id'][:8]}...")

print(f"\n{'='*60}")
print(f"Succès  : {succes}/5")
print(f"Échecs  : {echecs}/5")
print(f"Timeouts: {timeouts}/5")
print(f"{'='*60}\n")
