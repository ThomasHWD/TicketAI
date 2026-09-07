# Test en condition réelle du cache sémantique

**Date** : 5 septembre 2026 · **Corpus** : FAQ réelle du DFE (11 paires question/réponse) · **Appels Albert réels**, aucun mock.

Ce rapport mesure une seule propriété, celle que le projet énonce comme règle :

> *Mieux vaut qu'une question repasse par le RAG que d'être servie à tort.*

Un **faux positif** — réponse canonique servie sans revue humaine à une question qui n'est pas la même — est une faute. Un **faux négatif** — question équivalente renvoyée au RAG — n'est qu'un coût. Les deux sont comptés séparément dans tout ce qui suit ; ils ne se compensent pas.

**Fichiers**
- `backend/scripts/seed_faq_dfe.py` — construit la fixture
- `backend/scripts/test_cache_semantique.py` — passes A et B
- `backend/scripts/resultats_passe_a.json`, `resultats_passe_b.json` — résultats bruts

> **Lire d'abord ceci.** Les sections 1 à 9 mesurent le système **tel qu'il était** le
> 5 septembre 2026 au matin (`SEUIL_COSINUS=0,90`, prompt de garde unique). Les constats du
> § 7 ont donné lieu à des correctifs le jour même ; la **§ 10 remesure après correctifs** et
> corrige deux affirmations devenues fausses : le refus du garde cité en exemple au § 4
> était un artefact de format, et le décompte « 1 refus du juge sur 48 » ne vaut plus.

---

## Résumé

| Résultat | Avant correctifs (§ 1-9) | Après correctifs (§ 10) |
|---|---|---|
| **Faux positifs (servi sans revue une réponse hors cible)** | **0 / 48** en chaîne complète, **0 / 17** en interrogation directe du juge | **0 / 48** |
| Réponses servies en CANONIQUE | 8 / 48 | 14 / 48 |
| Faux négatifs (RAG ou SUGGESTION alors qu'équivalent) | 7 / 48 | 5 / 48, dont 3 en SUGGESTION (donc revus) |
| Concordance passe A (rejeu) ↔ passe B (vraie file Celery) | **12 / 12**, scores identiques à 7 décimales | **12 / 12** |
| Appels au juge réellement émis en passe A | **7 sur 48 cas** | 15 sur 48 |
| Refus corrects dus à la recherche vs au juge | **28 vs 1** — et ce « 1 » était un artefact (§ 4) | **20 vs 2** — deux vrais jugements |
| Précisions (suivis) servies par le cache | **0 sur 11** précisions réelles | 3 sur 11 |

**La propriété de sûreté tient.** Aucune réponse canonique n'a été servie à tort, sur aucun cas, dans aucune des trois campagnes.

**Mais elle n'est pas produite par le garde.** Le garde a tranché une fois sur quarante-huit. Ce qui protège aujourd'hui le système, c'est le seuil cosinus — c'est-à-dire précisément le mécanisme dont `garde-cache-canonique.md` explique qu'il ne peut pas faire ce travail :

> *« Un seuil cosinus, aussi élevé soit-il, ne sépare pas ces cas : la distribution des scores pour les paires servables et les paires non-servables se chevauche presque entièrement. »*

La mesure confirme ce chevauchement (§ 5). Le seuil actuel s'en tire en refusant tout ce qui est ambigu, garde et cas légitimes compris. Interrogé directement sur les 17 paires que la chaîne ne lui a jamais soumises, le juge s'est montré **strictement plus discriminant que le seuil** : 12 verdicts justes, 5 refus excessifs, **zéro approbation dangereuse** (§ 6).

---

## 1. Protocole

### Fixture

La FAQ du DFE fournit exactement la forme que le cache indexe — une question humaine, une réponse humaine — et porte des grappes adverses qu'on n'aurait pas su inventer. Tout est écrit sous un domaine dédié `DFE`, isolé du corpus de démo `IT` par le filtre strict de `search_hybrid` (`app/services/search.py:49`).

La fixture est construite par les **vrais** chemins de production, pas par écriture directe en base :

- le document de repli (`.md` bâti à partir des réponses) passe par `ingestion_job` ;
- les 11 réponses validées passent par `feedback_job`, qui indexe le vecteur de la **question** avec un payload `reponse_id`.

Vérification après seed, par `scroll` Qdrant filtré sur `domaine=DFE` :

```
points DFE : 19  |  points réponse : 11  |  chunks document : 8
```

8 réponses canoniques (`nb_validations=3`) : F1, F2, F3, F5, F6, F7, F8, F10.
3 validées non canoniques (`nb_validations=1`) : F4, F9, F11 — elles rendent la branche SUGGESTION exerçable.
3 fils de suivi, dont les réponses initiales restent `EN_ATTENTE` et ne passent jamais par `feedback_job` : le fil sert de contexte sans devenir lui-même candidat du cache.

> **Écart relevé sur la fixture existante.** Avant ce test, la branche CANONIQUE était *structurellement inatteignable* : Qdrant ne contenait qu'un seul point réponse, pointant vers une réponse non canonique. Les deux réponses canoniques en base n'avaient aucun point Qdrant, parce que `scripts/seed_demo_doc.py:202-213` écrit `canonique=True` directement en base **sans jamais appeler `feedback_job`**. Sur ces données, 100 % des questions partent en RAG et tout test du cache prouverait le vide. C'est un défaut du script de démo, pas du pipeline.

### Configuration effective, relevée depuis le conteneur

Pas depuis `.env` : `env_file:` est lu à la *création* du conteneur et prime sur le fichier monté.

| Paramètre | Valeur |
|---|---|
| `SEUIL_COSINUS` | `0.9` |
| `SEUIL_SUGGESTION` (dérivé) | `0.85` |
| `SEUIL_CANONIQUE` | `3` |
| Modèle du garde | `gemma-4-31b-it` — dédié, compteur distinct |
| Modèle de génération | `openai/gpt-oss-120b` |
| Reranker | `BAAI/bge-reranker-v2-m3` |
| Embeddings | `BAAI/bge-m3` |

### Les trois campagnes

| | Ce qui est mesuré | Cas | Écrit ? |
|---|---|---|---|
| **Passe A** | Décision de branche, rejeu littéral de `workers/question.py:65-110`, arrêt avant rerank et génération | 48 | non |
| **Passe B** | Bout en bout par la vraie file Celery, `Reponse.source` relu en base | 12 | oui |
| **Sonde juge** | `approuver()` interrogé directement sur les paires que la chaîne ne lui soumet jamais | 17 | non |

`approuver` est enveloppé d'un compteur d'appels, pour distinguer un « OUI » du juge d'un « OUI » du court-circuit typographique (0 appel LLM).

---

## 2. Passe A — décision de branche (48 cas)

```
CANONIQUE 8   ·   SUGGESTION 11   ·   RAG 29
Conformes à l'attendu : 36/48
FAUX POSITIFS : 0
```

| Famille | Contenu | Conformes |
|---|---|---|
| A | 10 reformulations équivalentes, attendu CANONIQUE | 5/10 |
| B | 14 questions proches mais différentes, attendu RAG | 12/14 |
| C | 4 variantes typographiques, attendu CANONIQUE sans appel LLM | 2/4 |
| D | 12 précisions dans un fil de suivi | 9/12 |
| E | 3 réponses validées non canoniques, attendu SUGGESTION | 3/3 |
| F | 5 hors périmètre, dont 2 sondes d'isolation inter-domaines | 5/5 |

**Isolation** : les 5 cas de la famille F plafonnent à 0,588 et ne remontent jamais un point du corpus `IT`, y compris sur deux questions tirées littéralement de ce corpus (« télétravail », « tickets restaurant » : 0,471 et 0,526). Le filtre de domaine tient.

**Branche SUGGESTION** : les 3 cas de la famille E sortent bien en SUGGESTION, avec `bloque_par=NON_CANONIQUE` et **compteur de garde à zéro**. Le garde n'est pas appelé sur cette branche, conformément à la conception.

### Les 12 cas non conformes

Aucun n'est un défaut de sûreté. Ils se répartissent en trois causes.

**a) 7 faux négatifs — équivalents renvoyés au RAG.** Coût, pas faute. Détaillés au § 5, ils sont tous récupérables sauf un (§ 6).

