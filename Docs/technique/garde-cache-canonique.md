# Garde du cache canonique

Ce document explique le mécanisme qui décide si une réponse canonique peut être servie sans revue humaine.

**Fichiers concernés**
- `backend/app/services/garde_cache.py` — implémentation du garde
- `backend/app/workers/question.py` — **premier** point d'appel : au service (étape 2)
- `backend/app/workers/feedback.py` — **second** point d'appel : à l'écriture d'un alias (`_alias_juge`)
- `backend/app/services/question_pipeline.py` — `peut_servir_sans_revue`, qui décide *ce qu'un OUI ouvre* (et non si le juge est appelé), et `Candidat.servable`
- `backend/app/services/search.py` — `franchit_le_rappel`, la disjonction cosinus / lexical
- `backend/app/models/garde_decision.py` — la table d'audit `garde_decisions`
- `backend/app/config.py` — `ALBERT_GARDE_MODEL_NAME`

---

## Problème

La recherche hybride dans Qdrant mesure une proximité vectorielle : deux questions proches dans l'espace sémantique obtiennent un score cosinus élevé même si elles n'appellent pas la même réponse. Des exemples typiques qui trompent le cosinus :

- Même sujet, chiffre différent : *"J'ai droit à combien de jours de RTT ?"* vs *"J'ai droit à combien de jours de congé ?"*
- Négation : *"Puis-je télétravail ?"* vs *"Puis-je **refuser** de télétravailler ?"*
- Périmètre restreint : *"Quel est le préavis de licenciement ?"* vs *"Quel est le préavis de licenciement **pour un CDD** ?"*
- Ajout de condition : *"Puis-je poser des congés en décembre ?"* vs *"Puis-je poser des congés en décembre **si j'ai moins d'un an d'ancienneté** ?"*

Un seuil cosinus, aussi élevé soit-il, ne sépare pas ces cas : la distribution des scores pour les paires servables et les paires non-servables se chevauche presque entièrement.

**Le second signal ne change rien à ce constat.** Depuis la recherche lexicale, un candidat
peut aussi atteindre le garde par son recouvrement de mots (BM25 ramené au terme). Les quatre
pièges ci-dessus le trompent tout autant : *"J'ai droit à combien de jours de RTT ?"* et
*"…de congé ?"* partagent tous leurs termes sauf un, et la négation de *"Puis-je **refuser** de
télétravailler ?"* ajoute un mot au lieu d'en retirer — le recouvrement en sort *renforcé*.
Élargir le rappel amène donc plus de paires au juge, pas des paires plus faciles.

---

## Solution : juge LLM binaire

Avant de servir une réponse canonique sans revue humaine, le pipeline appelle `garde_cache.statuer(question_posee, question_indexee, est_suivi=…)`. Le juge pose une question simple au LLM :

> *Ces deux questions expriment-elles exactement la même demande ?*

La réponse attendue est **OUI** ou **NON**. Toute réponse autre que `"OUI"` exact (insensible à la casse) est traitée comme un refus. Une exception ou un timeout est également un refus. Le garde est conservateur par construction : le moindre doute retire la réponse du service sans revue.

`statuer` renvoie une `Decision` (`verdict`, `court_circuit`, `modele`, `erreur`) — de quoi journaliser dans `garde_decisions` et distinguer un OUI de court-circuit d'un OUI jugé, un NON jugé d'un NON par indisponibilité d'Albert. `approuver()` reste disponible comme enveloppe booléenne pour les tests et scripts de calibration.

---

## Flux dans le pipeline

