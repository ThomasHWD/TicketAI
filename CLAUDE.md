# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TicketAI is a RAG-based helpdesk system that auto-answers employee questions (HR, IT, Legal) using internal documents, with a human validation loop. The system has four answer branches:
- **CANONIQUE** — a canonical answer was retrieved **and an LLM judge ruled the question asked equivalent to the one it is indexed under** (no human review needed)
- **SUGGESTION** — a validated but not-yet-canonical answer was retrieved; reused, but still requires human review
- **RAG** (`source == "LLM"`) — LLM generation from reranked document chunks (always requires human validation)
- **HORS_DOMAINE** — the generation ran but the model itself signalled the context does not carry the answer, by emitting a `[HORS_DOMAINE]` marker (`_HORS_DOMAINE_MARKER` in `services/llm.py`, stripped and
flagged by `generer_reponse`, recorded as `source="HORS_DOMAINE"` in `workers/question.py`). An abstention, not a failure: the branch exists so the system says "I don't know" instead of inventing.

Validated answers accumulate `nb_validations`; when they reach `seuil_canonique` (default 3), they become canonical and are re-indexed in Qdrant. Being canonical only makes an answer a *candidate* — the guard decides question by question.

### The primary invariant: never serve a false answer

Stated by the product owner on 2026-09-17 and ranked above every other concern, **including reviewer workload**: *"c'est la condition primaire de toujours servir une réponse juste, même si ça demande plus de travail aux validateurs."* Where a design trades safety against review cost, safety wins. This **supersedes** the earlier "1 gesture vs ≥3 revalidations" arithmetic wherever the two conflict.

The preference ordering it implies, in the owner's own terms:

1. General answer when the question is general; **specific when the question is specific**.
2. **Never a generic answer to a specific question** — the failure this ordering exists to forbid.
3. Failing a specific answer, *"général + exception"* is strictly better than *"général seul"*.

**Distinct canonical answers are therefore the nominal mode, not an edge case** — one canonical general answer and one canonical specific answer may coexist on the same subject. Nothing in the data model ever forbade it (`Reponse.canonique` is a per-row boolean, Qdrant holds one point per validated formulation, `trouver_reponse_reutilisable` already picks among several); four mechanisms made them unreachable, all four fixed on 2026-09-17: relevance now outranks `canonique` in the selection (§ Question pipeline), CORRIGÉE answers are reusable, aliases are judged before they are written (§ Feedback pipeline), and `a_relire` suspends the CANONIQUE branch.

**Measured end to end on 2026-09-18** (domain `T3`, doc A general + doc B specific, 3 passes per ask): the specific answer born of the RAG branch, validated once, **outranks the general canonical** — non-canonical at `nb_validations=1` beating canonical at 4, cosine 0.9042. That step is the only proof the starvation is lifted, and it cannot be shown outside real conditions, since producing two competing answers on one subject requires the fix itself. Two more validations promote it: `807a1755` (general, `a_relire`) and `266926a0` (specific) are then **both canonical, same domain, same subject**. A never-validated formulation of the specific question comes out **CANONIQUE 3/3** at 0.8075 carrying the specific answer; the general question returns the **general** answer 3/3 at 0.8472 (SUGGESTION, since it is flagged). No cannibalisation either way. The path that creates the specific canonical is **RAG → validate → SUGGESTION → validate → SUGGESTION → validate** — the "Corriger" gesture the plan assumed is not needed, because a judged refusal now routes the question to a RAG that answers it correctly.

Contrast with what is **not** done: an answer suspected of being contradicted is never destroyed (`obsolete`) on the strength of a paragraph↔question cosine. It loses the right to be served *without review*, which costs one reading and destroys nothing. "Never serve a false answer" is about serving, not about deleting.

---

## Commands

### Infrastructure

There is **no `docker-compose.yml`** and **no `make up` / `make down`** — only
`docker-compose.dev.yml` and `docker-compose.prod.yml`, and the Makefile targets below.

```bash
make dev         # full dev stack: infra + backend + workers + frontend, hot-reload
make dev-build   # rebuild the images (mandatory after touching requirements.txt)
make dev-down    # stop the containers, KEEP the data
make logs        # follows the dev stack
make reset-db    # alembic stamp base + upgrade head + seed_validators
```

⚠️ **`make clean` does not clean the dev stack.** It is
`docker compose -f docker-compose.prod.yml down --rmi all --volumes --remove-orphans`, and the
two Compose files declare **separate projects** (`name: ticketai-dev` vs `name: ticketai`), so
the volumes are disjoint (`ticketai-dev_postgres_data` vs `ticketai_postgres_data`). Running it
therefore leaves dev untouched and **destroys the prod volumes** if they live on the same
machine — plus every image (`--rmi all`). To actually wipe dev:

```bash
docker compose -f docker-compose.dev.yml down --volumes && make dev && make reset-db
```

**Infra ports are shifted in dev**: Postgres `5433`, Qdrant `6335`/`6336`, Valkey `6380`.
`docker-compose.prod.yml` and `backend/.env` use the standard ones (`5432`, `6333`, `6379`).

### Backend (from `backend/`)
```bash
# Activate venv first
source .venv/bin/activate

# Run API
uvicorn app.main:app --reload

# Run Celery workers
celery -A app.workers.celery_app worker -Q queue_ingestion -c 2
celery -A app.workers.celery_app worker -Q queue_questions -c 4

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Tests
pytest                              # all tests
pytest tests/test_search.py        # single file
pytest -k "test_name"              # single test

# Linting
ruff check .
ruff format .
```

**Utility scripts** (`backend/scripts/`, run by hand — none are part of CI):

