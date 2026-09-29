"""Campagne réelle du 29/09/2026 : candidats jugés après un refus (point 10), HORS_DOMAINE en confrontation (point 7).

    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/bout_en_bout_candidats_hd.py --phase mise_en_place|sonde|candidats|hd --validateur <uuid>

  mise_en_place  domaine TEST remis à plat, guide RH v1, générale ET précision « apprentis » canoniques
  sonde          classement des candidats (sans juge) sur plusieurs formulations — pour trouver les cas utiles
  candidats      3 passes par formulation : branche, réponse servie, nombre de jugements
  hd             deux canoniques HORS_DOMAINE (brute et corrigée), un document sans rapport puis un qui répond
"""

import argparse
import asyncio
import json
import uuid

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.user import User
from scripts.bout_en_bout_suivis import (
    PRECISION,
    Q_PATERNITE,
    TEXTE_V1,
    attendre,
    court,
    ecrire_etat,
    lire_etat,
    point_de,
    poser,
    titre,
    valider,
)
from scripts.bout_en_bout_verifs import attendre_analyses, ingerer, remettre_a_plat

FORMULATIONS = [
    "Combien de jours de congé de paternité ?",
    "Quelle est la durée du congé de paternité ?",
    "Combien de jours de congé de paternité pour un salarié ?",
    "Combien de jours de congé de paternité pour un salarié qui n'est pas apprenti ?",
    "Un apprenti a droit à combien de jours de congé de paternité ?",
    "Congé de paternité d'un apprenti : combien de jours ?",
    "Combien de jours de congé de paternité pour un salarié à temps partiel ?",
]


def mise_en_place(db, admin: User, validateur: str) -> None:
    remettre_a_plat(db, admin)
    titre("guide RH v1, générale et précision « apprentis » canoniques")
    ingerer(db, "guide_rh.txt", TEXTE_V1, validateur)
    initiale = poser(db, Q_PATERNITE)
    valider(db, initiale["reponse_id"], validateur)
    precision = poser(db, PRECISION, ticket_id=initiale["ticket_id"])
    valider(db, precision["reponse_id"], validateur)
    for rid in (initiale["reponse_id"], precision["reponse_id"]):
        attendre(lambda rid=rid: point_de(rid) or None, 180)
        r = db.query(Reponse).filter(Reponse.id == uuid.UUID(rid)).first()
        r.nb_validations, r.canonique = 3, True
    db.commit()
    ecrire_etat(generale=initiale["reponse_id"], apprentis=precision["reponse_id"])


def sonde(db) -> None:
    from app.config import settings
    from app.services.question_pipeline import trouver_candidats
    from app.services.search import search_hybrid

    etat = lire_etat()
    noms = {etat["generale"]: "GÉNÉRALE", etat["apprentis"]: "APPRENTIS"}
    for f in FORMULATIONS:
        candidats = trouver_candidats(db, search_hybrid(f, "TEST", top_k=15), limite=3)
        ordre = ", ".join(f"{noms.get(str(c.reponse.id), '?')} cos={c.score_cosinus:.3f}" for c in candidats)
        print(f"  « {f} »\n      → {ordre or 'aucun candidat'}")
    print(f"  (portes : cos ≥ {settings.seuil_cosinus - 0.05:.2f} ou lexical ≥ {settings.seuil_lexical_par_terme})")


def candidats(db, passes: int) -> None:
    etat = lire_etat()
    noms = {etat["generale"]: "GÉNÉRALE", etat["apprentis"]: "APPRENTIS"}
    bilan = {}
    for f in FORMULATIONS:
        titre(f)
        res = [poser(db, f) for _ in range(passes)]
        bilan[f] = [(r["branche"], noms.get(r["source_id"] or "", "—"), r["nb_jugements"]) for r in res]
    titre("bilan (branche, réponse servie, nombre de jugements)")
    for f, lignes in bilan.items():
        print(f"  « {f} »\n      {lignes}")
    ecrire_etat(bilan_candidats=bilan)


def hd(db, admin: User, validateur: str) -> None:
    from app.api.v1.reponses.actions import CorrigerRequest, corriger_reponse

    titre("deux canoniques HORS_DOMAINE : brute (RTT) et corrigée à la main (préavis)")
    brute = poser(db, "Combien de jours de RTT par an ?")
    corrigee = poser(db, "Quel est le délai de préavis en cas de démission ?")
    valider(db, brute["reponse_id"], validateur)
    asyncio.run(corriger_reponse(corrigee["reponse_id"], CorrigerRequest(
        contenu_corrige="Le préavis en cas de démission est d'un mois."), current_user=admin))
    for x in (brute, corrigee):
        attendre(lambda x=x: point_de(x["reponse_id"]) or None, 180)
        r = db.query(Reponse).filter(Reponse.id == uuid.UUID(x["reponse_id"])).first()
        r.nb_validations, r.canonique = 3, True
    db.commit()
    print(f"  branches : {brute['branche']} / {corrigee['branche']}")

    def etat(tag: str) -> dict:
        db.expire_all()
        sortie = {}
        for nom, x in (("brute", brute), ("corrigee", corrigee)):
            r = db.query(Reponse).filter(Reponse.id == uuid.UUID(x["reponse_id"])).first()
            sortie[nom] = {"obsolete": r.obsolete, "a_relire": r.a_relire_raison if r.a_relire else None,
                           "justification": court(r.analyse_justification, 110)}
            print(f"  [{tag}] {nom:<9} obsolete={r.obsolete!s:<5} a_relire={sortie[nom]['a_relire']}"
                  f"  {sortie[nom]['justification']}")
        return sortie

    titre("document sans rapport (mutuelle) : les deux doivent survivre")
    ingerer(db, "note_mutuelle.txt", "Note de service — Mutuelle\n\nLa mutuelle d'entreprise est prise en charge "
            "à 60 % par l'employeur.\n", validateur)
    attendre_analyses(db)
    apres_mutuelle = etat("mutuelle")

    titre("document qui répond (RTT 10 j, préavis deux mois)")
    ingerer(db, "note_rtt_preavis.txt", "Note de service — Temps de travail\n\nLes salariés bénéficient de 10 "
            "jours de RTT par an.\n\nLe préavis en cas de démission est de deux mois.\n", validateur)
    attendre_analyses(db)
    apres_reponse = etat("rtt+préavis")
    ecrire_etat(hd={"mutuelle": apres_mutuelle, "rtt_preavis": apres_reponse})
    print(json.dumps({"attendu": "mutuelle: aucun retrait ; rtt+préavis: brute retirée, corrigée à relire"},
                     ensure_ascii=False))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", required=True, choices=["mise_en_place", "sonde", "candidats", "hd"])
    p.add_argument("--validateur", required=True)
    p.add_argument("--passes", type=int, default=3)
    a = p.parse_args()
    db = SessionLocal()
    admin = db.query(User).filter(User.id == uuid.UUID(a.validateur)).first()
    try:
        if a.phase == "mise_en_place":
            mise_en_place(db, admin, a.validateur)
        elif a.phase == "sonde":
            sonde(db)
        elif a.phase == "candidats":
            candidats(db, a.passes)
        elif a.phase == "hd":
            hd(db, admin, a.validateur)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
