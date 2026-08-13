"""Décide si une réponse déjà servie survit à la nouvelle version d'un document.

C'est le seul endroit du projet où **le texte de la réponse est lu**. Tout le
reste de la chaîne d'obsolescence compare document à document : on sait quels
passages ont fondé une réponse, on vérifie s'ils existent encore. C'est robuste
mais ça ne répond pas à la question qui compte. Un chunk fait 384 tokens ; y
corriger une virgule le rend introuvable en sous-chaîne et condamnait jusqu'ici
une réponse parfaitement juste. À l'inverse, un article ajouté ailleurs qui
contredit frontalement une réponse ne touche aucun passage cité et passait
inaperçu. Les deux erreurs ont la même cause : personne ne lisait la réponse.

Le pipeline est un entonnoir, du gratuit au coûteux, et **seul le dernier étage
prononce un verdict** :

::

    unités de changement   (diff aligné, gratuit — services/obsolescence.py)
            ↓
    candidates             (citantes du document + voisines du domaine, dense Qdrant)
            ↓
    unites_pertinentes     (reranker : quelles unités portent sur cette question ?)
            ↓
    juger                  (LLM : ce changement contredit-il cette réponse ?)
            ↓
    decider                (retrait sec / relecture / rien)

Chaque étage est **orienté rappel** : un faux positif coûte un appel au modèle,
un faux négatif laisse servir une réponse fausse en silence. Les seuils sont donc
bas et les pannes se replient toujours vers « fais lire un humain », jamais vers
« laisse passer » ni vers « détruis ».
"""

import json
import uuid
from dataclasses import dataclass

from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.llm import chat
from app.services.obsolescence import (
    RAISON_CONTREDITE,
    RAISON_CONTREDITE_PROB,
    RAISON_MODIF,
    Unite,
    fermeture_copies,
    lever_a_relire,
    poser_a_relire,
    racines,
    reponses_obsoletes,
    retirer_du_service,
    serialiser_unites,
)
from app.services.qdrant import COLLECTION_NAME, client
from app.services.reranker import rerank
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
)
from sqlalchemy.orm import Session

# Au-delà, le document n'a pas été modifié : il a été réécrit. Il n'y a plus rien
# à discriminer — juger 200 réponses contre 300 changements coûterait une fortune
# pour conclure « tout est suspect », ce qu'on sait déjà. Le worker bascule alors
# sur le signalement en bloc, sans un seul appel au modèle.
MAX_UNITES = 40

# Budget d'appels au LLM par mise à jour. Le surplus n'est jamais ignoré : il part
# en relecture humaine avec sa propre raison, pour que la troncature soit visible.
MAX_JUGEMENTS = 25

# Réponses ramenées par unité de changement lors du rappel vectoriel.
TOP_K_UNITE = 20

# Seuil du rappel dense. Délibérément bas : l'embedding ne décide de rien, il
# élargit. Le reranker filtre derrière, et le modèle tranche.
SEUIL_RAPPEL = 0.35

# Seuil du reranker. Bas pour la même raison, et pour une seconde : le rapprochement
# se fait entre un paragraphe de document et une *question*, deux objets de nature
# différente dont les scores ne se comparent pas à ceux d'un couple question/question.
SEUIL_RERANK = 0.15

# Unités montrées au modèle pour une réponse donnée. Au-delà, le prompt se dilue
# et le verdict se dégrade.
MAX_UNITES_PAR_REPONSE = 3

VERDICT_CONTREDITE = "CONTREDITE"
VERDICT_INTACTE = "INTACTE"
VERDICT_INCERTAIN = "INCERTAIN"
VERDICTS = (VERDICT_CONTREDITE, VERDICT_INTACTE, VERDICT_INCERTAIN)


