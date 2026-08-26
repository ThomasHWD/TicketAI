import { AlertTriangle, RotateCcw, Trash2 } from "lucide-react";
import { formatDate } from "../../../lib/ticketStatus";
import type { ReponseObsolete } from "../../../types";
import ExpandableText from "./ExpandableText";
import InfoTooltip from "./InfoTooltip";
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
  onRetry: () => void;
};

function RaisonBadge({ raison }: { raison: ReponseObsolete["obsolete_raison"] }) {
  const map: Record<NonNullable<typeof raison>, { label: string; cls: string }> = {
    CONTREDITE_PAR_MAJ: { label: "contredite", cls: "bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400" },
    DOC_MIS_A_JOUR:     { label: "doc mis à jour", cls: "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-400" },
    DOC_SUPPRIMÉ:       { label: "doc supprimé", cls: "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-400" },
    RETIRÉ_À_LA_MAIN:   { label: "retrait manuel", cls: "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-400" },
  };
  if (!raison || !map[raison]) return null;
  const { label, cls } = map[raison];
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${cls}`}>{label}</span>
  );
}

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
  onRetry,
}: Props) {
  const q = searchQuery.trim().toLowerCase();

  if (loading) {
    return (
      <div aria-busy="true" className="divide-y divide-gray-100 dark:divide-white/5">
        {[...Array(4)].map((_, i) => (
          <div key={i} aria-hidden="true" className="px-5 py-4 space-y-2 animate-pulse">
            <div className="h-3.5 w-2/3 rounded bg-gray-100 dark:bg-white/8" />
            <div className="h-3 w-full rounded bg-gray-100 dark:bg-white/5" />
            <div className="h-3 w-4/5 rounded bg-gray-100 dark:bg-white/5" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div role="alert" className="px-5 py-12 text-center space-y-3">
        <p className="text-sm text-red-500 dark:text-red-400">
          {error instanceof Error ? error.message : "Erreur de chargement"}
        </p>
        <button
          onClick={onRetry}
          className="text-xs text-gray-500 dark:text-gray-400 underline underline-offset-2 hover:text-gray-700 dark:hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 rounded-sm"
        >
          Réessayer
        </button>
      </div>
    );
  }

  if (total === 0 && q) {
    return (
      <p className="px-5 py-12 text-center text-sm text-gray-500 dark:text-gray-400">
        Aucun résultat pour <span className="font-medium text-gray-600 dark:text-gray-300">«&nbsp;{searchQuery}&nbsp;»</span>.
      </p>
    );
  }

  if (total === 0) {
    return (
      <div className="px-5 py-16 text-center space-y-1">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Aucune réponse obsolète</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">Les réponses retirées du service apparaissent ici.</p>
      </div>
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {items.map((r) => (
          <article
            key={r.reponse_id}
            className="px-5 py-4 hover:bg-gray-50/70 dark:hover:bg-white/[0.02] transition-colors"
          >
            {/* Question + meta inline */}
            <div className="flex items-start gap-2 mb-2">
              <div className="flex-1 min-w-0 space-y-1.5">
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 leading-snug">
                  {r.question}
                </p>
                <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                  {r.canonique && (
                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                      canonique
                      <InfoTooltip content="Était servie directement sans relecture humaine. La restaurer la remettra en service immédiatement dès le seuil atteint." />
                    </span>
                  )}
                  <RaisonBadge raison={r.obsolete_raison} />
                  <span>{r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}</span>
                  <span aria-hidden="true" className="text-gray-200 dark:text-gray-700">·</span>
                  <span
                    className="truncate max-w-[12rem]"
                    title={r.document_filename ?? undefined}
                  >
                    {r.document_filename ?? "Document inconnu"}
                  </span>
                  {r.obsolete_version && (
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 dark:bg-white/8 dark:text-gray-400 text-xs">
                      v{r.obsolete_version}
                    </span>
                  )}
                  {r.obsolete_at && (
                    <>
                      <span aria-hidden="true" className="text-gray-200 dark:text-gray-700">·</span>
                      <span title={formatDate(r.obsolete_at)}>{depuis(r.obsolete_at)}</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            <ExpandableText text={contenuServi(r)} label={r.question} />

            {/* AI justification */}
            {r.analyse_justification && (
              <div className="mt-2.5 flex items-start gap-1.5 px-3 py-2 rounded-lg bg-amber-50/70 dark:bg-amber-400/5 border border-amber-100 dark:border-amber-500/15">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-500" aria-hidden="true" />
                <p className="text-xs text-amber-800/90 dark:text-amber-200/80 leading-relaxed">
                  {r.analyse_justification}
                </p>
              </div>
            )}

            {/* Actions */}
            <div className="mt-3 flex items-center justify-end gap-1.5">
              <button
                onClick={() => onRestore(r.reponse_id)}
                disabled={isPendingRestore}
                aria-label={`Restaurer — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                <RotateCcw size={12} aria-hidden="true" />
                Restaurer
              </button>
              <button
                onClick={() => onDeleteTarget({ reponse_id: r.reponse_id, question: r.question, obsolete: true })}
                aria-label={`Supprimer définitivement — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-red-100 dark:border-red-500/15 text-red-500 dark:text-red-400 text-xs font-medium hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60"
              >
                <Trash2 size={12} aria-hidden="true" />
                Supprimer
              </button>
            </div>
          </article>
        ))}
      </div>

      {restoreError && (
        <p role="alert" className="px-5 py-3 text-xs text-red-500 dark:text-red-400 border-t border-gray-100 dark:border-white/8">
          {restoreError instanceof Error ? restoreError.message : "Erreur de restauration"}
        </p>
      )}
    </>
  );
}
