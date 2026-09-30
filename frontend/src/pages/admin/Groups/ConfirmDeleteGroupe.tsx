import { useRef } from "react";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import type { Groupe } from "../../../types/index.tsx";
import { useDialogFocus } from "../../../hooks/useDialogFocus";

type Props = {
  groupe: Groupe;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
  error?: string | null;
};

export default function ConfirmDeleteGroupe({ groupe, onConfirm, onCancel, isPending, error }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(dialogRef, { onClose: onCancel });

  return (
    <div
      ref={dialogRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-group-title"
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
            <AlertTriangle size={18} className="text-red-600 dark:text-red-400" aria-hidden="true" />
          </div>
          <div>
            <p id="delete-group-title" className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Supprimer ce groupe ?
            </p>
            <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[220px]">
              {groupe.nom}
            </p>
          </div>
        </div>
        <p className="text-xs text-gray-600 dark:text-muted-foreground">
          Le groupe sera supprimé ainsi que toutes ses associations membres. Cette action est
          irréversible. Les tickets déjà transmis à ce domaine resteront accessibles jusqu'à
          réaffectation.
        </p>
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
            {isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} aria-hidden="true" />}
            Supprimer
          </button>
        </div>
      </div>
    </div>
  );
}
