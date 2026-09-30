# Référence API

Tous les endpoints HTTP de TicketAI, leurs paramètres et leurs gardes d'accès.

**Base :** `/api/v1` · **Documentation interactive :** `http://localhost:8000/docs`
(Swagger, généré automatiquement).

---

## Les gardes d'accès

Chaque endpoint est protégé par l'une de ces dépendances. Comprendre les quatre suffit à
lire tout le tableau qui suit.

| Garde | Condition | Notation ci-dessous |
|---|---|---|
| `CurrentUser` | JWT valide, utilisateur existant en base | 🔵 **Authentifié** |
| `BackofficeUser` | `role == ADMIN` **ou** au moins un groupe | 🟢 **Backoffice** |
| `AdminUser` | `role == ADMIN` uniquement | 🔴 **Admin** |
| `check_domain_read` | Membre du domaine — **l'admin passe toujours** | 📖 *lecture domaine* |
| `check_domain_write` | Membre du domaine — **aucune exception, admin compris** | ✍️ *écriture domaine* |

Le détail est dans [Auth & rôles](auth-et-roles.md).

---

## Authentification

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/auth/login` | — | Login LDAP ou base. **10 tentatives/min/IP** (fail-open si Valkey est indisponible) |
| `GET` | `/auth/me` | 🔵 | Profil courant : rôle, groupes, domaines |

---

## Tickets

### Soumission et cycle de vie

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/tickets/domaines` | 🔵 | Domaines disponibles (domaines distincts des groupes) |
| `POST` | `/tickets` | 🔵 | Pose une question. Renvoie un `job_id`, le traitement est asynchrone. `400` si le domaine est invalide ou la question vide |
| `POST` | `/tickets/{id}/suivi` | 🔵 créateur | Ajoute une précision au fil. `403` si ce n'est pas votre ticket · `409` si clôturé |
| `POST` | `/tickets/{id}/cloturer` | 🔵 créateur | Clôture, avec `note_qualite` et `note_delai` facultatives (1–5). `409` si déjà clôturé |
| `GET` | `/tickets/{job_id}/status` | 🔵 | État du job Celery et, s'il a réussi, la branche et la réponse |

### Consultation

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/tickets` | 🔵 | Liste paginée. **Un utilisateur sans groupe ne reçoit que ses propres tickets** |
| `GET` | `/tickets/{id}` | 🔵 | Détail. 📖 |
| `GET` | `/tickets/{id}/reponses` | 🔵 | Réponses du ticket. 📖 |
| `GET` | `/tickets/{id}/workflow` | 🔵 | Timeline chronologique complète. 📖 |
| `GET` | `/tickets/mes-assignations` | 🔵 | Tickets qui vous sont assignés |
| `GET` | `/tickets/participated` | 🔵 | Tickets sur lesquels vous êtes intervenu |
| `GET` | `/tickets/domaines/{domaine}/validateurs` | 🟢 | Validateurs du domaine (sélecteur d'assignation) |

#### Paramètres de `GET /tickets`

| Paramètre | Type | Effet |
|---|---|---|
| `page`, `limit` | int | Pagination (défaut 1, 10) |
| `domaine` | str | Un domaine — **intersecté avec vos domaines autorisés** |
| `domaines` | str | Plusieurs domaines séparés par des virgules, même règle |
| `statut` | str | `NOUVEAU` / `RÉPONDU` / `VALIDÉ` / `REJETÉ` |
| `closed` | bool | `true` = clôturés, `false` = ouverts |
| `search` | str | Objet et question. **Un UUID valide cherche par identifiant** |
| `user_id` | uuid | Tickets d'un utilisateur |
| `disponibles` | bool | Non assignés, ou assignés à vous |
| `note_max` | int | Note qualité **ou** délai ≤ à cette valeur |
| `periode` | str | `semaine` / `mois` / `annee`, appliqué sur la **date de clôture** |
| `exclure_canonique` | bool | Écarte les tickets répondus automatiquement |

### Verrou et assignation

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/tickets/{id}/lock` | 🟢 ✍️ | Prend ou prolonge le verrou (bail de `LOCK_TTL_SECONDS`, défaut 300 s). `409` si pris ou assigné à un autre |
| `POST` | `/tickets/{id}/heartbeat` | 🟢 ✍️ | Prolonge le bail. `409` si le verrou a été perdu |
| `POST` | `/tickets/{id}/unlock` | 🔵 | Libère le verrou si vous le détenez. Idempotent, `204` |
| `POST` | `/tickets/{id}/assigner` | 🟢 ✍️ | Assigne à un validateur. `422` s'il n'est pas membre du domaine. Libère le verrou |
| `POST` | `/tickets/{id}/desassigner` | 🟢 ✍️ | Remet dans le pot commun |

