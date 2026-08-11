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

import re
import uuid
from datetime import datetime, timezone

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.services.qdrant import delete_response_point
from sqlalchemy.orm import Session

# Raisons d'obsolescence stockées dans `Reponse.obsolete_raison`
RAISON_MAJ = "DOC_MIS_A_JOUR"
RAISON_SUPPRESSION = "DOC_SUPPRIMÉ"
RAISON_MANUELLE = "RETIRÉ_À_LA_MAIN"

# Raisons de relecture stockées dans `Reponse.a_relire_raison`
RAISON_MODIF = "DOC_MODIFIÉ"
RAISON_ILLISIBLE = "VERSION_SORTANTE_ILLISIBLE"

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
    return [
        p for p in (_normaliser(bloc) for bloc in texte.split("\n\n")) if len(p) >= LONGUEUR_MIN_AJOUT
    ]


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
        copies = {
            r[0]
            for r in db.query(Reponse.id).filter(Reponse.reponse_source_id.in_(frontiere)).all()
        }
        frontiere = copies - vus
        vus |= frontiere
    return vus


def reponses_obsoletes(
    db: Session,
    doc_id: str,
    indices: set[int] | None = None,
) -> list[Reponse]:
    """Réponses encore réutilisables qui s'appuient sur les chunks visés.

    ``indices=None`` → tout le document est concerné (cas de la suppression).
    Seules les ``VALIDÉE`` non déjà obsolètes sont retenues : ce sont les seules
    que ``_trouver_reponse_reutilisable`` peut resservir.
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
            Reponse.statut == "VALIDÉE",
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
) -> list[Reponse]:
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

    ids_en_attente = {
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
    en_attente = db.query(Reponse).filter(Reponse.id.in_(ids_en_attente)).all() if ids_en_attente else []
    retirer_du_service(db, en_attente, raison, doc_id, version)

    return reponses


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
    """Efface les colonnes de relecture, la suggestion LLM et les passages associés."""
    r.a_relire = False
    r.a_relire_raison = None
    r.a_relire_doc_id = None
    r.a_relire_version = None
    r.a_relire_at = None
    r.correction_suggeree = None
    r.passages_pertinents = None


def marquer_a_relire(
    db: Session,
    doc_id: str,
    version: int,
    raison: str = RAISON_MODIF,
) -> list[Reponse]:
    """Signale pour relecture les réponses encore servies potentiellement touchées.

    Répond à l'angle mort de ``indices_modifies`` : le contenu du document a
    changé quelque part, sans qu'aucun passage cité n'ait bougé. Impossible de
    savoir si le nouveau texte contredit ces réponses — seul un humain le peut.
    Le périmètre est donc **tout le document** : cibler « près de la zone
    modifiée » raterait précisément le cas visé, la contradiction étant ailleurs
    par définition.

    Toutes les réponses VALIDÉE survivantes sont signalées sans filtre automatique.
    Le filtre cosinus + LLM a été supprimé : il produisait des faux positifs
    (timeouts → fallback conservateur, jugements LLM erronés) sans garantie de
    zéro faux positif. L'humain lit les changements une fois par groupe et confirme
    en lot — c'est plus fiable et aussi rapide.

    Ne touche pas à Qdrant : c'est toute la différence avec l'obsolescence. La
    réponse continue d'être servie tant que personne n'a tranché.

    Flague la **famille entière** et non les seules ``racines`` : ``racines``
    conserve les copies dont la source est hors ensemble, qu'un futur filtre
    ``reponse_source_id IS NULL`` rendrait invisibles — donc indéboulonnables.
    Seul le *comptage* passe par ``racines``.

    Les réponses déjà obsolètes sont hors jeu : ``reponses_obsoletes`` les filtre,
    et ``marquer_obsoletes`` commite avant qu'on arrive ici.
    """
    reponses = reponses_obsoletes(db, doc_id, indices=None)

    maintenant = datetime.now(timezone.utc)
    for r in reponses:
        r.a_relire = True
        r.a_relire_raison = raison
        r.a_relire_doc_id = doc_id
        r.a_relire_version = version
        r.a_relire_at = maintenant

    db.commit()
    return reponses


def confirmer_actualite(db: Session, reponses: list[Reponse]) -> None:
    """Lève le signalement : un humain a relu et jugé la réponse toujours juste."""
    for r in reponses:
        lever_a_relire(r)
    db.commit()
