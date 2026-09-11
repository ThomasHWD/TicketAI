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
| `SEUIL_CANONIQUE` | `3` | oui |
| `SEUIL_COSINUS` | `0.80` | oui |
| `SEUIL_LEXICAL_PAR_TERME` | `1.0` | non (défaut dans le code) |

> ⚠️ **Un serveur LDAP/AD joignable est requis pour se connecter, y compris en
> développement.** Sans annuaire, `/auth/login` expire et aucun compte ne peut ouvrir de
> session. Prévoyez soit un tunnel vers l'AD de l'entreprise, soit un serveur LDAP de test.

`SEUIL_CANONIQUE` et `SEUIL_COSINUS` n'ont **pas** de valeur par défaut dans le code : ils
sont obligatoires et l'application refuse de démarrer s'ils manquent. Les valeurs
ci-dessus sont celles de `.env.example`.

`SEUIL_LEXICAL_PAR_TERME`, lui, a un défaut. C'est la **porte lexicale** du rappel : un
candidat est examiné si son cosinus franchit le seuil **ou** si son BM25 par terme franchit
celui-ci. Le mettre à `0` referme la porte et restaure exactement le comportement d'avant
BM25 — c'est l'échappatoire si une calibration tourne mal.

> ⚠️ Toute clé absente de `Settings` (`app/config.py`) est **silencieusement ignorée**
> (`extra: "ignore"`) : ni erreur, ni log, le défaut du code s'applique. Une faute de frappe
> dans un nom de variable ne se voit donc pas.

### Frontend

```bash
cp frontend/.env.example frontend/.env
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

## 4. Lancer les tests

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

## 5. Linting

```bash
# Backend (depuis backend/)
ruff check .
ruff format .

# Frontend (depuis frontend/)
npm run lint
```

Le CI bloque la CI si `ruff check` ou `oxlint` échouent.

---

## 6. Structure du projet

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
│       ├── context/         # Contextes React (suivi des jobs)
│       ├── lib/api/         # Appels API, découpés par domaine fonctionnel
│       ├── hooks/           # Hooks React Query, SSE, verrous…
│       └── types/           # Types TypeScript partagés
├── Docs/                    # Documentation
│   ├── fonctionnalites/     # Ce que fait le produit, écran par écran
│   └── technique/           # Comment le moteur fonctionne
├── docker-compose.yml       # Services infra (postgres, qdrant, valkey)
├── docker-compose.dev.yml   # Surcharge dev (hot-reload backend + frontend)
├── docker-compose.prod.yml  # Surcharge prod (nginx, build optimisé)
└── Makefile                 # Raccourcis make up/down/dev/prod/reset-db
```

---

## 7. Rôles utilisateurs

⚠️ **Il n'existe que deux rôles en base : `USER` et `ADMIN`.** Il n'y a pas de rôle
`VALIDATEUR`. L'accès se joue sur **deux axes indépendants** :

| Axe | Valeurs | D'où il vient |
|---|---|---|
| **Rôle** | `USER` \| `ADMIN` | L'annuaire (groupe AD `LDAP_GROUP_ADMIN`), gravé dans le JWT |
| **Appartenance à un groupe** | 0 à N groupes | Attribuée à la main par un admin |

Ce qui donne trois profils effectifs :

| Profil | Composition | Accès |
|---|---|---|
| **Employé** | `USER`, aucun groupe | Soumettre des tickets, voir **ses** réponses |
| **Validateur** | `USER` **ou** `ADMIN`, ≥ 1 groupe | Backoffice, limité aux domaines de ses groupes |
| **Administrateur** | `ADMIN` | Pages d'administration. **Sans groupe, il ne peut ni valider ni importer de document** |

C'est donc bien la **présence d'un groupe** — et non le rôle — qui ouvre le backoffice.

