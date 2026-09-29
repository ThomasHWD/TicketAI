"""Re-examination after a document deletion. A response cites the five reranked passages it was generated from, used
or not — deleting any of their documents withdrew it (29/09/2026: removing the télétravail note withdrew the vélo
canonical, which never relied on it). Withdrawal stays immediate and total; this only decides, afterwards, which
responses go back into service. Anything but an explicit « fully supported by what remains » keeps them withdrawn."""

import logging
import uuid

from app.config import settings
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.confrontation import textes_chunks
from app.services.document_service import STATUTS_VIVANTS
from app.services.llm import chat
from app.services.obsolescence import fermeture_copies, racines, reponses_obsoletes
from app.services.reverification_candidates import passages_actuels
from app.services.reverification_scoring import VERDICT_INCERTAIN, _lire_verdict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

VERDICT_SOUTENUE = "SOUTENUE"
VERDICT_DEPENDANTE = "DEPENDANTE"
VERDICTS_RETRAIT = (VERDICT_SOUTENUE, VERDICT_DEPENDANTE, VERDICT_INCERTAIN)

# One model call per distinct response — a heavily cited document must not drain the judge's daily counter (shared
# with the cache guard). Beyond this, responses simply stay withdrawn, as before this re-examination existed.
MAX_REEXAMENS = 100

PROMPT_RETRAIT = """Tu vérifies si une réponse déjà publiée peut rester en service après la suppression d'un
document de référence.

On te donne la question posée, la réponse telle qu'elle était servie, les passages du document SUPPRIMÉ qui
figuraient dans le contexte de cette réponse, et les passages RESTANTS, issus d'autres documents toujours en vigueur,
sur lesquels elle avait aussi été construite.

Rends exactement l'un de ces trois verdicts :
- SOUTENUE : chaque information de la réponse — chiffre, montant, délai, seuil, condition, population visée,
  interlocuteur, étape de procédure — figure explicitement dans les passages restants.
- DEPENDANTE : au moins une information de la réponse ne figure que dans les passages supprimés, ou ne figure
  nulle part dans les passages restants.
- INCERTAIN : les éléments fournis ne permettent pas de trancher.

Règles :
- Vérifie les informations de la réponse une à une contre les passages restants. Une information seulement
  plausible, déduite ou approchée n'est pas soutenue.
- Qu'un passage supprimé traite du même sujet ne rend pas la réponse DEPENDANTE : seule compte l'origine des
  informations qu'elle énonce.
- Ne rédige jamais de correction ni de réponse de remplacement.
- Dans le doute, réponds INCERTAIN et non SOUTENUE : une réponse remise en service sans sa source coûte plus cher
  qu'une restauration manuelle.

Réponds uniquement par un objet JSON, sans texte autour ni bloc de code :
{"verdict": "SOUTENUE|DEPENDANTE|INCERTAIN", "justification": "une phrase de 200 caractères maximum"}"""


def candidats_au_reexamen(db: Session, doc_id: str) -> list[Reponse]:
    """Roots that the deletion is about to withdraw, and that nothing else holds. Called BEFORE the withdrawal:
    `retirer_du_service` clears the review flags, and a family flagged by another pass must never come back
    through here — only a human lifts that flag."""
    touchees = reponses_obsoletes(db, doc_id)
    exclues: set[uuid.UUID] = set()
    for racine in racines(touchees):
        famille = fermeture_copies(db, {racine.id})
        if db.query(Reponse.id).filter(Reponse.id.in_(famille), Reponse.a_relire.is_(True)).first():
            exclues.add(racine.id)
    return [r for r in racines(touchees) if r.id not in exclues]


