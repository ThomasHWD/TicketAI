"""Bout en bout du scénario « règle générale vs exception », sur la stack de dev.

Le scénario est celui du plan : doc A « Le télétravail est autorisé du lundi au
mercredi », une réponse portée jusqu'à canonique, puis doc B « Les alternants
n'ont pas de télétravail » — qui n'existait pas quand la réponse a été générée.

Deux propriétés à vérifier, une par partie livrée :

- **partie B (confrontation)** : l'arrivée de B fait passer la canonique en
  ``a_relire`` / ``CONTREDITE_PROBABLE``, sans jamais la retirer du service
  (``obsolete is False``, point Qdrant toujours là) ;
- **partie A (contextualisation + lex specialis)** : le chunk de B remonte dans
  le top-5 reranké et la réponse générée énonce l'exception au lieu de la règle
  générale.

⚠️ **À lancer depuis le conteneur backend**, jamais depuis l'hôte : celui-ci
porte la configuration de *production* (5432/6333/6379) là où la stack de dev
écoute ailleurs, et pointer au mauvais endroit ne échoue pas — ça réussit
silencieusement contre les mauvaises données.

    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/bout_en_bout_teletravail.py --etape etat

Les étapes sont **séparées et rejouables**, et le travail passe par les vrais
workers (``apply_async`` + attente en base) plutôt que par un appel direct : ce
qu'on veut éprouver inclut le routage des files et l'enfilement de
``confrontation_job``, que l'exécution en process masquerait.

    --etape etat
    --etape ingerer   --fichier A|B
    --etape question  --texte "…"
    --etape valider   --reponse <id|dernier> --validateur <uuid>
    --etape verdict
    --etape sonde     --texte "…" [--passes 3]
    --etape payloads

L'état (doc_id, ids de tickets et de réponses) est repris d'une étape à l'autre
dans /tmp/bout_en_bout_teletravail.json.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import uuid

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.models.groupe import Groupe
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.user import User
from app.services.qdrant import COLLECTION_NAME, client

ETAT = "/tmp/bout_en_bout_teletravail.json"

# Les deux documents du plan, mot pour mot pour la règle et pour l'exception.
# L'en-tête sert seulement à ce que le synopsis ait de quoi situer le texte.
DOCUMENTS = {
    "A": (
        "note_teletravail_2026.txt",
        "Note de service NS-2026-03 — Télétravail\n"
        "\n"
        "Le télétravail est autorisé du lundi au mercredi.\n",
        "Note de service sur le télétravail",
    ),
    "B": (
        "note_alternants_2026.txt",
        "Note de service NS-2026-14 — Alternants\n"
        "\n"
        "Les alternants n'ont pas de télétravail.\n",
        "Note de service sur les alternants",
    ),
}


def lire_etat() -> dict:
    if not os.path.exists(ETAT):
        return {}
    with open(ETAT) as f:
        return json.load(f)


def ecrire_etat(**champs) -> dict:
    etat = lire_etat()
    etat.update(champs)
    with open(ETAT, "w") as f:
        json.dump(etat, f, indent=2)
    return etat


def titre(texte: str) -> None:
    print(f"\n\033[1m── {texte} {'─' * max(0, 68 - len(texte))}\033[0m")


def extrait(texte: str | None, n: int = 300) -> str:
    if not texte:
        return "∅"
    plat = " ".join(texte.split())
    return plat if len(plat) <= n else plat[:n] + "…"


def attendre(predicat, delai: int, quoi: str):
    """Sonde ``predicat`` jusqu'à ce qu'il rende autre chose que None."""
    debut = time.time()
    while time.time() - debut < delai:
        valeur = predicat()
        if valeur is not None:
            print(f"  {quoi} : abouti en {time.time() - debut:.0f} s")
            return valeur
        print(f"  {quoi} : {time.time() - debut:.0f} s…", end="\r", flush=True)
        time.sleep(2)
    print(f"  {quoi} : \033[31mtoujours rien après {delai} s\033[0m")
    return None


# ── étape « etat » ──────────────────────────────────────────────────────


def points_qdrant() -> tuple[list, list]:
    """(chunks de documents, points-réponses) — la collection entière."""
    tous, offset = [], None
    while True:
        lot, offset = client.scroll(COLLECTION_NAME, limit=200, offset=offset, with_payload=True)
        tous += lot
        if offset is None:
            break
    chunks = [p for p in tous if not (p.payload or {}).get("reponse_id")]
    reponses = [p for p in tous if (p.payload or {}).get("reponse_id")]
    return chunks, reponses


def etape_etat(db) -> None:
    titre("domaines configurés")
    for (d,) in db.query(Groupe.domaine).distinct().all():
        print(f"  {d}")

    titre("utilisateurs backoffice et leurs domaines")
    for u in db.query(User).all():
        print(f"  {u.id}  {u.role:<10} {u.email:<30} domaines={sorted(g.domaine for g in u.groupes) or '—'}")

    titre("documents")
    for d in db.query(Document).order_by(Document.created_at).all():
        print(f"  {d.doc_id}  v{d.version} {d.statut:<9} {d.nb_chunks:>3} chunks  {d.domaine:<10} {d.filename}")

    titre("réponses")
    for r in db.query(Reponse).order_by(Reponse.created_at).all():
        drapeaux = []
        if r.canonique:
            drapeaux.append("CANONIQUE")
        if r.a_relire:
            drapeaux.append(f"à relire={r.a_relire_raison}")
        if r.obsolete:
            drapeaux.append(f"OBSOLÈTE={r.obsolete_raison}")
        print(
            f"  {r.id}  {r.statut:<10} source={r.source:<12} nb_val={r.nb_validations} "
            f"{' '.join(drapeaux)}\n      {extrait(r.contenu, 120)}"
        )

    chunks, reponses = points_qdrant()
    titre(f"qdrant — {len(chunks)} chunks de documents, {len(reponses)} points-réponses")
    for p in chunks:
        c = p.payload or {}
        print(f"  chunk {c.get('doc_id')}#{c.get('chunk_index')} [{c.get('domaine')}] "
              f"contexte={extrait(c.get('contexte'), 80)}")
    for p in reponses:
        c = p.payload or {}
        print(f"  réponse {c.get('reponse_id')} indexée sous « {extrait(c.get('question_indexee'), 80)} »")

    print(f"\n  seuil_canonique={settings.seuil_canonique}  seuil_cosinus={settings.seuil_cosinus}  "
          f"contextualisation_active={settings.contextualisation_active}")


# ── étape « ingerer » ───────────────────────────────────────────────────


def etape_ingerer(db, lettre: str, domaine: str, uploader: str | None) -> None:
    from app.workers.ingestion import ingestion_job

    filename, contenu, description = DOCUMENTS[lettre]
    dossier = os.environ.get("UPLOAD_DIR", "/app/uploads_tmp")
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"{uuid.uuid4()}_{filename}")
    octets = contenu.encode()
    with open(chemin, "wb") as f:
        f.write(octets)

    doc_id = str(uuid.uuid4())
    titre(f"ingestion du document {lettre} — {filename}")
    print(f"  doc_id={doc_id} domaine={domaine}")
    print("  contenu :\n    " + "\n    ".join(contenu.strip().splitlines()))

    ingestion_job.apply_async(
        kwargs={
            "file_path": chemin,
            "filename": filename,
            "domaine": domaine,
            "description": description,
            "content_hash": hashlib.sha256(octets).hexdigest(),
            "uploaded_by": uploader,
            "doc_id": doc_id,
        },
        queue="queue_ingestion",
    )

    def abouti():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_id).first()
        return d if d and d.nb_chunks else None

    doc = attendre(abouti, 300, "ingestion")
    if doc is None:
        sys.exit(1)
    print(f"  {doc.nb_chunks} chunk(s) indexé(s), statut={doc.statut}")

    for p in points_qdrant()[0]:
        c = p.payload or {}
        if c.get("doc_id") != doc_id:
            continue
        titre(f"chunk #{c.get('chunk_index')} tel qu'écrit dans le payload")
        print(f"  contenu (brut)  : {extrait(c.get('contenu'))}")
        print(f"  contexte        : {extrait(c.get('contexte'))}")

    ecrire_etat(**{f"doc_{lettre}": doc_id, "domaine": domaine})


# ── étape « supprimer » ─────────────────────────────────────────────────


def etape_supprimer(db, doc_id: str, validateur: str) -> None:
    """Retire un document, pour rejouer le scénario sur un domaine propre.

    Passe par l'endpoint réel plutôt que par un DELETE en base : lui seul retire
    aussi les points Qdrant et déclenche la péremption des réponses citantes.
    """
    from app.api.v1.documents.core import delete_document

    if doc_id == "dernier":
        doc_id = lire_etat()["doc_A"]
    user = db.query(User).filter(User.id == uuid.UUID(validateur)).first()
    titre(f"suppression du document {doc_id}")
    print(f"  {json.dumps(asyncio.run(delete_document(doc_id, current_user=user, db=db)), indent=2)}")


# ── étape « question » ──────────────────────────────────────────────────


def etape_question(db, texte: str, domaine: str) -> None:
    from app.workers.question import question_job

    titre(f"question — « {texte} »")
    job = question_job.apply_async(args=[texte, domaine, None], queue="queue_questions")
    job_id = uuid.UUID(job.id)

    def abouti():
        db.expire_all()
        t = db.query(Ticket).filter(Ticket.job_id == job_id).first()
        return t if t and t.statut_job in ("TERMINÉ", "ÉCHOUÉ") else None

    ticket = attendre(abouti, 300, "pipeline question")
    if ticket is None:
        sys.exit(1)

    print(f"  ticket={ticket.id} statut_job={ticket.statut_job} score_similarite={ticket.score_similarite}")
    if ticket.erreur:
        print(f"  \033[31merreur : {ticket.erreur}\033[0m")

    reponses = db.query(Reponse).filter(Reponse.ticket_id == ticket.id).order_by(Reponse.created_at).all()
    for r in reponses:
        titre(f"réponse {r.id} — branche {r.source}")
        print(f"  statut={r.statut} canonique={r.canonique} source_id={r.reponse_source_id}")
        print("  contenu :\n    " + "\n    ".join((r.contenu or "").splitlines()))
        for rc in db.query(ReponseChunk).filter(ReponseChunk.reponse_id == r.id).all():
            print(f"  cite {rc.doc_id}#{rc.chunk_index} cos={rc.score_cosinus} rerank={rc.rerank_score}")

    if reponses:
        ecrire_etat(dernier_ticket=str(ticket.id), derniere_reponse=str(reponses[-1].id))


# ── étape « valider » ───────────────────────────────────────────────────


def etape_valider(db, reponse_id: str, validateur: str) -> None:
    from app.api.v1.reponses.actions import valider_reponse

    if reponse_id == "dernier":
        reponse_id = lire_etat()["derniere_reponse"]
    user = db.query(User).filter(User.id == uuid.UUID(validateur)).first()
    if user is None:
        print(f"validateur {validateur} introuvable", file=sys.stderr)
        sys.exit(1)

    titre(f"validation de {reponse_id} par {user.email}")
    resultat = asyncio.run(valider_reponse(reponse_id, current_user=user))
    print(f"  {json.dumps(resultat, indent=2, ensure_ascii=False)}")

    # feedback_job est asynchrone : sans cette attente, l'étape suivante
    # chercherait un point-réponse qui n'est pas encore écrit.
    cible = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    racine = str(cible.reponse_source_id or cible.id)

    def indexe():
        points = [p for p in points_qdrant()[1] if (p.payload or {}).get("reponse_id") == racine]
        return points or None

    points = attendre(indexe, 120, "indexation de la réponse")
    for p in points or []:
        print(f"  point {p.id} sous « {extrait((p.payload or {}).get('question_indexee'), 90)} »")

    ecrire_etat(racine=racine)


# ── étape « corriger » ──────────────────────────────────────────────────


def etape_corriger(db, reponse_id: str, texte: str, validateur: str) -> None:
    """Le geste « Corriger » : le relecteur écrit lui-même la bonne réponse.

    C'est l'étape qui **fait naître** une réponse spécifique distincte de la
    canonique générale. Elle était stérile jusqu'au 17/09/2026 : le filtre
    `statut == "VALIDÉE"` excluait CORRIGÉE de `trouver_reponse_reutilisable`,
    si bien que le texte écrit par le relecteur partait dans Qdrant, servait de
    matière au contexte RAG, et n'était jamais resservi — donc n'accumulait
    jamais de validations, donc ne devenait jamais canonique.
    """
    from app.api.v1.reponses.actions import CorrigerRequest, corriger_reponse

    if reponse_id == "dernier":
        reponse_id = lire_etat()["derniere_reponse"]
    user = db.query(User).filter(User.id == uuid.UUID(validateur)).first()
    if user is None:
        print(f"validateur {validateur} introuvable", file=sys.stderr)
        sys.exit(1)

    titre(f"correction de {reponse_id} par {user.email}")
    resultat = asyncio.run(
        corriger_reponse(reponse_id, CorrigerRequest(contenu_corrige=texte), current_user=user)
    )
    print(f"  {json.dumps(resultat, indent=2, ensure_ascii=False)}")

    def indexe():
        points = [p for p in points_qdrant()[1] if (p.payload or {}).get("reponse_id") == reponse_id]
        return points or None

    for p in attendre(indexe, 120, "indexation de la correction") or []:
        print(f"  point {p.id} sous « {extrait((p.payload or {}).get('question_indexee'), 90)} »")


# ── étape « verdict » ───────────────────────────────────────────────────


def etape_verdict(db) -> None:
    etat = lire_etat()
    racine = etat.get("racine")
    doc_b = etat.get("doc_B")

    titre("état des réponses après l'arrivée du document B")
    sortie = 0
    for r in db.query(Reponse).order_by(Reponse.created_at).all():
        marque = "→" if str(r.id) == racine else " "
        print(
            f"{marque} {r.id}  {r.statut:<10} canonique={r.canonique!s:<5} "
            f"a_relire={r.a_relire!s:<5} raison={str(r.a_relire_raison):<20} "
            f"doc={str(r.a_relire_doc_id)[:8]:<8} obsolete={r.obsolete!s:<5} {str(r.obsolete_raison)}"
        )
        if r.analyse_justification:
            print(f"      justification : {extrait(r.analyse_justification, 400)}")
        if r.analyse_extraits:
            print(f"      extraits      : {extrait(json.dumps(r.analyse_extraits, ensure_ascii=False), 300)}")

    if not racine:
        print("\n  (pas de réponse de référence dans l'état — rien à conclure)")
        return

    r = db.query(Reponse).filter(Reponse.id == uuid.UUID(racine)).first()
    indexee = any((p.payload or {}).get("reponse_id") == racine for p in points_qdrant()[1])

    titre("attendu de la partie B")
    for libelle, obtenu, attendu in [
        ("a_relire", r.a_relire, True),
        ("a_relire_raison", r.a_relire_raison, "CONTREDITE_PROBABLE"),
        ("a_relire_doc_id", r.a_relire_doc_id, doc_b),
        ("obsolete", r.obsolete, False),
        ("toujours indexée dans Qdrant", indexee, True),
    ]:
        ok = obtenu == attendu
        sortie |= 0 if ok else 1
        marque = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        ecart = "" if ok else f"   (attendu {attendu!r})"
        print(f"  {marque} {libelle:<30} = {obtenu!r}{ecart}")
    sys.exit(sortie)


# ── étape « contexte » ──────────────────────────────────────────────────


def etape_contexte(passes: int) -> None:
    """Le contextualiseur seul, sur des lots de tailles différentes.

    Isolé de l'ingestion parce que ce qu'on mesure ici est l'**arité** de la
    sortie : un tableau de la mauvaise longueur est rejeté par `_lire_locateurs`
    et le document s'indexe brut, sans que rien n'échoue. C'est le seul mode de
    dégradation silencieux du procédé, donc le seul qui demande une mesure
    plutôt qu'une lecture du code.
    """
    import app.services.contextualisation as ctx

    resume = "Note de service NS-2026-03 sur le télétravail, applicable aux salariés."
    lots = {
        1: ["Le télétravail est autorisé du lundi au mercredi."],
        2: ["Le télétravail est autorisé du lundi au mercredi.", "Les alternants n'en bénéficient pas."],
        3: ["Le télétravail est autorisé du lundi au mercredi.", "Les alternants n'en bénéficient pas.",
            "La demande se fait auprès du manager."],
    }

    vrai_chat = ctx.chat
    bruts: list[str] = []

    def espion(*a, **k):
        sortie = vrai_chat(*a, **k)
        bruts.append(sortie)
        return sortie

    ctx.chat = espion
    try:
        for taille, lot in lots.items():
            titre(f"lot de {taille} extrait(s) — {passes} passe(s)")
            for n in range(1, passes + 1):
                bruts.clear()
                obtenus = ctx._contextualiser_lot(lot, resume)
                marque = "\033[32m✓\033[0m" if len(obtenus) == taille else "\033[31m✗\033[0m"
                print(f"  {marque} passe {n} : {len(obtenus)} locateur(s) rendu(s) pour {taille} extrait(s)")
                print(f"      brut : {extrait(bruts[0] if bruts else None, 240)}")
    finally:
        ctx.chat = vrai_chat


# ── étape « sonde » ─────────────────────────────────────────────────────


def etape_sonde(texte: str, domaine: str, passes: int) -> None:
    """Rappel + rerank + génération, sans ticket ni cache.

    Le chemin ticket peut court-circuiter sur une canonique (branche
    CANONIQUE/SUGGESTION) et ne dit alors rien du rappel documentaire. Cette
    sonde isole exactement ce que la partie A prétend améliorer. Rejouée
    plusieurs fois, parce qu'une passe de LLM ne conclut rien.
    """
    from app.services.llm import generate
    from app.services.reranker import rerank
    from app.services.search import search_hybrid

    for n in range(1, passes + 1):
        titre(f"sonde {n}/{passes} — « {texte} »")
        chunks = search_hybrid(texte, domaine, top_k=15)
        print(f"  rappel : {len(chunks)} points")
        for c in chunks:
            marque = "R" if c.get("reponse_id") else "D"
            print(f"    [{marque}] {str(c.get('doc_id'))[:8]}#{c.get('chunk_index')} "
                  f"cos={c['score_cosinus']:.4f} lex={c.get('score_lexical', 0.0):.2f}/terme "
                  f"| {extrait(c.get('contenu_indexe'), 110)}")

        rerankes = rerank(texte, chunks, top_k=5)
        print(f"  rerank top-{len(rerankes)} :")
        for i, c in enumerate(rerankes):
            print(f"    #{i + 1} score={c['rerank_score']:.4f} {str(c.get('doc_id'))[:8]}#{c.get('chunk_index')} "
                  f"| {extrait(c.get('contenu_indexe'), 110)}")

        contenu, hors_domaine = generate(texte, rerankes)
        print(f"  génération{' [HORS_DOMAINE]' if hors_domaine else ''} :")
        print("    " + "\n    ".join(contenu.splitlines()))


# ── étape « payloads » ──────────────────────────────────────────────────


def etape_payloads() -> None:
    """`contenu` brut, `contexte` peuplé — puis la preuve par le ré-encodage."""
    from app.services.bm25 import encoder
    from scripts.reencoder_vecteurs_creux import texte_indexe as depuis_payload

    chunks, reponses = points_qdrant()
    titre(f"{len(chunks)} chunks de documents")
    for p in chunks:
        c = p.payload or {}
        encode = depuis_payload(c)
        print(f"\n  {p.id}  {c.get('doc_id')}#{c.get('chunk_index')} [{c.get('domaine')}]")
        print(f"    contenu       : {extrait(c.get('contenu'), 200)}")
        print(f"    contexte      : {extrait(c.get('contexte'), 200)}")
        print(f"    texte encodé  : {extrait(encode, 200)}")
        print(f"    tokens creux  : {len(encoder(encode, est_requete=False)['indices'])}")

    titre(f"{len(reponses)} points-réponses")
    for p in reponses:
        c = p.payload or {}
        print(f"  {p.id}  réponse={c.get('reponse_id')}")
        print(f"    question_indexee : {extrait(c.get('question_indexee'), 150)}")
        print(f"    texte encodé     : {extrait(depuis_payload(c), 150)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--etape", required=True,
                        choices=["etat", "ingerer", "supprimer", "question", "valider", "corriger",
                                 "verdict", "contexte", "sonde", "payloads"])
    parser.add_argument("--fichier", choices=["A", "B"])
    parser.add_argument("--texte")
    parser.add_argument("--reponse", default="dernier")
    parser.add_argument("--validateur")
    parser.add_argument("--uploader")
    parser.add_argument("--doc", default="dernier")
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--domaine")
    args = parser.parse_args()

    domaine = args.domaine or lire_etat().get("domaine")
    db = SessionLocal()
    try:
        if args.etape == "etat":
            etape_etat(db)
        elif args.etape == "ingerer":
            etape_ingerer(db, args.fichier, domaine, args.uploader)
        elif args.etape == "supprimer":
            etape_supprimer(db, args.doc, args.validateur)
        elif args.etape == "question":
            etape_question(db, args.texte, domaine)
        elif args.etape == "valider":
            etape_valider(db, args.reponse, args.validateur)
        elif args.etape == "corriger":
            etape_corriger(db, args.reponse, args.texte, args.validateur)
        elif args.etape == "verdict":
            etape_verdict(db)
        elif args.etape == "contexte":
            etape_contexte(args.passes)
        elif args.etape == "sonde":
            etape_sonde(args.texte, domaine, args.passes)
        elif args.etape == "payloads":
            etape_payloads()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
