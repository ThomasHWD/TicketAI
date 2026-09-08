import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

interface TicketSummary {
  id: string;
  objet: string;
  domaine: string;
  statut_ticket: string;
  branche?: string | null;
  created_at: string | null;
}

const STATUT_STYLE: Record<string, string> = {
  NOUVEAU:  "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  RÉPONDU:  "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  VALIDÉ:   "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  REJETÉ:   "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

const STATUT_META: Record<string, { prefix: string; label: string }> = {
  NOUVEAU: { prefix: "",   label: "Nouveau" },
  RÉPONDU: { prefix: "→", label: "En attente" },
  VALIDÉ:  { prefix: "✓", label: "Validé" },
  REJETÉ:  { prefix: "✕", label: "Rejeté" },
};


function StatutBadge({ statut }: { statut: string }) {
  const style = STATUT_STYLE[statut] ?? "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300";
  const meta = STATUT_META[statut];
  return (
    <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${style}`}>
      {meta ? (
        <>
          {meta.prefix && <span aria-hidden="true">{meta.prefix} </span>}
          {meta.label}
        </>
      ) : statut}
    </span>
  );
}

interface RecentTicketsProps {
  tickets: TicketSummary[];
  loading?: boolean;
}

export default function RecentTickets({ tickets, loading = false }: RecentTicketsProps) {

  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse space-y-3">
        <div className="h-5 bg-gray-200 dark:bg-white/10 rounded w-1/3" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-10 bg-gray-200 dark:bg-white/10 rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="glass-card p-5 rounded-2xl space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Derniers tickets
        </h3>
        <Link
          to="/tickets"
          className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline font-medium"
          aria-label="Voir tous les tickets"
        >
          Voir tous →
        </Link>
      </div>

      {tickets.length === 0 ? (
        <div className="py-5 text-center space-y-2">
          <p className="text-sm text-gray-500 dark:text-gray-400">Aucun ticket pour le moment</p>
          <Link to="/tickets" className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline font-medium">
            Commencer à traiter les tickets →
          </Link>
        </div>
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-white/5">
          {tickets.slice(0, 5).map((t) => (
            <Link
              key={t.id}
              to={`/tickets/${t.id}`}
              className="flex items-center gap-3 py-2.5 hover:bg-gray-50/50 dark:hover:bg-white/3 rounded-lg px-1 -mx-1 transition-colors group"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-800 dark:text-gray-200 truncate font-medium">
                  {t.objet}
                </p>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  {t.created_at && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                       {new Date(t.created_at).toLocaleDateString("fr-FR")}
                    </span>
                  )}
                </div>
              </div>
              <StatutBadge statut={t.statut_ticket} />
              <ChevronRight size={14} className="shrink-0 text-gray-300 dark:text-gray-600 group-hover:text-gray-500 dark:group-hover:text-gray-400 transition-colors" aria-hidden="true" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
