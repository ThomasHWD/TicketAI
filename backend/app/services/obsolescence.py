"""Détection des réponses rendues obsolètes par un changement de document.

**La comparaison est document ↔ document : le texte de la réponse n'y participe
jamais.** Le LLM reformule (« 2 jours » devient « deux jours hebdomadaires ») ;
chercher ses phrases dans le document n'aurait aucun sens. Ce qu'on exploite,
c'est que ``reponse_chunks`` mémorise *quels passages* ont servi, et que Qdrant
conserve leur texte brut dans le payload : il suffit de vérifier si ces passages
figurent encore dans la nouvelle version.

::

    DOCUMENT v1, chunk #7 (payload Qdrant `contenu`)
      « Le télétravail est limité à 2 jours par semaine, sur accord du manager. »
            │  reponse_chunks (doc_id=X, chunk_index=7)
            ↓
    RÉPONSE CANONIQUE — texte du LLM, JAMAIS comparé
      « Vous pouvez télétravailler jusqu'à deux jours hebdomadaires… »

    v2 : « …limité à 3 jours par semaine… » → passage absent → réponse obsolète

Insensible au re-découpage : ``chunk_text()`` produit des sous-chaînes du texte
complet (``RecursiveCharacterTextSplitter`` sur ``"\\n\\n".join(pages)``), donc
« ce passage existe-t-il encore ? » se répond par une recherche de sous-chaîne,
sans jamais comparer des frontières de chunks — lesquelles se décalent dès la
première modification et ne veulent rien dire d'une version à l'autre.
"""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.qdrant import delete_response_point
from sqlalchemy.orm import Session

# Raisons d'obsolescence stockées dans `Reponse.obsolete_raison`
RAISON_MAJ = "DOC_MIS_A_JOUR"
RAISON_SUPPRESSION = "DOC_SUPPRIMÉ"
RAISON_MANUELLE = "RETIRÉ_À_LA_MAIN"

# Raisons de relecture stockées dans `Reponse.a_relire_raison`
RAISON_MODIF = "DOC_MODIFIÉ"
RAISON_ILLISIBLE = "VERSION_SORTANTE_ILLISIBLE"

# Verdict de la ré-vérification (cf. `services/reverification.py`)
RAISON_CONTREDITE = "CONTREDITE_PAR_MAJ"  # obsolete_raison
RAISON_CONTREDITE_PROB = "CONTREDITE_PROBABLE"  # a_relire_raison
RAISON_ANALYSE = "ANALYSE_EN_COURS"  # a_relire_raison, transitoire
RAISON_INDISPONIBLE = "ANALYSE_INDISPONIBLE"  # a_relire_raison, repli
RAISON_PARTIELLE = "ANALYSE_PARTIELLE"  # a_relire_raison, budget épuisé
RAISON_MASSIVE = "REECRITURE_MASSIVE"  # a_relire_raison, document réécrit

_ESPACES = re.compile(r"\s+")

# En deçà, un paragraphe est un titre ou un artefact de mise en page : le
# signaler comme « passage ajouté » noierait le signal utile.
LONGUEUR_MIN_AJOUT = 40

# Longueur d'un extrait de passage montré à l'humain.
LONGUEUR_EXTRAIT = 240

# Extraits conservés par sens de changement. Trois suffisent à faire comprendre
# ce qui a bougé ; au-delà, on recopierait le document dans une colonne JSON.
MAX_EXTRAITS = 3


def extrait(texte: str) -> str:
    """Passage tronqué pour affichage.

    Vit ici, et non dans ``api/v1/documents.py``, pour que l'écran d'impact et
    les ``changements`` figés par le worker montrent exactement le même texte —
    ce sont les deux faces du même signalement, à quelques secondes d'écart.
    """
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_EXTRAIT else texte[:LONGUEUR_EXTRAIT] + "…"


def _normaliser(texte: str) -> str:
    """Espaces compactés, insécables normalisés, strip.

    Les deux textes sont déjà passés par ``clean_text`` : cette normalisation ne
    couvre que le rognage de bordure du splitter et les insécables des PDF.
    La classe d'espaces est unicode par défaut sur une chaîne : elle couvre
    donc aussi l'espace insécable des PDF, sans traitement dédié.
    """
    return _ESPACES.sub(" ", texte).strip()


