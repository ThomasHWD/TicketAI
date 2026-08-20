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
import TicketsInsatisfaitsModal from "../../components/dashboard/TicketsInsatisfaitsModal";
import TeamStatsPanel from "./TeamStats";
import HorsDomaineCard from "../../components/dashboard/HorsDomaineCard";

function formatDuration(seconds: number): string {
  if (seconds === 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}min`);
  return parts.length > 0 ? parts.join(" ") : "< 1 min";
}

type Periode = "semaine" | "mois" | "annee";
type Onglet = "overview" | "equipe";

const PERIODES: { value: Periode; label: string }[] = [
  { value: "semaine", label: "Semaine" },
  { value: "mois", label: "Mois" },
  { value: "annee", label: "Année" },
];

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-1 py-3 mr-6 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-emerald-500 text-gray-900 dark:text-gray-100"
          : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-white/20"
      }`}
    >
      {children}
    </button>
  );
}

export default function Dashboard() {
  const { userDomaines, isChef } = useAuth();
  const queryClient = useQueryClient();
  const [onglet, setOnglet] = useState<Onglet>("overview");
  const [refreshing, setRefreshing] = useState(false);
  const [showInsatisfaits, setShowInsatisfaits] = useState(false);
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
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 capitalize">
              {new Date().toLocaleDateString("fr-FR", {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Sélecteur domaine (vue d'ensemble seulement, si plusieurs domaines) */}
            {onglet === "overview" && userDomaines.length > 1 && (
              <div className="relative">
                <select
                  value={domaine}
                  onChange={(e) => setDomaine(e.target.value)}
                  aria-label="Domaine"
                  className="appearance-none pl-3 pr-8 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 cursor-pointer"
                >
                  <option value="">Tous les domaines</option>
                  {userDomaines.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
                <ChevronDown
                  size={12}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
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
                      : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
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
                await queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
                await queryClient.invalidateQueries({ queryKey: ["dashboard-docs"] });
                setRefreshing(false);
              }}
              className="p-1.5 rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
              title="Rafraîchir"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Tabs (chef seulement) ────────────────────────────────────── */}
      {isChef && (
        <div className="border-b border-gray-100 dark:border-white/8 px-6 shrink-0">
          <div className="max-w-screen-xl mx-auto flex">
            <TabButton active={onglet === "overview"} onClick={() => setOnglet("overview")}>
              Vue d'ensemble
            </TabButton>
            <TabButton active={onglet === "equipe"} onClick={() => setOnglet("equipe")}>
              <UsersRound size={13} />
              Mon équipe
            </TabButton>
          </div>
        </div>
      )}

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div className="max-w-screen-xl mx-auto w-full px-6 py-6 space-y-5 flex-1">
        {onglet === "overview" && (
          <>
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
                iconColor="text-amber-500"
                loading={statsLoading}
              />
              <StatCard
                title="Autonomie"
                value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
                variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
                hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
                icon={CheckCircle}
                iconColor="text-emerald-500"
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

            {/* Section analytique : BarChart (2/3) + panel droit (1/3) */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="lg:col-span-2">
                <TicketsBarChart
                  nouveaux={stats?.tickets_par_jour ?? []}
                  traitement={stats?.traitement_par_jour ?? []}
                  loading={statsLoading}
                  periode={periode}
                />
              </div>

              <div className="flex flex-col gap-4">
                <DonutChart
                  data={stats?.repartition_statuts ?? []}
                  loading={statsLoading}
                  periode={periode}
                />
                <SatisfactionCard
                  data={stats?.satisfaction ?? null}
                  loading={statsLoading}
                  onVoirInsatisfaits={() => setShowInsatisfaits(true)}
                />
              </div>
            </div>

            {/* Sujets hors domaine */}
            <HorsDomaineCard
              count={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.count ?? 0}
              pct={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.pct ?? 0}
              loading={statsLoading}
            />

            {/* Flux récents */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RecentTickets tickets={stats?.derniers_tickets ?? []} loading={statsLoading} />
              <RecentDocs docs={docsData?.items ?? []} loading={docsLoading} />
            </div>
          </>
        )}

        {onglet === "equipe" && isChef && <TeamStatsPanel periode={periode} />}
      </div>
    </div>
  );
}
