import { useRef } from "react";
import { AlertTriangle, X } from "lucide-react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { CibleSuppression } from "./utils";
import { useDialogFocus } from "../../../hooks/useDialogFocus";

type Props = {
  target: CibleSuppression;
  mutation: UseMutationResult<void, Error, string>;
  onClose: () => void;
};

export default function DeleteModal({ target, mutation, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  useDialogFocus(panelRef, { onClose, initialFocus: cancelBtnRef, closeOnEscape: !mutation.isPending });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={() => !mutation.isPending && onClose()}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-modal-title"
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl border border-gray-200/80 dark:border-white/10 bg-white dark:bg-[#141416] shadow-[0_8px_48px_0_rgba(0,0,0,0.18)] overflow-hidden outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-4 border-b border-gray-100 dark:border-white/8">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-red-50 dark:bg-red-500/10">
              <AlertTriangle size={15} className="text-red-500" aria-hidden="true" />
            </div>
            <div>
              <h3 id="delete-modal-title" className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                {target.obsolete
                  ? "Supprimer définitivement ?"
                  : "Supprimer cette réponse canonique ?"}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Cette action est irréversible.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            aria-label="Fermer"
            className="p-1.5 rounded-md text-muted-foreground hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/8 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          <p className="text-sm text-gray-600 dark:text-muted-foreground leading-relaxed">
            La réponse à{" "}
            <span className="font-medium text-gray-800 dark:text-gray-200">
              «&nbsp;{target.question}&nbsp;»
            </span>{" "}
            sera supprimée définitivement.{" "}
            {target.obsolete
              ? "Elle ne pourra plus être restaurée."
              : "Les futures questions similaires repasseront par le pipeline de génération normal."}
          </p>

          {mutation.isError && (
            <div role="alert" className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-100 dark:border-red-500/15">
              <AlertTriangle size={13} className="shrink-0 text-red-500" aria-hidden="true" />
              <p className="text-xs text-red-600 dark:text-red-400">
                {mutation.error instanceof Error ? mutation.error.message : "Erreur de suppression"}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 pb-5">
          <button
            ref={cancelBtnRef}
            onClick={onClose}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-md border border-gray-200 dark:border-white/12 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/8 disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
          >
            Annuler
          </button>
          <button
            onClick={() => mutation.mutate(target.reponse_id)}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-md bg-red-500 hover:bg-red-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60"
          >
            {mutation.isPending ? "Suppression…" : "Supprimer"}
          </button>
        </div>
      </div>
    </div>
  );
}
