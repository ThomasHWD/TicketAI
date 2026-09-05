# Traiter les tickets (backoffice)

Ce document décrit le travail quotidien d'un validateur : trouver les tickets à traiter,
se les réserver, et rendre un verdict.

**Qui a accès ?** Tout utilisateur appartenant à au moins un groupe, plus les
administrateurs. Un validateur ne voit que les tickets **de ses domaines** — le filtre est
appliqué en base, pas seulement dans l'interface.

---

## 1. Les pages du backoffice

| Page | Adresse | Contenu |
|---|---|---|
| **Tableau de bord** | `/` | Compteurs, graphiques, file d'attente — voir [Statistiques](statistiques-et-pilotage.md) |
| **Tickets** | `/tickets` | La file de travail : liste, filtres, onglets |
| **Détail d'un ticket** | `/tickets/{id}` | Le fil, les actions de validation, la barre latérale |
| **Mon suivi** | `/mon-suivi` | Les tickets auxquels *vous* avez participé |
| **Réponses enregistrées** | `/reponses-enregistrees` | La base de réponses — voir [Réponses enregistrées](reponses-enregistrees.md) |
| **Base de connaissances** | `/base-de-connaissances` | Les documents — voir [Base de connaissances](base-de-connaissances.md) |

---

## 2. La liste des tickets

### Les onglets

