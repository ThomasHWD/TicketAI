"""Étages 2 et 3 du pipeline de révérification : scoring et verdict LLM.

Étage 2 — ``unites_pertinentes`` : reranker, quelles unités de changement portent
sur la question de cette réponse ?
Étage 3 — ``juger`` : LLM, ce changement contredit-il la réponse servie ?
"""

import json
import logging

from app.config import settings
from app.services.llm import chat
from app.services.obsolescence import Unite
from app.services.reranker import rerank

logger = logging.getLogger(__name__)

# Seuil du reranker. Bas pour la même raison que SEUIL_RAPPEL, et pour une
# seconde : le rapprochement se fait entre un paragraphe de document et une
# *question*, deux objets de nature différente dont les scores ne se comparent
# pas à ceux d'un couple question/question.
SEUIL_RERANK = 0.15

# Unités montrées au modèle pour une réponse donnée. Au-delà, le prompt se dilue
# et le verdict se dégrade.
MAX_UNITES_PAR_REPONSE = 3

VERDICT_CONTREDITE = "CONTREDITE"
VERDICT_INTACTE = "INTACTE"
VERDICT_INCERTAIN = "INCERTAIN"
VERDICTS = (VERDICT_CONTREDITE, VERDICT_INTACTE, VERDICT_INCERTAIN)

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

PROMPT_SYSTEME_CONFRONTATION = """Tu vérifies si une réponse déjà publiée reste exacte maintenant
qu'un nouveau document de référence a été ajouté.

On te donne la question posée, la réponse telle qu'elle est servie aujourd'hui, les passages du
document sur lesquels cette réponse avait été construite (ils peuvent manquer), et les passages du
document qui vient d'être ajouté.

Le nouveau document ne remplace pas l'ancien : les deux sont en vigueur. Tu n'as donc pas à décider
lequel fait foi, mais à dire si ce que la réponse affirme reste vrai une fois le nouveau texte pris
en compte.

Rends exactement l'un de ces trois verdicts :
- CONTREDITE : le nouveau texte rend la réponse fausse ou trompeuse — il infirme ce qu'elle affirme,
  ou il pose une exception, une restriction ou une condition qu'elle passe sous silence alors
  qu'elle porte précisément sur ce cas.
- INTACTE : le nouveau texte ne porte pas sur ce qu'affirme la réponse, ou il la confirme.
- INCERTAIN : il pourrait la concerner, mais les éléments fournis ne permettent pas de trancher.

Règles :
- Ne juge que d'après les passages fournis. N'invente aucune règle absente.
- Le rapprochement qui t'amène ce couple est approximatif : un passage qui traite d'un autre sujet,
  d'une autre population ou d'un autre dispositif est INTACTE, même s'il emploie le même vocabulaire.
- Une réponse seulement *incomplète* est CONTREDITE — elle induit son lecteur en erreur par
  omission — mais dis-le dans la justification : incomplète et fausse n'appellent pas la même suite.
- Ne rédige jamais de correction ni de réponse de remplacement.
- Dans le doute, réponds INCERTAIN et non INTACTE : une réponse fausse laissée en service coûte
  plus cher qu'une relecture inutile.

Réponds uniquement par un objet JSON, sans texte autour ni bloc de code :
{"verdict": "CONTREDITE|INTACTE|INCERTAIN", "justification": "une phrase de 200 caractères maximum"}"""

LONGUEUR_JUSTIFICATION = 200


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
        logger.warning("reranker indisponible (%s) — jugement sans tri préalable", exc)
        return unites[:MAX_UNITES_PAR_REPONSE], False

    if not classees:
        logger.warning("reranker sans résultat exploitable — jugement sans tri préalable")
        return unites[:MAX_UNITES_PAR_REPONSE], False

    return [c["_unite"] for c in classees if c.get("rerank_score", 0.0) >= SEUIL_RERANK], True


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
    modele = settings.albert_reverif_model_name or settings.albert_llm_model_name
    return _lire_verdict(chat(messages, temperature=0, max_tokens=2048, timeout=60, model=modele))


def juger_confrontation(
    question: str,
    reponse_servie: str,
    unites: list[Unite],
    extraits_source: list[str],
) -> tuple[str, str]:
    """Même question, mais posée sur un document qui vient d'arriver.

    Trois différences avec ``juger``, toutes dictées par le fait qu'il n'y a pas
    de diff ici — le document est neuf, donc tout est un ajout :

    * le prompt dit que les deux documents sont **en vigueur en même temps**.
      Sans ça, le modèle traite le nouveau texte comme une v2 qui abroge la v1 et
      condamne des réponses parfaitement valables ;
    * il nomme explicitement le cas « règle générale puis exception », qui est la
      raison d'être de cette branche ;
    * il reçoit ``extraits_source``, les passages sur lesquels la réponse avait
      été bâtie. C'est ce qui lui permet de distinguer une réponse fausse d'une
      réponse incomplète, et d'écarter les faux appariements du rappel à 0,35.
      La liste peut être vide (copie sans chunks cités, document supprimé) : le
      prompt l'annonce, et le jugement reste meilleur que pas de jugement.

    Lève en cas d'échec HTTP, comme ``juger`` : l'appelant n'a pas les mêmes
    options face à une panne que face à une hésitation du modèle.
    """
    nouveaux = "\n\n".join(_formater(u) for u in unites)
    source = "\n\n---\n\n".join(extraits_source) if extraits_source else "(non disponibles)"
    messages = [
        {"role": "system", "content": PROMPT_SYSTEME_CONFRONTATION},
        {
            "role": "user",
            "content": (
                f"Question posée :\n{question}\n\n"
                f"Réponse actuellement servie :\n{reponse_servie}\n\n"
                f"Passages sur lesquels cette réponse avait été construite :\n{source}\n\n"
                f"Passages du document qui vient d'être ajouté :\n{nouveaux}"
            ),
        },
    ]
    modele = settings.albert_reverif_model_name or settings.albert_llm_model_name
    return _lire_verdict(chat(messages, temperature=0, max_tokens=2048, timeout=60, model=modele))


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
        logger.error("réponse Albert illisible (pas de JSON) : %r", brut)
        return VERDICT_INCERTAIN, "Réponse du modèle illisible."

    try:
        charge = json.loads(brut[debut : fin + 1])
    except json.JSONDecodeError:
        logger.error("réponse Albert illisible (JSON invalide) : %r", brut)
        return VERDICT_INCERTAIN, "Réponse du modèle illisible."

    verdict = str(charge.get("verdict", "")).strip().upper()
    if verdict not in VERDICTS:
        return VERDICT_INCERTAIN, "Verdict du modèle non reconnu."

    justification = " ".join(str(charge.get("justification") or "").split())
    return verdict, justification[:LONGUEUR_JUSTIFICATION]
