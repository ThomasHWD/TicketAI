"""Juge les réponses déjà servies contre un document qui vient d'être ingéré.

Enfilé par ``ingestion_job`` juste après le commit des lignes de document, sur
``queue_questions`` : comme la ré-vérification, ce job n'est que de l'attente
réseau Albert et n'a rien à faire dans la file qui sérialise les ingestions.

**Frère de ``reverification_job``, pas une réutilisation.** Le pipeline de
décision est le même à partir de l'étage 2 (``unites_pertinentes`` → ``juger`` →
``decider``) ; ce qui diffère est l'étage 1, et deux détails de
``reverification_job`` le rendaient inutilisable ici :

* il relit ses unités depuis ``DocumentVersion.changements`` et bascule en
  ``RAISON_MASSIVE`` au-delà de ``MAX_UNITES``. Sur un document neuf chaque
  paragraphe est un ajout : tout document d'un peu de volume dégénérerait en
  ``marquer_a_relire``, qui matche **zéro** réponse — rien ne cite un document
  neuf — et ne ferait donc rien, en silence ;
* ``rassembler_candidates`` → ``_voisines`` ré-embarque chaque unité chez
  Albert. L'ingestion vient de payer ces vecteurs ; l'appariement arrive donc
  tout fait, dans ``cibles``.

Le job démarre sur un lot déjà marqué ``ANALYSE_EN_COURS`` — posé dans le commit
de l'ingestion, pas ici, ce qui ferme la fenêtre de course. Ce drapeau est
transitoire et **le job a l'obligation de le résoudre** : trois filets s'en
assurent, le repli par réponse, le balayage final de ``rabattre``, et le
``on_failure``.

Ce que ce job ne fait **jamais** : rendre une réponse obsolète. ``decider`` ne
retire du service que sur ``CONTREDITE`` **et** ``citante``, et ``citante`` est
faux par construction ici (cf. ``services/confrontation.py``).
"""

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
    """Le filet de dernier recours, identique à celui de la ré-vérification.

    Sans lui, un worker tué net laisserait des réponses en « analyse en cours »
    indéfiniment : servies, marquées douteuses, et présentées à personne.
    """

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
    """Confronte chaque réponse visée aux chunks du document qui l'ont appariée.

    ``cibles`` est le ``{reponse_id: [chunk_index, …]}`` produit par
    ``cibles_confrontation`` à l'ingestion. Il transite par le broker plutôt
    qu'être recalculé ici : les vecteurs qui l'ont produit n'existent plus, et le
    refaire coûterait un ré-embedding complet du document.

    Convergent : ``familles_servies`` écarte ce qui est déjà obsolète, et un
    rejeu ne reprend que le reliquat encore en ``ANALYSE_EN_COURS``.
    """
    logger.info("confrontation : doc %s v%d, %d réponse(s) visée(s)", doc_id, version, len(cibles or {}))
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None or doc.version != version:
            # Le document a été remplacé ou supprimé entre-temps : `cibles`
            # désigne des chunks qui ne sont plus indexés, et la mise à jour porte
            # son propre job sur son propre périmètre.
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
                # Le surplus n'est jamais ignoré en silence — il part en relecture
                # avec sa raison, pour que la troncature soit visible.
                nb_indisponibles += signaler_sans_juger(
                    db, [c for c, _ in candidates[rang:]], RAISON_PARTIELLE, JUSTIF_PARTIELLE, doc_id, version
                )
                logger.info("budget épuisé — %d réponse(s) en relecture", len(candidates) - rang)
                break

            unites = [Unite(SENS_AJOUT, None, textes[i]) for i in indices if textes.get(i)]
            if not unites:
                # Les chunks appariés ont disparu de l'index depuis la détection.
                nb_indisponibles += signaler_sans_juger(
                    db, [candidate], RAISON_INDISPONIBLE, JUSTIF_SANS_TEXTE, doc_id, version
                )
                continue

            pertinentes, fiable = unites_pertinentes(candidate.question, unites)
            if fiable and not pertinentes:
                # Le nouveau document ne dit rien qui porte sur cette question :
                # rien à juger, et surtout rien à laisser en analyse.
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

        # Filet intermédiaire : une réponse flaguée à l'ingestion mais absente du
        # lot de candidates (validée puis rejetée entre-temps, famille recomposée)
        # resterait sinon en « analyse en cours » sans que rien ne la résolve.
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
    """Les réponses visées, chacune avec les indices de chunks qui l'ont appariée.

    ``citante=False`` n'est pas une convention d'écriture, c'est un fait : aucune
    réponse ne peut citer un document qui n'existait pas quand elle a été
    générée. C'est ce qui interdit structurellement le retrait sec sur ce chemin.

    Réduit aux ``racines`` pour la même raison que ``rassembler_candidates`` :
    une réponse réutilisée cinq fois coûterait sinon cinq jugements identiques.
    ``decider`` rouvre la famille au moment d'appliquer.

    Le tri dépense le budget sur les canoniques d'abord, puis sur les plus
    validées — c'est-à-dire les plus resservies, donc celles dont l'erreur se
    propage le plus.
    """
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
    """Les chunks appariés à cette réponse, ou à la copie qui l'a fait remonter.

    ``racines`` peut retenir une copie dont la source est hors ensemble, et c'est
    la *source* qui porte les points Qdrant : l'appariement est alors enregistré
    sous l'identifiant de la source. Sans ce repli, la copie arriverait sans
    aucun chunk et serait écartée du jugement.
    """
    indices = set(par_id.get(str(reponse.id), []))
    source: uuid.UUID | None = reponse.reponse_source_id
    if source is not None:
        indices |= set(par_id.get(str(source), []))
    return sorted(indices)
