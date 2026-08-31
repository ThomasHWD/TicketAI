# Pipeline de traitement des questions

Ce document décrit le traitement d'une question depuis sa réception jusqu'à la réponse produite. Il détail le flux, les branchements, et les décisions de conception.

**Fichiers concernés**
- `backend/app/workers/question.py` — point d'entrée Celery (`question_job`)
- `backend/app/services/question_pipeline.py` — logique métier (sans dépendance Celery)
- `backend/app/services/search.py` — recherche hybride + fusion RRF
- `backend/app/services/reranker.py` — reranking via Albert
- `backend/app/services/llm.py` — génération LLM via Albert
- `backend/app/services/garde_cache.py` — les deux juges qui autorisent le service sans revue
- `backend/app/workers/feedback.py` — réindexation après validation

> **Avant de toucher aux seuils ou à la condition de la branche CANONIQUE, lire
> [`garde-cache-canonique.md`](garde-cache-canonique.md)** — il documente pourquoi le score
> cosinus ne gouverne plus cette branche (AUC 0.000 mesuré) et ce qui l'a remplacé.

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
[Étape 2] Y a-t-il une réponse VALIDÉE réutilisable ?
        │
        ├── oui, canonique (score ≥ 0.70)
        │     │
        │     ▼
        │   [Garde] juge [2] pertinence  ET  juge [6] ancrage
        │     │
        │     ├── les deux approuvent ───────────────► CANONIQUE (servie sans revue)
        │     │
        │     └── un juge refuse ou échoue ──────────► on continue en étape 3
        │
        ├── oui, non canonique (score ≥ 0.85) ───────► SUGGESTION (revue humaine)
        │
        └── non ─────────────────────────────────────► on continue en étape 3
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

Un refus du garde renvoie au **RAG**, jamais en SUGGESTION : le refus signifie « cette
réponse en cache ne traite pas correctement cette question », donc la proposer au validateur
lui ferait relire une réponse connue pour être inadaptée plutôt qu'une réponse fraîche et
ciblée.

---

## Cycle de vie d'une réponse canonique

Comment une réponse naît en RAG, accumule des validations, devient canonique, puis est
servie directement — ou bloquée — sur de futures questions similaires.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 1 — Première question, aucun cache                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Employé A : « Quel est le montant de l'indemnité de télétravail ? »
       │
       ▼
  Recherche hybride Qdrant ── aucun point avec reponse_id trouvé
       │
       ▼
  Reranking → Génération LLM
       │
       ▼
  Reponse(source=LLM, statut=EN_ATTENTE)   ← en attente de validation humaine
       │
       ├── Validateur 1 → statut=VALIDÉE, nb_validations=1
       ├── Validateur 2 →                 nb_validations=2
       └── Validateur 3 →                 nb_validations=3 ≥ SEUIL_CANONIQUE
                │
                ▼
           canonique=True
           feedback_job() : indexation dans Qdrant
                │
                └── Point Qdrant :
                      vecteur = embed(question originale)   ← question, pas réponse
                      payload = { reponse_id, contenu: "15 €/mois…", domaine: RH }


╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 2 — Question suivante : paraphrase légitime                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Employé B : « Combien touche-t-on quand on travaille depuis chez soi ? »
       │
       ▼
  Recherche hybride ── point canonique retrouvé, score_cosinus = 0.71
                       (≥ SEUIL_CANDIDAT_CANONIQUE 0.70 ✓)
       │
       ▼
  trouver_reponse_reutilisable() → Reponse canonique
       │
       ▼
  Garde [2] pertinence : SUFFISANTE  (même intention, vocabulaire différent)
       │
       ▼
  Garde [6] ancrage    : ETAYEE      (15 €, 4 jours confirmés dans les extraits)
       │
       ▼
  Reponse(source=CANONIQUE, statut=VALIDÉE, garde_verdict=SUFFISANTE_ETAYEE)
       │
       └── ✓ Servie immédiatement, zéro validateur humain


╔══════════════════════════════════════════════════════════════════════════════╗
║  PHASE 3 — Question suivante : variante dangereuse                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

  Employé C : « Quel est le montant de l'indemnité pour un alternant ? »
       │
       ▼
  Recherche hybride ── point canonique retrouvé, score_cosinus = 0.84
       │
       ▼
  Garde [2] pertinence : SUFFISANTE  ← le juge ne voit pas que le doc
  │                                     ne couvre pas les alternants
  ▼
  Garde [6] ancrage    : NON_ETAYEE  ← les extraits ne mentionnent pas
  │                                     les alternants : silence = refus
  ▼
  garde_verdict=NON_ETAYEE → refus → bascule en RAG
       │
       ▼
  Reranking → Génération LLM → réponse ciblée (probablement HORS_DOMAINE)
  Reponse(source=LLM, statut=EN_ATTENTE, garde_verdict=NON_ETAYEE)
       │
       └── ✗ Validateur humain requis (trace du refus conservée pour audit)