**b) 3 précisions sorties en SUGGESTION là où j'attendais RAG.** SUGGESTION passe par une revue humaine : sur le critère du projet — servi sans revue, ou revu — ce sont des issues sûres. Mon attendu était trop strict.

**c) 2 cas de la famille B sortis en SUGGESTION.** Même remarque, et l'un des deux mérite d'être relevé pour la bonne raison : « Mes frais de mission ne m'ont pas été remboursés » a remonté **F8** (0,8987), c'est-à-dire la bonne entrée. Le validateur se voit proposer la bonne réponse. C'est le comportement souhaitable.

---

## 3. Passe B — bout en bout, vraie file Celery

12 questions poussées par `question_job.delay(...)`, `Reponse.source` relu en base.

| Question | Passe A (rejeu) | Passe B (`Reponse.source`) | Score |
|---|---|---|---|
| Quelle est la procédure pour saisir un engagement de dépense ? | SUGGESTION | SUGGESTION | 0,8892813 |
| Comment déclarer un service fait ? | RAG | LLM | 0,8418486 |
| Mes frais de mission ne m'ont pas été remboursés… | SUGGESTION | SUGGESTION | 0,8987203 |
| Mon fournisseur n'a pas été payé, dois-je prévenir la mission Budget ? | RAG | LLM | 0,7039559 |
| Comment fait-on un service fait partiel ? | RAG | LLM | 0,7849973 |
| Faut-il un engagement de dépense pour une visite médicale ? | RAG | LLM | 0,8398646 |
| Un SMS suffit-il comme justificatif de demande d'engagement ? | RAG | LLM | 0,6984417 |
| Y a t il un modèle de certificat administratif ? | SUGGESTION | SUGGESTION | 0,9999999 |
| comment fait on un engagement de dépense | CANONIQUE | **CANONIQUE** | 0,9762497 |
| Comment poser mes congés payés ? | RAG | HORS_DOMAINE | 0,5795031 |
| Quelle est la valeur des tickets restaurant ? | RAG | HORS_DOMAINE | 0,5261884 |
| J'ai une dépense que je n'avais pas prévue, comment procéder ? | CANONIQUE | **CANONIQUE** | 0,9365327 |

**Concordance 12/12**, scores identiques à la septième décimale. Le rejeu de la passe A est fidèle à la production ; les 48 cas de la passe A sont donc exploitables tels quels.

Deux observations que seule la passe B pouvait produire :

- **Les réponses CANONIQUE sortent directement en `statut=VALIDÉE`.** C'est bien ce que « servi sans revue humaine » signifie, mais cela confirme qu'un faux positif serait immédiatement visible par l'utilisateur, sans filet.
- **Une quatrième branche existe : `HORS_DOMAINE`.** Elle n'apparaît pas dans `CLAUDE.md`. Le LLM émet lui-même un marqueur `[HORS_DOMAINE]` (`services/llm.py:48`) quand le contexte ne porte pas la réponse, et `question.py:169` l'enregistre comme source. Sur les 2 questions hors périmètre, le système **s'est abstenu** au lieu d'inventer. C'est le bon comportement et il mérite d'être documenté.

### Qualité des réponses générées (branche RAG)

Comparées à la réponse FAQ de référence :

| Question | Verdict | Détail |
|---|---|---|
| Mon fournisseur n'a pas été payé, dois-je prévenir la mission Budget ? | **correcte** | Reproduit la procédure F5 (certificat Chorus, `sfact@onacvg.fr`) *et* répond à la question fermée : « il n'est pas nécessaire d'informer la mission Budget ». Servir F5 telle quelle n'aurait pas répondu au « dois-je ». |
| Faut-il un engagement de dépense pour une visite médicale ? | **correcte** | Mène avec le cas visite médicale (aucun engagement, facture à `sfact@`) et conserve la nuance cotisation annuelle. Meilleure que F6 servie brute. |
| Un SMS suffit-il comme justificatif ? | **correcte, avec réserve** | Conclut « Non » en dérivant les quatre critères de F9. Le raisonnement est exposé et juste, mais le corpus n'énonce pas cette règle pour le SMS : c'est une extrapolation assumée un peu trop fermement. |
| Comment déclarer un service fait ? | **partielle** | URL et principe exacts (F2). Mais invente le détail du formulaire (« référence de la commande et du bon de livraison », « quantités livrées ») et transpose au service fait une consigne d'archivage qui, dans le corpus, appartient à F1. |
| Comment fait-on un service fait partiel ? | **partielle** | Fusionne correctement F2 et F10. Invente en revanche un « champ dédié au solde » avec une option « restitué » — F10 dit d'*indiquer* que le solde doit être restitué, sans décrire d'interface — et des exemples de justificatifs (« rapport d'inspection »). |
| Comment poser mes congés payés ? | **abstention** | `HORS_DOMAINE`, renvoi vers les RH. |
| Quelle est la valeur des tickets restaurant ? | **abstention** | idem. |

**3 correctes, 2 partielles, 2 abstentions, 0 franchement fausse.**

Le défaut récurrent est unique et identifiable : **l'invention assurée de micro-détails opérationnels** (champs de formulaire, options d'interface, pièces à joindre). Le fond est juste, la mise en scène procédurale est fabriquée. Ces réponses sont toutes `EN_ATTENTE` et passent en revue humaine — c'est exactement ce que la revue est là pour attraper. Le risque ne deviendrait réel que si l'une d'elles atteignait le seuil canonique après trois validations distraites.

---

## 4. Qui refuse : le seuil ou le juge ?

C'est le résultat le plus utile du test.

Répartition des causes de blocage sur les 48 cas :

| Cause | Nombre | Sens |
|---|---|---|
| `AUCUN_CANDIDAT` | 28 | La recherche n'a rien remonté au-dessus de `SEUIL_SUGGESTION` (0,85) |
| `SEUIL` | 8 | Candidat canonique trouvé, mais sous `SEUIL_COSINUS` (0,90) → SUGGESTION |
| `NON_CANONIQUE` | 3 | Candidat validé non canonique → SUGGESTION |
| `GARDE` | 1 | **Le juge a dit NON** |
| aucun blocage | 8 | CANONIQUE servi |