`LDAP_GROUP_ADMIN` détermine le rôle à chaque login, et `LDAP_GROUP_GESTIONNAIRE` alimente
le drapeau `is_gestionnaire` (qui ne donne aucun droit en soi).

Les règles complètes sont dans [`technique/auth-et-roles.md`](technique/auth-et-roles.md).

---

## 8. Les trois branches de réponse

Comprendre ces branches est central pour travailler sur le pipeline :

| Branche | Déclencheur | Validation humaine ? |
|---|---|---|
| **CANONIQUE** | Candidat canonique avec `score_cosinus ≥ SEUIL_COSINUS` **et** un juge LLM qui confirme que la question posée est équivalente à la question indexée | Non — réponse directe |
| **SUGGESTION** | Réponse validée réutilisable, mais pas encore canonique, score sous `SEUIL_COSINUS`, **ou garde ayant refusé** | Oui |
| **RAG** | Aucun candidat réutilisable — génération LLM à partir des chunks | Oui |

Deux points que le tableau ne dit pas assez fort :

- **`SEUIL_COSINUS` est un filtre de coût, pas un filtre de sécurité.** Il limite le
  nombre de candidats envoyés au juge. C'est **le garde seul** qui décide si une réponse
  peut être servie sans revue humaine.
- **Un refus du garde sort en SUGGESTION, pas en RAG.** Il disqualifie le service *sans
  revue*, pas la proposition au relecteur. Sans ce repli le seuil était non monotone : le
  franchir pouvait faire perdre un candidat au lieu d'en gagner un.

Une réponse devient canonique après `SEUIL_CANONIQUE` (défaut : 3) validations humaines.
Être canonique n'en fait qu'un **candidat** — le garde tranche question par question. Elle
est alors indexée sous **une question par validation humaine**, pas une seule : chaque
copie SUGGESTION validée ajoute sa propre formulation comme point Qdrant.

⚠️ **Lisez [`technique/garde-cache-canonique.md`](technique/garde-cache-canonique.md)
avant de toucher aux seuils, au prompt du juge ou à la condition de la branche CANONIQUE.**

---

## 9. Workflow de développement

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

## 10. Documentation à lire ensuite

### Pour comprendre le moteur

| Document | Sujet |
|---|---|
| [`technique/architecture-pipeline-questions.md`](technique/architecture-pipeline-questions.md) | Détail du pipeline question → réponse |
| [`technique/garde-cache-canonique.md`](technique/garde-cache-canonique.md) | Le juge LLM de la branche CANONIQUE — **à lire avant de toucher aux seuils** |
| [`technique/mise-a-jour-documents.md`](technique/mise-a-jour-documents.md) | Mise à jour documentaire et ré-vérification des réponses |
| [`technique/auth-et-roles.md`](technique/auth-et-roles.md) | Rôles, groupes, domaines, LDAP, JWT |
| [`technique/reference-api.md`](technique/reference-api.md) | Tous les endpoints et leurs gardes d'accès |

### Pour comprendre le produit

| Document | Sujet |
|---|---|
| [`fonctionnalites/labels-et-categories.md`](fonctionnalites/labels-et-categories.md) | Statuts, badges et cycle de vie d'un ticket |
| [`fonctionnalites/espace-utilisateur.md`](fonctionnalites/espace-utilisateur.md) | Le parcours de l'employé |
| [`fonctionnalites/backoffice-tickets.md`](fonctionnalites/backoffice-tickets.md) | Le travail du validateur, verrous et assignation |
| [`fonctionnalites/notifications-et-temps-reel.md`](fonctionnalites/notifications-et-temps-reel.md) | SSE, canaux Redis, catalogue des événements |
| [`fonctionnalites/administration.md`](fonctionnalites/administration.md) | Groupes, santé, incidents, configuration |

Le sommaire complet est dans [`Docs/README.md`](README.md), et
[`CLAUDE.md`](../CLAUDE.md) sert de référence technique condensée pour les contributeurs
assistés par IA.
