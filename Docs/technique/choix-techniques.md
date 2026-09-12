# Choix techniques

Ce document explique les technologies retenues pour TicketAI et les raisons de chaque choix. L'objectif n'est pas de justifier après coup, mais de garder une trace des contraintes et des arbitrages pour éviter de les refaire à chaque passage sur le code.

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend        React 19 + Vite + TypeScript + Tailwind v4 │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼──────────────────────────────┐
│  API             FastAPI (Python 3.14)                       │
│  Workers         Celery — queue_questions / queue_ingestion  │
│  Broker          Valkey (Redis-compatible)                   │
└────────┬─────────────────────┬───────────────────┬──────────┘
         │                     │                   │
┌────────▼───────┐   ┌─────────▼──────┐  ┌─────────▼────────┐
│  PostgreSQL 16 │   │  Qdrant        │  │  Albert API      │
│  état métier   │   │  vecteurs 1024d│  │  embeddings      │
│  tickets,      │   │  dense + RRF   │  │  reranker, LLM   │
│  réponses,     │   │  filtre domaine│  │  (gouvernement   │
│  documents     │   │                │  │   français)      │
└────────────────┘   └────────────────┘  └──────────────────┘
```

---

## Backend : FastAPI

**Choix** : FastAPI avec Python 3.14, SQLAlchemy (ORM), Alembic (migrations).

**Ce que ça fait**

FastAPI est le serveur HTTP qui reçoit les requêtes du frontend et les expose sous forme d'API REST. SQLAlchemy traduit les objets Python en requêtes SQL vers PostgreSQL. Alembic versionne le schéma de la base et applique les migrations lors des déploiements.

**Pourquoi FastAPI**

FastAPI est la solution naturelle pour un service Python à forte composante IA :
- support natif de l'async, ce qui compte quand chaque requête peut appeler Albert (réseau)
- validation automatique via Pydantic (les mêmes modèles servent d'entrée et de sortie)
- génération OpenAPI sans code supplémentaire, utile pour le frontend

**Pourquoi pas Flask ou Django**

Flask est trop bas niveau pour un projet de cette taille (validation manuelle, pas d'async propre). Django apporterait beaucoup d'outillage inutile : son ORM intégré, son moteur de templates, son admin — autant de couches à contourner puisque le frontend est découplé et que SQLAlchemy est retenu.

**Pourquoi SQLAlchemy + Alembic**

Le schéma évolue (versions de documents, `garde_decisions`, champs `a_relire_doc_id`…). Alembic gère les migrations de manière déclarative et reproductible. SQLAlchemy donne le contrôle fin des transactions — nécessaire pour le pipeline de mise à jour des documents, où l'archivage de l'ancienne version et le flaggage des réponses doivent se faire dans la même transaction.

---

## Workers : Celery

**Choix** : Celery avec deux files séparées.

**Ce que ça fait**

Celery est le système de tâches asynchrones. Quand l'API reçoit une question ou un document à ingérer, elle ne traite pas la demande elle-même — elle publie une tâche dans une file. Des processus workers, tournant en parallèle de l'API, consomment ces files et exécutent le travail (embedding, appels Albert, génération LLM). Le résultat est écrit en base ; le frontend est notifié via SSE.

**Pourquoi des workers asynchrones**

Ingérer un PDF et répondre à une question prennent plusieurs secondes chacun (extraction, embedding, appels Albert). Bloquer la requête HTTP pendant ce temps est inutilisable. Celery découple l'entrée de la réponse : l'API accuse réception immédiatement, le worker traite en arrière-plan, le frontend suit via SSE.

**Pourquoi deux files distinctes**

`queue_ingestion` (2 workers) et `queue_questions` (4 workers) ont des profils différents :
- l'ingestion est rare, lente, et sollicite beaucoup de mémoire (parsing PDF)
- les questions sont fréquentes, plus courtes, et la latence est visible par l'utilisateur

Séparer les files empêche une ingestion lourde de bloquer la file des questions.

---

## Broker : Valkey

**Choix** : Valkey (fork Redis open-source).

**Ce que ça fait**

Valkey est le bus de messages entre l'API et les workers. L'API y publie les tâches Celery (« traiter cette question », « ingérer ce document ») ; les workers les consomment et y publient leur avancement. Valkey sert aussi de canal de diffusion pour les événements SSE : quand un worker termine, il publie un message que l'API relaie aux clients connectés.

**Pourquoi pas Redis directement**

Redis a changé de licence en 2024 (SSPL). Valkey est le fork maintenu par la Linux Foundation, compatible API, et utilisé par défaut dans les déploiements récents. En pratique le code ne voit aucune différence : l'URL `valkey://` est interchangeable avec `redis://` pour Celery et pour les canaux SSE.

