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

Avant de servir une réponse canonique sans revue humaine, le pipeline appelle `garde_cache.statuer(question_posee, question_indexee, est_suivi=…)`. Le juge pose une question simple au LLM :

> *Ces deux questions expriment-elles exactement la même demande ?*

La réponse attendue est **OUI** ou **NON**. Toute réponse autre que `"OUI"` exact (insensible à la casse) est traitée comme un refus. Une exception ou un timeout est également un refus. Le garde est conservateur par construction : le moindre doute retire la réponse du service sans revue.

`statuer` renvoie une `Decision` (`verdict`, `court_circuit`, `modele`, `erreur`) — de quoi journaliser dans `garde_decisions` et distinguer un OUI de court-circuit d'un OUI jugé, un NON jugé d'un NON par indisponibilité d'Albert. `approuver()` reste disponible comme enveloppe booléenne pour les tests et scripts de calibration.

---

## Flux dans le pipeline

```
Candidat canonique trouvé (score ≥ SEUIL_COSINUS)
        │
        ▼
Récupérer la question indexée
(payload `question_indexee` du point qui a matché ;
 repli Ticket.question / Reponse.question_suivi pour les points anciens)
        │
        ▼
Court-circuit : question posée ≡ question indexée ?
(normalisation : casse, ponctuation, espaces — pas les accents)
        │
        ├─── oui ──► OUI, sans appel LLM ──► CANONIQUE servie
        │
        └─── non
              │
              ▼
        Appel LLM (ALBERT_GARDE_MODEL_NAME)
              │
              ├─── "OUI" exact ──► CANONIQUE servie
              │
              └─── tout le reste ──► SUGGESTION (revue humaine)
```

**Le refus ne renvoie pas au RAG, il rend la réponse à la branche SUGGESTION.** Le garde répond à une seule question : *peut-on servir ceci sans qu'un humain le relise ?* Un NON disqualifie le service sans revue — pas la proposition au relecteur, qui reste libre de la corriger ou de la rejeter.

Sans ce repli, le système était **non monotone** : un candidat à 0,84 sortait en SUGGESTION sans être jugé, alors que le même à 0,86 était soumis au garde et, sur refus, renvoyé au RAG *sans candidat*. Franchir `SEUIL_COSINUS` dégradait donc l'issue, ce qui contredit son rôle de simple filtre de coût. Mesuré le 05/09/2026 : trois candidats avaient perdu leur SUGGESTION en passant le seuil de 0,90 à 0,85.

Le refus reste tracé dans `garde_decisions` : la SUGGESTION servie est indiscernable en base d'une SUGGESTION de la branche 2, seule la table d'audit dit qu'un juge est passé.

---

## Cas du suivi (fil de conversation)

Quand l'utilisateur envoie une précision dans un fil existant, la question brute est souvent elliptique : *"et pour un apprenti ?"*, *"dans ce cas ?"*. Comparer cette demi-phrase à une question indexée complète produirait un refus systématique.

Le garde reçoit donc `requete_recherche` à la place de `question` pour les suivis. `requete_recherche` est la concaténation de toutes les questions du fil dans l'ordre chronologique :

```
Quel est le préavis de licenciement ?
Et pour un apprenti ?
```

Le juge peut alors évaluer l'équivalence dans son contexte réel.

**Le juge reçoit un prompt système distinct en mode suivi** (`_PROMPT_SYSTEME_SUIVI`). Sans lui, il compare deux questions empilées à une question unique, ce qui ne peut pratiquement jamais « exprimer exactement la même demande » : le refus devenait un artefact de format et non un jugement. Mesuré le 05/09/2026 sur la FAQ DFE : **5 refus sur 5 précisions réelles**, dont un seul justifié. Le prompt dédié lui indique que la dernière ligne est la demande et que les précédentes ne servent qu'à lever les références implicites.

**Le court-circuit typographique est désactivé en mode suivi.** Comparer un fil entier à une question unique n'a pas de sens, et ne comparer que sa dernière ligne reviendrait à servir une réponse canonique après avoir jeté le contexte qui la rend sûre.

---

## Configuration

| Variable `.env` | Défaut | Description |
|---|---|---|
| `ALBERT_GARDE_MODEL_NAME` | *(vide)* | Modèle LLM dédié au garde. Si vide, utilise `ALBERT_LLM_MODEL_NAME`. |

