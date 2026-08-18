"""Étages 2 et 3 du pipeline de révérification : scoring et verdict LLM.

Étage 2 — ``unites_pertinentes`` : reranker, quelles unités de changement portent
sur la question de cette réponse ?
Étage 3 — ``juger`` : LLM, ce changement contredit-il la réponse servie ?
"""

import json

from app.services.llm import chat
from app.services.obsolescence import Unite
from app.services.reranker import rerank

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
        print(f"[REVERIF] reranker indisponible ({exc}) — jugement sans tri préalable")
        return unites[:MAX_UNITES_PAR_REPONSE], False

    if not classees:
        print("[REVERIF] reranker sans résultat exploitable — jugement sans tri préalable")
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