@dataclass
class Candidate:
    """Une réponse à juger, et ce qu'on sait déjà d'elle avant de la juger."""

    reponse: Reponse
    question: str
    # Cite au moins un chunk du document modifié. Conditionne la sévérité maximale
    # atteignable : voir `decider`.
    citante: bool
    # Cite un chunk qui a *disparu* de la nouvelle version. Signal factuel, pas
    # statistique : il court-circuite le filtre de pertinence.
    prioritaire: bool = False

    @property
    def texte(self) -> str:
        return self.reponse.contenu_corrige or self.reponse.contenu or ""

    def _cle_tri(self) -> tuple:
        return (self.prioritaire, self.citante, self.reponse.canonique, self.reponse.nb_validations or 0)


# ──────────────────────────────────────────────────────────────────────────────
# Étage 1 — qui pourrait être concerné
# ──────────────────────────────────────────────────────────────────────────────


def rassembler_candidates(
    db: Session,
    doc_id: str,
    domaine: str,
    unites: list[Unite],
    indices_disparus: set[int],
) -> list[Candidate]:
    """Les réponses susceptibles d'être touchées, les plus exposées d'abord.

    Deux sources, et il faut les deux :

    * **les citantes** — toutes les VALIDÉE encore servies qui s'appuient sur ce
      document. Le périmètre est le document entier et non « près de la zone
      modifiée » : la contradiction est par définition ailleurs dans le cas qu'on
      cherche à rattraper.
    * **les voisines du domaine** — celles dont la question ressemble à un
      changement, retrouvées en interrogeant Qdrant avec le texte de l'unité.
      Elles couvrent le cas où le nouvel article d'une charte contredit une
      réponse bâtie sur un *autre* document.

    Le tri n'est pas cosmétique : c'est l'ordre dans lequel le budget d'appels au
    modèle sera dépensé. Les prioritaires d'abord, puis les canoniques, puis les
    plus validées — c'est-à-dire les plus resservies, donc celles dont l'erreur
    se propage le plus.

    La liste est réduite à ses ``racines`` : les deux sources remontent les copies
    SUGGESTION/CANONIQUE, et une réponse réutilisée cinq fois coûterait sinon cinq
    jugements identiques. ``decider`` rouvre la famille au moment d'appliquer.
    """
    citantes = reponses_obsoletes(db, doc_id, indices=None)
    ids_citantes = {r.id for r in citantes}

    ids_prioritaires: set[uuid.UUID] = set()
    if indices_disparus:
        ids_prioritaires = {r.id for r in reponses_obsoletes(db, doc_id, indices=indices_disparus)}

    voisines = [r for r in _voisines(db, domaine, unites) if r.id not in ids_citantes]

    distinctes = racines(citantes + voisines)
    questions = _questions(db, distinctes)
    candidates = [
        Candidate(
            reponse=r,
            question=questions.get(r.id, ""),
            citante=r.id in ids_citantes,
            prioritaire=r.id in ids_prioritaires,
        )
        for r in distinctes
    ]

    candidates.sort(key=Candidate._cle_tri, reverse=True)
    return candidates


