import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  Archive,
  Clock,
  Lightbulb,
  ChevronDown,
  RefreshCw,
  Timer,
  AlertTriangle,
} from "lucide-react";
import { Link } from "react-router-dom";
import { getDashboardStats, getServicesHealth, apiFetch } from "../../lib/api";
import StatCard from "../../components/dashboard/StatCard";
import DonutChart from "../../components/dashboard/DonutChart";
import BranchesDonut from "../../components/dashboard/BranchesDonut";
import TicketsBarChart from "../../components/dashboard/TicketsBarChart";
import SatisfactionCard from "../../components/dashboard/SatisfactionCard";

function formatDuration(seconds: number): string {
  if (seconds === 0) return "0s";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}min`);
  if (s > 0 || parts.length === 0) parts.push(`${s}s`);
  return parts.join(" ");
}

type Periode = "semaine" | "mois" | "annee";

const PERIODES: { value: Periode; label: string }[] = [
  { value: "semaine", label: "Cette semaine" },
  { value: "mois", label: "Ce mois" },
  { value: "annee", label: "Cette année" },
];

export default function AdminDashboard() {
  const queryClient = useQueryClient();
  const [periode, setPeriode] = useState<Periode>("semaine");
  const [domaine, setDomaine] = useState<string>("");
  const [refreshing, setRefreshing] = useState(false);

  const { data: allDomaines } = useQuery({
    queryKey: ["admin-domaines"],
    queryFn: async () => {
      const res = await apiFetch("/api/v1/admin/domaines");
      if (!res.ok) return [] as string[];
      return res.json() as Promise<string[]>;
    },
    staleTime: 300_000,
    refetchOnWindowFocus: false,
  });

  const filterDomaine = domaine || undefined;

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["admin-dashboard-stats", filterDomaine, periode],
    queryFn: () => getDashboardStats(filterDomaine, periode),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const { data: health } = useQuery({
    queryKey: ["admin-health"],
    queryFn: getServicesHealth,
    staleTime: 120_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const totalIncidents =
    (health?.stats.tickets_echoues ?? 0) +
    (health?.stats.tickets_bloques ?? 0) +
    (health?.stats.documents_echoues ?? 0);

  return (
    <div className="p-6 space-y-6 max-w-screen-xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              setRefreshing(true);
              await queryClient.invalidateQueries({ queryKey: ["admin-dashboard-stats"] });
              await queryClient.invalidateQueries({ queryKey: ["admin-health"] });
              setRefreshing(false);
            }}
            className="p-2 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
            title="Rafraîchir"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Sélecteur domaine */}
          {(allDomaines?.length ?? 0) > 0 && (
            <div className="relative">
              <select
                value={domaine}
                onChange={(e) => setDomaine(e.target.value)}
                className="appearance-none pl-3 pr-8 py-2 text-sm rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400 cursor-pointer"
              >
                <option value="">Tous les domaines</option>
                {allDomaines?.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          )}

          {/* Sélecteur période */}
          <div className="flex rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 p-0.5">
            {PERIODES.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriode(p.value)}
                className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                  periode === p.value
                    ? "bg-emerald-500 text-white shadow-sm"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Bannière incidents */}
      {totalIncidents > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-700 dark:text-amber-300">
          <AlertTriangle size={14} className="shrink-0" />
          <span>
            {totalIncidents} incident{totalIncidents > 1 ? "s détectés" : " détecté"} —{" "}
            <Link
              to="/admin/config"
              className="underline underline-offset-2 hover:opacity-75 font-medium"
            >
              Voir l'onglet Santé
            </Link>
          </span>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Nouveaux tickets"
          value={stats?.stats_cartes.nouveaux.valeur ?? 0}
          variation={stats?.stats_cartes.nouveaux.variation ?? 0}
          hausse={stats?.stats_cartes.nouveaux.hausse ?? true}
          icon={Lightbulb}
          iconColor="text-blue-500"
          loading={statsLoading}
        />
        <StatCard
          title="En cours"
          value={stats?.stats_cartes.en_cours.valeur ?? 0}
          variation={stats?.stats_cartes.en_cours.variation ?? 0}
          hausse={stats?.stats_cartes.en_cours.hausse ?? true}
          icon={Clock}
          iconColor="text-amber-500"
          loading={statsLoading}
        />
        <StatCard
          title="Taux d'autonomie"
          value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
          variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
          hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
          icon={CheckCircle}
          iconColor="text-emerald-500"
          loading={statsLoading}
          suffix="%"
          subtitle={`${stats?.stats_cartes.repondu_canonique.count ?? 0} réponses automatiques`}
          variationUnit=" pts"
        />
        <StatCard
          title="Clôturés"
          value={stats?.stats_cartes.tickets_clotures.valeur ?? 0}
          variation={stats?.stats_cartes.tickets_clotures.variation ?? 0}
          hausse={stats?.stats_cartes.tickets_clotures.hausse ?? true}
          icon={Archive}
          iconColor="text-violet-500"
          loading={statsLoading}
        />
      </div>

      {/* Délais de traitement */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <StatCard
          title="Délai moyen avant 1ère réponse"
          value={stats?.stats_cartes.temps_premiere_reponse.valeur ?? 0}
          variation={stats?.stats_cartes.temps_premiere_reponse.variation ?? 0}
          hausse={stats?.stats_cartes.temps_premiere_reponse.hausse ?? true}
          icon={Clock}
          iconColor="text-orange-500"
          formatter={formatDuration}
          loading={statsLoading}
        />
        <StatCard
          title="Délai moyen avant clôture"
          value={stats?.stats_cartes.temps_cloture.valeur ?? 0}
          variation={stats?.stats_cartes.temps_cloture.variation ?? 0}
          hausse={stats?.stats_cartes.temps_cloture.hausse ?? true}
          icon={Timer}
          iconColor="text-rose-500"
          formatter={formatDuration}
          loading={statsLoading}
        />
      </div>

      {/* Donut statuts + Donut branches */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DonutChart data={stats?.repartition_statuts ?? []} loading={statsLoading} periode={periode} />
        <BranchesDonut data={stats?.repartition_branches ?? []} loading={statsLoading} />
      </div>

      {/* Bar chart */}
      <TicketsBarChart
        nouveaux={stats?.tickets_par_jour ?? []}
        traitement={stats?.traitement_par_jour ?? []}
        loading={statsLoading}
        periode={periode}
      />

      {/* Satisfaction */}
      <SatisfactionCard data={stats?.satisfaction ?? null} loading={statsLoading} />
    </div>
  );
}