Sur les 29 refus corrects (cas attendus en RAG et sortis en RAG) : **28 viennent de la recherche, 1 du juge.**

**Le juge a été appelé 7 fois sur 48 cas**, dont 6 pour approuver et 1 pour refuser. Deux CANONIQUE de plus ont été obtenus par court-circuit typographique, sans aucun appel LLM.

Le seul refus du juge mérite d'être cité en entier, parce que c'est le cas d'école de la grappe « Que dois-je faire ? » :

```
Fil        : « Ma facture n'est pas réglée, mon fournisseur me relance. Que dois-je faire ? »
Précision  : « mes frais de déplacement ne sont pas remboursés non plus, que faire ? »
Candidat   : F8, score 0,9785 — au-dessus du seuil, canonique
Verdict    : NON  →  RAG
```

Le seuil laissait passer. Le juge a vu que le fil et la question indexée ne portaient pas la même demande et a refusé. **C'est exactement le rôle pour lequel il a été conçu, et il l'a rempli.** Une seule fois sur quarante-huit.

> ⚠️ **Cette lecture est fausse, et le § 6 le démontre trois paragraphes plus loin.** La
> précision « mes frais de déplacement ne sont pas remboursés non plus, que faire ? » est
> autonome : « non plus » n'ajoute aucune condition, et elle redit F8 mot pour mot. Le juge
> n'a pas vu une différence de demande, il a vu **deux questions empilées face à une
> question unique** — le même artefact de format qui lui a fait refuser les 5 précisions du
> § 6. Une fois doté d'un prompt de suivi dédié (§ 10), il approuve ce cas. Le seul refus du
> juge mesuré en chaîne complète n'était donc pas un jugement : c'était un bug de prompt qui
> se trouvait tomber du côté sûr.

---

## 5. Distribution des scores : le chevauchement est réel

| Famille | min | max |
|---|---|---|
| A — équivalentes | 0,8057 | 0,9934 |
| B — proches mais différentes | 0,6551 | 0,8987 |
| C — variantes typographiques | 0,6343 | 1,0000 |
| D — précisions | 0,5694 | 0,9978 |
| E — SUGGESTION | 0,9485 | 1,0000 |
| F — hors périmètre | 0,4710 | 0,5881 |

La famille F se sépare nettement (< 0,59) : un seuil suffit à écarter le hors-sujet franc.

**Mais A et B se chevauchent sur toute la bande 0,80–0,90.** Quinze cas y tombent, appartenant à quatre familles différentes. Aucune valeur de `SEUIL_COSINUS` ne les sépare :

```
0,8987  B  frais de mission non remboursés          → F8   (équivalent en fait)
0,8893  A  procédure pour saisir un engagement      → F1   (équivalent)
0,8872  C  « depense » sans accent                  → F1   (équivalent)
0,8841  A  récupérer le reliquat                    → F10  (condition en moins)
0,8827  D  et pour un engagement de dépense ?       → F1   (dérive du fil)
0,8683  D  et si la dépense concerne la médecine…   → F6   (équivalent)
0,8609  B  … dois-je contacter le service facturier ? → F8 (périmètre réduit)
0,8524  D  peut-on la faire en monnaie étrangère ?  → F3   (équivalent)
0,8418  A  comment déclarer un service fait ?       → F2   (équivalent)
0,8399  B  engagement pour une visite médicale ?    → F6   (sous-cas)
0,8394  A  constater un service fait                → F2   (équivalent)
0,8331  D  et si ce sont mes frais de déplacement ? → F8   (équivalent)
0,8254  B  qui valide un engagement de dépense ?    → F1   (qui ≠ comment)
0,8057  A  engager une dépense dans une autre monnaie → F3 (équivalent)
0,8030  D  et en monnaie étrangère ?                → F3   (équivalent)
```

### Le score n'est pas comparable d'une entrée à l'autre

C'est la cause profonde des faux négatifs, et elle n'est pas dans le garde.

| Entrée | Question indexée | Scores de ses reformulations |
|---|---|---|
| F1 | « Comment fait on un engagement de dépense ? » | 0,8893 · 0,9831 · 0,9762 · 1,0000 |
| F2 | « Comment fait on un service fait ? » | 0,8418 · 0,8394 · 0,7850 · 0,6343 |

**F2 n'a jamais franchi le seuil, sur aucune de ses quatre reformulations.** Une sonde de recherche montre pourtant que le point F2 est **systématiquement le premier résultat** :

```
Comment fait on un service fait ?          → 1,0000  RÉPONSE F2
Comment déclarer un service fait ?         → 0,8418  RÉPONSE F2
COMMENT FAIT ON UN SERVICE FAIT ???        → 0,6343  RÉPONSE F2
```

La recherche ne se trompe pas : sur les 9 cas sous-seuil sondés, **le premier résultat est un point réponse, et c'est la bonne entrée FAQ, dans 9 cas sur 9**. Ce n'est donc pas un problème de rappel mais de **calibration** : `SEUIL_COSINUS` est une constante globale appliquée à des distributions de score propres à chaque question indexée. Une question courte et générique comme « Comment fait on un service fait ? » produit un vecteur fragile ; ses reformulations perdent 0,15 quand celles de F1 en perdent 0,02.

### Le court-circuit typographique est inatteignable dans la chaîne

`garde_cache._normaliser` retire casse, ponctuation et espaces multiples pour servir une répétition exacte sans appel LLM. Il fonctionne — interrogé directement, `approuver("COMMENT FAIT ON UN SERVICE FAIT ???", "Comment fait on un service fait ?")` renvoie **OUI sans appel LLM**.

Mais il ne sera jamais consulté sur ce cas. `search_hybrid` embarque la question **brute**, non normalisée (`question.py:73`), et `trouver_reponse_reutilisable` écarte tout ce qui est sous 0,85 **avant** que `approuver` n'existe. Passer en majuscules avec trois points d'interrogation fait chuter le cosinus de 1,0000 à 0,6343 : le candidat est éliminé deux étages plus bas.

Le court-circuit ne fonctionne donc que pour les variantes que l'embedding tolère déjà (espaces multiples : 1,0000 ; ponctuation finale absente : 0,9762). Pour la casse et la ponctuation lourde — précisément ce qu'il est censé absorber — **il est mort dans la chaîne**.

---

## 6. Que déciderait le garde si on le laissait décider ?

Puisque le seuil court-circuite le juge 41 fois sur 48, je lui ai soumis directement les 17 paires que la chaîne ne lui a jamais présentées : les 8 de la bande 0,85–0,90 et 9 sous 0,85.

**Résultat : 12 verdicts justes sur 17, et surtout — zéro « OUI » sur une paire non équivalente.** Les 5 écarts sont **tous** des « NON » là où j'attendais « OUI », c'est-à-dire tous du côté sûr.

Les 5 refus excessifs ont deux causes, toutes deux explicables :

**a) Une condition présente dans la question indexée et absente de la question posée (1 cas).**

```
posée   : « Puis-je récupérer le reliquat d'un engagement que je n'utiliserai pas ? »
indexée : « La prestation n'a été effectuée intégralement et/ou moins chère que prévue,
            puis je récupérer le reliquat d'engagement que je n'utiliserai pas ? »
verdict : NON
```

