# Scénarios de test — mise à jour de document

Ce guide permet de tester les comportements du pipeline en une seule session.
Deux documents suffisent : `test-avantages-v1.txt` (ingestion initiale) et
`test-avantages-v2.txt` (mise à jour).

---

## Pourquoi ces documents sont structurés ainsi

Le chunker BGE-M3 découpe le texte par fenêtre glissante de 384 tokens (chevauchement 128).
Le chevauchement crée des **chunks-frontière** qui contiennent la fin d'une section et le
début de la suivante. Si une réponse stocke un chunk-frontière avec TÉLÉTRAVAIL, elle
devient obsolète quand TÉLÉTRAVAIL est supprimé — même si sa question ne portait pas sur le
télétravail.

**Règles respectées dans ces documents :**
1. Chaque section fait ~250-300 mots (≈ 350-400 tokens) → chaque section a son propre chunk central
2. TÉLÉTRAVAIL est placé **à la fin** de V1 — sa suppression ne décale pas les sections précédentes
3. Une section **PRÉVOYANCE ET SANTÉ** est intercalée juste avant TÉLÉTRAVAIL — elle absorbe
   le chunk-frontière PRÉVOYANCE/TÉLÉTRAVAIL sans qu'aucun ticket ne pointe dessus
4. TR, TRANSPORT, CONGÉS, HORAIRES, PRÉVOYANCE sont **mot pour mot identiques** entre V1 et V2
5. L'ADDENDUM et ACCÈS ET SÉCURITÉ sont ajoutés **à la fin** de V2

---

## Pré-requis

```bash
make up                          # Postgres + Qdrant + Valkey
uvicorn app.main:app --reload    # backend (depuis backend/)
celery -A app.workers.celery_app worker -Q queue_ingestion -c 2
celery -A app.workers.celery_app worker -Q queue_questions -c 4
npm run dev                      # frontend
```

---

## Étape 1 — Ingérer V1

Dans le backoffice, onglet **Documents** :

1. Charger `test-avantages-v1.txt`
2. Nom suggéré : `Guide avantages salariés`
3. Attendre que le statut passe à **Indexé** (quelques secondes)

---

## Étape 2 — Soumettre 5 tickets

Envoyer via l'interface utilisateur (pas l'API — pour que le pipeline RAG complet tourne).
Envoyer un ticket à la fois, attendre la réponse avant le suivant.

| # | Question exacte | Section ciblée | Réponse attendue (thème) |
|---|---|---|---|
| T1 | `Quels sont les deux jours de la semaine autorisés pour le télétravail ?` | TÉLÉTRAVAIL | Mercredi et vendredi |
| T2 | `Jusqu'à quelle date expire la validité des titres-restaurant émis dans l'année ?` | TICKET RESTAURANT | 28 février de l'année suivante |
| T3 | `Entre quelle date commence et se termine la période d'acquisition des congés payés ?` | CONGÉS PAYÉS | Du 1er juin au 31 mai de l'année suivante |
| T4 | `Combien de minutes minimum dure la pause déjeuner ?` | HORAIRES DE TRAVAIL | 45 minutes minimum |
| T5 | `Quelle indemnité kilométrique reçoit un salarié qui vient travailler à vélo ?` | TRANSPORT | 0,25 € par kilomètre, plafonnée à 800 € par an |

**Pourquoi ces questions ?** Chaque question cible un fait numérique ou une date présents
**uniquement** dans la section visée. BGE-M3 n'a aucun autre chunk à lui préférer. Toute
question plus vague (« quelle part prend l'employeur », « horaires de présence obligatoire »)
risque de remonter un chunk d'une section adjacente à cause du chevauchement de 128 tokens.

---

## Étape 3 — Valider les 5 réponses

Dans le backoffice, onglet **Tickets** : valider chaque ticket sans modifier les réponses.
Toutes les 5 réponses doivent passer au statut **VALIDÉE**.

> Les réponses EN_ATTENTE non encore validées sont marquées obsolètes automatiquement
> lors de la mise à jour : les valider après une MAJ indexerait une réponse bâtie sur
> l'ancienne version.

---

## Étape 4 — Mettre à jour vers V2

Dans le backoffice, onglet **Documents** :

1. Ouvrir la fiche du document `Guide avantages salariés`
2. Cliquer **Mettre à jour**
3. Charger `test-avantages-v2.txt`
4. **Lire l'aperçu d'impact** avant de confirmer (voir tableau ci-dessous)
5. Confirmer la mise à jour

---

## Aperçu d'impact attendu

| Compteur | Valeur attendue |
|---|---|
| Réponses obsolètes | **1** — R(T1) télétravail uniquement |
| Réponses à relire | **4** — R(T2), R(T3), R(T4), R(T5) |
| Passages ajoutés | **2** — ADDENDUM (congés <5 ans) et ACCÈS ET SÉCURITÉ |
| Passages retirés | **1** — section TÉLÉTRAVAIL |

Le panneau « Cette version change le contenu » doit afficher les passages ajoutés et le
passage retiré. Les réponses à relire sont listées en-dessous ; chaque question est un
lien qui ouvre le ticket dans un nouvel onglet.

Si tu vois **5 réponses obsolètes**, le document précédent était trop court (tous les chunks
se chevauchaient). Ces fichiers V1/V2 corrigés règlent ce problème.

---

## Étape 5 — Résultats attendus par scénario

### Scénario A — OBSOLÈTE (R de T1)

**Ce qui se passe :**
La section TÉLÉTRAVAIL était à la fin de V1. Elle est absente de V2. Les chunks Qdrant
issus de cette section n'ont plus aucun correspondant dans le nouveau document.

**Mécanisme :** les chunks V1 de TÉLÉTRAVAIL ne trouvent aucune correspondance textuelle
verbatim dans V2 → chunks « perdus » → réponse marquée OBSOLÈTE et retirée de Qdrant.

**Où regarder :**
- Onglet **Réponses enregistrées › Obsolètes** → R(T1) présente
- Onglet standard → R(T1) absente, ne sera plus servie aux utilisateurs
- La prochaine question sur le télétravail repassera par le pipeline RAG (sur V2)

---

### Scénario B — À RELIRE (R de T2, T3, T4, T5)

**Ce qui se passe :**
Les sections TR, CONGÉS, HORAIRES, TRANSPORT sont mot pour mot identiques entre V1 et V2.
Les chunks de ces sections survivent → les 4 réponses ne sont PAS obsolètes.

V2 ajoute l'ADDENDUM (nouveaux droits à congés pour <5 ans d'ancienneté) et la section
ACCÈS ET SÉCURITÉ. Ces passages nouveaux sont détectés.

