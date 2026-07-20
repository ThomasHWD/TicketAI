import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getTickets } from "../../lib/api";
import type { Ticket, StatutTicket } from "../../types.ts";

function statutLabel(statut: StatutTicket, canonique: boolean) {
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function statutClass(statut: StatutTicket, canonique: boolean) {
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200";
  if (canonique) return "bg-emerald-50 text-emerald-600 border-emerald-200";
  if (statut === "VALIDÉ") return "bg-blue-50 text-blue-600 border-blue-200";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-600 border-yellow-200";
  return "bg-blue-50 text-blue-600 border-blue-200";
}

function StatutBadge({ statut, canonique }: { statut: StatutTicket; canonique: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${statutClass(statut, canonique)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {statutLabel(statut, canonique)}
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
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getTickets({ page, limit: LIMIT })
      .then((data) => {
        setTickets(data.items);
        setTotal(data.total);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [page]);

  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-800">Tickets</h1>
        <select className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500">
          <option>Trier par date</option>
          <option>Trier par statut</option>
        </select>
      </div>

      {/* Card */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Card header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800">Dernières questions</h2>
          <button className="flex items-center gap-1.5 text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-50 transition-colors">
            Créer un ticket
            <span className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 text-xs font-bold">+</span>
          </button>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 text-green-700 text-left">
                <th className="px-6 py-3 font-medium">Question</th>
                <th className="px-6 py-3 font-medium">Créée le</th>
                <th className="px-6 py-3 font-medium">Statut</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                    Chargement…
                  </td>
                </tr>
              )}
              {error && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-red-400">
                    {error}
                  </td>
                </tr>
              )}
              {!loading && !error && tickets.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-400">
                    Aucun ticket
                  </td>
                </tr>
              )}
              {!loading && tickets.map((t) => (
                <tr
                  key={t.id}
                  className="hover:bg-gray-50 transition-colors cursor-pointer focus-within:bg-gray-50"
                  onClick={() => navigate(`/tickets/${t.id}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${t.id}`); }}
                  tabIndex={0}
                  role="link"
                  aria-label={`Voir le ticket : ${t.question}`}
                >
                  <td className="px-6 py-4 text-gray-600 max-w-xs truncate" title={t.question}>
                    {t.question}
                  </td>
                  <td className="px-6 py-4 text-gray-500 whitespace-nowrap">
                    {formatDate(t.created_at)}
                  </td>
                  <td className="px-6 py-4">
                    <StatutBadge statut={t.statut_ticket as StatutTicket} canonique={t.canonique} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!loading && total > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 text-sm text-gray-500">
            <span>{from}–{to} sur {total}</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
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