```
Candidat rendu par `trouver_reponse_reutilisable`
(a franchi le rappel : cosinus ≥ SEUIL_SUGGESTION  OU  BM25/terme ≥ SEUIL_LEXICAL_PAR_TERME)
        │
        ▼
Le verdict peut-il changer l'issue ?
(`peut_servir_sans_revue` OU `candidat.servable` — c'est-à-dire :
 ce candidat serait réutilisé, en CANONIQUE ou en SUGGESTION)
        │
        ├─── non ──► RAG — candidat lexical seul et non canonique.
        │            L'issue est le RAG quel que soit le verdict :
        │            on n'appelle pas.
        │
        └─── oui  ◄── **aucune condition de score ni de statut ici**
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
              ├─── oui ──► OUI, sans appel LLM
              │
              └─── non ──► Appel LLM (ALBERT_GARDE_MODEL_NAME)
                             │
                             ├─── "OUI" exact
                             │
                             ├─── "NON" jugé ──► RAG
                             │                   (génération sur la question posée)
                             │
                             └─── pas de verdict ──► SUGGESTION si `servable`,
                                  (Albert injoignable, ou aucune    sinon RAG
                                   question indexable à soumettre)
        │
        ▼
      OUI ──┬── `peut_servir_sans_revue` ──► CANONIQUE si cosinus ≥ SEUIL_COSINUS,
            │                                sinon SUGGESTION
            │                                (`servir_reutilisation` reteste tout)
            │
            └── sinon (non canonique, ou signalée `a_relire`)
                                         ──► SUGGESTION (revue humaine)
```

### Le juge est appelé sans condition de score, et son refus renvoie au RAG

Deux changements du 18/09/2026, qui ne valent que pris ensemble.

**`SEUIL_COSINUS` ne décide plus si on appelle le juge**, seulement si un OUI a le droit d'être servi sans revue — et c'est `servir_reutilisation` qui le reteste. Tout candidat encore autorisé à servir sans revue est donc jugé. La porte du service sans revue est **strictement inchangée** : un OUI sous le seuil ressort en SUGGESTION, il n'ouvre rien. Ce qu'on gagne est l'usage du **NON** — mesuré sur la campagne 48 cas, deux candidats à 0,7996 et 0,785 n'étaient soumis à personne. C'est cette asymétrie qui rend l'élargissement sûr : on se sert du refus du juge, jamais de son accord.

**Un refus jugé envoie au RAG.** Le juge vient de dire que les deux questions ne posent pas la même demande : le candidat ne répond donc pas à celle-ci, et le proposer au relecteur, c'est lui mettre sous les yeux quelque chose que le système a déjà jugé hors sujet — sur l'écran où « Valider » est le bouton le moins cher, celui-là même qui écrit un alias (§ suivant). Mieux vaut une génération fondée sur les documents, pour la question réellement posée. C'est la règle que `Candidat.servable` énonçait déjà pour les candidats purement lexicaux ; elle était abandonnée au-dessus de `SEUIL_SUGGESTION` sans raison.

> **Ce que disait cette page jusqu'au 18/09/2026** : « le refus ne renvoie pas au RAG, il rend la réponse à la branche SUGGESTION », au motif que sans ce repli le système était **non monotone** — un candidat à 0,84 sortait en SUGGESTION sans être jugé, le même à 0,86 était jugé et, sur refus, renvoyé au RAG *sans candidat*, si bien que franchir le seuil *dégradait* l'issue. Les deux moitiés de cet argument sont tombées ensemble : la discontinuité n'existe plus, puisque le juge est désormais appelé des deux côtés du seuil ; et sa prémisse — un candidat refusé vaut mieux que le RAG — est ce que la mesure contredit. Sur les 9 refus de la campagne, **6 sortaient en SUGGESTION alors que le RAG était attendu** : « Qui valide un engagement de dépense ? » se voyait proposer « Comment fait on un engagement de dépense » à 0,8254, juste après le refus.

**Seul un refus *jugé* a cet effet.** `Decision.erreur` existe exactement pour cette distinction — « ce dernier ne doit pas être compté comme un refus du juge ». Albert injoignable, ou aucune question indexable à soumettre, ce n'est pas « pas la même demande », c'est l'**absence de verdict** : on garde alors le comportement antérieur, SUGGESTION sous revue humaine. Une panne réseau ne doit décider ni d'une branche, ni d'une génération.

**Coût assumé** : un refus *prudent* — paire en fait équivalente, cf. le cas à 0,8841 — prive le relecteur d'une réponse validée réutilisable et fait naître une lignée parallèle sur le même sujet. La sélection par pertinence l'amortit en faisant remonter la meilleure des deux. C'est le coût de relecture que l'invariant « jamais servir une réponse fausse » accepte explicitement, et il ne faut **pas** l'arbitrer en assouplissant le prompt du juge.

