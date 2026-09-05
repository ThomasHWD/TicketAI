# Garde du cache canonique

Ce document explique le mécanisme qui décide si une réponse canonique peut être servie sans revue humaine.

**Fichiers concernés**
- `backend/app/services/garde_cache.py` — implémentation du garde
- `backend/app/workers/question.py` — point d'appel dans le pipeline (étape 2)
- `backend/app/config.py` — `ALBERT_GARDE_MODEL_NAME`

---

## Problème

La recherche hybride dans Qdrant mesure une proximité vectorielle : deux questions proches dans l'espace sémantique obtiennent un score cosinus élevé même si elles n'appellent pas la même réponse. Des exemples typiques qui trompent le cosinus :

- Même sujet, chiffre différent : *"J'ai droit à combien de jours de RTT ?"* vs *"J'ai droit à combien de jours de congé ?"*
- Négation : *"Puis-je télétravail ?"* vs *"Puis-je **refuser** de télétravailler ?"*
- Périmètre restreint : *"Quel est le préavis de licenciement ?"* vs *"Quel est le préavis de licenciement **pour un CDD** ?"*
- Ajout de condition : *"Puis-je poser des congés en décembre ?"* vs *"Puis-je poser des congés en décembre **si j'ai moins d'un an d'ancienneté** ?"*

Un seuil cosinus, aussi élevé soit-il, ne sépare pas ces cas : la distribution des scores pour les paires servables et les paires non-servables se chevauche presque entièrement.

---

## Solution : juge LLM binaire

Avant de servir une réponse canonique sans revue humaine, le pipeline appelle `garde_cache.approuver(question_posee, question_indexee)`. Le juge pose une question simple au LLM :

> *Ces deux questions expriment-elles exactement la même demande ?*

La réponse attendue est **OUI** ou **NON**. Toute réponse autre que `"OUI"` exact (insensible à la casse) est traitée comme un refus. Une exception ou un timeout est également un refus. Le garde est conservateur par construction : le moindre doute envoie la question au pipeline RAG.

---

## Flux dans le pipeline

```
Candidat canonique trouvé (score ≥ SEUIL_COSINUS)
        │
        ▼
Récupérer la question indexée
(Ticket.question ou Reponse.question_suivi selon le type de réponse)
        │
        ▼
Court-circuit : question posée ≡ question indexée ?
(normalisation : casse, ponctuation, espaces — pas les accents)
        │
        ├─── oui ──► OUI, sans appel LLM
        │
        └─── non
              │
              ▼
        Appel LLM (ALBERT_GARDE_MODEL_NAME)
              │
              ├─── "OUI" exact ──► CANONIQUE servie
              │
              └─── tout le reste ──► pipeline RAG complet
```

---

## Cas du suivi (fil de conversation)

Quand l'utilisateur envoie une précision dans un fil existant, la question brute est souvent elliptique : *"et pour un apprenti ?"*, *"dans ce cas ?"*. Comparer cette demi-phrase à une question indexée complète produirait un refus systématique.

Le garde reçoit donc `requete_recherche` à la place de `question` pour les suivis. `requete_recherche` est la concaténation de toutes les questions du fil dans l'ordre chronologique :

```
Quel est le préavis de licenciement ?
Et pour un apprenti ?
```

Le juge peut alors évaluer l'équivalence dans son contexte réel.

---

## Configuration

| Variable `.env` | Défaut | Description |
|---|---|---|
| `ALBERT_GARDE_MODEL_NAME` | *(vide)* | Modèle LLM dédié au garde. Si vide, utilise `ALBERT_LLM_MODEL_NAME`. |

Utiliser un modèle dédié est recommandé : Albert applique ses quotas (jetons et requêtes) par modèle. Partager le modèle de génération laisse les appels de génération épuiser le quota du garde.

⚠️ **Un quota épuisé est silencieux.** Le garde n'a pas de verdict « indisponible » :
`approuver()` renvoie un booléen, et toute exception — dont un `429` d'Albert — devient
`False`, donc un refus. Un quota vidé se manifeste par des questions qui basculent
massivement en RAG, **sans message d'erreur ni trace distinctive en base**. Devant une
chute inexpliquée du taux de réponses canoniques, vérifier les quotas avant de suspecter
le prompt.

---

## Implémentation

```python
# backend/app/services/garde_cache.py

def approuver(question_posee: str, question_indexee: str) -> bool:
    # Court-circuit : identité typographique
    if _normaliser(question_posee) == _normaliser(question_indexee):
        return True

    # Appel LLM
    verdict = chat(messages, temperature=0, max_tokens=5, model=modele)
    return verdict.strip().upper() == "OUI"
    # Exception → False
```

`_normaliser` met en minuscules, supprime la ponctuation et normalise les espaces. Elle ne supprime pas les accents : "congé" et "conge" ne sont pas typographiquement identiques et doivent passer par le juge.

Le paramètre `max_tokens=5` limite la réponse à un mot. `temperature=0` supprime toute variabilité.

---

## Ce que le garde ne fait pas

- Il **ne lit pas la réponse** — il compare uniquement deux questions. Cela évite que le juge rationalise une réponse inadaptée au lieu de la bloquer.
- Il **ne cherche pas dans les documents** — aucun appel Qdrant, aucun reranking.
- Il **ne distingue pas les raisons de refus** — tout ce qui n'est pas OUI va en RAG. Il n'y a pas de valeur intermédiaire.
