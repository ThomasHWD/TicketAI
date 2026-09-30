import type { UseMutationResult } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
  Loader2,
} from "lucide-react";
import { estRaisonDeGroupe, RAISONS, type GroupeARelire } from "./utils";
import SensDuChangement from "./SensDuChangement";

interface GroupeHeaderProps {
  g: GroupeARelire;
  ouvert: boolean;
  diffId: string;
  headingId: string;
  confirmingLot: string | null;
  setConfirmingLot: React.Dispatch<React.SetStateAction<string | null>>;
  pendingLotCle: string | null;
  setPendingLotCle: React.Dispatch<React.SetStateAction<string | null>>;
  lotErrorCles: Set<string>;
  setLotErrorCles: React.Dispatch<React.SetStateAction<Set<string>>>;
  confirmLotMutation: UseMutationResult<void, Error, { doc_id: string; version: number }>;
  onToggleGroupe: (cle: string) => void;
}

export function GroupeHeader({
  g, ouvert, diffId, headingId,
  confirmingLot, setConfirmingLot,
  pendingLotCle, setPendingLotCle,
  lotErrorCles, setLotErrorCles,
  confirmLotMutation, onToggleGroupe,
}: GroupeHeaderProps) {
  return (
    <div className="rounded-xl border border-amber-200/70 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-400/5 overflow-hidden">
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
                <span className="shrink-0 px-1.5 py-px rounded text-xs font-medium bg-gray-200/80 text-gray-700 dark:bg-white/10 dark:text-gray-300">
                  supprimé
                </span>
              )}
            </div>
            <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">
              {g.reponses.length} réponse{g.reponses.length > 1 ? "s affichées" : " affichée"}
            </p>
          </div>
          {ouvert
            ? <ChevronUp size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" aria-hidden="true" />
            : <ChevronDown size={13} className="shrink-0 text-amber-600/50 dark:text-amber-400/50 ml-auto" aria-hidden="true" />}
        </button>

        {g.doc_id !== null && g.version !== null && (
          confirmingLot === g.cle ? (
            <div className="shrink-0 flex items-center gap-1.5">
              <span role="alert" className="text-xs font-medium text-amber-900 dark:text-amber-200">
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
                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md bg-primary hover:bg-primary-hover text-primary-foreground text-xs font-semibold disabled:opacity-40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                {confirmLotMutation.isPending
                  ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                  : <CheckCircle2 size={12} aria-hidden="true" />}
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
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary hover:bg-primary-hover text-primary-foreground text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
            >
              {pendingLotCle === g.cle && confirmLotMutation.isPending
                ? <Loader2 size={13} className="animate-spin" aria-hidden="true" />
                : <CheckCircle2 size={13} aria-hidden="true" />}
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

      {/* Always in DOM so aria-controls resolves */}
      <div
        id={diffId}
        className={`border-t border-amber-200/50 dark:border-amber-500/15 px-4 py-3 space-y-3${!ouvert ? " hidden" : ""}`}
      >
        {estRaisonDeGroupe(g.raison) ? (
          <p className="text-xs text-amber-800 dark:text-amber-200">
            {RAISONS[g.raison!]} Ces réponses sont signalées par précaution.
          </p>
        ) : g.changements ? (
          <>
            <SensDuChangement titre="ajouté" total={g.changements.nb_ajoutes} extraits={g.changements.extraits_ajoutes} />
            <SensDuChangement titre="retiré" total={g.changements.nb_retires} extraits={g.changements.extraits_retires} />
          </>
        ) : (
          <p className="text-xs text-amber-800 dark:text-amber-200">
            Le détail de cette mise à jour n'a pas été conservé.
          </p>
        )}
      </div>
    </div>
  );
}
