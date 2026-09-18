import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry

from app.crud.question import TicketDisparu, upsert_reponse, upsert_ticket
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.garde_cache import statuer
from app.services.llm import generate
from app.services.question_pipeline import (
    SEUIL_COSINUS,  # noqa: F401 — ré-exporté pour les tests qui l'importent depuis ce module
    SEUIL_SUGGESTION,  # noqa: F401
    charger_contexte_fil,
    journaliser_garde,
    peut_servir_sans_revue,
    servir_reutilisation,
    ticket_existe,
    trouver_reponse_reutilisable,
)
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.services.tag_suggestion import suggerer_tag
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Aliases privés maintenus pour la compatibilité des imports existants (tests, etc.)
_charger_contexte_fil = charger_contexte_fil
_upsert_reponse = upsert_reponse
_upsert_ticket = upsert_ticket
_ticket_existe = ticket_existe
_trouver_reponse_reutilisable = trouver_reponse_reutilisable
_servir_reutilisation = servir_reutilisation


def _on_failure_question_job(self, exc, task_id, args, kwargs, einfo):
    """Si le task échoue définitivement avec un ticket_id, le repasse à ÉCHOUÉ.

    Sans ce hook, un ticket rejoué par replay_echoues_job (statut_job=EN_ATTENTE)
    et qui échoue avant l'étape upsert_ticket reste bloqué à EN_ATTENTE pour
    toujours — invisible au filtre du prochain replay qui cible ÉCHOUÉ.
    """
    ticket_id = kwargs.get("ticket_id")
    if not ticket_id:
        return
    import uuid as _uuid

    try:
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == _uuid.UUID(ticket_id)).first()
            if ticket and ticket.statut_job == "EN_ATTENTE":
                ticket.statut_job = "ÉCHOUÉ"
                ticket.erreur = str(exc)
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions",
    on_failure=_on_failure_question_job,
)
def question_job(
    self,
    question: str,
    domaine: str,
    user_id: str | None = None,
    ticket_id: str | None = None,
    objet: str | None = None,
    retraiter: bool = False,
):
    try:
        logger.info("nouvelle question — domaine=%s question=%s", domaine, question)

        job_id = uuid.UUID(self.request.id)
        user_uuid = uuid.UUID(user_id) if user_id else None

        ticket_uuid = uuid.UUID(ticket_id) if ticket_id else None
        est_suivi = ticket_uuid is not None and not retraiter
        question_suivi = question if est_suivi else None

        if ticket_uuid is not None and not _ticket_existe(ticket_uuid):
            logger.info("ticket %s introuvable — job abandonné", ticket_uuid)
            return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(ticket_uuid)}

        # Étape 0 (suivi) — Charger le fil pour contextualiser recherche et LLM.
        historique: list[dict] | None = None
        requete_recherche = question
        if est_suivi:
            historique, requete_recherche = charger_contexte_fil(ticket_uuid, question)

        # Étape 1 — Embedding + recherche hybride
        logger.info("recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        logger.info("%d chunks trouvés", len(chunks))

        for i, chunk in enumerate(chunks[:3]):
            # Les deux signaux sont tracés : la porte se franchit par l'un ou
            # l'autre, donc lire les journaux exige de voir les deux.
            logger.debug(
                "#%d cosinus=%.4f lexical=%.2f/terme source=%s",
                i + 1,
                chunk["score_cosinus"],
                chunk.get("score_lexical", 0.0),
                chunk["source"],
            )

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Réponse déjà validée, retrouvée directement via son reponse_id.
        chunks_ctx: list[dict] | None = None
        db = SessionLocal()
        try:
            candidat = trouver_reponse_reutilisable(db, chunks)
            reponse_liee, score_liee = candidat.reponse, candidat.score_cosinus
            question_du_point = candidat.question_indexee

            if reponse_liee is not None:
                logger.info("score %.4f → réponse validée %s", score_liee, reponse_liee.id)

                # **Le juge est consulté exactement quand son verdict peut changer
                # l'issue** : dès que le candidat serait réutilisé sous une forme ou
                # une autre, CANONIQUE *ou* SUGGESTION. Ni le score ni le statut ne
                # décident *si on appelle* — ils décident seulement *ce qu'un OUI
                # ouvre*, et `servir_reutilisation` le reteste lui-même.
                #
                # L'asymétrie est ce qui rend l'élargissement sûr : **on se sert du
                # refus du juge, jamais de son accord.** Un OUI n'ouvre rien que
                # `peut_servir_sans_revue` n'autorisait déjà — une réponse signalée
                # `a_relire` que le juge approuve ressort en SUGGESTION, exactement
                # comme sans lui. Ce qu'on récupère, ce sont les **NON** qu'on ne
                # demandait à personne.
                #
                # La branche SUGGESTION n'avait aucun juge (cf. la docstring de
                # `Candidat.servable` : « la branche CANONIQUE a un juge pour la
                # protéger, la branche SUGGESTION n'en a aucun »), ce qui était sans
                # conséquence tant qu'un refus sortait *lui aussi* en SUGGESTION.
                # Depuis que le refus jugé renvoie au RAG, ne pas appeler le juge ne
                # fait plus économiser un appel : ça pose sur l'écran du relecteur
                # une réponse dont personne n'a vérifié qu'elle répondait à la
                # question — là où « Valider » est le bouton le moins cher.
                #
                # Mesuré le 18/09/2026, bout en bout télétravail, domaine neuf : la
                # canonique *générale*, signalée `CONTREDITE_PROBABLE` par la
                # confrontation, était proposée telle quelle à « est ce que
                # télétravail possible ? pour les alternant ? » (3 passes sur 3,
                # cosinus 0,8047, zéro ligne dans `garde_decisions`). Interrogé, le
                # juge la refuse 3 fois sur 3, et le RAG répond juste 3 fois sur 3
                # (« règle générale + exception », doc B reranké #1 à 0,9677).
                #
                # Quand ni `peut_servir_sans_revue` ni `servable` ne tiennent
                # (candidat retenu par les seuls mots et non canonique), l'issue est
                # le RAG quel que soit le verdict : on n'appelle pas.
                if peut_servir_sans_revue(reponse_liee) or candidat.servable:
                    # La question portée par le point qui a matché fait foi : une
                    # réponse est indexée sous autant de formulations qu'elle a de
                    # validations humaines, et le garde doit juger celle-là. Repli
                    # sur le ticket d'origine pour les points antérieurs, qui ne
                    # portent pas encore `question_indexee` dans leur payload.
                    question_indexee = question_du_point
                    if not question_indexee:
                        ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
                        question_indexee = reponse_liee.question_suivi or (
                            ticket_source.question if ticket_source else None
                        )
                    question_a_comparer = requete_recherche if est_suivi else question

                    decision = None
                    if question_indexee:
                        decision = statuer(question_a_comparer, question_indexee, est_suivi=est_suivi)
                        journaliser_garde(
                            decision,
                            job_id=job_id,
                            ticket_id=ticket_uuid,
                            domaine=domaine,
                            est_suivi=est_suivi,
                            question_posee=question_a_comparer,
                            question_indexee=question_indexee,
                            reponse_id=reponse_liee.id,
                            # Les deux signaux séparément : le cosinus garde le
                            # sens qu'il avait avant BM25, ce qui rend les décisions
                            # comparables d'une version à l'autre, et le lexical dit
                            # par quelle porte le candidat est passé.
                            score_cosinus=candidat.score_cosinus,
                            score_lexical=candidat.score_lexical,
                        )

                    approuve = decision is not None and decision.verdict

                    if approuve and peut_servir_sans_revue(reponse_liee):
                        # CANONIQUE **si** le candidat franchit aussi `SEUIL_COSINUS` ;
                        # `servir_reutilisation` le vérifie et rabat sur SUGGESTION
                        # sinon. On passe donc `True` sans redonder le test ici : la
                        # porte du service sans revue n'a qu'une seule définition.
                        #
                        # `peut_servir_sans_revue` ne conditionne plus l'appel au
                        # juge, seulement ce que son accord ouvre : un OUI sur une
                        # réponse signalée `a_relire` tombe dans la branche
                        # SUGGESTION ci-dessous, comme avant qu'on l'interroge.
                        logger.info("garde : OUI → CANONIQUE si le seuil est franchi, sinon SUGGESTION")
                        return servir_reutilisation(
                            db,
                            job_id,
                            ticket_uuid,
                            question,
                            domaine,
                            user_uuid,
                            reponse_liee,
                            score_liee,
                            question_suivi,
                            est_suivi,
                            self.request.retries,
                            True,
                            objet,
                            score_lexical=candidat.score_lexical or 0.0,
                        )
                    # **Refus du garde → RAG, toujours.** Le juge vient de dire que
                    # les deux questions ne posent pas la même demande : le candidat
                    # ne répond donc pas à celle-ci, et le proposer au relecteur,
                    # c'est lui mettre sous les yeux quelque chose que le système a
                    # déjà jugé hors sujet — sur l'écran où « Valider » est le bouton
                    # le moins cher. Mieux vaut une génération fondée sur les
                    # documents, pour la question réellement posée.
                    #
                    # C'est la règle que `Candidat.servable` énonçait déjà pour les
                    # candidats purement lexicaux (« s'il n'est pas canonique, ou si
                    # le juge le refuse, il repart au RAG ») ; elle était abandonnée
                    # au-dessus de `SEUIL_SUGGESTION` sans raison. Mesuré sur la
                    # campagne 48 cas : 9 refus, dont 6 sortaient en SUGGESTION alors
                    # que le RAG était attendu — « Qui valide un engagement de
                    # dépense ? » se voyait proposer « Comment fait on un engagement
                    # de dépense » à 0,8254, juste après le refus.
                    #
                    # L'ancien repli invoquait la non-monotonie (« franchir le seuil
                    # dégradait l'issue »). Sa prémisse — un candidat vaut mieux que
                    # le RAG — est précisément ce que ces 6 cas contredisent, et le
                    # juge est désormais appelé sans condition de score, donc la
                    # discontinuité n'existe plus.
                    #
                    # Coût assumé : un refus *prudent* (paire en fait équivalente,
                    # cf. le cas à 0,8841) prive le relecteur d'une réponse validée
                    # réutilisable et fait naître une lignée parallèle sur le même
                    # sujet. C1 l'amortit — la sélection par pertinence fera remonter
                    # la meilleure des deux. Le refus reste tracé dans `garde_decisions`.
                    #
                    # **Seul un refus jugé envoie au RAG.** `Decision.erreur` existe
                    # exactement pour ça : « ce dernier ne doit pas être compté comme
                    # un refus du juge ». Albert injoignable, ou aucune question
                    # indexable à soumettre, ce n'est pas « pas la même demande » —
                    # c'est l'absence de verdict. On garde alors le comportement
                    # antérieur, SUGGESTION sous revue humaine : une panne réseau ne
                    # doit pas décider d'une branche, ni coûter une génération.
                    refus_juge = decision is not None and not approuve and not decision.erreur

                    if not refus_juge and candidat.servable:
                        logger.info(
                            "garde → SUGGESTION (revue humaine) : %s",
                            "OUI, mais réponse signalée a_relire ou non canonique"
                            if approuve
                            else (decision.erreur if decision else "aucune question indexée"),
                        )
                        return servir_reutilisation(
                            db,
                            job_id,
                            ticket_uuid,
                            question,
                            domaine,
                            user_uuid,
                            reponse_liee,
                            score_liee,
                            question_suivi,
                            est_suivi,
                            self.request.retries,
                            False,
                            objet,
                            score_lexical=candidat.score_lexical or 0.0,
                        )
                    logger.info("garde : NON → RAG (génération sur la question posée)")
                else:
                    # Candidat retenu par les seuls mots, et non canonique : ni
                    # servable ni autorisé à servir sans revue, l'issue est le RAG
                    # quel que soit le verdict. C'est la seule branche où ne pas
                    # appeler le juge est une économie et non une issue perdue.
                    logger.info("candidat lexical seul, non canonique → RAG (juge inutile)")

        finally:
            db.close()

        # Étape 3 — Reranking
        if est_suivi:
            if chunks_ctx is None:
                chunks_ctx = search_hybrid(requete_recherche, domaine, top_k=15)
            chunks_rag = chunks_ctx
        else:
            chunks_rag = chunks
        logger.info("reranking des chunks...")
        chunks_rerankes = rerank(requete_recherche, chunks_rag, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            logger.debug("rerank #%d score=%.4f source=%s", i + 1, chunk["rerank_score"], chunk["source"])

        # Étape 4 — Génération LLM (avec l'historique du fil pour un suivi)
        logger.info("génération LLM...")
        hors_domaine = False
        try:
            reponse_texte, hors_domaine = generate(question, chunks_rerankes, historique=historique)
            suffix = " [HORS_DOMAINE]" if hors_domaine else ""
            logger.info("réponse générée (%d caractères)%s", len(reponse_texte), suffix)
            statut_job = "TERMINÉ"
            erreur = None
        except Exception as llm_exc:
            logger.error("erreur LLM : %s", llm_exc)
            reponse_texte = None
            statut_job = "ÉCHOUÉ"
            erreur = str(llm_exc)

        # Étape 5 — Sauvegarde PostgreSQL + enregistrement chunks
        db = SessionLocal()
        try:
            ticket = upsert_ticket(
                db,
                job_id,
                ticket_id=ticket_uuid,
                question=question,
                objet=objet,
                domaine=domaine,
                user_id=user_uuid,
                statut_job=statut_job,
                statut_ticket="RÉPONDU" if reponse_texte else "NOUVEAU",
                score_similarite=top_score,
                canonique=False,
                nb_retries=self.request.retries,
                erreur=erreur,
                processed_at=datetime.now(timezone.utc),
            )

            reponse_id = None
            if reponse_texte:
                if hors_domaine:
                    tag_suggere = None
                else:
                    rows = (
                        db.query(Reponse.tag)
                        .join(Ticket, Ticket.id == Reponse.ticket_id)
                        .filter(
                            Reponse.tag.isnot(None),
                            Reponse.canonique.is_(True),
                            Reponse.reponse_source_id.is_(None),
                            Reponse.obsolete.is_(False),
                            Ticket.domaine == domaine,
                        )
                        .distinct()
                        .all()
                    )
                    tags_existants = sorted(r.tag for r in rows) or None
                    tag_suggere = suggerer_tag(question, reponse_texte, db, tags_existants)
                reponse = upsert_reponse(
                    db,
                    ticket,
                    reponse_texte,
                    top_score,
                    source="HORS_DOMAINE" if hors_domaine else "LLM",
                    question_suivi=question_suivi,
                    nouveau=est_suivi,
                    tag=tag_suggere,
                )
                reponse_id = str(reponse.id)

                for chunk in chunks_rerankes:
                    if not chunk.get("doc_id"):
                        continue
                    rc = ReponseChunk(
                        id=uuid.uuid4(),
                        reponse_id=reponse.id,
                        doc_id=chunk.get("doc_id"),
                        chunk_index=chunk.get("chunk_index", 0),
                        score_cosinus=chunk.get("score_cosinus"),
                        rerank_score=chunk.get("rerank_score"),
                    )
                    db.add(rc)

            ticket_id_str = str(ticket.id)
            db.commit()
        finally:
            db.close()

        logger.info("ticket créé (id=%s)", ticket_id_str)

        if statut_job == "ÉCHOUÉ":
            raise self.retry(exc=Exception(erreur), countdown=60)

        if statut_job == "TERMINÉ":
            from app.services.broadcast import broadcast_sync

            event = "ticket_followup" if est_suivi else "ticket_answered"
            broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str, "domaine": domaine})
            if user_uuid:
                broadcast_sync(f"sse:user:{user_uuid}", event, {"ticket_id": ticket_id_str, "domaine": domaine})

        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "reponse": reponse_texte,
            "ticket_id": ticket_id_str,
            "reponse_id": reponse_id,
            "top_score_cosinus": top_score,
        }

    except Retry:
        raise
    except TicketDisparu as exc:
        logger.info("ticket %s supprimé en cours de traitement — job abandonné", exc)
        return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(exc)}
    except Exception as exc:
        logger.error("erreur question_job : %s", exc)
        raise self.retry(exc=exc) from exc
