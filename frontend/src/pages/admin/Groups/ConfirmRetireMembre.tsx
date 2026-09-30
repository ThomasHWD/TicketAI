import { useRef } from "react";
import { Loader2, UserMinus } from "lucide-react";
import type { UserSummary } from "../../../types/index.tsx";
import { displayName } from "./utils";
import { useDialogFocus } from "../../../hooks/useDialogFocus";

type Props = {
  membre: UserSummary;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
  error?: string | null;
  isLastChef?: boolean;
};

export default function ConfirmRetireMembre({ membre, onConfirm, onCancel, isPending, error, isLastChef }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, { onClose: onCancel });

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="retire-membre-title"
    >
      <button
        type="button"
        tabIndex={-1}
        aria-hidden="true"
        onClick={onCancel}
        className="absolute inset-0 cursor-default bg-black/30 dark:bg-black/60 backdrop-blur-sm"
      />
      <div
        className="relative bg-white dark:bg-[#141416] shadow-2xl border border-gray-200 dark:border-white/10 rounded-2xl w-full max-w-sm p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-red-100 dark:bg-red-400/15 shrink-0">
            <UserMinus size={18} className="text-red-600 dark:text-red-400" aria-hidden="true" />
          </div>
          <div>
            <p id="retire-membre-title" className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Retirer ce membre ?
            </p>
            <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[220px]">
              {displayName(membre)}
            </p>
          </div>
        </div>
        <p className="text-xs text-gray-600 dark:text-muted-foreground">
          Le gestionnaire perdra l'accès aux tickets et documents de ce domaine jusqu'à être
          réaffecté.
        </p>
        {isLastChef && (
          <div className="px-3 py-2.5 rounded-lg bg-amber-50 dark:bg-amber-400/10 border border-amber-200 dark:border-amber-400/20">
            <p className="text-xs text-amber-700 dark:text-amber-400 leading-relaxed">
              Ce gestionnaire est le <strong>seul chef d'équipe</strong>. Après retrait, aucun validateur prioritaire ne sera désigné pour ce domaine.
            </p>
          </div>
        )}
        {error && (
          <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>
        )}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="flex-1 px-4 py-2 rounded-md text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500 text-white disabled:opacity-50 transition-colors"
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : <UserMinus size={14} aria-hidden="true" />}
            Retirer
          </button>
        </div>
      </div>
    </div>
  );
}
