import { useNavigate } from "react-router-dom";
import {
  ChevronLeft, ChevronRight, CheckCircle2, Inbox, AlertTriangle,
  Lock, UserCheck, Loader2,
} from "lucide-react";
import { isProcessing } from "../../lib/ticketStatus";
import { formatDateShort, formatDateFull } from "../../lib/ticketStatus";
import { getListErrorMessage } from "../../lib/ticketFilters";
import { StatusBadge, DomaineBadge } from "./StatusBadge";
import type { Ticket, StatutTicket } from "../../types";

const SKELETON_WIDTHS = ["w-3/4", "w-2/3", "w-4/5", "w-1/2", "w-3/5", "w-5/6"];

function EmptyState({ hasFilters, isClosed, colSpan }: { hasFilters: boolean; isClosed: boolean; colSpan: number }) {
  const isSuccess = !hasFilters && !isClosed;
  return (
    <tr>
      <td colSpan={colSpan}>
        <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-sm border ${
            isSuccess
              ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20"
              : "bg-gray-50 dark:bg-white/5 border-gray-200 dark:border-white/10"
          }`}>
            {isSuccess
              ? <CheckCircle2 size={20} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
              : <Inbox size={20} className="text-subtle" aria-hidden="true" />
            }
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {hasFilters ? "Aucun résultat" : isClosed ? "Aucun ticket clôturé" : "File d'attente vide"}
            </p>
            <p className="text-xs text-muted-foreground">
              {hasFilters
                ? "Essayez d'autres filtres."
                : isClosed
                ? "Aucun ticket n'a encore été clôturé."
                : "Tous les tickets ont été traités — belle session !"}
            </p>
          </div>
        </div>
      </td>
    </tr>
  );
}

interface TicketsTableProps {
  tickets: Ticket[];
  isLoading: boolean;
  isFetchingBg: boolean;
  error: unknown;
  hasFilters: boolean;
  isClosed: boolean;
  multiDomain: boolean;
  total: number;
  from: number;
  to: number;
  page: number;
  totalPages: number;
  onPageChange: (updater: (p: number) => number) => void;
  onRefetch: () => void;
}

export function TicketsTable({
  tickets, isLoading, isFetchingBg, error,
  hasFilters, isClosed, multiDomain,
  total, from, to, page, totalPages,
  onPageChange, onRefetch,
}: TicketsTableProps) {
  const navigate = useNavigate();
  const errorMsg = error ? getListErrorMessage(error) : null;
  const colCount = multiDomain ? 5 : 4;

  return (
    <div id="tickets-table" className="glass-card rounded-xl overflow-hidden" role="tabpanel">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-white/5 bg-gray-50/60 dark:bg-white/[0.02]">
              <th className="px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide w-full">Objet</th>
              <th className="px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap hidden sm:table-cell">Créé</th>
              {multiDomain && (
                <th className="px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap hidden md:table-cell">Domaine</th>
              )}
              <th className="px-5 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide whitespace-nowrap">Statut</th>
              <th className="px-5 py-3 w-8 hidden sm:table-cell" aria-hidden="true" />
            </tr>
          </thead>

          <tbody className="divide-y divide-gray-50 dark:divide-white/[0.04]">
            {isLoading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="animate-pulse">
                <td className="px-5 py-4">
                  <div className="space-y-1.5">
                    <div className={`h-3.5 bg-gray-100 dark:bg-white/5 rounded ${SKELETON_WIDTHS[i % SKELETON_WIDTHS.length]}`} />
                    <div className="h-2.5 bg-gray-50 dark:bg-white/[0.03] rounded w-1/3" />
                  </div>
                </td>
                <td className="px-5 py-4 hidden sm:table-cell"><div className="h-3 bg-gray-100 dark:bg-white/5 rounded w-16" /></td>
                {multiDomain && <td className="px-5 py-4 hidden md:table-cell"><div className="h-5 bg-gray-100 dark:bg-white/5 rounded w-12" /></td>}
                <td className="px-5 py-4"><div className="h-5 bg-gray-100 dark:bg-white/5 rounded-full w-20" /></td>
                <td className="px-5 py-4 hidden sm:table-cell" />
              </tr>
            ))}

            {!isLoading && !!error && errorMsg && (
              <tr>
                <td colSpan={colCount} className="px-5 py-12 text-center">
                  <div className="flex flex-col items-center gap-4" role="alert">
                    <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 flex items-center justify-center shadow-sm">
                      <AlertTriangle size={20} className="text-red-500 dark:text-red-400" aria-hidden="true" />
                    </div>
                    <div className="space-y-1">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{errorMsg.title}</p>
                      <p className="text-xs text-muted-foreground">{errorMsg.detail}</p>
                    </div>
                    {errorMsg.loginPath ? (
                      <a href="/login" className="px-3 py-1.5 text-xs font-medium rounded-lg bg-primary hover:bg-primary-hover text-primary-foreground transition-colors">
                        Se reconnecter
                      </a>
                    ) : (
                      <button
                        onClick={onRefetch}
                        className="px-3 py-1.5 text-xs font-medium rounded-lg bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                      >
                        Réessayer
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )}

            {!isLoading && !error && tickets.length === 0 && (
              <EmptyState hasFilters={hasFilters} isClosed={isClosed} colSpan={colCount} />
            )}

            {!isLoading && !error && tickets.map((t: Ticket) => {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const tx = t as any;
              const locked = !!(t.lock_expires_at && new Date(t.lock_expires_at) > new Date());
              const processing = isProcessing(t.statut_job);
              const title: string = tx.objet ?? t.question;
              const closed = !!tx.closed_at;
              const reponseSource: string | null = tx.reponse_source ?? null;
              const assignedNom: string | null = tx.assigned_to_nom_complet ?? tx.assigned_to_email ?? null;
              const lockedEmail: string = t.locked_by_email ?? "un validateur";

              return (
                <tr
                  key={t.id}
                  className={`group transition-colors duration-100 focus-within:bg-gray-50/80 dark:focus-within:bg-white/[0.03] ${
                    locked
                      ? "cursor-default opacity-75 hover:opacity-90 hover:bg-amber-50/30 dark:hover:bg-amber-500/5"
                      : "cursor-pointer hover:bg-gray-50/80 dark:hover:bg-white/[0.03]"
                  }`}
                  onClick={() => { if (!locked) navigate(`/tickets/${t.id}`); }}
                  onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !locked) navigate(`/tickets/${t.id}`); }}
                  tabIndex={locked ? -1 : 0}
                  aria-label={`${title}${locked ? ` — non disponible, pris en charge par ${lockedEmail}` : ""}`}
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2 min-w-0">
                      {locked && (
                        <span
                          className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20 text-[10px] font-medium"
                          aria-label={`Pris en charge par ${lockedEmail}`}
                        >
                          <Lock size={11} aria-hidden="true" />
                          <span className="hidden sm:inline">En cours</span>
                        </span>
                      )}
                      <div className="min-w-0 flex-1">
                        <span
                          className="block truncate text-gray-800 dark:text-gray-200 font-medium text-sm group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors duration-100"
                          title={title}
                        >
                          {title}
                        </span>
                        {t.user_email && (
                          <span className="text-xs text-muted-foreground truncate mt-0.5 block">
                            {t.user_email}
                          </span>
                        )}
                      </div>
                      {assignedNom && (
                        <span
                          className="shrink-0 hidden md:inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-600 border border-violet-100 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20"
                          title={`Assigné à ${assignedNom}`}
                        >
                          <UserCheck size={11} aria-hidden="true" />
                          {assignedNom}
                        </span>
                      )}
                    </div>
                  </td>

                  <td className="px-5 py-4 text-xs text-muted-foreground whitespace-nowrap hidden sm:table-cell">
                    <time dateTime={t.created_at ?? undefined} title={formatDateFull(t.created_at)}>
                      {formatDateShort(t.created_at)}
                    </time>
                  </td>

                  {multiDomain && (
                    <td className="px-5 py-4 hidden md:table-cell">
                      <DomaineBadge domaine={t.domaine} />
                    </td>
                  )}

                  <td className="px-5 py-4 whitespace-nowrap">
                    <StatusBadge
                      statut={t.statut_ticket as StatutTicket}
                      canonique={t.canonique}
                      closed={closed}
                      processing={processing}
                      reponseSource={reponseSource}
                    />
                  </td>

                  <td className="px-5 py-4 hidden sm:table-cell">
                    <ChevronRight
                      size={14}
                      className="text-subtle group-hover:text-gray-500 dark:group-hover:text-gray-400 group-hover:translate-x-0.5 transition-all duration-150"
                      aria-hidden="true"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!isLoading && total > 0 && (
        <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.01]">
          <span className="text-xs text-muted-foreground tabular-nums flex items-center gap-2">
            {from}–{to} sur {total} ticket{total > 1 ? "s" : ""}
            {isFetchingBg && (
              <span className="inline-flex items-center gap-1 text-muted-foreground" aria-live="polite" aria-label="Actualisation en cours">
                <Loader2 size={11} className="animate-spin" aria-hidden="true" />
                Actualisation…
              </span>
            )}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md text-muted-foreground hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              aria-label="Page précédente"
            >
              <ChevronLeft size={14} aria-hidden="true" />
            </button>
            <span className="text-xs text-muted-foreground px-2 tabular-nums font-medium">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => onPageChange((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md text-muted-foreground hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              aria-label="Page suivante"
            >
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