Le refus reste tracé dans `garde_decisions` ; la table est le seul endroit qui dise qu'un juge est passé, le RAG produit étant indiscernable en base d'un RAG sans candidat.

**Mesure** — campagne 48 cas, **trois passes** (`scripts/resultats_non_vers_rag*.json`, 18/09/2026), comparées cas par cas et non seulement en totaux :

| | Avant | Après |
|---|---|---|
| Conformes | 35/48 | **43/48** |
| Faux positifs (servi sans revue hors cible) | 0 | **0** |
| Appels au juge | 27 | 30 |

Les trois passes sont **identiques champ par champ** — `branche`, `bloque_par`, `ok`, `verdict_garde`, `seuil_franchi` — ce qui est plus stable que le ±1 cas habituel à `temperature=0,1`. Le diff par cas contre la référence donne **exactement 9 cas changés, tous `SUGGESTION → RAG`, tous `bloque_par=GARDE`** ; aucun cas où `ok` bouge sans que la branche bouge. Les 3 CANONIQUE « non prévus » sont inchangés et ne sont pas des faux positifs : dans les trois, `candidat == cible_attendue` — la bonne réponse, par une branche que la colonne `attendu` prédisait en RAG. **Zéro exposition nouvelle sans revue** : la porte CANONIQUE exige toujours OUI **et** `franchit(SEUIL_COSINUS)` **et** `peut_servir_sans_revue`, et toute sortie RAG est `EN_ATTENTE`.

### `a_relire` ferme la porte du service sans revue, pas celle du juge

`peut_servir_sans_revue` (`services/question_pipeline.py`) dit *canonique **et** non signalée*. Une réponse que la confrontation ou la réverification vient de marquer `CONTREDITE_PROBABLE` perd le droit d'être servie sans revue — mais **elle est jugée comme les autres**, et c'est le verdict qui départage SUGGESTION et RAG.

> **Ce que disait cette page jusqu'au 18/09/2026 :** *« Une réponse signalée n'atteint plus le juge du tout. Le garde compare deux questions, il ne sait rien d'un document qui contredirait la réponse : lui soumettre le candidat ne pourrait produire qu'un OUI. La porte se ferme donc avant lui, ce qui économise un appel Albert pour un candidat qu'on ne servira de toute façon pas sans revue. »*

Les deux moitiés de cet argument étaient fausses, et la mesure les a prises en défaut ensemble.
La première — *« il ne pourrait dire que OUI »* — suppose que la paire est équivalente. Quand elle ne l'est pas, le juge dit NON, et c'est un signal **orthogonal** au drapeau : `a_relire` porte sur la *véracité* de la réponse, le garde sur l'*identité de la demande*. Sauter l'appel jette le second parce qu'on se méfie du premier.
La seconde — *« on ne la servira pas sans revue, donc l'appel est gratuit à économiser »* — ne valait que tant qu'un refus sortait **lui aussi** en SUGGESTION. Depuis que le refus jugé renvoie au RAG, ne pas appeler le juge n'économise plus un appel : ça pose sur l'écran du relecteur une réponse dont personne n'a vérifié qu'elle répondait à la question, là où « Valider » est le bouton le moins cher.

**Mesuré le 18/09/2026**, bout en bout télétravail sur un domaine neuf (doc A général → canonique à 3 formulations → doc B spécifique → question spécifique). La confrontation flague la canonique `CONTREDITE_PROBABLE` sans la détruire (`obsolete=false`) — puis la question « est ce que télétravail possible ? pour les alternant ? » se voyait proposer la réponse **générale**, 3 passes sur 3, cosinus 0,8047, **zéro ligne dans `garde_decisions`**. Interrogé, le juge refuse la paire 3 fois sur 3 (refus *jugé* : `erreur` nulle), et le RAG répond juste 3 fois sur 3, doc B reranké #1 à 0,9677 contre 0,0669 pour doc A.

La règle est donc : **le juge est consulté exactement quand son verdict peut changer l'issue** — `peut_servir_sans_revue(reponse) or candidat.servable`. Ni le score ni le statut ne décident *si on appelle* ; ils décident *ce qu'un OUI ouvre*. Seul le candidat retenu par les seuls mots et non canonique saute l'appel : son issue est le RAG quel que soit le verdict.

