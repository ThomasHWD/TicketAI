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
  Archive,
  RotateCcw,
} from "lucide-react";
import {
  getReponsesCanoniques,
  getReponsesObsoletes,
  editerReponseCanonique,
  supprimerReponseCanonique,
  restaurerReponse,
} from "../../lib/api";
import { formatDate } from "../../lib/ticketStatus";
import type { ReponseCanonique, ReponseObsolete } from "../../types.ts";

/** Contenu effectivement servi : la version corrigée prime sur l'originale. */
function contenuServi(r: { contenu: string; contenu_corrige: string | null }): string {
  return r.contenu_corrige ?? r.contenu;
}

const RELATIF = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });
const SEUILS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** « il y a 3 jours ». La date exacte reste accessible en `title`. */
function depuis(iso: string | null): string {
  if (!iso) return "—";
  const secondes = (Date.now() - new Date(iso).getTime()) / 1000;
  for (const [unite, taille] of SEUILS) {
    if (secondes >= taille) return RELATIF.format(-Math.floor(secondes / taille), unite);
  }
  return RELATIF.format(-Math.floor(secondes), "second");
}

const LIMIT = 10;

type Onglet = "canoniques" | "obsoletes";

/** Cible de la modale de suppression, commune aux deux onglets. */
type CibleSuppression = { reponse_id: string; question: string; obsolete: boolean };

