import type { UseMutationResult } from "@tanstack/react-query";
import type { CibleSuppression } from "./utils";

type Props = {
  target: CibleSuppression;
  mutation: UseMutationResult<void, Error, string>;
  onClose: () => void;
};

export default function DeleteModal({ target, mutation, onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Confirmer la suppression"
      onClick={() => !mutation.isPending && onClose()}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-white/60 dark:border-white/10 bg-white dark:bg-[#0b0f1a] p-6 shadow-[0_8px_40px_0_rgba(0,0,0,0.25)]"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
          {target.obsolete
            ? "Supprimer définitivement cette réponse ?"
            : "Supprimer cette réponse canonique ?"}
        </h3>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          La réponse à «&nbsp;{target.question}&nbsp;» sera supprimée définitivement.{" "}
          {target.obsolete
            ? "Elle ne pourra plus être restaurée."
            : "Les futures questions similaires repasseront par le pipeline de génération normal."}{" "}
          Cette action est irréversible.
        </p>
        {mutation.isError && (
          <p className="mt-3 text-sm text-red-600 dark:text-red-400">
            {mutation.error instanceof Error ? mutation.error.message : "Erreur de suppression"}
          </p>
        )}
        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={() => mutation.mutate(target.reponse_id)}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {mutation.isPending ? "Suppression…" : "Supprimer"}
          </button>
        </div>
      </div>
    </div>
  );
}