**Pourquoi pas RabbitMQ ou un broker managé**

Le projet est interne, sans exigence de durabilité forte sur les messages (un job perdu est relancé manuellement). Valkey est plus simple à opérer et suffit à la charge prévue.

---

## Base de données : PostgreSQL 16

**Choix** : PostgreSQL 16 via Docker.

**Ce que ça fait**

PostgreSQL stocke tout l'état métier du système : les tickets, les réponses, les versions de documents, les validations, les chunks cités, les décisions du garde, les utilisateurs et les groupes. C'est la source de vérité ; Qdrant ne stocke que les vecteurs et leurs métadonnées associées.

**Pourquoi PostgreSQL et pas SQLite ou MySQL**

L'état métier du système est relationnel et transactionnel par nature : un ticket a plusieurs réponses, une réponse a des chunks cités, une version de document est liée à des réponses à relire. PostgreSQL offre les transactions ACID dont le pipeline de mise à jour de documents a besoin (écriture atomique version N+1 + flaggage `a_relire`). SQLite ne supporte pas la concurrence des workers Celery. MySQL aurait fonctionné, PostgreSQL est simplement le standard de fait pour FastAPI + SQLAlchemy.

**Pas de multi-tenancy**

L'isolation est applicative (filtre par domaine), pas par schéma ou base. Le projet est mono-organisation ; ajouter un niveau d'isolation au schéma aurait compliqué les migrations sans apporter de valeur.

---

## Recherche vectorielle : Qdrant

**Choix** : Qdrant, auto-hébergé via Docker, avec vecteurs denses 1024 dimensions (BGE-M3 via Albert).

**Ce que ça fait**

Qdrant stocke deux types de points vectoriels : les chunks de documents (pour le RAG) et les questions validées associées à leurs réponses (pour le cache canonique). Quand une nouvelle question arrive, son vecteur est comparé à tous les points de la collection — Qdrant retourne les plus proches selon la similarité cosinus, filtrés par domaine. C'est ce résultat qui déclenche le branchement CANONIQUE / SUGGESTION / RAG.

**Pourquoi une base vectorielle dédiée et pas pgvector**

pgvector aurait simplifié l'infrastructure (une seule base), mais Qdrant apporte des fonctions critiques pour ce projet :
- **filtre par payload** : chaque point porte `domaine`, `reponse_id`, `score_cosinus` ; le filtre `domaine` est appliqué au niveau du moteur vectoriel, pas en post-filtrage applicatif — c'est une garantie de séparation des données entre domaines
- **mise à jour partielle des payloads** : le pipeline de feedback écrit `reponse_id` sur un point existant sans le supprimer et le recréer
- **collections multiples** : chunks de documents et réponses validées coexistent dans des collections séparées avec des schémas différents

**Pourquoi pas Pinecone, Weaviate ou Elasticsearch**

Pinecone est managé (données sortent de l'organisation, incompatible avec les contraintes de souveraineté d'un projet gouvernemental). Weaviate et Elasticsearch sont trop lourds à opérer pour une équipe réduite. Qdrant est léger, auto-hébergeable, et couvre exactement les besoins.

**Une recherche réellement hybride, l'IDF côté serveur**

Albert n'expose pas de vecteurs creux. La moitié lexicale a donc longtemps été inerte : `embed_texts` renvoyait un vecteur vide, la fusion RRF ne fusionnait qu'une seule liste, et chaque point stockait un creux vide. Elle est désormais calculée localement (`services/bm25.py`), sans dépendance de modèle ni téléchargement au runtime.

Le partage des rôles est le point à retenir : BM25 se décompose en l'**IDF**, qui dépend des statistiques du corpus et change à chaque insertion, et la **saturation TF**, qui ne dépend que du texte courant. Qdrant calcule la première (`Modifier.IDF` sur la configuration du vecteur creux) ; le client ne produit que la seconde. C'est le découpage que fait `fastembed` en interne — sans la dépendance.