### Réacheminement

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/tickets/{id}/recheminer` | 🟢 ✍️ domaine d'origine | Transfère le ticket vers un autre domaine et relance le pipeline. Corps : `{ "nouveau_domaine": "RH", "raison": "..." }` |

**Gardes spécifiques :**

| Code | Condition |
|---|---|
| `422` | `statut_ticket` n'est pas `RÉPONDU` |
| `422` | `nouveau_domaine` n'existe pas dans les groupes |
| `422` | `nouveau_domaine` est identique au domaine actuel |
| `422` | Le ticket a au moins une réponse avec `question_suivi` (précision de l'employé) |

**Effet :** réponse `EN_ATTENTE` supprimée (avec ses chunks), ticket remis à `NOUVEAU` / `EN_ATTENTE`, `reroute_source_domaine` renseigné, événement `RECHEMINE` écrit, `question_job` relancé avec `retraiter=True`, SSE `ticket_rerouted` émis vers les deux domaines et vers `sse:user:{id}` si le ticket a un propriétaire.

---

## Réponses

### Verdicts — uniquement sur les réponses `EN_ATTENTE`

Les quatre gardes appliquées à chaque verdict : état initial `EN_ATTENTE` (`409` sinon),
✍️ écriture domaine (`403`), anti-auto-validation (`403`), verrou libre ou détenu par vous
(`409`).

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/reponses/{id}/valider` | 🟢 | `VALIDÉE`, ticket `VALIDÉ`, `nb_validations + 1`, réindexation |
| `PUT` | `/reponses/{id}/corriger` | 🟢 | `CORRIGÉE`. `contenu_corrige` obligatoire non vide (`400`). Réindexation |
| `POST` | `/reponses/{id}/rejeter` | 🟢 | `REJETÉE`, ticket `REJETÉ` **et clôturé**. **Motif obligatoire.** Aucune indexation |

### Consultation

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/reponses/en-attente` | 🟢 | File de validation (`domaine`, `limit`) |
| `GET` | `/reponses/canoniques` | 🟢 | Réponses canoniques sources (`domaine`, `q`, `page`, `limit`) |
| `GET` | `/reponses/a-relire` | 🟢 | Signalées à relire, groupées par document |
| `GET` | `/reponses/obsoletes` | 🟢 | Retirées du service |

### Gestion de la base de réponses

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `PUT` | `/reponses/{id}/editer` | 🟢 ✍️ | Réécrit `contenu_corrige` et réindexe. Lève le drapeau *à relire* |
| `DELETE` | `/reponses/{id}` | 🟢 ✍️ | **Suppression définitive**, avec toutes les copies |
| `POST` | `/reponses/{id}/retirer` | 🟢 ✍️ | Passe en obsolète. `409` si pas signalée à relire. Réversible |
| `POST` | `/reponses/{id}/restaurer` | 🟢 ✍️ | Remet en service et réindexe. `409` si pas obsolète |
| `POST` | `/reponses/{id}/confirmer-actualite` | 🟢 ✍️ | Lève le signalement. `409` si pas signalée |
| `POST` | `/reponses/confirmer-actualite` | 🟢 | Lève le signalement **en lot** pour un `doc_id` + `version`. Restreint à vos domaines |

---

## Documents

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/documents` | 🟢 ✍️ | Import. PDF/DOCX/TXT/MD, **50 Mo max**. `DÉJÀ_INDEXÉ` si doublon · `409 DOCUMENT_HOMONYME` si même nom (contourné par `force_nouveau=true`) |
| `GET` | `/documents` | 🟢 📖 | Documents vivants (`domaine`, `domaines`, `limit` — défaut 500, max 1 000) |
| `GET` | `/documents/{doc_id}/chunks` | 🟢 📖 | Chunks indexés, dans l'ordre, lus depuis Qdrant |
| `GET` | `/documents/{doc_id}/download` | 🟢 📖 | Fichier d'origine |
| `DELETE` | `/documents/{doc_id}` | 🟢 ✍️ | Suppression douce. `409` si `EN_MAJ`. Marque les réponses citantes obsolètes, puis réexamine celles que d'autres sources soutiennent (`nb_a_reexaminer`) |
| `GET` | `/documents/{job_id}/status` | 🔵 | État du job d'ingestion |

