import { useEffect, useId, useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  EyeOff,
  FileText,
  Loader2,
  Pencil,
  X,
} from "lucide-react";
import type { ReponseSignalee } from "../../../types";
import ExpandableText from "./ExpandableText";
import InfoTooltip from "./InfoTooltip";
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
  onCollapseAll: () => void;
  onExpandAll: () => void;
  onRetry: () => void;
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
  onCollapseAll,
  onExpandAll,
  onRetry,
  onEdit,
  onSave,
  onCancel,
  onDraftChange,
  onRetrait,
}: Props) {
  const [confirmingLot, setConfirmingLot] = useState<string | null>(null);
  const [pendingLotCle, setPendingLotCle] = useState<string | null>(null);
  const [lotErrorCles, setLotErrorCles] = useState<Set<string>>(new Set());
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [confirmErrors, setConfirmErrors] = useState<Set<string>>(new Set());
  const uid = useId();

  useEffect(() => {
    if (!confirmMutation.isPending && confirmingId !== null) {
      if (confirmMutation.isError) {
        setConfirmErrors((prev) => new Set([...prev, confirmingId]));
      }
      setConfirmingId(null);
    }
  }, [confirmMutation.isPending, confirmMutation.isError, confirmingId]);

  useEffect(() => {
    if (!confirmLotMutation.isPending && pendingLotCle !== null) {
      if (confirmLotMutation.isError) {
        setLotErrorCles((prev) => new Set([...prev, pendingLotCle]));
      } else {
        setLotErrorCles((prev) => { const n = new Set(prev); n.delete(pendingLotCle); return n; });
      }
      setPendingLotCle(null);
    }
  }, [confirmLotMutation.isPending, confirmLotMutation.isError, pendingLotCle]);

  if (loading) {
    return (
      <div aria-busy="true" className="divide-y divide-gray-100 dark:divide-white/5">
        {[...Array(3)].map((_, i) => (
          <div key={i} aria-hidden="true" className="px-5 py-5 space-y-3 animate-pulse">
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

  if (total === 0) {
    return (
      <div className="px-5 py-16 text-center space-y-1">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Aucune réponse à relire</p>
        <p className="text-xs text-gray-400 dark:text-gray-500">Toutes les réponses sont à jour.</p>
      </div>
    );
  }

  const allCollapsed = groupes.length > 0 && groupes.every((g) => groupesReplies.has(g.cle));

  return (
    <>
      {groupes.length > 1 && (
        <div className="flex items-center justify-end px-5 py-2 border-b border-gray-100 dark:border-white/8">
          <button
            onClick={allCollapsed ? onExpandAll : onCollapseAll}
            className="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 rounded-sm"
            aria-label={allCollapsed ? "Développer tous les groupes" : "Réduire tous les groupes"}
          >
            {allCollapsed ? "Tout développer" : "Tout réduire"}
          </button>
        </div>
      )}
      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {groupes.map((g) => {
          const ouvert = !groupesReplies.has(g.cle);
          const diffId = `group-diff-${g.cle.replace(/[^a-zA-Z0-9]/g, "-")}`;
          const headingId = `${uid}-group-heading-${g.cle.replace(/[^a-zA-Z0-9]/g, "-")}`;
          return (
            <section key={g.cle} aria-labelledby={headingId} className="px-5 py-4 space-y-3">
              {/* Group header */}
              <div className="rounded-xl border border-amber-200/70 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-400/5 overflow-hidden">
                {/* Header bar */}
                <div className="flex items-center justify-between gap-3 px-4 py-3">
                  <button
                    onClick={() => onToggleGroupe(g.cle)}
                    className="min-w-0 flex-1 flex items-center gap-2.5 text-left rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
                    aria-expanded={ouvert}
                    aria-controls={diffId}
                  >
                    <FileText size={14} className="shrink-0 text-amber-500" aria-hidden="true" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span id={headingId} className="text-sm font-semibold text-amber-900 dark:text-amber-200 truncate" title={g.filename ?? undefined}>
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
                        {g.reponses.length} réponse{g.reponses.length > 1 ? "s" : ""} affichées
                      </p>
                    </div>
                    {ouvert ? (
                      <ChevronUp size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" aria-hidden="true" />
                    ) : (
                      <ChevronDown size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" aria-hidden="true" />
                    )}
                  </button>

                  {g.doc_id !== null && g.version !== null && (
                    confirmingLot === g.cle ? (
                      <div className="shrink-0 flex items-center gap-1.5">
                        <span role="alert" className="text-xs font-medium text-amber-900/80 dark:text-amber-200/70">
                          Confirmer toutes les réponses de ce document ?
                        </span>
                        <button
                          autoFocus
                          onClick={() => {
                            setPendingLotCle(g.cle);
                            confirmLotMutation.mutate({ doc_id: g.doc_id!, version: g.version! });
                            setConfirmingLot(null);
                          }}
                          disabled={confirmLotMutation.isPending}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                        >
                          {confirmLotMutation.isPending ? (
                            <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                          ) : (
                            <CheckCircle2 size={12} aria-hidden="true" />
                          )}
                          Confirmer
                        </button>
                        <button
                          onClick={() => setConfirmingLot(null)}
                          className="inline-flex items-center px-2.5 py-1.5 rounded-md border border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300 text-xs font-medium hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
                        >
                          Annuler
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmingLot(g.cle)}
                        disabled={confirmLotMutation.isPending}
                        aria-label={`Tout confirmer pour ${g.filename ?? "ce document"} — s'applique à l'ensemble du document`}
                        title={`Confirmer toutes les réponses de ce document (${g.reponses.length} affichées)`}
                        className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                      >
                        {pendingLotCle === g.cle && confirmLotMutation.isPending ? (
                          <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                        ) : (
                          <CheckCircle2 size={13} aria-hidden="true" />
                        )}
                        Tout confirmer
                      </button>
                    )
                  )}
                </div>

                {lotErrorCles.has(g.cle) && (
                  <div role="alert" className="px-4 py-2 flex items-center justify-between gap-3 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/8 border-t border-red-100 dark:border-red-500/15">
                    <span>Erreur — le lot n'a pas été confirmé.</span>
                    <div className="shrink-0 flex items-center gap-2">
                      <button
                        onClick={() => {
                          setLotErrorCles((prev) => { const n = new Set(prev); n.delete(g.cle); return n; });
                          setPendingLotCle(g.cle);
                          confirmLotMutation.mutate({ doc_id: g.doc_id!, version: g.version! });
                        }}
                        className="underline underline-offset-2 hover:text-red-700 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60 rounded-sm"
                      >
                        Réessayer
                      </button>
                      {!ouvert && (
                        <>
                          <span aria-hidden="true" className="opacity-40">·</span>
                          <button
                            onClick={() => onToggleGroupe(g.cle)}
                            className="underline underline-offset-2 hover:text-red-700 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60 rounded-sm"
                          >
                            Voir les réponses ↓
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Diff section — always in DOM so aria-controls resolves */}
                <div
                  id={diffId}
                  className={`border-t border-amber-200/50 dark:border-amber-500/15 px-4 py-3 space-y-3${!ouvert ? " hidden" : ""}`}
                >
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
              </div>

              {/* Response items */}
              <ul className="space-y-1.5">
                {g.reponses.map((r) => {
                  const isEditing = editingId === r.reponse_id;
                  const enAnalyse = r.a_relire_raison === EN_ANALYSE;
                  const isConfirmError = confirmErrors.has(r.reponse_id);
                  return (
                    <li
                      key={r.reponse_id}
                      className={`rounded-xl border px-4 py-3 space-y-2 transition-colors ${
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
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                              canonique
                              <InfoTooltip content="Servie directement sans relecture humaine — vérifiez bien avant de confirmer" />
                            </span>
                          )}
                          <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                            {r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}
                          </span>
                        </div>
                      </div>

                      {/* Content */}
                      {isEditing ? (
                        <div className="space-y-2">
                          {g.filename && (
                            <p className="text-xs text-amber-700/70 dark:text-amber-300/60">
                              Document : <span className="font-medium">{g.filename}</span>
                              {g.version !== null && <span className="ml-1 opacity-70">v{g.version}</span>}
                            </p>
                          )}
                          <details className="group/orig rounded-lg border border-gray-200/70 dark:border-white/8 bg-gray-50/50 dark:bg-white/[0.02]">
                            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 select-none list-none flex items-center gap-1 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
                              <span className="text-gray-300 dark:text-gray-600 group-open/orig:rotate-90 transition-transform inline-block">▶</span>
                              Texte actuel (référence)
                            </summary>
                            <p className="px-3 pb-3 text-xs text-gray-600 dark:text-gray-400 leading-relaxed whitespace-pre-wrap">
                              {contenuServi(r)}
                            </p>
                          </details>
                          <textarea
                            value={draft}
                            onChange={(e) => onDraftChange(e.target.value)}
                            rows={6}
                            autoFocus
                            aria-label="Modifier le contenu de la réponse"
                            className="w-full rounded-xl border border-gray-200 dark:border-white/15 bg-white dark:bg-white/5 px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 leading-relaxed resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                          />
                        </div>
                      ) : (
                        <ExpandableText text={contenuServi(r)} label={r.question} />
                      )}

                      <MotifSignalement reponse={r} />

                      {/* Per-item confirm error */}
                      {isConfirmError && !isEditing && (
                        <p role="alert" className="text-xs text-red-500 dark:text-red-400">
                          Erreur — signalement non levé. Réessayez.
                        </p>
                      )}

                      {/* Actions */}
                      {enAnalyse ? (
                        <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
                          <Loader2 size={12} className="animate-spin shrink-0" aria-hidden="true" />
                          Analyse IA en cours — résultat dans quelques minutes
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1.5">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => onSave(r.reponse_id)}
                                disabled={!draft.trim() || isPendingEdit}
                                aria-label={`Enregistrer les modifications — ${r.question}`}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                              >
                                <Check size={12} aria-hidden="true" />
                                Enregistrer
                              </button>
                              <button
                                onClick={onCancel}
                                aria-label={`Annuler les modifications — ${r.question}`}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
                              >
                                <X size={12} aria-hidden="true" />
                                Annuler
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => {
                                  setConfirmErrors((prev) => { const n = new Set(prev); n.delete(r.reponse_id); return n; });
                                  setConfirmingId(r.reponse_id);
                                  confirmMutation.mutate(r.reponse_id);
                                }}
                                disabled={confirmMutation.isPending}
                                aria-label={`Toujours d'actualité — ${r.question}`}
                                title="Lever le signalement — confirmer que cette réponse reste valide malgré la mise à jour du document"
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                              >
                                {confirmMutation.isPending && confirmingId === r.reponse_id ? (
                                  <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                                ) : (
                                  <CheckCircle2 size={12} aria-hidden="true" />
                                )}
                                Toujours d'actualité
                              </button>
                              <button
                                onClick={() => onEdit(r)}
                                aria-label={`Modifier — ${r.question}`}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 dark:border-white/12 text-gray-500 dark:text-gray-400 text-xs font-medium hover:text-gray-700 hover:bg-gray-50 dark:hover:text-gray-200 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
                              >
                                <Pencil size={12} aria-hidden="true" />
                                Modifier
                              </button>
                              <button
                                onClick={() => onRetrait(r)}
                                aria-label={`Retirer du service — ${r.question}`}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-amber-200 dark:border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-medium hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
                              >
                                <EyeOff size={12} aria-hidden="true" />
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

      {confirmMutation.isError && confirmErrors.size === 0 && (
        <p role="alert" className="px-5 py-3 text-xs text-red-500 dark:text-red-400 border-t border-gray-100 dark:border-white/8">
          Erreur de confirmation — le signalement n'a pas été levé.
        </p>
      )}
    </>
  );
}