```bash
PYTHONPATH=. python scripts/calibrate_threshold.py   # threshold sweep over dataset_calibration.json
PYTHONPATH=. python scripts/test_garde_reel.py       # exercises the guard against real Albert
PYTHONPATH=. python scripts/run_search.py            # ad-hoc hybrid-search probe
PYTHONPATH=. python scripts/backfill_documents.py    # rebuild `documents` rows from Qdrant
PYTHONPATH=. python scripts/seed_validators.py       # dev fixtures
PYTHONPATH=. python scripts/mesurer_longueurs.py     # re-measure the corpus, solve for B (read-only, no Albert)
PYTHONPATH=. python scripts/reencoder_vecteurs_creux.py --appliquer   # rewrite sparse vectors only, no Albert
PYTHONPATH=. python scripts/test_faq_campagne.py     # FAQ campaign: 34 embeddings, zero LLM
PYTHONPATH=. python scripts/diag_bm25.py             # decompose cosine / BM25 raw / per-term / gate taken
PYTHONPATH=. python scripts/balayer_seuil_lexical.py <campagne.json>   # replay a campaign at other thresholds, zero Albert
PYTHONPATH=. python scripts/reinitialiser_index.py   # recreate the collection — full re-ingestion, expensive
TAI_USER=... TAI_PASS=... python scripts/captures_doc.py   # documentation screenshots
```

⚠️ **Scripts read Qdrant and Postgres through `Settings`, i.e. through `backend/.env`, which
describes the *production* ports (`5432`/`6333`) while the dev stack listens on `5433`/`6335`.**
Both stacks can run at once — they are separate Compose projects — so pointing at the wrong one
does not fail, it silently succeeds against the wrong data.

**Only these force the dev ports themselves** (`os.environ.setdefault` at the top of the file):
`diag_bm25`, `diag_faq_seuil`, `mesurer_longueurs`, `reencoder_vecteurs_creux`,
`reinitialiser_index`, `test_faq_campagne`, `test_lexical_reel`,
`test_reverification_rappel_reel`.

**Every other script hits production**, including ones listed above — `run_search`,
`calibrate_threshold`, `test_garde_reel`, `backfill_documents`, `seed_validators`,
`test_cache_semantique`. Pass the variables on the command line, or add the `setdefault`
preamble:

```bash
QDRANT_PORT=6335 POSTGRES_PORT=5433 PYTHONPATH=. python scripts/<script>.py
```