### Versions

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/documents/{doc_id}/versions/preview` | 🟢 ✍️ | Analyse l'impact **sans rien modifier** |
| `POST` | `/documents/{doc_id}/versions/confirm` | 🟢 ✍️ | Applique la nouvelle version, déclenche la ré-vérification |
| `GET` | `/documents/{doc_id}/versions` | 🟢 📖 | Historique |
| `GET` | `/documents/{doc_id}/versions/{v}/download` | 🟢 📖 | Version archivée |
| `POST` | `/documents/{doc_id}/versions/{v}/restaurer` | 🟢 ✍️ | Revient à une version antérieure |

Voir [Mettre à jour un document](mise-a-jour-documents.md).

---

## Notifications et temps réel

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/notifications` | 🔵 | **Non lues uniquement**, 50 plus récentes |
| `POST` | `/notifications/{id}/lire` | 🔵 | Marque comme lue. Idempotent, `204` |
| `POST` | `/notifications/tout-lire` | 🔵 | Tout marquer lu, `204` |
| `GET` | `/sse/stream` | 🔵 | Flux Server-Sent Events. **Sa fermeture libère tous vos verrous** |

Voir [Notifications et temps réel](../fonctionnalites/notifications-et-temps-reel.md).

---

## Statistiques

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/stats/dashboard` | 🔵 | Cartes, répartitions, graphiques, satisfaction (`periode`, `domaine`) |
| `GET` | `/stats/groupe/{id}/membres` | 🔵 chef ou 🔴 | Stats par membre. `403` si vous n'êtes ni chef du groupe ni admin |
| `GET` | `/stats/hors-domaine` | 🔵 | Angles morts groupés par domaine (`periode`, défaut `mois`) |
| `DELETE` | `/stats/hors-domaine/{ticket_id}` | 🔵 | Masque la question des angles morts (`204`). **Le ticket n'est pas touché** |

`periode` vaut `semaine`, `mois` ou `annee`. Voir
[Statistiques et pilotage](../fonctionnalites/statistiques-et-pilotage.md).

---

## FAQ

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/faq/recherche?q=…` | 🔵 | Recherche sémantique dans les réponses canoniques. `429` si le quota par minute est dépassé |

Consultation **en lecture seule**, ouverte à tout utilisateur authentifié — `CurrentUser`
et non `BackofficeUser`. Aucun ticket n'est créé, aucune génération LLM ne tourne, **le
garde n'est jamais appelé** : la page *montre* ce qu'un humain a déjà validé au moins
`SEUIL_CANONIQUE` fois, elle ne *sert* rien sans revue. C'est pourquoi elle peut se passer
du juge là où la branche CANONIQUE ne le peut pas.

Trois points qui surprennent à la lecture du code :

- **Pas de filtrage par domaine**, contrairement à `check_domain_read` partout ailleurs.
  C'est délibéré et c'est le seul choix possible : un utilisateur lambda n'appartient à
  aucun groupe, filtrer par `user_domaines` ne renverrait rien.
- **Le score cosinus ne sort jamais de l'API.** Il ordonne les résultats, mais il n'a aucun
  sens pour un utilisateur final et invite aux mauvaises lectures.
- **Deux rangs.** `resultats` franchit `FAQ_SEUIL_PERTINENCE` ; `incertains` ne franchit que
  `FAQ_SEUIL_INCERTAIN` et n'est renvoyé **que si `resultats` est vide**. Un candidat retenu
  par la seule porte lexicale atterrit toujours dans `incertains` : sans juge sur cette
  branche, rien ne peut confirmer qu'un recouvrement de mots vaut une réponse.
  Les deux rangs ne sont pas plafonnés pareil : `resultats` est tronqué à
  `FAQ_MAX_RESULTATS` (5, configurable), `incertains` à `MAX_INCERTAINS` — **une constante de
  `services/faq.py` valant 3**, délibérément absente de la configuration. Rallonger une liste
  de pistes n'ajoute pas d'information, seulement du bruit.

> ⚠️ **Ne pas « corriger » un raté en abaissant `FAQ_SEUIL_PERTINENCE`.** Mesuré le
> 11/09/2026, la bande sous le seuil entrelace vrais et faux positifs sans valeur
> séparatrice : `hauteur fruit` → 0,6706 (correct) contre une demande sans rapport à 0,7110
> (faux). Le faux positif note *au-dessus* du vrai — aucun seuil ne les sépare. D'où deux
> rangs plutôt qu'un seuil déplacé.

