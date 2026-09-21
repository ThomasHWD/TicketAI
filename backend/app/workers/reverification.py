"""Reverification worker: runs after document_update_job, on queue_questions (Albert network waits, not ingestion"""

import logging

from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.reponse import Reponse
from app.services.broadcast import broadcast_sync
from app.services.obsolescence import (
    RAISON_ANALYSE,
    RAISON_INDISPONIBLE,
    RAISON_MASSIVE,
    RAISON_PARTIELLE,
    Unite,
    deserialiser_unites,
    marquer_a_relire,
    poser_a_relire,
    racines,
)
from app.services.reverification import (
    ACTION_A_RELIRE,
    ACTION_INTACTE,
    ACTION_RETIREE,
    MAX_JUGEMENTS,
    MAX_UNITES,
    MAX_UNITES_PAR_REPONSE,
    VERDICT_INTACTE,
    decider,
    juger,
    rassembler_candidates,
    signaler_sans_juger,
    tracer,
    unites_pertinentes,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Above this threshold Albert is down — remaining candidates go to human review immediately rather than burning 60 s
MAX_ECHECS = 3

JUSTIF_PANNE = "Le service d'analyse n'a pas répondu : la réponse n'est plus servie sans revue, à vérifier à la main."
JUSTIF_PARTIELLE = "Budget d'analyse épuisé pour cette mise à jour : aucun verdict rendu sur cette réponse."
JUSTIF_MASSIVE = "Document réécrit en profondeur : trop de changements pour juger réponse par réponse."


def unites_figees(db, doc_id: str, version: int) -> list[Unite]:
    """Units from the stored version, not recomputed — archive may be purged, and the human confirmed this diff."""
    ligne = (
        db.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == version).first()
    )
    return deserialiser_unites(ligne.changements if ligne else None)


def restees_en_analyse(db, doc_id: str, version: int) -> list[Reponse]:
    return (
        db.query(Reponse)
        .filter(
            Reponse.a_relire.is_(True),
            Reponse.a_relire_raison == RAISON_ANALYSE,
            Reponse.a_relire_doc_id == doc_id,
            Reponse.a_relire_version == version,
        )
        .all()
    )


def rabattre(db, doc_id: str, version: int, raison: str, justification: str) -> int:
    """Requalify lingering ANALYSE_EN_COURS as explicit human review. A persistent transient state is a silent bug."""
    restes = restees_en_analyse(db, doc_id, version)
    if not restes:
        return 0

    poser_a_relire(restes, raison, doc_id, version)
    tracer(db, restes, justification, None)
    return len(racines(restes))


