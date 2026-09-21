# CLAUDE.md

## Project Overview

TicketAI is a RAG-based helpdesk system (HR/IT/Legal) with a human validation loop. Four answer branches:
- **CANONIQUE** — cached answer, LLM judge confirmed same question, no human review
- **SUGGESTION** — validated answer reused, human review required
- **RAG** (`source == "LLM"`) — LLM generation from chunks, always requires validation
- **HORS_DOMAINE** — model signals context doesn't carry the answer (`[HORS_DOMAINE]` marker in `services/llm.py`)

**Primary invariant (above all else):** never serve a false answer. Specific question → specific answer; never a generic answer to a specific question. Distinct canonical answers on the same subject are the nominal mode, not an edge case. See `Docs/technique/garde-cache-canonique.md`.

---

## Commands

### Infrastructure

No `docker-compose.yml` — only `docker-compose.dev.yml` / `docker-compose.prod.yml`.

```bash
make dev         # full dev stack (infra + backend + workers + frontend, hot-reload)
make dev-build   # rebuild images — mandatory after touching requirements.txt
make dev-down    # stop containers, keep data
make logs        # follow dev stack logs
make reset-db    # alembic stamp base + upgrade head + seed_validators
```

⚠️ **`make clean` destroys prod volumes** (`docker-compose.prod.yml down --rmi all --volumes`), not dev. To wipe dev:
```bash
docker compose -f docker-compose.dev.yml down --volumes && make dev && make reset-db
```

Dev ports: Postgres `5433`, Qdrant `6335`/`6336`, Valkey `6380`.

### Backend (from `backend/`)
```bash
source .venv/bin/activate
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker -Q queue_ingestion -c 2
celery -A app.workers.celery_app worker -Q queue_questions -c 4
alembic upgrade head
pytest
ruff check . && ruff format .
```

Scripts in `backend/scripts/` — run by hand, not CI. Most hit **production ports** by default; prefix with `QDRANT_PORT=6335 POSTGRES_PORT=5433` for dev, or run inside the container.

### Frontend (from `frontend/`)
```bash
npm run dev && npm run build && npm run lint   # Vite dev, build, oxlint
```

---

## Architecture

- **FastAPI** `app/main.py` — routers: `/api/v1/tickets`, `/api/v1/reponses`, `/api/v1/documents`
- **Celery** `app/workers/` — `queue_ingestion` (ingestion + feedback reindex), `queue_questions` (RAG + reverification)
- **Postgres** via SQLAlchemy — models: `Ticket`, `Reponse`, `ReponseChunk`, `User`, `DocumentRelation`
- **Qdrant** — genuinely hybrid: dense (Albert) + sparse BM25 computed locally (`services/bm25.py`), manual RRF in `services/search.py`
- **Guard** `services/garde_cache.py` — one LLM call comparing two questions. Audit trail in `garde_decisions` (append-only, no FK). Read `Docs/technique/garde-cache-canonique.md` before touching thresholds or the judge prompt.
- **BM25 tokenisation** is French-specific (elision, diacritic folding, Snowball). Token indices use `xxhash` (not `hash()` — randomised by `PYTHONHASHSEED`). Changing `K1`/`B`/`AVG_LEN`/tokenisation invalidates all sparse vectors → fix with `scripts/reencoder_vecteurs_creux.py --appliquer`.
- **Contextualisation** `services/contextualisation.py` — chunks get a locator prefix before embedding. `texte_indexe(contenu, contexte)` is the single source of truth for what was indexed. `contenu` stays raw in payload.
- **Frontend** React 19 + Vite 8 + TypeScript 6 + Tailwind v4, React Query v5, React Router v7. SSE stream keeps network busy — never use `networkidle` in browser automation.

---

## Critical Gotchas

- **`backend/.env` is frozen at container creation** — editing it has no effect on a running stack. Recreate `backend`, `worker_questions`, `worker_ingestion`, then verify from inside the container.
- **Touching any `.py` under `backend/` triggers `watchmedo`**, which restarts uvicorn + all Celery workers and kills any long-running operation.
- **Albert throttles per model**: 1 280 000 input tokens/day **and** 1 000 requests/day. The request counter bites first on short prompts. Use `ALBERT_GARDE_MODEL_NAME` and `ALBERT_CONTEXTE_MODEL_NAME` to keep counters separate.
- **Scripts default to production ports.** Only a few force dev ports via `os.environ.setdefault`. Run inside the container to be safe.
- **`make clean` targets prod**, not dev. See Infrastructure above.

---

## Key Configuration (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ALBERT_API_KEY` | — | Required for all AI calls |
| `ALBERT_GARDE_MODEL_NAME` | `ALBERT_LLM_MODEL_NAME` | Guard judge model (keep counter separate) |
| `ALBERT_CONTEXTE_MODEL_NAME` | `ALBERT_TAG_MODEL_NAME` | Contextualiser model |
| `CONTEXTUALISATION_ACTIVE` | `true` | Kill switch — `false` = pre-contextualisation behaviour |
| `SEUIL_COSINUS` | `0.80` | CANONIQUE door (not a safety filter — the guard is) |
| `SEUIL_LEXICAL_PAR_TERME` | `1.0` | BM25 recall door. `0` closes it entirely. |
| `SEUIL_CANONIQUE` | `3` | Validations to promote to canonical |
| `DOCUMENTS_STORAGE_PATH` | — | Permanent file storage |
| `FAQ_MAX_RESULTATS` | `5` | FAQ result cap |
| `FAQ_SEUIL_PERTINENCE` | `0.75` | FAQ tier-1 threshold |
| `FAQ_SEUIL_INCERTAIN` | `0.55` | FAQ tier-2 threshold (shown only when tier-1 empty) |
| `FAQ_RATE_LIMIT_PAR_MINUTE` | `20` | Per-user rate limit (`0` disables) |

`SEUIL_SUGGESTION` is derived as `SEUIL_COSINUS − 0.05` in code. Do not declare it in `.env`. `model_config = {"extra": "ignore"}` means unknown keys are silently ignored.

---

## Domain Model

- `Ticket.statut_job`: `EN_ATTENTE | EN_COURS | TERMINÉ | ÉCHOUÉ`
- `Ticket.statut_ticket`: `NOUVEAU | RÉPONDU | VALIDÉ | REJETÉ`
- `Reponse.statut`: `EN_ATTENTE | VALIDÉE | REJETÉE | CORRIGÉE`
- `source == "CANONIQUE"` identifies an answer served without review
- `Reponse.reponse_source_id` → original response for SUGGESTION copies; `nb_validations` tracked on source
- A validator cannot validate their own ticket (`verifier_auto_validation` in `reponses.py`)
- Guard audit: `garde_decisions` — append-only, no FK, survives answer deletion
