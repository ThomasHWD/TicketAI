# Statistiques et pilotage

TicketAI expose trois vues chiffrées, destinées à trois publics différents :

| Vue | Page | Public | Question à laquelle elle répond |
|---|---|---|---|
| **Tableau de bord** | `/` | Validateurs | *Où en est mon domaine ?* |
| **Statistiques d'équipe** | `/mon-suivi` → stats du groupe | Chefs de groupe, admins | *Qui fait quoi dans mon équipe ?* |
| **Vue globale** | `/admin/dashboard` | Admins | *Comment se porte la plateforme ?* |

---

## 1. Le périmètre : ce que chacun voit

C'est le point à comprendre en premier, car il conditionne l'interprétation de tous les
chiffres.

| Profil | Périmètre des statistiques |
|---|---|
| **Validateur** | Uniquement les domaines de ses groupes |
| **Admin avec groupes** | Uniquement les domaines de ses groupes |
| **Admin sans groupe** | Tous les domaines |

Un filtre `domaine` peut restreindre davantage, mais **jamais élargir** : il est toujours
intersecté avec les domaines autorisés.

> Deux validateurs de domaines différents regardant « le » tableau de bord ne voient donc
> pas les mêmes chiffres. C'est voulu — les totaux sont locaux à un domaine.

---

## 2. Les périodes et la comparaison

Toutes les vues acceptent une période : `semaine`, `mois` ou `annee`.

| Période | Début | Comparée à |
|---|---|---|
| `semaine` | Lundi de la semaine en cours | La semaine précédente |
| `mois` | 1ᵉʳ du mois en cours | Le mois précédent |
| `annee` | 1ᵉʳ janvier | L'année précédente |

Chaque carte affiche donc une valeur **et** sa variation par rapport à la période
équivalente précédente. Les bornes sont calculées en UTC.

> **Attention aux périodes en cours.** Le mardi matin, la « semaine » ne compte que deux
> jours, tandis que la semaine précédente en compte sept. Une baisse affichée en début de
> période n'est pas nécessairement une baisse réelle.

---

## 3. Le tableau de bord du validateur

### Pourquoi on fait ça

Mesurer l'activité du domaine sur une période pour répondre en un coup d'œil à : *est-ce
que la file se vide ? Le système répond-il de plus en plus automatiquement ? Les délais
sont-ils acceptables ?* C'est le point de départ du pilotage quotidien.

### Comment ça fonctionne

La page d'accueil `/` s'ouvre sur six cartes. La plus importante est **Répondu canonique**
— elle indique le pourcentage de questions auxquelles personne n'a eu à répondre
manuellement. Elle monte à mesure que la base de réponses validées s'enrichit.

Pour voir les graphiques et la répartition par branche, cliquez **Afficher les analytiques** :
un anneau montre la distribution des tickets entre les quatre issues possibles (CANONIQUE /
SUGGESTION / LLM / HORS_DOMAINE), et une courbe montre l'évolution du volume par jour.

