import { AlertCircle, CheckCheck, Clock, Loader2, Send } from "lucide-react";
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
  suiviEnCours: boolean;
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
  suiviEnCours,
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
  if (closed) {
    return (
      <div className="glass-card rounded-2xl p-6 flex items-center gap-3">
        <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400 shrink-0">
          <CheckCheck size={18} aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-medium text-gray-800 dark:text-gray-100">Demande clôturée</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Vous avez indiqué que cette réponse vous convenait.
          </p>
        </div>
      </div>
    );
  }

  if (!hasVisibleAnswer) return null;

  return (
    <div className="glass-card rounded-2xl p-6 space-y-5">
      {suiviEnCours && (
        <div className="flex items-center gap-2 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 px-3 py-2 text-xs text-blue-700 dark:text-blue-300">
          <Clock size={14} aria-hidden="true" />
          Votre précision est en cours de traitement. Vous pourrez la clôturer ou en poser une
          nouvelle une fois qu'elle sera traitée.
        </div>
      )}

      {!showRating ? (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            Cette réponse vous convient-elle ?
          </p>
          <button
            type="button"
            onClick={() => setShowRating(true)}
            disabled={suiviEnCours}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <CheckCheck size={16} />
            Oui, clôturer ma demande
          </button>
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/60 dark:bg-white/[0.03] p-4">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            Évaluez votre expérience{" "}
            <span className="font-normal text-gray-500 dark:text-gray-400">(facultatif)</span>
          </p>
          <StarPicker label="Qualité de la réponse" value={noteQualite} onChange={setNoteQualite} />
          <StarPicker label="Rapidité de traitement" value={noteDelai} onChange={setNoteDelai} />
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => cloture.mutate(true)}
              disabled={cloture.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {cloture.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <CheckCheck size={16} />
              )}
              Clôturer
            </button>
            <button
              type="button"
              onClick={() => cloture.mutate(false)}
              disabled={cloture.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/5 text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Ignorer et clôturer
            </button>
            <button
              type="button"
              onClick={() => setShowRating(false)}
              disabled={cloture.isPending}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 underline underline-offset-2 disabled:opacity-40"
            >
              Annuler
            </button>
          </div>
        </div>
      )}

      {cloture.isError && (
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertCircle size={16} />
          {cloture.error instanceof Error ? cloture.error.message : "Une erreur est survenue"}
        </div>
      )}

      <div className="border-t border-gray-200 dark:border-white/10 pt-5 space-y-3">
        <label
          htmlFor="precision"
          className="block text-sm font-medium text-gray-700 dark:text-gray-200"
        >
          Sinon, apportez une précision
        </label>
        <textarea
          id="precision"
          value={precision}
          onChange={(e) => setPrecision(e.target.value)}
          rows={3}
          disabled={suiviEnCours}
          placeholder="Ex. : Et dans le cas d'un contrat à durée déterminée ?"
          className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y disabled:opacity-50 disabled:cursor-not-allowed"
        />

        {suivi.isError && (
          <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle size={16} />
            {suivi.error instanceof Error ? suivi.error.message : "Une erreur est survenue"}
          </div>
        )}

        <button
          type="button"
          onClick={() => suivi.mutate()}
          disabled={!canSubmitSuivi}
          className="inline-flex items-center gap-2 rounded-lg bg-white/60 dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-200 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {suivi.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Send size={16} />
          )}
          Envoyer la précision
        </button>
      </div>
    </div>
  );
}
