"""Fixture de test du cache sémantique, bâtie sur la FAQ réelle du DFE.

Le cache canonique indexe **question → réponse validée** : la FAQ fournit
exactement cette forme, avec des questions et des réponses écrites par des
humains. Elle porte en outre des grappes adverses qu'on n'aurait pas su
inventer (« Ma facture n'est pas réglée » vs « Mes frais de déplacement ne sont
pas remboursés » : même tournure, services destinataires différents).

Tout est écrit sous le domaine `DFE`, isolé du corpus de démo `IT` par le filtre
strict de `search_hybrid`. Identifiants déterministes (uuid5) : le script est
idempotent. `--purger` supprime **tout le domaine `DFE`** — la fixture et ce que
les passes de test en ont dérivé — et non la seule liste d'ids qu'il sait calculer
(voir `purger`).

    PYTHONPATH=. python scripts/seed_faq_dfe.py            # crée / met à jour
    PYTHONPATH=. python scripts/seed_faq_dfe.py --purger   # supprime

⚠️  Consomme des appels Albert (embeddings) : ~2 pour le document, 1 par réponse.
"""

import os
import re
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.document import Document
from app.models.document_upload import DocumentUpload
from app.models.document_version import DocumentVersion
from app.models.groupe import Groupe
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.feedback import feedback_job
from app.workers.ingestion import ingestion_job
from qdrant_client.models import FieldCondition, Filter, MatchValue

NS = uuid.UUID("dfe00000-1111-2222-3333-444444444444")
DOMAINE = "DFE"
DOC_ID = str(uuid.uuid5(NS, "doc-faq-dfe"))
XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DFE_FAQ.xlsx")

# Les 8 clés servies sans revue humaine ; F4/F9/F11 restent validées non canoniques
# pour que la branche SUGGESTION soit exerçable (et qu'on vérifie que le garde
# n'y est pas appelé).
CANONIQUES = {"F1", "F2", "F3", "F5", "F6", "F7", "F8", "F10"}

# Fils de suivi : une question initiale, une réponse, puis les précisions seront
# posées par le harnais. Les questions initiales sont choisies pour que la
# précision attendue tombe sur une *autre* entrée de la FAQ que l'initiale.
FILS = [
    ("fil-engagement", "F1", "Comment fait on un engagement de dépense ?"),
    ("fil-facture", "F5", "Ma facture n'est pas réglée , mon fournisseur me relance. Que dois-je faire ?"),
    ("fil-servicefait", "F2", "Comment fait on un service fait ?"),
]

XLNS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sid(cle: str) -> uuid.UUID:
    return uuid.uuid5(NS, cle)


def now():
    return datetime.now(timezone.utc)


def lire_faq(chemin: str) -> list[dict]:
    """Parse le .xlsx sans dépendance nouvelle : sharedStrings + sheet1 suffisent."""
    z = zipfile.ZipFile(chemin)
    racine = ET.fromstring(z.read("xl/sharedStrings.xml"))
    chaines = ["".join(t.text or "" for t in si.iter(XLNS + "t")) for si in racine.iter(XLNS + "si")]

    feuille = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    entrees = []
    for ligne in feuille.iter(XLNS + "row"):
        num = int(ligne.get("r"))
        if num < 4:  # lignes 1-3 : titre, vide, en-têtes
            continue
        cellules = {}
        for c in ligne.iter(XLNS + "c"):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find(XLNS + "v")
            if v is not None:
                cellules[col] = chaines[int(v.text)] if c.get("t") == "s" else v.text
        question = (cellules.get("C") or "").strip()
        reponse = (cellules.get("D") or "").strip()
        if not question or not reponse:
            continue
        entrees.append(
            {
                "cle": f"F{len(entrees) + 1}",
                "categorie": cellules.get("A") or "",
                "sous_categorie": cellules.get("B") or "",
                "question": question,
                "reponse": reponse,
            }
        )
    return entrees


