import type { UseMutationResult } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  EyeOff,
  FileText,
  Loader2,
  Pencil,
  X,
} from "lucide-react";
import type { ReponseSignalee } from "../../../types";
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
  if (loading) {
    return (
      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="px-5 py-5 space-y-3 animate-pulse">
            <div className="h-4 w-1/3 rounded bg-amber-100/80 dark:bg-amber-500/10" />
            <div className="space-y-2 pl-2">
              <div className="h-3 w-2/3 rounded bg-gray-100 dark:bg-white/8" />
              <div className="h-3 w-full rounded bg-gray-100 dark:bg-white/5" />
            </div>
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
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Aucune réponse à relire</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">Toutes les réponses sont à jour.</p>
      </div>
    );
  }

  return (
    <>
      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {groupes.map((g) => {
          const ouvert = !groupesReplies.has(g.cle);
          return (
            <section key={g.cle} className="px-5 py-4 space-y-3">
              {/* Group header */}
              <div className="rounded-xl border border-amber-200/70 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-400/5 overflow-hidden">
                {/* Header bar */}
                <div className="flex items-center justify-between gap-3 px-4 py-3">
                  <button
                    onClick={() => onToggleGroupe(g.cle)}
                    className="min-w-0 flex-1 flex items-center gap-2.5 text-left"
                    aria-expanded={ouvert}
                  >
                    <FileText size={14} className="shrink-0 text-amber-500" aria-hidden="true" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-amber-900 dark:text-amber-200 truncate">
                          {g.filename ?? "Document inconnu"}
                        </span>
                        {g.version !== null && (
                          <span className="shrink-0 px-1.5 py-px rounded text-xs font-medium bg-amber-200/60 text-amber-800 dark:bg-amber-400/20 dark:text-amber-300">
                            v{g.version}
                          </span>
                        )}
                        {g.document_supprime && (
                          <span className="shrink-0 px-1.5 py-px rounded text-xs font-medium bg-gray-200/80 text-gray-600 dark:bg-white/10 dark:text-gray-400">
                            supprimé
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-amber-800/70 dark:text-amber-300/60 mt-0.5">
                        {g.reponses.length} réponse{g.reponses.length > 1 ? "s" : ""} sur cette page
                      </p>
                    </div>
                    {ouvert ? (
                      <ChevronUp size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" />
                    ) : (
                      <ChevronDown size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" />
                    )}
                  </button>

                  {g.doc_id !== null && g.version !== null && (
                    <button
                      onClick={() => confirmLotMutation.mutate({ doc_id: g.doc_id!, version: g.version! })}
                      disabled={confirmLotMutation.isPending}
                      className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <CheckCircle2 size={13} />
                      Tout confirmer
                    </button>
                  )}
                </div>

                {/* Diff section */}
                {ouvert && (
                  <div className="border-t border-amber-200/50 dark:border-amber-500/15 px-4 py-3 space-y-3">
                    {estRaisonDeGroupe(g.raison) ? (
                      <p className="text-xs text-amber-800/80 dark:text-amber-200/70">
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
                      <p className="text-xs text-amber-800/70 dark:text-amber-200/60">
                        Le détail de cette mise à jour n'a pas été conservé.
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* Response items */}
              <ul className="space-y-1.5">
                {g.reponses.map((r) => {
                  const isEditing = editingId === r.reponse_id;
                  const enAnalyse = r.a_relire_raison === EN_ANALYSE;
                  return (
                    <li
                      key={r.reponse_id}
                      className={`group rounded-xl border px-4 py-3 space-y-2 transition-colors ${
                        enAnalyse
                          ? "border-gray-200/70 dark:border-white/8 bg-gray-50/50 dark:bg-white/[0.02]"
                          : "border-gray-200/70 dark:border-white/8 hover:border-gray-200 dark:hover:border-white/12"
                      }`}
                    >
                      {/* Question + badges */}
                      <div className="flex items-start gap-2">
                        <p className={`flex-1 min-w-0 text-sm font-semibold leading-snug ${
                          enAnalyse
                            ? "text-gray-500 dark:text-gray-400"
                            : "text-gray-900 dark:text-gray-50"
                        }`}>
                          {r.question}
                        </p>
                        <div className="flex items-center gap-1.5 shrink-0 pt-px">
                          {r.canonique && (
                            <span className="px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                              canonique
                            </span>
                          )}
                          <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                            {r.nb_validations} val.
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

                      <MotifSignalement reponse={r} />

                      {/* Actions */}
                      {enAnalyse ? (
                        <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
                          <Loader2 size={12} className="animate-spin shrink-0" />
                          <Clock size={12} className="shrink-0" />
                          Résultat dans quelques minutes
                        </div>
                      ) : (
                        <div className={`flex items-center justify-end gap-1.5 transition-opacity duration-150 ${isEditing ? "opacity-100" : "opacity-0 group-hover:opacity-100"}`}>
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => onSave(r.reponse_id)}
                                disabled={!draft.trim() || isPendingEdit}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <Check size={12} />
                                Enregistrer
                              </button>
                              <button
                                onClick={onCancel}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/8 transition-colors"
                              >
                                <X size={12} />
                                Annuler
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => confirmMutation.mutate(r.reponse_id)}
                                disabled={confirmMutation.isPending}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-emerald-200 dark:border-emerald-500/20 text-emerald-600 dark:text-emerald-300 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                              >
                                <CheckCircle2 size={12} />
                                Toujours d'actualité
                              </button>
                              <button
                                onClick={() => onEdit(r)}
                                aria-label="Modifier la réponse"
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-white/12 text-gray-500 dark:text-gray-400 text-xs font-medium hover:text-gray-700 hover:bg-gray-50 dark:hover:text-gray-200 dark:hover:bg-white/8 transition-colors"
                              >
                                <Pencil size={12} />
                                Modifier
                              </button>
                              <button
                                onClick={() => onRetrait(r)}
                                aria-label="Retirer la réponse du service"
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-amber-200 dark:border-amber-500/20 text-amber-600 dark:text-amber-300 text-xs font-medium hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors"
                              >
                                <EyeOff size={12} />
                                Retirer
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
      </div>

      {(confirmMutation.isError || confirmLotMutation.isError) && (
        <p className="px-5 py-3 text-xs text-red-500 dark:text-red-400 border-t border-gray-100 dark:border-white/8">
          Erreur de confirmation — le signalement n'a pas été levé.
        </p>
      )}
    </>
  );
}
