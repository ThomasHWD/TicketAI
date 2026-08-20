import { useRef } from "react";
import { AlertCircle, CheckCheck, Loader2, Send, X } from "lucide-react";
import StarPicker from "../../../components/ui/StarPicker";

interface ClotureMutation {
  mutate: (withNotes: boolean) => void;
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

interface SuiviMutation {
  mutate: () => void;
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

interface TicketActionsProps {
  closed: boolean;
  hasVisibleAnswer: boolean;
  cloture: ClotureMutation;
  showRating: boolean;
  setShowRating: (v: boolean) => void;
  noteQualite: number | null;
  noteDelai: number | null;
  setNoteQualite: (v: number) => void;
  setNoteDelai: (v: number) => void;
  precision: string;
  setPrecision: (v: string) => void;
  suivi: SuiviMutation;
  canSubmitSuivi: boolean;
}

export default function TicketActions({
  closed,
  hasVisibleAnswer,
  cloture,
  showRating,
  setShowRating,
  noteQualite,
  noteDelai,
  setNoteQualite,
  setNoteDelai,
  precision,
  setPrecision,
  suivi,
  canSubmitSuivi,
}: TicketActionsProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handlePrecisionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPrecision(e.target.value);
    const ta = e.currentTarget;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  };

  if (closed) {
    return (
      <div className="glass-card rounded-2xl px-5 py-4 flex items-center gap-3">
        <span className="w-9 h-9 rounded-full bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center shrink-0">
          <CheckCheck size={16} className="text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Demande clôturée</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Vous avez indiqué que cette réponse vous convenait.
          </p>
        </div>
      </div>
    );
  }

  if (!hasVisibleAnswer) return null;

  return (
    <div className="glass-card rounded-2xl overflow-hidden">
      {/* Follow-up section */}
      <div className="p-5 space-y-3">
        <label
          htmlFor="precision"
          className="block text-sm font-semibold text-gray-900 dark:text-white"
        >
          Apporter une précision
        </label>

        <textarea
          ref={textareaRef}
          id="precision"
          value={precision}
          onChange={handlePrecisionChange}
          placeholder="Ex. : Et dans le cas d'un contrat à durée déterminée ?"
          className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-xl px-3 py-2.5 text-gray-800 dark:text-gray-100 bg-white dark:bg-white/[0.03] placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none overflow-hidden transition-colors"
          style={{ minHeight: "80px", maxHeight: "200px" }}
          aria-describedby={suivi.isError ? "suivi-error" : undefined}
        />

        {suivi.isError && (
          <div
            id="suivi-error"
            role="alert"
            className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400"
          >
            <AlertCircle size={13} aria-hidden="true" />
            {suivi.error instanceof Error ? suivi.error.message : "Une erreur est survenue"}
          </div>
        )}

        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => suivi.mutate()}
            disabled={!canSubmitSuivi}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {suivi.isPending ? (
              <Loader2 size={15} className="animate-spin" aria-hidden="true" />
            ) : (
              <Send size={15} aria-hidden="true" />
            )}
            Envoyer
          </button>
        </div>
      </div>

      {/* Closure section */}
      <div className="border-t border-gray-100 dark:border-white/[0.06] px-5 py-4">
        {!showRating ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Cette réponse vous convient-elle ?
            </p>
            <button
              type="button"
              onClick={() => setShowRating(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 text-xs font-medium px-3 py-1.5 transition-colors"
            >
              <CheckCheck size={13} aria-hidden="true" />
              Clôturer le ticket
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  Avant de partir…
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  Comment évaluez-vous votre expérience ?{" "}
                  <span className="italic">Facultatif.</span>
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowRating(false)}
                aria-label="Annuler la clôture"
                className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 dark:hover:text-gray-200 transition-colors shrink-0"
              >
                <X size={15} aria-hidden="true" />
              </button>
            </div>

            <div className="space-y-3">
              <StarPicker
                label="Qualité de la réponse"
                value={noteQualite}
                onChange={setNoteQualite}
              />
              <StarPicker
                label="Rapidité de traitement"
                value={noteDelai}
                onChange={setNoteDelai}
              />
            </div>

            {cloture.isError && (
              <div
                role="alert"
                className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400"
              >
                <AlertCircle size={13} aria-hidden="true" />
                {cloture.error instanceof Error
                  ? cloture.error.message
                  : "Une erreur est survenue"}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 pt-0.5">
              <button
                type="button"
                onClick={() => cloture.mutate(true)}
                disabled={cloture.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {cloture.isPending ? (
                  <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                ) : (
                  <CheckCheck size={15} aria-hidden="true" />
                )}
                Confirmer et clôturer
              </button>
              <button
                type="button"
                onClick={() => cloture.mutate(false)}
                disabled={cloture.isPending}
                className="inline-flex items-center rounded-lg border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 text-sm px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Passer la notation
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
