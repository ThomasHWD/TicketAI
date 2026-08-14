import { AlertTriangle, Check, Pencil, Trash2, X } from "lucide-react";
import { formatDate } from "../../../lib/ticketStatus";
import type { ReponseCanonique } from "../../../types.ts";
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

  return (
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
          Aucune réponse enregistrée
        </p>
      )}
      {!loading && !error && total > 0 && items.length === 0 && q && (
        <p className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
          Aucun résultat pour « {searchQuery} » sur cette page.
        </p>
      )}

      {!loading &&
        items.map((r) => {
          const isEditing = editingId === r.reponse_id;
          return (
            <article
              key={r.reponse_id}
              className="px-6 py-4 space-y-2.5 hover:bg-gray-50/60 dark:hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex items-start gap-2">
                <p className="flex-1 min-w-0 text-sm font-medium text-gray-800 dark:text-gray-100 leading-snug">
                  {r.question}
                </p>
                <div className="flex items-center gap-1.5 shrink-0">
                  {r.a_relire && (
                    <button
                      onClick={onTabARelire}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-400/25 transition-colors"
                      title="Le document source a changé — voir l'onglet À relire"
                    >
                      <AlertTriangle size={11} aria-hidden="true" />
                      À relire
                    </button>
                  )}
                  <span
                    className="inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-full text-xs font-medium tabular-nums bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    title={`Réponse auto-servie ${r.occurence} fois`}
                  >
                    {r.occurence}×
                  </span>
                </div>
              </div>

              {isEditing ? (
                <textarea
                  value={draft}
                  onChange={(e) => onDraftChange(e.target.value)}
                  rows={6}
                  autoFocus
                  className="w-full rounded-xl border border-gray-200 dark:border-white/15 bg-white/70 dark:bg-white/5 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                />
              ) : (
                <ExpandableText text={contenuServi(r)} />
              )}

              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                  {r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}
                  {r.validated_at && (
                    <span className="ml-1" title={formatDate(r.validated_at)}>
                      · {depuis(r.validated_at)}
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-1.5">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => onSave(r.reponse_id)}
                        disabled={!draft.trim() || isPendingEdit}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        <Check size={14} />
                        Enregistrer
                      </button>
                      <button
                        onClick={onCancel}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                      >
                        <X size={14} />
                        Annuler
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => onEdit(r)}
                        title="Modifier"
                        aria-label="Modifier la réponse"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                      >
                        <Pencil size={13} />
                        Modifier
                      </button>
                      <button
                        onClick={() =>
                          onDeleteTarget({ reponse_id: r.reponse_id, question: r.question, obsolete: false })
                        }
                        title="Supprimer"
                        aria-label="Supprimer la réponse"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 text-xs font-medium hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                      >
                        <Trash2 size={13} />
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
