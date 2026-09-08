import { useNavigate } from "react-router-dom";
import { AlertCircle, ChevronLeft, ChevronRight, Inbox, Plus } from "lucide-react";
import { formatRelativeDate, formatDate } from "../../lib/ticketStatus";
import UserStatutBadge from "../ui/UserStatutBadge";
import { AutoClotureTimer } from "./AutoClotureTimer";
import type { Ticket } from "../../types";

function DomainChip({ domaine }: { domaine: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10 whitespace-nowrap">
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      {domaine}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse" aria-hidden="true">
      <td className="px-5 py-4"><div className="h-4 rounded-md bg-gray-200 dark:bg-white/10 w-3/4" /></td>
      <td className="hidden sm:table-cell px-5 py-4"><div className="h-5 rounded-full bg-gray-200 dark:bg-white/10 w-16" /></td>
      <td className="hidden sm:table-cell px-5 py-4"><div className="h-4 rounded-md bg-gray-200 dark:bg-white/10 w-28" /></td>
      <td className="px-5 py-4"><div className="h-5 rounded-full bg-gray-200 dark:bg-white/10 w-24" /></td>
    </tr>
  );
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <tr><td colSpan={4}>
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-11 h-11 rounded-2xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center mb-4">
          <AlertCircle size={20} className="text-red-500 dark:text-red-400" aria-hidden="true" />
        </div>
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Impossible de charger vos questions</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {error instanceof Error ? error.message : "Une erreur est survenue. Réessayez dans quelques instants."}
        </p>
        <button onClick={onRetry} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 transition-colors">
          Réessayer
        </button>
      </div>
    </td></tr>
  );
}

function EmptyState({ isFiltered, onNew, onReset }: { isFiltered: boolean; onNew: () => void; onReset: () => void }) {
  return (
    <tr><td colSpan={4}>
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-11 h-11 rounded-2xl bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 flex items-center justify-center mb-4 shadow-sm">
          <Inbox size={20} className="text-gray-500 dark:text-gray-400" aria-hidden="true" />
        </div>
        {isFiltered ? (
          <>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Aucun résultat</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">Aucune question ne correspond à ce filtre.</p>
            <button onClick={onReset} className="text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:underline">Effacer les filtres</button>
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Aucune question pour l'instant</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-5">Vos échanges avec le service d'assistance apparaîtront ici.</p>
            <button onClick={onNew} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-2 transition-colors">
              <Plus size={15} aria-hidden="true" />Poser ma première question
            </button>
          </>
        )}
      </div>
    </td></tr>
  );
}

interface TicketHistoryTableProps {
  tickets: Ticket[];
  isLoading: boolean;
  error: unknown;
  isFiltered: boolean;
  joursAutoCloture: number;
  from: number;
  to: number;
  page: number;
  totalPages: number;
  filteredCount: number;
  onRetry: () => void;
  onNew: () => void;
  onReset: () => void;
  onPageChange: (updater: (p: number) => number) => void;
}

export function TicketHistoryTable({
  tickets, isLoading, error, isFiltered, joursAutoCloture,
  from, to, page, totalPages, filteredCount,
  onRetry, onNew, onReset, onPageChange,
}: TicketHistoryTableProps) {
  const navigate = useNavigate();

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label="Historique des questions">
          <thead>
            <tr className="border-b border-gray-100 dark:border-white/5 bg-gray-50/60 dark:bg-white/[0.02]">
              <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide w-full">Objet</th>
              <th className="hidden sm:table-cell px-5 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Domaine</th>
              <th className="hidden sm:table-cell px-5 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">Posée le</th>
              <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide whitespace-nowrap">Statut</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50 dark:divide-white/[0.04]" aria-busy={isLoading}>
            {isLoading && Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)}
            {!isLoading && !!error && <ErrorState error={error} onRetry={onRetry} />}
            {!isLoading && !error && tickets.length === 0 && (
              <EmptyState isFiltered={isFiltered} onNew={onNew} onReset={onReset} />
            )}
            {!isLoading && !error && tickets.map((t) => (
              <tr
                key={t.id}
                onClick={() => navigate(`/historique/${t.id}`)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate(`/historique/${t.id}`); } }}
                tabIndex={0}
                aria-label={`Voir le détail de : ${t.objet ?? t.question}`}
                className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors duration-100 cursor-pointer focus-within:bg-gray-50/80 dark:focus-within:bg-white/[0.03] focus-visible:outline-none"
              >
                <td className="px-5 py-4">
                  <span className="block truncate font-medium text-gray-800 dark:text-gray-200 group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors duration-100" title={t.objet ?? t.question}>
                    {t.objet ?? t.question}
                  </span>
                </td>
                <td className="hidden sm:table-cell px-5 py-4">
                  <DomainChip domaine={t.domaine} />
                </td>
                <td className="hidden sm:table-cell px-5 py-4 whitespace-nowrap">
                  <span className="text-xs text-gray-500 dark:text-gray-400" title={formatDate(t.created_at)}>
                    {formatRelativeDate(t.created_at)}
                  </span>
                </td>
                <td className="px-5 py-4 whitespace-nowrap">
                  <div className="flex flex-col items-start gap-0.5">
                    <UserStatutBadge ticket={t} />
                    <AutoClotureTimer ticket={t} joursConfig={joursAutoCloture} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!isLoading && filteredCount > 0 && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.01]">
          <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums" aria-live="polite">
            {from}–{to} sur {filteredCount} question{filteredCount > 1 ? "s" : ""}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => onPageChange((p) => Math.max(1, p - 1))} disabled={page === 1} aria-label="Page précédente" className="p-2 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <span className="text-xs text-gray-500 dark:text-gray-400 px-2 tabular-nums font-medium">{page} / {totalPages}</span>
            <button onClick={() => onPageChange((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} aria-label="Page suivante" className="p-2 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
