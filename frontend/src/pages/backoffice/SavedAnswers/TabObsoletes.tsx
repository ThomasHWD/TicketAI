import { AlertTriangle, RotateCcw, Trash2 } from "lucide-react";
import { formatDate } from "../../../lib/ticketStatus";
import type { ReponseObsolete } from "../../../types";
import ExpandableText from "./ExpandableText";
import { contenuServi, depuis, type CibleSuppression } from "./utils";

type Props = {
  items: ReponseObsolete[];
  loading: boolean;
  error: Error | null;
  total: number;
  searchQuery: string;
  isPendingRestore: boolean;
  restoreError: Error | null;
  onRestore: (id: string) => void;
  onDeleteTarget: (t: CibleSuppression) => void;
};

export default function TabObsoletes({
  items,
  loading,
  error,
  total,
  searchQuery,
  isPendingRestore,
  restoreError,
  onRestore,
  onDeleteTarget,
}: Props) {
  const q = searchQuery.trim().toLowerCase();

  return (
    <>
      <div className="divide-y divide-gray-200 dark:divide-white/5">
        {loading && (
          <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">Chargement…</p>
        )}
        {error && (
          <p className="px-6 py-12 text-center text-red-600 dark:text-red-400">
            {error instanceof Error ? error.message : "Erreur de chargement"}
          </p>
        )}
        {!loading && !error && total === 0 && (
          <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
            Aucune réponse obsolète
          </p>
        )}
        {!loading && !error && total > 0 && items.length === 0 && q && (
          <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
            Aucun résultat pour « {searchQuery} » sur cette page.
          </p>
        )}

        {!loading &&
          items.map((r: ReponseObsolete) => (
            <article
              key={r.reponse_id}
              className="px-6 py-4 space-y-2.5 hover:bg-gray-50/60 dark:hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0 space-y-1">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100 leading-snug">
                    {r.question}
                  </p>
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    {r.canonique && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 text-xs font-medium">
                        canonique
                      </span>
                    )}
                    <span>{r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}</span>
                    <span className="text-gray-300 dark:text-gray-600">·</span>
                    <span
                      className="truncate max-w-[14rem]"
                      title={r.document_filename ?? undefined}
                    >
                      {r.document_filename ?? "Document inconnu"}
                    </span>
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 shrink-0">
                      {r.document_supprime
                        ? "supprimé"
                        : r.obsolete_version
                          ? `v${r.obsolete_version}`
                          : "mis à jour"}
                    </span>
                    <span
                      className="shrink-0"
                      title={r.obsolete_at ? formatDate(r.obsolete_at) : undefined}
                    >
                      {depuis(r.obsolete_at)}
                    </span>
                  </div>
                </div>
              </div>

              <ExpandableText text={contenuServi(r)} />

              {r.analyse_justification && (
                <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-300">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  <span>{r.analyse_justification}</span>
                </p>
              )}

              <div className="flex items-center justify-end gap-1.5">
                <button
                  onClick={() => onRestore(r.reponse_id)}
                  disabled={isPendingRestore}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  <RotateCcw size={13} />
                  Restaurer
                </button>
                <button
                  onClick={() =>
                    onDeleteTarget({ reponse_id: r.reponse_id, question: r.question, obsolete: true })
                  }
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 text-xs font-medium hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 size={13} />
                  Supprimer
                </button>
              </div>
            </article>
          ))}
      </div>

      {restoreError && (
        <p className="px-6 py-3 text-sm text-red-600 dark:text-red-400 border-t border-gray-200 dark:border-white/10">
          {restoreError instanceof Error ? restoreError.message : "Erreur de restauration"}
        </p>
      )}
    </>
  );
}
