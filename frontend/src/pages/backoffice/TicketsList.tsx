import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Lock } from "lucide-react";
import { getTickets } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Ticket, StatutTicket } from "../../types.ts";

function isLocked(t: Ticket): boolean {
  return !!(t.lock_expires_at && new Date(t.lock_expires_at) > new Date());
}

// Job en cours (question initiale OU précision fraîchement soumise) → « en cours ».
function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function statutLabel(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean) {
  if (closed) return "Clôturé";
  if (processing) return "En cours";
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function statutClass(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean) {
  if (closed) return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10";
  if (processing) return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ") return "bg-red-500/10 text-red-700 border-red-300/50 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique) return "bg-emerald-500/10 text-emerald-700 border-emerald-300/50 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉ") return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "RÉPONDU") return "bg-amber-500/10 text-amber-700 border-amber-300/50 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
}

function StatutBadge({ statut, canonique, closed, processing }: { statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${statutClass(statut, canonique, closed, processing)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {statutLabel(statut, canonique, closed, processing)}
    </span>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}


const LIMIT = 10;

export default function TicketsList() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const { userDomaines } = useAuth();

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ["tickets", "open", page, userDomaines],
    queryFn: () => getTickets({ page, limit: LIMIT, closed: false, domaines: userDomaines }),
    placeholderData: (prev) => prev,
  });

  const tickets = data?.items ?? [];
  const total = data?.total ?? 0;

  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Tickets</h1>
      </div>

      {/* Card */}
      <div className="glass-card rounded-2xl overflow-hidden">
        {/* Card header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-white/10">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">Dernières questions</h2>
          <button
            onClick={() => navigate("/nouveau-ticket")}
            className="flex items-center gap-1.5 text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-1.5 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
          >
            Créer un ticket
            <span className="w-5 h-5 rounded-full bg-gray-100 dark:bg-white/10 flex items-center justify-center text-gray-500 dark:text-gray-300 text-xs font-bold" aria-hidden="true">+</span>
          </button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Objet</th>
                <th className="px-6 py-3 font-medium">Créée le</th>
                <th className="px-6 py-3 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/5">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Chargement…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-red-600 dark:text-red-400">
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}
              {!loading && !error && tickets.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Aucun ticket
                  </td>
                </tr>
              )}
              {!loading && tickets.map((t) => {
                const locked = isLocked(t);
                return (
                <tr
                  key={t.id}
                  className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer focus-within:bg-gray-50 dark:focus-within:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
                  onClick={() => navigate(`/tickets/${t.id}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${t.id}`); }}
                  tabIndex={0}
                  role="link"
                  aria-label={`Voir le ticket : ${t.objet ?? t.question}${locked ? ` (pris en charge par ${t.locked_by_email ?? "un validateur"})` : ""}`}
                >
                  <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                    <div className="flex items-center gap-2 min-w-0">
                      {locked && (
                        <span
                          className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-50 text-amber-500 ring-1 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20"
                          title={`Pris en charge par ${t.locked_by_email ?? "un validateur"}`}
                        >
                          <Lock size={11} aria-hidden="true" />
                        </span>
                      )}
                      <span className="truncate max-w-xs" title={t.objet ?? t.question}>{t.objet ?? t.question}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    {formatDate(t.created_at)}
                  </td>
                  <td className="px-6 py-4">
                    <StatutBadge statut={t.statut_ticket as StatutTicket} canonique={t.canonique} closed={!!t.closed_at} processing={isProcessing(t.statut_job)} />
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
            <span>{from}–{to} sur {total}</span>
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
    </div>
  );
}