def construire_document(entrees: list[dict]) -> str:
    """Le corpus RAG de repli, bâti à partir des réponses de la FAQ.

    La FAQ ne vient pas avec ses documents sources : sans ce fichier, toute
    question retombée en RAG n'aurait aucun chunk et le repli serait ininterprétable.
    """
    lignes = ["# FAQ — Département des finances et de l'évaluation (DFE)", ""]
    for e in entrees:
        lignes += [f"## {e['question']}", "", f"*{e['categorie']} — {e['sous_categorie']}*", "", e["reponse"], ""]
    return "\n".join(lignes)


def purger(db) -> None:
    """Supprime la fixture **et tout ce que les passes de test ont produit à partir d'elle**.

    Sélection par prédicat (`domaine == DFE` et objet préfixé `[TEST-CACHE]`), pas
    par liste d'identifiants déterministes. La passe B pousse dans la vraie file
    Celery : elle crée des tickets et des copies SUGGESTION aux UUID *aléatoires*,
    que le script n'a aucun moyen d'énumérer. Ces copies portent un
    `reponse_source_id` vers les réponses de la fixture — les supprimer par id
    laissait donc la purge échouer sur `reponses_reponse_source_id_fkey`, et la
    fixture n'était pas re-semable après une passe B.

    Les copies sont supprimées avant leurs sources, sans quoi la même FK bloque.

    Même raisonnement côté Qdrant, et c'est le pendant exact de
    `delete_response_point` : suppression par **filtre de payload** sur le domaine,
    pas par liste d'ids. Une réponse porte un point par formulation validée, dont
    les ids dérivent de copies inconnues du script.
    """
    ids_tickets = [
        t[0]
        for t in db.query(Ticket.id)
        .filter(Ticket.domaine == DOMAINE, Ticket.objet.like("[TEST-CACHE]%"))
        .all()
    ]

    ids_reponses = [
        r[0] for r in db.query(Reponse.id).filter(Reponse.ticket_id.in_(ids_tickets)).all()
    ]
    # Les copies vivent sur les tickets de la passe B, donc déjà dans `ids_reponses` ;
    # on les rajoute quand même, une copie ayant pu naître ailleurs.
    ids_reponses += [
        r[0]
        for r in db.query(Reponse.id).filter(Reponse.reponse_source_id.in_(ids_reponses)).all()
        if r[0] not in ids_reponses
    ]

    # Dépendants d'abord — `reponse_chunks` (traçabilité des réponses RAG de la
    # passe B) et `notifications`, puis les copies avant leurs sources.
    db.query(ReponseChunk).filter(ReponseChunk.reponse_id.in_(ids_reponses)).delete(
        synchronize_session=False
    )
    db.query(Notification).filter(Notification.ticket_id.in_(ids_tickets)).delete(
        synchronize_session=False
    )
    db.query(TicketEvent).filter(TicketEvent.ticket_id.in_(ids_tickets)).delete(
        synchronize_session=False
    )
    nb_copies = (
        db.query(Reponse)
        .filter(Reponse.reponse_source_id.in_(ids_reponses))
        .delete(synchronize_session=False)
    )
    nb_reponses = (
        db.query(Reponse).filter(Reponse.id.in_(ids_reponses)).delete(synchronize_session=False)
    )
    db.query(Ticket).filter(Ticket.id.in_(ids_tickets)).delete(synchronize_session=False)
    db.query(DocumentUpload).filter(DocumentUpload.doc_id == DOC_ID).delete(synchronize_session=False)
    db.query(DocumentVersion).filter(DocumentVersion.doc_id == DOC_ID).delete(synchronize_session=False)
    db.query(Document).filter(Document.doc_id == DOC_ID).delete(synchronize_session=False)
    db.commit()

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="domaine", match=MatchValue(value=DOMAINE))]
        ),
        wait=True,
    )
    print(
        f"🧹 Purge : {len(ids_tickets)} tickets, {nb_reponses} réponses "
        f"(+{nb_copies} copies issues des passes), tous les points Qdrant du domaine {DOMAINE}"
    )


