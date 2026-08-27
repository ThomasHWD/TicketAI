# TicketAI — Présentation du projet

TicketAI est un helpdesk interne alimenté par l'IA qui répond automatiquement aux questions des employés (RH, IT, Juridique) en s'appuyant sur une base de connaissances validée par des experts métier.

---

## Contexte et objectif

Les employés posent leurs questions procédurales ou réglementaires via un portail web. Le système tente d'y répondre automatiquement en cherchant dans les documents internes et les réponses déjà validées. Si la confiance est suffisante, la réponse est servie instantanément ; sinon, elle est soumise à un expert du domaine pour validation.

Chaque validation renforce la base : au bout de trois validations, une réponse devient **canonique** et est servie directement, sans intervention humaine, pour toutes les questions similaires à venir.

---

## Utilisateurs

| Rôle | Ce qu'ils font |
|---|---|
| **Employé** | Soumet une question dans son domaine (RH, IT, Juridique) et consulte les réponses depuis l'espace utilisateur |
| **Validateur** (expert métier) | Valide, corrige ou rejette les réponses générées par l'IA depuis le backoffice ; gère la base documentaire |
| **Admin** | Configure les seuils, les groupes, les domaines et surveille la santé de la plateforme |

---

## Les trois branches de réponse

```
Question de l'employé
        │
        ▼
  Recherche hybride (dense + sparse, Qdrant)
        │
        ├── Score élevé + réponse canonique ──► CANONIQUE   (instantané, sans revue)
        │
        ├── Score élevé + réponse validée ───► SUGGESTION   (revue humaine requise)
        │
        └── Pas de réponse réutilisable ──────► RAG          (génération LLM, revue humaine requise)
```

**CANONIQUE** — la question est très proche d'une question déjà traitée et sa réponse a été validée suffisamment de fois. Aucune intervention humaine.

**SUGGESTION** — une réponse validée existe mais la confiance n'est pas assez haute pour la servir sans relecture. L'expert confirme ou corrige.

**RAG** — aucune réponse réutilisable. Le système reranke les chunks de documents pertinents et génère une réponse via LLM (Albert API). Elle est toujours soumise à validation avant d'être publiée.

---

## Boucle de feedback

```
Validation humaine
        │
        ▼
Réindexation dans Qdrant (vecteur de la question → payload reponse_id)
        │
        ▼
nb_validations atteint le seuil ──► réponse promue CANONIQUE
```

La base de connaissances s'enrichit naturellement au fil des validations, sans action manuelle.

---

## Stack technique

| Couche | Technologie |
|---|---|
| **Backend** | FastAPI (Python 3.14), SQLAlchemy, Alembic |
| **Workers** | Celery (files `queue_questions` et `queue_ingestion`) |
| **Broker** | Valkey (Redis-compatible) |
| **Base de données** | PostgreSQL 16 |
| **Recherche vectorielle** | Qdrant (vecteurs denses 1024d BGE-M3, fusion RRF manuelle) |
| **IA** | Albert API (gouvernement français) — embeddings, reranker, LLM |
| **Frontend** | React 19, Vite, TypeScript, Tailwind CSS v4 |
| **Infra locale** | Docker Compose (Postgres + Qdrant + Valkey) |

---

## Périmètre et contraintes

- Déploiement interne mono-organisation, sans multi-tenancy
- Interface entièrement en français (UI, prompts, documents)
- Domaines configurables par l'admin (par défaut : RH, IT, Juridique)
- Documents supportés : PDF, DOCX, TXT, MD
- Mise à jour documentaire versionnée : remplacer un document déclenche une révérification automatique des réponses existantes
- Authentification LDAP (production) ou base locale (développement)
- Mises à jour temps réel via SSE (Server-Sent Events)
- Un validateur ne peut pas valider son propre ticket

---

## Principes de conception

**L'expertise se capitalise.** Chaque validation réduit le coût de la prochaine réponse identique. Le seuil canonique est le levier central du système.

**Confiance graduelle.** Les réponses traversent une porte humaine tant que la confiance n'est pas établie. Quand elle l'est, elles passent seules.

**Incertitude explicite.** Quand le système ne peut pas répondre avec confiance, il le dit et route vers un expert — jamais de réponse silencieusement approximative.

**Propriété par domaine.** Chaque expert ne voit que les tickets de son domaine. La séparation est appliquée au niveau du filtre Qdrant, pas seulement de l'UI.
