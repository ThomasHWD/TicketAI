import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import type { Ticket, StatutTicket } from "../../types.ts";

// Un job en cours (question initiale OU précision qui vient d'être soumise)
// prime : le ticket est « en cours de traitement ».
function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

// La réponse n'est « disponible » pour l'utilisateur qu'une fois validée
// (statut_ticket VALIDÉ) ou canonique. Clôturé prime, puis le traitement en cours.
function statutLabel(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
) {
  if (closed) return "Clôturé";
  if (processing) return "En cours de traitement";
  if (statut === "REJETÉ") return "Sans réponse";
  if (statut === "VALIDÉ" || canonique) return "Répondu";
  return "En cours de traitement";
}

function statutClass(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
) {
  if (closed)
    return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10";
  if (processing)
    return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ")
    return "bg-red-500/10 text-red-700 border-red-300/50 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (statut === "VALIDÉ" || canonique)
    return "bg-emerald-500/10 text-emerald-700 border-emerald-300/50 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
}

function StatutBadge({
  statut,
  canonique,
  closed,
  processing,
}: {
  statut: StatutTicket;
  canonique: boolean;
  closed: boolean;
  processing: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${statutClass(statut, canonique, closed, processing)}`}
    >
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

export default function UserTicketHistory() {
  const navigate = useNavigate();
  const userId = getValidatorId();
  const [page, setPage] = useState(1);

  const { data, isLoading: loading, error } = useQuery({
    queryKey: ["mes-tickets", userId, page],
    queryFn: () => getTickets({ page, limit: LIMIT, userId }),
    placeholderData: (prev) => prev,
  });

  const tickets: Ticket[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Mon historique
        </h1>
      </div>

      {/* Card */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                <th className="px-6 py-3 font-medium">Objet</th>
                <th className="px-6 py-3 font-medium">Domaine</th>
                <th className="px-6 py-3 font-medium">Posée le</th>
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
                    Vous n'avez encore posé aucune question.
                  </td>
                </tr>
              )}
              {!loading &&
                tickets.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer focus-within:bg-gray-50 dark:focus-within:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500"
                    onClick={() => navigate(`/historique/${t.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(`/historique/${t.id}`);
                      }
                    }}
                    tabIndex={0}
                    role="link"
                    aria-label={`Voir le détail de : ${t.objet ?? t.question}`}
                  >
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                      <span className="block truncate max-w-md" title={t.objet ?? t.question}>
                        {t.objet ?? t.question}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                      {t.domaine}
                    </td>
                    <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDate(t.created_at)}
                    </td>
                    <td className="px-6 py-4">
                      <StatutBadge
                        statut={t.statut_ticket as StatutTicket}
                        canonique={t.canonique}
                        closed={!!t.closed_at}
                        processing={isProcessing(t.statut_job)}
                      />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!loading && total > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-white/10 text-sm text-gray-500 dark:text-gray-400">
            <span>
              {from}–{to} sur {total}
            </span>
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