> **Lire l'anneau :**
> - Beaucoup de `HORS_DOMAINE` ⇒ le corpus a des trous — voir les [angles morts](base-de-connaissances.md#6-les-angles-morts).
> - Beaucoup de `LLM` ⇒ les questions sont variées, ou la base de réponses est encore jeune.
> - Beaucoup de `CANONIQUE` ⇒ le système fait son travail.

Le sélecteur de période (semaine / mois / année) et le filtre domaine sont en haut de page.
Un voyant indique quand les données ont été chargées pour la dernière fois.

![Le tableau de bord du validateur](../images/21-dashboard.png)

> 📸 **[CAPTURE D'ÉCRAN COMPLÉMENTAIRE]** : *Le bloc « analytiques » déplié sur une instance chargée : anneau de répartition des branches, courbe des tickets par jour, carte satisfaction.*

### Détails techniques

Endpoint : `GET /stats/dashboard` (période par défaut : `semaine`).

**Les six cartes :**

| Carte | Ce qu'elle compte |
|---|---|
| **Nouveaux** | Tickets créés sans réponse validée |
| **En cours** | Tickets en cours de traitement |
| **Tickets clôturés** | Tickets fermés sur la période |
| **Répondu canonique** | **Un taux** : part des tickets traités automatiquement, sans intervention humaine |
| **Temps de première réponse** | Délai moyen entre création et première réponse |
| **Temps de clôture** | Délai moyen entre création et clôture |

**Autres blocs :**

| Bloc | Contenu |
|---|---|
| **Répartition des statuts** | Nouveau / En cours / Clôturé, en nombre et en pourcentage |
| **Tickets par jour** | Courbe d'activité (agrégée par mois quand la période est `annee`) |
| **Temps de traitement par jour** | Évolution des délais |
| **Derniers tickets** | Les 5 plus récents, avec la branche empruntée |
| **Satisfaction** | Moyennes des notes (voir [§ 4](#4-la-satisfaction)) |

---

## 4. La satisfaction

### Pourquoi on fait ça

Évaluer si les réponses servent vraiment les employés — pas seulement si la question a
été traitée. Un ticket clôturé noté 2/5 en qualité est un signal que la réponse n'était
pas satisfaisante, même si le système l'a bien gérée techniquement.

### Comment ça fonctionne

La carte **Satisfaction** du tableau de bord affiche deux moyennes avec leur effectif.
Cliquer sur la carte ouvre la liste des tickets mal notés pour pouvoir les examiner.

Deux précisions indispensables pour lire ces chiffres :
- Les moyennes portent sur les tickets **clôturés dans la période**, pas créés dans la
  période.
- **La notation est facultative.** Regardez toujours l'effectif (`nb_avec_notes`) avant
  d'interpréter une moyenne — une moyenne de 4,8 sur 3 tickets ne dit pas grand-chose.
  Quand aucun ticket n'a été noté, les moyennes valent `null` et l'interface affiche un
  état vide plutôt qu'un zéro trompeur.

> 📸 **[CAPTURE D'ÉCRAN REQUISE]** : *La carte « Satisfaction » du tableau de bord avec ses deux moyennes et l'effectif, puis la fenêtre modale « Tickets insatisfaits » ouverte listant les tickets mal notés avec leurs notes.*

### Détails techniques

Les notes sont saisies par l'employé à la clôture — voir
[Espace utilisateur](espace-utilisateur.md#8-clôturer-un-ticket-et-noter-la-réponse).

| Mesure | Champ |
|---|---|
| Moyenne de la qualité perçue | `avg_qualite` |
| Moyenne de la rapidité perçue | `avg_delai` |
| Nombre de tickets notés | `nb_avec_notes` |

Le filtre `note_max` de `GET /tickets` renvoie les tickets dont la note qualité **ou** la
note délai est inférieure ou égale à la valeur donnée. C'est ce qui alimente la fenêtre
« tickets insatisfaits » : un clic depuis la carte satisfaction ouvre directement la liste
des tickets mal notés.

---

## 5. Les statistiques par membre

### Pourquoi on fait ça

Répartir la charge dans l'équipe, pas classer les individus. Voir qui traite beaucoup de
tickets et qui peut en prendre davantage, ou qui contribue au corpus documentaire. C'est
un outil de management, pas de notation.

### Comment ça fonctionne

Depuis le tableau de bord, les chefs de groupe voient un onglet **Mon équipe**. Il liste
tous les membres du groupe avec, pour la période sélectionnée, le nombre de réponses
traitées et le nombre de documents ajoutés.

Les chefs apparaissent en tête de liste avec un badge dédié. Le total du groupe est affiché
en pied de tableau.

Si vous gérez plusieurs groupes, un sélecteur en haut de page permet de choisir le groupe
à afficher.

> 📸 **[CAPTURE D'ÉCRAN REQUISE]** : *La page de statistiques d'équipe montrant le tableau des membres du groupe avec leurs compteurs, le chef identifié, et le sélecteur de période.*

### Détails techniques

Endpoint : `GET /stats/groupe/{groupe_id}/membres`.

**Règles d'accès :**

| Profil | Accès |
|---|---|
| **Chef de groupe** (`is_chef = true`) | Les stats de **son** groupe |
| **Admin** | Les stats de **tous** les groupes |
| Membre simple | `403 Accès réservé au chef du groupe` |

C'est d'ailleurs la **seule** permission supplémentaire qu'apporte le statut de chef de
groupe.

Pour chaque membre du groupe, sur la période choisie : nombre de réponses traitées (là où
le membre figure comme validateur) et contribution documentaire. Le tri est modifiable
(tickets traités ou documents ajoutés, croissant ou décroissant).

---

## 6. La vue globale de l'administrateur

### Pourquoi on fait ça

Surveiller l'ensemble de la plateforme, tous domaines confondus, sans appartenir à un
groupe particulier. Un admin peut détecter qu'un domaine spécifique accumule des tickets
sans réponse ou que les délais s'allongent globalement.

### Comment ça fonctionne

Page `/admin/dashboard`, réservée au rôle `ADMIN`. Elle agrège la santé technique et
l'activité fonctionnelle de toute la plateforme. Les mêmes indicateurs que le tableau de
bord du validateur, mais agrégés sur tous les domaines — ou filtrés sur un domaine
spécifique via le sélecteur en haut de page.

> 📸 **[CAPTURE D'ÉCRAN REQUISE]** : *La page « Vue globale » de l'administration (`/admin/dashboard`), montrant l'agrégation multi-domaines et les indicateurs de plateforme.*

### Détails techniques

Les indicateurs de supervision (services, files Celery, quotas Albert, incidents) sont
détaillés dans [Administration](administration.md). La vue globale partage le même endpoint
`GET /stats/dashboard` que le tableau de bord validateur, mais sans filtre de domaine pour
les admins sans groupe.

---

## 7. Notes de lecture

Quelques pièges connus, à garder en tête avant de tirer des conclusions :

| Piège | Détail |
|---|---|
| **Les périodes en cours sont tronquées** | Comparer un lundi à une semaine complète produit une fausse baisse |
| **Les branches se comptent par ticket** | Un ticket avec plusieurs réponses (relances) compte une fois par branche distincte |
| **La satisfaction est déclarative et facultative** | Regardez `nb_avec_notes` avant d'interpréter une moyenne |
| **Les périmètres diffèrent** | Deux validateurs voient des totaux différents ; c'est normal |
| **Les tickets masqués** | Un ticket masqué des angles morts sort de cette vue, mais reste dans tous les autres compteurs |
