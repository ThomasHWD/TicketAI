import { Link } from "react-router-dom";
import { CheckCheck, Loader2, PenLine, X } from "lucide-react";
import { TicketRatingPanel } from "../../../components/user/TicketRatingPanel";
import { TicketActionsBar } from "../../../components/user/TicketActionsBar";

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
  isSuccess: boolean;
  error: unknown;
}

interface TicketActionsProps {
  closed: boolean;
  hasVisibleAnswer: boolean;
  rejected?: boolean;
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
  closed, hasVisibleAnswer, rejected = false,
  cloture, showRating, setShowRating,
  noteQualite, noteDelai, setNoteQualite, setNoteDelai,
  precision, setPrecision, suivi, canSubmitSuivi,
}: TicketActionsProps) {
  if (closed) {
    if (rejected) return null;
    return (
      <div className="glass-card rounded-2xl px-5 py-4 flex items-center gap-3">
        <span className="w-9 h-9 rounded-full bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center shrink-0">
          <CheckCheck size={16} className="text-emerald-600 dark:text-emerald-400" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Demande marquée comme résolue</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Vous avez indiqué que cette réponse vous convenait.</p>
        </div>
      </div>
    );
  }

  if (!hasVisibleAnswer) {
    if (!rejected) return null;
    return (
      <div className="glass-card rounded-2xl px-5 py-4 flex items-start gap-3">
        <span className="w-9 h-9 rounded-full bg-red-50 dark:bg-red-500/10 flex items-center justify-center shrink-0 mt-0.5">
          <X size={16} className="text-red-500 dark:text-red-400" aria-hidden="true" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Aucune réponse disponible</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 mb-4">
            Le service d'assistance n'a pas pu répondre à cette demande. Vous pouvez reformuler votre question ou fermer le ticket.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/nouveau-ticket" className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 transition-colors">
              <PenLine size={14} aria-hidden="true" />Reformuler ma question
            </Link>
            <button
              type="button"
              onClick={() => cloture.mutate(false)}
              disabled={cloture.isPending}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40"
            >
              {cloture.isPending
                ? <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                : <CheckCheck size={15} aria-hidden="true" />}
              Fermer le ticket
            </button>
          </div>
          {cloture.isError && (
            <p className="mt-2 text-xs text-red-600 dark:text-red-400" role="alert">
              {cloture.error instanceof Error ? cloture.error.message : "Une erreur est survenue"}
            </p>
          )}
        </div>
      </div>
    );
  }

  if (showRating) {
    return (
      <TicketRatingPanel
        cloture={cloture}
        noteQualite={noteQualite}
        noteDelai={noteDelai}
        setNoteQualite={setNoteQualite}
        setNoteDelai={setNoteDelai}
        onCancel={() => setShowRating(false)}
      />
    );
  }

  return (
    <TicketActionsBar
      suivi={suivi}
      precision={precision}
      setPrecision={setPrecision}
      canSubmitSuivi={canSubmitSuivi}
      onResolve={() => setShowRating(true)}
    />
  );
}