L'asymétrie qui rend l'élargissement sûr est la même qu'au § précédent : **on se sert du refus du juge, jamais de son accord.** Un OUI sur une réponse signalée `a_relire` n'ouvre rien — `servir_reutilisation` reteste `peut_servir_sans_revue` et rabat sur SUGGESTION, exactement comme avant qu'on l'interroge.

**Coût mesuré** — campagne 48 cas, trois passes (`scripts/resultats_juge_sur_suggestion*.json`, 18/09/2026), **identiques champ par champ, 0 cas instable, 0 faux positif dans les trois**. Conformité 43/48 → **42/48**, appels au juge 30 → 34.

La fixture DFE ne contient **aucune** réponse signalée : elle ne peut donc pas exercer le cas ci-dessus, seulement le coût de l'élargissement aux candidats `servable` non canoniques. Sur les 6 cas qui diffèrent de la référence, **3 sont de la dérive de corpus et non le changement** — leur `candidat` passe de `None` à une entrée, ce qui se décide dans `trouver_reponse_reutilisable`, en amont de toute ligne touchée ; l'IDF que Qdrant calcule porte sur la collection entière, et la campagne a été rejouée après avoir indexé un domaine de test. Les trois candidats ainsi apparus sont canoniques et sous `SEUIL_SUGGESTION` : l'ancien code les aurait jugés de la même façon et conclu au même RAG.

Reste **un seul cas** réellement changé par l'élargissement, `SUGGESTION → RAG` : « Comment connaitre les montants attribués par les collectivités territoriales ? » contre la question indexée « Comment puis-je connaitre, **pour mon service**, les montants attribués … », cosinus 0,9485, refus jugé. La question posée est générale, l'indexée est portée sur un service : le juge y refuse exactement la distinction général/spécifique dont cette branche existe pour tenir compte. Deux autres candidats non canoniques (0,9908 et 1,0) ont été jugés pour la première fois et **approuvés**, sans changer de branche — le coût net est de 2 appels au juge.

Ne pas relire ce cas comme une régression à corriger dans le prompt : la colonne `attendu` de la campagne encode le comportement d'alors, pas l'exigence, et le critère qui décide reste le faux positif — toujours 0.

**Le signalement reste un tri, pas un retrait.** `trouver_reponse_reutilisable` continue de rendre la réponse, qui reste amendable en un geste avec son `nb_validations` intact. Ce qu'elle perd est le seul privilège de la branche CANONIQUE. La détruire (`obsolete`) coûterait `SEUIL_CANONIQUE` revalidations pour un état final identique, sur la foi d'un simple cosinus entre un paragraphe et une question ; ne rien faire laissait servir sans revue une réponse que le système soupçonne fausse.

Le même prédicat a un **miroir SQL** dans `services/faq.py` — cette page n'a aucun relecteur, y montrer une réponse signalée serait exactement la servir sans revue. Les deux doivent rester d'accord ; `tests/test_faq.py` les compare sur le même jeu de drapeaux.

---

## Le second point d'appel : l'écriture d'un alias

Le garde est appelé à **deux** moments, et le second ne sert pas le même but.

Quand un relecteur valide une copie SUGGESTION, `feedback_job(source_id, formulation_id)` écrit un point Qdrant portant la question de la copie et le `reponse_id` de la source — un *alias*. Cette écriture est **plus forte que tout ce que le garde tranche au service** : à la question suivante le cosinus vaut ~1,0, le court-circuit typographique s'enclenche, et la réponse part en CANONIQUE **sans qu'aucun juge ne soit appelé**. Un alias faux ne passe donc pas devant le garde, il le contourne.

Or rien ne le vérifiait. Il suffisait qu'un relecteur clique « Valider » plutôt que « Corriger » sur une SUGGESTION *plausible mais à côté de la question* — la réponse générale n'est pas fausse, elle répond simplement à une autre demande — et le bouton vert est le chemin le moins cher de l'écran. La paire est donc soumise au même juge **avant** d'écrire quoi que ce soit (`_alias_juge`, `workers/feedback.py`) : A = la nouvelle formulation, B = la question sous laquelle la source est indexée.

Trois issues, et `Decision.erreur` existe exactement pour les séparer :