Quatre conséquences opérationnelles :
- `Modifier.IDF` se fixe **à la création de la collection**. L'ajouter à une collection existante suppose de la recréer et de tout réindexer (`scripts/reinitialiser_index.py`).
- L'IDF étant en log(N), **toute l'échelle lexicale se déplace quand le corpus grossit** : `SEUIL_LEXICAL_PAR_TERME` est à recalibrer périodiquement. Sa valeur par défaut a été mesurée sur 24 points.
- **Ce partage des rôles dicte aussi quoi réindexer, et il ne faut pas se tromper d'outil.** La saturation TF est figée **à l'écriture** : changer `K1`, `B`, `AVG_LEN` ou la tokenisation invalide tout vecteur creux déjà écrit, sans qu'aucune erreur ne le signale. Le bon outil est alors `scripts/reencoder_vecteurs_creux.py --appliquer`, **pas** `reinitialiser_index.py` : seule la moitié creuse change, si bien que rejouer l'ingestion rachèterait un embedding Albert par chunk pour réécrire ce que le client calcule localement et gratuitement. L'opération est exacte parce que les deux producteurs conservent le texte encodé verbatim en payload (`contenu` pour les chunks, `question_indexee` pour les points-réponses).
- **Les indices de tokens sont des `uint32`, limite dure du protocole** (`points.proto:130`, `repeated uint32 indices`). `xxh32` n'est donc pas un choix réglable — un hachage plus large ne peut pas être transmis. Les collisions fusionnent des fréquences documentaires et déflatent légèrement l'IDF ; à cette taille de corpus, négligeable.

**`AVG_LEN` et `B` vont par paire, et leur valeur vient d'une mesure.** Le corpus est bimodal : 578 chunks de documents (moyenne 95,6 tokens BM25, CV 0,24) et 40 points-réponses indexés sous une question (moyenne 4,4), qui partagent une collection, un `avgdl` et un top-k creux. La normalisation par la longueur n'agit donc presque pas *à l'intérieur* de chaque population et massivement **entre** les deux. `AVG_LEN` valait 40 — la moitié de la moyenne réelle des documents — ce qui donnait aux questions un avantage structurel de 2,44×. Les deux constantes sont désormais choisies ensemble sous une contrainte : poser `AVG_LEN` sur l'`avgdl` mesuré **sans déplacer l'échelle des questions**, puisque c'est elle que seuille `SEUIL_LEXICAL_PAR_TERME`. `AVG_LEN = 96`, `B = 0,70` → un chunk moyen pèse 1,0, l'écart tombe à 1,56×, le seuil calibré ne bouge pas. Mesure et résolution : `scripts/mesurer_longueurs.py`, § 15 du rapport.

**Le score lexical est planché à deux termes.** `SEUIL_LEXICAL_PAR_TERME` divise la somme BM25 par le nombre de termes de la requête ; à un seul terme le diviseur vaut 1 et la normalisation ne fait plus rien — n'importe quel mot présent dans moins de la moitié du corpus ouvrait alors la porte lexicale, et chaque ouverture coûte un appel au juge. D'où `DIVISEUR_MINIMAL = 2` (`services/search.py`). Aucun effet au-delà d'un terme, donc aucun effet sur les seuils calibrés.

**La tokenisation française est la partie risquée, pas la formule.** Élision retirée **par position** et non par appartenance — filtrer le jeu de lettres `l d j n s t c m` partout supprimait aussi « disque **C** », « permis **C** », « vitamine **D** » — sur les deux apostrophes, U+0027 **et** U+2019, cette dernière étant celle que produisent les traitements de texte d'où viennent les documents ingérés. Puis repli des diacritiques, mots-outils, radicalisation Snowball (`snowballstemmer`, l'implémentation de référence — rien ici n'est un algorithme maison).

Le score de fusion, lui, ne sert **qu'à l'ordonnancement**. Aucun score RRF n'est absolu — il ne dépend que du rang, et le premier d'un lot sans intérêt vaut autant que le premier d'un lot parfait. Les décisions se prennent donc sur chaque signal pris séparément, sur sa propre échelle : cosinus **ou** BM25 par terme.

