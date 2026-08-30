# Le garde du cache canonique

> **À lire avant de toucher aux seuils de candidature, aux invites des juges, ou à la
> condition de la branche CANONIQUE.** Chaque valeur de ce document a été mesurée contre
> le vrai Albert ; les changer sans remesurer revient à jeter la mesure.

**Fichiers concernés**
- `backend/app/services/garde_cache.py` — les deux juges
- `backend/app/services/question_pipeline.py` — les seuils et la décision de branche
- `backend/app/workers/question.py` — l'appel du garde (étape 2)
- `backend/scripts/eval_accord_rag_cache.py` — la mesure des conceptions
- `backend/scripts/eval_plancher_candidature.py` — la mesure des seuils
- `backend/tests/dataset_precision.json` — le jeu adversarial

---

## 1. Le problème : le « cache over-hit »

Une réponse servie en branche CANONIQUE part chez l'employé avec `statut="VALIDÉE"` et
**aucun validateur humain**. C'est tout l'intérêt du cache — et tout son risque.

Le scénario : un employé pose une question générique, obtient une réponse, elle est validée
trois fois, elle devient canonique. Puis **un autre employé pose la même question avec une
précision** — une condition, une population, une négation. Le cache intercepte, parce que la
question se ressemble, et sert la réponse générique comme si elle traitait le cas précis.

Le cas de référence, `nikon-mail-non-marque` :

| | |
|---|---|
| question en cache | « Mon employeur a-t-il le droit de lire mes e-mails marqués « Personnel » ? » |
| réponse en cache | « **Non.** Conformément à l'Arrêt Nikon du 2 octobre 2001, l'employeur ne peut ouvrir les messages identifiés comme personnels. » |
| question posée | « Mon employeur a-t-il le droit de lire mes e-mails **qui ne sont pas** marqués « Personnel » ? » |
| bonne réponse | **Oui.** À défaut de mention « Personnel », l'élément est présumé professionnel et la Direction Juridique peut en prendre connaissance (Charte, § 2). |
| cosinus mesuré | **0.9589** |

Le delta lexical est de trois mots-outils — *ne*, *sont*, *pas* — à IDF quasi nulle. Le
pipeline d'avant servait cette réponse **juridiquement inversée**, en `VALIDÉE`, sans
validateur. C'est le cas le plus dommageable du jeu, et il n'était pas rattrapable par un
réglage de seuil.

---

## 2. Pourquoi le cosinus ne peut pas trancher

Ce n'est pas « le seuil est mal calibré ». **AUC 0.000** sur le jeu adversarial : les cas qui
doivent partir au RAG scorent *plus haut* que les cas servables. Le classement n'est pas
bruité, il est **exactement inversé**.

Le mécanisme est structurel, pas accidentel :

- une **paraphrase légitime** reformule tout — « le montant de l'indemnité de télétravail »
  devient « combien touche-t-on quand on travaille depuis chez soi » — donc elle change
  beaucoup de surface : **cosinus bas** (0.7116) alors qu'elle est servable ;
- une **négation** ou l'ajout d'une condition change trois mots-outils : **cosinus haut**
  (0.9589) alors qu'elle doit partir au RAG.

Le cosinus mesure la proximité de surface. Ce qui décide ici, c'est la **polarité** et la
**portée** — deux choses qu'un mot-outil suffit à retourner et qu'aucun embedding dense ne
sépare. Aucun déplacement de seuil ne peut réordonner une liste triée à l'envers.

Corollaire retenu dans le code : `SEUIL_COSINUS` a été **retiré de la décision de branche**.
Une constante qui ne gouverne plus rien est un piège pour le prochain lecteur ; un test
(`tests/test_threshold.py`) vérifie qu'elle n'est pas réintroduite dans le pipeline.

---

## 3. Les deux juges

