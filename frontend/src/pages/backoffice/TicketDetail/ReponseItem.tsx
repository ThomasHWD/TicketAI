import { useState } from "react";
import { AlertCircle, Bot, Check, Pencil, Sparkles, ThumbsUp, X } from "lucide-react";
import { corrigerReponse, validerReponse, LockConflictError } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import { getValidatorId } from "../../../lib/currentUser";
import type { TicketReponse, StatutReponse } from "../../../types";
import { formatDate, BotAvatar } from "./utils";

export const SOURCE_LABEL: Record<string, { label: string; icon: typeof Bot }> = {
  SUGGESTION:    { label: "Suggestion",   icon: Sparkles },
  CANONIQUE:     { label: "Canonique",    icon: Bot },
  HORS_DOMAINE:  { label: "Hors domaine", icon: AlertCircle },
};

export function reponseStatutLabel(statut: StatutReponse, canonique: boolean) {
  if (statut === "VALIDÉE" || statut === "CORRIGÉE") return canonique ? "Canonique" : "Validée";
  if (statut === "REJETÉE") return "Rejetée";
  if (statut === "EN_ATTENTE") return "En attente";
  return statut;
}

export function reponseStatutClass(statut: StatutReponse, canonique: boolean) {
  if (statut === "REJETÉE")
    return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if ((statut === "VALIDÉE" || statut === "CORRIGÉE") && canonique)
    return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉE" || statut === "CORRIGÉE")
    return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  return "bg-yellow-50 text-yellow-600 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
}

export default function ReponseItem({
  reponse,
  readOnly,
  userEmail,
  onChanged,
  onLockConflict,
}: {
  reponse: TicketReponse;
  readOnly: boolean;
  userEmail: string | null;
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}) {
  const isHorsDomaine = reponse.source === "HORS_DOMAINE";
  const canAct = reponse.statut === "EN_ATTENTE" && !readOnly;
  const [editing, setEditing] = useState(isHorsDomaine && canAct);
  const [draft, setDraft] = useState(isHorsDomaine ? "" : reponse.contenu);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceInfo = SOURCE_LABEL[reponse.source];
  const isPending = reponse.statut === "EN_ATTENTE";
  const isCanonique = reponse.canonique;
  const showBot = isPending || isCanonique;
  const authorLabel = showBot
    ? "TicketAI"
    : (reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur");
  const authorClass = showBot
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-violet-700 dark:text-violet-300";

  function handleError(e: unknown) {
    if (e instanceof LockConflictError) { onLockConflict(e.message); return; }
    setError(e instanceof Error ? e.message : "Erreur");
  }

  async function handleValider() {
    setLoading(true); setError(null);
    try {
      await validerReponse(reponse.id, { validator_id: getValidatorId() });
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleCorriger() {
    if (!draft.trim() || draft === reponse.contenu) { setEditing(false); return; }
    setLoading(true); setError(null);
    try {
      await corrigerReponse(reponse.id, { contenu_corrige: draft, validator_id: getValidatorId() });
      setEditing(false); onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  function handleCancel() { setDraft(reponse.contenu); setEditing(false); setError(null); }

  return (
    <li className="px-5 py-4 space-y-3 animate-in fade-in slide-in-from-bottom-1 duration-300">
      {reponse.question_suivi && (
        <div className="flex gap-3 items-start">
          <UserAvatar name={userEmail ?? "?"} size={36} />
          <div className="flex-1 min-w-0 space-y-1.5">
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">Précision de l'utilisateur</span>
            <div className="bg-emerald-50 dark:bg-emerald-500/[0.08] border border-emerald-100 dark:border-emerald-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
              <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                {reponse.question_suivi}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-3 items-start">
        {showBot ? (
          <BotAvatar pulse={isPending} />
        ) : (
          <UserAvatar name={reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur"} size={36} />
        )}
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-semibold ${authorClass}`}>{authorLabel}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(reponse.created_at)}</span>
            <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${reponseStatutClass(reponse.statut, reponse.canonique)}`}>
              <span className="w-1 h-1 rounded-full bg-current" />
              {reponseStatutLabel(reponse.statut, reponse.canonique)}
            </span>
            {sourceInfo && reponse.source !== "CANONIQUE" && (
              <span className={`text-xs flex items-center gap-1 ${
                reponse.source === "HORS_DOMAINE"
                  ? "text-purple-500 dark:text-purple-400 font-medium"
                  : "text-gray-400 dark:text-gray-500"
              }`}>
                <sourceInfo.icon size={11} aria-hidden="true" />
                {sourceInfo.label}
              </span>
            )}
            {reponse.score_similarite != null && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                · {(reponse.score_similarite * 100).toFixed(0)} % similarité
              </span>
            )}
          </div>

          {editing ? (
            <div className="space-y-3">
              <textarea
                className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y leading-relaxed min-h-[420px]"
                rows={18}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={loading}
                autoFocus
                placeholder={isHorsDomaine ? "Aucun document ne couvre ce sujet. Rédigez une réponse à partir de vos connaissances…" : undefined}
                aria-label="Contenu corrigé"
              />
              {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCorriger}
                  disabled={loading || !draft.trim()}
                  className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                >
                  <Check size={14} aria-hidden="true" /> Valider la correction
                </button>
                {!isHorsDomaine && (
                  <button
                    onClick={handleCancel}
                    disabled={loading}
                    className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                  >
                    <X size={14} aria-hidden="true" /> Annuler
                  </button>
                )}
              </div>
            </div>
          ) : isHorsDomaine && !reponse.contenu_corrige ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 italic px-1">
              Sujet non couvert — une réponse manuelle est attendue.
            </p>
          ) : (
            <div className="bg-white/90 dark:bg-white/[0.07] border border-gray-200/70 dark:border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                {reponse.contenu_corrige ?? reponse.contenu}
              </p>
            </div>
          )}

          {canAct && !editing && (
            <div className="flex items-center gap-2 flex-wrap">
              {reponse.source !== "HORS_DOMAINE" && (
                <button
                  onClick={handleValider}
                  disabled={loading}
                  className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                >
                  <ThumbsUp size={14} aria-hidden="true" /> Valider
                </button>
              )}
              <button
                onClick={() => setEditing(true)}
                disabled={loading}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
              >
                <Pencil size={14} aria-hidden="true" /> {isHorsDomaine ? "Rédiger une réponse" : "Corriger"}
              </button>
              {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
