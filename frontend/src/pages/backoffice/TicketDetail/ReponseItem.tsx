import { useRef, useEffect } from "react";
import { AlertCircle, AlertTriangle, Bot, Check, Sparkles, Archive } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import UserAvatar from "../../../components/ui/UserAvatar";
import { useReponseActions } from "../../../hooks/useReponseActions";
import {
  EditingPanel, ValidationConfirmPanel, RejectionPanel,
  ActionButtons, ContextualHelp,
} from "../../../components/tickets/ReponseActionPanel";
import { getTags } from "../../../lib/api";
import type { TicketReponse, StatutReponse } from "../../../types";
import { formatDate, BotAvatar } from "./utils";
import { renderMarkdown } from "../../../components/ticket/utils";
import { RAISONS } from "../SavedAnswers/utils";

const SOURCE_LABEL: Record<string, { label: string; icon: typeof Bot }> = {
  SUGGESTION:   { label: "Suggestion",   icon: Sparkles },
  CANONIQUE:    { label: "Canonique",    icon: Bot },
  HORS_DOMAINE: { label: "Hors domaine", icon: AlertCircle },
};

function reponseStatutLabel(statut: StatutReponse, canonique: boolean, source?: string | null) {
  if (statut === "VALIDÉE" || statut === "CORRIGÉE") return canonique ? "Canonique" : "Validée";
  if (statut === "REJETÉE") return "Rejetée";
  if (statut === "EN_ATTENTE") return source === "SUGGESTION" ? "Suggestion" : "En attente";
  return statut;
}

function reponseStatutClass(statut: StatutReponse, _canonique: boolean, source?: string | null) {
  if (statut === "REJETÉE")
    return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (statut === "VALIDÉE" || statut === "CORRIGÉE")
    return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "EN_ATTENTE" && source === "SUGGESTION")
    return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20";
  return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
}

function confidenceChip(score: number) {
  if (score >= 0.85) return { label: "Confiance élevée",  className: "text-emerald-700 dark:text-emerald-400" };
  if (score >= 0.70) return { label: "Confiance moyenne", className: "text-amber-700 dark:text-amber-400" };
  return                    { label: "Confiance faible",  className: "text-red-600 dark:text-red-400" };
}

