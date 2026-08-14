import type { UseMutationResult } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  EyeOff,
  Pencil,
  X,
} from "lucide-react";
import type { ReponseSignalee } from "../../../types.ts";
import ExpandableText from "./ExpandableText";
import MotifSignalement from "./MotifSignalement";
import SensDuChangement from "./SensDuChangement";
import {
  contenuServi,
  EN_ANALYSE,
  estRaisonDeGroupe,
  RAISONS,
  type GroupeARelire,
} from "./utils";

type Props = {
  groupes: GroupeARelire[];
  loading: boolean;
  error: Error | null;
  total: number;
  groupesReplies: Set<string>;
  editingId: string | null;
  draft: string;
  isPendingEdit: boolean;
  confirmMutation: UseMutationResult<void, Error, string>;
  confirmLotMutation: UseMutationResult<void, Error, { doc_id: string; version: number }>;
  onToggleGroupe: (cle: string) => void;
  onEdit: (r: ReponseSignalee) => void;
  onSave: (id: string) => void;
  onCancel: () => void;
  onDraftChange: (v: string) => void;
  onRetrait: (r: ReponseSignalee) => void;
};

export default function TabARelire({
  groupes,
  loading,
  error,
  total,
  groupesReplies,
  editingId,
  draft,
  isPendingEdit,
  confirmMutation,
  confirmLotMutation,
  onToggleGroupe,
  onEdit,
  onSave,
  onCancel,
  onDraftChange,
  onRetrait,
}: Props) {
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
            Aucune réponse à relire
          </p>
        )}

        {!loading &&
          groupes.map((g) => {
            const ouvert = !groupesReplies.has(g.cle);
            return (
              <section key={g.cle} className="px-6 py-5 space-y-4">
                <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/80 dark:bg-amber-400/10 px-4 py-3.5 space-y-2.5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <button
                      onClick={() => onToggleGroupe(g.cle)}
                      className="min-w-0 flex-1 text-left"
                      aria-expanded={ouvert}
                    >
                      <p className="text-sm font-semibold text-amber-900 dark:text-amber-300 truncate flex items-center gap-1.5">
                        {g.filename ?? "Document inconnu"}
                        {g.version !== null && (
                          <span className="font-normal text-amber-900/70 dark:text-amber-200/70">
                            v{g.version}
                          </span>
                        )}
                        {ouvert ? (
                          <ChevronUp size={14} className="shrink-0 text-amber-700/60 dark:text-amber-300/60" />
                        ) : (
                          <ChevronDown size={14} className="shrink-0 text-amber-700/60 dark:text-amber-300/60" />
                        )}
                      </p>
                      <p className="mt-0.5 text-xs text-amber-900/80 dark:text-amber-200/80">
                        {g.reponses.length} réponse{g.reponses.length > 1 ? "s" : ""} sur cette page
                        {g.document_supprime && " — document supprimé depuis"}
                      </p>
                    </button>
                    {g.doc_id !== null && g.version !== null && (
                      <button
                        onClick={() =>
                          confirmLotMutation.mutate({ doc_id: g.doc_id!, version: g.version! })
                        }
                        disabled={confirmLotMutation.isPending}
                        className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        <CheckCircle2 size={15} />
                        Tout confirmer
                      </button>
                    )}
                  </div>

                  {ouvert && (
                    estRaisonDeGroupe(g.raison) ? (
                      <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
                        {RAISONS[g.raison!]} Ces réponses sont signalées par précaution.
                      </p>
                    ) : g.changements ? (
                      <>
                        <SensDuChangement
                          titre="ajouté"
                          total={g.changements.nb_ajoutes}
                          extraits={g.changements.extraits_ajoutes}
                        />
                        <SensDuChangement
                          titre="retiré"
                          total={g.changements.nb_retires}
                          extraits={g.changements.extraits_retires}
                        />
                      </>
                    ) : (
                      <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
                        Le détail de cette mise à jour n'a pas été conservé.
                      </p>
                    )
                  )}
                </div>

                <ul className="space-y-2">
                  {g.reponses.map((r) => {
                    const isEditing = editingId === r.reponse_id;
                    return (
                      <li
                        key={r.reponse_id}
                        className="rounded-xl border border-gray-200 dark:border-white/10 px-4 py-3 space-y-2"
                      >
                        <div className="flex items-start gap-2">
                          <p className="flex-1 min-w-0 text-sm font-medium text-gray-800 dark:text-gray-100">
                            {r.question}
                          </p>
                          {r.canonique && (
                            <span className="shrink-0 px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                              canonique
                            </span>
                          )}
                          <span className="shrink-0 text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                            {r.nb_validations} val.
                          </span>
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

                        <MotifSignalement reponse={r} />

                        {r.a_relire_raison === EN_ANALYSE ? (
                          <p className="text-right text-xs text-gray-400 dark:text-gray-500">
                            Résultat dans quelques minutes.
                          </p>
                        ) : (
                          <div className="flex items-center justify-end gap-1.5">
                            {isEditing ? (
                              <>
                                <button
                                  onClick={() => onSave(r.reponse_id)}
                                  disabled={!draft.trim() || isPendingEdit}
                                  title="Enregistrer"
                                  aria-label="Enregistrer"
                                  className="p-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                  <Check size={16} />
                                </button>
                                <button
                                  onClick={onCancel}
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
                                  onClick={() => confirmMutation.mutate(r.reponse_id)}
                                  disabled={confirmMutation.isPending}
                                  title="Toujours d'actualité : lever le signalement"
                                  aria-label="Toujours d'actualité"
                                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                >
                                  <CheckCircle2 size={15} />
                                  Toujours d'actualité
                                </button>
                                <button
                                  onClick={() => onEdit(r)}
                                  title="Modifier"
                                  aria-label="Modifier la réponse"
                                  className="p-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                                >
                                  <Pencil size={16} />
                                </button>
                                <button
                                  onClick={() => onRetrait(r)}
                                  title="Retirer du service"
                                  aria-label="Retirer la réponse du service"
                                  className="p-1.5 rounded-lg border border-amber-200 dark:border-amber-500/25 text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors"
                                >
                                  <EyeOff size={16} />
                                </button>
                              </>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}

        {(confirmMutation.isError || confirmLotMutation.isError) && (
          <p className="px-6 py-3 text-sm text-red-600 dark:text-red-400">
            Erreur de confirmation : le signalement n'a pas été levé.
          </p>
        )}
      </div>
    </>
  );
}
