import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronRight, HelpCircle } from "lucide-react";

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
  RÉPONDU: { prefix: "→", label: "Répondu" },
  VALIDÉ:  { prefix: "✓", label: "Validé" },
  REJETÉ:  { prefix: "✕", label: "Rejeté" },
};

const BRANCHE_BADGE: Record<string, { label: string; className: string }> = {
  CANONIQUE:  { label: "Auto",  className: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300" },
  SUGGESTION: { label: "Sugg.", className: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300" },
  LLM:        { label: "RAG",   className: "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300" },
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
  const [showLegend, setShowLegend] = useState(false);

  useEffect(() => {
    if (!showLegend) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setShowLegend(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showLegend]);

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
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
            Derniers tickets
          </h3>
          <div className="relative">
            <button
              type="button"
              aria-expanded={showLegend}
              aria-describedby="branch-legend"
              onClick={() => setShowLegend((v) => !v)}
              className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 rounded"
            >
              <HelpCircle size={12} />
              <span className="sr-only">Légende des branches</span>
            </button>
            {showLegend && (
              <div
                id="branch-legend"
                role="tooltip"
                className="absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 z-10 w-52 bg-gray-900 dark:bg-gray-800 text-white text-[10px] rounded-lg p-2.5 shadow-lg space-y-1.5"
              >
                <p className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-violet-400 shrink-0" aria-hidden="true" />
                  Auto = validé automatiquement
                </p>
                <p className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-400 shrink-0" aria-hidden="true" />
                  Sugg. = réponse suggérée
                </p>
                <p className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-400 shrink-0" aria-hidden="true" />
                  RAG = généré par IA
                </p>
              </div>
            )}
          </div>
        </div>
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
          {tickets.map((t) => (
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
                  <span className="text-xs text-gray-500 dark:text-gray-400">{t.domaine}</span>
                  {t.branche && BRANCHE_BADGE[t.branche] && (
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${BRANCHE_BADGE[t.branche].className}`}>
                      {BRANCHE_BADGE[t.branche].label}
                    </span>
                  )}
                  {t.created_at && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      · {new Date(t.created_at).toLocaleDateString("fr-FR")}
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
