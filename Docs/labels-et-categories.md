# Labels et catégories de tickets

Ce document explique la signification de chaque badge affiché sur un ticket, comment ils sont
calculés, et à quoi correspondent les onglets de filtrage dans la liste des tickets.

---

## 1. Les badges de statut

Chaque ticket affiche un badge coloré qui reflète son état courant. Voici tous les badges
possibles, par ordre de priorité d'affichage.

| Badge | Couleur | Signification |
|---|---|---|
| **Clôturé** | Gris | Ticket fermé par le demandeur ou automatiquement après validation |
| **En cours** | Bleu | L'IA est en train de générer une réponse |
| **Traitée** | Vert émeraude | Réponse canonique servie automatiquement, ou validée par un humain |
| **Hors domaine** | Violet | La question ne relève d'aucun domaine couvert |
| **Suggestion** | Ambre | Une réponse similaire existe mais doit être confirmée |
| **Rejetée** | Rouge | La réponse a été rejetée par un validateur |
| **Nouvelle** | Bleu ciel | Le ticket vient d'arriver, pas encore de réponse |

### Règle de priorité

Quand plusieurs conditions sont vraies en même temps, le badge est choisi dans cet ordre :

```
1. Clôturé      ← priorité absolue (ticket fermé)
2. En cours     ← l'IA travaille encore
3. Traitée      ← réponse canonique ou humaine confirmée
4. Hors domaine ← question hors périmètre (RÉPONDU + source HORS_DOMAINE)
5. Suggestion   ← réponse similaire à confirmer (RÉPONDU sans canonique)
6. Rejetée      ← réponse refusée
7. Nouvelle     ← état par défaut à l'arrivée
```

> **Note :** Le badge est identique ("Traitée", vert émeraude) qu'il s'agisse d'une réponse
> canonique (servie automatiquement par Qdrant) ou d'une réponse validée manuellement par un
> expert. La distinction reste visible dans le détail du ticket via la source de réponse.

---

## 2. Le cycle de vie d'un ticket

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TICKET CRÉÉ                                 │
│                        Badge: Nouvelle                              │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  L'IA traite          │
              │  Badge: En cours      │
              └───────────┬───────────┘
                          │
          ┌───────────────┼───────────────────┐
          ▼               ▼                   ▼
  ┌──────────────┐ ┌─────────────┐   ┌───────────────────┐
  │  Score élevé │ │Score moyen  │   │  Hors domaine     │
  │  + réponse   │ │             │   │  Badge:           │
  │  canonique   │ │             │   │  Hors domaine     │
  │  existante   │ │             │   └─────────┬─────────┘
  └──────┬───────┘ └──────┬──────┘             │
         │                │                    │
         ▼                ▼                    │
  ┌────────────┐   ┌──────────────┐           │
  │ CANONIQUE  │   │  SUGGESTION  │           │
  │ Badge:     │   │  Badge:      │           │
  │ Traitée    │   │  Suggestion  │           │
  └──────┬─────┘   └──────┬───────┘           │
         │                │                   │
         │         ┌──────┴──────┐            │
         │         ▼             ▼            │
         │   ┌──────────┐ ┌──────────┐       │
         │   │ Validée  │ │ Rejetée  │       │
         │   │ Badge:   │ │ Badge:   │       │
         │   │ Traitée  │ │ Rejetée  │       │
         │   └──────┬───┘ └──────────┘       │
         │          │                         │
         └────┬─────┘             ┌───────────┘
              │                   │
              ▼                   ▼
       ┌──────────────────────────────────┐
       │  Validations ≥ seuil canonique ? │
       └───────────────┬──────────────────┘
                       │
              Oui ◄────┴────► Non
               │               │
               ▼               │
       ┌──────────────┐        │ (reste Traitée)
       │  CANONIQUE   │        │
       │  Badge:      │        │
       │  Traitée     │        │
       └──────────────┘        │
                               │
    ┌──────────────────────┬────────────────────────────┐
    │  Clôture manuelle    │  Auto-clôture (Celery)     │
    │  par le demandeur    │  ticket VALIDÉ depuis       │
    │  (endpoint POST      │  ≥ jours_auto_cloture       │
    │  /cloturer)          │  (défaut : 7 jours)         │
    └──────────┬───────────┴────────────┬───────────────┘
               │                        │
               └───────────┬────────────┘
                           ▼
                   ┌───────────────┐
                   │   CLÔTURÉ     │
                   │   Badge: Gris │
                   └───────────────┘
```

---

## 3. La branche canonique en détail

La branche canonique est le chemin le plus automatisé : aucune intervention humaine n'est
requise. Le score de similarité ne suffit **pas** à l'emprunter — il ne fait que désigner un
candidat, que deux juges automatiques doivent ensuite approuver.

```
Question entrante
      │
      ▼
 Embedding  ──►  Qdrant (recherche hybride dense + sparse)
                          │
                          ▼
              ┌────────────────────────────────┐
              │  Un point porte-t-il un        │
              │  reponse_id, au-dessus de son  │
              │  plancher de candidature ?     │
              │  (canonique 0.70 · sinon 0.85) │
              └─────────────┬──────────────────┘
                            │
                 Oui ◄──────┴──────► Non
                  │                   │
                  ▼                   ▼
      ┌───────────────────────┐   Reranking + LLM
      │  La réponse est-elle  │   Badge: Suggestion
      │  canonique ?          │   (attente validation)
      └───────────┬───────────┘
                  │
       Oui ◄──────┴──────► Non
        │                   │
        ▼                   ▼
 ┌──────────────────┐   SUGGESTION
 │  GARDE           │   Badge: Suggestion
 │  [2] pertinence  │   (attente validation)
 │  [6] ancrage     │
 └────────┬─────────┘
          │
 Approuvé ◄┴► Refusé / juge indisponible
    │              │
    ▼              ▼
 CANONIQUE     Reranking + LLM
 Badge:        Badge: Suggestion
 Traitée       (attente validation)