def semer(db, entrees: list[dict]) -> None:
    if not db.query(Groupe).filter(Groupe.domaine == DOMAINE).first():
        db.add(Groupe(id=sid("groupe"), nom="Finances et évaluation", domaine=DOMAINE))
        db.commit()
        print(f"✅ Groupe créé : Finances et évaluation / {DOMAINE}")

    # ── Document RAG de repli ────────────────────────────────────────────────
    tmp = "/tmp/faq_dfe.md"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(construire_document(entrees))
    res = ingestion_job.apply(
        kwargs={
            "file_path": tmp,
            "filename": "faq_dfe.md",
            "domaine": DOMAINE,
            "description": "FAQ DFE — corpus de repli pour le test du cache sémantique",
            "content_hash": "test-cache-faq-dfe",
            "uploaded_by": None,
            "doc_id": DOC_ID,
        }
    ).get()
    print(f"✅ Document ingéré : {res['nb_chunks']} chunks (doc_id={DOC_ID})")

    # ── Une réponse validée par entrée de la FAQ ─────────────────────────────
    base = now() - timedelta(days=30)
    for i, e in enumerate(entrees):
        cle = e["cle"]
        canonique = cle in CANONIQUES
        tid, rid = sid(f"t-{cle}"), sid(f"r-{cle}")

        t = db.get(Ticket, tid) or Ticket(id=tid)
        t.question, t.domaine = e["question"], DOMAINE
        t.objet = f"[TEST-CACHE] {e['sous_categorie']}"
        t.job_id = sid(f"j-{cle}")
        t.statut_job, t.statut_ticket = "TERMINÉ", "VALIDÉ"
        t.canonique = canonique
        t.created_at = base + timedelta(hours=i)
        t.processed_at = t.validated_at = t.created_at
        db.merge(t)

        r = db.get(Reponse, rid) or Reponse(id=rid)
        r.ticket_id, r.contenu, r.source = tid, e["reponse"], "LLM"
        r.statut = "VALIDÉE"
        r.nb_validations = 3 if canonique else 1
        r.canonique = canonique
        r.obsolete, r.a_relire = False, False
        r.score_similarite = 0.95
        r.created_at = r.validated_at = t.created_at
        db.merge(r)
    db.commit()

    for e in entrees:
        feedback_job.apply(args=[str(sid(f"r-{e['cle']}"))]).get()
    print(f"✅ {len(entrees)} réponses indexées ({len(CANONIQUES)} canoniques)")

    # ── Fils de suivi, pour rendre charger_contexte_fil exerçable ────────────
    par_cle = {e["cle"]: e for e in entrees}
    for j, (cle_fil, cle_faq, question) in enumerate(FILS):
        tid = sid(f"t-suivi-{cle_fil}")
        t = db.get(Ticket, tid) or Ticket(id=tid)
        t.question, t.domaine = question, DOMAINE
        t.objet = f"[TEST-CACHE] fil {cle_fil}"
        t.job_id = sid(f"j-suivi-{cle_fil}")
        t.statut_job, t.statut_ticket = "TERMINÉ", "RÉPONDU"
        t.created_at = t.processed_at = base + timedelta(days=5, hours=j)
        db.merge(t)

        # EN_ATTENTE et jamais passée par feedback_job : le fil sert de contexte,
        # il ne doit pas devenir lui-même un candidat du cache.
        r = db.get(Reponse, sid(f"r-init-{cle_fil}")) or Reponse(id=sid(f"r-init-{cle_fil}"))
        r.ticket_id, r.contenu = tid, par_cle[cle_faq]["reponse"]
        r.source, r.statut = "LLM", "EN_ATTENTE"
        r.question_suivi = None
        r.created_at = t.created_at
        db.merge(r)
    db.commit()
    print(f"✅ {len(FILS)} fils de suivi créés")


def main() -> None:
    entrees = lire_faq(XLSX)
    print(f"📖 FAQ lue : {len(entrees)} entrées")
    for e in entrees:
        marque = "CANON" if e["cle"] in CANONIQUES else "  val"
        print(f"   {e['cle']:>3} [{marque}] {e['question'][:78]}")

    db = SessionLocal()
    try:
        if "--purger" in sys.argv:
            purger(db)
        else:
            semer(db, entrees)
    finally:
        db.close()


if __name__ == "__main__":
    main()
