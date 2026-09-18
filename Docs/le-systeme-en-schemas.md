# Le système en schémas

Tout ce que fait TicketAI, en onze schémas et sans une ligne de technique. Chaque schéma est
autonome : on peut entrer par n'importe lequel. Le schéma 7 raconte l'histoire complète — c'est
celui à lire si vous n'en lisez qu'un.

**Le code couleur est le même partout :**

| | Signification |
|---|---|
| 🟩 **vert** | envoyé à l'employé **sans relecture humaine** |
| 🟨 **ambre** | proposé au validateur — **rien ne part avant qu'un humain ait lu** |
| 🟦 **bleu** | rédigé par l'IA à partir des documents |
| ⬜ **gris** | le système s'abstient |

---

## 1. Les quatre issues possibles d'une question

```mermaid
flowchart LR
    Q["Une question arrive"] --> CAN["✅ CANONIQUE<br/>une réponse déjà validée est resservie<br/><b>sans relecture</b>"]
    Q --> SUG["👀 SUGGESTION<br/>une réponse déjà validée est reproposée<br/><b>un humain relit avant l'envoi</b>"]
    Q --> RAG["🧠 RAG<br/>l'IA rédige à partir des documents<br/><b>un humain relit avant l'envoi</b>"]
    Q --> HD["🤷 HORS DOMAINE<br/>les documents ne répondent pas<br/><b>le système le dit au lieu d'inventer</b>"]

    style CAN fill:#d1fae5,stroke:#059669
    style SUG fill:#fef3c7,stroke:#d97706
    style RAG fill:#dbeafe,stroke:#2563eb
    style HD fill:#e2e8f0,stroke:#64748b
```

*Une seule de ces quatre issues se passe d'un humain. C'est celle que tout le reste du système surveille.*

---

## 2. Une question, de bout en bout

```mermaid
flowchart TD
    A["Question posée"] --> B["Recherche dans la mémoire<br/>réponses déjà validées + passages de documents"]
    B --> C{"Une réponse déjà validée<br/>ressemble-t-elle assez ?"}

    C -- non --> RAG
    C -- oui --> D["🔍 Le garde compare<br/><b>la question posée</b> et <b>la question déjà validée</b>"]

    D -- "OUI, c'est la même demande" --> E{"Cette réponse a-t-elle le droit<br/>d'être servie toute seule ?"}
    D -- "NON, autre demande" --> RAG
    D -- "pas de verdict (panne)" --> SUG

    E -- "canonique · non signalée · très proche" --> CAN["✅ CANONIQUE"]
    E -- "sinon" --> SUG["👀 SUGGESTION"]

    RAG["🧠 L'IA rédige depuis les documents"] --> F{"Les documents<br/>répondent-ils ?"}
    F -- oui --> RAGOUT["🧠 RAG"]
    F -- non --> HD["🤷 HORS DOMAINE"]

    style CAN fill:#d1fae5,stroke:#059669
    style SUG fill:#fef3c7,stroke:#d97706
    style RAG fill:#dbeafe,stroke:#2563eb
    style RAGOUT fill:#dbeafe,stroke:#2563eb
    style HD fill:#e2e8f0,stroke:#64748b
```

*Une panne ne décide de rien : sans verdict du garde, rien n'est jamais servi sans relecture.*

---

## 3. Les deux portes d'entrée de la mémoire

```mermaid
flowchart LR
    Q["Question posée"] --> P1{"Porte du <b>sens</b><br/>ressemble-t-elle à une<br/>question déjà validée ?"}

    P1 -- oui --> EX["La réponse devient <b>candidate</b><br/>→ elle sera examinée"]
    P1 -- non --> P2{"Porte des <b>mots</b><br/>les mots rares<br/>coïncident-ils ?"}

    P2 -- oui --> EX
    P2 -- non --> RIEN["Pas de candidate<br/>→ l'IA rédige depuis les documents"]

    style EX fill:#fef3c7,stroke:#d97706
    style RIEN fill:#dbeafe,stroke:#2563eb
```

*Deux portes séparées, jamais un mélange : un sigle, un numéro d'article ou un nom propre que l'IA ne « comprend » pas passe quand même par la porte des mots.*

---

## 4. Les deux moments où le garde intervient