`make reset-db` **used to be** in this category — it ran from the local venv and therefore
initialised the *prod* database. It now runs through `$(DC_DEV) exec -T backend`, and refuses to
start if the dev backend container is not up. That is the general escape: **run inside the
container rather than tuning variables on the host** — the container already carries the right
configuration (`POSTGRES_HOST: postgres` in the service's `environment:`, internal port 5432),
the host carries production's.

Anything touching search, the thresholds or the judge prompt costs real Albert calls.
Two things to know before spending them:

- **Albert throttles per model on two counters**, `1 280 000` input tokens/day **and**
  `1 000` requests/day — the second bites first on short prompts, and a 429 carries no
  `Retry-After`. Rotating the API key changes nothing; switching model does. This is why
  `ALBERT_GARDE_MODEL_NAME` exists: sharing the generation model lets generation calls
  drain the judge's counter, producing silent guard refusals.
- **Editing `backend/.env` does not reach a running stack.** `env_file:` is read at
  container *creation* and those values outrank the mounted file in pydantic-settings, so an
  already-present key stays frozen at its old value, silently. Recreate `backend`,
  `worker_questions`, `worker_ingestion`, then verify from inside the container. And never
  edit a `*.py` under `backend/` during a long run — `watchmedo` restarts uvicorn and
  Celery, which kills it.
- **A running container's state is not its image's state.** Same trap, second form: a
  `pip install` done inside a container survives `restart` but dies at the next recreation,
  and `docker compose ps` still shows everything *running*. What gives it away is
  `RunningFor` — if it predates your `up`, Compose recreated nothing because the image never
  changed. `snowballstemmer` disappearing this way takes the whole stack down rather than
  degrading it: `embed_texts` computes the sparse vector **before** the Albert call, so every
  embedding raises. After touching `requirements.txt`, `make dev-build && make dev`, then
  verify the import from inside each of the four Python containers.
  ⚠️ **`make clean` is not the dev reset it looks like** — it targets the *prod* Compose
  project, destroying the prod volumes and every image while leaving dev untouched. See the
  Infrastructure section above.

Guard design and rationale: [`Docs/technique/garde-cache-canonique.md`](Docs/technique/garde-cache-canonique.md).

### Frontend (from `frontend/`)
```bash
npm run dev      # Vite dev server
npm run build    # tsc + Vite build
npm run lint     # oxlint
```

---

## Architecture

### Backend (`backend/`)
- **FastAPI** app in `app/main.py` — three routers: `/api/v1/tickets`, `/api/v1/reponses`, `/api/v1/documents`
- **Celery** workers in `app/workers/` — two queues: `queue_ingestion` (document ingestion + feedback reindexing) and `queue_questions` (RAG pipeline, plus `reverification_job` — network waits on Albert, which have nothing to do in the queue that serialises ingestions)
- **Broker**: Valkey (Redis-compatible) via `valkey_url` from settings
- **Database**: PostgreSQL via SQLAlchemy; models in `app/models/` (`Ticket`, `Reponse`, `ReponseChunk`, `User`, `DocumentRelation`)
- **Vector store**: Qdrant, genuinely hybrid — dense from Albert, sparse BM25 computed locally (`app/services/bm25.py`), manual RRF fusion in `app/services/search.py`. Albert exposes no sparse vectors, so the client produces tokens + TF saturation and **Qdrant supplies the IDF** (`Modifier.IDF` on the sparse config, set in `init_collection`). That modifier is fixed **at collection creation**: adding it to an existing collection requires recreating and re-indexing (`scripts/reinitialiser_index.py`).
  - **Tokenisation is French-specific and the risky part**: elision (`l'abonnement` → `abon`, not `l` + `abon`), diacritic folding, stopwords, Snowball stemming. Covered by `tests/test_bm25.py`.
  - Token indices come from `xxhash`, **not** Python's `hash()`, which is randomised per process by `PYTHONHASHSEED` — an index written by the ingestion worker would be unfindable from the API, silently.
  - **`AVG_LEN` and `B` in `bm25.py` are a calibrated pair, not two independent knobs.** The corpus is bimodal — document chunks (measured 2026-09-12: n=578, mean 95.6 BM25 tokens, CV 0.24) and response points indexed under a *question* (n=40, mean 4.4). Length normalisation therefore does almost nothing *within* each population and everything *between* them. `AVG_LEN` was `40`, half the real document mean, which gave question points a 2.44× structural advantage over chunks in the sparse top-k they share. The pair is now chosen under one constraint: put `AVG_LEN` on the measured document mean (what BM25 calls avgdl) **without moving the question scale**, since that is what `SEUIL_LEXICAL_PAR_TERME` thresholds. `AVG_LEN = 96`, `B = 0.70` → an average chunk weighs 1.0, a question keeps 1.567 (+0.6 %), the gap falls to 1.56×, and the calibrated threshold does not move. Re-measure with `scripts/mesurer_longueurs.py` once response points become a significant share of the corpus.
  - ⚠️ **Changing `K1`, `B`, `AVG_LEN` or the tokenisation invalidates every sparse vector already written** — TF saturation is frozen at write time, unlike the IDF Qdrant recomputes. Fix with `scripts/reencoder_vecteurs_creux.py --appliquer`, **not** `reinitialiser_index.py`: only the sparse half changes, so replaying ingestion would re-buy one Albert embedding per chunk for nothing. The re-encode is exact because both producers store the encoded text verbatim in the payload — `question_indexee` for response points, and for document chunks `texte_indexe(contenu, contexte)`, recomposed through the *same* function the producers call (see Contextualisation below). Reading `contenu` alone there would strip the locator from every sparse vector in the corpus at the next recalibration, silently, since the dense half would stay correct.
  - **Token indices are `uint32`, a hard Qdrant limit** (`points.proto:130`, `repeated uint32 indices`). `xxh32` is therefore not a tunable choice — a wider hash cannot be sent. Collisions merge document frequencies and slightly deflate the server-side IDF; at this corpus size the probability is negligible.
  - **Elisions are stripped by position, not by membership** (`_ELISION` regex, covering U+0027 and U+2019). Filtering the letter set `l d j n s t c m` everywhere also removed meaningful one-letter tokens — "disque **C**", "vitamine **D**".
  - `SEUIL_LEXICAL_PAR_TERME` divides the BM25 sum by the query's term count, floored at `DIVISEUR_MINIMAL = 2` (`search.py`). Without the floor a one-word query had a divisor of 1, so any word rarer than half the corpus opened the lexical door — and each opening costs a judge call.
- **AI services** in `app/services/`: embedding (`embed_texts`), reranker, LLM generation — all call Albert API (French government API)
- **Config**: `app/config.py` uses `pydantic-settings`; reads from `.env`

### Ingestion pipeline (`workers/ingestion.py`)
Upload → sanitize → extract text (PDF/DOCX/TXT/MD) → chunk (384 tokens BGE-M3, 128 overlap) → **contextualise** → embed → upsert into Qdrant → move to permanent storage → **confront the answers already being served**.

**Contextualisation** (`services/contextualisation.py`) — a chunk is vectorised *in isolation*, so "les alternants n'en bénéficient pas" contains no occurrence of "télétravail" and no search on telework ever retrieves it. Each chunk is therefore prefixed with one sentence that *locates* it (which rule it belongs to, who it applies to) and **that** text is what gets embedded, dense and sparse alike.
- **`contenu` stays raw in the payload; the prefix lives beside it in `contexte`.** `capturer_chunks` (`services/qdrant.py`) reads `contenu` to build the next version's diff, and an LLM output varies run to run — folding it into `contenu` would make *every* chunk look modified at *every* update, the phantom units the update pipeline is built to avoid.
- **`texte_indexe(contenu, contexte)` is the single definition of "what text was encoded"**, imported by both producers (`workers/ingestion.py`, `workers/document_update.py`) and by `scripts/reencoder_vecteurs_creux.py`. If those diverged, the next BM25 recalibration would rewrite the sparse vectors from text nobody ever indexed, silently.
- **Cost**: one synopsis call + one call per batch of `TAILLE_LOT = 5` chunks (~2,300 input tokens each), ingestion-only. The original recipe (whole document re-sent per chunk) would be ~5.8M tokens on this corpus against a 1,280,000/day quota. `ALBERT_CONTEXTE_MODEL_NAME` keeps that off the generation model's counter.
- **Everything is best-effort**: a network failure, unreadable JSON or a batch of the wrong length yields `""` and the ingestion falls back to exactly its previous behaviour. The returned list *always* has `len(chunks)` entries — an off-by-one would prefix each passage with its neighbour's subject, which is worse than no context because it makes the *wrong* chunk findable. Three consecutive failed batches abandon the document (a 429 holds for the day).
- ⚠️ **The batch prompt must state the expected count, and must not show a fixed-arity example.** Measured 2026-09-17 on the dev stack, 3 passes per batch size: with the old tail `["…", "…"]`, a **one-extract batch came back as `[ "…", "" ]` 3 times out of 3** — the model copied the example's arity and padded with an empty string — against 0 failures at 2 and at 3. `_lire_locateurs` rejected the batch, the document indexed raw, nothing failed. So every single-chunk document and every trailing batch where `len(chunks) % 5 == 1` silently lost its locator. The count is now repeated at the end of the user message and pinned by `test_le_lot_annonce_sa_longueur_au_modele`. This is the general shape of the failure here: **best-effort degradation is invisible to a green suite** — it can only be caught by measuring the model's actual output (`scripts/bout_en_bout_teletravail.py --etape contexte`).
- Downstream, `reciprocal_rank_fusion` exposes `contexte` and `contenu_indexe`; `reranker.py` and `llm.py generate()` both read `chunk.get("contenu_indexe") or chunk["contenu"]`. The reranker especially: a passage retrieved *because of* its locator would otherwise be re-scored without it and ranked last.
- `services/llm.py` `prompt_system` carries the **lex specialis** rule — specific beats general, state both, and say so when the question targets a case no excerpt covers rather than defaulting to the general rule.
- **Both of these govern the RAG branch only.** Measured 2026-09-17, 3 passes each: on the RAG branch the general question *and* the alternants question both state rule + exception, 3/3, with B's chunk reranked #1 at 0.9720 on the specific question. But the specific question routed through the **full pipeline** scored 0.7730 against the canonical's question points — under `SEUIL_COSINUS`, so the guard was never called and the cache returned the **general** answer. It lands in SUGGESTION (human review), never CANONIQUE, so nothing false is served unreviewed; but no amount of contextualisation or lex specialis reaches a question the cache answers. Harness: `scripts/bout_en_bout_teletravail.py`.

### Confrontation pipeline (`workers/confrontation.py`, `services/confrontation.py`)
The reverification funnel only fires on a **version replacement** — it needs an AVANT/APRÈS diff. Ingesting a document for the *first* time therefore touched nothing, including a CANONIQUE answer that the new document now contradicts and that kept being served **without human review**, indefinitely.

Detection runs inside `ingestion_job` and costs **zero Albert calls**: the chunk vectors have just been paid for, so `cibles_confrontation(embeddings, domaine)` is N dense Qdrant queries reusing `_voisines`' exact filter and `SEUIL_RAPPEL`. It returns `{reponse_id: [chunk_index, …]}` — keeping the chunk↔answer pairing is what lets the job judge each answer against the passages that actually matched it. Matched families are flagged `ANALYSE_EN_COURS` **in the same commit as the document rows** (closing the race window), and `confrontation_job` is enqueued on `queue_questions` only if there are targets.

`confrontation_job` is a deliberate **sibling** of `reverification_job`, not a reuse: the latter reads its units from `DocumentVersion.changements` and degenerates to `RAISON_MASSIVE` past `MAX_UNITES = 40`, which on a new document would match zero answers (nothing cites it) and do nothing, silently. Everything that matters is shared — `Candidate`, `unites_pertinentes`, `decider`, `signaler_sans_juger`, `rabattre`, `publier_bilan`, the `on_failure` discipline.

**Invariant: no answer ever becomes obsolete on this path.** `decider` calls `retirer_du_service` only on `CONTREDITE` **and** `citante`, and `citante` comes from `reponse_chunks` — a document that did not exist when the answer was generated has no row there. The cap at `a_relire` is a consequence of the data model, not a flag that could be lifted; and it is the right cap, because an *incomplete* answer is amended in one gesture ("Modifier", keeping `nb_validations`) where a withdrawal costs `SEUIL_CANONIQUE` revalidations for an identical end state. Pinned by `tests/test_confrontation.py`.

The judge gets a different prompt (`PROMPT_SYSTEME_CONFRONTATION`) saying both documents are **in force at the same time** — without it the model treats the new text as a v2 that repeals the v1 — plus `contexte_source(db, reponse)`, the passages the answer was actually built on, which is what lets it tell a *false* answer from an *incomplete* one and discard the false pairings of a 0.35 recall. New reason `NOUVEAU_DOC`: `DOC_MODIFIÉ` would send the reviewer looking for a diff that does not exist.

### Question pipeline (`workers/question.py`)
Embed question → hybrid search (dense + BM25, RRF for ordering) → look for a Qdrant point carrying a `reponse_id` that **clears the recall gate**: cosine `>= SEUIL_SUGGESTION` **or** per-term BM25 `>= SEUIL_LEXICAL_PAR_TERME` (`franchit_le_rappel`, `services/search.py`).

**Which candidate wins, when several clear the gate** (`trouver_reponse_reutilisable`): the `max()` key is `(score_rrf, canonique, nb_validations, id)` — **relevance first, status only as a tie-break**. It used to be the other way round, `r.canonique` primary and relevance third, which meant a canonical *general* answer at RRF 0.010 beat a validated *specific* answer at 0.030. The specific one was therefore never proposed, never validated, never canonical: a structural starvation that made distinct canonical answers impossible and returned the general answer to a specific question indefinitely. RRF is the system's declared ordering signal (`services/search.py`) and was already in this key — it was promoted, not invented. Accepted cost: near ties can now flip a canonical to a fresh answer, trading CANONIQUE for SUGGESTION — one more reading, not a safety risk, since the guard still decides what is served unreviewed. Candidates are `VALIDÉE` **or `CORRIGÉE`**, non-obsolete; excluding CORRIGÉE made "Corriger" — the reviewer's *correct* gesture — sterile, since the text a human wrote himself was indexed, fed the RAG context, and was never reused, so it could never accumulate validations.

**Which branch that candidate takes:**

1. **Any candidate that would be reused — `peut_servir_sans_revue(reponse) or candidat.servable`** → run the guard (`services/garde_cache.py`): one LLM call, binary OUI/NON. **The judge is consulted exactly when his verdict can change the outcome** (since 2026-09-18): neither the score nor the status gates the call, they decide only *what a OUI opens*. `SEUIL_COSINUS` **and** `peut_servir_sans_revue` are retested inside `servir_reutilisation`, so the unreviewed-serving door is strictly unchanged: a OUI below the threshold, or on a non-canonical or `a_relire` answer, comes out SUGGESTION — it opens nothing. What the widening buys is **use of the NON**; measured, two candidates at 0.7996 and 0.785 were submitted to nobody, and the entire SUGGESTION branch had no judge at all. That asymmetry is what makes it safe — the judge's refusal is used, never his approval. The only candidate that skips the call is one retained by the words alone **and** non-canonical: its outcome is RAG whatever the verdict, so the call would buy nothing. It compares **two questions and nothing else** — the question asked against **the question carried by the Qdrant point that actually matched** (payload `question_indexee`, propagated through `search_hybrid` → `trouver_reponse_reutilisable`; falls back to `Ticket.question` / `Reponse.question_suivi` for points written before multi-formulation indexing). An answer is indexed under as many questions as it has human validations, so re-deriving the question from the ticket would submit the *wrong* pair to the judge. It is shown neither the cached answer, nor any document. Approve → CANONIQUE **if** the candidate also clears `SEUIL_COSINUS`, SUGGESTION otherwise.
   **A judged refusal → full RAG** (`source == "LLM"`, `EN_ATTENTE`). The judge just ruled the two questions are not the same demand, so the candidate does not answer *this* one; proposing it to the reviewer puts something already ruled off-topic on the screen where "Valider" is the cheapest button — the same button that writes an alias (§ Feedback pipeline). `Candidat.servable` already stated this rule for lexical-only candidates; it was abandoned above `SEUIL_SUGGESTION` for no reason. **This reverses the earlier "Refuse → SUGGESTION, not full RAG" rule**, whose justification was non-monotonicity (a candidate at 0.84 came out SUGGESTION unjudged while the same at 0.86 was judged and, on refusal, sent to RAG with no candidate — crossing `SEUIL_COSINUS` *degraded* the outcome). Both halves of that argument fell together: the discontinuity is gone now that the judge is called on both sides of the threshold, and its premise — a refused candidate beats RAG — is what measurement contradicts (9 refusals, **6** came out SUGGESTION where RAG was expected). Campaign 48 cases, 3 identical passes: conformity 35/48 → **43/48**, judge calls 27 → 30, **0 false positives** either way; case-by-case diff is exactly 9 `SUGGESTION → RAG`, all `bloque_par=GARDE`.
   **Only a *judged* refusal does this.** `Decision.erreur` exists for that distinction — Albert unreachable, or no indexable question to submit, is an **absence of verdict**, not "not the same demand": the previous behaviour is kept, SUGGESTION under human review. A network outage must decide neither a branch nor a generation (an Albert outage must not be paid in calls to Albert). Accepted cost: a *prudent* refusal (the 0.8841 case, pair in fact equivalent) deprives the reviewer of a reusable validated answer and spawns a parallel lineage on the same subject — amortized by relevance-first selection. Do **not** arbitrate it by softening the judge prompt.
   **Short-circuit**: if the question, normalised for typography (case, punctuation, whitespace — **not accents**, `_normaliser` composes with NFC, it does not strip diacritics), is identical to the indexed question, it is served without calling the LLM. **Disabled in follow-up mode**: comparing a whole thread typographically to a single question is meaningless, and comparing only its last line would throw away the context that makes serving safe.
   **In follow-up mode**: the guard receives `requete_recherche` (the full thread concatenated) rather than the bare precision — "and for an apprentice?" only means something inside its thread. It is therefore given a **different system prompt** (`_PROMPT_SYSTEME_SUIVI`) telling it the last line is the actual demand and the preceding lines are context. Without it the judge compares two stacked questions against one and refuses by format artefact rather than by judgement — measured at 5 refusals out of 5.
   Every invocation is recorded in `garde_decisions` via `journaliser_garde` (own DB session, never raises).
   What authorises serving is the **transitivity of human validation**: a human validated answer A for question Q₁; if Q₂ asks exactly the same thing, A holds — nothing to re-derive from the corpus.
   **`a_relire` closes the door of *serving unreviewed*, not the door of the judge** (corrected 2026-09-18; this page said the opposite). The two signals are **orthogonal and cumulative**: the flag is about whether the *answer* is still true, the guard about whether the *demand* is the same. The old rationale — "the guard could only ever say OUI, the pair is fine" — assumes the pair *is* equivalent; when it is not, the judge says NON, and skipping the call throws that away because we distrust an unrelated signal. The second half — "we won't serve it unreviewed anyway, so the call is a free saving" — only held while a refusal *also* produced SUGGESTION. Measured 2026-09-18 on a fresh domain (doc A general → canonical at 3 formulations → doc B specific → specific question): the confrontation flags the canonical, and the general answer was then proposed to "est ce que télétravail possible ? pour les alternant ?" 3/3, cosine 0.8047, **zero rows in `garde_decisions`** — while the judge, once asked, refuses 3/3 and RAG answers correctly 3/3 (doc B reranked #1 at 0.9677). Campaign cost, 3 identical passes, 0 false positives: 43/48 → **42/48**, judge calls 30 → 34, of which only **2 calls and 1 branch change** are attributable to the widening (3 of the 6 diffs are Qdrant-IDF corpus drift, upstream of anything changed). The flag remains **a triage, not a withdrawal**: `trouver_reponse_reutilisable` still returns the answer, an approved one comes out SUGGESTION, and it stays amendable in one gesture with `nb_validations` intact. It loses only the CANONIQUE privilege. Same predicate has an SQL mirror in `services/faq.py` — that page has no reviewer at all, so showing a flagged answer there *is* serving it unreviewed; `tests/test_faq.py` compares the two on the same flag set.
2. **Guard approved but the answer is non-canonical, flagged `a_relire`, or below `SEUIL_COSINUS`** → returned as SUGGESTION (human review required). Same branch when there is **no verdict** (Albert unreachable, no indexable question) and the candidate is `servable`.
3. **No candidate found** → rerank top-15 chunks → LLM generation → save as EN_ATTENTE (RAG branch)

`SEUIL_COSINUS` — and the lexical door beside it — is not a safety filter: it decides **what a OUI is allowed to open** (CANONIQUE vs SUGGESTION), evaluated inside `servir_reutilisation`. It no longer meters judge calls; that is set upstream by the recall gate (`SEUIL_SUGGESTION`), which decides how many candidates exist at all. The guard alone decides whether a canonical answer is served without human review. **Read [`Docs/technique/garde-cache-canonique.md`](Docs/technique/garde-cache-canonique.md) before touching the thresholds, the judge prompt, or the CANONIQUE branch condition.**

### Feedback pipeline (`workers/feedback.py`)
Triggered after validation/correction; re-indexes the validated response in Qdrant (links `reponse_id` to the Qdrant point payload for future canonical lookup).

`feedback_job` writes one point **per human-validated formulation** of a response, indexed under the vector of a question. The payload carries `reponse_id`, `ticket_id`, `contenu`, `domaine` and `question_indexee` (the question *this* point is indexed under). These points are what `trouver_reponse_reutilisable` finds on the next similar question.

- `feedback_job(reponse_id)` → the original point, id `uuid5(reponse.id)`, indexed under `Ticket.question` (or `Reponse.question_suivi` for follow-ups).
- `feedback_job(reponse_source_id, formulation_id)` → an **additional formulation**: `formulation_id` is a validated SUGGESTION copy, and its own question is indexed under a distinct point `uuid5(f"{source.id}:{copie.id}")`. Emitted by `valider_reponse` alongside the source re-index. Without it, a response promoted canonical at three validations was reachable from a *single* formulation — the other two, explicitly validated by a human, were discarded.
  - ⚠️ **That alias is submitted to the guard before it is written** (`_alias_juge`) — the **second call site** of `garde_cache.statuer`. Writing an alias is *stronger* than anything the guard rules on at serving time: the point carries the copy's question with the source's `reponse_id`, so the next identical ask scores ~1.0, hits the typographic short-circuit, and is served CANONIQUE **with no judge at all**. A false alias does not pass the guard, it bypasses it — and nothing checked it. One reviewer clicking "Valider" instead of "Corriger" on a *plausible but off-target* SUGGESTION was enough, and the emerald button is the cheapest path on the screen. Three distinct outcomes: OUI → written; judged NON → no alias (which is just the pre-multi-formulation behaviour, not a loss); `Decision.erreur` → `retry`, because a default refusal would silently discard a formulation a human validated. Logged in `garde_decisions` with `score_cosinus = NULL` — the pair comes from a human gesture, not a search, and `0.0` would read as a very distant candidate. Cost: one judge call per *human validation*, zero when the two formulations are typographically identical.
  - Scope is deliberately limited to the alias: `nb_validations` is still incremented by the HTTP endpoint. Gating it would mean a synchronous LLM call on a web request, for a signal that *promotes* without *serving*.
- Consequently **`delete_response_point` deletes by payload filter `reponse_id`, not by point id** (`services/qdrant.py`). Deleting by id would remove only the original question and leave the answer servable from its aliases, making a withdrawal for obsolescence or contradiction silently ineffective.

### FAQ (`services/faq.py` → `api/v1/faq.py`, page `/faq`)
`GET /api/v1/faq/recherche?q=…` — **read-only consultation**, open to any authenticated user (`CurrentUser`, not `BackofficeUser`). One embedding call, one Qdrant query across **all domains**, restricted to response points via `FILTRE_POINTS_REPONSE` (`services/search.py` — document chunks carry no `reponse_id`, `IsEmpty` excludes them). Candidates are then filtered **in Postgres** to `canonique = True` + `obsolete = False`, deduplicated per `reponse_id` keeping the best-scoring formulation, and truncated to `FAQ_MAX_RESULTATS`.

- **No ticket is created, no LLM generation runs, the guard is never called.** The page *shows* what a human already validated; it does not *serve* anything unreviewed. That is why it can skip the guard where the CANONIQUE branch cannot.
- **No domain filtering** — a deliberate departure from `check_domain_read`, and the only possible one: a regular user belongs to no group, so filtering by `user_domaines` would return nothing. What is exposed was validated at least `SEUIL_CANONIQUE` times by a human *in order to be served as-is*.
- The displayed question is the point's `question_indexee` — the formulation the user actually matched, not `Ticket.question`. Same reasoning as the guard: a response has one point per validated formulation.
- The cosine score **orders the results but never leaves the API**: it is meaningless to an end user and invites false readings.
- **Two tiers.** `resultats` clears `FAQ_SEUIL_PERTINENCE`; `incertains` clears only `FAQ_SEUIL_INCERTAIN` and is returned **solely when `resultats` is empty** — a hint, not an answer. Do not "fix" a missed match by lowering `FAQ_SEUIL_PERTINENCE`: measured 2026-09-11, the sub-threshold band interleaves true and false positives with no separating value (`hauteur fruit` → 0.6706, correct; an unrelated demand → 0.7110, wrong). The false positive outscores the true one, so no threshold separates them — hence two tiers rather than a moved threshold.
- **Measured 2026-09-12** by `scripts/test_faq_campagne.py` (34 cases, 34 embeddings, zero LLM): **zero invariant violation** — no non-canonical answer surfaced in either tier, `incertains` never returned alongside `resultats`, nothing below `FAQ_SEUIL_PERTINENCE` served. The campaign runs a second pass with `SEUIL_LEXICAL_PAR_TERME = 0` from the same cached embeddings: the lexical door changes **3 cases out of 34, all inside `incertains`**, never `resultats` in either direction. That is the "lexical-only candidate is a hint, never an answer" rule verified by measurement rather than by reading the code. Same point, both contracts: `COMMENT FAIT ON UN SERVICE FAIT ???` at cosine 0.6343 is served CANONIQUE by the pipeline (judge approved) and returned as a *hint* by the FAQ (no judge). Raw: `scripts/resultats_faq_campagne.json`, report § 15.7.
- `a_relire` answers **are** filtered out (`Reponse.a_relire.is_(False)`), which is the *opposite* of the rule that held until 2026-09-17 ("the pipeline keeps serving them, so the FAQ must say the same thing"). The pipeline still proposes them — but in SUGGESTION, to a reviewer. This page has no reviewer, so showing an answer a judge suspects of being contradicted *is* serving it unreviewed. It reappears the moment the flag is lifted. The clause is the **SQL mirror of `peut_servir_sans_revue`** (`services/question_pipeline.py`); the two must agree, and a test in `tests/test_faq.py` compares them on the same flag set — a divergence would raise nothing, it would just reopen on one side the door the other closed.
- Cost: one Albert embedding per search. Hence explicit submit only (never search-as-you-type), a `staleTime` on the React Query cache, and `FAQ_RATE_LIMIT_PAR_MINUTE` per user via `core/rate_limit.py` — checked *before* the Albert call. That limiter is **fail-open**, unlike login's fail-closed `_check_login_rate`: a read-only page must not break on a Valkey blip.

### Document update pipeline (`workers/document_update.py` → `workers/reverification.py`)
Replacing a document's file keeps its `doc_id` and creates version N+1; the outgoing version is archived and stays downloadable. The update job itself no longer decides anything about VALIDÉE answers — it writes the new version, flags the affected answers `a_relire` / `ANALYSE_EN_COURS` **in the same transaction as the version switch** (closing the race window), and enqueues `reverification_job` on `queue_questions`.

The verdict is a four-stage funnel, cheap to expensive, and **only the last stage decides**:
1. **`unites_de_changement`** (`services/diff.py`, re-exported by `services/obsolescence.py`) — aligned paragraph diff, `SequenceMatcher(autojunk=False)`, producing `Unite(sens, avant, apres)` with rewrites paired before/after. An anti-reflow pass (`_requalifier`) drops units whose normalised text already exists on the other side. **Zero units ⇒ nothing is enqueued at all** — that is what pure reformatting produces.
2. **`rassembler_candidates`** (`services/reverification_candidates.py`) — answers citing the document, plus same-domain answers whose *question* is close to a change unit (deliberately dense-only — recall matters more than precision here, and a paragraph↔question lexical match is dominated by domain-common words; response points carry `reponse_id` but no `doc_id`).
3. **`unites_pertinentes`** (`services/reverification_scoring.py`) — one `rerank` call per answer. `rerank` returns `[]` *without raising* on an unexpected API shape, so the function returns `(unites, fiable)`; `fiable=False` sends the answer to the LLM anyway. Never read `[]` as "nothing relevant".
4. **`juger`** (`services/reverification_scoring.py`) — one `chat` call, `temperature=0`, strict JSON, shown the AVANT/APRÈS diff (not the document). Returns `CONTREDITE | INTACTE | INCERTAIN`. Unparseable output ⇒ `INCERTAIN`, **never `INTACTE`**. The prompt explicitly forbids drafting a correction.

Application rules (`decider`), all via `fermeture_copies` so copies are never left indexed:
- citing answer + `CONTREDITE` → `retirer_du_service` (`CONTREDITE_PAR_MAJ`), removed from Qdrant
- **non-citing answer + `CONTREDITE` → `a_relire` (`CONTREDITE_PROBABLE`) only — never `obsolete`.** This cap is the central guard rail: the link is only vector similarity between a paragraph and a question.
- `INTACTE` → `lever_a_relire`, but **only if `a_relire_doc_id == doc_id` *and* `a_relire_version == version`** — only lift the flag you raised yourself. The `doc_id` half stops this job erasing *another document's* signal; the version half stops it erasing *another pass's* signal on the same document, which did not instruct the same question. Measured 2026-09-18 (campaign T5, phases 11–12): the confrontation at doc B v1 flagged a general canonical `CONTREDITE_PROBABLE` — *"incomplete, it omits the missions-abroad exception"* — and the reverification of doc B v2, which judges only the 45 € → 60 € diff, ruled it `INTACTE` **correctly** and cleared a motive it had never examined. The answer returned to `canonique=True, a_relire=False`: servable unreviewed while still omitting the exception. Not an invariant breach — the guard still stands between it and a specific question — but C1's door reopened by side effect. The version check is free because **both callers post `RAISON_ANALYSE` with the version they later pass to `decider`**, so the transient state still resolves; that, not the lifting itself, is the risk the fix carries, and it is what `phase_drapeau` measures (3 rounds at v4/v5/v6, `0827d395 → INTACTE` every time with the v1 flag intact, 0 answers frozen in `ANALYSE_EN_COURS`). A flag from another pass now waits for a human (`confirmer_actualite`), the only thing that actually instructed it.
- `INCERTAIN` / Albert failure / budget exhausted / >40 units → `a_relire` with an explicit reason, always still served

`indices_modifies` is **demoted**: it no longer condemns anything, it marks answers as *prioritaires* whose units bypass the rerank filter. `ANALYSE_EN_COURS` is the only transient state and the worker is obliged to resolve it (three safety nets: per-answer fallback, final `rabattre`, `on_failure`). EN_ATTENTE answers are still perimed + requeued through the RAG, but only when there is at least one change unit.

**Read [`Docs/technique/mise-a-jour-documents.md`](Docs/technique/mise-a-jour-documents.md) before touching this pipeline, `clean_text`, or the chunking parameters** — it documents the two-phase preview/confirm flow, the mandatory scroll-before-delete ordering, why units travel through `DocumentVersion.changements` rather than the broker, and why changing the extraction pipeline would drown every future diff in phantom units.

### Frontend (`frontend/`)
- **React 19** + **Vite 8** + **TypeScript 6** + **Tailwind CSS v4**
- **React Query v5** for server state; **React Router v7** for routing
- **Linter**: oxlint (not ESLint)
- API calls in `src/lib/api/` (split per domain: `tickets`, `reponses`, `documents`, `admin`, `stats`…), proxied by Vite to backend at `/api/v1`
- Pages under `src/pages/`: `backoffice/` (Dashboard, TicketsList, TicketDetail, SavedAnswers, KnowledgeBase, TicketTracking), `user/` (UserDashboard, NewTicket, UserTicketDetail, SuggestionBox), `admin/` (Groups, SiteConfig, AdminDashboard)
- Types in `src/types/` (`tickets.ts`, `reponses.ts`, `documents.ts`, `notifications.ts`, `index.ts`)
- Realtime: one SSE stream (`useSSE`) invalidates React Query caches — **never `networkidle` in browser automation**, the stream keeps the network busy forever

---

## Key Configuration

Backend `.env` must define:
- `ALBERT_API_KEY` — required for embeddings, LLM, and reranker
- `ALBERT_GARDE_MODEL_NAME` — the guard's own model; empty ⇒ falls back to `ALBERT_LLM_MODEL_NAME`. Albert's two daily quotas (1 280 000 input tokens **and** 1 000 requests) are attached to the **model**, not to the key or the account, so sharing one model lets generation calls drain the judge's counter and produce silent refusals. Read at call time, so a bench can switch judges by env var without editing a `.py` (which would trigger the `watchmedo` restart and kill a running pass).
- `ALBERT_CONTEXTE_MODEL_NAME` — the contextualiser's model; empty ⇒ falls back to `ALBERT_TAG_MODEL_NAME`, whose counter is already separate from generation. Same reasoning as `ALBERT_GARDE_MODEL_NAME`, and it matters more here: an ingestion spends one call per batch of 5 chunks, so a 578-chunk corpus is ~130 requests against a 1,000/day quota.
- `CONTEXTUALISATION_ACTIVE` (true) — the kill switch. `false` restores exactly the pre-contextualisation behaviour with **no** extra Albert call, and desindexes nothing: points already written keep their `contexte` and `texte_indexe` keeps recomposing it.
- `SEUIL_LEXICAL_PAR_TERME` (1.0) — the **lexical door** of the recall stage. A candidate is examined if its cosine clears the threshold **OR** its per-term BM25 clears this one. **You do not threshold the fusion, you threshold each signal on its own scale**: no fusion score is absolute — RRF depends only on rank (first of a useless batch scores like first of a perfect one), and distribution-based fusion normalises *per query*. RRF is used for **ordering only**.
  - This door is what makes BM25 worth having: an acronym, an article reference or a proper noun the embedding model doesn't know has a mediocre cosine and a perfect word overlap. A blended score (cosine + capped bonus) structurally cannot surface those — it was tried and removed for exactly that reason.
  - **Per term, not raw**: a BM25 score is a sum over query terms, so a long question scores higher mechanically. Measured 2026-09-11: raw 2.17 / 3.42 / 4.41, per term 1.08 / 1.14 / 1.47.
  - **`0` closes the lexical door** and restores the exact pre-BM25 behaviour — the escape hatch if a calibration goes wrong.
  - ⚠️ **Recalibrate as the corpus grows**: Qdrant's IDF scales with log(N), so the whole scale shifts. The default was measured on 24 points.
  - This stage is a **recall** filter, not a safety one. Widening it costs judge calls, not safety — the guard decides what may be served unreviewed. `garde_decisions` records both signals (`score_cosinus`, `score_lexical`) so you can read back *which door* a candidate came through.
  - **The mirror-fill is load-bearing** (`_completer_scores` in `search.py`). A point outside one branch's top-k would otherwise inherit `0.0` on that branch. Missing the dense direction makes BM25 useless (found, then dropped by the threshold); missing the lexical direction was measured to flip ranking — `Combien mesure une poire` beat `Combien fait une pomme en hauteur ?` for `combien mesure une pomme ?`. Two extra Qdrant queries, zero Albert calls.
  - **The FAQ has no judge**, so a candidate that passed by the lexical door alone lands in `incertains`, never in `resultats`: nothing there can confirm that a word overlap is worth an answer.
- `SEUIL_COSINUS` — **the CANONIQUE door, not a pre-guard filter** (changed 2026-09-18): the guard is called on every candidate still entitled to serve unreviewed, and this threshold decides whether its OUI yields CANONIQUE or falls back to SUGGESTION. Not a safety control — the guard decides what is safe to serve. The calibration history below is still valid, since it measured which reformulations deserve to be *served* at each level; what changed is that candidates below the threshold are now judged too, and a refusal sends them to RAG. `SEUIL_SUGGESTION` is derived in code as `SEUIL_COSINUS − 0.05` (module level in `services/question_pipeline.py`); the `SEUIL_SUGGESTION` and `SEUIL_CANDIDAT_CANONIQUE` keys are **commented out** in `.env` and absent from `.env.example` — they were read by nothing, do not reinstate them. More generally, `model_config = {"extra": "ignore"}` (`config.py`) means **any key not declared in `Settings` is silently ignored**: no error, no log, the code default applies. Set to **`0.80`** on 2026-09-07 (from `0.90` → `0.85` on 2026-09-05, then `0.85` → `0.80`): at `0.90` the threshold was refusing in the judge's place and discarding equivalent reformulations. At `0.80` the same 48-case campaign yields CANONIQUE 19 (vs 14), 22 judge calls (vs 15), and **still zero false positives**. **Do not lower it further**: the band [0.80, 0.85) held 5 equivalent reformulations, the band [0.75, 0.80) holds none out of 4 — genuinely different demands. The remaining false negatives are out of any *threshold's* reach — but not out of BM25's. Re-run 2026-09-12 after the `AVG_LEN`/`B` recalibration: the normalisation defect scoring 0.6343 (`COMMENT FAIT ON UN SERVICE FAIT ???` — all caps and punctuation noise wreck the embedding, the word overlap is perfect) is now **recovered through the lexical door**, judged OUI, served CANONIQUE. That is the case BM25 exists for. The judge refusal at 0.8841 still stands and is correct behaviour. Campaign totals moved from CANONIQUE 19 / RAG 17 / 22 judge calls to CANONIQUE 21 / RAG 15 / **31 judge calls**, same 36/48 conformity, **still zero false positives** — the wider recall costs judge calls, not safety, exactly as `SEUIL_LEXICAL_PAR_TERME` predicts. Raw results: `scripts/resultats_passe_a_bm25_recalibre.json` vs `scripts/resultats_passe_a_080.json`. See [`Docs/technique/rapport-test-cache-semantique.md`](Docs/technique/rapport-test-cache-semantique.md), § 12.
- `SEUIL_CANONIQUE` — validations needed to promote a response to canonical (default 3)
- `DOCUMENTS_STORAGE_PATH` — permanent file storage path
- `FAQ_MAX_RESULTATS` (5), `FAQ_SEUIL_PERTINENCE` (0.75), `FAQ_SEUIL_INCERTAIN` (0.55), `FAQ_RATE_LIMIT_PAR_MINUTE` (20, `0` disables) — the FAQ page. `FAQ_SEUIL_PERTINENCE` defaults to the value of `SEUIL_SUGGESTION` (`SEUIL_COSINUS − 0.05`): the level at which the system already considers an answer worth proposing to a human. The rate limit is what stops a handful of users draining the daily Albert embedding quota, since one search = one embedding.

---

## Domain Model Notes

- `Ticket.statut_job`: `EN_ATTENTE | EN_COURS | TERMINÉ | ÉCHOUÉ` (Celery job state)
- `Ticket.statut_ticket`: `NOUVEAU | RÉPONDU | VALIDÉ | REJETÉ` (business state)
- `Reponse.statut`: `EN_ATTENTE | VALIDÉE | REJETÉE | CORRIGÉE`
- A validator cannot validate their own ticket (`verifier_auto_validation` in `reponses.py`)
- `Reponse.reponse_source_id` points to the original response when branch is SUGGESTION; `nb_validations` is tracked on the source, not the suggestion copy
- **`source == "CANONIQUE"`** is what identifies an answer served without human review. `Reponse` itself still carries no trace of the verdict — a guard refusal produces an ordinary RAG answer indistinguishable in the DB from a no-candidate case. **The audit trail lives in `garde_decisions`** (`models/garde_decision.py`), written by `journaliser_garde` on every guard invocation: the pair judged, the score, the verdict, whether it was a typographic short-circuit, and whether the refusal was a judgement or an Albert failure. Append-only and deliberately without foreign keys, so it survives the deletion of what it describes. `verdict = true` is the row that matters — it is the only record of why something was served unreviewed.
