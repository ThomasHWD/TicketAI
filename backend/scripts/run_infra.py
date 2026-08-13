import os

import psycopg2
import redis
import requests
from dotenv import load_dotenv
from qdrant_client import QdrantClient

print("--- TEST INFRA ---")

# --- Chargement du fichier d'environnement "../.env" ---
load_dotenv("../.env")


# --- Test connection LLM ---
try:
    url = f"{os.getenv('LLM_URL')}/chat/completions"
    payload = {
        "model": os.getenv("LLM_MODEL_NAME"),
        "messages": [{"role": "user", "content": "Ping"}],
        "stream": False,
    }

    response = requests.post(url, json=payload, timeout=5)
    if response.status_code == 200:
        print(
            "Connexion LLM : OK : ",
            response.json()["choices"][0]["message"]["content"].strip(),
        )
    else:
        print(f"Erreur connexion LLM : Status code {response.status_code} - {response.text}")

except Exception as e:
    print(f"Erreur connexion LLM : {e}")


# --- Test QDrant ---
try:
    client = QdrantClient(host=os.getenv("QDRANT_HOST"), port=int(os.getenv("QDRANT_PORT")))
    collections_info = client.get_collections()
    print(f"Connexion QDrant : OK : {collections_info}")

except Exception as e:
    print(f"Erreur connexion QDrant : {e}")


# --- Test POSTGRES ---
try:
    connection = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        database=os.getenv("POSTGRES_DB"),
        port=os.getenv("POSTGRES_PORT"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )
    print("Connexion POSTGRES : OK")
    connection.close()

except Exception as e:
    print(f"Erreur connexion POSTGRES : {e}")


# --- Test Valkey ---
try:
    r = redis.Redis(
        host=os.getenv("VALKEY_HOST"),
        port=int(os.getenv("VALKEY_PORT")),
        decode_responses=True,
    )
    if r.ping():
        print("Connexion Valkey : OK")

except Exception as e:
    print(f"Erreur connexion Valkey : {e}")
