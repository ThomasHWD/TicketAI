# Pipeline de traitement des questions

Ce document décrit le traitement d'une question depuis sa réception jusqu'à la réponse produite. Il détail le flux, les branchements, et les décisions de conception.

**Fichiers concernés**
- `backend/app/workers/question.py` — point d'entrée Celery (`question_job`)
- `backend/app/services/question_pipeline.py` — logique métier (sans dépendance Celery)
- `backend/app/services/search.py` — recherche hybride + fusion RRF
- `backend/app/services/reranker.py` — reranking via Albert
- `backend/app/services/llm.py` — génération LLM via Albert
- `backend/app/workers/feedback.py` — réindexation après validation

---

## Vue d'ensemble

```
Question de l'utilisateur
        │
        ▼
[Étape 0] Suivi ? ──oui──► Reconstituer le fil (historique + requête enrichie)
        │
        ▼
[Étape 1] Embedding dense (Albert) + recherche hybride Qdrant (top 15)
        │
        ▼
[Étape 2] Y a-t-il une réponse VALIDÉE avec score ≥ seuil ?
        │
        ├─── oui + canonique + score ≥ SEUIL_COSINUS ──► CANONIQUE (servie sans revue)
        │
        ├─── oui (autre cas) ──────────────────────────► SUGGESTION (revue humaine)
        │
        └─── non
              │
              ▼
        [Étape 3] Reranking (Albert, top 5)
              │
              ▼
        [Étape 4] Génération LLM (Albert, temperature=0.1)
              │
              ▼
        [Étape 5] Sauvegarde PostgreSQL + chunks cités
              │
              ▼
             RAG (revue humaine obligatoire)
```

---

