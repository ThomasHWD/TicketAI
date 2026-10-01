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
import TicketsInsatisfaitsModal from "../../components/dashboard/TicketsInsatisfaitsModal";

function formatDuration(seconds: number): string {
  if (seconds === 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}j`);
  if (h > 0) parts.push(`${h}h`);
  return parts.length > 0 ? parts.join(" ") : "< 1 h";
}

type Periode = "semaine" | "mois" | "annee";

const PERIODES: { value: Periode; label: string }[] = [
  { value: "semaine", label: "Semaine" },
  { value: "mois", label: "Mois" },
  { value: "annee", label: "Année" },
];

export default function AdminDashboard() {
  const queryClient = useQueryClient();
  const [periode, setPeriode] = useState<Periode>("semaine");
  const [domaine, setDomaine] = useState<string>("");
  const [refreshing, setRefreshing] = useState(false);
  const [showInsatisfaits, setShowInsatisfaits] = useState(false);

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
    <div className="min-h-full flex flex-col">
      {showInsatisfaits && (
        <TicketsInsatisfaitsModal
          onClose={() => setShowInsatisfaits(false)}
          periode={periode}
          domaine={filterDomaine}
        />
      )}

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div className="border-b border-gray-100 dark:border-white/8 px-6 py-5 shrink-0">
        <div className="max-w-screen-xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
              Dashboard
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5 capitalize">
              {new Date().toLocaleDateString("fr-FR", {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Sélecteur domaine */}
            {(allDomaines?.length ?? 0) > 0 && (
              <div className="relative">
                <select
                  value={domaine}
                  onChange={(e) => setDomaine(e.target.value)}
                  aria-label="Domaine"
                  className="appearance-none pl-3 pr-8 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 cursor-pointer"
                >
                  <option value="">Tous les domaines</option>
                  {allDomaines?.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
                <ChevronDown
                  size={12}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle pointer-events-none"
                />
              </div>
            )}

            {/* Sélecteur de période */}
            <div className="flex items-center bg-gray-100 dark:bg-white/8 rounded-lg p-0.5 gap-0.5">
              {PERIODES.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPeriode(p.value)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    periode === p.value
                      ? "bg-white dark:bg-white/15 text-gray-900 dark:text-gray-100 shadow-sm"
                      : "text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            {/* Rafraîchir */}
            <button
              onClick={async () => {
                setRefreshing(true);
                await queryClient.invalidateQueries({ queryKey: ["admin-dashboard-stats"] });
                await queryClient.invalidateQueries({ queryKey: ["admin-health"] });
                setRefreshing(false);
              }}
              className="p-1.5 rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-muted-foreground hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
              title="Rafraîchir"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div className="max-w-screen-xl mx-auto w-full px-6 py-6 space-y-5 flex-1">

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

        {/* KPI — 6 cartes */}
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
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
            iconColor="text-amber-700 dark:text-amber-400"
            loading={statsLoading}
          />
          <StatCard
            title="Autonomie"
            value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
            variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
            hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
            icon={CheckCircle}
            iconColor="text-emerald-700 dark:text-emerald-400"
            loading={statsLoading}
            suffix="%"
            subtitle={`${stats?.stats_cartes.repondu_canonique.count ?? 0} réponses auto`}
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
          <StatCard
            title="Délai 1ère réponse"
            value={stats?.stats_cartes.temps_premiere_reponse.valeur ?? 0}
            variation={stats?.stats_cartes.temps_premiere_reponse.variation ?? 0}
            hausse={stats?.stats_cartes.temps_premiere_reponse.hausse ?? true}
            icon={Clock}
            iconColor="text-orange-500"
            formatter={formatDuration}
            loading={statsLoading}
          />
          <StatCard
            title="Délai clôture"
            value={stats?.stats_cartes.temps_cloture.valeur ?? 0}
            variation={stats?.stats_cartes.temps_cloture.variation ?? 0}
            hausse={stats?.stats_cartes.temps_cloture.hausse ?? true}
            icon={Timer}
            iconColor="text-rose-500"
            formatter={formatDuration}
            loading={statsLoading}
          />
        </div>

        {/* Section analytique : LineChart (2/3) + Satisfaction (1/3) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TicketsBarChart
              nouveaux={stats?.tickets_par_jour ?? []}
              traitement={stats?.traitement_par_jour ?? []}
              loading={statsLoading}
              periode={periode}
            />
          </div>
          <SatisfactionCard
            data={stats?.satisfaction ?? null}
            loading={statsLoading}
            onVoirInsatisfaits={() => setShowInsatisfaits(true)}
          />
        </div>

        {/* Répartitions : statuts + branches */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <DonutChart data={stats?.repartition_statuts ?? []} loading={statsLoading} periode={periode} />
          <BranchesDonut data={stats?.repartition_branches ?? []} loading={statsLoading} />
        </div>
      </div>
    </div>
  );
}
