"""Campagne réelle des correctifs du 28/09/2026 non encore éprouvés hors tests (Albert, vrais workers, API HTTP).

Enchaîne, sur un domaine TEST remis à plat :

  1. fil paternité : initiale validée (non canonique) + précision « apprentis » canonique + 2 brouillons SUGGESTION
  2. MAJ 25 → 30 j : la générale est retirée, la canonique « apprentis » (exception inchangée) reste servie
     [correctif texte actuel], les brouillons repartent au pipeline [pt 3], citations en v2 [pt 9]
  3. « Corriger » une SUGGESTION jugée OUI : la source en profite [pt 1]
  4. canonique HORS_DOMAINE corrigée à la main, puis MAJ d'un document que rien ne cite qui la contredit :
     détectée par les voisines [pts 5 et 6]
  5. SUGGESTION de cette canonique signalée : l'API HTTP prévient le relecteur [pt 4]
  6. brouillon d'un employé lambda : l'API HTTP ne le lui livre pas, le relecteur le lit [pt 11]
  7. document sans rapport : rien de retiré ; document qui répond : « pas d'information » retirée,
     son brouillon renvoyé [pts 3 et 7]
  8. aperçu d'une MAJ v3 : rapprochement par version des citations [pt 9]

    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/bout_en_bout_verifs.py --validateur <uuid>
"""

import argparse
import asyncio
import hashlib
import os
import uuid
from datetime import datetime, timezone

import httpx
from app.core.security import create_access_token
from app.database import SessionLocal
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.user import User
from scripts.bout_en_bout_suivis import (
    DOMAINE,
    PRECISION,
    Q_PATERNITE,
    TEXTE_V1,
    TEXTE_V2,
    attendre,
    court,
    point_de,
    poser,
    titre,
    valider,
)

API = "http://localhost:8000/api/v1"
Q_PREAVIS = "Quel est le délai de préavis en cas de démission ?"
NOTE_TELETRAVAIL = "Note de service — Télétravail\n\nLe télétravail est autorisé deux jours par semaine.\n"
NOTE_TELETRAVAIL_V2 = NOTE_TELETRAVAIL + "\nLe préavis en cas de démission est de deux mois.\n"
NOTE_MUTUELLE = "Note de service — Mutuelle\n\nLa mutuelle d'entreprise est prise en charge à 60 % par l'employeur.\n"

bilan: list[tuple[str, bool, str]] = []


def verifier(libelle: str, ok: bool, detail: str = "") -> None:
    bilan.append((libelle, ok, detail))
    marque = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    suite = f" — {detail}" if detail else ""
    print(f"  {marque} {libelle}{suite}", flush=True)


def ingerer(db, nom: str, texte: str, validateur: str) -> str:
    from app.workers.ingestion import ingestion_job

    doc_id = str(uuid.uuid4())
    chemin = f"/app/uploads_tmp/{uuid.uuid4()}_{nom}"
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    open(chemin, "w").write(texte)
    ingestion_job.apply_async(kwargs={
        "file_path": chemin, "filename": nom, "domaine": DOMAINE, "description": nom,
        "content_hash": hashlib.sha256(texte.encode()).hexdigest(), "uploaded_by": validateur, "doc_id": doc_id,
    }, queue="queue_ingestion")

    def indexe():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_id).first()
        return d if d and d.nb_chunks else None

    attendre(indexe)
    return doc_id


def mettre_a_jour(db, doc_id: str, nom: str, texte: str, validateur: str) -> None:
    from app.workers.document_update import document_update_job

    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    cible = doc.version + 1
    chemin = f"/app/uploads_tmp/{uuid.uuid4()}_{nom}"
    open(chemin, "w").write(texte)
    doc.statut = "EN_MAJ"
    db.commit()
    document_update_job.apply_async(kwargs={
        "doc_id": doc_id, "new_version": cible, "file_path": chemin, "filename": nom,
        "description": doc.description or "", "content_hash": hashlib.sha256(texte.encode()).hexdigest(),
        "uploaded_by": validateur,
    }, queue="queue_ingestion")

    def publiee():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_id).first()
        return d if d.version == cible and d.statut == "ACTIF" else None

    attendre(publiee)
    attendre_analyses(db)


def attendre_analyses(db) -> None:
    def finies():
        db.expire_all()
        return True if db.query(Reponse).filter(Reponse.a_relire_raison == "ANALYSE_EN_COURS").count() == 0 else None

    attendre(finies, 400, 3)


