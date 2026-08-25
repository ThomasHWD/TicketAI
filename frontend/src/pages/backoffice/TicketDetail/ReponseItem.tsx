import { useState, useRef, useEffect } from "react";
import { AlertCircle, Bot, Check, Pencil, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { corrigerReponse, validerReponse, rejeterReponse, LockConflictError } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import { getValidatorId } from "../../../lib/currentUser";
import type { TicketReponse, StatutReponse } from "../../../types";
import { formatDate, BotAvatar } from "./utils";
import { renderMarkdown } from "../../../components/ticket/utils";

export const SOURCE_LABEL: Record<string, { label: string; icon: typeof Bot }> = {
  SUGGESTION:   { label: "Suggestion",   icon: Sparkles },
  CANONIQUE:    { label: "Canonique",    icon: Bot },
  HORS_DOMAINE: { label: "Hors domaine", icon: AlertCircle },
};

export function reponseStatutLabel(statut: StatutReponse, canonique: boolean, source?: string | null) {
  if (statut === "VALIDÉE" || statut === "CORRIGÉE") return canonique ? "Canonique" : "Validée";
  if (statut === "REJETÉE") return "Rejetée";
  if (statut === "EN_ATTENTE") return source === "SUGGESTION" ? "Suggestion" : "En attente";
  return statut;
}

export function reponseStatutClass(statut: StatutReponse, canonique: boolean, source?: string | null) {
  if (statut === "REJETÉE")
    return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (statut === "VALIDÉE" || statut === "CORRIGÉE")
    return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "EN_ATTENTE" && source === "SUGGESTION")
    return "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20";
  return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
}

function confidenceChip(score: number) {
  if (score >= 0.85) return { label: "Confiance élevée", className: "text-emerald-600 dark:text-emerald-400" };
  if (score >= 0.70) return { label: "Confiance moyenne", className: "text-amber-600 dark:text-amber-400" };
  return { label: "Confiance faible", className: "text-red-500 dark:text-red-400" };
}