def _voisines(db: Session, domaine: str, unites: list[Unite]) -> list[Reponse]:
    """Réponses validées du domaine dont la question ressemble à un changement.

    Une requête **dense uniquement** : ``embed_texts`` renvoie un vecteur sparse
    vide (``{"indices": [], "values": []}``), interroger la branche sparse
    reviendrait à envoyer un vecteur nul à Qdrant. Pour la même raison on
    n'emprunte pas ``search_hybrid``, qui ne sait pas non plus cibler les points
    de réponse.

    ``must_not=[IsEmpty("reponse_id")]`` est le seul moyen d'isoler ces points :
    ``feedback_job`` les écrit avec ``{reponse_id, ticket_id, contenu, domaine}``
    et **sans** ``doc_id``, dans la même collection que les chunks de document.
    Aucun index de payload sur ``reponse_id`` — Qdrant filtre donc en scan, ce qui
    reste acceptable à cette volumétrie et se paye une fois par mise à jour.

    Une panne d'embedding ou de Qdrant rend une liste vide et n'interrompt rien :
    les citantes, elles, sont connues sans appel réseau et restent jugées.
    """
    if not unites:
        return []

    try:
        embeddings = embed_texts([u.texte for u in unites], is_query=True)
    except Exception as exc:
        print(f"[REVERIF] embedding des changements indisponible ({exc}) — rappel limité aux citantes")
        return []

    filtre = Filter(
        must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))],
        must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))],
    )

    trouves: set[uuid.UUID] = set()
    for emb in embeddings:
        try:
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=emb["dense"],
                using="dense",
                query_filter=filtre,
                limit=TOP_K_UNITE,
                with_payload=["reponse_id"],
            )
        except Exception as exc:
            print(f"[REVERIF] rappel Qdrant impossible ({exc})")
            return []
        for point in res.points:
            if point.score < SEUIL_RAPPEL:
                continue
            brut = (point.payload or {}).get("reponse_id")
            if brut:
                try:
                    trouves.add(uuid.UUID(str(brut)))
                except ValueError:
                    continue

    if not trouves:
        return []

    # Une copie SUGGESTION/CANONIQUE ne porte pas de point à elle : c'est la source
    # qui a été retrouvée. La descente transitive ramène la famille, faute de quoi
    # on retirerait la graine et la copie continuerait d'être servie.
    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, trouves)),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def _questions(db: Session, reponses: list[Reponse]) -> dict[uuid.UUID, str]:
    """La question à laquelle chaque réponse répond — la précision si elle existe.

    ``question_suivi`` prime sur la question du ticket pour la même raison qu'à
    l'indexation (cf. ``feedback_job``) : quand une réponse est née d'une relance,
    c'est la relance qui la décrit, pas la demande initiale du fil.
    """
    ids = {r.ticket_id for r in reponses if r.ticket_id is not None}
    tickets = {t.id: t.question for t in db.query(Ticket).filter(Ticket.id.in_(ids)).all()} if ids else {}
    return {r.id: r.question_suivi or tickets.get(r.ticket_id, "") for r in reponses}


# ──────────────────────────────────────────────────────────────────────────────
# Étage 2 — quels changements portent sur cette réponse
# ──────────────────────────────────────────────────────────────────────────────


def unites_pertinentes(question: str, unites: list[Unite]) -> tuple[list[Unite], bool]:
    """Les changements qui concernent cette question, et si le tri est digne de foi.

    Un appel de reranker par **réponse**, et non par couple (réponse, unité) :
    l'API prend une requête et une liste de documents, elle rend directement le
    classement cherché. Le cross-encoder est bien meilleur que le cosinus pour
    « ce passage porte-t-il sur cette question ? », qui est exactement la question
    posée ici.

    Le second membre du tuple vaut ``False`` quand le tri n'a pas eu lieu. Ce
    n'est pas un détail : ``rerank`` renvoie une liste **vide** sans lever quand
    la réponse d'Albert n'a pas la forme attendue (cf. ``services/reranker.py``,
    la branche ``if "results" in predictions`` n'a pas de ``else``). Lire cette
    liste vide comme « aucune unité pertinente » ferait sortir silencieusement
    toutes les réponses du pipeline le jour où le format de l'API change — soit
    exactement la panne qui ne se voit pas. On renvoie donc les unités non
    triées, et l'appelant les fait juger quand même.
    """
    if len(unites) <= 1:
        return unites, True

    marques = [{"contenu": u.texte, "_unite": u} for u in unites]
    try:
        classees = rerank(question, marques, top_k=MAX_UNITES_PAR_REPONSE)
    except Exception as exc:
        print(f"[REVERIF] reranker indisponible ({exc}) — jugement sans tri préalable")
        return unites[:MAX_UNITES_PAR_REPONSE], False

    if not classees:
        print("[REVERIF] reranker sans résultat exploitable — jugement sans tri préalable")
        return unites[:MAX_UNITES_PAR_REPONSE], False

    return [c["_unite"] for c in classees if c.get("rerank_score", 0.0) >= SEUIL_RERANK], True


# ──────────────────────────────────────────────────────────────────────────────
# Étage 3 — le verdict
# ──────────────────────────────────────────────────────────────────────────────

