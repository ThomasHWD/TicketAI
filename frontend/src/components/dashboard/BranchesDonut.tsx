import type { RepartitionBranche } from "../../lib/api";
import { useTheme } from "../../hooks/useTheme";

const BRANCHE_CONFIG: Record<string, { label: string; color: string; darkColor: string }> = {
  CANONIQUE:    { label: "Canonique",      color: "#8b5cf6", darkColor: "#a78bfa" },
  SUGGESTION:   { label: "Suggestion",     color: "#0d9488", darkColor: "#2dd4bf" },
  LLM:          { label: "Génération IA",  color: "#e11d48", darkColor: "#fb7185" },
  HORS_DOMAINE: { label: "Hors domaine",   color: "#9333ea", darkColor: "#c084fc" },
};

interface BranchesDonutProps {
  data: RepartitionBranche[];
  loading?: boolean;
}

export default function BranchesDonut({ data, loading = false }: BranchesDonutProps) {
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

  return (
    <div className="glass-card p-5 rounded-2xl flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Branches de traitement
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
          {total} ticket{total > 1 ? "s" : ""}
        </span>
      </div>

      {total === 0 ? (
        <p className="text-sm text-gray-400 dark:text-gray-600 text-center py-6">
          Aucune donnée sur cette période
        </p>
      ) : (
        <div className="space-y-5">
          {[...data].sort((a, b) => b.count - a.count).map((d) => {
            const cfg = BRANCHE_CONFIG[d.branche];
            if (!cfg) return null;
            const color = isDark ? cfg.darkColor : cfg.color;
            return (
              <div key={d.branche} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                    {cfg.label}
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
