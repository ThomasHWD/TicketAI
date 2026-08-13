"""Ré-vérifie, réponse par réponse, ce qu'une nouvelle version de document invalide.

Enfilé par ``document_update_job`` juste après la bascule de version, sur
``queue_questions`` : ce job n'est que de l'attente réseau Albert, il n'a rien à
faire dans la file qui sérialise les ingestions.

Le job démarre sur un lot de réponses déjà marquées ``ANALYSE_EN_COURS`` — le
drapeau est posé dans la foulée du commit de version, pas ici. C'est ce qui ferme
la fenêtre de course : entre la publication de la v2 et le verdict il s'écoule de
trente secondes à quelques minutes, pendant lesquelles les réponses continuent
d'être servies. Elles le sont, mais plus jamais sans que l'interface le dise.

Ce drapeau est un état transitoire, et **le job a l'obligation de le résoudre**
pour chacune des réponses qu'il a reçues : il le lève (``INTACTE``), l'aggrave en
obsolescence (``CONTREDITE`` sur une citante), ou le requalifie en une raison de
relecture explicite. Trois filets successifs garantissent qu'aucune réponse ne
reste coincée : le repli par réponse en cas de panne d'Albert, le balayage final
de ``rabattre``, et le ``on_failure`` de la tâche pour le worker tué net.

Toute la logique de décision vit dans ``services/reverification.py``, qui ne
connaît pas Celery et se teste sans broker. Ce module ne porte que la politique :
les plafonds, l'ordre de dépense du budget, les replis et les événements SSE.
"""

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

# Échecs d'appel au modèle consécutifs à partir desquels on considère Albert
# injoignable plutôt que capricieux. Insister coûterait un timeout de 60 s par
# candidate restante pour un résultat connu d'avance ; le reliquat part donc
# directement en relecture.
MAX_ECHECS = 3

JUSTIF_PANNE = "Le service d'analyse n'a pas répondu : la réponse reste servie, à vérifier à la main."
JUSTIF_PARTIELLE = "Budget d'analyse épuisé pour cette mise à jour : aucun verdict rendu sur cette réponse."
JUSTIF_MASSIVE = "Document réécrit en profondeur : trop de changements pour juger réponse par réponse."


def unites_figees(db, doc_id: str, version: int) -> list[Unite]:
    """Les unités de changement telles qu'elles ont été enregistrées sur la version.

    Relues et non recalculées, pour deux raisons. L'archive de la version
    sortante peut avoir été purgée entre-temps, et surtout : l'humain a vu ce
    diff-là sur l'écran d'impact avant de confirmer. Recalculer ouvrirait la
    possibilité que le modèle juge sur autre chose que ce qui a été montré.
    """
    ligne = (
        db.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == version).first()
    )
    return deserialiser_unites(ligne.changements if ligne else None)


def restees_en_analyse(db, doc_id: str, version: int) -> list[Reponse]:
    """Les réponses de ce lot dont personne n'a encore résolu le drapeau transitoire."""
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
    """Requalifie en relecture explicite ce qui est resté « analyse en cours ».

    ``ANALYSE_EN_COURS`` est le seul état transitoire du modèle de données, et un
    état transitoire qui survit est un bug silencieux : la réponse reste servie,
    l'interface annonce une analyse qui n'aura jamais lieu, et personne n'est
    sollicité. Le rabattement est toujours conservateur — la réponse n'est jamais
    retirée du service sur une panne, elle est mise dans la file de relecture.
    """
    restes = restees_en_analyse(db, doc_id, version)
    if not restes:
        return 0

    poser_a_relire(restes, raison, doc_id, version)
    tracer(db, restes, justification, None)
    return len(racines(restes))