def attendre_renvoi(db, ticket_id: uuid.UUID, depuis: datetime, suivi: str | None):
    def renvoye():
        db.expire_all()
        q = db.query(Reponse).filter(Reponse.ticket_id == ticket_id, Reponse.created_at > depuis,
                                     Reponse.obsolete.is_(False))
        q = q.filter(Reponse.question_suivi == suivi) if suivi else q.filter(Reponse.question_suivi.is_(None))
        return q.first()

    try:
        return attendre(renvoye, 300, 3)
    except TimeoutError:
        return None


def http_reponses(user: User, ticket_id) -> list[dict]:
    jeton = create_access_token(user.id, user.role)
    r = httpx.get(f"{API}/tickets/{ticket_id}/reponses", headers={"Authorization": f"Bearer {jeton}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def remettre_a_plat(db, admin: User) -> None:
    from app.api.v1.documents.core import delete_document

    titre("0. remise à plat du domaine TEST")
    # old drafts retired first: deleting their document would send ~15 of them back to the pipeline (noise, quota)
    nb = db.query(Reponse).filter(Reponse.statut == "EN_ATTENTE", Reponse.obsolete.is_(False)).update(
        {"obsolete": True, "obsolete_raison": "RETIRÉ_À_LA_MAIN"}, synchronize_session=False)
    db.commit()
    print(f"  {nb} ancien(s) brouillon(s) retiré(s)")
    for d in db.query(Document).filter(Document.domaine == DOMAINE, Document.statut != "SUPPRIMÉ").all():
        asyncio.run(delete_document(d.doc_id, current_user=admin, db=db))
        print(f"  document {d.filename} {d.doc_id[:8]} supprimé")
    restants = db.query(Reponse).filter(Reponse.obsolete.is_(False), Reponse.statut.in_(("VALIDÉE", "CORRIGÉE"))).all()
    for r in restants:  # réponses sans citation (HORS_DOMAINE) : hors de portée de la suppression de document
        r.obsolete, r.obsolete_raison = True, "RETIRÉ_À_LA_MAIN"
        for p in point_de(str(r.id)):
            from app.services.qdrant import COLLECTION_NAME, client
            from qdrant_client.models import PointIdsList

            client.delete(COLLECTION_NAME, points_selector=PointIdsList(points=[p.id]))
    db.commit()
    print(f"  {len(restants)} réponse(s) résiduelle(s) retirée(s)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--validateur", required=True)
    a = p.parse_args()
    db = SessionLocal()
    admin = db.query(User).filter(User.id == uuid.UUID(a.validateur)).first()
    try:
        remettre_a_plat(db, admin)

        # ── 1 ──────────────────────────────────────────────────────────────
        titre("1. fil paternité, précision « apprentis » canonique, 2 brouillons SUGGESTION")
        doc1 = ingerer(db, "guide_rh.txt", TEXTE_V1, a.validateur)
        initiale = poser(db, Q_PATERNITE)
        valider(db, initiale["reponse_id"], a.validateur)
        precision = poser(db, PRECISION, ticket_id=initiale["ticket_id"])
        valider(db, precision["reponse_id"], a.validateur)
        attendre(lambda: point_de(precision["reponse_id"]) or None, 180)
        apprentis = db.query(Reponse).filter(Reponse.id == uuid.UUID(precision["reponse_id"])).first()
        apprentis.nb_validations, apprentis.canonique = 3, True
        db.commit()
        attendre(lambda: point_de(initiale["reponse_id"]) or None, 180)
        brouillons = [poser(db, Q_PATERNITE) for _ in range(2)]
        verifier("brouillons SUGGESTION créés", all(b["branche"] == "SUGGESTION" for b in brouillons))

        # ── 2 ──────────────────────────────────────────────────────────────
        titre("2. MAJ 25 → 30 j")
        t0 = datetime.now(timezone.utc)
        mettre_a_jour(db, doc1, "guide_rh.txt", TEXTE_V2, a.validateur)
        db.expire_all()
        generale = db.query(Reponse).filter(Reponse.id == uuid.UUID(initiale["reponse_id"])).first()
        apprentis = db.query(Reponse).filter(Reponse.id == uuid.UUID(precision["reponse_id"])).first()
        verifier("générale (25 j) retirée", generale.obsolete, f"{generale.obsolete_raison} : "
                 f"{court(generale.analyse_justification, 100)}")
        verifier("canonique « apprentis » (inchangée) toujours servie sans revue",
                 not apprentis.obsolete and not apprentis.a_relire and apprentis.canonique,
                 f"obsolete={apprentis.obsolete} a_relire={apprentis.a_relire_raison}")
        for b in brouillons:
            n = attendre_renvoi(db, uuid.UUID(b["ticket_id"]), t0, None)
            citations = db.query(ReponseChunk).filter(ReponseChunk.reponse_id == n.id).all() if n else []
            vs = sorted({c.version for c in citations})
            verifier(f"brouillon {b['reponse_id'][:8]} renvoyé, réponse v2 citant la v2",
                     n is not None and "30" in (n.contenu or "") and vs == [2],
                     f"{court(n.contenu if n else None, 80)} versions={vs}")
        rejoue = poser(db, PRECISION, ticket_id=poser(db, Q_PATERNITE)["ticket_id"])
        verifier("la précision « apprentis » reçoit encore la CANONIQUE après la MAJ", rejoue["branche"] == "CANONIQUE")

        # ── 3 ──────────────────────────────────────────────────────────────
        titre("3. « Corriger » une SUGGESTION jugée OUI")
        from app.api.v1.reponses.actions import CorrigerRequest, corriger_reponse

        n = attendre_renvoi(db, uuid.UUID(brouillons[0]["ticket_id"]), t0, None)
        valider(db, str(n.id), a.validateur)
        attendre(lambda: point_de(str(n.id)) or None, 180)
        suggestion = poser(db, Q_PATERNITE)
        verifier("SUGGESTION de la réponse validée, juge OUI",
                 suggestion["branche"] == "SUGGESTION" and suggestion["source_id"] == str(n.id)
                 and suggestion["garde"]["verdict"])
        texte = "Le congé de paternité est de 30 jours calendaires, à prendre dans les six mois suivant la naissance."
        asyncio.run(corriger_reponse(suggestion["reponse_id"], CorrigerRequest(contenu_corrige=texte),
                                     current_user=admin))
        db.expire_all()
        source = db.query(Reponse).filter(Reponse.id == n.id).first()
        verifier("correction propagée à la source", source.contenu_corrige == texte)

        # ── 4 ──────────────────────────────────────────────────────────────
        titre("4. canonique HORS_DOMAINE corrigée à la main, MAJ d'un document que rien ne cite")
        doc2 = ingerer(db, "note_teletravail.txt", NOTE_TELETRAVAIL, a.validateur)
        attendre_analyses(db)
        hd = poser(db, Q_PREAVIS)
        verifier("question hors domaine", hd["branche"] == "HORS_DOMAINE")
        asyncio.run(corriger_reponse(hd["reponse_id"], CorrigerRequest(contenu_corrige=(
            "Le préavis en cas de démission est d'un mois.")), current_user=admin))
        hdr = db.query(Reponse).filter(Reponse.id == uuid.UUID(hd["reponse_id"])).first()
        hdr.nb_validations, hdr.canonique = 3, True
        db.commit()
        attendre(lambda: point_de(hd["reponse_id"]) or None, 180)
        cites = db.query(ReponseChunk).filter(ReponseChunk.doc_id == doc2).count()
        verifier("aucune réponse ne cite la note télétravail", cites == 0)
        mettre_a_jour(db, doc2, "note_teletravail.txt", NOTE_TELETRAVAIL_V2, a.validateur)

        def signalee():  # a neighbour is not flagged ANALYSE_EN_COURS: wait for its own verdict
            db.expire_all()
            r = db.query(Reponse).filter(Reponse.id == uuid.UUID(hd["reponse_id"])).first()
            return r if r.a_relire or r.obsolete else None

        try:
            hdr = attendre(signalee, 300, 3)
        except TimeoutError:
            hdr = db.query(Reponse).filter(Reponse.id == uuid.UUID(hd["reponse_id"])).first()
        verifier("canonique CORRIGÉE contredite détectée par les voisines, jamais retirée d'office",
                 hdr.a_relire and not hdr.obsolete,
                 f"{hdr.a_relire_raison} : {court(hdr.analyse_justification, 100)}")

        # ── 5 ──────────────────────────────────────────────────────────────
        titre("5. SUGGESTION d'une source signalée : l'API HTTP prévient le relecteur")
        sug = poser(db, Q_PREAVIS)
        [item] = [r for r in http_reponses(admin, sug["ticket_id"]) if r["id"] == sug["reponse_id"]]
        verifier("SUGGESTION (pas CANONIQUE) d'une source à relire", sug["branche"] == "SUGGESTION")
        verifier("API : source_a_relire + justification", item["source_a_relire"]
                 and bool(item["source_analyse_justification"]),
                 f"{item['source_a_relire_raison']} : {court(item['source_analyse_justification'], 80)}")

        # ── 6 ──────────────────────────────────────────────────────────────
        titre("6. brouillon d'un employé lambda")
        lambda_user = User(email=f"lambda-{uuid.uuid4().hex[:6]}@test.local", role="USER")
        db.add(lambda_user)
        db.commit()
        from app.workers.question import question_job

        job = question_job.apply_async(args=["Quel est le montant de la prime de fin d'année ?", DOMAINE,
                                             str(lambda_user.id)], queue="queue_questions")

        def ticket_lambda():
            db.expire_all()
            from app.models.ticket import Ticket

            t = db.query(Ticket).filter(Ticket.job_id == uuid.UUID(job.id), Ticket.statut_job == "TERMINÉ").first()
            return t

        t = attendre(ticket_lambda)
        vu_employe = http_reponses(lambda_user, t.id)
        vu_relecteur = http_reponses(admin, t.id)
        verifier("l'employé ne reçoit pas le brouillon", all(r["contenu"] is None for r in vu_employe)
                 and vu_employe[0]["statut"] == "EN_ATTENTE")
        verifier("le relecteur le lit", bool(vu_relecteur[0]["contenu"]), court(vu_relecteur[0]["contenu"], 80))

        # ── 7 ──────────────────────────────────────────────────────────────
        titre("7. nouveau document qui répond : « pas d'information » retirée, son brouillon renvoyé")
        brute = poser(db, "Combien de jours de RTT par an ?")
        valider(db, brute["reponse_id"], a.validateur)
        attendre(lambda: point_de(brute["reponse_id"]) or None, 180)
        sug = poser(db, "Combien de jours de RTT par an ?")  # nb_val=1 : SUGGESTION, brouillon en attente
        r7 = db.query(Reponse).filter(Reponse.id == uuid.UUID(brute["reponse_id"])).first()
        r7.nb_validations, r7.canonique = 3, True
        db.commit()
        verifier("HORS_DOMAINE brute canonique avec un brouillon SUGGESTION",
                 brute["branche"] == "HORS_DOMAINE" and sug["branche"] == "SUGGESTION")
        t7 = datetime.now(timezone.utc)
        ingerer(db, "note_mutuelle.txt", NOTE_MUTUELLE, a.validateur)
        attendre_analyses(db)
        db.expire_all()
        verifier("document sans rapport : rien n'est retiré",
                 not db.query(Reponse).filter(Reponse.id == r7.id).first().obsolete)
        ingerer(db, "note_rtt.txt", "Note — Temps de travail\n\nLes salariés bénéficient de 10 jours de RTT par an.\n",
                a.validateur)
        attendre_analyses(db)
        db.expire_all()
        ancien = db.query(Reponse).filter(Reponse.id == uuid.UUID(sug["reponse_id"])).first()
        n7 = attendre_renvoi(db, uuid.UUID(sug["ticket_id"]), t7, None)
        verifier("document qui répond : retirée avec son brouillon, renvoyé au pipeline",
                 db.query(Reponse).filter(Reponse.id == r7.id).first().obsolete and ancien.obsolete and n7 is not None,
                 f"nouveau {n7.source if n7 else '∅'} : {court(n7.contenu if n7 else None, 80)}")

        # ── 8 ──────────────────────────────────────────────────────────────
        titre("8. aperçu d'une MAJ v3 (exception 28 → 35 j) : rapprochement par version")
        from app.services.document_service import stager_et_analyser

        doc = db.query(Document).filter(Document.doc_id == doc1).first()
        v3 = TEXTE_V2.replace("28 jours", "35 jours").encode()
        apercu = stager_et_analyser(db, doc, contents=v3, filename="guide_rh.txt",
                                    content_hash=hashlib.sha256(v3).hexdigest(), description=doc.description,
                                    user_id=admin.id)
        citations = sorted({(c.chunk_index, c.version) for c in db.query(ReponseChunk).filter(
            ReponseChunk.reponse_id == apprentis.id)})
        ids_a_analyser = {i["reponse_id"] for i in apercu["a_analyser"]}
        print(f"  canonique « apprentis » cite {citations} ; prioritaires={apercu['nb_prioritaires']} "
              f"à analyser={apercu['nb_a_analyser']}")
        verifier("une citation v1 n'est pas rapprochée des indices de la v2, mais la réponse reste analysée",
                 str(apprentis.id) in ids_a_analyser
                 and str(apprentis.id) not in {i["reponse_id"] for i in apercu["items"]})
    finally:
        db.close()

    titre("bilan")
    for libelle, ok, _ in bilan:
        print(f"  {'✓' if ok else '✗'} {libelle}")
    print(f"\n  {sum(ok for _, ok, _ in bilan)}/{len(bilan)}")
    return 0 if all(ok for _, ok, _ in bilan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
