"""Campagne bout en bout : « règle générale, puis document qui la précise ».

Sujet **neuf** (plafond de remboursement d'un repas en mission) sur un domaine
**neuf**, pour que rien ne soit hérité des mesures antérieures — le corpus de la
stack de dev porte déjà trois variantes du scénario télétravail, et l'IDF de
Qdrant est calculée sur la collection entière.

Le sujet est choisi pour que la mauvaise réponse soit **vérifiable par machine** :
la règle générale dit `20 €`, l'exception dit `45 €`. « Servir la générale à une
question spécifique » se lit alors dans le texte servi, sans jugement humain.

    doc A — Le remboursement d'un repas en mission est plafonné à 20 €.
    doc B — Pour les missions à l'étranger, ce plafond est porté à 45 €.

Ce que chaque phase prouve, et à quel correctif ça se rattache :

===== ===================================== ==================================
phase  ce qui est mesuré                     correctif éprouvé
===== ===================================== ==================================
  1    ingestion de A, contextualisation     —
  2    la générale monte à canonique         —
  3    témoin : formulation neuve → CANONIQUE —
  4    B arrive → confrontation              nouveau (confrontation)
  5    question générale → la générale       C1 (a_relire n'est plus servi
       question spécifique → la spécifique   sans revue), C4 (refus → RAG)
  6    la spécifique devient canonique       C3 (pertinence d'abord,
                                             CORRIGÉE réutilisable)
  7    deux canoniques, zéro cannibalisation C1+C3+C4 ensemble
  8    bilan garde_decisions                 C2 (alias jugé avant écriture)
  9    miroir FAQ, page sans relecteur       C1 côté SQL
 10    fil de suivi « et à l'étranger ? »    C4 en mode suivi
 11    doc B en v2 : 45 € → 60 €             mise à jour + retrait du service
===== ===================================== ==================================

Les phases 10 et 11 comblent deux angles morts constatés après coup : sur le
domaine T5, après la phase 9, la base portait **0 réponse de suivi et 0 document
en version > 1**. Tout ce qui touche au fil et au remplacement de version était
donc couvert unitairement mais jamais exercé en réel — et la mise à jour est le
seul chemin capable de rendre une réponse **obsolète**, là où la confrontation
plafonne à `a_relire`.

⚠️ **À lancer depuis le conteneur backend**, jamais depuis l'hôte : celui-ci
porte la configuration de *production* (5432/6333) là où la stack de dev écoute
ailleurs. Pointer au mauvais endroit n'échoue pas — ça réussit silencieusement
contre les mauvaises données.

    docker compose -f docker-compose.dev.yml exec -T -e PYTHONPATH=/app backend \\
        python scripts/campagne_regle_generale.py --phase tout

Les phases sont séparées et rejouables ; l'état passe par
/tmp/campagne_regle_generale.json et le relevé complet est écrit dans
scripts/resultats_campagne_regle_generale.json.

⚠️ Ne **jamais** éditer un .py sous backend/ pendant une passe : `watchmedo`
relance uvicorn et les workers, ce qui tue la campagne en cours.
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.models.garde_decision import GardeDecision
from app.models.groupe import Groupe
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.user import User
from app.services.qdrant import COLLECTION_NAME, client

ETAT = "/tmp/campagne_regle_generale.json"
RELEVE = os.path.join(os.path.dirname(__file__), "resultats_campagne_regle_generale.json")

DOMAINE = "T5"
PASSES = 3

# ── le corpus ───────────────────────────────────────────────────────────
# B ne répète jamais « 20 » : c'est une *précision* de A, pas une v2 qui
# l'abroge. C'est précisément la distinction que PROMPT_SYSTEME_CONFRONTATION
# doit tenir, et la mesurer exige que le texte ne la donne pas gratuitement.

DOCUMENTS = {
    "A": (
        "ns_2026_21_frais_repas.txt",
        "Note de service NS-2026-21 — Frais de repas en mission\n"
        "\n"
        "Le remboursement d'un repas pris en mission est plafonné à 20 € par repas.\n"
        "Ce plafond s'applique à l'ensemble des agents et vaut pour le déjeuner "
        "comme pour le dîner.\n"
        "La demande de remboursement est déposée sur l'intranet dans les trente jours "
        "qui suivent la fin de la mission.\n",
        "Note de service sur les frais de repas en mission",
    ),
    "B": (
        "ns_2026_34_missions_etranger.txt",
        "Note de service NS-2026-34 — Missions à l'étranger\n"
        "\n"
        "Pour les missions à l'étranger, le plafond de remboursement d'un repas est "
        "porté à 45 € par repas.\n"
        "Ce plafond majoré s'applique dès le franchissement de la frontière et "
        "jusqu'au retour en France.\n"
        "Les justificatifs originaux sont exigés pour toute mission hors de France.\n",
        "Note de service sur les missions à l'étranger",
    ),
}

# Formulations générales. Le **vivier** est plus large que `seuil_canonique`
# parce qu'une validation ne tombe pas forcément sur la lignée précédente : un
# refus jugé renvoie au RAG (C4), ce qui fait naître une lignée parallèle sur le
# même sujet. C'est le coût assumé d'un refus prudent, documenté et **à ne pas
# arbitrer en assouplissant le juge** ; le relecteur réel, lui, continue de
# valider jusqu'à ce qu'une lignée atteigne le seuil. Le harnais fait pareil.
#
# Mesuré le 18/09/2026 : « À combien s'élève le remboursement… » contre « Quel
# est le plafond de remboursement… » est refusé à 0,9533 de cosinus — le plafond
# et le montant effectivement remboursé ne sont pas la même demande. Le RAG a
# alors répondu juste (20 €) : rien de faux n'a été servi, une génération a été
# dépensée.
VIVIER_GENERAL = [
    "Quel est le plafond de remboursement d'un repas en mission ?",
    "Combien puis-je me faire rembourser pour un repas lors d'une mission ?",
    "À combien s'élève le remboursement d'un repas en mission ?",
    "Quel est le montant maximum remboursé pour un repas en mission ?",
    "Jusqu'à quel montant un repas en mission est-il remboursé ?",
    "Quel plafond s'applique au remboursement d'un repas en mission ?",
]
# Jamais validées : réservées aux sondes, pour qu'aucun court-circuit
# typographique ne vienne masquer ce qu'on mesure.
G_SONDE = "Quel montant maximum pour un repas en mission ?"
G_SONDE2 = "Un repas en mission, c'est remboursé jusqu'à combien ?"

# Formulations spécifiques — la précision porte sur « à l'étranger ».
S1 = "Quel est le plafond de remboursement d'un repas lors d'une mission à l'étranger ?"
VIVIER_SPECIFIQUE = [
    "Combien puis-je me faire rembourser pour un repas en mission à l'étranger ?",
    "À l'étranger, quel est le montant maximum remboursé pour un repas ?",
    "Quel plafond de repas s'applique lors d'une mission à l'étranger ?",
    "En mission à l'étranger, jusqu'à combien un repas est-il remboursé ?",
    "Quel est le plafond repas pour une mission effectuée à l'étranger ?",
]
S_SONDE = "Pour une mission hors de France, quel plafond de repas s'applique ?"

# Le fil de la phase 10. La précision est volontairement **inintelligible hors
# de son fil** : « et à l'étranger ? » seule ne désigne ni un repas, ni une
# mission, ni un plafond. C'est ce qui fait qu'un suivi traité comme une
# question isolée se voit tout de suite, dans le texte servi.
G_FIL = "Un agent en mission peut-il se faire rembourser son repas ?"
S_FIL = "Et pour une mission à l'étranger ?"

# La v2 de doc B (phase 11). **Seul le montant change** : le diff se réduit donc
# à une réécriture de paragraphe, et l'anti-reflow de `_requalifier` n'a aucun
# prétexte à l'écarter. 60 € n'apparaît nulle part ailleurs dans le corpus, donc
# « la réponse servie porte encore 45 € » est une erreur lisible sans jugement.
DOC_B_V2 = (
    "ns_2026_34_missions_etranger.txt",
    "Note de service NS-2026-34 — Missions à l'étranger\n"
    "\n"
    "Pour les missions à l'étranger, le plafond de remboursement d'un repas est "
    "porté à 60 € par repas.\n"
    "Ce plafond majoré s'applique dès le franchissement de la frontière et "
    "jusqu'au retour en France.\n"
    "Les justificatifs originaux sont exigés pour toute mission hors de France.\n",
    "Note de service sur les missions à l'étranger",
)


def doc_b_variante(cible: int) -> tuple[str, str, str]:
    """Une v{n} de doc B pour la phase 12. **Aucun montant ne bouge.**

    Trois contraintes tenues ensemble :

    * ne toucher à aucun montant — la phase 11 asserte « 60 € » et un rejeu
      complet de la campagne la joue avant celle-ci ;
    * produire un diff non vide, sinon rien n'est enfilé du tout ;
    * garder le changement sur le paragraphe du *plafond majoré*, assez proche du
      sujet « remboursement de repas » pour que la générale soit rapprochée par
      similarité et **effectivement soumise au juge**.

    Le texte dépend de la version visée : la phase peut donc être rejouée, et
    chaque rejeu produit un vrai diff au lieu de se court-circuiter sur
    l'empreinte — un « on remesure sans réingérer » ne rejugerait rien.
    """
    precisions = {
        3: "jours de transit compris",
        4: "escales et jours de transit compris",
        5: "y compris les escales, les jours de transit et le jour du retour",
    }
    precision = precisions.get(cible, f"selon les modalités en vigueur au titre de la version {cible}")
    return (
        "ns_2026_34_missions_etranger.txt",
        "Note de service NS-2026-34 — Missions à l'étranger\n"
        "\n"
        "Pour les missions à l'étranger, le plafond de remboursement d'un repas est "
        "porté à 60 € par repas.\n"
        "Ce plafond majoré s'applique dès le franchissement de la frontière et "
        f"jusqu'au retour en France, {precision}.\n"
        "Les justificatifs originaux sont exigés pour toute mission hors de France.\n",
        "Note de service sur les missions à l'étranger",
    )


# Le motif rendu par le juge de confrontation le 18/09/2026, repris mot pour mot :
# la phase 12 restaure un état mesuré, elle n'en fabrique pas un.
JUSTIF_CONFRONTATION = (
    "La réponse est incomplète car elle omet l'exception des missions à l'étranger où le plafond est porté à 45 €."
)


# ── utilitaires ─────────────────────────────────────────────────────────


def lire_etat() -> dict:
    if not os.path.exists(ETAT):
        return {}
    with open(ETAT) as f:
        return json.load(f)


def ecrire_etat(**champs) -> dict:
    etat = lire_etat()
    etat.update(champs)
    with open(ETAT, "w") as f:
        json.dump(etat, f, indent=2, ensure_ascii=False)
    return etat


def journal(**champs) -> None:
    """Ajoute une observation au relevé cumulatif, sur disque.

    Sérialise d'abord en mémoire, écrit ensuite : une valeur non sérialisable
    (un `Unite` passé par mégarde, mesuré le 18/09/2026) faisait sinon planter
    `json.dump` **au milieu du fichier**, qui devenait illisible — et c'est le
    relevé de toute la campagne qui partait avec, pour une ligne de mesure.
    """
    releve = []
    if os.path.exists(RELEVE):
        with open(RELEVE) as f:
            try:
                releve = json.load(f)
            except json.JSONDecodeError as exc:
                print(f"  \033[33m⚠\033[0m relevé illisible ({exc}) — on repart d'un relevé vide", flush=True)
    champs["horodatage"] = datetime.now(timezone.utc).isoformat()
    releve.append(champs)
    texte = json.dumps(releve, indent=2, ensure_ascii=False, default=str)
    with open(RELEVE, "w") as f:
        f.write(texte)


def titre(texte: str) -> None:
    print(f"\n\033[1m── {texte} {'─' * max(0, 70 - len(texte))}\033[0m", flush=True)


def extrait(texte: str | None, n: int = 240) -> str:
    if not texte:
        return "∅"
    plat = " ".join(texte.split())
    return plat if len(plat) <= n else plat[:n] + "…"


def attendre(predicat, delai: int, quoi: str):
    debut = time.time()
    while time.time() - debut < delai:
        valeur = predicat()
        if valeur is not None:
            print(f"  {quoi} : abouti en {time.time() - debut:.0f} s", flush=True)
            return valeur
        time.sleep(2)
    print(f"  {quoi} : \033[31mtoujours rien après {delai} s\033[0m", flush=True)
    return None


# Les assertions de la campagne s'accumulent ici, puis sont rendues en bloc.
CONSTATS: list[tuple[bool, str, str]] = []


def constat(ok: bool, libelle: str, detail: str = "") -> bool:
    CONSTATS.append((ok, libelle, detail))
    marque = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {marque} {libelle}" + (f"\n      {detail}" if detail else ""), flush=True)
    return ok


def dit(texte: str | None, montant: str) -> bool:
    """Le texte énonce-t-il ce montant ? Comparaison sur le nombre, pas la phrase."""
    return bool(texte) and re.search(rf"\b{montant}\b", texte) is not None


def points_qdrant() -> tuple[list, list]:
    tous, offset = [], None
    while True:
        lot, offset = client.scroll(COLLECTION_NAME, limit=200, offset=offset, with_payload=True)
        tous += lot
        if offset is None:
            break
    return (
        [p for p in tous if not (p.payload or {}).get("reponse_id")],
        [p for p in tous if (p.payload or {}).get("reponse_id")],
    )


def validateur(db) -> User:
    """L'administrateur, rattaché au domaine de la campagne si besoin."""
    u = db.query(User).filter(User.role == "ADMIN").first()
    if u is None:
        print("aucun ADMIN en base", file=sys.stderr)
        sys.exit(1)
    if DOMAINE not in {g.domaine for g in u.groupes}:
        groupe = db.query(Groupe).filter(Groupe.domaine == DOMAINE).first()
        if groupe is None:
            groupe = Groupe(nom=f"Campagne {DOMAINE}", domaine=DOMAINE)
            db.add(groupe)
            db.flush()
        u.groupes.append(groupe)
        db.commit()
        db.refresh(u)
    return u


