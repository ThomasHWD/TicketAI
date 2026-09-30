"""Bout en bout des correctifs du 28/09/2026, en conditions réelles (Albert, vrais workers, vraies files).

Un document, deux sujets portant chacun une exception « apprentis » : le congé de paternité et la prime de fin
d'année. C'est la forme exacte du danger — deux fils finissant par « et pour un apprenti ? » qui n'appellent pas la
même réponse.

Phases (rejouables séparément, état dans /tmp/bout_en_bout_suivis.json) :

  mise_en_place  ingestion, fil A (question + précision), validations, précision portée canonique
  rappel         3 fils identiques au fil A : la précision reçoit-elle la CANONIQUE ?
  danger         3 fils « prime de fin d'année » + « et pour un apprenti ? » : jamais la réponse paternité
  autonome       3 questions neuves « … pour un apprenti ? » d'emblée
  herite         point réécrit sous la précision nue : ce que le juge en aurait fait, neutralisation, reprise
  maj            mise à jour du document (règle générale 25 → 30 j) : brouillons renvoyés, versions de citation

À lancer dans le conteneur :
    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/bout_en_bout_suivis.py --phase mise_en_place --validateur <uuid>
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.document import Document
from app.models.garde_decision import GardeDecision
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.user import User
from app.services.qdrant import COLLECTION_NAME, client

ETAT = "/tmp/bout_en_bout_suivis.json"
DOMAINE = "TEST"

TEXTE_V1 = """Guide RH 2026 — Congés et primes

Le congé de paternité et d'accueil de l'enfant est de 25 jours calendaires.

Les apprentis bénéficient d'un congé de paternité de 28 jours calendaires, dont 3 jours pris en charge par le CFA.

La prime de fin d'année est de 800 euros bruts, versée en décembre.