```mermaid
flowchart TB
    subgraph M1["① Avant de resservir une réponse"]
        direction LR
        A1["Un employé pose une question"] --> A2["🔍 Garde"]
        A2 --> A3["la réponse est resservie<br/>— ou l'IA rédige"]
    end

    subgraph M2["② Avant d'enregistrer une nouvelle formulation"]
        direction LR
        B1["Un validateur clique « Valider »"] --> B2["🔍 Garde"]
        B2 --> B3["la question du ticket rejoint la mémoire<br/>— ou non"]
    end
```

*Le second est le plus important : une formulation enregistrée à tort serait resservie plus tard **sans que le garde soit rappelé**. On le consulte donc avant d'écrire, pas après.*

---

## 5. Ce qu'un OUI ouvre, ce qu'un NON ferme

```mermaid
flowchart LR
    NON["🔍 NON du garde"] --> N1["<b>ferme une porte</b><br/>la réponse trouvée n'est pas réutilisée,<br/>l'IA rédige depuis les documents"]
    OUI["🔍 OUI du garde"] --> O1["<b>n'ouvre rien à lui seul</b><br/>toutes les autres conditions sont<br/>revérifiées derrière lui"]

    style N1 fill:#dbeafe,stroke:#2563eb
    style O1 fill:#fef3c7,stroke:#d97706
```

*On se sert du refus du juge, jamais de son accord. C'est ce déséquilibre volontaire qui rend son élargissement sans risque : lui donner la parole plus souvent ne peut que **fermer** des portes.*

---

## 6. Ce qui se passe quand un document arrive

```mermaid
flowchart TD
    A["Fichier déposé"] --> E{"Document <b>neuf</b><br/>ou <b>nouvelle version</b> ?"}

    E -- "nouvelle version" --> P["Aperçu : ce qui change, avant / après<br/>rien ne bouge tant qu'on n'a pas confirmé"]
    P --> B
    E -- "neuf" --> B["Découpage en passages<br/>chacun reçoit une phrase qui dit <b>de quoi il parle</b>"]

    B --> D["Mise en mémoire"]

    D --> F["<b>Nouvelle version</b> → on réexamine les réponses<br/>bâties sur ce document"]
    D --> G["<b>Document neuf</b> → confrontation :<br/>les réponses déjà servies<br/>sont-elles encore justes ?"]

    F --> H{"Verdict, réponse par réponse"}
    G --> H

    H -- "fausse, et elle citait<br/>le document modifié" --> H1["🚫 Retirée du service"]
    H -- "mise en doute" --> H2["⚠️ Signalée « à relire »<br/>rien n'est supprimé"]
    H -- "toujours juste" --> H3["✅ Rien ne change"]

    style H1 fill:#fee2e2,stroke:#dc2626
    style H2 fill:#fef3c7,stroke:#d97706
    style H3 fill:#d1fae5,stroke:#059669
```

*Un document **neuf** ne retire jamais rien : il ne peut que poser une question à un humain. Seule une réponse qui citait vraiment un document peut être retirée quand ce document change.*

---

## 7. Le scénario complet : le document A, puis le document B

```mermaid
flowchart TD
    subgraph T1["① Le document A arrive — « télétravail : du lundi au mercredi »"]
        A1["« Puis-je télétravailler ? »"] --> A2["🧠 L'IA rédige depuis A"]
        A2 --> A3["3 validations"]
        A3 --> A4["✅ Réponse GÉNÉRALE, canonique"]
    end

    subgraph T2["② Le document B arrive — « les alternants n'y ont pas droit »"]
        B1["Import de B"] --> B2["Confrontation :<br/>la réponse générale tient-elle encore ?"]
        B2 --> B3["⚠️ Signalée « à relire »<br/>toujours proposée · plus jamais servie seule<br/>retirée de Questions fréquentes"]
    end

    subgraph T3["③ Un alternant pose SA question"]
        C1["« Et pour un alternant ? »"] --> C3["🔍 Garde : la réponse générale<br/>répond-elle à <b>cette</b> question ?"]
        C3 -- "NON, autre demande" --> C4["🧠 L'IA rédige depuis B"]
        C4 --> C5["3 validations"]
        C5 --> C6["✅ Réponse SPÉCIFIQUE, canonique"]
    end

    subgraph T4["④ Les deux vivent ensemble"]
        D1["Question générale<br/>→ réponse générale ✅"]
        D2["Question spécifique<br/>→ réponse spécifique ✅"]
    end

    A4 --> B1
    B3 --> C1
    C6 --> D1

    style A4 fill:#d1fae5,stroke:#059669
    style B3 fill:#fef3c7,stroke:#d97706
    style C6 fill:#d1fae5,stroke:#059669
    style D1 fill:#d1fae5,stroke:#059669
    style D2 fill:#d1fae5,stroke:#059669
```