class TacheReverif(celery_app.Task):
    """Last-resort net: OOM-kill would leave responses stuck in ANALYSE_EN_COURS forever without this."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        doc_id, version = kwargs.get("doc_id"), kwargs.get("version")
        if not doc_id or version is None:
            return

        db = SessionLocal()
        try:
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            logger.error("échec définitif — %d réponse(s) rabattues en relecture", nb)
        except Exception as e:
            logger.error("rabattement impossible après échec : %s", e)
        finally:
            db.close()


@celery_app.task(
    name="reverification_job",
    base=TacheReverif,
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    queue="queue_questions",
)
def reverification_job(
    self,
    doc_id: str,
    version: int,
    domaine: str,
    indices_disparus: list[int] | None = None,
):
    """Judge each response in the batch. Convergent: already-obsolete responses skipped, upserts are idempotent."""
    logger.info("ré-vérification : doc %s v%d", doc_id, version)
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None or doc.version != version:
            # v(n+1) arrived while this was queued — judging a stale diff produces verdicts on text no longer served.
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            logger.info("version dépassée — abandon, %d réponse(s) rabattues", nb)
            return {"statut": "DEPASSE", "doc_id": doc_id, "version": version}

        unites = unites_figees(db, doc_id, version)

        if not unites:
            # document_update_job only enqueues with at least one unit — arriving here signals a truncated version row.
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            logger.warning("aucune unité relue — %d réponse(s) en relecture", nb)
            return publier_bilan(doc_id, version, domaine, {"nb_indisponibles": nb})

        if len(unites) > MAX_UNITES:
            # rewritten not modified — no model call would discriminate.
            touchees = marquer_a_relire(db, doc_id, version, RAISON_MASSIVE)
            tracer(db, touchees, JUSTIF_MASSIVE, None)
            nb = len(racines(touchees))
            logger.info("%d unités (> %d) — %d réponse(s) en relecture, 0 appel LLM", len(unites), MAX_UNITES, nb)
            return publier_bilan(doc_id, version, domaine, {"nb_a_relire": nb})

        candidates = rassembler_candidates(db, doc_id, domaine, unites, set(indices_disparus or []))
        logger.info("%d unité(s), %d réponse(s) à examiner", len(unites), len(candidates))

        broadcast_sync(
            f"sse:domain:{domaine}",
            "reverification_started",
            {"doc_id": doc_id, "version": version, "nb_a_analyser": len(candidates)},
        )

        comptes = {ACTION_RETIREE: 0, ACTION_A_RELIRE: 0, ACTION_INTACTE: 0}
        nb_indisponibles = 0
        budget = MAX_JUGEMENTS
        echecs = 0

        for rang, candidate in enumerate(candidates):
            if budget <= 0:
                # surplus goes to human review — truncation is never silent.
                nb_indisponibles += signaler_sans_juger(
                    db, candidates[rang:], RAISON_PARTIELLE, JUSTIF_PARTIELLE, doc_id, version
                )
                logger.info("budget épuisé — %d réponse(s) en relecture", len(candidates) - rang)
                break

            pertinentes, fiable = unites_pertinentes(candidate.question, unites)

            if candidate.prioritaire and not pertinentes:
                # cited passage disappeared — a fact, not a similarity guess; reranker can't override this signal.
                pertinentes = unites[:MAX_UNITES_PAR_REPONSE]

            if fiable and not pertinentes:
                # no changes touch this question — clear the transient flag without calling the model.
                comptes[decider(db, candidate, VERDICT_INTACTE, "", [], doc_id, version)] += 1
                continue

            budget -= 1
            try:
                verdict, justification = juger(candidate.question, candidate.texte, pertinentes)
            except Exception as exc:
                echecs += 1
                logger.error("jugement impossible (%s)", exc)
                reste = candidates[rang:] if echecs >= MAX_ECHECS else [candidate]
                nb_indisponibles += signaler_sans_juger(db, reste, RAISON_INDISPONIBLE, JUSTIF_PANNE, doc_id, version)
                if echecs >= MAX_ECHECS:
                    logger.error("Albert injoignable — %d réponse(s) en relecture", len(reste))
                    break
                continue

            echecs = 0
            action = decider(db, candidate, verdict, justification, pertinentes, doc_id, version)
            comptes[action] += 1
            logger.info("%s → %s (%s)", candidate.reponse.id, verdict, action)

        # safety net: a response flagged by document_update but absent from candidates would stay stuck otherwise.
        nb_indisponibles += rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)

        return publier_bilan(
            doc_id,
            version,
            domaine,
            {
                "nb_contredites": comptes[ACTION_RETIREE],
                "nb_a_relire": comptes[ACTION_A_RELIRE],
                "nb_intactes": comptes[ACTION_INTACTE],
                "nb_indisponibles": nb_indisponibles,
            },
        )

    except Exception as exc:
        logger.error("erreur reverification_job doc %s v%d : %s", doc_id, version, exc)
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


def publier_bilan(doc_id: str, version: int, domaine: str, comptes: dict) -> dict:
    """Broadcast results and return to Celery. sse:admin is separate from the domain event — admin's saved-answers"""
    bilan = {
        "nb_contredites": 0,
        "nb_a_relire": 0,
        "nb_intactes": 0,
        "nb_indisponibles": 0,
        **comptes,
    }
    logger.info(
        "%d retirée(s), %d à relire, %d intacte(s), %d non jugée(s)",
        bilan["nb_contredites"], bilan["nb_a_relire"], bilan["nb_intactes"], bilan["nb_indisponibles"],
    )

    broadcast_sync(
        f"sse:domain:{domaine}",
        "reverification_done",
        {"doc_id": doc_id, "version": version, **bilan},
    )
    broadcast_sync("sse:admin", "saved_answers_updated", {"doc_id": doc_id, "version": version})

    return {"statut": "OK", "doc_id": doc_id, "version": version, **bilan}