def indices_modifies(anciens_chunks: dict[int, str], nouveau_texte: str) -> set[int]:
    """Indices des chunks de la version sortante absents de la nouvelle version.

    ``anciens_chunks`` : ``{chunk_index: contenu}`` capturé dans Qdrant **avant**
    toute suppression — c'est la seule source du texte de la version sortante.
    """
    ref = _normaliser(nouveau_texte)
    return {i for i, txt in anciens_chunks.items() if _normaliser(txt or "") not in ref}


def decouper_en_passages(texte: str) -> list[str]:
    """Paragraphes du texte, les fragments trop courts écartés.

    Le paragraphe, et non le chunk : un chunk fait 384 tokens, soit un extrait
    illisible dans l'écran d'impact et une granularité si grosse que la moindre
    retouche marquerait 1 500 caractères comme « ajoutés ». ``clean_text``
    normalise déjà les sauts multiples en ``\\n\\n``, et ``texte_complet`` joint
    les pages pareillement : la frontière est fiable.

    Le seuil écarte les titres, numérotations et fragments de mise en page, que
    les PDF produisent en quantité et qui ne portent aucune information.
    """
    return [p for p in (_normaliser(bloc) for bloc in texte.split("\n\n")) if len(p) >= LONGUEUR_MIN_AJOUT]


def passages_ajoutes(nouveaux_passages: list[str], ancien_texte: str) -> list[str]:
    """Passages de la nouvelle version absents de l'ancienne — la détection en miroir.

    ``indices_modifies`` répond « ce sur quoi la réponse s'appuyait a-t-il
    changé ? ». Il est aveugle au cas inverse : un article ajouté **ailleurs**
    dans le document, qui contredirait une réponse existante, ne touche aucun
    passage cité et passe donc inaperçu. Or les mises à jour de charte sont
    typiquement additives (« article 7 bis »), et cette réponse-là continuerait
    d'être servie automatiquement.

    Aucune règle automatique ne peut décider si un ajout invalide une réponse :
    cela demande de lire. La fonction ne sert donc **pas** à rendre obsolète,
    seulement à rendre visible — l'écran d'impact affiche les passages ajoutés
    et laisse l'arbitrage à l'humain.

    Comme ``indices_modifies``, la recherche est une sous-chaîne du texte complet
    normalisé : un paragraphe simplement recoupé ou refusionné reste retrouvé, et
    ne se signale donc pas comme un ajout.
    """
    ref = _normaliser(ancien_texte)
    return [p for p in nouveaux_passages if _normaliser(p or "") not in ref]


SENS_AJOUT = "AJOUT"
SENS_RETRAIT = "RETRAIT"
SENS_REECRITURE = "REECRITURE"


@dataclass(frozen=True)
class Unite:
    """Un changement isolé entre deux versions, apparié quand c'est une réécriture.

    L'appariement est ce qui distingue cette structure des deux listes plates que
    produisait ``passages_ajoutes`` appelé dans les deux sens. « ce paragraphe a
    été remplacé par celui-ci » se juge ; « un paragraphe est apparu quelque part
    et un autre a disparu ailleurs » ne se juge pas — c'est la même information
    privée de ce qui la rend exploitable, par un humain comme par un modèle.
    """

    sens: str  # SENS_AJOUT | SENS_RETRAIT | SENS_REECRITURE
    avant: str | None  # None pour un ajout
    apres: str | None  # None pour un retrait

    @property
    def texte(self) -> str:
        """Le versant à indexer et à faire lire : le nouveau s'il existe."""
        return self.apres or self.avant or ""


def _requalifier(unite: Unite, ref_ancien: str, ref_nouveau: str) -> Unite | None:
    """Écarte les unités qui ne portent rien de neuf, requalifie les demi-vraies.

    ``SequenceMatcher`` raisonne sur des *positions* dans une liste de
    paragraphes : déplacer un article en tête de document lui fait voir une
    suppression et une insertion, alors que le texte est rigoureusement le même.
    Sans cette passe, un simple redécoupage de pages produirait des dizaines
    d'unités fantômes et rendrait l'étage suivant aussi inondant que le
    signalement en bloc qu'on remplace.

    Le test est celui, exact au caractère près, qui garde déjà le reformatage
    hors du calcul d'obsolescence : « ce paragraphe existe-t-il, normalisé,
    ailleurs dans l'autre version ? ».
    """
    neuf = unite.apres is not None and _normaliser(unite.apres) not in ref_ancien
    perdu = unite.avant is not None and _normaliser(unite.avant) not in ref_nouveau

    if neuf and perdu:
        return unite
    if neuf:
        # L'ancien paragraphe survit ailleurs : seul le nouveau est un vrai apport.
        return Unite(SENS_AJOUT, None, unite.apres)
    if perdu:
        # Le nouveau paragraphe existait déjà : seul l'ancien a réellement disparu.
        return Unite(SENS_RETRAIT, unite.avant, None)
    return None


