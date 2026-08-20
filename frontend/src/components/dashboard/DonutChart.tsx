import { useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { useTheme } from "../../hooks/useTheme";

interface StatutItem {
  statut: string;
  count: number;
  pct: number;
}

const STATUT_CONFIG: Record<string, { label: string; color: string; darkColor: string }> = {
  NOUVEAU:    { label: "À traiter", color: "#3b82f6", darkColor: "#60a5fa" },
  "EN COURS": { label: "En cours",  color: "#f59e0b", darkColor: "#fbbf24" },
  CLOTURÉ:    { label: "Clôturés",  color: "#10b981", darkColor: "#34d399" },
};

const DEFAULT_COLOR = "#6b7280";

function CustomTooltip({ active, payload }: { active?: boolean; payload?: { payload: StatutItem }[] }) {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload;
  const cfg = STATUT_CONFIG[item.statut];
  const color = cfg?.color ?? DEFAULT_COLOR;

  return (
    <div className="px-3 py-2 rounded-xl shadow-lg bg-white dark:bg-[#141416] border border-gray-100 dark:border-white/10 text-sm space-y-0.5 min-w-[140px]">
      <div className="flex items-center gap-2 font-semibold text-gray-800 dark:text-gray-100">
        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
        {cfg?.label ?? item.statut}
      </div>
      <div className="pl-4 text-gray-600 dark:text-gray-300">
        <span className="font-bold text-gray-900 dark:text-gray-100">{item.count}</span>
        {" ticket"}{item.count > 1 ? "s" : ""}
      </div>
      <div className="pl-4 text-gray-400 dark:text-gray-500 text-xs">
        {item.pct}% du total
      </div>
    </div>
  );
}

type Periode = "semaine" | "mois" | "annee";

const PERIODE_LABEL: Record<Periode, string> = {
  semaine: "cette semaine",
  mois: "ce mois",
  annee: "cette année",
};

interface DonutChartProps {
  data: StatutItem[];
  loading?: boolean;
  periode?: Periode;
}

export default function DonutChart({ data, loading = false, periode = "semaine" }: DonutChartProps) {
  const [hiddenStatuts, setHiddenStatuts] = useState<Set<string>>(new Set());
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const total = data.reduce((s, d) => s + d.count, 0);
  const visibleData = data.filter((d) => !hiddenStatuts.has(d.statut));

  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse">
        <div className="h-5 bg-gray-200 dark:bg-white/10 rounded w-1/2 mb-4" />
        <div className="flex justify-center">
          <div className="w-48 h-48 rounded-full bg-gray-200 dark:bg-white/10" />
        </div>
      </div>
    );
  }

  function toggleStatut(statut: string) {
    setHiddenStatuts((prev) => {
      const next = new Set(prev);
      if (next.has(statut)) {
        next.delete(statut);
      } else {
        // Ne pas masquer si c'est le dernier statut visible
        const visibleCount = data.length - next.size;
        if (visibleCount <= 1) return prev;
        next.add(statut);
      }
      return next;
    });
  }

  return (
    <div className="glass-card p-5 rounded-2xl space-y-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
        Répartition — {PERIODE_LABEL[periode]}
      </h3>

      <div className="relative h-52">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={visibleData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={88}
              dataKey="count"
              strokeWidth={2}
              stroke="transparent"
            >
              {visibleData.map((entry) => {
                const cfg = STATUT_CONFIG[entry.statut];
                return (
                  <Cell
                    key={entry.statut}
                    fill={cfg ? (isDark ? cfg.darkColor : cfg.color) : DEFAULT_COLOR}
                  />
                );
              })}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>

        {/* Centre du donut */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">{total}</span>
          <span className="text-xs text-gray-500 dark:text-gray-400">tickets</span>
        </div>
      </div>

      {/* Légende interactive */}
      <div className="flex flex-wrap gap-2">
        {data.map((d) => {
          const cfg = STATUT_CONFIG[d.statut];
          const color = cfg ? (isDark ? cfg.darkColor : cfg.color) : DEFAULT_COLOR;
          const isHidden = hiddenStatuts.has(d.statut);
          return (
            <button
              key={d.statut}
              onClick={() => toggleStatut(d.statut)}
              aria-pressed={!isHidden}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-opacity ${
                isHidden ? "opacity-40" : "opacity-100"
              } border-transparent hover:border-gray-200 dark:hover:border-white/10`}
            >
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
              <span className="text-gray-700 dark:text-gray-300">
                {cfg?.label ?? d.statut} · {d.pct}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