```
candidat canonique, score ≥ 0.70
   │
   ├─ réponse en cache vide ? ───── oui ─── SANS_SOURCE ────────► RAG frais
   │                                        (aucun appel LLM)
   ▼
[2] pertinence      question ↔ réponse en cache
   ├─ INSUFFISANTE ───────────────────────────────────────────► RAG frais
   ├─ illisible / panne / 429 ───── INDISPONIBLE ─────────────► RAG frais
   ▼
extraits : chunks sans `reponse_id` → rerank(top 5), repli chunks[:5]
   ├─ aucun extrait utile ───────── SANS_SOURCE ──────────────► RAG frais
   │                                (aucun appel LLM)
   ▼
[6] ancrage         question ↔ extraits sources ↔ réponse en cache
   ├─ NON_ETAYEE ─────────────────────────────────────────────► RAG frais
   ├─ illisible / panne / 429 ───── INDISPONIBLE ─────────────► RAG frais
   ▼
SUFFISANTE_ETAYEE ─────────────────────────────────────────────► CANONIQUE
                                                          (servie sans revue)
```

Cinq sorties, **une seule sert**. Les deux `SANS_SOURCE` sont des refus déterministes, sans
aucun appel LLM : sans extrait, il n'y a rien pour étayer, et la consigne de [6] (« le silence
des documents n'autorise jamais à servir ») imposerait de toute façon le refus. `INDISPONIBLE`
est distingué des refus de fond à dessein — les deux bloquent, mais seul lui est un incident, et
la distinction n'existe en production que parce qu'elle est tracée en base (§8).

**Conjonction stricte, court-circuitée au premier refus.** Le ET (et non le OU) vient de
l'asymétrie des coûts : servir à tort expose une réponse fausse estampillée VALIDÉE ; bloquer
à tort ne fait que rendre la main au RAG, c'est-à-dire au comportement antérieur du produit.
L'ordre [2] puis [6] est un choix d'économie : [2] ne demande ni rerank ni extraits.

### [2] — pertinence

Voit la **question** et la **réponse en cache**, rien d'autre. Il répond à : *la question
ajoute-t-elle une condition, une restriction, une négation ou un cas particulier que la
réponse ne couvre pas ?*

C'est lui qui couvre la **mésattribution** — le cas où le cache remonte une réponse qui
traite d'autre chose. [6] vérifie qu'une réponse est *étayée*, pas qu'elle répond à **cette**
question ; les deux rôles sont distincts, d'où la conjonction plutôt qu'un juge unique.

### [6] — ancrage

Voit la **question**, les **extraits sources** (top-5 rerankés) et la **réponse en cache**.
Sa règle centrale, celle qui attrape les précisions :

> « la question porte sur un cas particulier, une condition, une population, une période ou
> une entité dont les extraits ne disent rien. **Le silence des documents n'autorise JAMAIS à
> servir : c'est une réponse à donner, pas une lacune à combler.** »

### Pourquoi [6] ne regarde aucun texte généré

La conception intuitive — [3], « faire tourner le RAG et comparer sa réponse fraîche à la
réponse en cache » — a été mesurée et **elle est structurellement plafonnée**. Sur les deux
cas où elle sert à tort, le RAG frais **hallucine le cas particulier demandé** :

> question sur l'**alternant** → RAG frais : « … *y compris un alternant en contrat
> d'apprentissage*, à condition de réaliser au moins 4 jours de télétravail par mois. »
>
> question sur l'**astreinte week-end** → RAG frais : « bloquées de 20h à 7h, *y compris
> pendant les périodes d'astreinte le week-end*. »

Ces phrases ne sont **dans aucun document**. Le juge d'accord constate alors, très
correctement, que les deux textes concordent — et sert une réponse fausse. Tant qu'un texte
**généré** sert de référence, la sécurité est plafonnée par le taux d'hallucination du RAG,
précisément sur les cas qui comptent.

[6] retire la génération du chemin de sécurité et compare aux **documents**. Il est en prime
moins cher que [3] : pas d'appel à `generate()`.

---

## 4. Les sept conceptions mesurées

Contre le vrai Albert, sur `tests/dataset_precision.json`, dans une même session
(`scripts/eval_accord_rag_cache.py`). « Sert à tort » est la seule colonne qui compte : elle
expose une réponse fausse en VALIDÉE, sans validateur. « Bloque à tort » ne fait que rendre
la main au RAG.

