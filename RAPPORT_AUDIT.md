# Rapport d'audit — TicketAI
**Date :** 2026-08-17  
**Auditeur :** Claude Sonnet 4.6 (architecte logiciel, expert sécurité, ingénieur QA)  
**Version auditée :** branche `dev`, commit `623e803`

---

## 1. Résumé exécutif

TicketAI est un système helpdesk RAG bien structuré, avec une logique métier soigneusement conçue (pipeline CANONIQUE / SUGGESTION / RAG, vérification des documents, workflow de validation, verrou collaboratif). Les tests sont en place (439 backend, 62 frontend, tous verts), la séparation des responsabilités est globalement respectée.

Cependant, **trois failles de sécurité significatives** exigent une correction immédiate avant tout déploiement en production : une injection LDAP potentielle sur le login, l'endpoint de configuration admin accessible sans authentification, et des credentials de service réels dans le `.env`. S'y ajoutent plusieurs problèmes de sécurité de niveau moyen et des dettes techniques ciblées.

**Score global estimé : 6,5 / 10** (en progression depuis le précédent audit 5,5/10 grâce aux avancées sur les documents et l'auto-clôture, mais des nouvelles failles ont été identifiées).

---

## 2. Diagnostic du site en direct (http://localhost:5173/)

| Vérification | Résultat | Détail |
|---|---|---|
| Frontend HTTP | ✅ 200 OK | Vite dev server répond en 7 ms |
| Asset HTML | ✅ Valide | DOCTYPE, charset, viewport corrects |
| API `/api/v1/tickets` sans auth | ✅ 401 | Protection attendue OK |
| API `/api/v1/admin/config` sans auth | ❌ **200 OK** | **Bug critique — données exposées sans token** |
| Tests frontend (Vitest) | ✅ 62/62 | Tous passés |
| Tests backend (pytest) | ✅ 439/439 | Tous passés |
| Couverture backend | ⚠️ 75% | `auto_cloture.py` 0 %, `qdrant.py` 33 % |

---

## 3. Failles de sécurité

### 🔴 CRITIQUE

#### SEC-01 — Injection LDAP sur le formulaire de login
**Fichier :** `backend/app/services/ldap_auth.py:69`

```python
# Code actuel — vulnérable
def _search_filter(username: str) -> str:
    return settings.ldap_user_search_filter.format(username=username)
```

Le `username` fourni par l'utilisateur est injecté directement dans le filtre LDAP via `str.format()`. Un attaquant peut soumettre `*)(|(cn=*)` pour modifier la sémantique du filtre et contourner l'authentification ou extraire des informations de l'annuaire.

**Correction :**
```python
from ldap3.utils.conv import escape_filter_chars

def _search_filter(username: str) -> str:
    safe = escape_filter_chars(username)
    return settings.ldap_user_search_filter.format(username=safe)
```

---

#### SEC-02 — `GET /api/v1/admin/config` accessible sans authentification
**Fichier :** `backend/app/api/v1/admin/health.py:317`

```python
# Code actuel — aucune dépendance d'auth
@router.get("/config")
def get_config(db: DB):
    """Retourne toute la configuration du site (accessible à tout utilisateur authentifié)."""
```

Malgré le commentaire, l'endpoint est accessible sans aucun token. Confirmé par `curl http://localhost:8000/api/v1/admin/config` → HTTP 200. Même si le contenu actuel est anodin (bannière), toute clé future ajoutée à `SiteConfig` sera exposée publiquement.

**Correction :**
```python
@router.get("/config")
def get_config(current_user: CurrentUser, db: DB):
```

---

#### SEC-03 — Credentials de production dans le `.env`
**Fichier :** `backend/.env:20,46`

```
ALBERT_API_KEY=sk-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
LDAP_BIND_PASSWORD=*O9eLTiBWwIFY8Petr7ix-
```

Le fichier `.env` contient la clé API Albert (token JWT décodable) et le mot de passe du compte de service LDAP de production. Ces credentials doivent être **révoqués/changés immédiatement** si ce fichier a jamais été partagé, versionné ou accessible à des tiers.

**Action requise :** rotation des credentials + audit de l'historique git de ce fichier.

---

### 🟠 ÉLEVÉ

#### SEC-04 — JWT secret trop faible + durée trop longue
**Fichier :** `backend/.env:38-40`

```
JWT_SECRET_KEY=dev-secret-change-me  # Secret devinable
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480      # 8 heures
```

Un secret de 20 caractères fixes est insuffisant. Un token volé reste exploitable pendant 8 heures sans possibilité de révocation. Il n'existe pas de mécanisme de refresh token.

**Recommandations :**
- Remplacer par `openssl rand -hex 32`
- Réduire à 60 minutes maximum
- Implémenter un refresh token avec rotation

---

#### SEC-05 — Absence de middleware CORS
**Fichier :** `backend/app/main.py`

L'application FastAPI ne déclare aucun middleware `CORSMiddleware`. En production derrière un reverse proxy, cela peut soit bloquer le frontend s'il est servi depuis un domaine différent, soit ouvrir l'API à toutes les origines selon la configuration du proxy.

**Correction :**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://votre-domaine.fr"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

#### SEC-06 — TLS LDAP désactivé
**Fichier :** `backend/.env:55`, `backend/app/services/ldap_auth.py:87`

```python
tls = Tls(validate=ssl.CERT_REQUIRED if settings.ldap_tls_validate else ssl.CERT_NONE)
```
```
LDAP_TLS_VALIDATE=false
```

La validation du certificat TLS du serveur LDAP est désactivée. Une attaque MITM peut intercepter les credentials de bind (compte de service) et les mots de passe utilisateur lors du re-bind.

**Recommandation :** `LDAP_TLS_VALIDATE=true` + configurer le bundle CA approprié.

---

#### SEC-07 — Absence de rate-limiting sur `/auth/login`

Aucun mécanisme de limitation de débit sur le endpoint d'authentification. Un attaquant peut effectuer des attaques par force brute ou par dictionnaire contre les comptes LDAP sans aucune contrainte.

**Recommandation :** Ajouter `slowapi` (ou équivalent) avec une limite de 5 tentatives/minute par IP.

---

### 🟡 MOYEN

#### SEC-08 — JWT stocké dans `localStorage` (vulnérabilité XSS)
**Fichier :** `frontend/src/lib/api/client.ts:61`

```typescript
localStorage.setItem(TOKEN_KEY, res.access_token);
```

`localStorage` est accessible par tout JavaScript de la page, y compris via une injection XSS. La pratique recommandée est un cookie `HttpOnly; Secure; SameSite=Strict` géré côté serveur.

---

#### SEC-09 — `heartbeat` accessible à tous les utilisateurs authentifiés
**Fichier :** `backend/app/api/v1/tickets/manage.py:463`

```python
@router.post("/tickets/{ticket_id}/heartbeat")
async def heartbeat_ticket(ticket_id: str, current_user: CurrentUser):  # devrait être BackofficeUser
```

N'importe quel utilisateur lambda peut prolonger un verrou de ticket en devinant un UUID. Devrait être restreint aux membres backoffice.

---

#### SEC-10 — Statut job Celery sans contrôle de propriété
**Fichier :** `backend/app/api/v1/tickets/submit.py:137`

```python
@router.get("/tickets/{job_id}/status")
async def statut_ticket(job_id: str, current_user: CurrentUser):
    result = AsyncResult(job_id, app=celery_app)
```

Tout utilisateur authentifié peut interroger le résultat de n'importe quel job Celery par son ID. Bien que les UUIDs ne soient pas devinables, il manque une vérification que le job appartient à l'utilisateur courant.

---

## 4. Bugs et erreurs logiques

### BUG-01 — `ETATS_FINAUX` contient un statut inexistant (`CANONIQUE`)
**Fichier :** `backend/app/services/reponse_service.py:10`  
**Sévérité :** 🟠 Élevé

```python
ETATS_FINAUX = {"REJETÉE", "CORRIGÉE", "CANONIQUE"}
```

`CANONIQUE` n'est pas une valeur valide de `Reponse.statut`. Le statut d'une réponse canonique reste `VALIDÉE` (`canonique` étant un champ booléen séparé). Conséquence : une réponse `VALIDÉE` ne figure pas dans `ETATS_FINAUX`, donc `verifier_etat_initial()` ne la bloque pas. Un validateur peut re-valider, corriger ou rejeter une réponse déjà `VALIDÉE`.

**Correction :**
```python
ETATS_FINAUX = {"VALIDÉE", "REJETÉE", "CORRIGÉE"}
```

---

### BUG-02 — `GET /documents` non paginé — risque de surcharge
**Fichier :** `backend/app/api/v1/documents/core.py:124`  
**Sévérité :** 🟡 Moyen

```python
@router.get("/documents")
async def list_documents(...):
    """Liste des documents indexés, non paginée (filtrage côté client)."""
    docs = q.order_by(Document.updated_at.desc()).all()
```

L'endpoint charge tous les documents en mémoire. Avec des centaines de documents, la réponse peut dépasser plusieurs Mo et bloquer la boucle d'événements FastAPI.

---

### BUG-03 — `_avg_closure_time` filtre sur `Ticket.canonique` (champ non pertinent)
**Fichier :** `backend/app/api/v1/stats/dashboard.py:90`  
**Sévérité :** 🟡 Moyen

```python
def _avg_closure_time(db, start, end, domain_filters):
    result = db.query(...).filter(
        Ticket.closed_at >= start,
        ...
        Ticket.canonique.is_(False),  # ← filtre douteux
    ).scalar()
```

`Ticket.canonique` est redondant (c'est le champ sur `Reponse` qui fait foi), et le filtre `Ticket.canonique.is_(False)` exclut silencieusement certains tickets du calcul de temps moyen, faussant la statistique.

---

### BUG-04 — Déprecation Pydantic V1 non corrigée
**Fichier :** `backend/app/api/v1/suggestions.py`  
**Sévérité :** 🟢 Faible

```
PydanticDeprecatedSince20: Support for class-based `config` is deprecated
```

Un modèle Pydantic utilise encore la syntaxe `class Config` (V1). Sera une erreur en Pydantic V3.

---

## 5. Qualité du code et dette technique

### QUA-01 — Absence de lazy loading (code splitting)
**Fichier :** `frontend/src/App.tsx`

Tous les composants sont importés statiquement. Le bundle initial charge les 15+ pages (admin, backoffice, user) quel que soit le rôle de l'utilisateur. Sur des connexions lentes, le Time To Interactive sera dégradé.

**Recommandation :**
```typescript
const Dashboard = lazy(() => import('./pages/backoffice/Dashboard'));
// + <Suspense fallback={<Spinner />}> autour des <Routes>
```

---

### QUA-02 — Double pattern de gestion de session DB
**Partout dans le backend**

Deux patterns coexistent sans règle claire :
- `Depends(get_db)` (correct, utilisé dans `documents/core.py`, `admin/`)
- `SessionLocal()` manuel dans un bloc `try/finally` (utilisé dans `tickets/`, `reponses/`, `security.py`)

Le second pattern est moins testable et peut mener à des fuites de connexion si le `finally` n'est pas atteint (exception Celery, `SystemExit`).

---

### QUA-03 — `print()` omniprésent au lieu de `logging`
**Fichiers multiples**

Plus de 15 occurrences de `print()` dans le code de production (`reranker.py`, `question_pipeline.py`, `reponses/actions.py`, `qdrant.py`, etc.). `print()` est synchrone, non structuré, non filtrable par niveau, et non capturé par les outils d'observabilité.

**Recommandation :** remplacer par `import logging; logger = logging.getLogger(__name__)`.

---

### QUA-04 — `useQuery` sans `staleTime` sur `/auth/me`
**Fichier :** `frontend/src/lib/auth.tsx:56`

```typescript
const { data: freshUser } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => { /* ... */ },
    enabled: !!token,
    // staleTime absent → refetch à chaque focus de fenêtre
});
```

Sans `staleTime`, React Query revalide le profil utilisateur à chaque focus de la fenêtre. Cela génère des appels réseau inutiles.

**Recommandation :** `staleTime: 5 * 60 * 1000` (5 minutes).

---

### QUA-05 — Couverture de tests insuffisante sur les workers critiques
| Fichier | Couverture |
|---|---|
| `app/workers/auto_cloture.py` | **0 %** |
| `app/services/qdrant.py` | **33 %** |
| `app/services/admin_service.py` | **34 %** |
| `app/services/ticket_service.py` | **68 %** |

La fermeture automatique des tickets (`auto_cloture.py`) est un worker Celery Beat sans aucun test. Une régression passera totalement inaperçue.

---

## 6. Performance et optimisation

### PERF-01 — N+1 queries potentielles dans `serialize_ticket`
**Fichier :** `backend/app/services/ticket_service.py`

Sans profiling, les relations `ticket.user`, `ticket.locker`, `ticket.assignee` peuvent déclencher des queries N+1. Les endpoints de listing chargent les réponses via `selectinload(Ticket.reponses)` mais pas les autres relations.

---

### PERF-02 — SSE admin sans filtrage par domaine
**Fichier :** `backend/app/api/v1/sse.py:63`

```python
if not domaines:
    use_domain_pattern = True
    # → psubscribe("sse:domain:*") — écoute TOUS les domaines
```

Un administrateur sans groupes configurés s'abonne à tous les événements de tous les domaines via `psubscribe`. Sur une architecture multi-domaines avec fort trafic, cela surcharge inutilement la connexion SSE.

---

### PERF-03 — Bundle frontend sans chunk splitting
Aucun `build.rollupOptions.output.manualChunks` configuré dans `vite.config.ts`. Recharts (bibliothèque lourde), le code admin et le code backoffice sont tous bundlés ensemble.

---

## 7. Plan d'action priorisé

### Phase 1 — Urgence sécurité (à traiter avant tout déploiement)

| # | Action | Fichier | Effort |
|---|---|---|---|
| 1 | Corriger l'injection LDAP avec `escape_filter_chars` | `ldap_auth.py:69` | 15 min |
| 2 | Ajouter `CurrentUser` sur `GET /admin/config` | `health.py:317` | 5 min |
| 3 | Révoquer et rotater `ALBERT_API_KEY` et `LDAP_BIND_PASSWORD` | `.env` | immédiat |
| 4 | Générer un JWT secret fort (`openssl rand -hex 32`) | `.env:38` | 5 min |
| 5 | Réduire `ACCESS_TOKEN_EXPIRE_MINUTES` à 60 | `.env:40` | 5 min |
| 6 | Corriger `ETATS_FINAUX` (ajouter `VALIDÉE`, supprimer `CANONIQUE`) | `reponse_service.py:10` | 5 min |

### Phase 2 — Sécurité élevée (sprint suivant)

| # | Action | Fichier | Effort |
|---|---|---|---|
| 7 | Ajouter middleware CORS avec origines explicites | `main.py` | 30 min |
| 8 | Activer TLS LDAP (`LDAP_TLS_VALIDATE=true`) | `.env:55` | 30 min |
| 9 | Ajouter rate-limiting sur `/auth/login` (`slowapi`) | `auth.py` | 1h |
| 10 | Restreindre `/heartbeat` à `BackofficeUser` | `manage.py:463` | 5 min |
| 11 | Ajouter contrôle de propriété sur `GET /tickets/{job_id}/status` | `submit.py:137` | 30 min |

### Phase 3 — Bugs et qualité (backlog)

| # | Action | Effort |
|---|---|---|
| 12 | Corriger `_avg_closure_time` (supprimer filtre `Ticket.canonique`) | 15 min |
| 13 | Paginer `GET /documents` | 1h |
| 14 | Corriger la déprecation Pydantic V1 dans `suggestions.py` | 15 min |
| 15 | Remplacer tous les `print()` par `logging` | 2h |
| 16 | Unifier le pattern DB sur `Depends(get_db)` | 3h |
| 17 | Ajouter `staleTime` sur `useQuery` auth/me | 5 min |
| 18 | Écrire des tests pour `auto_cloture.py` (0 %) | 2h |

### Phase 4 — Performance et UX (roadmap)

| # | Action | Effort |
|---|---|---|
| 19 | Lazy loading des routes dans `App.tsx` | 2h |
| 20 | Configurer `build.rollupOptions` pour le chunking Recharts/admin | 1h |
| 21 | Migrer JWT vers cookie `HttpOnly` (nécessite backend + frontend) | 1 jour |
| 22 | Implémenter refresh token | 1-2 jours |

---

*Rapport généré le 2026-08-17 par analyse statique du code, tests automatisés et vérification du comportement en production locale.*