Quatre onglets découpent la file. Le détail exact de ce qui tombe dans chacun, ainsi que
la signification des badges de couleur, est documenté dans
[Cycle de vie et labels d'un ticket](labels-et-categories.md).

En résumé :

| Onglet | Contenu |
|---|---|
| **Tous** | Tous les tickets ouverts (non clôturés) |
| **En attente** | Ceux qui réclament une action humaine |
| **Traités** | Réponse canonique servie, ou réponse validée par un humain |
| **Clôturés** | Requête serveur séparée (`closed=true`) |

![La file de tickets avec ses quatre onglets](../images/20-tickets-liste.png)

Les onglets portent leur compteur (`Tous 8`, `En attente 6`, `Traités 2`), et la colonne
de droite montre les badges dans leurs différents états : **En cours**, **Nouvelle**,
**Suggestion**, **Hors domaine**, **Traitée**. Noter la pastille orange sur *Réponses
enregistrées* dans la barre latérale : c'est le compteur de réponses à relire.

> 📸 **[CAPTURE D'ÉCRAN COMPLÉMENTAIRE]** : *Un ticket verrouillé par un autre validateur (cadenas) et un ticket assigné (avatar) — cela demande deux comptes validateurs connectés simultanément.*

### Les filtres disponibles

L'endpoint `GET /api/v1/tickets` accepte :

| Paramètre | Effet |
|---|---|
| `page`, `limit` | Pagination (défaut : page 1, 10 par page) |
| `domaine` / `domaines` | Un domaine, ou plusieurs séparés par des virgules. **Toujours intersecté avec vos domaines autorisés** |
| `statut` | Filtre sur `statut_ticket` (`NOUVEAU`, `RÉPONDU`, `VALIDÉ`, `REJETÉ`) |
| `closed` | `true` = clôturés, `false` = ouverts |
| `search` | Cherche dans l'objet et la question. **Si la valeur est un UUID valide, cherche le ticket par son identifiant** |
| `user_id` | Tickets d'un utilisateur donné |
| `disponibles` | Ne garde que les tickets non assignés, ou assignés à vous |
| `note_max` | Tickets dont la note qualité **ou** délai est ≤ à cette valeur — pour retrouver les insatisfaits |
| `periode` | `semaine` / `mois` / `annee`, appliqué sur la **date de clôture** |
| `exclure_canonique` | Écarte les tickets répondus automatiquement |

> **Garde-fou :** un utilisateur sans groupe qui appelle cet endpoint ne reçoit que ses
> propres tickets, quels que soient les filtres passés.

---

## 3. Le verrou collaboratif

### Le problème

Deux validateurs du même domaine ouvrent le même ticket. Tous deux rédigent une
correction. Le second écrase le travail du premier — ou pire, la question reçoit deux
verdicts contradictoires.

### La solution : un bail à expiration

Ouvrir un ticket en prend le **verrou**. Ce n'est pas un blocage définitif mais un *bail*
qui expire tout seul, ce qui évite qu'un onglet oublié gèle un ticket pour toujours.

```mermaid
stateDiagram-v2
    [*] --> Libre
    Libre --> Detenu: POST /lock — bail de 300 s
    Detenu --> Detenu: POST /heartbeat — prolonge le bail
    Detenu --> Libre: POST /unlock
    Detenu --> Libre: bail expiré
    Detenu --> Libre: déconnexion SSE
    Detenu --> Libre: verdict rendu
    Libre --> [*]
```

| Mécanisme | Détail |
|---|---|
| **Durée du bail** | `LOCK_TTL_SECONDS`, **défaut 300 s** (5 minutes) |
| **Prolongation** | Un *heartbeat* périodique repousse l'échéance tant que l'onglet est ouvert |
| **Libération explicite** | `POST /tickets/{id}/unlock` — idempotent, n'agit que si vous détenez le verrou |
| **Libération à la déconnexion** | Quand le flux SSE se ferme, **tous** les verrous de cet utilisateur sont relâchés |
| **Libération après verdict** | Valider, corriger ou rejeter libère le verrou automatiquement |

L'acquisition est **atomique** : un `UPDATE` conditionnel qui ne réussit que si le ticket
est libre, déjà à vous, ou si le bail précédent a expiré. Deux validateurs qui cliquent en
même temps ne peuvent pas obtenir le verrou tous les deux.

Si le verrou est déjà pris, l'API répond `409` avec l'e-mail du détenteur et la date
d'expiration, ce qui permet à l'interface d'afficher *« En cours de traitement par
marie@entreprise.fr »*.

### Verrou et assignation

Ce sont deux notions différentes :

| | **Verrou** | **Assignation** |
|---|---|---|
| Durée | quelques minutes | jusqu'à changement explicite |
| Objectif | éviter la collision d'édition | répartir la charge dans l'équipe |
| Posé par | celui qui ouvre le ticket | n'importe quel validateur du domaine |
| Expire seul | oui | non |

Un ticket **assigné à quelqu'un d'autre** ne peut pas être verrouillé par vous : l'API
répond `409` avec `is_assigned: true`. L'assignation prime donc sur le verrou.

---

## 4. L'assignation

| Action | Endpoint | Règle |
|---|---|---|
| Assigner | `POST /tickets/{id}/assigner` | L'assigné doit être **membre du domaine du ticket** (`422` sinon) |
| Désassigner | `POST /tickets/{id}/desassigner` | Remet le ticket dans le pot commun |

Assigner un ticket **libère son verrou** au passage — l'assigné n'hérite pas du verrou de
celui qui l'a assigné.

Les deux actions écrivent un événement dans la timeline (`ASSIGNE` / `DESASSIGNE`) et
notifient en temps réel : le domaine entier, plus l'assigné personnellement.

La page **Mon suivi** (`/mon-suivi`) et l'endpoint `GET /tickets/mes-assignations`
permettent à chacun de retrouver ce qui lui a été confié.

Pour peupler le sélecteur d'assignation, l'interface appelle
`GET /tickets/domaines/{domaine}/validateurs`.

> 📸 **[CAPTURE D'ÉCRAN REQUISE]** : *Le menu d'assignation ouvert sur un ticket, listant les validateurs du domaine avec leurs avatars. Annoter pour montrer que seuls les membres du domaine apparaissent.*

---

## 5. Rendre un verdict

C'est le cœur du travail de validation. Trois issues possibles.

```mermaid
flowchart TD
    A[Réponse EN_ATTENTE] --> B{Verdict du validateur}
    B -->|La réponse est bonne| C[VALIDER]
    B -->|Le fond est bon,<br/>la forme à retoucher| D[CORRIGER]
    B -->|La réponse est fausse<br/>ou hors sujet| E[REJETER]

    C --> F[statut = VALIDÉE<br/>ticket = VALIDÉ<br/>nb_validations + 1]
    D --> G[statut = CORRIGÉE<br/>ticket = VALIDÉ<br/>contenu_corrige rempli]
    E --> H[statut = REJETÉE<br/>ticket = REJETÉ<br/>ticket clôturé]

    F --> I[feedback_job :<br/>réindexation Qdrant]
    G --> I
    H --> J[Rien n'est indexé]

    I --> K{nb_validations<br/>≥ SEUIL_CANONIQUE ?}
    K -->|oui| L[Réponse promue<br/>CANONIQUE]
    K -->|non| M[Réutilisable en<br/>SUGGESTION]
```

### Valider

`POST /reponses/{id}/valider`

- La réponse passe `VALIDÉE`, le ticket passe `VALIDÉ`.
- Le compteur `nb_validations` est incrémenté — **sur la réponse source** si celle-ci est
  une copie SUGGESTION, sinon sur elle-même.
- Quand le compteur atteint `SEUIL_CANONIQUE` (**défaut : 3**), la réponse devient
  canonique.
- Un `feedback_job` réindexe la réponse dans Qdrant pour qu'elle soit réutilisable.
- L'employé reçoit une notification.

### Corriger

`PUT /reponses/{id}/corriger` — le corps doit contenir un `contenu_corrige` non vide
(`400` sinon).

- La réponse passe `CORRIGÉE`, le ticket passe `VALIDÉ`.
- Le texte original est **conservé** dans `contenu` ; la correction va dans
  `contenu_corrige`. C'est la version corrigée qui est servie.
- Si la réponse était signalée *à relire*, le drapeau est levé.
- Un `feedback_job` est déclenché : la version corrigée est indexée.

> **À noter :** corriger n'incrémente pas `nb_validations`. Une réponse corrigée ne
> progresse pas vers le statut canonique par cette action.

### Rejeter

`POST /reponses/{id}/rejeter` — **le motif est obligatoire**.

- La réponse passe `REJETÉE`, le ticket passe `REJETÉ` **et est clôturé** (`closed_at`
  renseigné).
- Rien n'est indexé dans Qdrant : une réponse rejetée ne sera jamais réutilisée.
- L'employé reçoit une notification de type `REPONSE_REJETEE`.

![Le détail d'un ticket : conversation, actions de validation et barre latérale](../images/30-ticket-detail.png)

On y voit la réponse produite par l'IA (signalée « Générée par l'IA à partir des
documents — relisez attentivement avant de valider »), les trois actions **Valider /
Corriger / Rejeter**, et la barre latérale qui porte le statut, le demandeur et
l'assignation.

> 📸 **[CAPTURE D'ÉCRAN COMPLÉMENTAIRE]** : *La zone de saisie du motif de rejet ouverte, pour montrer qu'elle est obligatoire.*

### Les quatre gardes avant tout verdict

Chaque action de verdict vérifie, dans cet ordre :

| Garde | Refus | Message |
|---|---|---|
| **État initial** | `409` | La réponse est déjà `VALIDÉE` / `REJETÉE` / `CORRIGÉE` — seules les `EN_ATTENTE` sont traitables |
| **Domaine** | `403` | Vous devez être **membre** du domaine du ticket. *Sans exception pour l'admin* |
| **Anti-auto-validation** | `403` | Vous ne pouvez pas trancher sur **votre propre ticket** |
| **Verrou** | `409` | Le ticket doit être libre ou verrouillé par vous |

La règle anti-auto-validation est structurelle : elle garantit qu'une réponse servie sans
revue a bien été examinée par quelqu'un d'autre que le demandeur.

---

## 6. La timeline d'un ticket

`GET /tickets/{id}/workflow` reconstitue l'histoire complète du ticket, triée
chronologiquement. C'est ce qu'affiche la fenêtre *Workflow*.

| Type d'événement | Origine | Signification |
|---|---|---|
| `CREE` | ticket | Le ticket a été créé |
| `SUIVI` | réponse avec `question_suivi` | L'employé a relancé le fil |
| `REPONSE_GENEREE` | réponse | L'IA a produit une réponse (le `meta` porte la branche) |
| `ASSIGNE` / `DESASSIGNE` | table `ticket_events` | Changement d'assignation, avec l'acteur |
| `VALIDE` / `CORRIGE` / `REJETE` | réponse validée | Verdict humain, avec l'acteur et le motif de rejet |
| `CLOTURE` | ticket | Le ticket a été fermé |

Les événements portent l'e-mail et le nom complet de l'acteur quand il est connu. À
horodatage égal, un ordre de type départage l'affichage (création avant suivi avant
réponse avant verdict avant clôture) pour que la timeline reste lisible.

![La fenêtre « Historique » d'un ticket](../images/31-ticket-workflow.png)

Elle s'ouvre par le bouton **Voir l'historique** de la barre latérale.

> 📸 **[CAPTURE D'ÉCRAN COMPLÉMENTAIRE]** : *La même fenêtre sur un ticket ayant vécu — création, réponse générée, assignation, relance, seconde réponse, validation, clôture. C'est la vue qui montre le mieux la traçabilité ; l'instance de test n'a que deux événements.*

---

## 7. Mon suivi

Page `/mon-suivi`, alimentée par `GET /tickets/participated`.

Elle rassemble les tickets sur lesquels **vous** êtes intervenu — validés, corrigés,
rejetés ou assignés — pour permettre de revenir sur son propre travail sans fouiller
toute la file du domaine.

![La page « Mon suivi »](../images/22-mon-suivi.png)

---

## 8. Ce qui bouge tout seul

Le backoffice n'a pas besoin d'être rafraîchi. Chaque action diffuse un événement temps
réel sur le canal du domaine, et les listes concernées se rechargent seules :

| Événement | Ce qui se met à jour |
|---|---|
| `ticket_created`, `ticket_answered` | La file de tickets |
| `ticket_locked`, `ticket_unlocked` | Les cadenas dans la liste |
| `ticket_assigned`, `ticket_unassigned` | La liste et « Mes assignations » |
| `reponse_validated`, `reponse_corrected`, `reponse_rejected` | Le ticket et les réponses enregistrées |
| `ticket_closed` | La file et les compteurs |

Le mécanisme complet est décrit dans
[Notifications et temps réel](notifications-et-temps-reel.md).