def unites_de_changement(ancien_texte: str, nouveau_texte: str) -> list[Unite]:
    """Ce qui a changé d'une version à l'autre, apparié quand c'est appariable.

    ``SequenceMatcher`` aligne les deux listes de paragraphes et rend des blocs
    ``replace`` / ``delete`` / ``insert``. Un ``replace`` est apparié par position
    à l'intérieur du bloc : c'est une approximation, mais dans le seul cas qui
    compte — un paragraphe réécrit au milieu de paragraphes stables — le bloc ne
    contient qu'une paire et l'appariement est exact.

    ``autojunk=False`` n'est pas un détail : à ``True`` (le défaut), l'heuristique
    « junk » écarte tout élément présent dans plus de 1 % d'une séquence de plus
    de 200 items. Sur un document à en-têtes ou mentions répétés — la norme pour
    une charte paginée — elle fabrique des ``replace`` entre paragraphes sans
    rapport, donc des réécritures inventées.

    **Aucun seuil de similarité globale n'intervient.** Sur une charte de 60 000
    caractères, remplacer « 2 jours » par « 3 jours » donne un ratio de 0,9999 :
    tout filtre par ratio classerait « cosmétique » exactement le changement le
    plus dangereux. Le garde-fou contre le reformatage est ``_requalifier``, qui
    compare des textes et non des scores.

    Liste vide ⇒ la nouvelle version ne dit rien de neuf : aucune réponse n'est
    à inquiéter, et le pipeline de ré-vérification n'est même pas lancé.
    """
    anciens = decouper_en_passages(ancien_texte)
    nouveaux = decouper_en_passages(nouveau_texte)

    brutes: list[Unite] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, anciens, nouveaux, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        supprimes, ajoutes = anciens[i1:i2], nouveaux[j1:j2]
        commun = min(len(supprimes), len(ajoutes))
        brutes += [Unite(SENS_REECRITURE, a, n) for a, n in zip(supprimes[:commun], ajoutes[:commun], strict=True)]
        brutes += [Unite(SENS_RETRAIT, a, None) for a in supprimes[commun:]]
        brutes += [Unite(SENS_AJOUT, None, n) for n in ajoutes[commun:]]

    ref_ancien, ref_nouveau = _normaliser(ancien_texte), _normaliser(nouveau_texte)
    return [u for u in (_requalifier(b, ref_ancien, ref_nouveau) for b in brutes) if u is not None]


# Au-delà, sérialiser les unités recopierait le document dans une colonne JSON.
MAX_OCTETS_UNITES = 256 * 1024


def analyser_changements(ancien_texte: str, nouveau_texte: str) -> dict:
    """Le résumé des changements, tel qu'il est affiché puis figé sur la version.

    Fonction **pure** à deux chaînes : l'aperçu (``api/v1/documents.py``) et le
    worker (``workers/document_update.py``) en avaient chacun une copie, dont
    l'une se déclarait « le jumeau » de l'autre — deux implémentations tenues de
    rester d'accord sans aucun test pour le garantir. Les deux appelants gardent
    leur propre ``extract_text`` ; la logique ne vit plus qu'ici.

    ``nb_ajoutes`` / ``nb_retires`` / ``extraits_*`` sont conservés tels quels :
    l'onglet « À relire » lit ces clés dans les lignes ``DocumentVersion`` déjà
    écrites, qui ne seront pas rétro-remplies.
    """
    unites = unites_de_changement(ancien_texte, nouveau_texte)
    ajoutes = [u for u in unites if u.sens in (SENS_AJOUT, SENS_REECRITURE)]
    retires = [u for u in unites if u.sens in (SENS_RETRAIT, SENS_REECRITURE)]

    return {
        "nb_unites": len(unites),
        "nb_ajoutes": len(ajoutes),
        "nb_retires": len(retires),
        "extraits_ajoutes": [extrait(u.apres or "") for u in ajoutes[:MAX_EXTRAITS]],
        "extraits_retires": [extrait(u.avant or "") for u in retires[:MAX_EXTRAITS]],
        **serialiser_unites(unites),
    }


