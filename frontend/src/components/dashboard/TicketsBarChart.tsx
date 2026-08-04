import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

interface DayData {
  date: string;
  count: number;
}

type Periode = "semaine" | "mois" | "annee";

interface TicketsLineChartProps {
  nouveaux: DayData[];
  traitement: DayData[];
  loading?: boolean;
  periode?: Periode;
}

const MOIS_FR = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"];

function formatDate(dateStr: string, periode: Periode): string {
  const d = new Date(dateStr + "T00:00:00");
  if (periode === "annee") return MOIS_FR[d.getMonth()];
  if (periode === "semaine") return d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric" });
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

const TITRE: Record<Periode, string> = {
  semaine: "Activité — 7 derniers jours",
  mois: "Activité — 30 derniers jours",
  annee: "Activité — cette année",
};

export default function TicketsBarChart({ nouveaux, traitement, loading = false, periode = "mois" }: TicketsLineChartProps) {
  const isDark = document.documentElement.classList.contains("dark");

  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse">
        <div className="h-5 bg-gray-200 dark:bg-white/10 rounded w-1/3 mb-4" />
        <div className="h-44 bg-gray-200 dark:bg-white/10 rounded" />
      </div>
    );
  }

  // Fusionner les deux séries sur la même clé date
  const chartData = nouveaux.map((d, i) => ({
    label: formatDate(d.date, periode),
    nouveaux: d.count,
    traitement: traitement[i]?.count ?? 0,
  }));

  const xInterval = periode === "semaine" ? 0 : periode === "annee" ? 0 : 4;

  return (
    <div className="glass-card p-5 rounded-2xl space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
        {TITRE[periode]}
      </h3>
      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
              axisLine={false}
              tickLine={false}
              interval={xInterval}
            />
            <YAxis
              allowDecimals={false}
              tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                borderRadius: "10px",
                border: "none",
                boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
                background: isDark ? "#1e293b" : "#fff",
                color: isDark ? "#e2e8f0" : "#1e293b",
                fontSize: 12,
              }}
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              formatter={(value: any, name: any) => [
                value,
                name === "nouveaux" ? "Nouveaux tickets" : "Tickets en traitement",
              ]}
              labelStyle={{ fontWeight: 600, marginBottom: 4 }}
            />
            <Legend
              formatter={(value) =>
                value === "nouveaux" ? "Nouveaux tickets" : "Tickets en traitement"
              }
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            />
            <Line
              type="monotone"
              dataKey="nouveaux"
              stroke={isDark ? "#60a5fa" : "#3b82f6"}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
            <Line
              type="monotone"
              dataKey="traitement"
              stroke={isDark ? "#34d399" : "#10b981"}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