*Deux réponses canoniques sur un même sujet, ce n'est pas un doublon à nettoyer : c'est le fonctionnement normal. Personne n'a rédigé la seconde à la main — elle est née de la question posée.*

---

## 8. Le bon geste sur une réponse signalée

```mermaid
flowchart TD
    X["⚠️ La réponse générale, signalée « à relire »"] --> Y{"Est-elle <b>fausse</b>,<br/>ou seulement <b>incomplète</b> ?"}

    Y -- "incomplète — le cas courant" --> Y1["<b>Modifier</b> : on y ajoute l'exception<br/>👍 un seul geste, les validations sont conservées"]
    Y -- "juste telle quelle" --> Y2["<b>Toujours d'actualité</b><br/>👍 le signalement est levé, tout repart"]
    Y -- "vraiment fausse" --> Y3["<b>Retirer du service</b><br/>👎 tout est à revalider depuis zéro"]

    style Y1 fill:#d1fae5,stroke:#059669
    style Y2 fill:#d1fae5,stroke:#059669
    style Y3 fill:#fee2e2,stroke:#dc2626
```

*Inutile de cliquer « Corriger » pour rédiger la réponse spécifique : elle arrivera toute seule dans la file (schéma 7, acte ③).*

---

## 9. Ce que le signalement « à relire » change vraiment

```mermaid
flowchart TD
    R["Une réponse canonique"] --> A{"Signalée « à relire » ?"}
    A -- non --> A1["servie sans relecture ✅<br/>visible dans Questions fréquentes ✅"]
    A -- oui --> A2["proposée au validateur 👀<br/>absente de Questions fréquentes ❌<br/>validations conservées · rien n'est supprimé"]

    style A1 fill:#d1fae5,stroke:#059669
    style A2 fill:#fef3c7,stroke:#d97706
```

*Un signalement ne détruit rien : il retire le droit d'être servi **sans relecture**. Coût pour l'équipe : une lecture. Coût d'un retrait : trois revalidations.*

---

## 10. Cycle de vie d'une réponse

```mermaid
stateDiagram-v2
    direction LR

    state "Proposée" as P
    state "Validée" as V
    state "Canonique" as C
    state "À relire" as A
    state "Retirée" as R

    [*] --> P : rédigée par l'IA
    P --> V : un validateur accepte
    V --> C : 3 validations
    C --> A : un document neuf ou modifié la met en doute
    A --> C : Toujours d'actualité · Modifier
    A --> R : Retirer du service
    C --> R : contredite par la mise à jour d'un document qu'elle cite
    R --> V : restaurer
```

*Une réponse validée mais pas encore canonique est déjà réutilisée — sous relecture. La canonisation ne change qu'une chose : le droit de partir sans relecture.*

---

## 11. Qui décide quoi

```mermaid
flowchart LR
    S["Les seuils"] --> S1["décident <b>qui est candidat</b><br/>jamais si une réponse est vraie"]
    G["🔍 Le garde"] --> G1["décide si <b>c'est la même demande</b><br/>jamais si une réponse est vraie"]
    H["L'humain"] --> H1["décide si <b>c'est vrai</b><br/><b>lui seul</b>"]

    style S1 fill:#e2e8f0,stroke:#64748b
    style G1 fill:#e2e8f0,stroke:#64748b
    style H1 fill:#d1fae5,stroke:#059669
```

*Toute la machine sert une seule règle : **ne jamais servir une réponse fausse**, même si cela demande plus de travail aux validateurs.*

---

## Pour aller plus loin

| Le détail de… | se lit dans |
|---|---|
| les schémas 2, 3, 5 | [Pipeline de traitement des questions](technique/architecture-pipeline-questions.md) |
| les schémas 4, 5, 11 | [Garde du cache canonique](technique/garde-cache-canonique.md) |
| les schémas 6, 7 | [Quand le corpus bouge](technique/mise-a-jour-documents.md) |
| les schémas 8, 9, 10 | [Réponses enregistrées](fonctionnalites/reponses-enregistrees.md) |
| l'import d'un document | [Base de connaissances](fonctionnalites/base-de-connaissances.md) |
| les chiffres derrière le schéma 7 | [Campagnes de mesure](technique/rapport-test-cache-semantique.md) § 17 |
