import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCheck, ChevronDown, Loader2, Send, X } from "lucide-react";

interface SuiviMutation {
  mutate: () => void;
  isPending: boolean;
  isError: boolean;
  isSuccess: boolean;
  error: unknown;
}

interface TicketActionsBarProps {
  suivi: SuiviMutation;
  precision: string;
  setPrecision: (v: string) => void;
  canSubmitSuivi: boolean;
  onResolve: () => void;
}

export function TicketActionsBar({
  suivi, precision, setPrecision, canSubmitSuivi, onResolve,
}: TicketActionsBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [showPrecision, setShowPrecision] = useState(false);

  useEffect(() => {
    if (showPrecision) textareaRef.current?.focus();
  }, [showPrecision]);

  function handlePrecisionChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setPrecision(e.target.value);
    const ta = e.currentTarget;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }

  const showSuiviSuccess = suivi.isSuccess && !suivi.isPending && !precision;

  return (
    <div className="glass-card rounded-2xl p-5 space-y-3">
      {showSuiviSuccess && (
        <div role="status" className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400 pb-1">
          <CheckCheck size={13} aria-hidden="true" />
          Votre précision a bien été envoyée.
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100">Cette réponse vous convient-elle ?</p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => { setShowPrecision(false); setPrecision(""); onResolve(); }}
            className="inline-flex items-center gap-2 rounded-lg bg-primary hover:bg-primary-hover text-primary-foreground text-xs font-medium px-3 py-2 transition-colors"
          >
            <CheckCheck size={13} aria-hidden="true" />
            Oui, c'est résolu
          </button>
          {!showPrecision && (
            <button
              type="button"
              onClick={() => setShowPrecision(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 text-xs font-medium px-3 py-2 transition-colors"
            >
              Non, apporter une précision
              <ChevronDown size={12} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {showPrecision && (
        <div className="border-t border-gray-100 dark:border-white/[0.06] pt-3 space-y-3">
          <div className="flex items-center justify-between">
            <label htmlFor="precision" className="text-sm font-semibold text-gray-900 dark:text-white">
              Apporter une précision
            </label>
            <button
              type="button"
              onClick={() => { setShowPrecision(false); setPrecision(""); }}
              aria-label="Fermer"
              className="p-1.5 rounded-md text-muted-foreground hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 dark:hover:text-gray-200 transition-colors"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>

          <textarea
            ref={textareaRef}
            id="precision"
            value={precision}
            onChange={handlePrecisionChange}
            maxLength={2000}
            placeholder="Ex. : Et dans le cas d'un contrat à durée déterminée ?"
            className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2.5 text-gray-800 dark:text-gray-100 bg-white dark:bg-white/[0.03] placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none overflow-hidden transition-colors"
            style={{ minHeight: "80px", maxHeight: "200px" }}
            aria-describedby={suivi.isError ? "suivi-error" : undefined}
          />

          {suivi.isError && (
            <div id="suivi-error" role="alert" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
              <AlertCircle size={13} aria-hidden="true" />
              {suivi.error instanceof Error ? suivi.error.message : "Une erreur est survenue"}
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => suivi.mutate()}
              disabled={!canSubmitSuivi}
              className="inline-flex items-center gap-2 rounded-lg bg-primary hover:bg-primary-hover text-primary-foreground text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {suivi.isPending
                ? <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                : <Send size={15} aria-hidden="true" />}
              Envoyer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
