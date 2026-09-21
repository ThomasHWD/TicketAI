"""Juge les réponses déjà servies contre un document qui vient d'être ingéré. Sibling de reverification_job (même"""

import logging
import uuid

from app.database import SessionLocal
from app.models.document import Document
from app.models.reponse import Reponse
from app.services.broadcast import broadcast_sync
from app.services.confrontation import (
    contexte_source,
    familles_servies,
    identifiants,
    textes_chunks,
)
from app.services.diff import SENS_AJOUT, Unite
from app.services.obsolescence import (
    RAISON_INDISPONIBLE,
    RAISON_NOUVEAU_DOC,
    RAISON_PARTIELLE,
    racines,
)
from app.services.reverification import (
    ACTION_A_RELIRE,
    ACTION_INTACTE,
    ACTION_RETIREE,
    MAX_JUGEMENTS,
    VERDICT_INTACTE,
    Candidate,
    decider,
    juger_confrontation,
    questions_des_reponses,
    signaler_sans_juger,
    unites_pertinentes,
)
from app.workers.celery_app import celery_app
from app.workers.reverification import (
    JUSTIF_PANNE,
    JUSTIF_PARTIELLE,
    MAX_ECHECS,
    publier_bilan,
    rabattre,
)

logger = logging.getLogger(__name__)

JUSTIF_SANS_TEXTE = "Les passages du nouveau document n'ont pas pu être relus : réponse signalée par précaution."


class TacheConfrontation(celery_app.Task):
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
    name="confrontation_job",
    base=TacheConfrontation,
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    queue="queue_questions",
)
def confrontation_job(
    self,
    doc_id: str,
    version: int,
    domaine: str,
    cibles: dict[str, list[int]],
):
    """Confronte chaque réponse visée aux chunks du document qui l'ont appariée. `cibles` travels through the broker"""
    logger.info("confrontation : doc %s v%d, %d réponse(s) visée(s)", doc_id, version, len(cibles or {}))
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None or doc.version != version:
            # document replaced or deleted — update job covers its own scope
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            logger.info("version dépassée — abandon, %d réponse(s) rabattues", nb)
            return {"statut": "DEPASSE", "doc_id": doc_id, "version": version}

        tous_indices = {i for indices in (cibles or {}).values() for i in indices}
        textes = textes_chunks(doc_id, version, tous_indices)
        if not textes:
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_SANS_TEXTE)
            logger.warning("aucun chunk relu — %d réponse(s) en relecture", nb)
            return publier_bilan(doc_id, version, domaine, {"nb_indisponibles": nb})

        candidates = _candidates(db, cibles)
        logger.info("%d chunk(s) relu(s), %d réponse(s) à examiner", len(textes), len(candidates))

        broadcast_sync(
            f"sse:domain:{domaine}",
            "reverification_started",
            {"doc_id": doc_id, "version": version, "nb_a_analyser": len(candidates)},
        )

        comptes = {ACTION_RETIREE: 0, ACTION_A_RELIRE: 0, ACTION_INTACTE: 0}
        nb_indisponibles = 0
        budget = MAX_JUGEMENTS
        echecs = 0

        for rang, (candidate, indices) in enumerate(candidates):
            if budget <= 0:
                nb_indisponibles += signaler_sans_juger(
                    db, [c for c, _ in candidates[rang:]], RAISON_PARTIELLE, JUSTIF_PARTIELLE, doc_id, version
                )
                logger.info("budget épuisé — %d réponse(s) en relecture", len(candidates) - rang)
                break

            unites = [Unite(SENS_AJOUT, None, textes[i]) for i in indices if textes.get(i)]
            if not unites:
                nb_indisponibles += signaler_sans_juger(
                    db, [candidate], RAISON_INDISPONIBLE, JUSTIF_SANS_TEXTE, doc_id, version
                )
                continue

            pertinentes, fiable = unites_pertinentes(candidate.question, unites)
            if fiable and not pertinentes:
                comptes[decider(db, candidate, VERDICT_INTACTE, "", [], doc_id, version)] += 1
                continue

            budget -= 1
            try:
                verdict, justification = juger_confrontation(
                    candidate.question,
                    candidate.texte,
                    pertinentes,
                    contexte_source(db, candidate.reponse),
                )
            except Exception as exc:
                echecs += 1
                logger.error("jugement impossible (%s)", exc)
                reste = [c for c, _ in candidates[rang:]] if echecs >= MAX_ECHECS else [candidate]
                nb_indisponibles += signaler_sans_juger(db, reste, RAISON_INDISPONIBLE, JUSTIF_PANNE, doc_id, version)
                if echecs >= MAX_ECHECS:
                    logger.error("Albert injoignable — %d réponse(s) en relecture", len(reste))
                    break
                continue

            echecs = 0
            action = decider(
                db, candidate, verdict, justification, pertinentes, doc_id, version,
                raison_incertain=RAISON_NOUVEAU_DOC,
            )
            comptes[action] += 1
            logger.info("%s → %s (%s)", candidate.reponse.id, verdict, action)

        # safety net: a response flagged at ingestion but absent from candidates would stay stuck otherwise
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
        logger.error("erreur confrontation_job doc %s v%d : %s", doc_id, version, exc)
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


def _candidates(db, cibles: dict[str, list[int]]) -> list[tuple[Candidate, list[int]]]:
    """Les réponses visées, chacune avec les indices de chunks qui l'ont appariée. `citante=False` by construction"""
    par_id = {str(k): v for k, v in cibles.items()}
    servies = familles_servies(db, identifiants(cibles))
    distinctes = racines(servies)
    questions = questions_des_reponses(db, distinctes)

    couples = [
        (
            Candidate(reponse=r, question=questions.get(r.id, ""), citante=False, prioritaire=False),
            _indices(par_id, r),
        )
        for r in distinctes
    ]
    couples = [(c, indices) for c, indices in couples if indices]
    couples.sort(key=lambda couple: (couple[0].reponse.canonique, couple[0].reponse.nb_validations or 0), reverse=True)
    return couples


def _indices(par_id: dict[str, list[int]], reponse: Reponse) -> list[int]:
    """Chunks appariés à cette réponse, ou à sa source (qui holds the Qdrant points when a copy was retained by"""
    indices = set(par_id.get(str(reponse.id), []))
    source: uuid.UUID | None = reponse.reponse_source_id
    if source is not None:
        indices |= set(par_id.get(str(source), []))
    return sorted(indices)