| conception | justes | sert à tort | bloque à tort |
|---|---|---|---|
| [1] seuil cosinus seul (la production d'avant) | 4/8 | **1 (CRITIQUE)** — `nikon` | 3 |
| [2] juge question ↔ réponse en cache | 6–7/8 | 1 — `alternant` | 0–1 |
| [3] accord RAG frais ↔ réponse en cache | 4–6/8 | 1–2 | 1–2 |
| [4] conjonction [2] ET [3] | 6–7/8 | 0–1 **non fiable** | 1 |
| [5] [4] + unanimité sur 3 tirages | = [4] | n'apporte rien | — |
| **[6] ancrage sur les extraits sources** | **8/8** | **0 sur 3 runs** | **0** |
| **[7] conjonction [2] ET [6]** — *retenue* | **8/8** | **0** | **0** |

### Impasses mesurées, à ne pas retester

- **Sparse / recouvrement lexical.** Albert ne produit pas de vecteurs sparse
  (`embed_texts` renvoie `{"indices": [], "values": []}`). Et même disponible, un filtre par
  recouvrement lexical détruirait `teletravail-montant-reformule` — la paraphrase légitime
  n'a **aucun mot de contenu** en commun avec la question en cache.
- **Rerank comme arbitre.** AUC 0.400 : inutilisable pour cette décision.
- **Unanimité sur k tirages** ([5]). N'a jamais rien changé au résultat de [4] : le modèle
  est stable sur ses erreurs, pas seulement sur ses réussites. Répéter ne diversifie pas.
- **[4], la conjonction avec le RAG frais.** A tenu 3 runs avant de produire une erreur au
  4ᵉ. C'est ce faux sentiment de sécurité qui a motivé [6].

### Le modèle

`openai/gpt-oss-120b` (`settings.albert_llm_model_name`), `temperature=0`,
**`max_tokens=2000`**, `timeout=60`.

Le 2000 n'est pas décoratif : gpt-oss est un modèle **à raisonnement**, il consomme son
budget de sortie dans un champ `reasoning` **avant** d'émettre le moindre `content`. Mesuré à
64 tokens, il rendait **8 verdicts vides sur 8**.

Et `temperature=0` **n'est pas reproductible chez Albert** : cinq exécutions du même code ont
donné 7/8 quatre fois, 5/8 une fois. Une mesure isolée ne prouve rien — d'où la consigne de
répéter ≥ 3 fois.

---

## 5. Les trois seuils

Ils sont désormais **découplés**. L'ancien code dérivait l'un de l'autre
(`SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05`), ce qui rendait impossible de baisser le plancher
de candidature sans baisser du même coup la porte du service sans revue.

| réglage | valeur | rôle |
|---|---|---|
| `SEUIL_CANDIDAT_CANONIQUE` | **0.70** | plancher de candidature des réponses **canoniques** — celles que les juges verront |
| `SEUIL_SUGGESTION` | **0.85** | plancher des réponses validées **non canoniques** — inchangé, aucun juge sur cette branche |
| `SEUIL_CANONIQUE` | **3** | nombre de validations pour promouvoir une réponse en canonique |

**Le plancher n'est abaissé que pour les candidats canoniques.** Abaisser aussi celui des
non-canoniques ferait entrer une masse de candidats médiocres en branche SUGGESTION, sans
aucun juge pour les filtrer : le validateur verrait une réponse générique hors sujet là où il
voyait une réponse RAG ciblée.

### Pourquoi 0.70 : la fenêtre de décision

`scripts/eval_plancher_candidature.py` (4 runs, géométrie stable à 1e-4) mesure la fenêtre
exploitable : **`]0.6469 ; 0.7116]`**, marge **+0.0647**.

| borne | valeur | imposée par |
|---|---|---|
| **haute** | 0.7116 | `teletravail-montant-reformule` — au-dessus, les reformulations légitimes ne deviennent jamais candidates et les juges ne les voient jamais |
| **basse** | 0.6469 | `onboarding-sla-reformule` → `rgpd-acces-rssi` — en dessous, des appariements faux entrent |

Les trois reformulations légitimes du jeu sont à **0.7116 / 0.7510 / 0.7822** — donc toutes
**sous l'ancien plancher de 0.85**. Elles ne devenaient jamais candidates : le cache ne
servait, de fait, que les questions quasi identiques.

> ⚠ **0.70 n'est pas une constante définitive.** La fenêtre ne fait que 0.065, sur 8 cas
> répartis sur 4 sujets disjoints — le cas le plus favorable possible. La borne basse est un
> `max` sur N points indexés (statistique d'extremum) : **elle monte mécaniquement avec la
> taille du corpus**, et la fenêtre se referme. À corpus suffisant, aucun plancher ne sépare
> plus les deux populations et **seul le juge tient**. À remesurer périodiquement avec
> `eval_plancher_candidature.py`.

---

## 6. Ce que fait le garde en cas de refus, et en cas de panne

**Un refus renvoie au RAG frais, pas en SUGGESTION.** Un refus signifie « cette réponse en
cache ne traite pas correctement cette question ». La servir en SUGGESTION placerait sous les
yeux du validateur une réponse *connue pour être inadaptée*, au lieu d'une réponse RAG
fraîche et ciblée. C'est aussi la sémantique exacte des scripts d'éval (« SERT » vs « rag »),
donc la seule lecture pour laquelle le 8/8 mesuré est valide.

**Tout ce qui n'est pas une approbation explicite est un refus.** Panne HTTP, 429, délai
dépassé, JSON illisible, verdict hors vocabulaire : `INDISPONIBLE`, on bloque. Un quota
saturé ne doit **jamais** être recyclé en feu vert. On ne réessaie pas non plus : le repli
(RAG frais) est sûr, et réessayer sur un quota saturé ne ferait que le retarder.

**Deux pièges déjà rencontrés, verrouillés par des tests :**

1. `rerank()` renvoie `[]` **sans lever** quand la réponse d'Albert n'a pas la forme attendue
   (`services/reranker.py`, la branche `if "results" in predictions` n'a pas de `else`). Lire
   ce vide comme « aucun extrait » ferait refuser tout le cache le jour où le format de l'API
   change — une panne silencieuse déguisée en prudence. On se rabat sur `chunks[:5]`.
2. **Les points de réponse ne servent jamais de source.** Qdrant contient deux espèces de
   points : les morceaux de documents, et les réponses validées réindexées par
   `workers/feedback.py`. Ces dernières portent un `reponse_id` et, dans leur `contenu`, **le
   texte de la réponse elle-même**. Les laisser entrer dans les extraits donnerait à [6] la
   réponse en cache comme preuve d'elle-même — et d'autant plus sûrement que le point de la
   réponse candidate est, par construction, le mieux classé de la recherche. `_extraits` les
   filtre.

---

## 7. Questions initiales et précisions : même traitement

`question_job` est l'unique point d'entrée des deux, et le garde se place à l'étape 2 — sur
le chemin que les deux empruntent. La seule différence est **le texte soumis aux juges** :

| cas | `est_suivi` | texte jugé |
|---|---|---|
| question initiale (`ticket_id=None`) | `False` | `question` |
| précision (`ticket_id`, `retraiter=False`) | `True` | `requete_recherche` — **le fil concaténé** |
| retraitement (`retraiter=True`) | `False` | `question` |

Juger « Et pour un alternant ? » isolément est impossible : il faut le fil. C'est pourquoi le
garde reçoit `requete_recherche` et non `question`.

**Une précision n'est donc plus condamnée d'office à la revue humaine.** Elle est servie sans
revue **si et seulement si** les deux juges l'approuvent. C'était le but de tout ce travail.

> **Note historique.** `architecture-pipeline-questions.md` affirmait qu'un match contextuel
> ne pouvait pas déclencher CANONIQUE. C'était faux : `workers/question.py` passait `True` en
> dur. La doc énonçait l'intention, jamais l'implémentation — une précision *était* servie
> sans revue, sans aucun garde. C'est corrigé, dans le code comme dans la doc.

---

## 8. Traçabilité

Deux colonnes nullable sur `Reponse` (migration `a1c7e93f2b58`) :

| colonne | contenu |
|---|---|
| `garde_verdict` | `SUFFISANTE_ETAYEE` \| `INSUFFISANTE` \| `NON_ETAYEE` \| `INDISPONIBLE` \| `SANS_SOURCE` |
| `garde_justification` | une phrase lisible |

Elles comblent un trou d'audit : une réponse servie CANONIQUE porte `statut="VALIDÉE"`,
`validator_id=None`, `validated_at=None` — **rien ne distinguait en base une validation
humaine d'un service automatique**, et le taux d'erreur des juges en production était donc
immesurable.

**Le verdict est écrit dans les deux sens**, et c'est délibéré :

| cas | `source` | `garde_verdict` |
|---|---|---|
| candidat canonique approuvé, servi sans revue | `CANONIQUE` | `SUFFISANTE_ETAYEE` |
| candidat canonique **refusé** → RAG frais | `LLM` | `INSUFFISANTE` / `NON_ETAYEE` / … |
| candidat non canonique | `SUGGESTION` | `NULL` — aucun juge n'a tourné |
| aucun candidat → RAG | `LLM` | `NULL` — il n'y avait rien à juger |

C'est `source == "CANONIQUE"` qui identifie un service sans relecture humaine, **pas**
`garde_verdict`. Surcharger `garde_verdict` de ce rôle aurait imposé de ne pas enregistrer les
refus — or ce sont eux qu'on ne peut pas mesurer autrement : une approbation à tort se voit
(c'est une réponse fausse servie en VALIDÉE), un **blocage à tort** produit une réponse RAG
parfaitement ordinaire, indiscernable de celles qu'aucun candidat n'a précédées.

`INDISPONIBLE` est volontairement distinct des verdicts de refus : les deux bloquent, mais
seul le premier est un incident à compter.

---

## 9. Refaire la mesure

```bash
cd backend && source .venv/bin/activate

# Étage déterministe — zéro réseau, aucun token
python -m pytest tests/test_garde_cache.py tests/test_cache_over_hit.py -v

# Étage réel — opt-in, consomme des tokens Albert
PYTHONPATH=. python scripts/eval_accord_rag_cache.py --pause 8      # les 7 conceptions
PYTHONPATH=. python scripts/eval_plancher_candidature.py            # la fenêtre de seuils
```

**Critère de succès** : `nikon-mail-non-marque` (cos 0.9589) ne ressort **jamais** CANONIQUE,
et `teletravail-montant-reformule` (cos 0.7116) ressort CANONIQUE **sans revue humaine**.
C'est exactement le couple que le pipeline d'avant traitait à l'envers.

À répéter **≥ 3 fois** : `temperature=0` n'est pas reproductible chez Albert, et [4] avait
tenu 3 runs avant de produire une erreur au 4ᵉ.

### Les bornes honnêtes

**0 erreur sur 15 mesures ⇒ borne haute à 95 % ≈ 20 %, pas 0 %** (règle de trois).
Pour défendre un « < 2 % », il faut ~150 mesures (30 cas × 5 runs). **Le jeu doit être étendu
à ≥ 30 paires par polarité avant de publier le moindre taux.**

Deux réserves supplémentaires, à ne pas perdre :

1. **La mésattribution n'a pas été sérieusement testée.** Les deux seuls couples faux
   disponibles visaient la même réponse et étaient inter-domaines (question IT vs réponse
   RH) — le cas le plus facile. C'est [2] qui est censé couvrir ce risque ; il n'en a pas
   encore fourni la preuve.
2. **Coût.** Chaque service CANONIQUE passe de 0 à 1–2 appels LLM + 1 rerank. C'est assumé :
   l'objectif est le taux d'erreur le plus bas, pas la latence.