```

**Trois invariants à retenir :**

1. Le vecteur indexé est celui de la **question**, pas de la réponse — question↔question
   donne un cosinus exploitable, question↔réponse plafonnait à ~0.50.
2. `source == "CANONIQUE"` est le seul marqueur d'un service sans relecture humaine.
   `garde_verdict` est tracé dans les deux sens (approbation *et* refus) pour l'audit.
3. Un refus du garde renvoie au **RAG**, jamais en SUGGESTION — proposer au validateur
   une réponse connue pour être inadaptée serait contre-productif.

---

## Seuils de décision

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `SEUIL_CANDIDAT_CANONIQUE` | 0.70 | Score minimum pour qu'une réponse **canonique** devienne candidate — elle passe ensuite devant les juges |
| `SEUIL_SUGGESTION` | 0.85 | Score minimum pour qu'une réponse validée **non canonique** sorte en SUGGESTION |
| `SEUIL_CANONIQUE` | 3 | Nombre de validations pour promouvoir une réponse en canonique |

Ces valeurs viennent de `.env` via `app/config.py`. Les deux planchers sont **indépendants** : l'un n'est plus dérivé de l'autre.

**Aucun score ne décide plus du service sans revue humaine.** Mesuré contre le vrai Albert, le cosinus est *non informatif* pour cette décision (AUC 0.000 sur le jeu adversarial : les cas à envoyer au RAG scorent plus haut que les cas servables). `SEUIL_COSINUS` a donc été retiré du pipeline ; il ne subsiste dans `config.py` que comme repère d'affichage pour les scripts d'éval. Ce qui autorise le service sans revue, c'est le garde — voir [`garde-cache-canonique.md`](garde-cache-canonique.md).

Le plancher canonique est **plus bas** que celui de SUGGESTION, et c'est délibéré : ces candidats passent devant deux juges avant d'être servis, alors que la branche SUGGESTION n'a aucun filtre au-delà du score. Les trois reformulations légitimes mesurées se situent entre 0.71 et 0.79 — sous 0.85, elles ne devenaient jamais candidates.

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

## Étape 2 — Candidature, garde, puis branche CANONIQUE ou SUGGESTION

### 2a — Trouver un candidat

La fonction `trouver_reponse_reutilisable` parcourt les 15 chunks retournés et cherche si l'un d'eux porte un `reponse_id` (lien vers une réponse validée, inscrit lors du feedback). Le filtre se fait en deux temps :

1. les chunks sont retenus au **plancher le plus bas des deux** (0.70), pour ne pas écarter en amont un candidat canonique légitime ;
2. après la requête SQL, chaque candidat est confronté à **son propre** plancher — 0.70 s'il est canonique, 0.85 sinon.

Si plusieurs réponses validées matchent, on choisit de manière déterministe : `canonique` d'abord, puis `nb_validations`, puis meilleur score, puis UUID. Ce départage n'a pas changé : `nb_validations` prime toujours sur le score, mais un mauvais choix est désormais rattrapé par les juges.

> **Effet de bord du plancher à 0.70, à connaître.** `canonique` étant la **première** clé de tri, une réponse canonique à 0.72 évince désormais une réponse non canonique à 0.95. Avant, la canonique à 0.72 n'était candidate d'aucune façon (plancher unique à 0.85) et c'est la non canonique qui sortait en SUGGESTION ; maintenant c'est la canonique qui passe devant les juges, et s'ils refusent, le ticket part au **RAG** au lieu de sortir en SUGGESTION.
>
> Ce n'est pas une régression de sûreté — le RAG est le repli sûr, et le candidat évincé n'aurait de toute façon pas été servi sans relecture. Mais c'est un cas que les mesures ne couvrent pas : les 8 cas du jeu adversarial portent sur 4 sujets disjoints, donc jamais deux candidats en concurrence. Le départage n'est épinglé que par un test unitaire (`tests/test_cache_over_hit.py`, « canonique prime sur le score »), pas par une mesure Albert.

### 2b — Le garde (candidats canoniques uniquement)

```python
verdict = autoriser_service_canonique(
    requete_recherche,                                    # le fil complet en mode suivi
    reponse_liee.contenu_corrige or reponse_liee.contenu,  # ce qui serait réellement servi
    chunks_garde,                                          # rerecherchés sur le fil si suivi
)
```

Deux juges LLM en **conjonction stricte**, court-circuités au premier refus :

- **[2] pertinence** — question ↔ réponse en cache. « La question ajoute-t-elle une condition, une restriction, une négation ou un cas particulier que la réponse ne couvre pas ? »
- **[6] ancrage** — question ↔ **extraits sources** ↔ réponse en cache. « La réponse est-elle entièrement étayée par les documents, pour la question exactement posée ? » Aucun texte généré n'entre dans ce chemin.

Trois précisions que le code impose et qu'il ne faut pas défaire :

- le texte jugé est `requete_recherche`, donc **le fil complet** en mode suivi — juger « Et pour un alternant ? » isolément est impossible ;
- c'est `contenu_corrige or contenu` qui est soumis, c'est-à-dire **le texte réellement servi**, pas la version d'origine ;
- en mode suivi, les extraits soumis à [6] proviennent d'une recherche refaite sur le fil (`chunks_ctx`), pas de la recherche initiale ; cette recherche est réutilisée par l'étape 3, donc elle n'est jamais payée deux fois.

Tout ce qui n'est pas une approbation explicite est un refus — panne HTTP, 429, délai dépassé, JSON illisible.

Le verdict et sa justification sont persistés dans `Reponse.garde_verdict` / `garde_justification`, **qu'il approuve ou qu'il refuse** : un blocage à tort produit une réponse RAG en apparence ordinaire, et sans cette trace il resterait invisible. C'est `source == "CANONIQUE"` qui identifie un service sans relecture humaine, pas la présence d'un verdict.

### 2c — La branche

**CANONIQUE** (servie sans revue humaine) :
- `reponse.canonique == True`, score ≥ 0.70
- **et les deux juges approuvent** (`garde_verdict = "SUFFISANTE_ETAYEE"`)

**SUGGESTION** (revue humaine requise) :
- réponse `statut == "VALIDÉE"`, `obsolete == False`, **non canonique**, score ≥ 0.85
- aucun juge n'est appelé sur cette branche : `garde_verdict` reste `NULL`

**RAG** — un juge refuse ou échoue, ou aucun candidat n'a été trouvé. Le flux tombe en étape 3 et une réponse fraîche est générée.

Pour CANONIQUE et SUGGESTION, `reponse_source_id` pointe vers la réponse originale. Pour SUGGESTION, `nb_validations` est suivi sur la source, pas sur la copie.

Détail des juges, de leurs invites et des mesures qui les justifient : [`garde-cache-canonique.md`](garde-cache-canonique.md).

---

## Étape 3 — Reranking

Si aucune réponse réutilisable n'a été trouvée — ou si le garde a refusé le candidat canonique — les 15 chunks passent au reranker Albert (cross-encoder) qui les reclasse par pertinence sémantique vis-à-vis de la question. On garde les **top 5**.

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

Quand `nb_validations` atteint `SEUIL_CANONIQUE` (défaut : 3), la réponse passe `canonique=True`. Elle devient alors **candidate** au service direct sur de nouvelles questions similaires — le garde ayant le dernier mot, question par question.

> Ces points de réponse portent un `reponse_id` et, dans leur `contenu`, le texte de la réponse. `garde_cache._extraits` les **écarte** des extraits soumis au juge d'ancrage : les laisser passer donnerait à la réponse en cache le statut de preuve d'elle-même.

---

## Mode suivi (fil de conversation)

Quand un utilisateur pose une précision sur un ticket existant (`ticket_id` fourni, `retraiter=False`), le pipeline entre en mode suivi :

1. **`charger_contexte_fil`** reconstruit l'historique du ticket (alternance user/assistant) et concatène toutes les questions pour former `requete_recherche` (enrichie).
2. La recherche hybride et le reranking utilisent cette `requete_recherche` enrichie.
3. La génération LLM reçoit l'`historique` et peut résoudre les références implicites (`"et pour ça ?"`, pronoms anaphoriques…).
4. Si une réponse de suivi est validée, elle est indexée sous sa propre `question_suivi` (pas la question initiale du ticket).
5. Une précision **peut** être servie en CANONIQUE, sans revue humaine — mais seulement si les deux juges du garde l'approuvent, et ils jugent le **fil complet** (`requete_recherche`), pas la seule précision.

> **Correction d'un écart historique.** Ce point 5 affirmait jusqu'ici qu'un match contextuel ne pouvait *pas* déclencher CANONIQUE (`autoriser_canonique=False`). C'était faux : `workers/question.py` passait `True` en dur, et une précision était donc servie sans revue **et sans aucun garde**. La doc énonçait une intention qui n'a jamais été implémentée. Le comportement décrit ci-dessus est celui du code.

---

## File Celery

Le worker tourne sur `queue_questions` (4 workers concurrents par défaut). `feedback_job` tourne sur `queue_ingestion` pour ne pas saturer la file des questions avec des opérations I/O lourdes.

```bash
celery -A app.workers.celery_app worker -Q queue_questions -c 4
celery -A app.workers.celery_app worker -Q queue_ingestion -c 2
```

Retries : 3 tentatives max, délai 60s, sur toute exception non-`TicketDisparu`. `TicketDisparu` est catché et retourne `{"statut": "IGNORÉ"}` sans retry — un ticket supprimé ne reviendra jamais.
