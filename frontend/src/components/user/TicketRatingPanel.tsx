import { AlertCircle, CheckCheck, Loader2, X } from "lucide-react";
import StarPicker from "../ui/StarPicker";

interface ClotureMutation {
  mutate: (withNotes: boolean) => void;
  isPending: boolean;
  isError: boolean;
  error: unknown;
}

interface TicketRatingPanelProps {
  cloture: ClotureMutation;
  noteQualite: number | null;
  noteDelai: number | null;
  setNoteQualite: (v: number) => void;
  setNoteDelai: (v: number) => void;
  onCancel: () => void;
}

export function TicketRatingPanel({
  cloture, noteQualite, noteDelai, setNoteQualite, setNoteDelai, onCancel,
}: TicketRatingPanelProps) {
  return (
    <div className="glass-card rounded-2xl p-5 space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">Avant de partir…</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Comment évaluez-vous votre expérience ? <span className="italic">Facultatif.</span>
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Annuler"
          className="p-2 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-white/5 dark:hover:text-gray-200 transition-colors shrink-0"
        >
          <X size={15} aria-hidden="true" />
        </button>
      </div>

      <div className="space-y-3">
        <StarPicker label="Qualité de la réponse" value={noteQualite} onChange={setNoteQualite} />
        <StarPicker label="Rapidité de traitement" value={noteDelai} onChange={setNoteDelai} />
      </div>

      {cloture.isError && (
        <div role="alert" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
          <AlertCircle size={13} aria-hidden="true" />
          {cloture.error instanceof Error ? cloture.error.message : "Une erreur est survenue"}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-0.5">
        <button
          type="button"
          onClick={() => cloture.mutate(true)}
          disabled={cloture.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {cloture.isPending
            ? <Loader2 size={15} className="animate-spin" aria-hidden="true" />
            : <CheckCheck size={15} aria-hidden="true" />}
          Confirmer
        </button>
        <button
          type="button"
          onClick={() => cloture.mutate(false)}
          disabled={cloture.isPending}
          className="inline-flex items-center text-sm px-4 py-2 text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Fermer le ticket sans noter
        </button>
      </div>
    </div>
  );
}
