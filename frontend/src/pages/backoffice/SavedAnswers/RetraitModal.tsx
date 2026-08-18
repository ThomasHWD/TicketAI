import { EyeOff, X, AlertTriangle } from "lucide-react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { ReponseSignalee } from "../../../types";

type Props = {
  target: ReponseSignalee;
  mutation: UseMutationResult<void, Error, string>;
  onClose: () => void;
};

export default function RetraitModal({ target, mutation, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Confirmer le retrait"
      onClick={() => !mutation.isPending && onClose()}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-gray-200/80 dark:border-white/10 bg-white dark:bg-[#0d1117] shadow-[0_8px_48px_0_rgba(0,0,0,0.18)] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-4 border-b border-gray-100 dark:border-white/8">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-500/10">
              <EyeOff size={15} className="text-amber-500" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                Retirer cette réponse du service ?
              </h3>
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                La réponse rejoindra l'onglet Obsolètes, restaurable à tout moment.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            aria-label="Fermer"
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/8 disabled:opacity-40 transition-colors"
          >
            <X size={15} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
            La réponse à{" "}
            <span className="font-medium text-gray-800 dark:text-gray-200">
              «&nbsp;{target.question}&nbsp;»
            </span>{" "}
            ne sera plus servie automatiquement. Les questions similaires repasseront par la génération.
            Ses validations sont conservées.
          </p>

          {mutation.isError && (
            <div className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-100 dark:border-red-500/15">
              <AlertTriangle size={13} className="shrink-0 text-red-500" />
              <p className="text-xs text-red-600 dark:text-red-400">
                {mutation.error instanceof Error ? mutation.error.message : "Erreur de retrait"}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 pb-5">
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-xl border border-gray-200 dark:border-white/12 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/8 disabled:opacity-40 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={() => mutation.mutate(target.reponse_id)}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending ? "Retrait…" : "Retirer du service"}
          </button>
        </div>
      </div>
    </div>
  );
}
