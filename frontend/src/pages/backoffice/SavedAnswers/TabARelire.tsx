import { useEffect, useId, useState } from "react";
import type { UseMutationResult } from "@tanstack/react-query";
import type { ReponseSignalee } from "../../../types";
import { type GroupeARelire } from "./utils";
import { GroupeHeader } from "./GroupeHeader";
import { ReponseItemARelire } from "./ReponseItemARelire";

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
  groupes, loading, error, total,
  groupesReplies, editingId, draft, isPendingEdit,
  confirmMutation, confirmLotMutation,
  onToggleGroupe, onCollapseAll, onExpandAll, onRetry,
  onEdit, onSave, onCancel, onDraftChange, onRetrait,
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
        <button onClick={onRetry} className="text-xs text-gray-500 dark:text-gray-400 underline underline-offset-2 hover:text-gray-700 dark:hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 rounded-sm">
          Réessayer
        </button>
      </div>
    );
  }

  if (total === 0) {
    return (
      <div className="px-5 py-16 text-center space-y-1">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Aucune réponse à relire</p>
        <p className="text-xs text-gray-500 dark:text-gray-400">Toutes les réponses sont à jour.</p>
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
            className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 rounded-sm"
            aria-label={allCollapsed ? "Développer tous les groupes" : "Réduire tous les groupes"}
          >
            {allCollapsed ? "Tout développer" : "Tout réduire"}
          </button>
        </div>
      )}

      <div className="divide-y divide-gray-100 dark:divide-white/5">
        {groupes.map((g) => {
          const ouvert = !groupesReplies.has(g.cle);
          const slug = g.cle.replace(/[^a-zA-Z0-9]/g, "-");
          const diffId = `group-diff-${slug}`;
          const headingId = `${uid}-group-heading-${slug}`;
          return (
            <section key={g.cle} aria-labelledby={headingId} className="px-5 py-4 space-y-3">
              <GroupeHeader
                g={g} ouvert={ouvert} diffId={diffId} headingId={headingId}
                confirmingLot={confirmingLot} setConfirmingLot={setConfirmingLot}
                pendingLotCle={pendingLotCle} setPendingLotCle={setPendingLotCle}
                lotErrorCles={lotErrorCles} setLotErrorCles={setLotErrorCles}
                confirmLotMutation={confirmLotMutation}
                onToggleGroupe={onToggleGroupe}
              />
              <ul className="space-y-1.5">
                {g.reponses.map((r) => (
                  <ReponseItemARelire
                    key={r.reponse_id}
                    r={r}
                    filename={g.filename}
                    version={g.version}
                    editingId={editingId}
                    draft={draft}
                    isPendingEdit={isPendingEdit}
                    confirmMutation={confirmMutation}
                    confirmingId={confirmingId}
                    setConfirmingId={setConfirmingId}
                    confirmErrors={confirmErrors}
                    setConfirmErrors={setConfirmErrors}
                    onEdit={onEdit}
                    onSave={onSave}
                    onCancel={onCancel}
                    onDraftChange={onDraftChange}
                    onRetrait={onRetrait}
                  />
                ))}
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
