import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getTickets } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Ticket } from "../../types";

function StatutBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10">
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      Clôturé
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

export default function ClosedTicketsList() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const { userDomaines } = useAuth();

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ["tickets", "closed", page, userDomaines],
    queryFn: () => getTickets({ page, limit: LIMIT, closed: true, domaines: userDomaines }),
    placeholderData: (prev) => prev,
  });

  const tickets = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Tickets clôturés</h1>
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">Historique des tickets clôturés</h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Objet</th>
                <th className="px-6 py-3 font-medium">Créée le</th>
                <th className="px-6 py-3 font-medium">Clôturé le</th>
                <th className="px-6 py-3 font-medium">Statut</th>
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
              {!loading && !error && tickets.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                    Aucun ticket clôturé
                  </td>
                </tr>
              )}
              {!loading && tickets.map((t: Ticket) => (
                <tr
                  key={t.id}
                  className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer focus-within:bg-gray-50 dark:focus-within:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
                  onClick={() => navigate(`/tickets/${t.id}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${t.id}`); }}
                  tabIndex={0}
                  role="link"
                  aria-label={`Voir le ticket : ${t.objet ?? t.question}`}
                >
                  <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                    <span className="truncate max-w-xs block" title={t.objet ?? t.question}>{t.objet ?? t.question}</span>
                  </td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    {formatDate(t.created_at)}
                  </td>
                  <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    {formatDate(t.closed_at ?? null)}
                  </td>
                  <td className="px-6 py-4">
                    <StatutBadge />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

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
