import type { RepartitionBranche } from "../../lib/api";
import { useTheme } from "../../hooks/useTheme";

type Periode = "semaine" | "mois" | "annee";

const PERIODE_LABEL: Record<Periode, string> = {
  semaine: "cette semaine",
  mois: "ce mois",
  annee: "cette année",
};

const BRANCHE_CONFIG: Record<string, { label: string; color: string; darkColor: string; description: string }> = {
  CANONIQUE:    { label: "Canonique",     color: "#8b5cf6", darkColor: "#a78bfa", description: "Réponse automatique haute confiance — servie sans intervention humaine" },
  SUGGESTION:   { label: "Suggestion",    color: "#0d9488", darkColor: "#2dd4bf", description: "Réponse réutilisée depuis une réponse validée — soumise à validation humaine" },
  LLM:          { label: "Génération IA", color: "#e11d48", darkColor: "#fb7185", description: "Réponse générée par l'IA depuis les documents — soumise à validation humaine" },
  HORS_DOMAINE: { label: "Hors domaine",  color: "#f97316", darkColor: "#fb923c", description: "Ticket sans domaine correspondant dans la base de connaissances" },
};

interface BranchesDonutProps {
  data: RepartitionBranche[];
  loading?: boolean;
  periode?: Periode;
}

export default function BranchesDonut({ data, loading = false, periode }: BranchesDonutProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse space-y-4">
        <div className="h-4 bg-gray-200 dark:bg-white/10 rounded w-2/5" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <div className="flex justify-between">
              <div className="h-3.5 bg-gray-200 dark:bg-white/10 rounded w-1/4" />
              <div className="h-3.5 bg-gray-200 dark:bg-white/10 rounded w-12" />
            </div>
            <div className="h-1.5 bg-gray-200 dark:bg-white/10 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  const total = data.reduce((s, d) => s + d.count, 0);
  const periodeLabel = periode ? PERIODE_LABEL[periode] : null;

  return (
    <div className="glass-card p-5 rounded-2xl flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Branches de traitement{periodeLabel ? ` — ${periodeLabel}` : ""}
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
          {total} ticket{total > 1 ? "s" : ""}
        </span>
      </div>

      {total === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">
          Aucune donnée sur cette période
        </p>
      ) : (
        <div className="space-y-5">
          {[...data].sort((a, b) => b.count - a.count).map((d) => {
            const cfg = BRANCHE_CONFIG[d.branche];
            if (!cfg) return null;
            const color = isDark ? cfg.darkColor : cfg.color;
            const descId = `branche-desc-${d.branche}`;
            return (
              <div key={d.branche} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span
                    className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200"
                    aria-describedby={descId}
                  >
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} aria-hidden />
                    {cfg.label}
                    <span id={descId} className="sr-only">{cfg.description}</span>
                  </span>
                  <div className="flex items-center gap-3 tabular-nums">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {d.count} ticket{d.count > 1 ? "s" : ""}
                    </span>
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 w-10 text-right">
                      {d.pct}%
                    </span>
                  </div>
                </div>
                <div className="h-1.5 rounded-full bg-gray-100 dark:bg-white/10 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${d.pct}%`, backgroundColor: color }}
                    role="progressbar"
                    aria-valuenow={d.pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${cfg.label} : ${d.pct}%`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