**Quand BM25 sert, et quand il ne sert pas.** Sur des reformulations en langage naturel il n'apporte rien : c'est le travail de l'embedding, et il le fait bien. Mesuré sur 48 cas au 11/09, la porte lexicale y consommait 29 % du budget du juge pour un gain net d'un cas. Sur des termes hors distribution du modèle — référence d'article, nom propre, valeur exacte — elle rattrape **7 requêtes sur 7** que le dense perdait entièrement, à des cosinus de 0,34 à 0,61. BM25 est donc utile *à la condition* que le corpus contienne ce vocabulaire ; sur un corpus purement rédactionnel, le bon réglage serait `SEUIL_LEXICAL_PAR_TERME = 0`. Les deux mesures et leur réconciliation : § 14.2 de [`rapport-test-cache-semantique.md`](rapport-test-cache-semantique.md).

Campagne rejouée le 12/09 après recalibrage d'`AVG_LEN`/`B` : CANONIQUE 19 → **21**, appels au juge 22 → **31**, même conformité 36/48, et **toujours zéro faux positif**. Le rendement de la porte s'améliore sans que la sûreté bouge — elle coûte des appels au juge, pas de la sûreté, ce qui est exactement sa promesse. Le cas emblématique, « COMMENT FAIT ON UN SERVICE FAIT ??? » à un cosinus de 0,6343 (majuscules et ponctuation détruisent l'embedding, le recouvrement lexical est parfait), était décrit comme hors de portée de tout *seuil* : il l'est toujours, mais plus de BM25. Détail : § 15.

**Côté FAQ, la porte ne déplace que des pistes.** Campagne dédiée (`scripts/test_faq_campagne.py`, 34 cas) : zéro violation d'invariant, et les 3 seuls cas que la porte lexicale change restent dans le rang `incertains` — jamais dans `resultats`. C'est la règle de `services/faq.py` — sans juge pour confirmer qu'un recouvrement de mots vaut une réponse, un candidat entré par les seuls mots se propose sans s'affirmer — désormais **mesurée** et plus seulement énoncée. § 15.7.

---

## IA : Albert API

**Choix** : Albert API (gouvernement français) pour les trois usages IA : embeddings, reranker, LLM.

**Ce que ça fait**

Albert est l'API qui fait tourner les modèles de langage. Elle intervient à trois moments du pipeline :
- **à l'ingestion** : transformer chaque chunk de document en vecteur dense (embedding)
- **à la question** : re-vectoriser la question, reranker les chunks candidats par pertinence, puis générer la réponse en langage naturel
- **au garde** : juger si deux questions demandent la même chose (une seule question LLM binaire, OUI/NON)

**Pourquoi Albert**

Albert est l'API IA mise à disposition des administrations françaises. Pour un projet interne à une organisation publique, c'est la solution naturelle — contrainte de souveraineté, données qui ne quittent pas l'infrastructure publique, pas de coûts d'usage externe.

**Trois modèles distincts**

Albert expose plusieurs modèles sur le même endpoint. Le projet en utilise trois :
- **modèle d'embedding** (`ALBERT_EMBEDDING_MODEL_NAME`) — BGE-M3 1024d, utilisé à l'ingestion et à la recherche
- **modèle de reranking** (`ALBERT_RERANKER_MODEL_NAME`) — pour ordonner les chunks avant la génération
- **modèle LLM** (`ALBERT_LLM_MODEL_NAME`) — génération des réponses
- **modèle du garde** (`ALBERT_GARDE_MODEL_NAME`) — juge LLM du cache canonique, intentionnellement séparé

**Pourquoi le garde a son propre modèle**

Albert limite les appels par modèle (1 280 000 tokens/jour **et** 1 000 requêtes/jour — ce second compteur est le plus contraignant sur de courts prompts). Partager le modèle de génération avec le garde ferait drainer le compteur du juge par les appels de génération, produisant des refus silencieux du garde. La variable `ALBERT_GARDE_MODEL_NAME` découple les deux compteurs.

**Contrainte de quota**

Les 1 000 requêtes/jour sont attachées au modèle, pas à la clé API. Changer de clé ne débloque rien ; changer de modèle change le compteur. C'est un point structurant : toute campagne de test ou calibration sur des données réelles consomme ce quota, et les scripts utilitaires (`calibrate_threshold.py`, `test_garde_reel.py`) doivent être utilisés avec parcimonie.

---

## Frontend : React + Vite + TypeScript + Tailwind CSS v4

**Ce que ça fait**

React produit l'interface utilisateur : l'espace employé (soumettre une question, suivre son ticket) et le backoffice (valider, corriger, gérer les documents). Vite est l'outil de build et le serveur de développement. TypeScript type les échanges avec l'API. Tailwind fournit les classes CSS utilitaires. React Query gère le cache des données serveur et les actualisations déclenchées par SSE.

**Pourquoi React 19**

React est le framework retenu pour l'écosystème disponible (React Query, React Router) et la familiarité de l'équipe. La v19 apporte les Server Components, non utilisés ici, mais les autres améliorations (actions, `use()`) simplifient les patterns de chargement de données.

**Pourquoi Vite**

Vite remplace Create React App, abandonné. Démarrage à chaud en millisecondes, proxy vers le backend configurable directement dans `vite.config.ts`, build rapide.

**Pourquoi TypeScript**

Le backend expose une API avec des types précis (statuts, branches, rôles). TypeScript permet de les reproduire côté frontend (`src/types/`) et de détecter à la compilation les désynchronisations entre l'API et l'UI.

**Pourquoi Tailwind CSS v4**

Tailwind v4 remplace la configuration `tailwind.config.js` par un fichier CSS natif (`@theme`). Pour un projet sans designer dédié, les classes utilitaires permettent d'itérer rapidement sans alterner entre fichiers CSS et composants. oxlint est le linter retenu (plus rapide que ESLint, sufficient pour ce projet).

**React Query v5 pour l'état serveur**

L'UI est majoritairement du state serveur (listes de tickets, réponses, documents). React Query gère le cache, la revalidation, et les mutations sans Redux ou Zustand. Les invalidations de cache sont déclenchées par le flux SSE (`useSSE`) — quand un worker pousse un événement, le cache est invalidé et la liste se rafraîchit sans rechargement.

**SSE plutôt que WebSockets**

Les mises à jour temps réel sont unidirectionnelles (serveur → client). SSE couvre ce besoin avec une implémentation simple côté serveur (endpoint HTTP standard, pas de bibliothèque dédiée) et une connexion persistante qui traverse les proxies sans configuration spéciale. WebSockets auraient apporté la bidirectionnalité, inutile ici.

---

## Infrastructure locale : Docker Compose

**Choix** : Docker Compose pour PostgreSQL, Qdrant et Valkey.

**Ce que ça fait**

Docker Compose démarre les trois services d'infrastructure (PostgreSQL, Qdrant, Valkey) dans des conteneurs isolés avec un seul `make up`. Le backend et les workers tournent en dehors des conteneurs (dans le venv Python), mais s'y connectent via les ports exposés.

**Pourquoi Docker Compose et pas des services locaux**

Les trois services ont des contraintes de version (PostgreSQL 16 pour certaines fonctions JSON, Qdrant pour la compatibilité des payloads). Docker Compose garantit que chaque développeur tourne exactement la même version, sans conflit avec d'autres projets sur la même machine.

**Limitation connue : `env_file` figé**

`env_file:` dans `docker-compose.yml` est lu à la création du conteneur, pas au démarrage. Les valeurs chargées au moment de `docker compose up` sont figées — une modification ultérieure de `.env` n'atteint pas le conteneur en cours d'exécution. Il faut recréer les conteneurs (`docker compose up --force-recreate`) et vérifier depuis l'intérieur qu'une clé a bien changé. Ce comportement est documenté dans [Onboarding développeur](../onboarding-dev.md).

**Limitation connue : l'état d'un conteneur n'est pas l'état de son image**

Même piège, seconde forme. Un `pip install` lancé *dans* un conteneur survit à un `restart` mais disparaît à la recréation suivante, et `docker compose ps` affiche malgré tout tout le monde *running*. Ce qui trahit la situation, c'est `RunningFor` : s'il est antérieur au `up` que l'on vient de lancer, Compose n'a rien recréé parce que l'image n'a pas changé.

La perte de `snowballstemmer` par ce chemin ne dégrade pas le système, elle l'arrête : `embed_texts` calcule le vecteur creux **avant** l'appel Albert, donc tout embedding lève. Après toute modification de `requirements.txt`, il faut donc `make dev-build && make dev`, puis vérifier l'import depuis l'intérieur de chacun des quatre conteneurs Python.

⚠️ Ne jamais utiliser `make clean` pour cela : la cible est `down --rmi all --volumes`, elle détruit les volumes Qdrant et PostgreSQL.