export default function SavedAnswers() {
  const queryClient = useQueryClient();
  const [onglet, setOnglet] = useState<Onglet>("canoniques");
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CibleSuppression | null>(null);

  const canoniques = useQuery({
    queryKey: ["reponses-canoniques", page],
    queryFn: () => getReponsesCanoniques({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "canoniques",
  });

  const obsoletes = useQuery({
    queryKey: ["reponses-obsoletes", "liste", page],
    queryFn: () => getReponsesObsoletes({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "obsoletes",
  });

  // Compteur de l'onglet : requête distincte (limit 1) pour rester à jour même
  // depuis l'onglet Canoniques. Clé partagée avec le badge de la Sidebar.
  const { data: compteur } = useQuery({
    queryKey: ["reponses-obsoletes", "count"],
    queryFn: () => getReponsesObsoletes({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });
  const nbObsoletes = compteur?.total ?? 0;

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
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      setDeleteTarget(null);
    },
  });

  // Une réponse restaurée réapparaît côté canoniques : les deux listes bougent.
  const restoreMutation = useMutation({
    mutationFn: (id: string) => restaurerReponse(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reponses-obsoletes"] });
      queryClient.invalidateQueries({ queryKey: ["reponses-canoniques"] });
    },
  });

  const requete = onglet === "canoniques" ? canoniques : obsoletes;
  const loading = requete.isLoading;
  const error = requete.error;
  const total = requete.data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);
  const nbColonnes = onglet === "canoniques" ? 4 : 5;

  function changerOnglet(cible: Onglet) {
    setOnglet(cible);
    setPage(1);
    cancelEdit();
  }

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

  function ongletClasses(cible: Onglet) {
    return `flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
      onglet === cible
        ? "border-emerald-500 text-gray-800 dark:text-gray-100"
        : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
    }`;
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
        <div
          className="flex items-center gap-1 px-4 border-b border-gray-200 dark:border-white/10"
          role="tablist"
        >
          <button
            role="tab"
            aria-selected={onglet === "canoniques"}
            onClick={() => changerOnglet("canoniques")}
            className={ongletClasses("canoniques")}
          >
            <BadgeCheck size={16} className="text-emerald-500" aria-hidden="true" />
            Canoniques
          </button>
          <button
            role="tab"
            aria-selected={onglet === "obsoletes"}
            onClick={() => changerOnglet("obsoletes")}
            className={ongletClasses("obsoletes")}
          >
            <Archive size={16} className="text-gray-400" aria-hidden="true" />
            Obsolètes
            {nbObsoletes > 0 && (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-300">
                {nbObsoletes}
              </span>
            )}
          </button>
        </div>

        {onglet === "obsoletes" && (
          <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
            Ces réponses ne sont plus servies : le passage du document sur lequel
            elles s'appuyaient a changé. Leurs validations sont conservées — les
            restaurer les remet en service telles quelles.
          </p>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Question</th>
                <th className="px-6 py-3 font-medium">Réponse servie</th>
                {onglet === "canoniques" ? (
                  <th className="px-6 py-3 font-medium text-center whitespace-nowrap">Fois posée</th>
                ) : (
                  <>
                    <th className="px-6 py-3 font-medium">Document</th>
                    <th className="px-6 py-3 font-medium whitespace-nowrap">Depuis</th>
                  </>
                )}
                <th className="px-6 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/5">
              {loading && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Chargement…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-red-600 dark:text-red-400">
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}
              {!loading && !error && total === 0 && (
                <tr>
                  <td colSpan={nbColonnes} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    {onglet === "canoniques"
                      ? "Aucune réponse enregistrée"
                      : "Aucune réponse obsolète"}
                  </td>
                </tr>
              )}

              {!loading &&
                onglet === "canoniques" &&
                (canoniques.data?.items ?? []).map((r) => {
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
                                onClick={() =>
                                  setDeleteTarget({
                                    reponse_id: r.reponse_id,
                                    question: r.question,
                                    obsolete: false,
                                  })
                                }
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

              {!loading &&
                onglet === "obsoletes" &&
                (obsoletes.data?.items ?? []).map((r: ReponseObsolete) => (
                  <tr
                    key={r.reponse_id}
                    className="align-top hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                  >
                    <td className="px-6 py-4 text-gray-700 dark:text-gray-200">
                      <span className="block max-w-xs" title={r.question}>
                        {r.question}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                        {r.canonique && (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                            canonique
                          </span>
                        )}
                        {r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                      <span className="block max-w-md whitespace-pre-wrap">{contenuServi(r)}</span>
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                      <span
                        className="block max-w-[12rem] truncate"
                        title={r.document_filename ?? undefined}
                      >
                        {r.document_filename ?? "Document inconnu"}
                      </span>
                      <span className="mt-1 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300">
                        {r.document_supprime
                          ? "supprimé"
                          : r.obsolete_version
                            ? `v${r.obsolete_version}`
                            : "mis à jour"}
                      </span>
                    </td>
                    <td
                      className="px-6 py-4 whitespace-nowrap text-gray-500 dark:text-gray-400"
                      title={formatDate(r.obsolete_at)}
                    >
                      {depuis(r.obsolete_at)}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => restoreMutation.mutate(r.reponse_id)}
                          disabled={restoreMutation.isPending}
                          title="Restaurer : remettre cette réponse en service"
                          aria-label="Restaurer la réponse"
                          className="p-1.5 rounded-lg border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          <RotateCcw size={16} />
                        </button>
                        <button
                          onClick={() =>
                            setDeleteTarget({
                              reponse_id: r.reponse_id,
                              question: r.question,
                              obsolete: true,
                            })
                          }
                          title="Supprimer définitivement"
                          aria-label="Supprimer définitivement la réponse"
                          className="p-1.5 rounded-lg border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {restoreMutation.isError && (
          <p className="px-6 py-3 text-sm text-red-600 dark:text-red-400 border-t border-gray-200 dark:border-white/10">
            {restoreMutation.error instanceof Error
              ? restoreMutation.error.message
              : "Erreur de restauration"}
          </p>
        )}

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
              {deleteTarget.obsolete
                ? "Supprimer définitivement cette réponse ?"
                : "Supprimer cette réponse canonique ?"}
            </h3>
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              La réponse à «&nbsp;{deleteTarget.question}&nbsp;» sera supprimée
              définitivement.{" "}
              {deleteTarget.obsolete
                ? "Elle ne pourra plus être restaurée."
                : "Les futures questions similaires repasseront par le pipeline de génération normal."}{" "}
              Cette action est irréversible.
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