PROMPT_SYSTEME = """Tu vérifies si une réponse déjà publiée reste exacte après la modification
d'un document de référence.

On te donne la question posée, la réponse telle qu'elle est servie aujourd'hui, et les passages
du document qui ont changé, sous la forme AVANT / APRÈS.

Rends exactement l'un de ces trois verdicts :
- CONTREDITE : le nouveau texte rend la réponse fausse ou périmée — un chiffre, un délai, un seuil,
  une condition, un interlocuteur ou une procédure qu'elle énonce a changé, ou la règle sur laquelle
  elle repose a été abrogée.
- INTACTE : les changements ne portent pas sur ce qu'affirme la réponse, ou la confirment.
- INCERTAIN : les changements pourraient la concerner, mais les éléments fournis ne permettent
  pas de trancher.

Règles :
- Ne juge que d'après les passages fournis. N'invente aucune règle absente.
- Une simple reformulation, un changement de numérotation ou de ponctuation sans effet sur le fond
  est INTACTE.
- Ne rédige jamais de correction ni de réponse de remplacement.
- Dans le doute, réponds INCERTAIN et non INTACTE : une réponse fausse laissée en service coûte
  plus cher qu'une relecture inutile.

Réponds uniquement par un objet JSON, sans texte autour ni bloc de code :
{"verdict": "CONTREDITE|INTACTE|INCERTAIN", "justification": "une phrase de 200 caractères maximum"}"""

LONGUEUR_JUSTIFICATION = 200


def juger(question: str, reponse_servie: str, unites: list[Unite]) -> tuple[str, str]:
    """Demande au modèle si ces changements contredisent cette réponse.

    Le prompt montre **le diff, pas l'état actuel du document**. C'est délibéré :
    « ce qui a changé contredit-il cette réponse ? » est une question fermée, dont
    les deux termes sont sous les yeux du modèle. « cette réponse est-elle encore
    déductible du document ? » ferait re-juger tout le pipeline RAG et
    condamnerait des réponses correctes au seul motif que la recherche ne les
    retrouve pas — on remplacerait une machine à faux positifs par une autre.

    Lève en cas d'échec HTTP : c'est à l'appelant de décider quoi faire d'une
    panne, et il n'a pas les mêmes options qu'une hésitation du modèle. Une sortie
    illisible, en revanche, vaut ``INCERTAIN`` — jamais ``INTACTE``.
    """
    changements = "\n\n".join(_formater(u) for u in unites)
    messages = [
        {"role": "system", "content": PROMPT_SYSTEME},
        {
            "role": "user",
            "content": (
                f"Question posée :\n{question}\n\n"
                f"Réponse actuellement servie :\n{reponse_servie}\n\n"
                f"Changements apportés au document :\n{changements}"
            ),
        },
    ]

    return _lire_verdict(chat(messages, temperature=0, max_tokens=2048, timeout=60))


def _formater(unite: Unite) -> str:
    if unite.avant is None:
        return f"[AJOUTÉ]\n{unite.apres}"
    if unite.apres is None:
        return f"[SUPPRIMÉ]\n{unite.avant}"
    return f"[MODIFIÉ]\nAVANT : {unite.avant}\nAPRÈS : {unite.apres}"


def _lire_verdict(brut: str) -> tuple[str, str]:
    """Extrait ``(verdict, justification)`` d'une sortie de modèle.

    Tolère l'encadrement en bloc de code et le bavardage autour de l'objet, que
    les modèles produisent malgré la consigne. Tout ce qui reste illisible ou
    inattendu retombe sur ``INCERTAIN`` : le seul repli acceptable est celui qui
    fait relire un humain, jamais celui qui laisse la réponse en service sans
    l'avoir vérifiée.
    """
    debut, fin = brut.find("{"), brut.rfind("}")
    if debut == -1 or fin <= debut:
        print(f"[REVERIF] réponse Albert illisible (pas de JSON) : {brut!r}")
        return VERDICT_INCERTAIN, "Réponse du modèle illisible."

    try:
        charge = json.loads(brut[debut : fin + 1])
    except json.JSONDecodeError:
        print(f"[REVERIF] réponse Albert illisible (JSON invalide) : {brut!r}")
        return VERDICT_INCERTAIN, "Réponse du modèle illisible."

    verdict = str(charge.get("verdict", "")).strip().upper()
    if verdict not in VERDICTS:
        return VERDICT_INCERTAIN, "Verdict du modèle non reconnu."

    justification = " ".join(str(charge.get("justification") or "").split())
    return verdict, justification[:LONGUEUR_JUSTIFICATION]


