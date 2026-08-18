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
| **En cours** | Bleu clair | L'IA est en train de générer une réponse |
| **Canonique** | Vert | Réponse validée ≥ seuil, réutilisée automatiquement |
| **Validée** | Bleu | Un humain a validé la réponse de l'IA |
| **Hors domaine** | Violet | La question ne relève d'aucun domaine couvert |
| **Suggestion** | Ambre | Une réponse similaire existe mais doit être confirmée |
| **Rejetée** | Rouge | La réponse a été rejetée par un validateur |
| **Nouvelle** | Gris clair | Le ticket vient d'arriver, pas encore de réponse |

### Règle de priorité

Quand plusieurs conditions sont vraies en même temps, le badge est choisi dans cet ordre :

```
1. Clôturé      ← priorité absolue (ticket fermé)
2. En cours     ← l'IA travaille encore
3. Canonique    ← réponse automatique de haute confiance
4. Validée      ← réponse humaine confirmée
5. Hors domaine ← question hors périmètre
6. Suggestion   ← réponse similaire à confirmer
7. Rejetée      ← réponse refusée
8. Nouvelle     ← état par défaut à l'arrivée
```

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
  │ Canonique  │   │  Suggestion  │           │
  └──────┬─────┘   └──────┬───────┘           │
         │                │                   │
         │         ┌──────┴──────┐            │
         │         ▼             ▼            │
         │   ┌──────────┐ ┌──────────┐       │
         │   │ Validée  │ │ Rejetée  │       │
         │   │ Badge:   │ │ Badge:   │       │
         │   │ Validée  │ │ Rejetée  │       │
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
       ┌──────────────┐        │ (reste Validée)
       │  CANONIQUE   │        │
       │  Badge:      │        │
       │  Canonique   │        │
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
requise si la réponse est déjà connue avec haute confiance.

```
Question entrante
      │
      ▼
 Embedding  ──►  Qdrant (recherche hybride dense + sparse)
                          │
                          ▼
              ┌───────────────────────┐
              │  Score cosinus        │
              │  ≥ seuil    │
              └─────────┬─────────────┘
                        │
             Oui ◄──────┴──────► Non
              │                   │
              ▼                   ▼
   ┌─────────────────┐     Reranking + LLM
   │ reponse_id dans │     Badge: Suggestion
   │ le payload      │     (attente validation)
   │ Qdrant ?        │
   └────────┬────────┘
            │
   Oui ◄───┴───► Non
    │              │
    ▼              ▼
 CANONIQUE     Cherche une réponse
 Badge vert    VALIDÉE liée au doc
               Badge: Suggestion
```

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

### Répondus

Tickets qui ont reçu une réponse considérée comme satisfaisante (humaine ou automatique) :

```
┌─────────────────────────────────────────────────────┐
│                    RÉPONDUS                         │
├─────────────────────────────────────────────────────┤
│  ● canonique = true                                 │
│    → réponse automatique de haute confiance         │
│    Badge: Canonique                                 │
│                                                     │
│  ● statut_ticket = VALIDÉ                           │
│    → réponse confirmée par un validateur humain     │
│    Badge: Validée                                   │
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
Badge           │ Tous │ En attente │ Répondus │ Clôturés
────────────────┼──────┼────────────┼──────────┼──────────
Nouvelle        │  ✓   │     ✓      │          │
En cours        │  ✓   │     ✓      │          │
Suggestion      │  ✓   │     ✓      │          │
Hors domaine    │  ✓   │     ✓      │          │
Canonique       │  ✓   │            │    ✓     │
Validée         │  ✓   │            │    ✓     │
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
  Score cosinus : 0.82  ≥  seuil 0.70
  Aucune réponse canonique trouvée dans Qdrant
  └─► Badge: Suggestion  →  onglet En attente

Jour 1 — Validation
  Marie (RH) valide la suggestion
  nb_validations : 1
  └─► Badge: Validée  →  onglet Répondus

Jour 2 — Autre ticket similaire
  "Je veux prendre des RTT, comment faire ?"
  Score : 0.91  →  réponse validée réutilisée
  Marie valide à nouveau — nb_validations : 2
  └─► Badge: Validée  →  onglet Répondus

Jour 3 — Seuil canonique atteint (défaut : 3)
  "Procédure RTT ?"
  Marie valide — nb_validations : 3
  Réponse promue, réindexée dans Qdrant
  └─► Badge: Canonique  →  onglet Répondus

Jour 4 — Ticket identique suivant
  Score : 0.94  +  reponse_id trouvé dans Qdrant
  └─► Badge: Canonique  →  aucune validation requise
```
