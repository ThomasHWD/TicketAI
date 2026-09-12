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
BM25 — c'est l'échappatoire si une calibration tourne mal. Le défaut de `1.0` a été mesuré sur
**24 points** : il est à recalibrer quand le corpus grossit, l'IDF que Qdrant calcule côté
serveur suivant `log(N)`. Voir [§ 9](#9-la-recherche-est-réellement-hybride--ce-quil-faut-savoir-avant-dy-toucher).

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
| `postgres` | Base relationnelle | `:5433` |
| `qdrant` | Index vectoriel | `:6335` / `:6336` |
| `valkey` | Broker Celery | `:6380` |
| `backend` | API FastAPI (`watchmedo` auto-restart) | `:8000` |
| `worker_ingestion` | Worker Celery — ingestion documents | — |
| `worker_questions` | Worker Celery — pipeline RAG | — |
| `worker_beat` | Celery Beat — tâches planifiées | — |
| `frontend` | Vite dev server (`npm run dev`) | `:5173` |

Les conteneurs applicatifs (backend, workers, frontend) montent le code source en volume : toute modification de fichier est prise en compte sans reconstruire l'image.

> ⚠️ **Les ports d'infra sont décalés en dev** (`5433`, `6335`, `6380`) alors que
> `docker-compose.prod.yml` et `backend/.env` parlent des ports standard (`5432`, `6333`,
> `6379`). Un script lancé depuis la machine hôte avec le `.env` tel quel viserait donc la
> **prod**. Les scripts de `backend/scripts/` forcent les ports de dev par
> `os.environ.setdefault` en tête de fichier — reprenez ce préambule dans tout nouveau script :
>
> ```python
> os.environ.setdefault("QDRANT_HOST", "localhost")
> os.environ.setdefault("QDRANT_PORT", "6335")
> os.environ.setdefault("POSTGRES_HOST", "localhost")
> os.environ.setdefault("POSTGRES_PORT", "5433")
> ```

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
│   ├── scripts/             # Utilitaires lancés à la main — aucun n'est dans le CI
│   │                        #   seed_validators, seed_demo_doc, captures_doc
│   │                        #   calibrate_threshold, test_cache_semantique, test_faq_campagne
│   │                        #   mesurer_longueurs, reencoder_vecteurs_creux, reinitialiser_index
│   │                        #   backfill_documents, run_search, diag_bm25, balayer_seuil_lexical…
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
| **CANONIQUE** | Candidat canonique franchissant le rappel — `score_cosinus ≥ SEUIL_COSINUS` **ou** `score_lexical ≥ SEUIL_LEXICAL_PAR_TERME` — **et** un juge LLM qui confirme que la question posée est équivalente à la question indexée | Non — réponse directe |
| **SUGGESTION** | Réponse validée réutilisable, mais pas encore canonique, sous le rappel des deux côtés, **ou garde ayant refusé** | Oui |
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

## 9. La recherche est réellement hybride — ce qu'il faut savoir avant d'y toucher

Qdrant porte **deux vecteurs par point** : un dense de 1024 dimensions produit par Albert, et
un creux BM25 calculé **localement** (`app/services/bm25.py`). Albert n'expose pas de vecteurs
creux : le client produit les tokens et la saturation TF, et **c'est Qdrant qui fournit l'IDF**
(`Modifier.IDF` sur la configuration creuse, posé dans `init_collection`).

Ce partage explique la plupart des pièges ci-dessous — le poids final d'un terme est calculé
moitié à l'écriture, moitié à la lecture.

| Ce qui est figé à l'écriture | Ce qui est recalculé à chaque requête |
|---|---|
| tokenisation, saturation TF (`K1`, `B`, `AVG_LEN`) | IDF (dépend du corpus entier) |

### Les pièges, par ordre de méchanceté

**1. `Modifier.IDF` se pose à la création de la collection.** L'ajouter à une collection
existante impose de la recréer et de tout réindexer (`scripts/reinitialiser_index.py`).

**2. Changer `K1`, `B`, `AVG_LEN` ou la tokenisation invalide tous les vecteurs creux déjà
écrits.** Le rattrapage se fait avec `scripts/reencoder_vecteurs_creux.py --appliquer`, **pas**
avec `reinitialiser_index.py` : seule la moitié creuse change, rejouer l'ingestion rachèterait
un embedding Albert par chunk pour rien. Le ré-encodage est exact parce que les deux
producteurs stockent le texte encodé tel quel dans le payload (`contenu` pour les chunks,
`question_indexee` pour les points de réponse).

**3. `AVG_LEN` et `B` forment une paire calibrée, pas deux boutons indépendants.** Le corpus est
**bimodal** — des chunks de document (mesuré le 12/09/2026 : n=578, moyenne 95,6 tokens BM25) et
des points de réponse indexés sous une *question* (n=40, moyenne 4,4). La normalisation par
longueur ne joue donc presque rien *à l'intérieur* de chaque population et tout *entre* elles.
Valeurs actuelles : `AVG_LEN = 96` (la moyenne documentaire mesurée, ce que BM25 appelle
`avgdl`), `B = 0.70`. À re-mesurer avec `scripts/mesurer_longueurs.py` dès que les points de
réponse pèseront une part significative du corpus.

**4. Les indices de tokens viennent de `xxhash`, surtout pas du `hash()` de Python** — celui-ci
est randomisé par processus via `PYTHONHASHSEED`. Un indice écrit par le worker d'ingestion
serait introuvable depuis l'API, **silencieusement**.

**5. Les indices creux sont des `uint32`, limite dure du protocole Qdrant**
(`points.proto:130`, `repeated uint32 indices`). `xxh32` n'est donc pas un réglage : un hash
plus large ne peut pas être envoyé.

**6. `snowballstemmer` manquant met la stack à terre, il ne la dégrade pas.** `embed_texts`
calcule le vecteur creux **avant** l'appel Albert : sans le stemmer, *tout* embedding lève.
Un `pip install` fait à l'intérieur d'un conteneur survit à un `restart` mais meurt à la
recréation suivante, et `docker compose ps` continue d'afficher *running*. Après avoir touché
`requirements.txt` : `make dev-build && make dev`, puis vérifier l'import depuis chacun des
quatre conteneurs Python.

**7. La tokenisation est spécifique au français** — élision (`l'abonnement` → `abon`, et non
`l` + `abon`), pliage des diacritiques, mots vides, racinisation Snowball. Les élisions sont
retirées **par position, via une regex**, et non par appartenance à un ensemble de lettres :
filtrer `l d j n s t c m` partout supprimait aussi des tokens porteurs de sens — « disque **C** »,
« vitamine **D** ». Couvert par `tests/test_bm25.py`.

**8. Le score lexical est ramené au terme, avec un plancher à 2.** Un score BM25 est une somme
sur les termes de la requête : brut, il favorise mécaniquement les questions longues. Sans le
`DIVISEUR_MINIMAL = 2` de `search.py`, une requête d'un seul mot aurait un diviseur de 1 — et
n'importe quel mot plus rare que la moitié du corpus ouvrait la porte lexicale. Chaque
ouverture coûte un appel au juge.

**9. Le rattrapage croisé porte la fusion** (`_completer_scores` dans `search.py`). Un point
hors du top-k d'une branche hériterait sinon d'un `0.0` sur celle-ci. Manquer le sens dense
rend BM25 inutile (trouvé, puis écarté par le seuil) ; manquer le sens lexical a été mesuré
comme inversant le classement. Coût : deux requêtes Qdrant, zéro appel Albert.

⚠️ **Le RRF ne sert qu'à ordonner.** Les seuils portent sur **chaque signal brut, sur sa propre
échelle** — aucun score de fusion n'est absolu.

Le raisonnement complet est dans [`technique/choix-techniques.md`](technique/choix-techniques.md)
et les mesures dans [`technique/rapport-test-cache-semantique.md`](technique/rapport-test-cache-semantique.md) § 15.

---

## 10. Workflow de développement

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

## 11. Documentation à lire ensuite

### Pour comprendre le moteur

| Document | Sujet |
|---|---|
| [`technique/architecture-pipeline-questions.md`](technique/architecture-pipeline-questions.md) | Détail du pipeline question → réponse |
| [`technique/choix-techniques.md`](technique/choix-techniques.md) | Pourquoi cette stack — et le raisonnement derrière la recherche hybride (BM25, porte lexicale, RRF pour l'ordre seul) |
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