## Seuils de décision

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SEUIL_COSINUS` | 0.90 | Score minimum pour déclencher CANONIQUE ou SUGGESTION |
| `SEUIL_SUGGESTION` | `SEUIL_COSINUS − 0.05` = 0.85 | Score minimum pour la branche SUGGESTION |
| `SEUIL_CANONIQUE` | 3 | Nombre de validations pour promouvoir une réponse en canonique |

Ces valeurs viennent de `.env` via `app/config.py`. `SEUIL_COSINUS` a été calibré sur un golden set — ne pas le modifier sans relancer `scripts/calibrate_threshold.py`.

---

## Étape 1 — Recherche hybride

```python
chunks = search_hybrid(question, domaine, top_k=15)
```

**Deux requêtes Qdrant en parallèle :**
1. Recherche **dense** (vecteur 1024d BGE-M3, cosinus)
2. Recherche **sparse** (vecteurs BGE-M3 sparse, BM25-like)

**Fusion manuelle RRF** (`k=60`) :

```
score_rrf(point) = Σ  1 / (k + rang_dans_liste)
```

Le score cosinus brut de la recherche dense est conservé dans `score_cosinus` pour les décisions de seuil. Le score RRF sert uniquement au tri final.

> **Pourquoi RRF manuel ?** Le Prefetch+Fusion natif de Qdrant 1.18 est buggé avec des vecteurs 1024d — comportement silencieusement incorrect. RRF manuel produit un résultat identique à ce qu'on attendrait du natif.

> **Note sur le sparse :** Albert ne génère pas de vecteurs sparse. `embed_texts` retourne `{"dense": [...], "sparse": {"indices": [], "values": []}}`. La recherche sparse est donc actuellement inopérante — elle ne remonte rien et n'impacte pas les résultats. La plomberie est en place pour quand Albert exposera les vecteurs sparse BGE-M3.

**Filtre domaine strict :** chaque requête Qdrant filtre par `domaine` (`IT`, `RH`, `JURIDIQUE`). Aucune fuite inter-domaine n'est possible.

---

## Étape 2 — Branche CANONIQUE ou SUGGESTION

La fonction `trouver_reponse_reutilisable` parcourt les 15 chunks retournés et cherche si l'un d'eux porte un `reponse_id` (lien vers une réponse validée, inscrit lors du feedback) **avec un score cosinus ≥ `SEUIL_SUGGESTION`**.

Si plusieurs réponses validées matchent, on choisit de manière déterministe : `canonique` d'abord, puis `nb_validations`, puis meilleur score, puis UUID.

**Conditions pour CANONIQUE** (servie sans revue humaine) :
- réponse trouvée avec `reponse.canonique == True`
- `score_cosinus >= SEUIL_COSINUS`
- question **brute** (pas une question contextuelle de suivi — voir ci-dessous)

**Conditions pour SUGGESTION** (revue humaine requise) :
- réponse trouvée avec `reponse.statut == "VALIDÉE"` et `obsolete == False`
- mais au moins une condition CANONIQUE non remplie : score en dessous de `SEUIL_COSINUS`, ou réponse pas encore canonique, ou contexte de suivi

Dans les deux cas, `reponse_source_id` pointe vers la réponse originale. Pour SUGGESTION, `nb_validations` est suivi sur la source, pas sur la copie.

---

## Étape 3 — Reranking

Si aucune réponse réutilisable n'a été trouvée, les 15 chunks passent au reranker Albert (cross-encoder) qui les reclasse par pertinence sémantique vis-à-vis de la question. On garde les **top 5**.

```python
chunks_rerankes = rerank(requete_recherche, chunks_rag, top_k=5)
```

Le reranker retourne un `relevance_score` par chunk (`rerank_score` dans le code). En cas de réponse inattendue de l'API, `rerank` retourne `[]` sans lever d'exception.

---

## Étape 4 — Génération LLM

```python
reponse_texte, hors_domaine = generate(question, chunks_rerankes, historique=historique)
```

**Prompt système** : assistant de support interne, répond uniquement depuis le contexte, sans citer de source, en français formel, 300 mots max. Si l'information n'est pas disponible, le LLM préfixe sa réponse par `[HORS_DOMAINE]`.

**Paramètres** : `temperature=0.1`, `max_tokens=512`, `timeout=120s`.

Les chunks sont présentés triés par `rerank_score` décroissant, avec leur score en en-tête :
```
[pertinence=0.92]
...texte du chunk...
```

En cas d'échec LLM, le ticket passe en `ÉCHOUÉ` et Celery retente jusqu'à 3 fois (délai 60s).

---

## Étape 5 — Sauvegarde

- Le `Ticket` est créé (ou mis à jour si retraitement).
- La `Reponse` est créée avec `statut="EN_ATTENTE"`, `source="LLM"` (ou `"HORS_DOMAINE"`).
- Les `ReponseChunk` sont enregistrés (doc_id, chunk_index, scores) pour la traçabilité et le pipeline de révérification documentaire.
- Un événement SSE est broadcasted : `ticket_answered` sur le channel du domaine et, si connu, de l'utilisateur.

---

## Feedback — comment une réponse devient réutilisable

Après validation humaine (`statut → VALIDÉE`), `feedback_job` est déclenché. Il indexe un nouveau point Qdrant représentant cette réponse, **avec le vecteur de la question** (et non le texte de la réponse).

**Pourquoi indexer la question ?**
- Question↔question : cosinus élevé pour des questions proches → seuil facilement atteint.
- Question↔réponse : cosinus plafonné vers ~0.50, n'atteint jamais le seuil.

Le payload du point inclut `reponse_id`, ce qui permet à `trouver_reponse_reutilisable` de retrouver la réponse lors d'une future question similaire. L'identifiant du point est un UUID5 déterministe dérivé de `reponse_id` (un upsert ultérieur écrase proprement l'ancien).

Quand `nb_validations` atteint `SEUIL_CANONIQUE` (défaut : 3), la réponse passe `canonique=True`. Elle est alors servie directement sur de nouvelles questions similaires, sans revue humaine.

---

## Mode suivi (fil de conversation)

Quand un utilisateur pose une précision sur un ticket existant (`ticket_id` fourni, `retraiter=False`), le pipeline entre en mode suivi :

1. **`charger_contexte_fil`** reconstruit l'historique du ticket (alternance user/assistant) et concatène toutes les questions pour former `requete_recherche` (enrichie).
2. La recherche hybride et le reranking utilisent cette `requete_recherche` enrichie.
3. La génération LLM reçoit l'`historique` et peut résoudre les références implicites (`"et pour ça ?"`, pronoms anaphoriques…).
4. Si une réponse de suivi est validée, elle est indexée sous sa propre `question_suivi` (pas la question initiale du ticket).
5. Un match contextuel ne peut **pas** déclencher CANONIQUE (`autoriser_canonique=False`) — il sort toujours en SUGGESTION, car la contextualisation peut avoir biaisé la recherche.

---

## File Celery

Le worker tourne sur `queue_questions` (4 workers concurrents par défaut). `feedback_job` tourne sur `queue_ingestion` pour ne pas saturer la file des questions avec des opérations I/O lourdes.

```bash
celery -A app.workers.celery_app worker -Q queue_questions -c 4
celery -A app.workers.celery_app worker -Q queue_ingestion -c 2
```

Retries : 3 tentatives max, délai 60s, sur toute exception non-`TicketDisparu`. `TicketDisparu` est catché et retourne `{"statut": "IGNORÉ"}` sans retry — un ticket supprimé ne reviendra jamais.
