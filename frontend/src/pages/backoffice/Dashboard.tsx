import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  Archive,
  Clock,
  Lightbulb,
  ChevronDown,
  UsersRound,
  RefreshCw,
  Timer,
} from "lucide-react";
import { useAuth } from "../../lib/auth";
import { getDashboardStats, listDocuments } from "../../lib/api";
import StatCard from "../../components/dashboard/StatCard";
import DonutChart from "../../components/dashboard/DonutChart";
import TicketsBarChart from "../../components/dashboard/TicketsBarChart";
import RecentDocs from "../../components/dashboard/RecentDocs";
import RecentTickets from "../../components/dashboard/RecentTickets";
import SatisfactionCard from "../../components/dashboard/SatisfactionCard";
import TeamStatsPanel from "./TeamStats";

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
type Onglet = "overview" | "equipe";

const PERIODES: { value: Periode; label: string }[] = [
  { value: "semaine", label: "Cette semaine" },
  { value: "mois", label: "Ce mois" },
  { value: "annee", label: "Cette année" },
];

export default function Dashboard() {
  const { userDomaines, isChef } = useAuth();
  const queryClient = useQueryClient();
  const [onglet, setOnglet] = useState<Onglet>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const [periode, setPeriode] = useState<Periode>("semaine");
  const [domaine, setDomaine] = useState<string>(
    userDomaines.length === 1 ? userDomaines[0] : "",
  );

  const filterDomaine = domaine || undefined;

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats", filterDomaine, periode],
    queryFn: () => getDashboardStats(filterDomaine, periode),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: onglet === "overview",
  });

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: ["dashboard-docs", filterDomaine],
    queryFn: () =>
      listDocuments(
        undefined,
        filterDomaine ? [filterDomaine] : userDomaines.length > 0 ? userDomaines : undefined,
      ),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
    enabled: onglet === "overview",
  });

  return (
    <div className="p-6 space-y-6 max-w-screen-xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-2">
          {isChef && (
            <div className="flex items-center gap-1 p-1 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 w-fit">
              <button
                onClick={() => setOnglet("overview")}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                  onglet === "overview"
                    ? "bg-emerald-500 text-white shadow-sm"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
                }`}
              >
                Vue d'ensemble
              </button>
              <button
                onClick={() => setOnglet("equipe")}
                className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                  onglet === "equipe"
                    ? "bg-emerald-500 text-white shadow-sm"
                    : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
                }`}
              >
                <UsersRound size={14} />
                Mon équipe
              </button>
            </div>
          )}
          <button
            onClick={async () => {
              setRefreshing(true);
              await queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
              await queryClient.invalidateQueries({ queryKey: ["dashboard-docs"] });
              setRefreshing(false);
            }}
            className="p-2 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
            title="Rafraîchir"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Sélecteur domaine (uniquement sur vue d'ensemble, si plusieurs domaines) */}
          {onglet === "overview" && userDomaines.length > 1 && (
            <div className="relative">
              <select
                value={domaine}
                onChange={(e) => setDomaine(e.target.value)}
                className="appearance-none pl-3 pr-8 py-2 text-sm rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400 cursor-pointer"
              >
                <option value="">Tous mes domaines</option>
                {userDomaines.map((d) => (
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

      {onglet === "overview" && (
        <>
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
              title="Nombre de réponses canonique"
              value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
              variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
              hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
              icon={CheckCircle}
              iconColor="text-emerald-500"
              loading={statsLoading}
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

          {/* Délais de traitement — hors réponses canoniques */}
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

          {/* Donut + Docs */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <DonutChart data={stats?.repartition_statuts ?? []} loading={statsLoading} periode={periode} />
            <SatisfactionCard data={stats?.satisfaction ?? null} loading={statsLoading} />
          </div>

          {/* Bar chart */}
          <TicketsBarChart
            nouveaux={stats?.tickets_par_jour ?? []}
            traitement={stats?.traitement_par_jour ?? []}
            loading={statsLoading}
            periode={periode}
          />

          {/* Recent tickets + satisfaction */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <RecentTickets tickets={stats?.derniers_tickets ?? []} loading={statsLoading} />
            <RecentDocs docs={docsData?.items ?? []} loading={docsLoading} />
          </div>
        </>
      )}

      {onglet === "equipe" && isChef && (
        <TeamStatsPanel periode={periode} />
      )}
    </div>
  );
}
