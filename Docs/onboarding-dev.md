# Onboarding développeur — TicketAI

Guide de mise en route pour un nouveau développeur sur le projet, du clone au premier `pytest` vert.

---

## Prérequis

| Outil | Version minimale | Rôle |
|---|---|---|
| Python | 3.14 | Backend FastAPI + workers Celery |
| Node.js | 20 LTS | Frontend React |
| Docker + Docker Compose | v2 | Infra locale (Postgres, Qdrant, Valkey) |
| Make | — | Raccourcis de commandes |

---

## 1. Cloner le dépôt

```bash
git clone <url-du-repo> TicketAI
cd TicketAI
```

La branche de travail par défaut est `dev`. `main` est la branche de production.

---

## 2. Variables d'environnement

### Racine (optionnel, pour Docker Compose)

```bash
cp .env.example .env
```

Ce fichier passe `POSTGRES_USER`, `POSTGRES_PASSWORD`, etc. à Docker Compose.

### Backend

```bash
cp backend/.env.example backend/.env
```

Valeurs minimales à renseigner pour démarrer :

| Variable | Exemple | Obligatoire |
|---|---|---|
| `POSTGRES_USER` | `ticketai` | oui |
| `POSTGRES_PASSWORD` | `secret` | oui |
| `POSTGRES_DB` | `ticketai_db` | oui |
| `ALBERT_API_KEY` | `<clé API gouvernement>` | oui (LLM/embeddings/reranker) |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` | oui |
| `DOCUMENTS_STORAGE_PATH` | `/tmp/ticketai/documents` | oui |
| `AUTH_MODE` | `db` (local) ou `ldap` (prod) | recommandé : `db` en dev |

En mode `AUTH_MODE=db`, le login s'appuie uniquement sur la base Postgres (pas besoin d'un Active Directory). Mettre `AUTH_MODE=ldap` uniquement si vous avez accès à un serveur LDAP.

### Frontend

```bash
cp frontend/.env.exemple frontend/.env
```

Le fichier contient une seule variable :

```
VITE_API_URL=http://localhost:8000
```

Elle configure le proxy Vite qui redirige `/api/*` vers le backend.

---

## 3. Démarrer la stack de développement

```bash
make dev
```

C'est la seule commande nécessaire. Elle lance en parallèle, avec hot-reload :

| Conteneur | Rôle | Port |
|---|---|---|
| `postgres` | Base relationnelle | `:5432` |
| `qdrant` | Index vectoriel | `:6333` / `:6334` |
| `valkey` | Broker Celery | `:6379` |
| `backend` | API FastAPI (`watchmedo` auto-restart) | `:8000` |
| `worker_ingestion` | Worker Celery — ingestion documents | — |
| `worker_questions` | Worker Celery — pipeline RAG | — |
| `worker_beat` | Celery Beat — tâches planifiées | — |
| `frontend` | Vite dev server (`npm run dev`) | `:5173` |

Les conteneurs applicatifs (backend, workers, frontend) montent le code source en volume : toute modification de fichier est prise en compte sans reconstruire l'image.

> **Premier démarrage** : Docker doit builder les images backend. C'est plus long la première fois (~2 min). Les fois suivantes, seuls les layers modifiés sont reconstruits.

### Initialiser la base au premier démarrage

Une fois la stack `healthy`, initialiser le schéma et les utilisateurs de dev :

```bash
make reset-db
```

Cette commande enchaîne `alembic stamp base`, `alembic upgrade head`, et l'insertion de deux validateurs fictifs (`validateur.a@entreprise.fr`, `validateur.b@entreprise.fr`). À relancer après chaque `make clean`.

### Swagger / Docs API

`http://localhost:8000/docs`

### Arrêter

```bash
make dev-down
```

### Venv local (pour les tests et le linting uniquement)

Docker gère l'exécution de l'application. Un venv local est uniquement nécessaire pour lancer `pytest` ou `ruff` directement depuis votre machine :

```bash
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 6. Lancer les tests

Les tests sont organisés en deux catégories :

| Catégorie | Marqueur | Infrastructure requise |
|---|---|---|
| Unitaires | *(aucun)* | aucune |
| Intégration | `@pytest.mark.integration` | Postgres + Qdrant + Valkey |

```bash
cd backend
source .venv/bin/activate

# Tous les tests (unitaires seulement si l'infra est absente)
pytest

# Un fichier précis
pytest tests/test_search.py

# Un test précis
pytest -k "test_hybrid_search"

# Avec couverture
pytest --cov=app
```

**Garde-fou base de données** : les tests écrivent dans une base dont le nom se termine par `_test` (ex. `ticketai_db_test`). Le conftest refuse d'écrire dans une base de dev. La base de test est créée automatiquement si elle n'existe pas.

**Sans infrastructure** : `pytest` skip automatiquement les tests d'intégration si Postgres/Qdrant/Valkey ne sont pas joignables. Aucune erreur n'est levée — le test est ignoré.

### Tests frontend

```bash
cd frontend
npm run test
```

---

## 7. Linting

```bash
# Backend (depuis backend/)
ruff check .
ruff format .

# Frontend (depuis frontend/)
npm run lint
```

Le CI bloque la CI si `ruff check` ou `oxlint` échouent.

---

## 8. Structure du projet

```
TicketAI/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # Routes FastAPI (tickets, reponses, documents, auth, admin…)
│   │   ├── models/          # Modèles SQLAlchemy (Ticket, Reponse, Document, User…)
│   │   ├── schemas/         # Schémas Pydantic (entrée/sortie des routes)
│   │   ├── services/        # Logique métier (search, embed, rerank, llm, ldap…)
│   │   ├── workers/         # Tâches Celery (ingestion, question, feedback, document_update)
│   │   ├── config.py        # Settings pydantic-settings (lit le .env)
│   │   ├── database.py      # engine + SessionLocal SQLAlchemy
│   │   └── main.py          # Entrée FastAPI, routers, CORS
│   ├── alembic/             # Migrations de schéma
│   ├── scripts/             # Utilitaires (seed, calibration, backfill)
│   ├── tests/               # Suite pytest
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/           # Pages React (backoffice, user, admin)
│       ├── components/      # Composants réutilisables
│       ├── lib/api.tsx      # Appels API centralisés
│       ├── hooks/           # Hooks React Query
│       └── types/index.tsx  # Types TypeScript partagés
├── Docs/                    # Documentation fonctionnelle
├── docker-compose.yml       # Services infra (postgres, qdrant, valkey)
├── docker-compose.dev.yml   # Surcharge dev (hot-reload backend + frontend)
├── docker-compose.prod.yml  # Surcharge prod (nginx, build optimisé)
└── Makefile                 # Raccourcis make up/down/dev/prod/reset-db
```

---

## 9. Rôles utilisateurs

| Rôle | Accès |
|---|---|
| `USER` | Soumettre des tickets, voir ses réponses |
| `VALIDATEUR` | Valider/corriger/rejeter les réponses en attente |
| `ADMIN` | configuration, gestion utilisateurs |

En mode `AUTH_MODE=db`, les rôles sont attribués directement en base. En production (`AUTH_MODE=ldap`), les groupes LDAP `LDAP_GROUP_GESTIONNAIRE` et `LDAP_GROUP_ADMIN` déterminent le rôle au login.

---

## 10. Les trois branches de réponse

Comprendre ces branches est central pour travailler sur le pipeline :

| Branche | Déclencheur | Validation humaine ? |
|---|---|---|
| **CANONIQUE** | Score cosinus ≥ seuil **et** réponse validée indexée dans Qdrant | Non — réponse directe |
| **SUGGESTION** | Score cosinus ≥ seuil mais pas encore canonique | Oui |
| **RAG** | Score sous le seuil — génération LLM à partir des chunks | Oui |

Une réponse devient canonique après `SEUIL_CANONIQUE` (défaut : 3) validations humaines.

---

## 11. Workflow de développement

```
feature/ma-feature
    │
    ├── make dev                   # toute la stack (infra + backend + workers + frontend)
    ├── make reset-db              # si première fois ou après make clean
    │
    ├── [code — hot-reload actif dans tous les conteneurs]
    │
    ├── pytest                     # tests (venv local requis)
    ├── ruff check . && ruff format .
    │
    └── PR → dev → CI GitHub Actions (lint + tests complets)
```

Le CI tourne la suite complète (unitaires + intégration) avec Postgres, Valkey et Qdrant provisionnés automatiquement. Une PR ne peut être mergée que si le CI est vert.

---

## 12. Documentation à lire ensuite

| Document | Sujet |
|---|---|
| [`Docs/architecture-pipeline-questions.md`](architecture-pipeline-questions.md) | Détail du pipeline question → réponse |
| [`Docs/mise-a-jour-documents.md`](mise-a-jour-documents.md) | Pipeline de mise à jour de documents et vérification de cohérence |
| [`Docs/labels-et-categories.md`](labels-et-categories.md) | Statuts, badges, et cycle de vie d'un ticket |
| [`CLAUDE.md`](../CLAUDE.md) | Référence technique rapide pour les contributeurs IA |