Le prompt du juge liste explicitement « condition supplémentaire » comme motif de refus. **Le verdict est correct ; c'est mon attendu qui était faux.**

**b) Le mode suivi (4 cas) — et c'est un constat de conception.**

En mode suivi, le juge reçoit `requete_recherche`, c'est-à-dire le **fil concaténé** (`question.py:95`), et le compare à une question indexée unique :

```
posée   : « Comment fait on un engagement de dépense ?\net si la dépense concerne
            la médecine de prévention ? »
indexée : « Faut il faire un engagement de dépense pour la médecine de prévention ? »
verdict : NON
```

Deux questions empilées ne peuvent pratiquement jamais « exprimer exactement la même demande » qu'une question unique. **Sur les 5 précisions réelles soumises au juge, il a répondu NON 5 fois** — dont une seule à raison.

### Conséquence : les précisions ne bénéficient jamais du cache

C'était l'une des deux questions posées au départ. La réponse est nette.

Sur les 11 précisions authentiques testées (famille D, hors répétition littérale) : **0 ont été servies en CANONIQUE**. Sept n'ont même pas remonté de candidat au-dessus du seuil ; les quatre autres ont été refusées, par le seuil ou par le juge.

Le seul CANONIQUE de la famille D est le cas où la précision **répète mot pour mot la question initiale du fil** — la concaténation vaut alors « Q\nQ », et le juge reconnaît Q. Ce n'est pas une précision, c'est une répétition.

**Le cache canonique est donc de fait fermé aux précisions.** C'est sûr — aucun risque de servir à tort dans un fil — mais c'est une fermeture structurelle, non un arbitrage cas par cas. Le comportement observé est conforme à la règle du projet ; il ne correspond pas à ce que la conception du mode suivi laisse attendre.

### Simulation chiffrée d'un seuil abaissé

Verdicts mesurés, pas extrapolés :

| Configuration | CANONIQUE | Faux positifs | Faux négatifs | Appels juge / 48 |
|---|---|---|---|---|
| Actuelle (0,85 / 0,90) | 8 | **0** | 7 | 7 |
| `SEUIL_COSINUS` → 0,85 | 11 | **0** | 4 | 15 |
| + plancher de recherche → 0,80 | 14 | **0** | 1 | 22 |

Abaisser les deux seuils récupère **6 des 7 faux négatifs sans produire un seul faux positif mesuré**, parce que sur les 15 cas nouvellement soumis au juge, celui-ci refuse correctement les 7 pièges (question fermée, sous-cas de F6, « qui » vs « comment », dérives de fil) et approuve les équivalents.

Le septième faux négatif — la variante en majuscules à 0,6343 — n'est récupérable par aucun seuil raisonnable. Il relève d'un correctif de code, pas de calibration.

Coût : le juge passerait de 7 à ~22 appels pour 48 questions, soit ~46 %. Sur un modèle dédié plafonné à 1 000 requêtes/jour, cela autorise encore de l'ordre de 2 000 questions quotidiennes. **Le budget n'est pas le facteur limitant.**

---

## 7. Constats

Classés par ce qu'ils coûtent.

1. **La règle de sûreté du projet est respectée** — 0 faux positif sur 48 cas en chaîne complète, 0 approbation dangereuse sur 17 interrogations directes du juge, y compris sur la grappe adverse « Que dois-je faire ? » où une confusion enverrait l'agent au mauvais service.

2. **Le garde ne porte pas la décision : le seuil la porte à sa place, et moins bien.** 28 refus corrects sur 29 viennent de la recherche, 1 du juge. Or `garde-cache-canonique.md` explique lui-même qu'un seuil cosinus ne peut pas séparer les paires servables des autres. La mesure lui donne raison (§ 5) : la configuration actuelle contredit sa propre justification.

3. **`SEUIL_COSINUS` est une constante globale appliquée à des échelles de score locales.** F1 tolère ses reformulations (0,89–1,00), F2 les perd toutes (0,63–0,84), alors que la recherche identifie correctement l'entrée cible dans 9 cas sur 9. Une entrée FAQ peut ainsi devenir invisible au cache pour la seule raison que sa question indexée est courte.

4. **Le cache est fermé aux précisions.** 0 sur 11. Le juge reçoit un fil concaténé de deux questions et le compare à une question unique : l'équivalence est structurellement inatteignable. Comportement sûr, mais qui n'est pas un arbitrage.

5. **Le court-circuit typographique est mort dans la chaîne.** Il fonctionne en isolation, mais la recherche embarque la question brute et le filtre à 0,85 élimine les variantes de casse avant qu'il ne soit consulté.

6. **`seed_demo_doc.py:202-213` écrit `canonique=True` sans indexer.** Sur les données de démo, la branche CANONIQUE est inatteignable. C'est ce qui a rendu la fixture FAQ nécessaire.

7. **La branche `HORS_DOMAINE` n'est pas documentée** dans `CLAUDE.md`, qui n'annonce que trois branches. Elle s'est correctement déclenchée 2 fois sur 2 : le système s'abstient au lieu d'inventer.

8. **Les réponses RAG inventent des micro-détails opérationnels** avec assurance — champs de formulaire, options d'interface. Le fond reste juste. La revue humaine est là pour ça ; le risque n'existe que si de telles réponses accumulent trois validations et deviennent canoniques.

## 8. Pistes

