import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle,
  Archive,
  Activity,
  Clock,
  ChevronDown,
  ChevronUp,
  UsersRound,
  RefreshCw,
  Timer,
  AlertTriangle,
  ClipboardList,
  CheckCircle2,
} from "lucide-react";
import { useAuth } from "../../lib/auth";
import { getDashboardStats, listDocuments, getTickets } from "../../lib/api";
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
      role="tab"
      aria-selected={active}
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
  const [refreshing, setRefreshing] = useState(false);
  const [showInsatisfaits, setShowInsatisfaits] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [analyticsOpen, setAnalyticsOpen] = useState(() => localStorage.getItem("dashboard-analytics") !== "0");
  const [searchParams, setSearchParams] = useSearchParams();

  const onglet = (searchParams.get("onglet") as Onglet) || "overview";
  const periode = (searchParams.get("periode") as Periode) || "semaine";
  const domaine = searchParams.get("domaine") ?? (userDomaines.length === 1 ? userDomaines[0] : "");
  const filterDomaine = domaine || undefined;

  const { data: stats, isLoading: statsLoading, isError: statsError, dataUpdatedAt: statsUpdatedAt } = useQuery({
    queryKey: ["dashboard-stats", filterDomaine, periode],
    queryFn: () => getDashboardStats(filterDomaine, periode),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: onglet === "overview",
  });

  useEffect(() => {
    if (statsUpdatedAt > 0) setLastUpdated(new Date(statsUpdatedAt));
  }, [statsUpdatedAt]);

  const { data: docsData, isLoading: docsLoading, isError: docsError } = useQuery({
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

  const { data: pendingData, isLoading: pendingLoading, isError: pendingError } = useQuery({
    queryKey: ["dashboard-pending", filterDomaine],
    queryFn: () =>
      getTickets({
        statut: "RÉPONDU",
        limit: 100,
        domaines: filterDomaine
          ? [filterDomaine]
          : userDomaines.length > 0
            ? userDomaines
            : undefined,
      }),
    staleTime: 30_000,
    enabled: onglet === "overview",
  });

  const pendingCount = pendingData?.total ?? 0;
  const pendingBranchSummary = (() => {
    const items = pendingData?.items as Array<{ branche?: string | null }> | undefined;
    if (!items?.length) return null;
    const rag = items.filter((t) => t.branche === "LLM").length;
    const sugg = items.filter((t) => t.branche === "SUGGESTION").length;
    const auto = items.filter((t) => t.branche === "CANONIQUE").length;
    const parts: string[] = [];
    if (rag > 0) parts.push(`${rag} RAG`);
    if (sugg > 0) parts.push(`${sugg} Sugg.`);
    if (auto > 0) parts.push(`${auto} Auto`);
    return parts.length > 0 ? parts.join(" · ") : null;
  })();
  const isDataStale = lastUpdated != null && Date.now() - lastUpdated.getTime() > 2 * 60_000;

  async function handleRefresh() {
    setRefreshing(true);
    await Promise.all([
      queryClient.refetchQueries({ queryKey: ["dashboard-stats", filterDomaine, periode] }),
      queryClient.refetchQueries({ queryKey: ["dashboard-docs", filterDomaine] }),
      queryClient.refetchQueries({ queryKey: ["dashboard-pending", filterDomaine] }),
    ]);
    setRefreshing(false);
    setLastUpdated(new Date());
  }

  function formatLastUpdated(d: Date): string {
    const mins = Math.floor((Date.now() - d.getTime()) / 60_000);
    if (mins < 1) return "à l'instant";
    if (mins === 1) return "il y a 1 min";
    return `il y a ${mins} min`;
  }

  return (
    <div className="min-h-full flex flex-col">
      {showInsatisfaits && (
        <TicketsInsatisfaitsModal
          onClose={() => setShowInsatisfaits(false)}
          periode={periode}
          domaine={filterDomaine}
        />
      )}

      {/* ── En-tête ──────────────────────────────────────────────────── */}
      <div className="border-b border-gray-100 dark:border-white/8 px-6 py-5 shrink-0">
        <div className="max-w-screen-xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">
              Tableau de bord
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
                  onChange={(e) => {
                    const d = e.target.value;
                    setSearchParams((prev) => {
                      const next = new URLSearchParams(prev);
                      if (d) next.set("domaine", d); else next.delete("domaine");
                      return next;
                    }, { replace: true });
                  }}
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
            <div role="radiogroup" aria-label="Période d'analyse" className="flex items-center bg-gray-100 dark:bg-white/8 rounded-lg p-0.5 gap-0.5">
              {PERIODES.map((p) => (
                <button
                  key={p.value}
                  role="radio"
                  aria-checked={periode === p.value}
                  onClick={() => setSearchParams((prev) => {
                    const next = new URLSearchParams(prev);
                    next.set("periode", p.value);
                    return next;
                  }, { replace: true })}
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

            {/* Rafraîchir + timestamp */}
            <div className="flex items-center gap-2">
              {lastUpdated && !refreshing && (
                <span
                  role="status"
                  aria-live="polite"
                  className={`text-xs hidden sm:inline ${isDataStale ? "text-amber-500 dark:text-amber-400" : "text-gray-400 dark:text-gray-500"}`}
                >
                  {isDataStale && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 mr-1 align-middle animate-pulse" aria-hidden="true" />}
                  Mis à jour {formatLastUpdated(lastUpdated)}
                </span>
              )}
              <button
                onClick={handleRefresh}
                disabled={refreshing}
                className="p-1.5 rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="Rafraîchir les données"
                title="Rafraîchir"
              >
                <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Tabs (chef seulement) ────────────────────────────────────── */}
      {isChef && (
        <div className="border-b border-gray-100 dark:border-white/8 px-6 shrink-0">
          <div className="max-w-screen-xl mx-auto flex" role="tablist">
            <TabButton active={onglet === "overview"} onClick={() => setSearchParams((prev) => { const next = new URLSearchParams(prev); next.delete("onglet"); return next; }, { replace: true })}>
              Vue d'ensemble
            </TabButton>
            <TabButton active={onglet === "equipe"} onClick={() => setSearchParams((prev) => { const next = new URLSearchParams(prev); next.set("onglet", "equipe"); return next; }, { replace: true })}>
              <UsersRound size={13} />
              Mon équipe
            </TabButton>
          </div>
        </div>
      )}

      {/* ── Contenu ──────────────────────────────────────────────────── */}
      <div className="max-w-screen-xl mx-auto w-full px-6 py-6 space-y-5 flex-1">
        {onglet === "overview" && (
          <div role="tabpanel" aria-label="Vue d'ensemble" className="contents">
            {/* ── Hero file d'attente ───────────────────────────────────── */}
            {pendingLoading ? (
              <div className="glass-card rounded-2xl px-6 py-5 animate-pulse flex items-center gap-6">
                <div className="h-10 w-14 bg-gray-200 dark:bg-white/10 rounded" />
                <div className="space-y-2 flex-1">
                  <div className="h-4 w-52 bg-gray-200 dark:bg-white/10 rounded" />
                  <div className="h-3 w-32 bg-gray-200 dark:bg-white/10 rounded" />
                </div>
                <div className="h-9 w-48 bg-gray-200 dark:bg-white/10 rounded-lg ml-auto" />
              </div>
            ) : pendingError ? (
              <div className="glass-card rounded-2xl px-6 py-4 flex items-center gap-3 border border-red-200 dark:border-red-500/20">
                <AlertTriangle size={16} className="text-red-500 shrink-0" />
                <p className="text-sm text-gray-600 dark:text-gray-400 flex-1">
                  Impossible de charger la file d'attente.
                </p>
                <button
                  onClick={() => queryClient.refetchQueries({ queryKey: ["dashboard-pending", filterDomaine] })}
                  className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline shrink-0"
                >
                  Réessayer
                </button>
              </div>
            ) : pendingCount === 0 ? (
              <div className="glass-card rounded-2xl px-6 py-3.5 flex items-center gap-3 ring-1 ring-emerald-300/50 dark:ring-emerald-500/25">
                <CheckCircle2 size={15} className="text-emerald-500 dark:text-emerald-400 shrink-0" />
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  File vide —{" "}
                  <span className="font-medium text-emerald-600 dark:text-emerald-400">
                    aucun ticket en attente
                  </span>{" "}
                  de validation.
                </span>
              </div>
            ) : (
              <Link
                to="/tickets"
                state={{ filter: "en_attente", domaine: filterDomaine ?? "tous" }}
                className="glass-card rounded-2xl px-6 py-5 flex items-center gap-5 ring-1 ring-amber-300/50 dark:ring-amber-500/25 hover:shadow-md transition-shadow group"
              >
                <div className="flex items-baseline gap-3 shrink-0">
                  <span className="text-5xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100 leading-none">
                    {pendingCount}
                  </span>
                  <div>
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300 leading-tight">
                      tickets en attente de validation
                    </p>
                    {pendingBranchSummary && (
                      <div className="mt-0.5">
                        <p className="text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">
                          {pendingBranchSummary}
                        </p>
                        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                          RAG = généré par IA · Sugg. = à vérifier · Auto = validé sans relecture
                        </p>
                      </div>
                    )}
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-2 shrink-0">
                  <span className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 group-hover:bg-emerald-700 text-white text-sm font-medium transition-colors">
                    <ClipboardList size={14} />
                    Commencer la validation
                  </span>
                </div>
              </Link>
            )}

            {/* ── KPI analytiques — 5 cartes ou erreur ─────────────────── */}
            {statsError ? (
              <div className="glass-card rounded-2xl p-5 flex items-center gap-3">
                <AlertTriangle size={16} className="text-red-500 shrink-0" />
                <p className="text-sm text-gray-600 dark:text-gray-400 flex-1">
                  Impossible de charger les statistiques. Vérifiez la connexion au serveur.
                </p>
                <button
                  onClick={() => queryClient.refetchQueries({ queryKey: ["dashboard-stats", filterDomaine, periode] })}
                  className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline shrink-0"
                >
                  Réessayer
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider px-0.5">
                  Indicateurs · {PERIODES.find((p) => p.value === periode)?.label}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
                  <StatCard
                    title="En cours"
                    value={stats?.stats_cartes.en_cours.valeur ?? 0}
                    variation={stats?.stats_cartes.en_cours.variation ?? 0}
                    hausse={stats?.stats_cartes.en_cours.hausse ?? true}
                    icon={Activity}
                    iconColor="text-amber-500"
                    iconBg="bg-amber-50 dark:bg-amber-500/10"
                    loading={statsLoading}
                    featured
                  />
                  <StatCard
                    title="Réponses auto"
                    value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
                    variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
                    hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
                    icon={CheckCircle}
                    iconColor="text-emerald-500"
                    loading={statsLoading}
                    suffix="%"
                    subtitle={`${stats?.stats_cartes.repondu_canonique.count ?? 0} sans relecture humaine`}
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
                    positiveIsUp={false}
                    subtitle="dépôt ticket → 1ère réponse IA"
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
                    positiveIsUp={false}
                    subtitle="dépôt ticket → validation finale"
                  />
                </div>
                <HorsDomaineCard
                  count={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.count ?? 0}
                  pct={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.pct ?? 0}
                  loading={statsLoading}
                />
              </div>
            )}

            {/* Séparateur zones action / analytique */}
            <button
              type="button"
              aria-expanded={analyticsOpen}
              onClick={() => {
                const next = !analyticsOpen;
                setAnalyticsOpen(next);
                localStorage.setItem("dashboard-analytics", next ? "1" : "0");
              }}
              className="flex items-center gap-3 w-full group"
            >
              <div className="flex-1 h-px bg-gray-100 dark:bg-white/8 group-hover:bg-gray-200 dark:group-hover:bg-white/12 transition-colors" />
              <span className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 shrink-0 group-hover:text-gray-700 dark:group-hover:text-gray-300 transition-colors px-1">
                {analyticsOpen ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                {analyticsOpen ? "Masquer les analytiques" : "Afficher les analytiques"}
              </span>
              <div className="flex-1 h-px bg-gray-100 dark:bg-white/8 group-hover:bg-gray-200 dark:group-hover:bg-white/12 transition-colors" />
            </button>

            {analyticsOpen && (
              <div id="analytics-section" className="space-y-4">
                {/* Tendances */}
                <p className="text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider px-0.5">
                  Tendances
                </p>
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

                {/* Activité récente */}
                <p className="text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider px-0.5">
                  Activité récente
                </p>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <RecentTickets tickets={stats?.derniers_tickets ?? []} loading={statsLoading} />
                  <RecentDocs
                    docs={docsData?.items ?? []}
                    loading={docsLoading}
                    error={docsError}
                    onRetry={() => queryClient.refetchQueries({ queryKey: ["dashboard-docs", filterDomaine] })}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {onglet === "equipe" && isChef && <TeamStatsPanel periode={periode} />}
      </div>
    </div>
  );
}
