import { AlertTriangle, Check, Pencil, Trash2, X } from "lucide-react";
import { formatDate } from "../../../lib/ticketStatus";
import type { ReponseCanonique } from "../../../types";
import ExpandableText from "./ExpandableText";
import { contenuServi, depuis, type CibleSuppression } from "./utils";

type Props = {
  items: ReponseCanonique[];
  loading: boolean;
  error: Error | null;
  total: number;
  searchQuery: string;
  editingId: string | null;
  draft: string;
  isPendingEdit: boolean;
  onEdit: (r: ReponseCanonique) => void;
  onSave: (id: string) => void;
  onCancel: () => void;
  onDraftChange: (v: string) => void;
  onDeleteTarget: (t: CibleSuppression) => void;
  onTabARelire: () => void;
};

export default function TabCanoniques({
  items,
  loading,
  error,
  total,
  searchQuery,
  editingId,
  draft,
  isPendingEdit,
  onEdit,
  onSave,
  onCancel,
  onDraftChange,
  onDeleteTarget,
  onTabARelire,
}: Props) {
  const q = searchQuery.trim().toLowerCase();

  if (loading) {
    return (
      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="px-5 py-4 space-y-2 animate-pulse">
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
      <p className="px-5 py-12 text-center text-sm text-red-500 dark:text-red-400">
        {error instanceof Error ? error.message : "Erreur de chargement"}
      </p>
    );
  }

  if (total === 0) {
    return (
      <div className="px-5 py-16 text-center space-y-1">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Aucune réponse enregistrée</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">Les réponses validées 3 fois ou plus apparaissent ici.</p>
      </div>
    );
  }

  if (items.length === 0 && q) {
    return (
      <p className="px-5 py-12 text-center text-sm text-gray-400 dark:text-gray-500">
        Aucun résultat pour <span className="font-medium text-gray-600 dark:text-gray-300">«&nbsp;{searchQuery}&nbsp;»</span> sur cette page.
      </p>
    );
  }

  return (
    <div className="divide-y divide-gray-100 dark:divide-white/5">
      {items.map((r) => {
        const isEditing = editingId === r.reponse_id;
        return (
          <article
            key={r.reponse_id}
            className="group px-5 py-4 hover:bg-gray-50/70 dark:hover:bg-white/[0.02] transition-colors"
          >
            {/* Question row */}
            <div className="flex items-start gap-2 mb-2">
              <p className="flex-1 min-w-0 text-sm font-semibold text-gray-900 dark:text-gray-50 leading-snug">
                {r.question}
              </p>
              <div className="flex items-center gap-1.5 shrink-0 pt-px">
                {r.a_relire && (
                  <button
                    onClick={onTabARelire}
                    title="Le document source a changé — voir l'onglet À relire"
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-400/25 transition-colors"
                  >
                    <AlertTriangle size={10} aria-hidden="true" />
                    À relire
                  </button>
                )}
                <span
                  className="inline-flex items-center justify-center min-w-[1.75rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                  title={`Auto-servie ${r.occurence} fois`}
                >
                  {r.occurence}×
                </span>
              </div>
            </div>

            {/* Content */}
            {isEditing ? (
              <textarea
                value={draft}
                onChange={(e) => onDraftChange(e.target.value)}
                rows={6}
                autoFocus
                className="w-full rounded-xl border border-gray-200 dark:border-white/15 bg-white dark:bg-white/5 px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 leading-relaxed resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              />
            ) : (
              <ExpandableText text={contenuServi(r)} />
            )}

            {/* Meta + actions row */}
            <div className="mt-2.5 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                <span>{r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}</span>
                {r.validated_at && (
                  <>
                    <span className="text-gray-200 dark:text-gray-700">·</span>
                    <span title={formatDate(r.validated_at)}>{depuis(r.validated_at)}</span>
                  </>
                )}
              </div>

              <div className={`flex items-center gap-1.5 transition-opacity duration-150 ${isEditing ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
                {isEditing ? (
                  <>
                    <button
                      onClick={() => onSave(r.reponse_id)}
                      disabled={!draft.trim() || isPendingEdit}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <Check size={13} />
                      Enregistrer
                    </button>
                    <button
                      onClick={onCancel}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/8 transition-colors"
                    >
                      <X size={13} />
                      Annuler
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => onEdit(r)}
                      aria-label="Modifier la réponse"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-white/12 text-gray-500 dark:text-gray-400 text-xs font-medium hover:text-gray-700 hover:bg-gray-50 dark:hover:text-gray-200 dark:hover:bg-white/8 transition-colors"
                    >
                      <Pencil size={12} />
                      Modifier
                    </button>
                    <button
                      onClick={() => onDeleteTarget({ reponse_id: r.reponse_id, question: r.question, obsolete: false })}
                      aria-label="Supprimer la réponse"
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-red-100 dark:border-red-500/15 text-red-500 dark:text-red-400 text-xs font-medium hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 size={12} />
                      Supprimer
                    </button>
                  </>
                )}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