```

Un refus des juges renvoie au RAG, **pas** en suggestion de la réponse en cache : le
validateur relit alors une réponse fraîche et ciblée, plutôt qu'une réponse dont on sait
déjà qu'elle ne traite pas le cas posé. Détail et mesures :
[Le garde du cache canonique](garde-cache-canonique.md).

---

## 4. Les onglets de filtrage

La liste des tickets propose quatre onglets. Voici exactement quels tickets tombent dans
chaque onglet.

### Tous

Affiche l'ensemble des tickets ouverts (non clôturés). Le compteur indique le total serveur.

### En attente

Tickets qui nécessitent une action humaine. Regroupe :

```
┌─────────────────────────────────────────────────────┐
│                   EN ATTENTE                        │
├─────────────────────────────────────────────────────┤
│  ● statut_ticket = NOUVEAU                          │
│    → ticket arrivé, l'IA n'a pas encore répondu    │
│    Badge: Nouvelle                                   │
│                                                     │
│  ● statut_ticket = RÉPONDU  ET  canonique = false   │
│    → réponse de l'IA à valider (toutes sources)     │
│    Badge: Suggestion  ou  Hors domaine              │
└─────────────────────────────────────────────────────┘
```

> **Note :** Les tickets « Hors domaine » apparaissent dans cet onglet car ils attendent
> qu'un validateur les traite manuellement. Leur badge violet reste affiché.

### Traités

Tickets qui ont reçu une réponse considérée comme satisfaisante (humaine ou automatique) :

```
┌─────────────────────────────────────────────────────┐
│                    TRAITÉS                          │
├─────────────────────────────────────────────────────┤
│  ● canonique = true                                 │
│    → réponse automatique de haute confiance         │
│    Badge: Traitée                                   │
│                                                     │
│  ● statut_ticket = VALIDÉ                           │
│    → réponse confirmée par un validateur humain     │
│    Badge: Traitée                                   │
└─────────────────────────────────────────────────────┘
```

### Clôturés

Tickets fermés. Requête séparée côté serveur (`closed=true`). Deux chemins mènent ici :

```
┌─────────────────────────────────────────────────────┐
│                    CLÔTURÉS                         │
├─────────────────────────────────────────────────────┤
│  ● Clôture manuelle par le demandeur                │
│    → via le bouton "Clôturer" dans son espace       │
│    → seul le créateur du ticket peut le faire       │
│                                                     │
│  ● Auto-clôture par Celery Beat                     │
│    → ticket VALIDÉ depuis ≥ jours_auto_cloture      │
│    → (défaut : 7 jours après validated_at)          │
│                                                     │
│  Badge: Clôturé (gris) — plus d'action requise      │
└─────────────────────────────────────────────────────┘
```

---

## 5. Récapitulatif badge × onglet

```
Badge           │ Tous │ En attente │ Traités  │ Clôturés
────────────────┼──────┼────────────┼──────────┼──────────
Nouvelle        │  ✓   │     ✓      │          │
En cours        │  ✓   │     ✓      │          │
Suggestion      │  ✓   │     ✓      │          │
Hors domaine    │  ✓   │     ✓      │          │
Traitée         │  ✓   │            │    ✓     │
Rejetée         │  ✓   │     ✓      │          │
Clôturé         │      │            │          │    ✓
```

> Un ticket « Rejeté » reste en attente car la question n'a pas de réponse valide — un
> validateur doit corriger ou escalader.

---

## 6. Exemple complet : du ticket à la canonisation

```
Jour 1 — Arrivée
  Thomas soumet : "Comment poser des RTT ?"
  └─► Badge: Nouvelle  →  onglet En attente

Jour 1 — Traitement IA (quelques secondes)
  Aucune réponse réutilisable dans Qdrant
  Reranking + génération LLM
  └─► Badge: Suggestion  →  onglet En attente

Jour 1 — Validation
  Marie (RH) valide la suggestion
  nb_validations : 1
  └─► Badge: Traitée  →  onglet Traités

Jour 2 — Autre ticket similaire
  "Je veux prendre des RTT, comment faire ?"
  Score : 0.91  ≥  0.85  →  réponse validée réutilisée en suggestion
  Marie valide à nouveau — nb_validations : 2
  └─► Badge: Traitée  →  onglet Traités

Jour 3 — Seuil canonique atteint (défaut : 3)
  "Procédure RTT ?"
  Marie valide — nb_validations : 3
  Réponse promue, réindexée dans Qdrant
  └─► Badge: Traitée  →  onglet Traités

Jour 4 — Ticket identique suivant
  Score : 0.94  +  reponse_id canonique trouvé dans Qdrant
  Garde : [2] SUFFISANTE  et  [6] ETAYEE
  └─► Badge: Traitée  →  aucune validation requise

Jour 5 — Même sujet, mais avec une précision
  "Et pour un alternant, comment je pose des RTT ?"
  Score : 0.93  →  même réponse canonique candidate
  Garde : [6] NON_ETAYEE (les documents ne disent rien des alternants)
  └─► retour au RAG  →  Badge: Suggestion  →  onglet En attente
```