export default function ReponseItem({
  reponse,
  readOnly,
  onChanged,
  onLockConflict,
}: {
  reponse: TicketReponse;
  readOnly: boolean;
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}) {
  const isHorsDomaine = reponse.source === "HORS_DOMAINE";
  const isRag = reponse.source === "LLM";
  const canAct = reponse.statut === "EN_ATTENTE" && !readOnly;

  const DRAFT_KEY = `ticketai-draft-${reponse.id}`;
  const [editing, setEditing] = useState(isHorsDomaine && canAct);
  const [draft, setDraft] = useState(() => {
    if (isHorsDomaine) return localStorage.getItem(DRAFT_KEY) ?? "";
    return reponse.contenu;
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingValidation, setConfirmingValidation] = useState(false);
  const [justValidated, setJustValidated] = useState(false);
  const [confirmingRejection, setConfirmingRejection] = useState(false);
  const [rejectRaison, setRejectRaison] = useState("");
  const validateConfirmRef = useRef<HTMLButtonElement>(null);
  const rejectTextareaRef = useRef<HTMLTextAreaElement>(null);

  const errorId = `edit-error-${reponse.id}`;

  useEffect(() => {
    if (confirmingValidation) validateConfirmRef.current?.focus();
  }, [confirmingValidation]);

  useEffect(() => {
    if (confirmingRejection) rejectTextareaRef.current?.focus();
  }, [confirmingRejection]);
  const sourceInfo = SOURCE_LABEL[reponse.source];
  const isPending = reponse.statut === "EN_ATTENTE";
  const isCanonique = reponse.canonique;
  const showBot = isPending || isCanonique;
  const authorLabel = showBot
    ? "TicketAI"
    : (reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur");
  const authorClass = showBot
    ? "text-sm font-semibold text-emerald-700 dark:text-emerald-400"
    : "text-sm font-semibold text-violet-700 dark:text-violet-300";

  const reponseDate = formatDate(reponse.created_at);
  const nearCanonical = isPending && reponse.nb_validations >= 2;

  function updateDraft(value: string) {
    setDraft(value);
    if (isHorsDomaine) {
      if (value) localStorage.setItem(DRAFT_KEY, value);
      else localStorage.removeItem(DRAFT_KEY);
    }
  }

  function handleError(e: unknown) {
    if (e instanceof LockConflictError) { onLockConflict(e.message); return; }
    setError(e instanceof Error ? e.message : "Une erreur est survenue. Vérifiez votre connexion et réessayez.");
  }

  async function handleValider() {
    if (isRag && !confirmingValidation) {
      setConfirmingValidation(true);
      return;
    }
    setConfirmingValidation(false);
    setLoading(true); setError(null);
    try {
      await validerReponse(reponse.id, { validator_id: getValidatorId() });
      setJustValidated(true);
      setTimeout(() => onChanged(), 250);
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleCorriger() {
    if (!draft.trim() || draft.trim() === reponse.contenu.trim()) { setEditing(false); return; }
    setLoading(true); setError(null);
    try {
      await corrigerReponse(reponse.id, { contenu_corrige: draft, validator_id: getValidatorId() });
      if (isHorsDomaine) localStorage.removeItem(DRAFT_KEY);
      setEditing(false);
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleRejeter() {
    setLoading(true); setError(null);
    try {
      await rejeterReponse(reponse.id, { validator_id: getValidatorId(), raison: rejectRaison.trim() || undefined });
      setConfirmingRejection(false);
      setRejectRaison("");
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  function handleCancel() {
    setDraft(isHorsDomaine ? (localStorage.getItem(DRAFT_KEY) ?? "") : reponse.contenu);
    setEditing(false);
    setError(null);
  }

  return (
    <li
      className="px-5 py-4 flex gap-3.5 items-start motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 duration-300"
      aria-label={`Réponse — ${authorLabel}`}
    >
      {showBot ? (
        <BotAvatar pulse={isPending} />
      ) : (
        <UserAvatar name={reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur"} size={32} />
      )}

      <div className="flex-1 min-w-0 space-y-3">
          {/* Author row */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={authorClass}>{authorLabel}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">{reponseDate}</span>
            <span
              className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${reponseStatutClass(reponse.statut, reponse.canonique, reponse.source)}`}
            >
              <span className="w-1 h-1 rounded-full bg-current" aria-hidden="true" />
              {reponseStatutLabel(reponse.statut, reponse.canonique, reponse.source)}
            </span>
            {sourceInfo && reponse.source !== "CANONIQUE" && (
              <span
                className={`text-xs flex items-center gap-1 ${
                  reponse.source === "HORS_DOMAINE"
                    ? "text-purple-500 dark:text-purple-400 font-medium"
                    : "text-gray-400 dark:text-gray-500"
                }`}
              >
                <sourceInfo.icon size={11} aria-hidden="true" />
                {sourceInfo.label}
              </span>
            )}
            {reponse.score_similarite != null && !isHorsDomaine && (() => {
              const conf = confidenceChip(reponse.score_similarite);
              return (
                <span
                  className={`text-xs ${conf.className}`}
                  title={`Score de similarité brut : ${(reponse.score_similarite * 100).toFixed(0)} %`}
                >
                  · {conf.label}
                </span>
              );
            })()}
            {nearCanonical && (
              <span
                className="text-xs text-emerald-600 dark:text-emerald-400 font-medium"
                title="Une validation supplémentaire la rendra canonique"
              >
                · Promotion imminente
              </span>
            )}
          </div>

          {/* Source context */}
          {isPending && reponse.source === "SUGGESTION" && (
            <p className="text-xs text-gray-400 dark:text-gray-500 -mt-1">
              Réutilise une réponse validée antérieure — vérifiez qu'elle s'applique à ce cas.
            </p>
          )}
          {isPending && isRag && (
            <p className="text-xs text-amber-600/80 dark:text-amber-400/80 -mt-1">
              Générée par l'IA à partir des documents — relisez attentivement avant de valider.
            </p>
          )}

          {/* Content */}
          {editing ? (
            <div className="space-y-3">
              <textarea
                className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y leading-relaxed min-h-[200px] sm:min-h-[420px] transition-shadow"
                rows={18}
                value={draft}
                onChange={(e) => updateDraft(e.target.value)}
                disabled={loading}
                autoFocus
                placeholder={
                  isHorsDomaine
                    ? "Aucun document ne couvre ce sujet. Rédigez une réponse à partir de vos connaissances…"
                    : undefined
                }
                aria-label="Contenu corrigé"
                aria-describedby={error ? errorId : undefined}
              />
              {isHorsDomaine && draft && (
                <p className="text-[11px] text-gray-400 dark:text-gray-500">Brouillon sauvegardé localement.</p>
              )}
              {error && (
                <p id={errorId} className="text-xs text-red-600 dark:text-red-400" role="alert">
                  {error}
                </p>
              )}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCorriger}
                  disabled={loading || !draft.trim()}
                  aria-label={`Valider la correction de la réponse du ${reponseDate}`}
                  title="Soumettre la version corrigée — elle sera envoyée à l'employé"
                  className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
                >
                  <Check size={14} aria-hidden="true" />
                  Valider la correction
                </button>
                <button
                  onClick={handleCancel}
                  disabled={loading}
                  className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                >
                  <X size={14} aria-hidden="true" />
                  Annuler
                </button>
              </div>
            </div>
          ) : isHorsDomaine && !reponse.contenu_corrige ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 italic">
              Sujet non couvert — une réponse manuelle est attendue.
            </p>
          ) : (
            <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
              {renderMarkdown(reponse.contenu_corrige ?? reponse.contenu)}
            </p>
          )}

          {/* Action buttons */}
          {canAct && !editing && (
            <div className="flex flex-col gap-2 pt-1 border-t border-gray-100 dark:border-white/[0.07] mt-1">
              {justValidated ? (
                <div role="status" className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400 font-medium py-1">
                  <Check size={14} aria-hidden="true" />
                  Réponse validée
                </div>
              ) : confirmingValidation ? (
                <div role="alert" className="p-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 space-y-2.5">
                  <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
                    Confirmer la validation de cette réponse générée par l'IA ?
                  </p>
                  {error && (
                    <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>
                  )}
                  <div className="flex items-center gap-2">
                    <button
                      ref={validateConfirmRef}
                      onClick={handleValider}
                      disabled={loading}
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
                    >
                      <ThumbsUp size={14} aria-hidden="true" />
                      Oui, valider
                    </button>
                    <button
                      onClick={() => setConfirmingValidation(false)}
                      disabled={loading}
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors"
                    >
                      <X size={14} aria-hidden="true" />
                      Annuler
                    </button>
                  </div>
                </div>
              ) : confirmingRejection ? (
                <div role="alert" className="p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 space-y-2.5">
                  <p className="text-xs font-medium text-red-700 dark:text-red-300">
                    Confirmer le rejet de cette réponse ?
                  </p>
                  <textarea
                    ref={rejectTextareaRef}
                    value={rejectRaison}
                    onChange={(e) => setRejectRaison(e.target.value)}
                    placeholder="Raison du rejet (optionnel)"
                    rows={2}
                    disabled={loading}
                    className="w-full text-sm text-gray-700 dark:text-gray-100 bg-white dark:bg-white/5 border border-red-200 dark:border-red-500/30 rounded-md p-2 focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
                    aria-label="Raison du rejet"
                  />
                  {error && (
                    <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>
                  )}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleRejeter}
                      disabled={loading}
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 font-medium transition-colors"
                    >
                      <ThumbsDown size={14} aria-hidden="true" />
                      Oui, rejeter
                    </button>
                    <button
                      onClick={() => { setConfirmingRejection(false); setRejectRaison(""); setError(null); }}
                      disabled={loading}
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
                    >
                      <X size={14} aria-hidden="true" />
                      Annuler
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  {reponse.source !== "HORS_DOMAINE" && (
                    <span className="inline-flex items-center gap-1.5">
                      <button
                        onClick={handleValider}
                        disabled={loading}
                        data-action="valider"
                        aria-label={`Valider la réponse du ${reponseDate}`}
                        title="Valider → envoie la réponse à l'employé et incrémente son score de validation (→ canonique à 3 validations)"
                        className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
                      >
                        <ThumbsUp size={14} aria-hidden="true" />
                        Valider
                      </button>
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1.5">
                    <button
                      onClick={() => setEditing(true)}
                      disabled={loading}
                      data-action="corriger"
                      aria-label={isHorsDomaine ? `Rédiger une réponse pour la demande du ${reponseDate}` : `Corriger la réponse du ${reponseDate}`}
                      title={isHorsDomaine ? "Rédiger une réponse manuelle pour ce sujet non couvert" : "Modifier la réponse avant validation"}
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
                    >
                      <Pencil size={14} aria-hidden="true" />
                      {isHorsDomaine ? "Rédiger une réponse" : "Corriger"}
                    </button>
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <button
                      onClick={() => setConfirmingRejection(true)}
                      disabled={loading}
                      data-action="rejeter"
                      aria-label={`Rejeter la réponse du ${reponseDate}`}
                      title="Rejeter cette réponse — elle ne sera pas envoyée à l'employé"
                      className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                    >
                      <ThumbsDown size={14} aria-hidden="true" />
                      Rejeter
                    </button>
                  </span>
                  {error && (
                    <p className="text-xs text-red-600 dark:text-red-400 w-full" role="alert">
                      {error}{" "}
                      <button
                        onClick={() => setError(null)}
                        className="underline hover:no-underline ml-1"
                      >
                        Fermer
                      </button>
                    </p>
                  )}
                </div>
              )}

              {/* Contextual help */}
              {!justValidated && (
                <details className="group mt-0.5">
                  <summary className="text-[11px] text-gray-400 dark:text-gray-500 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300 transition-colors list-none flex items-center gap-1 select-none">
                    <span className="transition-transform group-open:rotate-90 inline-block text-[10px]" aria-hidden="true">▶</span>
                    À propos de ces actions
                  </summary>
                  <div className="mt-2 p-3 rounded-xl bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.06] text-xs text-gray-600 dark:text-gray-300 space-y-1.5">
                    <p><span className="font-medium">Valider</span> : approuve et envoie la réponse à l'employé. Chaque validation incrémente son score (seuil canonique : 3).</p>
                    <p><span className="font-medium">Corriger</span> : modifie la réponse avant envoi. Le brouillon est préservé localement.</p>
                    {reponse.source === "SUGGESTION" && (
                      <p className="text-amber-600/80 dark:text-amber-400/80"><span className="font-medium">Suggestion</span> : réutilise une réponse validée. Assurez-vous qu'elle s'applique à ce cas précis.</p>
                    )}
                    {isRag && (
                      <p className="text-amber-600/80 dark:text-amber-400/80"><span className="font-medium">Réponse IA</span> : générée à partir des documents internes — peut contenir des imprécisions.</p>
                    )}
                    {nearCanonical && (
                      <p className="text-emerald-600 dark:text-emerald-400"><span className="font-medium">Promotion imminente</span> : cette réponse a {reponse.nb_validations} validation(s). La prochaine la rendra canonique.</p>
                    )}
                    <p><span className="font-medium">Rejeter</span> : refuse la réponse — elle ne sera pas envoyée. Une raison peut être précisée.</p>
                    <p className="text-gray-400 dark:text-gray-500">Raccourcis : <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">V</kbd> Valider · <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">E</kbd> Corriger · <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">R</kbd> Rejeter · <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">Alt+←</kbd> Retour</p>
                  </div>
                </details>
              )}
            </div>
          )}
        </div>
    </li>
  );
}