**Mécanisme :** dès qu'un passage est ajouté ou retiré quelque part dans le document,
**toutes les réponses VALIDÉE survivantes** sont signalées pour relecture — sans filtre
cosinus ni filtre LLM. Il est impossible de savoir automatiquement si un ajout contredit
une réponse : seul un humain peut trancher. Les réponses continuent d'être servies pendant
la relecture.

**Où regarder :**
- Onglet **Réponses enregistrées › À relire** → R(T2), R(T3), R(T4), R(T5) groupées sous
  le document, avec les changements de contenu affichés en tête de groupe
- Chaque question est un lien vers le ticket correspondant (s'ouvre dans un nouvel onglet)

**Actions depuis l'onglet À relire :**
- **Corriger R(T3)** → saisir la nuance (25 j au-delà de 5 ans, 20 j en-dessous) → CORRIGÉE
- **Valider en lot** R(T2), R(T4), R(T5) → toujours exactes → disparaissent de l'onglet
- **Retirer** → si une réponse est trop imprécise → REJETÉE

> La relecture est volontairement large : mieux vaut relire quatre réponses en deux minutes
> que laisser passer silencieusement une contradiction. Le bouton "tout confirmer" permet
> de traiter les cas évidents en lot.

---

### Scénario C — REFORMATAGE PUR (aucun flag)

Pour vérifier la propriété anti-inondation : charger à nouveau V1 (ou V2 avec un espace
de plus) sans modification de fond.

**Résultat attendu :**
- 0 réponse obsolète
- 0 réponse à relire
- Le panneau « Cette version change le contenu » n'apparaît pas dans l'aperçu

---

## Résumé

| Réponse | Ticket | Résultat | Mécanisme |
|---|---|---|---|
| R(T1) — mercredi et vendredi | T1 | **OBSOLÈTE** | Section TÉLÉTRAVAIL supprimée de V2, chunks perdus |
| R(T2) — 28 février | T2 | **À RELIRE** | Passages ajoutés ailleurs dans V2 |
| R(T3) — 1er juin au 31 mai | T3 | **À RELIRE** | Passages ajoutés ailleurs dans V2 |
| R(T4) — 45 minutes | T4 | **À RELIRE** | Passages ajoutés ailleurs dans V2 |
| R(T5) — 0,25 € / km | T5 | **À RELIRE** | Passages ajoutés ailleurs dans V2 |

---

## Diagnostic en cas d'écart

**Encore 5 obsolètes après ces nouveaux fichiers :**
Vérifier que V1 et V2 ont le MÊME TEXTE mot pour mot pour les sections TR/CONGÉS/HORAIRES/TRANSPORT
(y compris l'en-tête du document). Une seule différence de caractère suffit à invalider le chunk.

**R(T1) n'est pas obsolète :**
La section TÉLÉTRAVAIL a peut-être été partiellement reproduite dans V2, ou le chunk
correspondant est recoupé avec un passage encore présent. Vérifier que V2 ne contient
aucun extrait de la section TÉLÉTRAVAIL.

**0 réponse à relire alors que V2 ajoute de nouveaux passages :**
L'extraction textuelle a échoué (fichier corrompu, codec). Vérifier les logs du worker
ingestion et que `ALBERT_API_KEY` est valide.

**Les réponses à relire n'apparaissent pas groupées dans l'onglet :**
Vérifier que les 4 réponses ont bien le statut VALIDÉE avant la mise à jour — les
EN_ATTENTE sont marquées obsolètes, pas à relire.

**Plus de 1 réponse obsolète :**
Le pipeline est correct — c'est le RAG initial qui a récupéré des chunks hors-section.
BGE-M3 crée des embeddings denses : deux questions dans des domaines voisins peuvent
matcher un chunk de la mauvaise section (ex. toute question sur remboursement/employeur
peut remonter un chunk TRANSPORT ; toute question sur présence/disponibilité peut remonter
un chunk TÉLÉTRAVAIL). Quand TÉLÉTRAVAIL est supprimé, ces chunks disparaissent et les
réponses liées deviennent obsolètes à juste titre.
**Solution** : utiliser les questions exactes du tableau. Elles ciblent des valeurs
numériques ou des dates uniques à leur section (28 février, 0,25 €/km, 45 minutes…)
qu'aucun autre chunk du document ne peut battre.