| Verdict | Effet |
|---|---|
| **OUI** | l'alias est écrit |
| **NON jugé** | pas d'alias — la réponse reste atteignable depuis ses formulations existantes, soit le comportement d'avant l'indexation multi-formulations ; ce n'est pas une perte |
| **Albert injoignable** (`erreur`) | `retry`. Un refus par défaut perdrait en silence une formulation qu'un humain a validée |

Le refus est consigné dans `garde_decisions` avec `score_cosinus = NULL` : cette paire ne vient pas d'une recherche mais d'un geste humain, et un `0.0` se lirait comme un candidat très lointain.

**Coût** : un appel juge par *validation humaine* de SUGGESTION — un événement rare, pas une question — et zéro quand les deux formulations sont typographiquement identiques.

**Portée délibérément limitée à l'alias.** `nb_validations` sur la source continue d'être incrémenté par l'endpoint HTTP. Le bloquer demanderait un appel LLM synchrone sur une requête web, pour un signal qui *promeut* sans *servir* ; c'est l'alias qui crée le cosinus à 1,0. À rouvrir si la mesure montre des promotions abusives.

---

## Par quelle porte le candidat est arrivé

Cette porte n'est plus celle du juge — il est appelé sans condition de score (§ ci-dessus) —
mais celle du **service sans revue** : c'est `servir_reutilisation` qui l'évalue sur un OUI,
pour trancher entre CANONIQUE et SUGGESTION. Ce n'est pas un seuil mais une **disjonction**
(`franchit_le_rappel`, `services/search.py`, appelée avec `SEUIL_COSINUS`) :

| Porte | Signal | Seuil |
|---|---|---|
| Dense | `score_cosinus` — cosinus pur, inchangé depuis avant BM25 | `SEUIL_COSINUS` (0,80) |
| Lexicale | `score_lexical` — BM25 divisé par le nombre de termes de la requête | `SEUIL_LEXICAL_PAR_TERME` (1,0) |

**On ne seuille pas la fusion, on seuille chaque signal sur son échelle.** Aucun score de
fusion n'est absolu : le RRF ne dépend que du rang — premier d'un lot inutile vaut premier
d'un lot parfait — et une fusion par distribution normalise par requête. Le RRF ne sert donc
qu'à **ordonner**.