def serialiser_unites(unites: list[Unite], max_octets: int = MAX_OCTETS_UNITES) -> dict:
    """Les unités sous forme JSON-able, tronquées à un budget d'octets.

    Elles transitent par ``DocumentVersion.changements`` et non par les kwargs
    Celery : le worker de ré-vérification relit ainsi *exactement* ce que
    l'humain a vu à l'écran d'impact, et n'a pas besoin de ré-extraire une
    archive qui aura peut-être été purgée. Un rejeu depuis le retry admin part
    donc du même diff, pas d'un diff recalculé sur un disque qui a bougé.

    ``unites_tronquees`` n'est pas décoratif : il dit à l'étage de décision que
    le jugement portera sur un échantillon, pas sur la totalité des changements.
    """
    gardees: list[dict] = []
    octets = 0
    for u in unites:
        brut = {"sens": u.sens, "avant": u.avant, "apres": u.apres}
        octets += len(json.dumps(brut, ensure_ascii=False).encode())
        if octets > max_octets:
            break
        gardees.append(brut)

    return {"unites": gardees, "unites_tronquees": len(gardees) < len(unites)}


def deserialiser_unites(changements: dict | None) -> list[Unite]:
    """Relit les unités figées sur la version. Tolérant aux lignes d'avant."""
    if not changements:
        return []
    return [Unite(u.get("sens", SENS_AJOUT), u.get("avant"), u.get("apres")) for u in changements.get("unites") or []]


def fermeture_copies(db: Session, graines: set[uuid.UUID]) -> set[uuid.UUID]:
    """Descend des réponses-graines vers toutes leurs copies, transitivement.

    ``reponse_chunks`` n'est peuplé que sur la branche RAG : les copies
    SUGGESTION/CANONIQUE ne citent aucun chunk et ne se rattachent à leur origine
    que par ``reponse_source_id``. Et comme ``corriger_reponse`` réindexe la
    *copie* dans Qdrant, une copie peut à son tour être source — d'où la descente
    transitive. L'ensemble des visités garantit la terminaison même sur un cycle
    (``A.source = B`` et ``B.source = A``).
    """
    vus = set(graines)
    frontiere = set(graines)
    while frontiere:
        copies = {r[0] for r in db.query(Reponse.id).filter(Reponse.reponse_source_id.in_(frontiere)).all()}
        frontiere = copies - vus
        vus |= frontiere
    return vus


def reponses_obsoletes(
    db: Session,
    doc_id: str,
    indices: set[int] | None = None,
) -> list[Reponse]:
    """Réponses indexées dans Qdrant qui s'appuient sur les chunks visés.

    ``indices=None`` → tout le document est concerné (cas de la suppression).
    VALIDÉE et CORRIGÉE sont retenues : les deux sont indexées dans Qdrant par
    ``feedback_job`` et doivent être retirées de l'index à la suppression du
    document source. CORRIGÉE n'est pas resservie directement (filtre VALIDÉE
    dans ``_trouver_reponse_reutilisable``) mais son point Qdrant subsiste et
    polluerait le contexte RAG si on ne le supprime pas.
    """
    if indices is not None and not indices:
        return []

    q = db.query(ReponseChunk.reponse_id).filter(ReponseChunk.doc_id == doc_id)
    if indices is not None:
        q = q.filter(ReponseChunk.chunk_index.in_(sorted(indices)))

    graines = {r[0] for r in q.distinct().all()}
    if not graines:
        return []

    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, graines)),
            Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def racines(reponses: list[Reponse]) -> list[Reponse]:
    """Réduit une famille aux réponses *distinctes* qu'elle représente.

    ``reponses_obsoletes`` remonte les copies SUGGESTION/CANONIQUE : une réponse
    réutilisée cinq fois apparaît six fois. Compter ces lignes gonflerait
    l'annonce « N réponses vont devenir obsolètes » d'un facteur arbitraire.

    On écarte donc les copies **dont la source est elle-même dans l'ensemble** —
    et non toutes les copies : une copie VALIDÉE dont la source a été rejetée
    n'est représentée par personne d'autre, et doit rester comptée.
    """
    ids = {r.id for r in reponses}
    return [r for r in reponses if r.reponse_source_id not in ids]