Une recherche = un embedding Albert. D'où la soumission explicite (jamais de recherche à la
frappe), le cache React Query, et `FAQ_RATE_LIMIT_PAR_MINUTE` par utilisateur — vérifié
**avant** l'appel Albert. Ce limiteur est **fail-open**, contrairement au fail-closed du
login : une page en lecture seule ne doit pas tomber sur un hoquet de Valkey.

---

## Suggestions

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/suggestions` | 🔵 | Envoie un retour (10 à 2 000 caractères), `201` |
| `GET` | `/suggestions` | 🔴 | Liste |
| `PATCH` | `/suggestions/{id}/lu` | 🔴 | Marque comme lue |
| `DELETE` | `/suggestions/{id}` | 🔴 | Supprime, `204` |

---

## Administration

### Groupes et membres

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/admin/groupes` | 🔴 | Groupes et leurs membres |
| `GET` | `/admin/domaines` | 🔴 | Domaines distincts |
| `POST` | `/admin/groupes` | 🔴 | Crée un groupe, `201`. Le domaine doit être libre |
| `DELETE` | `/admin/groupes/{id}` | 🔴 | Supprime le groupe et ses associations, `204` |
| `POST` | `/admin/groupes/{gid}/membres/{user_id}` | 🔴 | Ajoute un membre — **UUID ou e-mail**, création à la volée, `201` |
| `DELETE` | `/admin/groupes/{gid}/membres/{user_id}` | 🔴 | Retire un membre, `204` |
| `PUT` | `/admin/groupes/{gid}/membres/{user_id}/chef` | 🔴 | Désigne ou révoque le chef |
| `GET` | `/admin/gestionnaires` | 🔴 | Gestionnaires depuis l'AD, avec repli sur la base |

### Supervision

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/admin/health` | 🔴 | État des 9 services + indicateurs fonctionnels |
| `GET` | `/admin/albert-quotas` | 🔴 | Consommation du jour par modèle, face aux limites `tpd` / `rpd` |
| `GET` | `/admin/incidents` | 🔴 | Tickets échoués, tickets bloqués (> 10 min), documents échoués |

### Réparation

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `POST` | `/admin/tickets/{id}/retry` | 🔴 | Relance. `409` si le ticket n'est pas `ÉCHOUÉ` / `EN_COURS` |
| `DELETE` | `/admin/tickets/{id}` | 🔴 | Supprime. Même condition, `204` |
| `POST` | `/admin/documents/{task_id}/retry` | 🔴 | Relance l'ingestion. `409` si le fichier temporaire a disparu |
| `GET` | `/admin/documents/{task_id}/download` | 🔴 | Récupère le fichier temporaire |
| `DELETE` | `/admin/documents/{task_id}` | 🔴 | Efface le fichier temporaire et la trace, `204` |
| `POST` | `/admin/documents/reconcile` | 🔴 | Recrée les lignes `documents` manquantes depuis Qdrant. **Idempotent** |

### Configuration

| Méthode | Route | Accès | Description |
|---|---|---|---|
| `GET` | `/admin/config` | 🔵 | **Tout utilisateur** — l'interface a besoin de la bannière. Renvoie aussi `jours_auto_cloture` (lecture seule) |
| `PUT` | `/admin/config/{key}` | 🔴 | Modifie une clé. `404` si la clé est inconnue. `banner` diffuse `banner_updated` |

---

## Codes de statut

| Code | Signification dans TicketAI |
|---|---|
| `200` / `201` | Succès |
| `204` | Succès sans contenu (suppressions, marquages) |
| `400` | Entrée invalide : domaine inconnu, question vide, fichier trop gros ou mal formé |
| `401` | JWT absent, invalide ou expiré |
| `403` | Domaine non autorisé, ou tentative de valider **son propre ticket** |
| `404` | Ressource inexistante, ou clé de configuration inconnue |
| `409` | **Conflit d'état** : verrou pris, ticket déjà clôturé, réponse déjà traitée, document homonyme, document en cours de mise à jour |
| `422` | Contrainte métier : assigné hors du domaine, longueur de suggestion hors bornes |
| `429` | Limite de tentatives de login dépassée |

Le `409` est le code le plus fréquent et le plus informatif : il signale presque toujours
que **quelqu'un d'autre est déjà passé** ou que l'objet n'est pas dans l'état attendu. Son
corps porte le détail (détenteur du verrou, date d'expiration, statut courant).