Ce que cela change pour le garde : **il voit des paires qu'aucun seuil cosinus n'aurait
laissées passer.** Cas mesuré le 12/09/2026 — `COMMENT FAIT ON UN SERVICE FAIT ???` obtient un
cosinus de 0,6343 (les majuscules et le bruit de ponctuation démolissent l'embedding) alors
que son recouvrement lexical est parfait. Il franchit par la porte lexicale, le juge répond
OUI, la réponse sort en CANONIQUE. C'est exactement le cas pour lequel BM25 existe, et il
était hors de portée de *n'importe quel* abaissement de `SEUIL_COSINUS`.

**Cet élargissement coûte des appels au juge, pas de la sûreté.** Sur la campagne de 48 cas
rejouée le 12/09/2026 : CANONIQUE 19 → 21, appels au juge 22 → 31, et **toujours zéro faux
positif**. `SEUIL_COSINUS` comme `SEUIL_LEXICAL_PAR_TERME` restent des filtres de coût ; c'est
le garde seul qui décide de servir sans revue.

**`garde_decisions` porte les deux colonnes** (`score_cosinus` **et** `score_lexical`,
`models/garde_decision.py`) précisément pour qu'on puisse relire *par quelle porte* un candidat
est passé. Une seule colonne rendrait l'audit ambigu, et `score_cosinus` a été laissé **pur** —
jamais mélangé au lexical — pour que les décisions antérieures à BM25 restent comparables aux
nouvelles. `score_lexical` est nul sur les lignes écrites avant la recherche lexicale.

> ⚠️ `SEUIL_LEXICAL_PAR_TERME` est à recalibrer quand le corpus grossit : l'IDF que Qdrant
> calcule côté serveur suit `log(N)`, donc toute l'échelle se déplace. Le défaut de 1,0 a été
> mesuré sur 24 points. Le mettre à `0` referme la porte et restaure exactement le
> comportement d'avant BM25 — c'est l'échappatoire si une calibration tourne mal. Détail dans
> [`choix-techniques.md`](choix-techniques.md) et
> [`rapport-test-cache-semantique.md`](rapport-test-cache-semantique.md) § 15.

**La FAQ, elle, n'a pas de juge** — et en tire la conséquence inverse : un candidat passé par
la seule porte lexicale y atterrit dans `incertains`, jamais dans `resultats`. Rien, sur cette
page, ne peut confirmer qu'un recouvrement de mots vaut une réponse. C'est la même porte, deux
contrats différents.

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

**Côté indexation, la précision n'est jamais indexée nue** (28/09/2026). Une réponse de suivi validée était indexée sous `question_suivi` — *« et pour un apprenti ? »* — donc sans le contexte que ce paragraphe protège côté A. Un autre fil finissant par les mêmes mots la retrouvait à cosinus ≈ 1, et le juge voyait une question B identique à la dernière ligne du fil : OUI probable, et la réponse sur un tout autre sujet servie sans revue (pour une question neuve identique, le court-circuit répondait même OUI sans appel). Indexer la question initiale ne vaut pas mieux : la réponse spécifique servirait la question générale.

`feedback_job` indexe désormais une **question autonome** (`services/reformulation.py`) : le fil est réécrit une fois, à la validation, en une question qui porte son contexte (*« Quel est le préavis de licenciement pour un apprenti ? »*), stockée dans `Reponse.question_autonome` et reprise telle quelle aux réindexations. Une sortie inexploitable (plusieurs lignes, vide, trop longue) n'est pas indexée ; une panne Albert relance la tâche. Coût : un appel au modèle du garde par suivi validé.

Les points écrits avant ce correctif sont **neutralisés au service** : `question_du_point_fiable` reconnaît un point dont la question indexée est la précision nue d'une réponse (ou d'une de ses copies, pour un alias) sans reformulation qui la cautionne. La paire n'est pas jugeable, et c'est traité **comme un refus : RAG**. La première version les envoyait en SUGGESTION, et la mesure a montré que c'était pire : le relecteur recevait la réponse « congé paternité » pour une question sur la prime, là où le juge, lui, refusait. `scripts/reindexer_suivis.py` réécrit ces points (simulation par défaut, `--appliquer`).

**Côté recherche, une précision est cherchée avec son fil** (`requete_recherche`), pour la réutilisation comme pour le RAG, qui faisait déjà cette recherche : un seul embedding au lieu de deux. Cherchée seule, « et pour un apprenti ? » n'atteignait jamais la question autonome sous laquelle elle avait été validée.

Mesuré le 28/09/2026 sur la stack de dev, avec Albert (`scripts/bout_en_bout_suivis.py`). Un document porte deux sujets, chacun avec une exception « apprentis » ; chaque cas a été joué 3 fois :

| Cas | Point rappelé (cosinus) | Issue |
|---|---|---|
| Fil paternité + « et pour un apprenti ? », précision cherchée seule | spécifique 0,65 : sous les portes | RAG 3/3, aucune CANONIQUE possible |
| Même fil, précision cherchée avec son fil | spécifique 0,98, générale 0,90 | **CANONIQUE 3/3**, juge OUI, réponse juste |
| Fil prime + « et pour un apprenti ? » | spécifique paternité 0,64 : non rappelée | RAG 3/3, juste (400 €) |
| Fil paternité + « et pour un salarié à temps partiel ? », générale canonique | générale 0,90 : au-dessus du seuil CANONIQUE | **juge NON 3/3** → RAG (HORS_DOMAINE, juste) |
| Question neuve « … pour un apprenti ? » | 1,00 | CANONIQUE 3/3 |
| Fil prime face à la précision nue (point hérité), juge seul | — | NON 3/3 |

La dernière ligne tempère le risque d'origine : sur ce cas, le juge en mode suivi refusait déjà la précision nue. Le correctif ferme surtout le court-circuit sans appel (question neuve typographiquement identique à une précision) et donne aux juges comme à la FAQ une question lisible. Une seule formulation a été mesurée : cela ne prouve pas que le juge ait toujours tenu.

---

## Configuration