# ── briques : ingérer, demander, valider ────────────────────────────────


def ingerer(db, lettre: str, uploader: str | None = None) -> str:
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
    print(f"  doc_id={doc_id} domaine={DOMAINE}")
    print("  " + "\n  ".join(contenu.strip().splitlines()), flush=True)

    ingestion_job.apply_async(
        kwargs={
            "file_path": chemin,
            "filename": filename,
            "domaine": DOMAINE,
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

    doc = attendre(abouti, 420, f"ingestion de {lettre}")
    if doc is None:
        constat(False, f"document {lettre} ingéré", "aucun chunk après 420 s")
        sys.exit(1)

    contextes = []
    for p in points_qdrant()[0]:
        c = p.payload or {}
        if c.get("doc_id") != doc_id:
            continue
        contextes.append(c.get("contexte") or "")
        print(f"  chunk #{c.get('chunk_index')}")
        print(f"    contenu  : {extrait(c.get('contenu'), 160)}")
        print(f"    contexte : {extrait(c.get('contexte'), 160)}", flush=True)

    constat(
        all(contextes) and len(contextes) == doc.nb_chunks,
        f"document {lettre} : {doc.nb_chunks} chunk(s), tous contextualisés",
        f"contextes vides : {sum(1 for c in contextes if not c)}/{len(contextes)}",
    )
    journal(phase="ingestion", document=lettre, doc_id=doc_id, nb_chunks=doc.nb_chunks, contextes=contextes)
    ecrire_etat(**{f"doc_{lettre}": doc_id})
    return doc_id


def demander(db, texte: str) -> dict:
    """Une question, par le vrai worker, jusqu'au ticket abouti."""
    from app.workers.question import question_job

    job = question_job.apply_async(args=[texte, DOMAINE, None], queue="queue_questions")
    job_id = uuid.UUID(job.id)

    def abouti():
        """« ÉCHOUÉ » n'est pas terminal — et le confondre avec un échec ment.

        Mesuré le 18/09/2026 : un 429 d'Albert sur la génération écrit
        `statut_job=ÉCHOUÉ` puis `question_job` se rejoue 60 s plus tard et
        aboutit. Conclure au premier ÉCHOUÉ fait rendre au harnais une réponse
        vide là où le système en a produit une bonne — un faux négatif fabriqué
        par l'outil de mesure. On n'accepte donc que TERMINÉ, et on laisse le
        délai global couvrir les reprises.
        """
        db.expire_all()
        t = db.query(Ticket).filter(Ticket.job_id == job_id).first()
        if t is None:
            return None
        if t.statut_job == "TERMINÉ":
            return t
        if t.statut_job == "ÉCHOUÉ":
            print(f"    échec transitoire ({extrait(t.erreur, 60)}) — on attend la reprise", flush=True)
        return None

    ticket = attendre(abouti, 420, f"question « {extrait(texte, 60)} »")
    if ticket is None:
        return {"erreur": "délai dépassé", "question": texte}

    reponses = db.query(Reponse).filter(Reponse.ticket_id == ticket.id).order_by(Reponse.created_at).all()
    r = reponses[-1] if reponses else None
    cites = (
        [
            {"doc_id": rc.doc_id, "chunk": rc.chunk_index, "cos": rc.score_cosinus, "rerank": rc.rerank_score}
            for rc in db.query(ReponseChunk).filter(ReponseChunk.reponse_id == r.id).all()
        ]
        if r
        else []
    )

    # La décision du garde attachée à CE job, s'il y en a eu une.
    g = db.query(GardeDecision).filter(GardeDecision.job_id == job_id).first()
    garde = (
        {
            "verdict": g.verdict,
            "court_circuit": g.court_circuit,
            "erreur": g.erreur,
            "cosinus": g.score_cosinus,
            "lexical": g.score_lexical,
            "question_indexee": g.question_indexee,
        }
        if g
        else None
    )

    obs = {
        "question": texte,
        "ticket_id": str(ticket.id),
        "statut_job": ticket.statut_job,
        "erreur": ticket.erreur,
        "branche": r.source if r else None,
        "reponse_id": str(r.id) if r else None,
        "reponse_source_id": str(r.reponse_source_id) if r and r.reponse_source_id else None,
        "cosinus": ticket.score_similarite,
        "contenu": r.contenu_corrige or r.contenu if r else None,
        "cite": cites,
        "garde": garde,
    }

    juge = "—"
    if garde:
        juge = "court-circuit" if garde["court_circuit"] else ("OUI" if garde["verdict"] else "NON")
        if garde["erreur"]:
            juge = f"panne({extrait(garde['erreur'], 40)})"
    print(
        f"  branche={str(obs['branche']):<11} cos={obs['cosinus']} garde={juge}"
        f" source_id={str(obs['reponse_source_id'])[:8]}"
    )
    print(f"    {extrait(obs['contenu'], 300)}", flush=True)
    return obs


def demander_suivi(db, ticket_id: str, texte: str) -> dict:
    """Une précision posée **dans le fil** d'un ticket existant.

    Un suivi n'ouvre pas de ticket : il ajoute une réponse à celui qu'on lui
    passe. `demander` attend un ticket portant son `job_id` et resterait donc
    bloqué ici — d'où ce frère, qui guette la réponse nouvelle.
    """
    from app.workers.question import question_job

    tid = uuid.UUID(ticket_id)
    db.expire_all()
    avant = {r.id for r in db.query(Reponse).filter(Reponse.ticket_id == tid).all()}

    job = question_job.apply_async(
        kwargs={"question": texte, "domaine": DOMAINE, "user_id": None, "ticket_id": ticket_id},
        queue="queue_questions",
    )
    job_id = uuid.UUID(job.id)

    def abouti():
        db.expire_all()
        nouvelles = [
            r
            for r in db.query(Reponse).filter(Reponse.ticket_id == tid).order_by(Reponse.created_at).all()
            if r.id not in avant
        ]
        if nouvelles:
            return nouvelles[-1]
        t = db.query(Ticket).filter(Ticket.id == tid).first()
        return t if t and t.statut_job == "ÉCHOUÉ" else None

    r = attendre(abouti, 420, f"suivi « {extrait(texte, 50)} »")
    if r is None or isinstance(r, Ticket):
        print("  \033[31maucune réponse de suivi\033[0m", flush=True)
        return {"question": texte, "ticket_id": ticket_id, "erreur": "aucune réponse", "garde": None}

    g = db.query(GardeDecision).filter(GardeDecision.job_id == job_id).first()
    garde = (
        {
            "verdict": g.verdict,
            "court_circuit": g.court_circuit,
            "erreur": g.erreur,
            "cosinus": g.score_cosinus,
            "est_suivi": g.est_suivi,
            "question_posee": g.question_posee,
            "question_indexee": g.question_indexee,
        }
        if g
        else None
    )
    obs = {
        "question": texte,
        "ticket_id": ticket_id,
        "reponse_id": str(r.id),
        "reponse_source_id": str(r.reponse_source_id) if r.reponse_source_id else None,
        "branche": r.source,
        "est_suivi": r.question_suivi == texte,
        "contenu": r.contenu_corrige or r.contenu,
        "garde": garde,
    }
    juge = "—"
    if garde:
        juge = "court-circuit" if garde["court_circuit"] else ("OUI" if garde["verdict"] else "NON")
        if garde["erreur"]:
            juge = f"panne({extrait(garde['erreur'], 40)})"
        print(f"    garde={juge} suivi={garde['est_suivi']} cos={garde['cosinus']}")
        print(f"      paire soumise : {extrait(garde['question_posee'], 120)}")
        print(f"      contre        : {extrait(garde['question_indexee'], 120)}", flush=True)
    print(f"  branche={obs['branche']:<11} suivi={obs['est_suivi']} garde={juge}")
    print(f"    {extrait(obs['contenu'], 300)}", flush=True)
    return obs


def sonder(db, texte: str, passes: int = PASSES) -> list[dict]:
    titre(f"sonde ×{passes} — « {texte} »")
    obs = []
    for n in range(1, passes + 1):
        print(f"  passe {n}/{passes}", flush=True)
        obs.append(demander(db, texte))
    journal(phase="sonde", question=texte, passes=obs)
    return obs


def valider(db, reponse_id: str) -> dict:
    """Valide une réponse et rend l'état de sa **racine**.

    Le compteur qui décide de la promotion vit sur la source, pas sur la copie :
    `valider_reponse` incrémente `reponse_source.nb_validations` et renvoie, lui,
    le compteur de la réponse validée — à 0 pour toute copie SUGGESTION. Lire la
    valeur rendue ferait croire qu'aucune validation ne s'accumule.
    """
    from app.api.v1.reponses.actions import valider_reponse

    user = validateur(db)
    asyncio.run(valider_reponse(reponse_id, current_user=user))

    db.expire_all()
    cible = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    racine_id = cible.reponse_source_id or cible.id
    racine = db.query(Reponse).filter(Reponse.id == racine_id).first()
    print(
        f"  validée → racine={str(racine_id)[:8]} nb_validations={racine.nb_validations} canonique={racine.canonique}",
        flush=True,
    )

    # feedback_job est asynchrone : sans cette attente, la phase suivante
    # chercherait un point-réponse qui n'est pas encore écrit.
    attendu = racine.nb_validations

    def indexe():
        pts = [p for p in points_qdrant()[1] if (p.payload or {}).get("reponse_id") == str(racine_id)]
        return pts if len(pts) >= attendu else None

    # Un alias refusé par le garde (C2) n'est jamais écrit : l'attente peut donc
    # légitimement expirer sans que rien n'aille mal. On la borne court.
    pts = attendre(indexe, 90, "indexation des formulations") or [
        p for p in points_qdrant()[1] if (p.payload or {}).get("reponse_id") == str(racine_id)
    ]
    for p in pts:
        print(f"    point sous « {extrait((p.payload or {}).get('question_indexee'), 80)} »", flush=True)
    journal(
        phase="validation",
        reponse_id=reponse_id,
        racine=str(racine_id),
        nb_validations=racine.nb_validations,
        canonique=bool(racine.canonique),
        formulations=[(p.payload or {}).get("question_indexee") for p in pts],
    )
    return {"racine": str(racine_id), "nb_validations": racine.nb_validations, "canonique": bool(racine.canonique)}


def attendre_confrontation(db, delai: int = 600) -> None:
    """Patiente jusqu'à ce que plus aucune réponse ne soit en analyse."""

    def fini():
        db.expire_all()
        reste = (
            db.query(Reponse)
            .join(Ticket, Reponse.ticket_id == Ticket.id)
            .filter(Ticket.domaine == DOMAINE, Reponse.a_relire_raison == "ANALYSE_EN_COURS")
            .count()
        )
        return True if reste == 0 else None

    # Laisser le job démarrer avant de conclure « plus rien en cours ».
    time.sleep(10)
    attendre(fini, delai, "confrontation")


def reponses_du_domaine(db) -> list[Reponse]:
    return (
        db.query(Reponse)
        .join(Ticket, Reponse.ticket_id == Ticket.id)
        .filter(Ticket.domaine == DOMAINE)
        .order_by(Reponse.created_at)
        .all()
    )


def tableau_reponses(db) -> None:
    titre("réponses du domaine")
    for r in reponses_du_domaine(db):
        drapeaux = []
        if r.canonique:
            drapeaux.append("CANONIQUE")
        if r.a_relire:
            drapeaux.append(f"à relire={r.a_relire_raison}")
        if r.obsolete:
            drapeaux.append(f"OBSOLÈTE={r.obsolete_raison}")
        print(
            f"  {str(r.id)[:8]} {r.statut:<10} {r.source:<11} nb_val={r.nb_validations} "
            f"{' '.join(drapeaux)}\n      {extrait(r.contenu_corrige or r.contenu, 130)}",
            flush=True,
        )


# ── phases ──────────────────────────────────────────────────────────────


def phase_1(db) -> None:
    titre("PHASE 1 — le document général arrive")
    validateur(db)  # crée le groupe du domaine au besoin
    ingerer(db, "A")


# Les questions posées par la dernière montée en canonique, pour que l'appelant
# puisse relire *comment* la promotion s'est faite et pas seulement son résultat.
OBSERVATIONS: list[dict] = []


def porter_a_canonique(db, vivier: list[str], montant: str, etiquette: str, depart: str | None = None) -> str:
    """Valide formulation après formulation jusqu'à ce qu'une lignée soit canonique.

    Reproduit le geste réel du relecteur plutôt qu'un compte fixe de validations :
    un refus jugé du garde renvoie la question au RAG (C4) et fait naître une
    lignée parallèle, si bien que N validations ne donnent pas forcément N sur la
    même réponse. Le relecteur, lui, revalide ; la boucle s'arrête sur l'état
    visé, pas sur un quota d'appels.
    """
    OBSERVATIONS.clear()
    lignees: dict[str, int] = {}
    if depart:
        res = valider(db, depart)
        lignees[res["racine"]] = res["nb_validations"]
        if res["canonique"]:
            return res["racine"]

    for i, q in enumerate(vivier, start=1):
        titre(f"{etiquette} — validation n°{i} « {q} »")
        obs = demander(db, q)
        OBSERVATIONS.append(obs)
        if not obs.get("reponse_id"):
            constat(False, f"{etiquette} n°{i} : réponse produite", str(obs))
            sys.exit(1)
        constat(
            dit(obs["contenu"], montant),
            f"{etiquette} n°{i} : la réponse énonce bien {montant} €",
            f"branche={obs['branche']} — {extrait(obs['contenu'], 150)}",
        )
        res = valider(db, obs["reponse_id"])
        lignees[res["racine"]] = res["nb_validations"]
        if res["canonique"]:
            print(
                f"\n  seuil atteint après {i} validation(s) — lignées : { {k[:8]: v for k, v in lignees.items()} }",
                flush=True,
            )
            journal(
                phase="promotion",
                etiquette=etiquette,
                racine=res["racine"],
                validations_depensees=i,
                lignees=dict(lignees),
            )
            return res["racine"]

    constat(
        False,
        f"{etiquette} : une lignée atteint {settings.seuil_canonique} validations",
        f"vivier épuisé — lignées={ {k[:8]: v for k, v in lignees.items()} }",
    )
    sys.exit(1)


def phase_2(db) -> None:
    titre("PHASE 2 — une réponse générale monte jusqu'à canonique")
    racine = porter_a_canonique(db, VIVIER_GENERAL, "20", "générale")

    db.expire_all()
    r = db.query(Reponse).filter(Reponse.id == uuid.UUID(racine)).first()
    constat(
        bool(r.canonique) and r.nb_validations >= settings.seuil_canonique,
        "la réponse générale est canonique",
        f"racine={racine[:8]} nb_validations={r.nb_validations}",
    )
    constat(
        dit(r.contenu_corrige or r.contenu, "20"),
        "la canonique générale énonce bien la règle générale (20 €)",
        extrait(r.contenu_corrige or r.contenu, 160),
    )
    ecrire_etat(generale=racine)


def phase_3(db) -> None:
    titre("PHASE 3 — témoin AVANT B : une formulation neuve sort CANONIQUE")
    generale = lire_etat().get("generale")
    obs = sonder(db, G_SONDE)
    branches = [o["branche"] for o in obs]
    constat(
        all(b == "CANONIQUE" for b in branches),
        f"formulation jamais validée servie sans revue, {PASSES}/{PASSES}",
        f"branches={branches}",
    )
    constat(
        all(dit(o["contenu"], "20") for o in obs),
        "le témoin énonce bien la règle générale (20 €)",
        f"extrait : {extrait(obs[0]['contenu'], 160)}",
    )
    constat(
        all(o["reponse_source_id"] == generale for o in obs),
        "le témoin provient bien de la canonique générale",
        f"sources={[str(o['reponse_source_id'])[:8] for o in obs]}",
    )


def phase_4(db) -> None:
    titre("PHASE 4 — le document B précise la règle ; la confrontation s'exécute")
    generale = lire_etat().get("generale")
    doc_b = ingerer(db, "B")
    attendre_confrontation(db)

    db.expire_all()
    r = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    indexee = any((p.payload or {}).get("reponse_id") == generale for p in points_qdrant()[1])

    titre("verdict de la confrontation sur la canonique générale")
    constat(bool(r.a_relire), "la canonique générale est signalée à relire", f"raison={r.a_relire_raison}")
    constat(
        r.a_relire_raison in ("NOUVEAU_DOC", "CONTREDITE_PROBABLE"),
        "la raison désigne bien l'arrivée d'un document",
        f"a_relire_raison={r.a_relire_raison!r}",
    )
    constat(r.a_relire_doc_id == doc_b, "le signal pointe vers B", f"doc={r.a_relire_doc_id}")
    constat(
        r.obsolete is False,
        "INVARIANT : elle n'est PAS détruite (obsolete reste False)",
        f"obsolete={r.obsolete} raison={r.obsolete_raison}",
    )
    constat(indexee, "INVARIANT : elle est toujours indexée dans Qdrant")
    constat(bool(r.canonique), "elle reste canonique (le drapeau est un tri, pas un retrait)")
    if r.analyse_justification:
        print(f"\n  justification du juge :\n    {extrait(r.analyse_justification, 500)}", flush=True)
    journal(
        phase="confrontation",
        doc_b=doc_b,
        a_relire=bool(r.a_relire),
        raison=r.a_relire_raison,
        obsolete=bool(r.obsolete),
        canonique=bool(r.canonique),
        indexee=indexee,
        justification=r.analyse_justification,
    )


def phase_5(db) -> None:
    titre("PHASE 5 — les deux questions, APRÈS l'arrivée de B")
    generale = lire_etat().get("generale")

    titre("5a — question GÉNÉRALE : on doit au minimum avoir la règle générale")
    obs_g = sonder(db, G_SONDE2)
    constat(
        all(dit(o["contenu"], "20") for o in obs_g),
        f"la question générale reçoit la règle générale (20 €), {PASSES}/{PASSES}",
        f"branches={[o['branche'] for o in obs_g]}",
    )
    constat(
        all(o["branche"] != "CANONIQUE" for o in obs_g),
        "C1 : signalée à relire, elle n'est plus servie SANS REVUE",
        f"branches={[o['branche'] for o in obs_g]} (CANONIQUE attendu absent)",
    )

    titre("5b — question SPÉCIFIQUE : interdiction de servir l'ancienne canonique")
    obs_s = sonder(db, S1)
    constat(
        all(dit(o["contenu"], "45") for o in obs_s),
        f"la question spécifique reçoit la BONNE réponse (45 €), {PASSES}/{PASSES}",
        f"branches={[o['branche'] for o in obs_s]}",
    )
    constat(
        not any(o["reponse_source_id"] == generale for o in obs_s),
        "INVARIANT : l'ancienne canonique générale n'est JAMAIS servie à la question spécifique",
        f"sources={[str(o['reponse_source_id'])[:8] for o in obs_s]}",
    )
    refus = [o for o in obs_s if o.get("garde") and not o["garde"]["verdict"] and not o["garde"]["erreur"]]
    constat(
        bool(refus),
        "C4 : le garde a été consulté et a refusé au moins une fois",
        f"{len(refus)}/{PASSES} refus jugés — cosinus={[o['garde']['cosinus'] for o in obs_s if o.get('garde')]}",
    )
    constat(
        all(o["branche"] == "LLM" for o in refus),
        "C4 : après un refus jugé, la question repart bien au RAG (source=LLM)",
        f"branches après refus={[o['branche'] for o in refus]}",
    )
    # La preuve documentaire : la génération s'appuie sur B.
    doc_b = lire_etat().get("doc_B")
    cite_b = [any(c["doc_id"] == doc_b for c in o["cite"]) for o in obs_s if o["branche"] == "LLM"]
    constat(
        bool(cite_b) and all(cite_b),
        "la génération spécifique cite bien le document B",
        f"cite B={cite_b}",
    )
    spec = next((o for o in obs_s if o["branche"] == "LLM" and dit(o["contenu"], "45")), None)
    if spec:
        ecrire_etat(reponse_specifique=spec["reponse_id"])


def phase_6(db) -> None:
    titre("PHASE 6 — la réponse spécifique gagne sa propre canonique")
    etat = lire_etat()
    generale = etat.get("generale")
    depart = etat.get("reponse_specifique")
    if not depart:
        constat(False, "une réponse spécifique issue du RAG existe", "phase 5 n'en a produit aucune")
        sys.exit(1)

    # C3 se lit ici : la spécifique part de zéro validation face à une générale
    # déjà canonique. Qu'elle soit tout de même retenue par la sélection est
    # exactement ce que « la pertinence d'abord, le statut en départage » a
    # débloqué — avant, la générale raflait tout et la spécifique n'accumulait
    # jamais rien (famine structurelle).
    db.expire_all()
    g0 = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    print(
        f"  au départ : générale nb_val={g0.nb_validations} canonique={g0.canonique} | "
        f"spécifique nb_val=0 canonique=False",
        flush=True,
    )

    racine = porter_a_canonique(db, VIVIER_SPECIFIQUE, "45", "spécifique", depart=depart)
    montee = list(OBSERVATIONS)
    ecrire_etat(specifique=racine)

    db.expire_all()
    s = db.query(Reponse).filter(Reponse.id == uuid.UUID(racine)).first()
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    constat(
        bool(s.canonique),
        "la réponse spécifique est devenue canonique",
        f"nb_validations={s.nb_validations}",
    )
    # C3, lu sur la montée elle-même : tant qu'elle était moins validée que la
    # générale canonique, la spécifique a quand même été retenue comme candidate.
    reprises = [o for o in montee if o["reponse_source_id"] == racine]
    constat(
        bool(reprises),
        "C3 : la spécifique, moins validée que la canonique générale, est tout de même "
        "resservie — la pertinence prime sur le statut",
        f"{len(reprises)}/{len(montee)} question(s) resservies par la lignée spécifique "
        f"(générale canonique à nb_val={g0.nb_validations} au départ)",
    )
    constat(
        not any(o["reponse_source_id"] == generale for o in montee),
        "pendant toute la montée, la canonique générale n'a jamais été servie à une question spécifique",
        f"sources={[str(o['reponse_source_id'])[:8] for o in montee]}",
    )
    constat(
        bool(g.canonique) and not g.obsolete,
        "MODE NOMINAL : les deux canoniques coexistent sur le même sujet, même domaine",
        f"générale={str(g.id)[:8]} (nb_val={g.nb_validations}, a_relire={g.a_relire}) | "
        f"spécifique={str(s.id)[:8]} (nb_val={s.nb_validations})",
    )


def phase_7(db) -> None:
    titre("PHASE 7 — non-cannibalisation : chaque question reçoit la sienne")
    etat = lire_etat()
    generale, specifique = etat.get("generale"), etat.get("specifique")

    titre("7a — formulation générale jamais validée")
    obs_g = sonder(db, G_SONDE2)
    constat(
        all(dit(o["contenu"], "20") for o in obs_g),
        f"la question générale reçoit toujours la règle générale, {PASSES}/{PASSES}",
        f"branches={[o['branche'] for o in obs_g]} sources={[str(o['reponse_source_id'])[:8] for o in obs_g]}",
    )
    constat(
        not any(o["reponse_source_id"] == specifique for o in obs_g),
        "la canonique SPÉCIFIQUE ne cannibalise pas la question générale",
        f"sources={[str(o['reponse_source_id'])[:8] for o in obs_g]}",
    )

    titre("7b — formulation spécifique jamais validée")
    obs_s = sonder(db, S_SONDE)
    constat(
        all(dit(o["contenu"], "45") for o in obs_s),
        f"la question spécifique reçoit la réponse spécifique (45 €), {PASSES}/{PASSES}",
        f"branches={[o['branche'] for o in obs_s]} sources={[str(o['reponse_source_id'])[:8] for o in obs_s]}",
    )
    constat(
        not any(o["reponse_source_id"] == generale for o in obs_s),
        "INVARIANT : la canonique GÉNÉRALE ne cannibalise pas la question spécifique",
        f"sources={[str(o['reponse_source_id'])[:8] for o in obs_s]}",
    )
    # Ce qui est garanti ici est la sûreté, pas la branche. Mesuré le 18/09/2026 :
    # les 3 passes sortent en SUGGESTION avec le bon contenu (45 €), parce que la
    # sélection a retenu `d922d15a` (nb_val=2, non canonique) plutôt que la
    # canonique spécifique — quasi-ex æquo en RRF. C'est le coût assumé et
    # documenté de C3 (« la pertinence d'abord, le statut en départage ») : une
    # lecture de plus pour le relecteur, jamais une réponse fausse. Exiger
    # CANONIQUE ici reviendrait à réclamer une propriété que la conception a
    # explicitement échangée contre la sûreté — l'ordre de préférence du
    # propriétaire place la justesse au-dessus de la charge de relecture.
    constat(
        all(o["branche"] != "CANONIQUE" or dit(o["contenu"], "45") for o in obs_s),
        "INVARIANT : rien de faux n'est servi sans revue sur la question spécifique",
        f"branches={[o['branche'] for o in obs_s]} — une sortie non-CANONIQUE est une "
        f"relecture de plus, pas une réponse fausse",
    )
    sans_revue = [o for o in obs_s if o["branche"] == "CANONIQUE"]
    print(
        f"\n  observation (hors constat) : {len(sans_revue)}/{PASSES} passe(s) servies sans revue ; "
        f"le reste part en relecture avec le bon contenu — coût assumé de C3.",
        flush=True,
    )


def phase_8(db) -> None:
    titre("PHASE 8 — journal du garde et attribution")
    debut = lire_etat().get("debut")
    q = db.query(GardeDecision).filter(GardeDecision.domaine == DOMAINE)
    if debut:
        q = q.filter(GardeDecision.created_at >= datetime.fromisoformat(debut))
    lignes = q.order_by(GardeDecision.created_at).all()

    print(f"  {len(lignes)} décision(s) de garde sur le domaine {DOMAINE}\n", flush=True)
    for d in lignes:
        verdict = "OUI" if d.verdict else "NON"
        if d.court_circuit:
            verdict = "OUI (court-circuit)"
        if d.erreur:
            verdict = f"NON (panne : {extrait(d.erreur, 40)})"
        cos = f"{d.score_cosinus:.4f}" if d.score_cosinus is not None else "  NULL "
        print(f"  {verdict:<20} cos={cos} lex={d.score_lexical}")
        print(f"      posée   : {extrait(d.question_posee, 90)}")
        print(f"      indexée : {extrait(d.question_indexee, 90)}", flush=True)

    alias = [d for d in lignes if d.score_cosinus is None]
    constat(
        bool(alias),
        "C2 : des formulations ont été soumises au garde AVANT d'être écrites en alias",
        f"{len(alias)} décision(s) à score_cosinus NULL (la paire vient d'un geste humain, pas d'une recherche)",
    )
    juges = [d for d in lignes if not d.court_circuit and not d.erreur]
    refus = [d for d in juges if not d.verdict]
    constat(
        bool(refus),
        "C4 : le juge a refusé des paires, et ces refus ont servi",
        f"{len(refus)} refus jugés sur {len(juges)} appels réels",
    )
    constat(
        not any(d.erreur for d in lignes),
        "aucune décision rendue par défaut faute d'Albert",
        f"pannes={sum(1 for d in lignes if d.erreur)}",
    )
    journal(
        phase="garde",
        total=len(lignes),
        appels_juges=len(juges),
        refus=len(refus),
        alias=len(alias),
        pannes=sum(1 for d in lignes if d.erreur),
    )


def phase_faq(db) -> None:
    """La FAQ n'a aucun relecteur : elle doit cacher ce que le garde suspend.

    Les deux canoniques sont rendues visibles en FAQ ici — sans quoi le filtre
    `faq_visible` masquerait tout et la mesure passerait à vide, ce qui ne dirait
    rien du miroir SQL de `peut_servir_sans_revue` qu'on vient éprouver.
    """
    titre("PHASE 9 — la FAQ, page sans relecteur")
    from app.services.faq import rechercher_faq

    etat = lire_etat()
    generale, specifique = etat.get("generale"), etat.get("specifique")
    db.expire_all()
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    s = db.query(Reponse).filter(Reponse.id == uuid.UUID(specifique)).first()
    for r in (g, s):
        r.faq_visible = True
    db.commit()
    print(f"  générale a_relire={g.a_relire} | spécifique a_relire={s.a_relire}", flush=True)

    def chercher(q: str) -> tuple[list[str], list[str]]:
        res = rechercher_faq(db, q, settings.faq_max_resultats)
        ids = [str(r["reponse_id"]) for r in res.get("resultats") or []]
        inc = [str(r["reponse_id"]) for r in res.get("incertains") or []]
        print(
            f"  « {extrait(q, 60)} »\n    résultats={[i[:8] for i in ids]} incertains={[i[:8] for i in inc]}",
            flush=True,
        )
        return ids, inc

    ids_s, inc_s = chercher(S_SONDE)
    ids_g, inc_g = chercher(G_SONDE2)

    if g.a_relire:
        constat(
            generale not in ids_s + inc_s + ids_g + inc_g,
            "la FAQ masque la canonique signalée à relire (miroir SQL de peut_servir_sans_revue)",
            "une page sans relecteur ne peut pas montrer ce que le pipeline n'ose plus servir sans revue",
        )
    else:
        constat(True, "canonique générale non signalée — rien à masquer côté FAQ", "a_relire=False")
    constat(
        specifique in ids_s + inc_s,
        "la FAQ expose la canonique spécifique sur la question spécifique",
        f"résultats={[i[:8] for i in ids_s]} incertains={[i[:8] for i in inc_s]}",
    )


def phase_suivi(db) -> None:
    """Le mode suivi, jamais exercé par les phases 1-9 (mesuré : 0 réponse de suivi).

    Deux raisons de le mesurer à part. D'abord le garde y reçoit un **prompt
    différent** (`_PROMPT_SYSTEME_SUIVI`) et une requête différente — le fil
    entier concaténé, pas la dernière ligne : sans ça il compare deux questions
    empilées à une seule et refuse par artefact de format, mesuré à 5 refus sur
    5. Ensuite C4 vient de changer ce qu'un refus *fait* : il part désormais au
    RAG. L'interaction des deux n'avait jamais tourné.

    Chaque passe ouvre **son propre fil** : rejouer la précision dans le même
    ticket ferait lire à la passe 2 la réponse de la passe 1, et on mesurerait
    l'historique au lieu du mécanisme.
    """
    titre("PHASE 10 — mode suivi : le fil, le garde et C4")

    obs, fils = [], []
    for n in range(1, PASSES + 1):
        print(f"\n  ── fil {n}/{PASSES} ─────────────────────────────", flush=True)
        ouverture = demander(db, G_FIL)
        if ouverture.get("erreur") or not ouverture.get("ticket_id"):
            constat(False, "le fil s'ouvre", f"passe {n} : {ouverture.get('erreur')}")
            continue
        fils.append(ouverture)
        obs.append(demander_suivi(db, ouverture["ticket_id"], S_FIL))

    journal(phase="suivi", ouverture=G_FIL, precision=S_FIL, fils=fils, passes=obs)
    abouties = [o for o in obs if o.get("contenu")]

    constat(
        len(abouties) == PASSES and all(o["est_suivi"] for o in abouties),
        f"la précision est bien traitée en mode suivi, {len(abouties)}/{PASSES}",
        f"question_suivi renseignée sur {sum(1 for o in abouties if o['est_suivi'])} réponse(s)",
    )
    # Le fait mesurable qui distingue « le garde a vu le fil » de « le garde a vu
    # la dernière ligne » : la question soumise doit porter les deux tours.
    juges = [o for o in abouties if o.get("garde")]
    if juges:
        entiers = [
            o
            for o in juges
            if G_FIL.lower() in (o["garde"]["question_posee"] or "").lower()
            and S_FIL.lower() in (o["garde"]["question_posee"] or "").lower()
        ]
        constat(
            len(entiers) == len(juges),
            "le garde reçoit le FIL ENTIER, pas la seule précision",
            f"{len(entiers)}/{len(juges)} paires soumises portent l'ouverture ET la précision",
        )
        constat(
            not any(o["garde"]["court_circuit"] for o in juges),
            "aucun court-circuit typographique en suivi (désactivé par conception)",
            f"court-circuits={sum(1 for o in juges if o['garde']['court_circuit'])}/{len(juges)}",
        )
    else:
        print("\n  aucun appel au garde sur ce fil — aucun candidat n'a franchi le rappel.", flush=True)

    constat(
        bool(abouties) and all(dit(o["contenu"], "45") for o in abouties),
        f"INVARIANT : « et à l'étranger ? » reçoit bien 45 €, {len(abouties)}/{PASSES}",
        f"branches={[o['branche'] for o in abouties]} "
        f"gardes={[('—' if not o.get('garde') else ('OUI' if o['garde']['verdict'] else 'NON')) for o in abouties]}",
    )
    # Un refus en suivi est légitime ; ce qui ne l'est pas, c'est qu'il débouche
    # sur la règle générale servie à une question qui porte la précision.
    refus = [o for o in abouties if o.get("garde") and not o["garde"]["verdict"] and not o["garde"]["erreur"]]
    constat(
        all(dit(o["contenu"], "45") for o in refus),
        "C4 en suivi : un refus jugé repart au RAG et la réponse reste juste",
        f"{len(refus)} refus jugé(s), tous suivis d'une réponse à 45 €",
    )


def phase_maj(db) -> None:
    """Remplacer doc B par une v2 — le seul chemin qui peut **détruire**.

    Les phases 1-9 n'exercent que la confrontation, qui ne se déclenche qu'à une
    *première* ingestion et plafonne structurellement à `a_relire` (rien ne cite
    un document neuf). Ici la canonique spécifique cite bel et bien doc B
    (vérifié en ouverture de phase), donc `decider` peut cette fois appeler
    `retirer_du_service` : c'est le seul endroit de la campagne où une réponse
    peut devenir obsolète.

    Le montant passe de 45 € à 60 € et **rien d'autre ne bouge** : le diff se
    réduit à une réécriture de paragraphe, et « la réponse servie dit encore
    45 € » devient une erreur lisible par la machine.

    L'étage HTTP aperçu/confirmation est délibérément court-circuité — c'est de
    la plomberie d'IHM. Ce qui est mesuré ici est le pipeline : diff, ré-index,
    mise sous analyse, `reverification_job`, et ce que le verdict applique.
    """
    titre("PHASE 11 — doc B passe en v2 : mise à jour et retrait du service")
    from app.models.document_version import DocumentVersion
    from app.services.document_service import prochaine_version
    from app.workers.document_update import document_update_job

    etat = lire_etat()
    doc_b, specifique = etat.get("doc_B"), etat.get("specifique")
    if not doc_b or not specifique:
        constat(False, "doc B et la canonique spécifique existent", "phases 4 et 6 non jouées")
        sys.exit(1)

    db.expire_all()
    s0 = db.query(Reponse).filter(Reponse.id == uuid.UUID(specifique)).first()
    cite = db.query(ReponseChunk).filter(ReponseChunk.reponse_id == s0.id, ReponseChunk.doc_id == doc_b).count()
    constat(
        cite > 0,
        "la canonique spécifique CITE doc B — le retrait sec est donc atteignable",
        f"{cite} chunk(s) cité(s) ; sans ça la phase ne mesurerait que le plafond a_relire",
    )
    print(
        f"  avant : spécifique={str(s0.id)[:8]} canonique={s0.canonique} obsolete={s0.obsolete} "
        f"a_relire={s0.a_relire} nb_val={s0.nb_validations}",
        flush=True,
    )

    filename, contenu, description = DOC_B_V2
    dossier = os.environ.get("UPLOAD_DIR", "/app/uploads_tmp")
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"{uuid.uuid4()}_{filename}")
    octets = contenu.encode()
    with open(chemin, "wb") as f:
        f.write(octets)

    doc = db.query(Document).filter(Document.doc_id == doc_b).first()
    empreinte = hashlib.sha256(octets).hexdigest()

    # Rejouable : une fois la v2 en place, on ne repart pas pour une v3 — on
    # remesure. Sans ça, relancer la phase après un incident de harnais
    # fabriquerait une version de plus à chaque essai.
    if doc.content_hash == empreinte:
        cible = doc.version
        print(f"  doc B est déjà en v{cible} avec ce contenu — on remesure sans réingérer", flush=True)
    else:
        cible = prochaine_version(db, doc)
        doc.statut = "EN_MAJ"
        doc.update_started_at = datetime.now(timezone.utc)
        db.commit()
        print(f"  doc B → v{cible} : 45 € devient 60 €, le reste du texte est inchangé", flush=True)

        document_update_job.apply_async(
            kwargs={
                "doc_id": doc_b,
                "new_version": cible,
                "file_path": chemin,
                "filename": filename,
                "description": description,
                "content_hash": empreinte,
                "uploaded_by": None,
            },
            queue="queue_ingestion",
        )

        def en_place():
            db.expire_all()
            d = db.query(Document).filter(Document.doc_id == doc_b).first()
            return d if d and d.version == cible else None

        if attendre(en_place, 420, f"mise à jour en v{cible}") is None:
            constat(False, f"doc B est passé en v{cible}", "délai dépassé")
            sys.exit(1)
        attendre_confrontation(db)

    # ── ce que la mise à jour a produit ──
    chunks_v2 = [
        p.payload
        for p in points_qdrant()[0]
        if (p.payload or {}).get("doc_id") == doc_b and (p.payload or {}).get("version") == cible
    ]
    anciens = [
        p
        for p in points_qdrant()[0]
        if (p.payload or {}).get("doc_id") == doc_b and (p.payload or {}).get("version") != cible
    ]
    constat(
        bool(chunks_v2) and not anciens and all(c.get("contexte") for c in chunks_v2),
        f"v{cible} indexée et contextualisée, v{cible - 1} désindexée",
        f"chunks v{cible}={len(chunks_v2)} résidus anciens={len(anciens)}",
    )

    version = (
        db.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_b, DocumentVersion.version == cible - 1).first()
    )
    unites = (version.changements or {}).get("nb_unites") if version else None
    constat(
        bool(unites),
        "le diff est calculé et figé sur la version sortante",
        f"nb_unites={unites} (zéro unité ⇒ rien n'est enfilé, et le reste ne mesurerait rien)",
    )

    db.expire_all()
    s = db.query(Reponse).filter(Reponse.id == uuid.UUID(specifique)).first()
    pts = [p for p in points_qdrant()[1] if (p.payload or {}).get("reponse_id") == specifique]
    print(
        f"  après : obsolete={s.obsolete} ({s.obsolete_raison}) a_relire={s.a_relire} ({s.a_relire_raison}) "
        f"canonique={s.canonique} points Qdrant={len(pts)}",
        flush=True,
    )
    constat(
        s.obsolete or s.a_relire,
        "la canonique spécifique ne peut plus être servie sans revue",
        f"obsolete={s.obsolete} a_relire={s.a_relire} — l'un des deux suffit, l'invariant porte sur le service",
    )
    # Le piège documenté : supprimer par id de point laisserait la réponse
    # servable depuis ses alias, et le retrait serait silencieusement sans effet.
    if s.obsolete:
        constat(
            not pts,
            "retrait effectif : plus AUCUN point Qdrant sous ce reponse_id, alias compris",
            f"points restants={len(pts)}",
        )
    else:
        print("  (pas de retrait sec : le verdict n'a pas conclu à une contradiction)", flush=True)

    reste = (
        db.query(Reponse)
        .join(Ticket, Reponse.ticket_id == Ticket.id)
        .filter(Ticket.domaine == DOMAINE, Reponse.a_relire_raison == "ANALYSE_EN_COURS")
        .count()
    )
    constat(reste == 0, "aucune réponse laissée en « analyse en cours »", f"restantes={reste}")

    # ── la mesure qui tranche : l'ancien montant ne doit plus jamais sortir ──
    obs = sonder(db, S_SONDE)
    constat(
        all(not dit(o["contenu"], "45") for o in obs),
        f"INVARIANT : l'ancien montant (45 €) n'est plus jamais servi, {PASSES}/{PASSES}",
        f"branches={[o['branche'] for o in obs]}",
    )
    constat(
        all(dit(o["contenu"], "60") for o in obs),
        f"la question spécifique reçoit le NOUVEAU montant (60 €), {PASSES}/{PASSES}",
        f"sources={[str(o['reponse_source_id'])[:8] for o in obs]}",
    )

    # ── trouvaille du 18/09/2026, corrigée depuis ──
    # Cette phase a montré que `decider` (branche INTACTE) levait le drapeau dès
    # que `a_relire_doc_id == doc_id`, **sans regarder pourquoi il avait été
    # posé** : le `CONTREDITE_PROBABLE` soulevé par la confrontation de doc B v1
    # (« incomplète, elle omet l'exception ») était effacé par la ré-vérification
    # de la v2, qui ne juge que le diff 45 → 60 et n'a jamais instruit ce motif.
    # La générale redevenait servable sans revue en omettant toujours l'exception.
    # `decider` exige désormais aussi `a_relire_version == version` : on ne lève
    # que le drapeau qu'on a soi-même posé. **La propriété est assertée par la
    # phase 12**, qui rejoue la séquence à la v3 ; on se contente ici de rendre
    # l'état visible, la phase 11 étant rejouable sans relancer de verdict.
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(etat.get("generale"))).first()
    print(
        f"\n  générale {str(g.id)[:8]} : a_relire={g.a_relire} ({g.a_relire_raison}) "
        f"version={g.a_relire_version} obsolete={g.obsolete} canonique={g.canonique}",
        flush=True,
    )
    journal(
        phase="maj",
        doc_b=doc_b,
        version=cible,
        nb_unites=unites,
        specifique_obsolete=bool(s.obsolete),
        specifique_raison=s.obsolete_raison or s.a_relire_raison,
        points_restants=len(pts),
        generale_a_relire=bool(g.a_relire),
    )