def marquer_obsoletes(
    db: Session,
    doc_id: str,
    raison: str,
    version: int | None = None,
    indices: set[int] | None = None,
) -> tuple[list[Reponse], list[Reponse]]:
    """Retire de Qdrant puis marque obsolètes les réponses concernées.

    Le point Qdrant supprimé est la garantie principale : la réponse n'est plus
    jamais retrouvée. Le drapeau assure la traçabilité et l'onglet « Obsolètes ».
    Idempotent : un second passage ne retrouve rien (filtre ``obsolete is False``)
    et ``delete_response_point`` sur un id absent est un no-op.

    Les réponses EN_ATTENTE liées au document sont également obsolètes : elles ont
    été générées sur l'ancienne version et n'ont pas encore été validées. Elles
    n'ont pas de point Qdrant (indexé seulement après validation) ; l'appel
    ``delete_response_point`` est donc un no-op pour elles.
    """
    reponses = reponses_obsoletes(db, doc_id, indices)
    retirer_du_service(db, reponses, raison, doc_id, version)
    return reponses, perimer_en_attente(db, doc_id, raison, version)


def perimer_en_attente(db: Session, doc_id: str, raison: str, version: int | None) -> list[Reponse]:
    """Périme les réponses EN_ATTENTE bâties sur le document, quel que soit le chunk cité.

    Aucun jugement n'est requis pour celles-là : elles n'ont jamais été servies,
    ne sont pas indexées, et les valider plus tard reviendrait à publier une
    réponse construite sur une version qui n'existe plus. Les repasser au RAG
    (``requeuer_en_attente``) coûte un ticket retraité et rend une réponse à jour
    — c'est strictement moins cher que de faire trancher un humain ou un modèle.

    Extrait de ``marquer_obsoletes`` parce que la mise à jour n'appelle plus que
    cette moitié : depuis que le verdict revient à la ré-vérification, faire
    prononcer une obsolescence à ``indices_modifies`` seul n'a plus lieu d'être.
    """
    ids = {
        r[0]
        for r in db.query(Reponse.id)
        .join(ReponseChunk, ReponseChunk.reponse_id == Reponse.id)
        .filter(
            ReponseChunk.doc_id == doc_id,
            Reponse.statut == "EN_ATTENTE",
            Reponse.obsolete.is_(False),
        )
        .distinct()
        .all()
    }
    en_attente = db.query(Reponse).filter(Reponse.id.in_(ids)).all() if ids else []
    retirer_du_service(db, en_attente, raison, doc_id, version)
    return en_attente


def retirer_du_service(
    db: Session,
    reponses: list[Reponse],
    raison: str,
    doc_id: str | None,
    version: int | None,
) -> None:
    """Retire de Qdrant et pose les drapeaux, sur une liste déjà constituée.

    Extrait de ``marquer_obsoletes`` pour servir aussi le retrait à la main
    (``POST /reponses/{id}/retirer``), qui part d'une famille précise et non
    d'un document.
    """
    maintenant = datetime.now(timezone.utc)

    for r in reponses:
        delete_response_point(str(r.id))
        r.obsolete = True
        r.obsolete_raison = raison
        r.obsolete_doc_id = doc_id
        r.obsolete_version = version
        r.obsolete_at = maintenant
        # Une réponse signalée à la v3 puis périmée à la v4 siégerait dans les
        # deux onglets. L'obsolescence tranche la question que la relecture
        # posait : le signal n'a plus lieu d'être.
        lever_a_relire(r)

    db.commit()


def lever_a_relire(r: Reponse) -> None:
    """Efface les colonnes de relecture, la suggestion LLM et les passages associés.

    Ne touche **pas** à ``analyse_justification`` / ``analyse_extraits`` :
    ``retirer_du_service`` passe par ici avant de poser une obsolescence, et
    effacer la justification en chemin priverait l'onglet « Obsolètes » de la
    seule chose qui rend un retrait sec compréhensible. Les deux colonnes sont
    remises à zéro explicitement par le verdict ``INTACTE``, qui est le seul cas
    où plus rien n'est à expliquer.
    """
    r.a_relire = False
    r.a_relire_raison = None
    r.a_relire_doc_id = None
    r.a_relire_version = None
    r.a_relire_at = None
    r.correction_suggeree = None
    r.passages_pertinents = None