Par ordre de rapport bénéfice/risque. *(État à la rédaction initiale : aucune appliquée. Voir § 10 pour ce qui l'a été depuis, et avec quel effet mesuré.)*

- **Abaisser `SEUIL_COSINUS` vers 0,85, voire le plancher de recherche vers 0,80**, et laisser le juge trancher la bande de recouvrement. Mesuré : 6 faux négatifs récupérés, 0 faux positif, coût en appels négligeable. C'est la modification la plus rentable, et celle qui rend au garde le rôle que la documentation lui assigne.
- **Normaliser la question avant l'embedding** (ou appliquer `_normaliser` avant le filtre de score), pour que le court-circuit typographique soit atteignable.
- **Revoir ce que le juge reçoit en mode suivi** : lui présenter la question reconstruite plutôt que le fil brut concaténé, ou adapter le prompt au cas « fil vs question unique ». Tant que ce point n'est pas traité, le cache restera fermé aux précisions.
- **Documenter la branche `HORS_DOMAINE`** dans `CLAUDE.md`.
- **Corriger `seed_demo_doc.py`** pour qu'il passe par `feedback_job`, sans quoi aucun test du cache sur les données de démo n'a de sens.

---

## 9. Coût réel et nettoyage

| Poste | Modèle | Appels |
|---|---|---|
| Seed (document + 11 réponses) | `BAAI/bge-m3` | ~13 |
| Passe A — recherche | `BAAI/bge-m3` | 48 |
| Passe A — garde | `gemma-4-31b-it` | 7 |
| Passe B — recherche / rerank / génération | bge-m3, reranker, `gpt-oss-120b` | 12 / 7 / 7 |
| Sonde juge (§ 6) | `gemma-4-31b-it` | 16 (17 paires, 1 court-circuit) |

Soit ≈ 73 appels `bge-m3`, ≈ 23 `gemma-4-31b-it`, ≈ 7 reranker, ≈ 7 `gpt-oss-120b`. Marge très large sur les deux compteurs Albert (1 000 requêtes et 1,28 M jetons par jour, **par modèle**).

**Données laissées en place** : 26 tickets `[TEST-CACHE]` (11 FAQ + 3 fils + 12 de la passe B), 11 réponses validées, 1 document `faq_dfe.md` (`doc_id=9d5baddd-8668-5a0a-8e54-70fe44d37eda`), 19 points Qdrant sous `domaine=DFE`. Tout est sous le domaine `DFE`, sans contact avec le corpus `IT`.

Suppression de la fixture :

```bash
docker exec -w /app -e PYTHONPATH=. ticketai-worker_ingestion-1 python scripts/seed_faq_dfe.py --purger
```

Les 12 tickets de la passe B ne sont pas couverts par `--purger` (identifiants Celery aléatoires) ; ils portent l'objet `[TEST-CACHE] passe B`.

---

## 10. Après correctifs — seconde mesure (même jour)

Les constats 1 à 8 ont donné lieu à cinq modifications, puis à un **rejeu intégral des 48 cas de la passe A et des 12 cas de la passe B**, sur la même fixture, avec les mêmes questions.

### Ce qui a été modifié

| # | Modification | Constat visé |
|---|---|---|
| 1 | `SEUIL_COSINUS` : 0,90 → **0,85** (`SEUIL_SUGGESTION` dérivé : 0,85 → 0,80) | 2, 3 |
| 2 | **Prompt de garde dédié au mode suivi** (`_PROMPT_SYSTEME_SUIVI`) : dit au juge que la dernière ligne du fil est la demande et que les précédentes ne servent qu'à lever les références implicites | 4 |
| 3 | **Court-circuit typographique désactivé en mode suivi** — comparer un fil entier à une question unique n'a pas de sens ; ne comparer que sa dernière ligne reviendrait à servir une réponse canonique après avoir jeté le contexte qui la rend sûre | 4, 5 |
| 4 | **Table d'audit `garde_decisions`** + `garde_cache.statuer()` renvoyant une `Decision` (verdict, court-circuit, modèle, erreur) au lieu d'un booléen | 2 — *le garde était indécidable a posteriori* |
| 5 | Consigne anti-fabrication dans le prompt système de génération (`services/llm.py`) : interdiction de décrire une étape, un champ de formulaire ou une pièce à fournir absents du contexte | 8 |
| 6 | `HORS_DOMAINE` documentée dans `CLAUDE.md` ; `seed_demo_doc.py` doté d'un `--indexer` qui passe par `feedback_job` | 6, 7 |

La piste « normaliser la question avant l'embedding » (constat 5) **n'a pas été appliquée** : elle touche le chemin d'indexation, donc invaliderait tous les vecteurs déjà en base.

### Passe A rejouée — 48 cas

```
AVANT (0,90)   CANONIQUE  8   SUGGESTION 11   RAG 29   ·   faux positifs 0   ·   appels juge  7
APRÈS (0,85)   CANONIQUE 14   SUGGESTION 10   RAG 24   ·   faux positifs 0   ·   appels juge 15
```

Le garde est passé de 7 à 15 appels, et de 1 refus à 3 — dont **2 comptent parmi les refus corrects** (contre 1 avant, qui n'en était pas un). La répartition des blocages devient `AUCUN_CANDIDAT` 21, `SEUIL` 7, `NON_CANONIQUE` 3, `GARDE` 3 : la recherche reste de très loin le premier filtre, mais le juge n'est plus décoratif.

**Zéro faux positif, sur les deux configurations.** Le critère employé ici n'est **pas** la colonne « branche attendue » — révisable, et de fait révisée — mais un critère objectif : *est un faux positif toute réponse servie sans revue humaine dont le candidat n'est pas l'entrée FAQ qui répond réellement à la question.* Sur les 14 CANONIQUE, le candidat servi est la bonne entrée **14 fois sur 14**.

### Les six CANONIQUE supplémentaires, et l'attribution honnête

Quatre d'entre eux tombaient sous `attendu=RAG`. Il faut dire d'où ils viennent avant de conclure.

| Cas | Score | Servi | Cause de la bascule |
|---|---|---|---|
| « Quelle est la procédure pour saisir un engagement de dépense ? » | 0,8893 | F1 | seuil (était SUGGESTION) |
| « Comment fait on un engagement de depense ? » *(sans accent)* | 0,8872 | F1 | seuil |
| « Mes frais de mission ne m'ont pas été remboursés, que dois-je faire ? » | 0,8987 | F8 | seuil |
| *fil-engagement* + « peut-on la faire en monnaie étrangère ? » | 0,8524 | F3 | seuil **et** prompt suivi |
| *fil-servicefait* + « et pour un engagement de dépense ? » | 0,8827 | F1 | seuil **et** prompt suivi |
| *fil-facture* + « mes frais de déplacement ne sont pas remboursés non plus, que faire ? » | 0,9785 | F8 | **prompt suivi seul** — c'est le cas cité au § 4 |

Les quatre premiers sont des reformulations ou des ellipses qui se résolvent sans ambiguïté :
« frais de mission » et « frais de déplacements » désignent la même chose ici — F8 renvoie
littéralement au service *missions déplacements* ; « peut-on **la** faire en monnaie
étrangère ? » n'a qu'un antécédent possible dans son fil et redevient F3 mot pour mot. Le
cinquième, « et pour un engagement de dépense ? » dans un fil portant sur le service fait,
est **le plus discutable** : « et pour X ? » après « comment fait-on Y ? » reporte
normalement le cadre interrogatif sur X — ce que le juge a fait, et F1 répond bien à la
question — mais une lecture concurrente existe (« un service fait est-il requis pour un
engagement ? »). Elle se dirait autrement, et le contrôle objectif tient : la réponse servie
répond à la question posée. **C'est néanmoins le cas à surveiller** : si une ellipse de cette
forme produit un jour un service hors cible, le correctif est une clause « en cas de lecture
multiple, réponds NON » dans `_PROMPT_SYSTEME_SUIVI`.

Les colonnes `attendu` de ces six cas ont été révisées dans le harnais, chacune avec le
motif inscrit en commentaire. **Ce n'est défendable que parce que le critère de faux positif,
lui, n'a pas bougé** — sans quoi ce serait blanchir une régression en réécrivant la cible.
Conformité après révision : **39/48** (contre 36 avant).

### Le coût du seuil abaissé : trois SUGGESTION perdues

Effet de bord qui n'était pas prévu, et qui découle de la conception : **un refus du garde n'a pas de repli SUGGESTION** (`question.py` — refus ⇒ pipeline RAG complet). Franchir `SEUIL_COSINUS` fait donc *sortir* un candidat de la branche SUGGESTION pour l'exposer au juge, qui peut le renvoyer au RAG.

| Question | Score | Avant | Après |
|---|---|---|---|
| « Puis-je récupérer le reliquat d'un engagement que je n'utiliserai pas ? » | 0,8841 | SUGGESTION | **RAG** (juge : NON) |
| « … dois-je contacter le service facturier ? » | 0,8609 | SUGGESTION | **RAG** (juge : NON) |
| *fil-engagement* + « et si la dépense concerne la médecine de prévention ? » | 0,8683 | SUGGESTION | **RAG** (juge : NON) |

Sur ces trois cas, le relecteur ne voit plus de candidat proposé. Les trois verdicts sont
défendables (F10 porte une condition absente de la question posée ; les deux autres
restreignent le périmètre), mais l'issue est moins utile qu'avant. Compensation : **six cas
gagnent une SUGGESTION** qu'ils n'avaient pas (F2 sur deux reformulations, F3, F6, F8, F1),
le solde net est positif. Le vrai enseignement est ailleurs :

> **Rendre à la branche SUGGESTION les réponses refusées par le garde** serait une
> amélioration franche — un refus signifie « pas la même demande », pas « candidat
> inutile pour le relecteur ».

**Appliqué depuis** — voir § 11. Les trois lignes du tableau ci-dessus sortent désormais en SUGGESTION et non en RAG ; le tableau est conservé tel quel parce qu'il documente le défaut qui a motivé le correctif.

### Passe B rejouée — bout en bout

```
CANONIQUE 4  ·  SUGGESTION 3  ·  LLM 3  ·  HORS_DOMAINE 2
Concordance passe A ↔ passe B : 12/12, scores identiques
```

Le rejeu de la passe A reste fidèle à la production après changement de seuil et de prompt.

### La table d'audit fonctionne

`garde_decisions` contient **exactement 4 lignes** après la passe B — une par appel du garde, aucune de plus, aucune de moins :

```
question posée                                  → indexée                        score   verdict  court-circuit  modèle
Quelle est la procédure pour saisir un engag…   Comment fait on un engagement…   0,8893    OUI         non       gemma-4-31b-it
Mes frais de mission ne m'ont pas été rembou…   Mes frais de déplacements ne…    0,8987    OUI         non       gemma-4-31b-it
comment fait on un engagement de dépense        Comment fait on un engagement…   0,9762    OUI         OUI       —
J'ai une dépense que je n'avais pas prévue,…    J'ai une dépense imprévue. Q…    0,9365    OUI         non       gemma-4-31b-it
```

La troisième ligne est celle qui justifie la table : `court_circuit = true`, `modele = NULL`. Un OUI rendu **sans appel LLM** et un OUI du juge servent tous deux la réponse sans revue humaine, mais ne valent pas preuve de la même chose. Le champ `erreur` distingue de même un NON jugé d'un NON par défaut faute d'avoir pu joindre Albert — le mode d'échec silencieux décrit dans `garde-cache-canonique.md`, jusqu'ici invisible en base.

### Ce que la seconde mesure ne dit pas

- **Le constat 3 tient toujours.** `SEUIL_COSINUS` reste une constante globale appliquée à des échelles de score locales : F2 plafonne à 0,8418 sur sa meilleure reformulation et n'est toujours **jamais** servie en canonique, alors que la recherche la place première à chaque fois. Abaisser le seuil ne corrige pas la cause, il la déplace.
- **Le constat 5 tient entièrement.** « COMMENT FAIT ON UN SERVICE FAIT ??? » reste à 0,6343 et n'atteint aucun candidat. Le court-circuit typographique demeure inatteignable en chaîne pour la casse et la ponctuation lourde.
- **La qualité des réponses RAG n'a pas été remesurée.** La consigne anti-fabrication (modification 5) est appliquée mais **non vérifiée** : il faudrait rejouer les deux cas classés « partielle » au § 3 et relire le texte produit.
- **Un seul corpus, un seul domaine, 48 cas.** Zéro faux positif mesuré n'est pas zéro faux positif.

### Coût Albert de la seconde campagne

≈ 48 `bge-m3` + 15 `gemma-4-31b-it` (passe A) · ≈ 12 `bge-m3`, 3 reranker, 3 `gpt-oss-120b`, 3 `gemma-4-31b-it` (passe B). Cumul de la journée très en deçà des deux compteurs (1 000 requêtes et 1,28 M jetons par jour, **par modèle**).

---

## 11. Correctifs de conception issus de la seconde mesure

La seconde mesure a laissé deux défauts identifiés et non corrigés : la non-monotonie du
seuil (§ 10, « trois SUGGESTION perdues ») et le constat 3 (une réponse n'est atteignable
que depuis une seule formulation). Tous deux sont maintenant traités. **Ce ne sont pas des
réglages : ce sont deux changements de comportement du pipeline.** Aucune campagne complète
n'a été rejouée après ces changements — ce qui suit est ce qui a été effectivement mesuré,
et rien de plus.

### 11.1 Un refus du garde rend le candidat à la branche SUGGESTION

`workers/question.py` — le refus n'enclenche plus le pipeline RAG complet, il appelle
`servir_reutilisation` comme la branche 2.

Le raisonnement tient en une phrase : le garde répond à *« peut-on servir ceci sans qu'un
humain le relise ? »*. Un NON disqualifie le service sans revue, pas la proposition au
relecteur — qui reste libre de la corriger ou de la rejeter. La règle asymétrique du projet
est intacte : **rien n'est servi sans revue de plus qu'avant**, c'est même exactement la
même population qui l'est.

Ce que cela répare est une **non-monotonie** : un candidat à 0,84 sortait en SUGGESTION
*sans être jugé*, tandis que le même à 0,86 était soumis au garde et, sur refus, renvoyé au
RAG sans candidat. Franchir `SEUIL_COSINUS` — un filtre de coût — *dégradait* l'issue. Les
trois cas du § 10 étaient précisément cela.

Le refus reste tracé dans `garde_decisions`. Contrepartie à connaître : **en base, la
SUGGESTION produite par un refus est indiscernable d'une SUGGESTION ordinaire.** La table
d'audit est le seul endroit où le passage du juge est écrit.

### 11.2 Une réponse est indexée sous chacune de ses formulations validées

`workers/feedback.py`, `api/v1/reponses/actions.py`, `services/qdrant.py`,
`services/search.py`, `services/question_pipeline.py`.

Le constat 3 avait été formulé comme un problème d'échelle de seuil. C'en était un, mais
la cause était en amont : `feedback_job` écrivait **un point par réponse**, sous la
question d'origine seulement. Valider une copie SUGGESTION incrémentait `nb_validations`
sur la source et **réindexait la question de la source** — la formulation qu'un humain
venait de valider était jetée. Une réponse canonique à trois validations ne portait qu'un
vecteur.

Désormais `valider_reponse` émet un second `feedback_job(source_id, formulation_id)` qui
indexe la question de la copie sur un point distinct, `uuid5(f"{source.id}:{copie.id}")`.
Trois conséquences qu'il fallait câbler ensemble :

- le payload porte `question_indexee` — **le garde doit juger la paire réellement
  retrouvée** ; redériver la question de `Ticket.question` lui soumettrait, sur un match
  d'alias, une paire que la recherche n'a jamais produite ;
- `trouver_reponse_reutilisable` renvoie un triplet `(reponse, score, question_indexee)`,
  celle du point le mieux classé ;
- **`delete_response_point` supprime par filtre de payload `reponse_id`, plus par id de
  point.** Sans cela un retrait pour obsolescence ou contradiction n'aurait supprimé que la
  question d'origine et laissé la réponse servable depuis ses alias — un retrait sans effet,
  silencieux.

Le signal exploité ici est une validation humaine explicite, plus forte que le jugement LLM
sur lequel tranche le garde, pas plus faible.

#### Mesure de bout en bout sur F2

F2 est le cas que le § 10 donnait comme non résoluble par le seuil : la recherche le plaçait
premier à chaque fois, aucune reformulation ne dépassait 0,8418. On a rejoué ce que fait
désormais `valider_reponse` : indexer **une** formulation validée.

| Question posée | Avant | Après |
|---|---|---|
| « Comment déclarer un service fait ? » — *la formulation indexée* | 0,8418 · SUGGESTION | **1,0000 · CANONIQUE** |
| « Comment procède-t-on pour constater un service fait ? » — *jamais indexée* | 0,8394 · SUGGESTION | **0,8744 · CANONIQUE** |

La seconde ligne est la plus instructive : une formulation que **personne n'a validée**
gagne 0,035 et franchit le seuil, parce qu'un second vecteur couvre une autre zone de
l'espace sémantique. Le gain déborde donc au-delà des formulations validées — et c'est
exactement là que le garde sert de filet. Il a été consulté sur les deux et a jugé la bonne
paire (`question_indexee` du point qui a matché).

### 11.3 Ce que ces correctifs ne démontrent pas

- **Aucune campagne complète n'a été rejouée après le 11.1 et le 11.2.** Le chiffre
  « 0 faux positif sur 48 » du § 10 vaut pour la configuration d'alors, pas pour celle-ci.
  Les deux changements élargissent la population servie en canonique : le refaire est le
  prochain travail utile.
- **Le débordement mesuré au 11.2 coupe dans les deux sens.** Une formulation non validée
  qui franchit le seuil est un gain quand elle est équivalente, une exposition au juge quand
  elle ne l'est pas. C'est délibéré — le garde est là pour ça — mais cela déplace la charge
  de la preuve du seuil vers le juge, et n'a été observé que sur deux cas.
- **La fixture DFE a dérivé.** La sonde a laissé la réponse F2 avec **2 points Qdrant** ; le
  décompte « 19 points DFE / 11 points réponse » documenté plus haut ne correspond plus.
  À reseeder avant toute nouvelle campagne.

### 11.4 Vérification

Cinq tests dans `backend/tests/test_formulations_indexees.py`, portant chacun sur une
propriété qui rougirait si elle sautait — vérifiés par mutation (rétablir la suppression par
id et l'ancien `point_id` produit `2 failed, 3 passed`) :

| Test | Propriété |
|---|---|
| `test_retrait_supprime_tous_les_points_de_la_reponse` | le sélecteur est bien un `Filter` sur le payload `reponse_id` |
| `test_formulation_supplementaire_ecrit_un_point_distinct` | l'alias n'écrase pas le point d'origine, et porte le bon `reponse_id` |
| `test_le_garde_juge_la_question_du_point_qui_a_matche` | c'est la question du point **le mieux classé** qui remonte |
| `test_question_indexee_absente_du_payload_ne_casse_pas` | un point antérieur renvoie `None`, l'appelant retombe sur `Ticket.question` |
| `test_refus_du_garde_sert_une_suggestion_sans_relancer_le_rag` | sur refus : `servir_reutilisation` appelé, reranker et génération **non** appelés |

État à la clôture : `ruff check app scripts tests` → *All checks passed* ;
`pytest -m 'not integration'` → **161 passed, 303 deselected**.

---

## 12. Campagne à `SEUIL_COSINUS = 0,80` — le juge mis sous pression

**Date** : 7 septembre 2026. Première campagne complète depuis les correctifs du § 11
(repli SUGGESTION sur refus, indexation multi-formulations). Question posée : *en abaissant
encore le seuil, sert-on à tort quand les candidats deviennent nettement plus proches du
bruit — et le juge fait-il son travail ?*

Fixture repurgée et resemée à l'état documenté avant la passe (**19 points DFE / 11 points
réponse / 8 chunks**, 8 canoniques + 3 validées non canoniques), afin d'isoler la variable
seuil. Seuils relevés **depuis l'intérieur** des conteneurs après recréation :
`SEUIL_COSINUS=0.8`, `SEUIL_SUGGESTION=0.75`.

### Les trois seuils, mêmes 48 cas

| | CANONIQUE | SUGGESTION | RAG | appels juge | NON | OUI | **Faux positifs** |
|---|---|---|---|---|---|---|---|
| `0,90` | 8 | 11 | 29 | 7 | 1 | 6 | **0 / 48** |
| `0,85` | 14 | 10 | 24 | 15 | 3 | 12 | **0 / 48** |
| **`0,80`** | **19** | **12** | **17** | **22** | **5** | **17** | **0 / 48** |

Critère de faux positif inchangé et non révisable : *servi sans revue une réponse dont le
candidat n'est pas l'entrée FAQ qui répond réellement*. Les 19 CANONIQUE sont toutes sur
leur cible.

Le juge passe de 7 à 22 saisines et de 1 à 5 refus. **Le taux de refus est stable** (14 %,
20 %, 23 %) : on ne l'a pas noyé sous des cas faciles, on lui a donné plus de vrai travail.

### Le résultat qui compte : les deux distributions se chevauchent

Dans la bande `[0,825 ; 0,885]`, le juge approuve et refuse **en alternance**, sur des
scores que rien ne sépare :

| Score | Verdict | Question posée → question indexée |
|---|---|---|
| 0,8254 | **NON** | « Qui valide un engagement de dépense ? » → « Comment fait on un engagement de dépense ? » |
| 0,8331 | OUI | *fil-facture* + « et si ce sont mes frais de déplacement ? » → F8 |
| 0,8399 | **NON** | « Faut-il un engagement pour une visite médicale ? » → « …pour la médecine de prévention ? » |
| 0,8418 | OUI | « Comment déclarer un service fait ? » → « Comment fait on un service fait ? » |
| 0,8609 | **NON** | « …dois-je contacter le service facturier ? » → « Mes frais de déplacements ne sont pas remboursés. Que dois-je faire ? » |
| 0,8683 | **NON** | *fil-engagement* + « et si la dépense concerne la médecine de prévention ? » → F6 |
| 0,8841 | **NON** | « Puis-je récupérer le reliquat…? » → « La prestation n'a été effectuée intégralement **et/ou moins chère que prévue**, puis je récupérer le reliquat…? » |
| 0,8893 | OUI | « Quelle est la procédure pour saisir un engagement de dépense ? » → F1 |

C'est la démonstration expérimentale de ce que `garde-cache-canonique.md` postulait :
**aucun seuil ne sépare ces huit lignes.** Placé n'importe où entre 0,82 et 0,89, il
couperait au travers des deux populations. Le juge, lui, les sépare — et dans le bon sens.

Deux refus sont exemplaires : `0,8254` (« **qui valide** » ≠ « **comment fait-on** » : même
objet, demande différente) et `0,8841` (la question indexée porte une condition — prestation
partielle ou moins chère — que la question posée ne porte pas, donc une réponse potentiellement
hors périmètre).

### Ce que le repli SUGGESTION change concrètement

Les 5 refus du juge **sortent tous en SUGGESTION**, pas en RAG : le relecteur voit le
candidat, et sur les cinq c'est à chaque fois la bonne entrée FAQ.

Deux d'entre eux portent sur des périmètres quasi synonymes (`0,8399` « visite médicale » vs
« médecine de prévention » ; `0,8683` où la précision recouvre largement F6). **Ce sont des
refus corrects**, et il faut résister à la tentation de les lire comme un excès de zèle : la
règle du projet dit que dans la zone d'ambiguïté on ne sert pas sans revue. « Quasi
synonyme » n'est pas « exactement la même demande » — et c'est précisément la question que le
juge a à trancher. Une visite médicale n'est pas nécessairement une visite de médecine de
prévention ; l'exception que porte la réponse F6 pourrait ne pas s'appliquer.

C'est là que le repli SUGGESTION prend tout son sens : le coût d'un refus prudent n'est plus
la perte de la réponse, seulement une revue humaine. **Le juge peut donc être strict sans que
ça coûte cher.** Assouplir son prompt pour « récupérer » ces cas reviendrait à échanger de la
sûreté contre une économie de revue — mauvais côté de l'asymétrie.

Quatre cas supplémentaires tombent dans la bande `[0,75 ; 0,80]` ouverte par la dérivation de
`SEUIL_SUGGESTION`, et sortent en SUGGESTION au lieu de RAG (« service fait *partiel* » à
0,785, « comment **annule**-t-on un engagement » à 0,7996, « engagement pour une **formation** »
à 0,7821, « facture réglée mais **montant faux** » à 0,7788). Aucun n'est servi sans revue.
À surveiller : ce sont des demandes réellement différentes, et les proposer au relecteur n'est
utile que si le relecteur les rejette effectivement.

### Fidélité et intégrité de la mesure

Passe B rejouée dans la vraie file Celery : **12/12 de concordance** avec le rejeu de la
passe A (`CANONIQUE`, `SUGGESTION`, `LLM`/`HORS_DOMAINE` correspondent un pour un). Le
harnais reflète toujours la production.

`garde_decisions` sur la fenêtre de la passe B : 4 OUI jugés, 1 NON jugé, 1 court-circuit
typographique, et **`erreur IS NULL` partout**. Aucun refus n'est imputable à un 429 Albert —
vérification indispensable, sans quoi un quota épuisé se lirait comme une prudence du juge.

### Limites de cette campagne

- **Un seul corpus, un seul domaine, 48 cas.** Zéro faux positif mesuré n'est pas zéro faux
  positif. La FAQ DFE a des grappes adverses serrées, ce qui rend l'épreuve sévère, mais elle
  reste une seule épreuve.
- **La ligne « répartition des refus corrects » du harnais est devenue dégénérée** : elle ne
  compte que les cas finissant en RAG, or seuils et juge produisent désormais des SUGGESTION.
  Elle affiche `AUCUN_CANDIDAT 16` et n'informe plus. À reformuler avant la prochaine passe.
- **La qualité des textes RAG n'a pas été remesurée**, toujours pas depuis le § 3.
- **Le taux de « faux négatifs » n'est pas un indicateur à minimiser.** Il est tentant de lire
  les 2 restants, ou les refus sur périmètres quasi synonymes, comme une marge de progrès à
  aller chercher dans le prompt du juge. Ce serait optimiser contre la règle du projet. Le seul
  chiffre dont la valeur cible est zéro est celui des faux positifs.

### Conclusion

À `0,80`, le cache sert **19 réponses sur 48 sans revue humaine — contre 8 à `0,90` — sans
un seul faux positif**, tout en donnant au juge trois fois plus de décisions à prendre. La
propriété de sûreté ne s'est pas dégradée en élargissant : elle a simplement cessé d'être
assurée par le seuil pour l'être par le juge, ce qui était l'intention de conception.

---

## 13. Normaliser la question avant embedding : mesuré, et écarté

Le § 5 relève un cas (`COMMENT FAIT ON UN SERVICE FAIT ???`, score `0,6343`) où le
court-circuit typographique de `_normaliser` ne peut pas jouer : il n'intervient qu'après
la recherche, or `search_hybrid` embarque la question **brute** (`workers/question.py:73`).
La correction évidente — normaliser avant l'embedding — a été mesurée le 07/09/2026 sur
`BAAI/bge-m3`, quatre sondes, ~40 textes embarqués. **Elle est écartée.**

### Ce que la mesure établit

D'abord un fait contre-intuitif : **bge-m3 n'est pas robuste à la casse**. Contre la
question indexée `Comment fait on un service fait ?` :

| Variante de la question posée | Similarité |
|---|---|
| Identique | 1,0000 |
| Minuscules seules | 0,9911 |
| Sans ponctuation | 0,9815 |
| `???` seuls | 0,8622 |
| Majuscules seules | **0,7170** |
| Majuscules + `???` | **0,6344** |

Les majuscules à elles seules coûtent 0,28. Ce n'est donc pas un défaut du garde mais un
défaut de **recherche** : une question criée retrouve aussi de moins bons chunks, la
branche RAG en souffre autant que le cache.

### Pourquoi le correctif n'est pas rentable

Deux régimes possibles, tous deux mesurés :

| Régime | Cas pathologique | Reformulations équivalentes | Questions à garder distinctes |
|---|---|---|---|
| Requête normalisée, index brut | 0,6344 → 0,9597 | **−0,0336 à −0,0574** | ≈ 0 |
| Symétrique (requête + index) | 0,6343 → 1,0000 | −0,0070 à −0,0185 | ≈ 0 (max +0,0152) |

- **Le régime asymétrique est disqualifié.** Comparer une requête normalisée à des vecteurs
  indexés bruts fait perdre 4 à 6 centièmes à *tous* les cas bien formés. La reformulation
  équivalente de F2 passe de `0,8418` à `0,7844`, sous `SEUIL_COSINUS` : on échangerait un
  CANONIQUE contre un autre.
- **Le régime symétrique est sûr mais coûteux au mauvais endroit.** Il ne rapproche pas les
  paires qui doivent rester distinctes (la grappe « Que dois-je faire ? » se *sépare* même
  légèrement : F8/F7 `0,7630 → 0,7173`) et ne perturbe pas la recherche documentaire
  (±0,02 sur les chunks DFE). Mais il rabote 1 à 2 centièmes sur **chaque** reformulation
  légitime, et c'est rédhibitoire ici : le § 12 établit que `0,80` est un plancher, la bande
  [0,75 ; 0,80) ne contenant que des demandes réellement différentes. **On ne peut donc pas
  compenser en abaissant le seuil.** Une des reformulations mesurées tombe de `0,8209` à
  `0,8039` — quatre millièmes de marge.

On paierait une perte systématique sur le cas courant pour un gain sur un cas rare. Et le
cas rare n'est pas perdu : il part au RAG, ce qui est un **coût, pas une faute**.

### Le correctif à retenir si le motif se répète

Non pas normaliser avant embedding, mais **indexer la forme normalisée comme point Qdrant
supplémentaire** — exactement la mécanique du levier 1 (§ 11), un point par formulation,
payload `question_indexee` propre. Gain intégral sur le cas pathologique, **aucun vecteur
existant modifié**, donc calibration du § 12 préservée. À déclencher sur constat en
production, pas par anticipation : un cas sur 48 ne le justifie pas.
