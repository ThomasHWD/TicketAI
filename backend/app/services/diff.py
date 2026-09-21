"""Calcul de diff textuel entre deux versions d'un document. Module pur : pas de dépendance DB ni modèles."""

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_ESPACES = re.compile(r"\s+")

# En deçà, un paragraphe est un titre ou un artefact de mise en page.
LONGUEUR_MIN_AJOUT = 40

# Longueur d'un extrait de passage montré à l'humain.
LONGUEUR_EXTRAIT = 240

# Extraits conservés par sens de changement.
MAX_EXTRAITS = 3

# Au-delà, sérialiser les unités recopierait le document dans une colonne JSON.
MAX_OCTETS_UNITES = 256 * 1024

SENS_AJOUT = "AJOUT"
SENS_RETRAIT = "RETRAIT"
SENS_REECRITURE = "REECRITURE"


@dataclass(frozen=True)
class Unite:
    """Changement isolé entre deux versions, apparié (AVANT/APRÈS) quand c'est une réécriture."""

    sens: str  # SENS_AJOUT | SENS_RETRAIT | SENS_REECRITURE
    avant: str | None  # None pour un ajout
    apres: str | None  # None pour un retrait

    @property
    def texte(self) -> str:
        """Le versant à indexer et à faire lire : le nouveau s'il existe."""
        return self.apres or self.avant or ""


def extrait(texte: str) -> str:
    """Passage tronqué pour affichage. Centralised so preview screen and frozen changements show identical text."""
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_EXTRAIT else texte[:LONGUEUR_EXTRAIT] + "…"


def _normaliser(texte: str) -> str:
    """Espaces compactés, insécables normalisés, strip."""
    return _ESPACES.sub(" ", texte).strip()


def indices_modifies(anciens_chunks: dict[int, str], nouveau_texte: str) -> set[int]:
    """Indices des chunks de la version sortante absents de la nouvelle version."""
    ref = _normaliser(nouveau_texte)
    return {i for i, txt in anciens_chunks.items() if _normaliser(txt or "") not in ref}


def decouper_en_passages(texte: str) -> list[str]:
    """Paragraphes du texte, les fragments trop courts écartés."""
    return [p for p in (_normaliser(bloc) for bloc in texte.split("\n\n")) if len(p) >= LONGUEUR_MIN_AJOUT]


def passages_ajoutes(nouveaux_passages: list[str], ancien_texte: str) -> list[str]:
    """Passages de la nouvelle version absents de l'ancienne."""
    ref = _normaliser(ancien_texte)
    return [p for p in nouveaux_passages if _normaliser(p or "") not in ref]


def _requalifier(unite: Unite, ref_ancien: str, ref_nouveau: str) -> Unite | None:
    """Écarte les unités qui ne portent rien de neuf, requalifie les demi-vraies."""
    neuf = unite.apres is not None and _normaliser(unite.apres) not in ref_ancien
    perdu = unite.avant is not None and _normaliser(unite.avant) not in ref_nouveau

    if neuf and perdu:
        return unite
    if neuf:
        return Unite(SENS_AJOUT, None, unite.apres)
    if perdu:
        return Unite(SENS_RETRAIT, unite.avant, None)
    return None


def unites_de_changement(ancien_texte: str, nouveau_texte: str) -> list[Unite]:
    """Ce qui a changé, apparié quand appariable. `autojunk=False`: with True, headers/footers repeated in >1% of"""
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


def analyser_changements(ancien_texte: str, nouveau_texte: str) -> dict:
    """Résumé des changements, affiché sur l'écran d'impact et figé sur la version."""
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
    """Les unités sous forme JSON-able, tronquées à un budget d'octets."""
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