| Variable `.env` | Défaut | Description |
|---|---|---|
| `ALBERT_GARDE_MODEL_NAME` | *(vide)* | Modèle LLM dédié au garde. Si vide, utilise `ALBERT_LLM_MODEL_NAME`. |
| `SEUIL_COSINUS` | *(obligatoire ; `.env.example` : 0.80)* | Porte dense **du service sans revue** : au-dessous, un OUI du juge sort en SUGGESTION. |
| `SEUIL_LEXICAL_PAR_TERME` | `1.0` | Porte lexicale, **en disjonction** de la précédente. `0` la referme. |

Les deux règlent **ce qu'un OUI a le droit d'ouvrir**, pas la sûreté : c'est le verdict qui
protège, pas le seuil. Ils ne commandent plus le débit d'appels au juge — celui-ci est appelé
pour tout candidat encore autorisé à servir sans revue. Le débit se règle donc **en amont**,
par le rappel (`SEUIL_SUGGESTION`, dérivé de `SEUIL_COSINUS − 0,05`), qui décide combien de
candidats existent.

Utiliser un modèle dédié est recommandé : Albert applique ses quotas (jetons et requêtes) par modèle. Partager le modèle de génération laisse les appels de génération épuiser le quota du garde.

⚠️ **Un quota épuisé ne produit pas d'erreur visible côté utilisateur.** Toute exception —
dont un `429` d'Albert — devient un `verdict=False`, et un quota vidé se manifeste donc par
une chute du taux de réponses canoniques, les questions basculant massivement en SUGGESTION.
C'est bien SUGGESTION et non RAG : `Decision.erreur` est renseignée, l'appelant y lit une
absence de verdict plutôt qu'un refus, et ne relance pas une génération par panne réseau —
une coupure d'Albert ne doit pas se payer en appels à… Albert. **La distinction se lit dans
`garde_decisions`**, où `erreur` est journalisée. Devant une chute inexpliquée, interroger
cette table avant de suspecter le prompt.

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
- Il **n'a pas de verdict intermédiaire** — la sortie est binaire. Mais l'appelant, lui, distingue deux refus : un NON *jugé* renvoie au RAG, un refus faute d'avoir pu joindre Albert rend la réponse en SUGGESTION. `Decision.erreur` sert donc l'audit **et** le routage, depuis le 18/09/2026.
- Il **ne choisit pas la question B** — celle-ci lui est fournie par le point Qdrant qui a matché (voir ci-dessous). Le garde ne peut pas rattraper une mauvaise paire.
- Il **ne juge pas la réponse encore d'actualité** — il ne voit ni les documents, ni leurs versions. Une réponse contredite par une ingestion récente lui paraîtra parfaite si la paire de questions, elle, est bonne. C'est `peut_servir_sans_revue` qui lui retire alors le droit d'être servie sans revue — mais pas celui d'être jugée : les deux signaux sont orthogonaux et se cumulent, l'un sur la véracité de la réponse, l'autre sur l'identité de la demande.

---

## Quelle question B est jugée

Une réponse est indexée sous **une question par formulation validée par un humain**, chacune sur son propre point Qdrant (`feedback_job(source_id, formulation_id)`). Le garde doit juger la paire **réellement retrouvée** : la question B est lue dans le payload `question_indexee` du point qui a matché, transportée par `search_hybrid` puis `trouver_reponse_reutilisable`.

La redériver de `Ticket.question` — ce que faisait le code avant — soumettrait au juge la question d'origine alors que la recherche a matché sur un alias, donc une paire que rien n'a produite. Les points écrits avant l'introduction des formulations multiples n'ont pas cette clé ; l'appelant retombe alors sur `Ticket.question` / `Reponse.question_suivi`.

Ce mécanisme élargit la couverture du cache sans toucher aux seuils : mesuré le 05/09/2026, indexer *une* formulation validée fait passer « Comment déclarer un service fait ? » de 0,8418 (SUGGESTION) à 1,0000 (CANONIQUE), et — effet de bord recherché — une formulation que **personne n'a validée**, « Comment procède-t-on pour constater un service fait ? », de 0,8394 à 0,8744, franchissant le seuil elle aussi. Le gain déborde donc au-delà des formulations validées : c'est précisément là que le garde sert de filet, et il a bien été consulté sur les deux.