def phase_drapeau(db) -> None:
    """Un verdict ne lève que le drapeau qu'il a lui-même posé.

    Trouvaille de la phase 11, corrigée le 18/09/2026 dans `decider` : la branche
    INTACTE effaçait tout signalement portant le même `doc_id`, quelle que soit la
    passe qui l'avait posé. La confrontation à l'arrivée de doc B v1 avait signalé
    la générale « incomplète, elle omet l'exception » ; la ré-vérification de doc B
    v2, qui ne juge que le diff 45 → 60, l'a trouvée INTACTE **à raison** et a
    effacé au passage un motif qu'elle n'avait jamais examiné. La générale est
    redevenue servable sans revue en omettant toujours l'exception.

    On rejoue la séquence à la v3, et c'est la **seconde** propriété qui compte le
    plus : le drapeau de la v1 doit survivre à un INTACTE de la v3, **et**
    `ANALYSE_EN_COURS` doit continuer de se résoudre. Si un appelant posait ce
    drapeau transitoire avec une version autre que celle qu'il repasse à
    `decider`, la condition ajoutée le laisserait collé — une réponse gelée « en
    analyse » pour toujours, bien pire que le défaut corrigé. Lecture du code dit
    que les deux appelants sont cohérents ; seule la mesure le montre.
    """
    titre("PHASE 12 — un verdict ne lève que le drapeau qu'il a posé")
    from app.models.document_version import DocumentVersion
    from app.services.diff import deserialiser_unites
    from app.services.document_service import prochaine_version
    from app.services.obsolescence import RAISON_CONTREDITE_PROB, poser_a_relire
    from app.services.question_pipeline import peut_servir_sans_revue
    from app.services.reverification_candidates import rassembler_candidates
    from app.workers.document_update import document_update_job

    etat = lire_etat()
    doc_b, generale = etat.get("doc_B"), etat.get("generale")
    if not doc_b or not generale:
        constat(False, "doc B et la canonique générale existent", "phases 1-6 non jouées")
        sys.exit(1)

    # Restaurer le drapeau que la confrontation avait réellement posé, et que la
    # ré-vérification de la v2 a effacé avant le correctif. Par la fonction du
    # pipeline, au nom de doc B **v1**, avec le motif rendu par le juge ce jour-là.
    db.expire_all()
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    if not g.a_relire:
        famille = [g] + db.query(Reponse).filter(Reponse.reponse_source_id == g.id).all()
        poser_a_relire(famille, RAISON_CONTREDITE_PROB, doc_b, 1)
        g.analyse_justification = JUSTIF_CONFRONTATION
        db.commit()
        print(f"  drapeau de la confrontation restauré sur {str(g.id)[:8]} (doc B v1)", flush=True)
    db.expire_all()
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    constat(
        bool(g.a_relire) and g.a_relire_doc_id == doc_b and g.a_relire_version == 1,
        "état de départ : la générale est signalée au nom de doc B v1",
        f"a_relire={g.a_relire} raison={g.a_relire_raison} version={g.a_relire_version}",
    )
    print(f"  la générale à surveiller est {g.id} (verdict lisible dans les logs worker_questions)", flush=True)

    # ── sans citante validée, le job ne part même pas ──
    # `document_update_job` n'enfile `reverification_job` que `if nb_a_analyser:`,
    # et ce compte ne recense que les **citantes** non obsolètes. Après la phase
    # 11, doc B n'en avait plus aucune : la première écriture de cette phase a
    # poussé une v3 avec « 0 à analyser », aucun verdict n'a été rendu, et les six
    # constats sont passés **à vide** en affichant du vert. D'où ce garde-fou en
    # tête, et les constats de non-vacuité plus bas.
    def citantes() -> list[Reponse]:
        ids = {rc.reponse_id for rc in db.query(ReponseChunk).filter(ReponseChunk.doc_id == doc_b).all()}
        return [
            r
            for r in db.query(Reponse).filter(Reponse.id.in_(ids)).all()
            if not r.obsolete and r.statut in ("VALIDÉE", "CORRIGÉE")
        ]

    if not citantes():
        print("  aucune citante validée — on en fabrique une par le chemin normal (RAG puis validation)", flush=True)
        obs = demander(db, S_SONDE)
        valider(db, obs["reponse_id"])
        db.expire_all()
    vivantes = citantes()
    constat(
        bool(vivantes),
        "une citante validée existe : la ré-vérification aura de quoi partir",
        f"citantes={[str(r.id)[:8] for r in vivantes]} — sans elle `nb_a_analyser` vaut 0 "
        f"et le job n'est jamais enfilé, ce qui rend toute la phase muette",
    )

    doc = db.query(Document).filter(Document.doc_id == doc_b).first()
    cible = prochaine_version(db, doc)
    filename, contenu, description = doc_b_variante(cible)
    dossier = os.environ.get("UPLOAD_DIR", "/app/uploads_tmp")
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, f"{uuid.uuid4()}_{filename}")
    octets = contenu.encode()
    with open(chemin, "wb") as f:
        f.write(octets)

    empreinte = hashlib.sha256(octets).hexdigest()
    doc.statut = "EN_MAJ"
    doc.update_started_at = datetime.now(timezone.utc)
    db.commit()
    print(f"  doc B → v{cible} : aucun montant ne bouge, la portée du plafond est précisée", flush=True)

    document_update_job.apply_async(
        kwargs={
            "doc_id": doc_b,
            "new_version": cible,
            "file_path": chemin,
            "filename": filename,
            "description": description,
            "content_hash": empreinte,
            "uploaded_by": None,
        },
        queue="queue_ingestion",
    )

    def en_place():
        db.expire_all()
        d = db.query(Document).filter(Document.doc_id == doc_b).first()
        return d if d and d.version == cible else None

    if attendre(en_place, 420, f"mise à jour en v{cible}") is None:
        constat(False, f"doc B est passé en v{cible}", "délai dépassé")
        sys.exit(1)
    attendre_confrontation(db)

    version = (
        db.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_b, DocumentVersion.version == cible - 1).first()
    )
    unites = deserialiser_unites(version.changements if version else None)
    constat(
        bool(unites),
        f"le diff v{cible - 1}→v{cible} existe : il y a de quoi juger",
        f"nb_unites={len(unites)} (zéro unité ⇒ rien n'est enfilé, et la phase passerait à vide)",
    )

    # ── non-vacuité : la générale a-t-elle seulement été soumise au juge ? ──
    # `rassembler_candidates` est rejoué ici sur le diff figé. S'il ne remonte pas
    # la générale, aucun verdict ne la concernait et « son drapeau a survécu » ne
    # dit rien. Coût : les embeddings des unités, pas d'appel au juge.
    candidates = rassembler_candidates(db, doc_b, DOMAINE, unites, set())
    vus = {str(c.reponse.id) for c in candidates}
    constat(
        generale in vus,
        "la générale faisait bien partie des candidates soumises au verdict",
        f"candidates={[str(c.reponse.id)[:8] for c in candidates]} — sinon le constat suivant "
        f"serait vrai par absence de juge, pas par correctif",
    )

    # ── la mesure qui tranche ──
    db.expire_all()
    g = db.query(Reponse).filter(Reponse.id == uuid.UUID(generale)).first()
    print(
        f"  après v{cible} : générale a_relire={g.a_relire} ({g.a_relire_raison}) "
        f"version={g.a_relire_version} obsolete={g.obsolete} canonique={g.canonique}",
        flush=True,
    )
    constat(
        bool(g.a_relire) and g.a_relire_raison == RAISON_CONTREDITE_PROB and g.a_relire_version == 1,
        f"le motif posé à la v1 survit au verdict de la v{cible}",
        f"a_relire={g.a_relire} raison={g.a_relire_raison} version={g.a_relire_version} — "
        f"avant correctif : effacé parce que le doc_id suffisait",
    )
    constat(
        not peut_servir_sans_revue(g),
        "la générale reste donc hors du service sans revue, motif toujours ouvert",
        f"canonique={g.canonique} a_relire={g.a_relire} obsolete={g.obsolete}",
    )
    constat(
        (g.analyse_justification or "") == JUSTIF_CONFRONTATION,
        "et la justification d'origine n'a pas été effacée avec le drapeau",
        f"justification={extrait(g.analyse_justification, 90)!r}",
    )

    # Le risque du correctif, et la seule chose qu'un test unitaire ne montre pas :
    # que les deux appelants posent bien `ANALYSE_EN_COURS` avec la version qu'ils
    # repassent à `decider`. Sinon l'état transitoire ne se résoudrait plus.
    reste = (
        db.query(Reponse)
        .join(Ticket, Reponse.ticket_id == Ticket.id)
        .filter(Ticket.domaine == DOMAINE, Reponse.a_relire_raison == "ANALYSE_EN_COURS")
        .count()
    )
    constat(
        reste == 0,
        "aucune réponse gelée en « analyse en cours » — l'état transitoire se résout toujours",
        f"restantes={reste} ; c'est le risque propre au correctif, pas au défaut corrigé",
    )

    journal(
        phase="drapeau",
        doc_b=doc_b,
        version=cible,
        nb_unites=len(unites),
        candidates=[str(c.reponse.id) for c in candidates],
        generale=str(g.id),
        generale_a_relire=bool(g.a_relire),
        generale_raison=g.a_relire_raison,
        generale_version=g.a_relire_version,
        analyses_restantes=reste,
    )