export default function ReponseItem({
  reponse,
  domaine,
  readOnly,
  onChanged,
  onLockConflict,
}: {
  reponse: TicketReponse;
  domaine: string;
  readOnly: boolean;
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}) {
  const validateConfirmRef = useRef<HTMLButtonElement>(null);
  const rejectTextareaRef  = useRef<HTMLTextAreaElement>(null);

  const actions = useReponseActions(reponse, { onChanged, onLockConflict });
  const { isHorsDomaine, isRag, canAct: canActRaw } = actions;
  const canAct = canActRaw && !readOnly;

  const { data: tags = [] } = useQuery({
    queryKey: ["tags-canoniques", domaine],
    queryFn: () => getTags(domaine, true),
    staleTime: 0,
    enabled: (isRag || isHorsDomaine) && canAct,
  });

  const errorId = `edit-error-${reponse.id}`;
  const reponseDate = formatDate(reponse.created_at);

  useEffect(() => { if (actions.confirmingValidation) validateConfirmRef.current?.focus(); }, [actions.confirmingValidation]);
  useEffect(() => { if (actions.confirmingRejection)  rejectTextareaRef.current?.focus();  }, [actions.confirmingRejection]);

  const sourceInfo  = SOURCE_LABEL[reponse.source];
  const isPending   = reponse.statut === "EN_ATTENTE";
  const isCanonique = reponse.canonique;
  const showBot     = isPending || isCanonique;
  const authorLabel = showBot
    ? "TicketAI"
    : (reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur");
  const authorClass = showBot
    ? "text-sm font-semibold text-emerald-700 dark:text-emerald-400"
    : "text-sm font-semibold text-violet-700 dark:text-violet-300";
  const nearCanonical = isPending && reponse.nb_validations >= 2;

  return (
    <li
      data-reponse-item
      className="px-5 py-4 flex gap-3.5 items-start motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 duration-300"
      aria-label={`Réponse — ${authorLabel}`}
    >
      {showBot
        ? <BotAvatar pulse={isPending} />
        : <UserAvatar name={reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur"} size={32} />
      }

      <div className="flex-1 min-w-0 space-y-3">
        {/* Author row */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className={authorClass}>{authorLabel}</span>
          <span className="text-xs text-muted-foreground">{reponseDate}</span>
          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${reponseStatutClass(reponse.statut, reponse.canonique, reponse.source)}`}>
            <span className="w-1 h-1 rounded-full bg-current" aria-hidden="true" />
            {reponseStatutLabel(reponse.statut, reponse.canonique, reponse.source)}
          </span>
          {sourceInfo && reponse.source !== "CANONIQUE" && (
            <span className={`text-xs flex items-center gap-1 ${reponse.source === "HORS_DOMAINE" ? "text-purple-500 dark:text-purple-400 font-medium" : "text-muted-foreground"}`}>
              <sourceInfo.icon size={11} aria-hidden="true" />
              {sourceInfo.label}
            </span>
          )}
          {reponse.score_similarite != null && !isHorsDomaine && (() => {
            const conf = confidenceChip(reponse.score_similarite);
            return (
              <span className={`text-xs ${conf.className}`} title={`Score de similarité brut : ${(reponse.score_similarite * 100).toFixed(0)} %`}>
                · {conf.label}
              </span>
            );
          })()}
          {nearCanonical && (
            <span className="text-xs text-emerald-700 dark:text-emerald-400 font-medium" title="Une validation supplémentaire la rendra canonique">
              · Promotion imminente
            </span>
          )}
          {reponse.obsolete && (
            <span className="inline-flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400" title={`Retirée du service actif${reponse.obsolete_raison ? ` — ${reponse.obsolete_raison}` : ""}`}>
              <Archive size={11} aria-hidden="true" />
              Obsolète
            </span>
          )}
        </div>

        {/* Source context */}
        {isPending && reponse.source === "SUGGESTION" && (
          <p className="text-xs text-muted-foreground -mt-1">
            Réutilise une réponse validée antérieure — vérifiez qu'elle s'applique à ce cas.
          </p>
        )}
        {isPending && reponse.source_a_relire && (
          <div role="note" className="flex items-start gap-1.5 text-xs leading-relaxed text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-lg px-3 py-2">
            <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              La réponse réutilisée est signalée à relire suite à un changement de document
              {reponse.source_analyse_justification
                ? ` : ${reponse.source_analyse_justification}`
                : reponse.source_a_relire_raison && reponse.source_a_relire_raison in RAISONS
                  ? ` : ${RAISONS[reponse.source_a_relire_raison as keyof typeof RAISONS]}`
                  : "."}
              {" "}Vérifiez-la contre le document avant de valider.
            </span>
          </div>
        )}
        {isPending && isRag && (
          <p className="text-xs text-amber-800 dark:text-amber-300 -mt-1">
            Générée par l'IA à partir des documents — relisez attentivement avant de valider.
          </p>
        )}

        {/* Content */}
        {actions.editing ? (
          <EditingPanel
            draft={actions.draft}
            loading={actions.loading}
            error={actions.error}
            errorId={errorId}
            isHorsDomaine={isHorsDomaine}
            reponseDate={reponseDate}
            onDraftChange={actions.updateDraft}
            onSubmit={actions.handleCorriger}
            onCancel={actions.handleCancel}
            tagDraft={actions.tagDraft}
            tags={tags}
            faqVisible={actions.faqVisible}
            onTagChange={actions.setTagDraft}
            onFaqVisibleChange={actions.setFaqVisible}
          />
        ) : isHorsDomaine && !reponse.contenu_corrige ? (
          <p className="text-sm text-muted-foreground italic">
            Sujet non couvert — une réponse manuelle est attendue.
          </p>
        ) : (
          <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
            {renderMarkdown(reponse.contenu_corrige ?? reponse.contenu ?? "")}
          </p>
        )}

        {/* Action area */}
        {canAct && !actions.editing && (
          <div className="flex flex-col gap-2 pt-1 border-t border-gray-100 dark:border-white/[0.07] mt-1">
            {actions.justValidated ? (
              <div role="status" className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400 font-medium py-1">
                <Check size={14} aria-hidden="true" />
                Réponse validée
              </div>
            ) : actions.confirmingValidation ? (
              <ValidationConfirmPanel
                variant={actions.isSuggestion ? "suggestion" : "rag"}
                confirmRef={validateConfirmRef}
                loading={actions.loading}
                error={actions.error}
                tagDraft={actions.tagDraft}
                tags={tags}
                faqVisible={actions.faqVisible}
                onTagChange={actions.setTagDraft}
                onFaqVisibleChange={actions.setFaqVisible}
                onConfirm={actions.handleValider}
                onCancel={() => actions.setConfirmingValidation(false)}
              />
            ) : actions.confirmingRejection ? (
              <RejectionPanel
                textareaRef={rejectTextareaRef}
                loading={actions.loading}
                error={actions.error}
                rejectRaison={actions.rejectRaison}
                onReasonChange={actions.setRejectRaison}
                onReject={actions.handleRejeter}
                onCancel={() => { actions.setConfirmingRejection(false); actions.setRejectRaison(""); actions.setError(null); }}
              />
            ) : (
              <ActionButtons
                isHorsDomaine={isHorsDomaine}
                loading={actions.loading}
                reponseDate={reponseDate}
                error={actions.error}
                onValider={actions.handleValider}
                onEdit={() => actions.setEditing(true)}
                onReject={() => actions.setConfirmingRejection(true)}
                onDismissError={() => actions.setError(null)}
              />
            )}
            {!actions.justValidated && (
              <ContextualHelp reponse={reponse} isRag={isRag} nearCanonical={nearCanonical} />
            )}
          </div>
        )}
      </div>
    </li>
  );
}