# ──────────────────────────────────────────────────────────────────────────────
# Étage 4 — l'application
# ──────────────────────────────────────────────────────────────────────────────

ACTION_RETIREE = "retiree"
ACTION_A_RELIRE = "a_relire"
ACTION_INTACTE = "intacte"


def decider(
    db: Session,
    candidate: Candidate,
    verdict: str,
    justification: str,
    unites: list[Unite],
    doc_id: str,
    version: int,
) -> str:
    """Applique le verdict, et renvoie l'action retenue pour le comptage.

    Une seule asymétrie, mais elle est le garde-fou central : **une réponse qui
    ne cite pas le document ne peut pas être retirée automatiquement.** Elle n'a
    été rapprochée du changement que par similarité vectorielle entre un
    paragraphe et une question — deux objets de nature différente, indexés pour
    autre chose. Détruire à tort une canonique à douze validations coûte bien plus
    cher que d'imposer vingt relectures ; le verdict plafonne donc à la relecture.

    Chaque décision est commitée séparément (``retirer_du_service`` commite) : un
    worker qui meurt à mi-parcours conserve les jugements déjà payés, et le rejeu
    ne repasse que sur le reliquat.
    """
    famille = _famille(db, candidate.reponse)
    extraits = serialiser_unites(unites)["unites"]

    if verdict == VERDICT_CONTREDITE and candidate.citante:
        retirer_du_service(db, famille, RAISON_CONTREDITE, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_RETIREE

    if verdict == VERDICT_CONTREDITE:
        poser_a_relire(famille, RAISON_CONTREDITE_PROB, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_A_RELIRE

    if verdict == VERDICT_INTACTE:
        for r in famille:
            # Ne jamais effacer le signalement d'un *autre* document : cette
            # réponse peut attendre une relecture déclenchée ailleurs, que ce
            # job n'a pas instruite et n'a aucun titre à clore.
            if r.a_relire_doc_id == doc_id:
                lever_a_relire(r)
                r.analyse_justification = None
                r.analyse_extraits = None
        db.commit()
        return ACTION_INTACTE

    poser_a_relire(famille, RAISON_MODIF, doc_id, version)
    tracer(db, famille, justification, extraits)
    return ACTION_A_RELIRE


def signaler_sans_juger(
    db: Session,
    candidates: list[Candidate],
    raison: str,
    justification: str,
    doc_id: str,
    version: int,
) -> int:
    """Envoie en relecture des réponses qu'on n'a pas pu juger, et le dit.

    Sert les trois cas où le pipeline s'arrête avant le verdict : budget d'appels
    épuisé, document réécrit au-delà du plafond, Albert injoignable. Aucun de ces
    cas ne doit être silencieux — c'est précisément parce que l'ancien système
    tronquait sans le dire qu'on ne pouvait pas lui faire confiance.
    """
    for candidate in candidates:
        famille = _famille(db, candidate.reponse)
        poser_a_relire(famille, raison, doc_id, version)
        tracer(db, famille, justification, None)
    db.commit()
    return len(candidates)


def _famille(db: Session, reponse: Reponse) -> list[Reponse]:
    """La réponse et toutes ses copies encore en service.

    Les copies SUGGESTION/CANONIQUE ne citent aucun chunk : elles ne se rattachent
    à leur origine que par ``reponse_source_id``. Décider sur la seule graine
    laisserait la copie indexée, donc resservie.
    """
    return db.query(Reponse).filter(Reponse.id.in_(fermeture_copies(db, {reponse.id}))).all()


def tracer(db: Session, reponses: list[Reponse], justification: str, extraits: list[dict] | None) -> None:
    for r in reponses:
        r.analyse_justification = justification or None
        r.analyse_extraits = {"unites": extraits} if extraits else None
    db.commit()
