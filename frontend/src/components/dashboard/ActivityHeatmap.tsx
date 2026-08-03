import { useState } from "react";

interface DayData {
  date: string;
  count: number;
}

interface ActivityHeatmapProps {
  data: DayData[];
  loading?: boolean;
}

function getCellColor(count: number): string {
  if (count === 0) return "bg-gray-100 dark:bg-white/5";
  if (count <= 2) return "bg-emerald-200 dark:bg-emerald-900/60";
  if (count <= 5) return "bg-emerald-400 dark:bg-emerald-600";
  return "bg-emerald-600 dark:bg-emerald-400";
}

const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"];
const DAYS = ["", "L", "", "M", "", "V", ""];

export default function ActivityHeatmap({ data, loading = false }: ActivityHeatmapProps) {
  const [tooltip, setTooltip] = useState<{ date: string; count: number; x: number; y: number } | null>(null);

  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse">
        <div className="h-5 bg-gray-200 dark:bg-white/10 rounded w-1/3 mb-4" />
        <div className="h-24 bg-gray-200 dark:bg-white/10 rounded" />
      </div>
    );
  }

  // Build 53 weeks × 7 days grid (last 365 days)
  // data is ordered from oldest to newest
  const CELL = 14;
  const GAP = 2;
  const STEP = CELL + GAP;
  const LEFT_PAD = 24;
  const TOP_PAD = 28;

  // Group data by week
  const weeks: DayData[][] = [];
  let week: DayData[] = [];

  // Pad start so first day aligns to its weekday
  const firstDate = data[0] ? new Date(data[0].date) : new Date();
  const firstDow = firstDate.getDay() === 0 ? 6 : firstDate.getDay() - 1; // Mon=0
  for (let i = 0; i < firstDow; i++) {
    week.push({ date: "", count: -1 });
  }

  for (const d of data) {
    week.push(d);
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  }
  if (week.length > 0) {
    while (week.length < 7) week.push({ date: "", count: -1 });
    weeks.push(week);
  }

  const svgW = LEFT_PAD + weeks.length * STEP;
  const svgH = TOP_PAD + 7 * STEP;

  // Month labels
  const monthLabels: { label: string; col: number }[] = [];
  let lastMonth = -1;
  weeks.forEach((w, wi) => {
    const firstReal = w.find((d) => d.date);
    if (firstReal) {
      const m = new Date(firstReal.date).getMonth();
      if (m !== lastMonth) {
        monthLabels.push({ label: MONTHS[m], col: wi });
        lastMonth = m;
      }
    }
  });

  const totalTickets = data.reduce((s, d) => s + d.count, 0);

  return (
    <div className="glass-card p-5 rounded-2xl space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Activité de traitement — 365 derniers jours
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {totalTickets.toLocaleString("fr-FR")} réponses traitées
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="relative" style={{ width: svgW, height: svgH }}>
          {/* Month labels */}
          {monthLabels.map(({ label, col }) => (
            <span
              key={`${label}-${col}`}
              className="absolute text-[10px] text-gray-400 dark:text-gray-500"
              style={{ left: LEFT_PAD + col * STEP, top: 4 }}
            >
              {label}
            </span>
          ))}

          {/* Day labels */}
          {DAYS.map((d, i) => (
            d ? (
              <span
                key={i}
                className="absolute text-[10px] text-gray-400 dark:text-gray-500"
                style={{ left: 4, top: TOP_PAD + i * STEP + 1 }}
              >
                {d}
              </span>
            ) : null
          ))}

          {/* Cells */}
          {weeks.map((week, wi) =>
            week.map((day, di) => {
              if (day.count === -1 || !day.date) return null;
              const x = LEFT_PAD + wi * STEP;
              const y = TOP_PAD + di * STEP;
              return (
                <div
                  key={`${wi}-${di}`}
                  className={`absolute rounded-sm cursor-pointer transition-transform hover:scale-110 ${getCellColor(day.count)}`}
                  style={{ left: x, top: y, width: CELL, height: CELL }}
                  onMouseEnter={() => {
                    setTooltip({ date: day.date, count: day.count, x: x + CELL / 2, y: y });
                  }}
                  onMouseLeave={() => setTooltip(null)}
                />
              );
            })
          )}

          {/* Tooltip */}
          {tooltip && (
            <div
              className="absolute z-10 pointer-events-none px-2.5 py-1.5 rounded-lg text-xs font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 shadow-lg whitespace-nowrap -translate-x-1/2 -translate-y-full -mt-1"
              style={{ left: tooltip.x, top: tooltip.y - 4 }}
            >
              {new Date(tooltip.date).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })}
              {" · "}
              <strong>{tooltip.count}</strong> réponse{tooltip.count > 1 ? "s" : ""} traitée{tooltip.count > 1 ? "s" : ""}
            </div>
          )}
        </div>
      </div>

      {/* Légende intensité */}
      <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
        <span>Moins</span>
        {["bg-gray-100 dark:bg-white/5", "bg-emerald-200 dark:bg-emerald-900/60", "bg-emerald-400 dark:bg-emerald-600", "bg-emerald-600 dark:bg-emerald-400"].map((cls, i) => (
          <span key={i} className={`w-3 h-3 rounded-sm ${cls}`} />
        ))}
        <span>Plus</span>
      </div>
    </div>
  );
}