class TacheReverif(celery_app.Task):
    """Porte le filet de dernier recours : un worker tué ne laisse rien en suspens.

    Appelé une fois les retries épuisés (un ``Retry`` ne passe pas par ici). Sans
    lui, un OOM-kill à mi-parcours laisserait indéfiniment des réponses en
    « analyse en cours » — servies, marquées douteuses, et jamais présentées à
    personne.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        doc_id, version = kwargs.get("doc_id"), kwargs.get("version")
        if not doc_id or version is None:
            return

        db = SessionLocal()
        try:
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            print(f"[REVERIF] ❌ échec définitif — {nb} réponse(s) rabattues en relecture")
        except Exception as e:
            print(f"[REVERIF] rabattement impossible après échec : {e}")
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
    """Juge les réponses du lot et applique les verdicts, dans la limite du budget.

    Convergent par construction : ``reponses_obsoletes`` écarte ce qui est déjà
    obsolète et ``delete_response_point`` sur un identifiant absent est un no-op,
    donc un rejeu ne fait que reprendre le reliquat.
    """
    print(f"🔎 --- RÉ-VÉRIFICATION (doc {doc_id} v{version}) ---")
    db = SessionLocal()

    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        if doc is None or doc.version != version:
            # Une v(n+1) est passée entre-temps : elle a reflagué le même périmètre
            # à son propre numéro et porte son propre job. Juger sur un diff périmé
            # produirait des verdicts sur un texte qui n'est plus servi.
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            print(f"[REVERIF] version dépassée — abandon, {nb} réponse(s) rabattues")
            return {"statut": "DEPASSE", "doc_id": doc_id, "version": version}

        unites = unites_figees(db, doc_id, version)

        if not unites:
            # `document_update_job` n'enfile qu'avec au moins une unité : arriver
            # ici signale une ligne de version tronquée ou perdue, pas un
            # reformatage. On ne se tait pas là-dessus.
            nb = rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
            print(f"[REVERIF] aucune unité relue — {nb} réponse(s) en relecture")
            return _termine(doc_id, version, domaine, {"nb_indisponibles": nb})

        if len(unites) > MAX_UNITES:
            # Le document n'a pas été modifié, il a été réécrit : il n'y a plus
            # rien à discriminer et aucun appel au modèle ne le dirait mieux.
            touchees = marquer_a_relire(db, doc_id, version, RAISON_MASSIVE)
            tracer(db, touchees, JUSTIF_MASSIVE, None)
            nb = len(racines(touchees))
            print(f"[REVERIF] {len(unites)} unités (> {MAX_UNITES}) — {nb} réponse(s) en relecture, 0 appel LLM")
            return _termine(doc_id, version, domaine, {"nb_a_relire": nb})

        candidates = rassembler_candidates(db, doc_id, domaine, unites, set(indices_disparus or []))
        print(f"[REVERIF] {len(unites)} unité(s), {len(candidates)} réponse(s) à examiner")

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
                # Le surplus n'est jamais ignoré en silence : c'est précisément ce
                # que faisait l'ancien système, et c'est pour ça qu'on ne pouvait
                # pas lui faire confiance. Il part en relecture, avec sa raison.
                nb_indisponibles += signaler_sans_juger(
                    db, candidates[rang:], RAISON_PARTIELLE, JUSTIF_PARTIELLE, doc_id, version
                )
                print(f"[REVERIF] budget épuisé — {len(candidates) - rang} réponse(s) en relecture")
                break

            pertinentes, fiable = unites_pertinentes(candidate.question, unites)

            if candidate.prioritaire and not pertinentes:
                # Un passage cité par cette réponse a disparu de la nouvelle
                # version : c'est un fait, pas une ressemblance. Le reranker,
                # qui n'est qu'un tri, n'a pas à pouvoir annuler ce signal.
                pertinentes = unites[:MAX_UNITES_PAR_REPONSE]

            if fiable and not pertinentes:
                # Aucun changement ne porte sur cette question : rien à juger, et
                # surtout rien à laisser traîner — le drapeau transitoire tombe.
                comptes[decider(db, candidate, VERDICT_INTACTE, "", [], doc_id, version)] += 1
                continue

            budget -= 1
            try:
                verdict, justification = juger(candidate.question, candidate.texte, pertinentes)
            except Exception as exc:
                echecs += 1
                print(f"[REVERIF] jugement impossible ({exc})")
                reste = candidates[rang:] if echecs >= MAX_ECHECS else [candidate]
                nb_indisponibles += signaler_sans_juger(db, reste, RAISON_INDISPONIBLE, JUSTIF_PANNE, doc_id, version)
                if echecs >= MAX_ECHECS:
                    print(f"[REVERIF] Albert injoignable — {len(reste)} réponse(s) en relecture")
                    break
                continue

            echecs = 0
            action = decider(db, candidate, verdict, justification, pertinentes, doc_id, version)
            comptes[action] += 1
            print(f"[REVERIF] {candidate.reponse.id} → {verdict} ({action})")

        # Filet intermédiaire : une réponse flaguée à l'étape 10 de la mise à jour
        # mais absente du lot de candidates (session concurrente, famille recomposée)
        # resterait sinon en « analyse en cours » sans que rien ne la résolve.
        nb_indisponibles += rabattre(db, doc_id, version, RAISON_INDISPONIBLE, JUSTIF_PANNE)

        return _termine(
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
        print(f"[REVERIF] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


def _termine(doc_id: str, version: int, domaine: str, comptes: dict) -> dict:
    """Publie le bilan et le rend à Celery.

    ``saved_answers_updated`` sur ``sse:admin`` n'est pas redondant avec
    l'événement de domaine : sans lui, l'onglet « Réponses enregistrées » d'un
    admin affiche une liste périmée jusqu'au prochain rafraîchissement manuel,
    alors que des réponses viennent d'y entrer ou d'en sortir.
    """
    bilan = {
        "nb_contredites": 0,
        "nb_a_relire": 0,
        "nb_intactes": 0,
        "nb_indisponibles": 0,
        **comptes,
    }
    print(
        f"[REVERIF] ✅ {bilan['nb_contredites']} retirée(s), "
        f"{bilan['nb_a_relire']} à relire, {bilan['nb_intactes']} intacte(s), "
        f"{bilan['nb_indisponibles']} non jugée(s)"
    )

    broadcast_sync(
        f"sse:domain:{domaine}",
        "reverification_done",
        {"doc_id": doc_id, "version": version, **bilan},
    )
    broadcast_sync("sse:admin", "saved_answers_updated", {"doc_id": doc_id, "version": version})

    return {"statut": "OK", "doc_id": doc_id, "version": version, **bilan}
