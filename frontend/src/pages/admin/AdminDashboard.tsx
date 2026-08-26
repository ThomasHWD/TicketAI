import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import {
  CheckCircle,
  Archive,
  Clock,
  Lightbulb,
  ChevronDown,
  RefreshCw,
  Timer,
  AlertTriangle,
  Inbox,
  X,
} from "lucide-react";
import { getDashboardStats, getServicesHealth, apiFetch } from "../../lib/api";
import StatCard from "../../components/dashboard/StatCard";
import DonutChart from "../../components/dashboard/DonutChart";
import BranchesDonut from "../../components/dashboard/BranchesDonut";
import TicketsBarChart from "../../components/dashboard/TicketsBarChart";
import SatisfactionCard from "../../components/dashboard/SatisfactionCard";
import TicketsInsatisfaitsModal from "../../components/dashboard/TicketsInsatisfaitsModal";

function formatDuration(seconds: number): string {
  if (seconds === 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}min`);
  return parts.length > 0 ? parts.join(" ") : "< 1 min";
}

function formatAge(ms: number): string {
  if (!ms) return "";
  const s = Math.floor((Date.now() - ms) / 1000);
  if (s < 10) return "à l'instant";
  if (s < 60) return `il y a ${s}s`;
  const m = Math.floor(s / 60);
  return `il y a ${m} min`;
}

type Periode = "semaine" | "mois" | "annee";

const PERIODES: { value: Periode; label: string; key: string }[] = [
  { value: "semaine", label: "Semaine", key: "1" },
  { value: "mois", label: "Mois", key: "2" },
  { value: "annee", label: "Année", key: "3" },
];

const VARIATION_LABEL: Record<Periode, string> = {
  semaine: "vs sem. préc.",
  mois: "vs mois préc.",
  annee: "vs an préc.",
};

export default function AdminDashboard() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const VALID_PERIODES: Periode[] = ["semaine", "mois", "annee"];
  const rawPeriode = searchParams.get("periode");
  const periode: Periode = VALID_PERIODES.includes(rawPeriode as Periode) ? (rawPeriode as Periode) : "semaine";
  const domaine = searchParams.get("domaine") ?? "";
  const [refreshing, setRefreshing] = useState(false);
  const [showInsatisfaits, setShowInsatisfaits] = useState(false);
  const [incidentDismissed, setIncidentDismissed] = useState(false);

  const setPeriode = (p: Periode) =>
    setSearchParams((prev) => { prev.set("periode", p); return prev; }, { replace: true });
  const setDomaine = (d: string) =>
    setSearchParams((prev) => { if (d) prev.set("domaine", d); else prev.delete("domaine"); return prev; }, { replace: true });

  const { data: health, isError: healthError } = useQuery({
    queryKey: ["admin-health"],
    queryFn: getServicesHealth,
    staleTime: 120_000,
    refetchInterval: 120_000,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const totalIncidents =
    (health?.stats.tickets_echoues ?? 0) +
    (health?.stats.tickets_bloques ?? 0) +
    (health?.stats.documents_echoues ?? 0);

  const incidentDetail = [
    health?.stats.tickets_echoues
      ? `${health.stats.tickets_echoues} ticket${health.stats.tickets_echoues > 1 ? "s" : ""} échoué${health.stats.tickets_echoues > 1 ? "s" : ""}`
      : null,
    health?.stats.tickets_bloques
      ? `${health.stats.tickets_bloques} ticket${health.stats.tickets_bloques > 1 ? "s" : ""} bloqué${health.stats.tickets_bloques > 1 ? "s" : ""}`
      : null,
    health?.stats.documents_echoues
      ? `${health.stats.documents_echoues} document${health.stats.documents_echoues > 1 ? "s" : ""} échoué${health.stats.documents_echoues > 1 ? "s" : ""}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  // Reset incident dismiss when incident count changes (new or resolved incidents)
  useEffect(() => { setIncidentDismissed(false); }, [totalIncidents]);

  // Keyboard shortcuts: 1/2/3 for period switching
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "1") setPeriode("semaine");
      if (e.key === "2") setPeriode("mois");
      if (e.key === "3") setPeriode("annee");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ["admin-dashboard-stats", filterDomaine, periode],
    queryFn: () => getDashboardStats(filterDomaine, periode),
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
  });

  const variationLabel = VARIATION_LABEL[periode];

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
            <div className="flex items-center gap-2 mt-0.5">
              <p className="text-sm text-gray-500 dark:text-gray-400 capitalize">
                {new Date().toLocaleDateString("fr-FR", {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </p>
              {!statsLoading && dataUpdatedAt > 0 && (
                <span
                  aria-live="polite"
                  aria-atomic="true"
                  className="text-xs text-gray-400 dark:text-gray-500 tabular-nums"
                >
                  · mis à jour {formatAge(dataUpdatedAt)}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Sélecteur domaine */}
            {(allDomaines?.length ?? 0) > 0 && (
              <div className="flex items-center gap-1">
                <div className="relative">
                  <select
                    value={domaine}
                    onChange={(e) => setDomaine(e.target.value)}
                    aria-label="Filtrer par domaine"
                    className="appearance-none pl-3 pr-8 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 cursor-pointer"
                  >
                    <option value="">Tous les domaines</option>
                    {allDomaines?.map((d) => (
                      <option key={d} value={d}>{d}</option>
                    ))}
                  </select>
                  <ChevronDown
                    size={12}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
                    aria-hidden
                  />
                </div>
                {domaine && (
                  <button
                    onClick={() => setDomaine("")}
                    aria-label="Effacer le filtre domaine"
                    className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                  >
                    <X size={12} aria-hidden />
                  </button>
                )}
              </div>
            )}

            {/* Sélecteur de période */}
            <div
              className="flex items-center bg-gray-100 dark:bg-white/8 rounded-lg p-0.5 gap-0.5"
              role="group"
              aria-label="Période (raccourcis : 1 Semaine, 2 Mois, 3 Année)"
            >
              {PERIODES.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPeriode(p.value)}
                  aria-pressed={periode === p.value}
                  title={`${p.label} (touche ${p.key})`}
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
                await Promise.all([
                  queryClient.refetchQueries({ queryKey: ["admin-dashboard-stats"] }),
                  queryClient.refetchQueries({ queryKey: ["admin-health"] }),
                ]);
                setRefreshing(false);
              }}
              className="p-1.5 rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors"
              aria-label="Rafraîchir les données"
              title="Rafraîchir (Ctrl+R)"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} aria-hidden={true} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────── */}
      <div className="max-w-screen-xl mx-auto w-full px-6 py-6 space-y-5 flex-1">

        {/* Bannière incidents */}
        {totalIncidents > 0 && !incidentDismissed && (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 px-3.5 py-2.5 text-sm text-red-700 dark:text-red-300"
          >
            <AlertTriangle size={16} className="shrink-0" aria-hidden />
            <span className="flex-1">
              {incidentDetail} —{" "}
              <Link
                to="/admin/config"
                className="underline underline-offset-2 hover:opacity-75 font-medium"
              >
                Voir l'onglet Santé
              </Link>
            </span>
            <button
              onClick={() => setIncidentDismissed(true)}
              aria-label="Masquer cette alerte"
              className="p-0.5 hover:opacity-70 transition-opacity shrink-0"
            >
              <X size={13} aria-hidden />
            </button>
          </div>
        )}

        {/* Bannière erreur santé système */}
        {healthError && !incidentDismissed && (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-700 dark:text-amber-300"
          >
            <AlertTriangle size={16} className="shrink-0" aria-hidden />
            <span className="flex-1">
              Impossible de vérifier l'état du système — les données de santé sont indisponibles.{" "}
              <Link
                to="/admin/config"
                className="underline underline-offset-2 hover:opacity-75 font-medium"
              >
                Voir l'onglet Santé
              </Link>
            </span>
            <button
              onClick={() => setIncidentDismissed(true)}
              aria-label="Masquer cette alerte"
              className="p-0.5 hover:opacity-70 transition-opacity shrink-0"
            >
              <X size={13} aria-hidden />
            </button>
          </div>
        )}

        {/* État d'erreur stats */}
        {statsError ? (
          <div className="flex flex-col items-center py-14 gap-3 text-gray-500 dark:text-gray-400">
            <AlertTriangle size={24} className="text-red-400" aria-hidden />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Impossible de charger les statistiques
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Vérifiez votre connexion réseau ou réessayez.
            </p>
            <button
              onClick={() => queryClient.refetchQueries({ queryKey: ["admin-dashboard-stats"] })}
              className="mt-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
            >
              Réessayer
            </button>
          </div>
        ) : (
          <>
            {/* KPI — 6 cartes */}
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
              <StatCard
                title="Nouveaux tickets"
                description="Tickets créés sur la période sélectionnée"
                value={stats?.stats_cartes.nouveaux.valeur ?? 0}
                variation={stats?.stats_cartes.nouveaux.variation ?? 0}
                hausse={stats?.stats_cartes.nouveaux.hausse ?? true}
                icon={Lightbulb}
                iconColor="text-blue-500"
                loading={statsLoading}
                variationLabel={variationLabel}
              />
              <StatCard
                title="En cours"
                description="Tickets actuellement en cours de traitement"
                value={stats?.stats_cartes.en_cours.valeur ?? 0}
                variation={stats?.stats_cartes.en_cours.variation ?? 0}
                hausse={stats?.stats_cartes.en_cours.hausse ?? true}
                icon={Inbox}
                iconColor="text-amber-500"
                loading={statsLoading}
                variationLabel={variationLabel}
              />
              <StatCard
                title="Autonomie"
                description="Tickets répondus automatiquement via réponse canonique, sans intervention humaine"
                value={stats?.stats_cartes.repondu_canonique.valeur ?? 0}
                variation={stats?.stats_cartes.repondu_canonique.variation ?? 0}
                hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true}
                icon={CheckCircle}
                iconColor="text-emerald-500"
                loading={statsLoading}
                suffix="%"
                subtitle={`${stats?.stats_cartes.repondu_canonique.count ?? 0} réponses auto`}
                variationUnit=" pts"
                variationLabel={variationLabel}
              />
              <StatCard
                title="Clôturés"
                description="Tickets clôturés sur la période sélectionnée"
                value={stats?.stats_cartes.tickets_clotures.valeur ?? 0}
                variation={stats?.stats_cartes.tickets_clotures.variation ?? 0}
                hausse={stats?.stats_cartes.tickets_clotures.hausse ?? true}
                icon={Archive}
                iconColor="text-violet-500"
                loading={statsLoading}
                variationLabel={variationLabel}
              />
              <StatCard
                title="Délai 1ère réponse"
                description="Délai médian entre la création du ticket et la première réponse envoyée"
                value={stats?.stats_cartes.temps_premiere_reponse.valeur ?? 0}
                variation={stats?.stats_cartes.temps_premiere_reponse.variation ?? 0}
                hausse={stats?.stats_cartes.temps_premiere_reponse.hausse ?? true}
                icon={Clock}
                iconColor="text-orange-500"
                formatter={formatDuration}
                loading={statsLoading}
                positiveIsUp={false}
                variationLabel={variationLabel}
              />
              <StatCard
                title="Délai clôture"
                description="Délai médian entre la création du ticket et sa clôture"
                value={stats?.stats_cartes.temps_cloture.valeur ?? 0}
                variation={stats?.stats_cartes.temps_cloture.variation ?? 0}
                hausse={stats?.stats_cartes.temps_cloture.hausse ?? true}
                icon={Timer}
                iconColor="text-rose-500"
                formatter={formatDuration}
                loading={statsLoading}
                positiveIsUp={false}
                variationLabel={variationLabel}
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
              <BranchesDonut data={stats?.repartition_branches ?? []} loading={statsLoading} periode={periode} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