Utiliser un modèle dédié est recommandé : Albert applique ses quotas (jetons et requêtes) par modèle. Partager le modèle de génération laisse les appels de génération épuiser le quota du garde.

⚠️ **Un quota épuisé ne produit pas d'erreur visible côté utilisateur.** Le garde n'a pas
de verdict « indisponible » : toute exception — dont un `429` d'Albert — devient un refus.
Un quota vidé se manifeste par une chute du taux de réponses canoniques, les questions
basculant massivement en SUGGESTION. **La distinction se lit dans `garde_decisions`** :
`Decision.erreur` y est journalisée, et un refus par indisponibilité s'y sépare d'un refus
jugé. Devant une chute inexpliquée, interroger cette table avant de suspecter le prompt.

---

## Implémentation

```python
# backend/app/services/garde_cache.py

def statuer(question_posee, question_indexee, *, est_suivi=False) -> Decision:
    # Court-circuit : identité typographique — hors suivi uniquement
    if not est_suivi and _normaliser(question_posee) == _normaliser(question_indexee):
        return Decision(verdict=True, court_circuit=True)

    modele = settings.albert_garde_model_name or settings.albert_llm_model_name
    messages = [
        {"role": "system", "content": _PROMPT_SYSTEME_SUIVI if est_suivi else _PROMPT_SYSTEME},
        {"role": "user", "content": f"Question A : {question_posee}\nQuestion B : {question_indexee}"},
    ]
    try:
        verdict = chat(messages, temperature=0, max_tokens=20, model=modele)
        return Decision(verdict=verdict.strip().upper() == "OUI", modele=modele)
    except Exception as exc:
        return Decision(verdict=False, modele=modele, erreur=str(exc)[:500])
```

`_normaliser` met en minuscules, supprime la ponctuation et normalise les espaces. Elle ne supprime pas les accents : "congé" et "conge" ne sont pas typographiquement identiques et doivent passer par le juge.

Le paramètre `max_tokens=20` laisse la place à un mot de verdict même si le modèle le préfixe ; `temperature=0` supprime toute variabilité. Le modèle est lu **à l'appel**, pas à l'import : un banc peut changer de juge par variable d'environnement sans éditer un `.py` (ce qui relancerait `watchmedo` et tuerait la passe en cours).

---

## Ce que le garde ne fait pas

- Il **ne lit pas la réponse** — il compare uniquement deux questions. Cela évite que le juge rationalise une réponse inadaptée au lieu de la bloquer.
- Il **ne cherche pas dans les documents** — aucun appel Qdrant, aucun reranking.
- Il **ne distingue pas les raisons de refus** — tout ce qui n'est pas OUI sort en SUGGESTION. Il n'y a pas de verdict intermédiaire ; `Decision.erreur` sert l'audit, pas le routage.
- Il **ne choisit pas la question B** — celle-ci lui est fournie par le point Qdrant qui a matché (voir ci-dessous). Le garde ne peut pas rattraper une mauvaise paire.

---

## Quelle question B est jugée

Une réponse est indexée sous **une question par formulation validée par un humain**, chacune sur son propre point Qdrant (`feedback_job(source_id, formulation_id)`). Le garde doit juger la paire **réellement retrouvée** : la question B est lue dans le payload `question_indexee` du point qui a matché, transportée par `search_hybrid` puis `trouver_reponse_reutilisable`.

La redériver de `Ticket.question` — ce que faisait le code avant — soumettrait au juge la question d'origine alors que la recherche a matché sur un alias, donc une paire que rien n'a produite. Les points écrits avant l'introduction des formulations multiples n'ont pas cette clé ; l'appelant retombe alors sur `Ticket.question` / `Reponse.question_suivi`.

Ce mécanisme élargit la couverture du cache sans toucher aux seuils : mesuré le 05/09/2026, indexer *une* formulation validée fait passer « Comment déclarer un service fait ? » de 0,8418 (SUGGESTION) à 1,0000 (CANONIQUE), et — effet de bord recherché — une formulation que **personne n'a validée**, « Comment procède-t-on pour constater un service fait ? », de 0,8394 à 0,8744, franchissant le seuil elle aussi. Le gain déborde donc au-delà des formulations validées : c'est précisément là que le garde sert de filet, et il a bien été consulté sur les deux.
