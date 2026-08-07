import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Pencil,
  Trash2,
  Check,
  X,
  BadgeCheck,
} from "lucide-react";
import {
  getReponsesCanoniques,
  editerReponseCanonique,
  supprimerReponseCanonique,
} from "../../lib/api";
import type { ReponseCanonique } from "../../types.ts";

/** Contenu effectivement servi : la version corrigée prime sur l'originale. */
function contenuServi(r: ReponseCanonique): string {
  return r.contenu_corrige ?? r.contenu;
}

const LIMIT = 10;

export default function SavedAnswers() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ReponseCanonique | null>(null);

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ["reponses-canoniques", page],
    queryFn: () => getReponsesCanoniques({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
  });

  const editMutation = useMutation({
    mutationFn: ({ id, contenu }: { id: string; contenu: string }) =>
      editerReponseCanonique(id, { contenu }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      setEditingId(null);
      setDraft("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => supprimerReponseCanonique(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
      setDeleteTarget(null);
    },
  });

  const answers = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  function startEdit(r: ReponseCanonique) {
    setEditingId(r.reponse_id);
    setDraft(contenuServi(r));
  }

  function cancelEdit() {
    setEditingId(null);
    setDraft("");
  }

  function saveEdit(id: string) {
    if (!draft.trim()) return;
    editMutation.mutate({ id, contenu: draft });
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Réponses Enregistrées
        </h1>
      </div>

      {/* Card */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-6 py-4 border-b border-gray-200 dark:border-white/10">
          <BadgeCheck size={18} className="text-emerald-500" aria-hidden="true" />
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
            Base de connaissances canonique
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Question</th>
                <th className="px-6 py-3 font-medium">Réponse servie</th>
                <th className="px-6 py-3 font-medium text-center whitespace-nowrap">Fois posée</th>
                <th className="px-6 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/5">
              {loading && (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Chargement…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-red-600 dark:text-red-400">
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}
              {!loading && !error && answers.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Aucune réponse enregistrée
                  </td>
                </tr>
              )}
              {!loading &&
                answers.map((r) => {
                  const isEditing = editingId === r.reponse_id;
                  return (
                    <tr
                      key={r.reponse_id}
                      className="align-top hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      <td className="px-6 py-4 text-gray-700 dark:text-gray-200">
                        <span className="block max-w-xs" title={r.question}>
                          {r.question}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                        {isEditing ? (
                          <textarea
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            rows={5}
                            autoFocus
                            className="w-full min-w-[18rem] rounded-xl border border-gray-200 dark:border-white/15 bg-white/70 dark:bg-white/5 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                          />
                        ) : (
                          <span className="block max-w-md whitespace-pre-wrap">
                            {contenuServi(r)}
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center whitespace-nowrap">
                        <span
                          className="inline-flex items-center justify-center min-w-[2rem] px-2 py-0.5 rounded-full text-xs font-medium tabular-nums bg-emerald-500/10 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                          title={`Réponse auto-servie ${r.occurence} fois`}
                        >
                          {r.occurence}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-1.5">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => saveEdit(r.reponse_id)}
                                disabled={!draft.trim() || editMutation.isPending}
                                title="Enregistrer"
                                aria-label="Enregistrer"
                                className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <Check size={16} />
                              </button>
                              <button
                                onClick={cancelEdit}
                                title="Annuler"
                                aria-label="Annuler"
                                className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                              >
                                <X size={16} />
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => startEdit(r)}
                                title="Modifier"
                                aria-label="Modifier la réponse"
                                className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                              >
                                <Pencil size={16} />
                              </button>
                              <button
                                onClick={() => setDeleteTarget(r)}
                                title="Supprimer"
                                aria-label="Supprimer la réponse"
                                className="p-1.5 rounded-lg border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                              >
                                <Trash2 size={16} />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!loading && total > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-white/10 text-sm text-gray-500 dark:text-gray-400">
            <span>
              {from}–{to} sur {total}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modale de confirmation de suppression */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Confirmer la suppression"
          onClick={() => !deleteMutation.isPending && setDeleteTarget(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-white/60 dark:border-white/10 bg-white dark:bg-[#0b0f1a] p-6 shadow-[0_8px_40px_0_rgba(0,0,0,0.25)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
              Supprimer cette réponse canonique ?
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              La réponse à «&nbsp;{deleteTarget.question}&nbsp;» sera supprimée
              définitivement. Les futures questions similaires repasseront par le
              pipeline de génération normal. Cette action est irréversible.
            </p>
            {deleteMutation.isError && (
              <p className="mt-3 text-sm text-red-600 dark:text-red-400">
                {deleteMutation.error instanceof Error
                  ? deleteMutation.error.message
                  : "Erreur de suppression"}
              </p>
            )}
            <div className="mt-6 flex items-center justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget.reponse_id)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {deleteMutation.isPending ? "Suppression…" : "Supprimer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