def passages_du_document(db: Session, reponse: Reponse, doc_id: str) -> list[str]:
    """Passages of `doc_id` in this response's context, read from Qdrant — before the deletion removes them."""
    lignes = (
        db.query(ReponseChunk.version, ReponseChunk.chunk_index)
        .filter(ReponseChunk.reponse_id == reponse.id, ReponseChunk.doc_id == doc_id)
        .all()
    )
    par_version: dict[int | None, set[int]] = {}
    for version, index in lignes:
        par_version.setdefault(version, set()).add(index)
    textes: list[str] = []
    for version, indices in par_version.items():
        if version is not None:
            textes.extend(t for t in textes_chunks(doc_id, version, indices).values() if t)
    return textes


def appuye_d_abord_sur(db: Session, reponse: Reponse, doc_id: str) -> bool:
    """The deleted document ranked first in this response's context — it surely relied on it, no call needed."""
    tete = (
        db.query(ReponseChunk.doc_id)
        .filter(ReponseChunk.reponse_id == reponse.id, ReponseChunk.rerank_score.isnot(None))
        .order_by(ReponseChunk.rerank_score.desc())
        .first()
    )
    return tete is not None and tete[0] == doc_id


def passages_restants(db: Session, reponse: Reponse, doc_id: str) -> list[dict]:
    """The other documents of its context, as they stand now: `[{doc_id, version, texte}]`. Read before the
    withdrawal — it deletes the response's own point, the query vector for updated documents.

    Updates never re-point citations, so a response still in service cites the version it was generated on. If
    that document moved on since, the response went through its re-verification and stayed unflagged: its current
    text is the source, read as the passages closest to the response's question (zero Albert calls)."""
    lignes = (
        db.query(ReponseChunk.doc_id, ReponseChunk.version, ReponseChunk.chunk_index)
        .filter(ReponseChunk.reponse_id == reponse.id, ReponseChunk.doc_id != doc_id)
        .all()
    )
    cites: dict[str, dict[int | None, set[int]]] = {}
    for autre, version, index in lignes:
        cites.setdefault(autre, {}).setdefault(version, set()).add(index)
    vivants = {
        d.doc_id: d.version
        for d in db.query(Document).filter(Document.doc_id.in_(cites), Document.statut.in_(STATUTS_VIVANTS)).all()
    }
    passages: list[dict] = []
    for autre, par_version in cites.items():
        actuelle = vivants.get(autre)
        if actuelle is None:
            continue  # deleted as well: not a source anymore
        if actuelle in par_version:
            textes = list(textes_chunks(autre, actuelle, par_version[actuelle]).values())
        else:
            textes = passages_actuels(reponse, autre, actuelle)
        passages.extend({"doc_id": autre, "version": actuelle, "texte": t} for t in textes if t)
    return passages


def encore_en_vigueur(db: Session, passages: list[dict]) -> list[str]:
    """Texts of the passages whose document is still live at that version — one may have been deleted since."""
    vivants = {
        (d.doc_id, d.version)
        for d in db.query(Document)
        .filter(Document.doc_id.in_({p["doc_id"] for p in passages}), Document.statut.in_(STATUTS_VIVANTS))
        .all()
    }
    return [p["texte"] for p in passages if (p["doc_id"], p["version"]) in vivants]


def question_de(db: Session, reponse: Reponse) -> str | None:
    if reponse.question_suivi:
        return reponse.question_autonome  # a bare follow-up (« et pour un apprenti ? ») is not a question
    ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
    return ticket.question if ticket else None


def juger_retrait(question: str, reponse_servie: str, retires: list[str], restants: list[str]) -> tuple[str, str]:
    messages = [
        {"role": "system", "content": PROMPT_RETRAIT},
        {
            "role": "user",
            "content": (
                f"Question posée :\n{question}\n\n"
                f"Réponse servie :\n{reponse_servie}\n\n"
                f"Passages du document SUPPRIMÉ :\n{chr(10).join(retires) or '(non disponibles)'}\n\n"
                f"Passages RESTANTS :\n" + "\n\n---\n\n".join(restants)
            ),
        },
    ]
    modele = settings.albert_reverif_model_name or settings.albert_llm_model_name
    return _lire_verdict(chat(messages, temperature=0, max_tokens=2048, timeout=60, model=modele), VERDICTS_RETRAIT)