def poser_a_relire(reponses: list[Reponse], raison: str, doc_id: str, version: int) -> None:
    """Pose le drapeau de relecture, sans commit ni Qdrant.

    Ne touche pas à Qdrant : c'est toute la différence avec l'obsolescence. La
    réponse continue d'être servie tant que personne n'a tranché.
    """
    maintenant = datetime.now(timezone.utc)
    for r in reponses:
        r.a_relire = True
        r.a_relire_raison = raison
        r.a_relire_doc_id = doc_id
        r.a_relire_version = version
        r.a_relire_at = maintenant


def marquer_a_relire(
    db: Session,
    doc_id: str,
    version: int,
    raison: str = RAISON_MODIF,
) -> list[Reponse]:
    """Signale en bloc toutes les réponses encore servies du document.

    Périmètre volontairement large — tout le document — parce qu'aucune
    information ne permet de faire mieux dans les deux cas qui en restent
    tributaires : la version sortante illisible (``RAISON_ILLISIBLE``, pas de
    diff calculable) et le document réécrit au-delà du plafond
    (``RAISON_MASSIVE``, plus rien à discriminer).

    Ce n'était **pas** un cas particulier auparavant : la moindre retouche
    passait par ici, et envoyait tout le corpus validé du document en relecture.
    Le tri est désormais fait par ``workers/reverification.py``, qui juge réponse
    par réponse ; cette fonction est le repli, plus la règle.

    Flague la **famille entière** et non les seules ``racines`` : ``racines``
    conserve les copies dont la source est hors ensemble, qu'un futur filtre
    ``reponse_source_id IS NULL`` rendrait invisibles — donc indéboulonnables.
    Seul le *comptage* passe par ``racines``.

    Les réponses déjà obsolètes sont hors jeu : ``reponses_obsoletes`` les filtre,
    et ``marquer_obsoletes`` commite avant qu'on arrive ici.
    """
    reponses = reponses_obsoletes(db, doc_id, indices=None)
    poser_a_relire(reponses, raison, doc_id, version)
    db.commit()
    return reponses


def flaguer_en_analyse(db: Session, doc_id: str, version: int) -> list[Reponse]:
    """Marque « analyse en cours » les réponses que la ré-vérification va juger.

    Posé **dans la foulée de la bascule de version**, avant que le job d'analyse
    ne démarre. Celui-ci met de trente secondes à quelques minutes ; sans ce
    drapeau, il existerait une fenêtre pendant laquelle le document dit une chose,
    les réponses canoniques en disent une autre, et rien nulle part ne le signale.

    Le drapeau n'est pas une demande de relecture : c'est un état transitoire que
    le job résout — il le lève (``INTACTE``), l'aggrave en obsolescence
    (``CONTREDITE``) ou le requalifie (``INCERTAIN``, budget, panne). Le front le
    présente donc comme un badge neutre et non comme une tâche à traiter. S'il
    survit à la fin du job, c'est que le worker est mort : le ``on_failure``
    le rabat alors en ``RAISON_INDISPONIBLE``.
    """
    return marquer_a_relire(db, doc_id, version, RAISON_ANALYSE)


def confirmer_actualite(db: Session, reponses: list[Reponse]) -> None:
    """Lève le signalement : un humain a relu et jugé la réponse toujours juste."""
    for r in reponses:
        lever_a_relire(r)
    db.commit()


def requeuer_en_attente(db: Session, reponses: list[Reponse]) -> None:
    """Re-soumet au pipeline RAG les tickets dont la réponse EN_ATTENTE vient d\'être rendue obsolète.

    Import différé de ``question_job`` pour briser la dépendance circulaire :
    ``obsolescence`` ← importe ← ``question``, et ``question`` importe ce module.
    On ne l\'importe qu\'au moment de l\'appel, pas au chargement du module.
    """
    if not reponses:
        return

    from app.workers.question import question_job  # noqa: PLC0415 — import différé anti-circulaire

    ids_tickets = {r.ticket_id for r in reponses if r.ticket_id is not None}
    if not ids_tickets:
        return

    tickets = db.query(Ticket).filter(Ticket.id.in_(ids_tickets)).all()
    for ticket in tickets:
        ticket.statut_job = "EN_ATTENTE"
        ticket.statut_ticket = "NOUVEAU"
        ticket.erreur = None
    db.commit()

    for ticket in tickets:
        question_job.delay(
            question=ticket.question,
            domaine=ticket.domaine,
            user_id=str(ticket.user_id) if ticket.user_id else None,
            ticket_id=str(ticket.id),
            objet=ticket.objet,
            retraiter=True,
        )
        print(f"[REQUEUE] ticket {ticket.id} re-soumis au pipeline RAG")