Pour les apprentis, la prime de fin d'année est de 400 euros bruts.
"""
TEXTE_V2 = TEXTE_V1.replace("est de 25 jours calendaires", "est de 30 jours calendaires")

Q_PATERNITE = "Combien de jours de congé de paternité ?"
Q_PRIME = "Quel est le montant de la prime de fin d'année ?"
PRECISION = "et pour un apprenti ?"
PRECISION_PARTIEL = "et pour un salarié à temps partiel ?"
Q_AUTONOME = "Combien de jours de congé de paternité pour un apprenti ?"


# ── utilitaires ─────────────────────────────────────────────────────────


def lire_etat() -> dict:
    return json.load(open(ETAT)) if os.path.exists(ETAT) else {}


def ecrire_etat(**champs) -> dict:
    etat = {**lire_etat(), **champs}
    json.dump(etat, open(ETAT, "w"), indent=2, ensure_ascii=False)
    return etat


def titre(t: str) -> None:
    print(f"\n\033[1m── {t} {'─' * max(0, 70 - len(t))}\033[0m", flush=True)


def court(t: str | None, n: int = 160) -> str:
    plat = " ".join((t or "").split())
    return plat if len(plat) <= n else plat[:n] + "…"


def attendre(predicat, delai: int = 300, pas: float = 2):
    debut = time.time()
    while time.time() - debut < delai:
        v = predicat()
        if v is not None:
            return v
        time.sleep(pas)
    raise TimeoutError(f"rien après {delai} s")


def poser(db, texte: str, ticket_id: str | None = None) -> dict:
    """Soumet au vrai worker et attend la réponse. Rend branche, contenu, décision du garde."""
    from app.workers.question import question_job

    t0 = datetime.now(timezone.utc)
    kwargs = {"ticket_id": ticket_id} if ticket_id else {}
    job = question_job.apply_async(args=[texte, DOMAINE, None], kwargs=kwargs, queue="queue_questions")
    job_id = uuid.UUID(job.id)

    def abouti():
        db.expire_all()
        if ticket_id:
            return (
                db.query(Reponse)
                .filter(Reponse.ticket_id == uuid.UUID(ticket_id), Reponse.question_suivi == texte,
                        Reponse.created_at >= t0)
                .first()
            )
        t = db.query(Ticket).filter(Ticket.job_id == job_id).first()
        if t is None or t.statut_job not in ("TERMINÉ", "ÉCHOUÉ"):
            return None
        return db.query(Reponse).filter(Reponse.ticket_id == t.id).order_by(Reponse.created_at.desc()).first()

    r = attendre(abouti)
    jugements = db.query(GardeDecision).filter(GardeDecision.job_id == job_id).order_by(GardeDecision.created_at).all()
    g = jugements[-1] if jugements else None
    resultat = {
        "question": texte,
        "ticket_id": str(r.ticket_id),
        "reponse_id": str(r.id),
        "branche": r.source,
        "source_id": str(r.reponse_source_id) if r.reponse_source_id else None,
        "contenu": r.contenu,
        "nb_jugements": len(jugements),
        "garde": None
        if g is None
        else {
            "question_indexee": g.question_indexee,
            "verdict": g.verdict,
            "court_circuit": g.court_circuit,
            "erreur": g.erreur,
            "cos": g.score_cosinus,
            "lex": g.score_lexical,
        },
    }
    garde = resultat["garde"]
    juge = "juge non appelé" if garde is None else (
        f"juge {'OUI' if garde['verdict'] else 'NON'}{' (court-circuit)' if garde['court_circuit'] else ''}"
        f"{' ERREUR ' + garde['erreur'] if garde['erreur'] else ''} vs « {court(garde['question_indexee'], 70)} »"
        f" cos={garde['cos'] if garde['cos'] is None else round(garde['cos'], 4)}"
        f" lex={garde['lex'] if garde['lex'] is None else round(garde['lex'], 2)}"
    )
    print(f"  « {texte} » → \033[1m{r.source}\033[0m — {juge}\n      {court(r.contenu)}", flush=True)
    return resultat


def valider(db, reponse_id: str, validateur: str) -> None:
    from app.api.v1.reponses.actions import valider_reponse

    user = db.query(User).filter(User.id == uuid.UUID(validateur)).first()
    asyncio.run(valider_reponse(reponse_id, current_user=user))


def point_de(rid: str):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    filtre = Filter(must=[FieldCondition(key="reponse_id", match=MatchValue(value=rid))])
    lot, _ = client.scroll(COLLECTION_NAME, scroll_filter=filtre, limit=10, with_payload=True)
    return lot


# ── phases ──────────────────────────────────────────────────────────────


def mise_en_place(db, validateur: str) -> None:
    from app.services.reformulation import question_autonome
    from app.workers.feedback import fil_jusqua
    from app.workers.ingestion import ingestion_job

    titre("ingestion du guide RH v1")
    doc_id = str(uuid.uuid4())
    chemin = f"/app/uploads_tmp/{uuid.uuid4()}_guide_rh.txt"
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    open(chemin, "w").write(TEXTE_V1)
    ingestion_job.apply_async(kwargs={
        "file_path": chemin, "filename": "guide_rh.txt", "domaine": DOMAINE, "description": "Guide RH congés et primes",
        "content_hash": hashlib.sha256(TEXTE_V1.encode()).hexdigest(), "uploaded_by": validateur, "doc_id": doc_id,
    }, queue="queue_ingestion")

    def indexe():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_id).first()
        return d if d and d.nb_chunks else None

    doc = attendre(indexe)
    print(f"  doc {doc_id} v{doc.version} — {doc.nb_chunks} chunk(s)")

    titre("fil A : question initiale puis précision")
    initiale = poser(db, Q_PATERNITE)
    valider(db, initiale["reponse_id"], validateur)
    precision = poser(db, PRECISION, ticket_id=initiale["ticket_id"])

    titre("validation de la précision → reformulation réelle à l'indexation")
    valider(db, precision["reponse_id"], validateur)

    def reformulee():
        db.expire_all()
        r = db.query(Reponse).filter(Reponse.id == uuid.UUID(precision["reponse_id"])).first()
        pts = point_de(precision["reponse_id"])
        return (r, pts) if r.question_autonome and pts else None

    r, pts = attendre(reformulee, 180)
    print(f"  question_autonome stockée : « {r.question_autonome} »")
    for p in pts:
        print(f"  point Qdrant {p.id} indexé sous « {p.payload.get('question_indexee')} »")

    titre("stabilité de la reformulation — 3 appels sur le même fil")
    fil = fil_jusqua(db, r, db.query(Ticket).filter(Ticket.id == r.ticket_id).first())
    print(f"  fil : {fil}")
    for n in range(3):
        print(f"  passe {n + 1} : « {question_autonome(fil)} »")

    titre("précision portée canonique (raccourci : 3 validations mesurées le 18/09, pas rejouées)")
    r.nb_validations, r.canonique = 3, True
    db.commit()

    chunks = db.query(ReponseChunk).filter(ReponseChunk.reponse_id.in_(
        [uuid.UUID(initiale["reponse_id"]), uuid.UUID(precision["reponse_id"])])).all()
    print(f"  versions des citations : {sorted({(c.chunk_index, c.version) for c in chunks})}")

    ecrire_etat(doc_id=doc_id, initiale=initiale, precision=precision, question_autonome=r.question_autonome,
                versions_citations_v1=sorted({c.version for c in chunks if c.version is not None}))


def fils(db, question: str, passes: int, cle: str, precision: str = PRECISION) -> None:
    resultats = []
    for n in range(passes):
        titre(f"{cle} — passe {n + 1}/{passes}")
        ouverture = poser(db, question)
        suivi = poser(db, precision, ticket_id=ouverture["ticket_id"])
        resultats.append({"ouverture": ouverture, "suivi": suivi})
    ecrire_etat(**{cle: resultats})
    titre(f"bilan {cle}")
    for n, res in enumerate(resultats, 1):
        s = res["suivi"]
        print(f"  passe {n} : précision → {s['branche']:<12} {court(s['contenu'], 110)}")


def autonome(db, passes: int) -> None:
    resultats = []
    for n in range(passes):
        titre(f"autonome — passe {n + 1}/{passes}")
        resultats.append(poser(db, Q_AUTONOME))
    ecrire_etat(autonome=resultats)


def herite(db) -> None:
    from app.services.embedding import embed_texts
    from app.services.garde_cache import statuer
    from qdrant_client.models import PointStruct, SparseVector

    etat = lire_etat()
    rid = etat["precision"]["reponse_id"]
    r = db.query(Reponse).filter(Reponse.id == uuid.UUID(rid)).first()
    [ancien] = [p for p in point_de(rid) if str(p.id) == str(uuid.uuid5(uuid.NAMESPACE_DNS, rid))]

    titre("réécriture du point sous la précision nue (état d'avant le correctif)")
    emb = embed_texts([PRECISION])[0]
    client.upsert(COLLECTION_NAME, points=[PointStruct(
        id=ancien.id,
        vector={"dense": emb["dense"], "sparse": SparseVector(**emb["sparse"])},
        payload={**ancien.payload, "question_indexee": PRECISION},
    )])
    r.question_autonome = None
    db.commit()
    print(f"  point {ancien.id} → « {PRECISION} », question_autonome effacée")

    titre("ce que le juge aurait fait avant le correctif — fil « prime » vs précision nue, 3 appels")
    fil_prime = f"{Q_PRIME}\n{PRECISION}"
    verdicts = [statuer(fil_prime, PRECISION, est_suivi=True).verdict for _ in range(3)]
    print(f"  verdicts : {['OUI' if v else 'NON' for v in verdicts]}")

    titre("même fil servi aujourd'hui, point hérité en place")
    ouverture = poser(db, Q_PRIME)
    suivi = poser(db, PRECISION, ticket_id=ouverture["ticket_id"])

    titre("reprise : scripts/reindexer_suivis.py --appliquer")
    sortie = subprocess.run([sys.executable, "scripts/reindexer_suivis.py", "--appliquer"],
                            capture_output=True, text=True, env={**os.environ})
    print("  " + "\n  ".join((sortie.stdout + sortie.stderr).strip().splitlines()[-6:]))
    db.expire_all()
    r = db.query(Reponse).filter(Reponse.id == uuid.UUID(rid)).first()
    apres = [p.payload.get("question_indexee") for p in point_de(rid)]
    print(f"  après reprise : question_autonome=« {r.question_autonome} », points={apres}")
    ecrire_etat(herite={"verdicts_avant_correctif": verdicts, "suivi_aujourdhui": suivi,
                        "apres_reprise": {"question_autonome": r.question_autonome, "points": apres}})


def maj(db, validateur: str) -> None:
    from app.workers.document_update import document_update_job

    etat = lire_etat()
    doc_id = etat["doc_id"]
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()

    titre("avant la mise à jour : brouillons SUGGESTION en attente")
    en_attente = db.query(Reponse).filter(Reponse.statut == "EN_ATTENTE", Reponse.source == "SUGGESTION",
                                          Reponse.obsolete.is_(False)).all()
    for r in en_attente:
        print(f"  {r.id} ticket={r.ticket_id} source={r.reponse_source_id} suivi={r.question_suivi!r}")
    tickets_suivis = {str(r.ticket_id): r.question_suivi for r in en_attente}

    titre("mise à jour v1 → v2 : « 25 jours » devient « 30 jours »")
    chemin = f"/app/uploads_tmp/{uuid.uuid4()}_guide_rh.txt"
    open(chemin, "w").write(TEXTE_V2)
    t0 = datetime.now(timezone.utc)
    doc.statut = "EN_MAJ"
    db.commit()
    document_update_job.apply_async(kwargs={
        "doc_id": doc_id, "new_version": doc.version + 1, "file_path": chemin, "filename": "guide_rh.txt",
        "description": doc.description or "", "content_hash": hashlib.sha256(TEXTE_V2.encode()).hexdigest(),
        "uploaded_by": validateur,
    }, queue="queue_ingestion")

    def publiee():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_id).first()
        return d if d.version == 2 and d.statut == "ACTIF" else None

    attendre(publiee)

    def analysee():
        db.expire_all()
        restes = db.query(Reponse).filter(Reponse.a_relire_raison == "ANALYSE_EN_COURS").count()
        return True if restes == 0 else None

    attendre(analysee, 400, 3)
    print("  v2 publiée, analyse terminée")

    titre("verdicts")
    for r in db.query(Reponse).filter(Reponse.statut.in_(("VALIDÉE", "CORRIGÉE")),
                                      Reponse.reponse_source_id.is_(None)).all():
        print(f"  {r.id} suivi={r.question_suivi!r} obsolete={r.obsolete} ({r.obsolete_raison}) "
              f"a_relire={r.a_relire} ({r.a_relire_raison})\n      justification : {court(r.analyse_justification)}")

    titre("brouillons en attente : retirés puis renvoyés au pipeline ?")
    for r in en_attente:
        db.refresh(r)
    # only drafts whose source was withdrawn are expected back — the others stay in the queue, untouched
    tickets_suivis = {str(r.ticket_id): r.question_suivi for r in en_attente if r.obsolete}
    print(f"  {len(tickets_suivis)}/{len(en_attente)} brouillon(s) retiré(s) avec leur source")

    def renvoyes():
        db.expire_all()
        nouveaux = {}
        for tid, suivi in tickets_suivis.items():
            q = db.query(Reponse).filter(Reponse.ticket_id == uuid.UUID(tid), Reponse.created_at > t0,
                                         Reponse.obsolete.is_(False))
            q = q.filter(Reponse.question_suivi == suivi) if suivi else q.filter(Reponse.question_suivi.is_(None))
            n = q.first()
            if n is None:
                return None
            nouveaux[tid] = n
        return nouveaux

    try:
        nouveaux = attendre(renvoyes, 400, 3)
    except TimeoutError:
        nouveaux = {}
        print("  \033[31maucun renvoi observé\033[0m")
    for r in en_attente:
        db.refresh(r)
        n = nouveaux.get(str(r.ticket_id))
        print(f"  ancien {str(r.id)[:8]} obsolete={r.obsolete} ({r.obsolete_raison})"
              f" → nouveau {n.source if n else '∅'} : {court(n.contenu if n else None, 110)}")
        if n:
            vs = sorted({c.version for c in db.query(ReponseChunk).filter(ReponseChunk.reponse_id == n.id).all()},
                        key=str)
            print(f"      versions citées par la nouvelle réponse : {vs}")

    titre("versions des citations de la réponse initiale du fil A (écrites en v1)")
    vs = {(c.chunk_index, c.version) for c in db.query(ReponseChunk).filter(
        ReponseChunk.reponse_id == uuid.UUID(etat["initiale"]["reponse_id"])).all()}
    print(f"  {sorted(vs)}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", required=True,
                   choices=["mise_en_place", "rappel", "danger", "partiel", "autonome", "herite", "maj"])
    p.add_argument("--validateur")
    p.add_argument("--passes", type=int, default=3)
    a = p.parse_args()
    db = SessionLocal()
    try:
        if a.phase == "mise_en_place":
            mise_en_place(db, a.validateur)
        elif a.phase == "rappel":
            fils(db, Q_PATERNITE, a.passes, "rappel")
        elif a.phase == "danger":
            fils(db, Q_PRIME, a.passes, "danger")
        elif a.phase == "partiel":
            # générale portée canonique : une précision sans réponse spécifique ne doit pas la recevoir sans revue
            r = db.query(Reponse).filter(Reponse.id == uuid.UUID(lire_etat()["initiale"]["reponse_id"])).first()
            r.nb_validations, r.canonique = 3, True
            db.commit()
            fils(db, Q_PATERNITE, a.passes, "partiel", PRECISION_PARTIEL)
        elif a.phase == "autonome":
            autonome(db, a.passes)
        elif a.phase == "herite":
            herite(db)
        elif a.phase == "maj":
            maj(db, a.validateur)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