# ── bilan ───────────────────────────────────────────────────────────────


def bilan() -> int:
    titre("BILAN")
    echecs = [c for c in CONSTATS if not c[0]]
    for ok, libelle, _detail in CONSTATS:
        marque = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {marque} {libelle}")
    print(f"\n  \033[1m{len(CONSTATS) - len(echecs)}/{len(CONSTATS)} constats tenus\033[0m", flush=True)
    journal(
        phase="bilan",
        tenus=len(CONSTATS) - len(echecs),
        total=len(CONSTATS),
        echecs=[{"libelle": c[1], "detail": c[2]} for c in echecs],
    )
    return 1 if echecs else 0


PHASES = {
    "1": phase_1,
    "2": phase_2,
    "3": phase_3,
    "4": phase_4,
    "5": phase_5,
    "6": phase_6,
    "7": phase_7,
    "8": phase_8,
    "9": phase_faq,
    "10": phase_suivi,
    "11": phase_maj,
    "12": phase_drapeau,
}
# 10 avant 11, et pas l'inverse : la phase 11 fait passer le montant de
# référence de 45 € à 60 €, ce qui invaliderait l'attendu de la phase 10. La 12
# vient après la 11 : elle rejoue le drapeau que la 11 a vu s'effacer.
ORDRE = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, help="1..11, « tout », ou une liste « 4,5,6 »")
    parser.add_argument("--etat", action="store_true", help="affiche l'état du domaine et sort")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.etat:
            tableau_reponses(db)
            return 0

        if args.phase == "tout":
            demandees = list(ORDRE)
        else:
            demandees = [p.strip() for p in args.phase.split(",")]

        if "1" in demandees and not lire_etat().get("debut"):
            ecrire_etat(debut=datetime.now(timezone.utc).isoformat(), domaine=DOMAINE)

        for p in demandees:
            if p not in PHASES:
                print(f"phase inconnue : {p}", file=sys.stderr)
                return 2
            PHASES[p](db)

        tableau_reponses(db)
        return bilan()
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
