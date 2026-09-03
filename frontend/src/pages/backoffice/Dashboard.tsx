import { useState } from "react";
import {
  CheckCircle, Archive, Activity, Clock,
  ChevronDown, ChevronUp, UsersRound, RefreshCw,
  Timer, AlertTriangle, X, HelpCircle,
} from "lucide-react";
import { useAuth } from "../../lib/auth";
import { useDashboard, PERIODES, formatDuration } from "../../hooks/useDashboard";
import StatCard from "../../components/dashboard/StatCard";
import DonutChart from "../../components/dashboard/DonutChart";
import TicketsBarChart from "../../components/dashboard/TicketsBarChart";
import RecentDocs from "../../components/dashboard/RecentDocs";
import RecentTickets from "../../components/dashboard/RecentTickets";
import SatisfactionCard from "../../components/dashboard/SatisfactionCard";
import TicketsInsatisfaitsModal from "../../components/dashboard/TicketsInsatisfaitsModal";
import HorsDomaineCard from "../../components/dashboard/HorsDomaineCard";
import { QueueHero } from "../../components/dashboard/QueueHero";
import TeamStatsPanel from "./TeamStats";

function TabButton({ id, controls, active, onClick, children }: {
  id: string; controls: string; active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      id={id} onClick={onClick} role="tab"
      aria-selected={active} aria-controls={controls} tabIndex={active ? 0 : -1}
      className={`flex items-center gap-1.5 px-1 py-3 mr-6 text-sm font-medium border-b-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-1 ${
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
  const { isChef } = useAuth();
  const [showInsatisfaits, setShowInsatisfaits] = useState(false);

  const {
    onglet, periode, domaine, filterDomaine,
    refreshing, refreshError, lastUpdated, analyticsOpen, onboardingDismissed,
    stats, statsLoading, statsError,
    docsData, docsLoading, docsError,
    pendingLoading, pendingError,
    pendingCount, assignedCount, isDataStale, variationLabel,
    assignedColorClass, formatLastUpdated,
    handleRefresh, dismissOnboarding, showOnboarding, toggleAnalytics,
    setPeriode, setDomaine, setOnglet,
    queryClient, userDomaines,
  } = useDashboard();

  return (
    <div className="min-h-full flex flex-col">
      <a href="#queue-hero" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:bg-white dark:focus:bg-gray-900 focus:text-emerald-700 dark:focus:text-emerald-400 focus:rounded-lg focus:shadow-lg focus:text-sm focus:font-medium focus:ring-2 focus:ring-emerald-400">
        Aller à la file d'attente
      </a>

      {showInsatisfaits && (
        <TicketsInsatisfaitsModal onClose={() => setShowInsatisfaits(false)} periode={periode} domaine={filterDomaine} />
      )}

      {/* Header */}
      <div className="border-b border-gray-100 dark:border-white/8 px-6 py-5 shrink-0">
        <div className="max-w-screen-xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight text-gray-900 dark:text-gray-100">Tableau de bord</h1>
              <button onClick={showOnboarding} className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/8 transition-colors" aria-label="Revoir le guide de démarrage">
                <HelpCircle size={13} aria-hidden="true" /><span>Aide</span>
              </button>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 capitalize">
              {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {onglet === "overview" && userDomaines.length > 1 && (
              <div className="relative">
                <label htmlFor="domaine-select" className="sr-only">Filtrer par domaine</label>
                <select id="domaine-select" value={domaine} onChange={(e) => setDomaine(e.target.value)} aria-label="Domaine" className="appearance-none pl-3 pr-8 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400/60 cursor-pointer">
                  <option value="">Tous les domaines</option>
                  {userDomaines.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
                <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              </div>
            )}

            <div
              role="radiogroup" aria-label="Période d'analyse"
              className="flex items-center bg-gray-100 dark:bg-white/8 rounded-lg p-0.5 gap-0.5"
              onKeyDown={(e) => {
                const idx = PERIODES.findIndex((p) => p.value === periode);
                if (e.key === "ArrowRight") setPeriode(PERIODES[(idx + 1) % PERIODES.length].value);
                else if (e.key === "ArrowLeft") setPeriode(PERIODES[(idx - 1 + PERIODES.length) % PERIODES.length].value);
              }}
            >
              {PERIODES.map((p) => (
                <button key={p.value} role="radio" aria-checked={periode === p.value} tabIndex={periode === p.value ? 0 : -1}
                  onClick={() => setPeriode(p.value)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-1 ${
                    periode === p.value ? "bg-white dark:bg-white/15 text-gray-900 dark:text-gray-100 shadow-sm" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              {refreshError && !refreshing && <span role="alert" className="text-xs text-red-500 dark:text-red-400">Échec du rafraîchissement</span>}
              {lastUpdated && !refreshing && !refreshError && (
                <span role="status" aria-live="polite" className={`text-xs ${isDataStale ? "text-amber-500 dark:text-amber-400" : "text-gray-500 dark:text-gray-400"}`}>
                  {isDataStale && <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 mr-1 align-middle animate-pulse" aria-hidden="true" />}
                  Mis à jour {formatLastUpdated(lastUpdated)}
                </span>
              )}
              <button onClick={handleRefresh} disabled={refreshing} className="p-1.5 rounded-lg border border-gray-200 dark:border-white/12 bg-white dark:bg-white/6 text-gray-500 dark:text-gray-400 hover:text-emerald-500 dark:hover:text-emerald-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed" aria-label="Rafraîchir les données" title="Rafraîchir">
                <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Tab bar (chef uniquement) */}
      {isChef && (
        <div className="border-b border-gray-100 dark:border-white/8 px-6 shrink-0">
          <div className="max-w-screen-xl mx-auto flex" role="tablist" aria-label="Vues du tableau de bord" aria-orientation="horizontal"
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" && onglet === "overview") setOnglet("equipe");
              else if (e.key === "ArrowLeft" && onglet === "equipe") setOnglet("overview");
            }}
          >
            <TabButton id="tab-overview" controls="tabpanel-overview" active={onglet === "overview"} onClick={() => setOnglet("overview")}>Vue d'ensemble</TabButton>
            <TabButton id="tab-equipe" controls="tabpanel-equipe" active={onglet === "equipe"} onClick={() => setOnglet("equipe")}>
              <UsersRound size={13} />Mon équipe
            </TabButton>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="max-w-screen-xl mx-auto w-full px-6 py-6 space-y-5 flex-1">
        {onglet === "overview" && (
          <div id="tabpanel-overview" role="tabpanel" aria-labelledby="tab-overview" className="space-y-5">

            {/* Onboarding */}
            {!onboardingDismissed && (
              <div role="note" className="glass-card rounded-2xl px-5 py-4 flex items-start gap-4 border border-emerald-200 dark:border-emerald-500/20">
                <div className="flex-1 space-y-1">
                  <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Bienvenue dans votre tableau de bord</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                    La <strong className="font-medium text-gray-700 dark:text-gray-300">file d'attente</strong> liste les tickets auxquels l'IA a répondu et qui attendent votre avis.
                    Les tickets <strong className="font-medium">Hors Domaine</strong> et les <strong className="font-medium">Suggestions</strong> nécessitent votre validation.
                    Les tickets <strong className="font-medium">Auto</strong> (canoniques) sont déjà validés — aucune action requise.
                  </p>
                </div>
                <button onClick={dismissOnboarding} className="shrink-0 p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/8 transition-colors" aria-label="Fermer le message d'accueil">
                  <X size={14} />
                </button>
              </div>
            )}

            <QueueHero
              pendingCount={pendingCount}
              assignedCount={assignedCount}
              pendingLoading={pendingLoading}
              pendingError={pendingError}
              filterDomaine={filterDomaine}
              assignedColorClass={assignedColorClass}
              onRetry={() => queryClient.refetchQueries({ queryKey: ["dashboard-pending", filterDomaine] })}
            />

            {/* KPI cards */}
            {statsError ? (
              <div className="glass-card rounded-2xl p-5 flex items-center gap-3">
                <AlertTriangle size={16} className="text-red-500 shrink-0" />
                <p className="text-sm text-gray-600 dark:text-gray-400 flex-1">Impossible de charger les statistiques. Réessayez dans quelques instants.</p>
                <button onClick={() => queryClient.refetchQueries({ queryKey: ["dashboard-stats", filterDomaine, periode] })} className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline shrink-0">Réessayer</button>
              </div>
            ) : (
              <div className="space-y-2">
                <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider px-0.5">
                  Indicateurs · {PERIODES.find((p) => p.value === periode)?.label}
                </h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
                  <StatCard title="En cours" value={stats?.stats_cartes.en_cours.valeur ?? 0} variation={stats?.stats_cartes.en_cours.variation ?? 0} hausse={stats?.stats_cartes.en_cours.hausse ?? true} icon={Activity} iconColor="text-amber-500" iconBg="bg-amber-50 dark:bg-amber-500/10" loading={statsLoading} subtitle="tickets ouverts sur la période" variationLabel={variationLabel} featured />
                  <StatCard title="Réponses auto" value={stats?.stats_cartes.repondu_canonique.valeur ?? 0} variation={stats?.stats_cartes.repondu_canonique.variation ?? 0} hausse={stats?.stats_cartes.repondu_canonique.hausse ?? true} icon={CheckCircle} iconColor="text-emerald-500" loading={statsLoading} suffix="%" subtitle={`${stats?.stats_cartes.repondu_canonique.count ?? 0} tickets sans validation humaine`} variationUnit=" pts" variationLabel={variationLabel} />
                  <StatCard title="Clôturés" value={stats?.stats_cartes.tickets_clotures.valeur ?? 0} variation={stats?.stats_cartes.tickets_clotures.variation ?? 0} hausse={stats?.stats_cartes.tickets_clotures.hausse ?? true} icon={Archive} iconColor="text-violet-500" loading={statsLoading} subtitle="validés sur la période" variationLabel={variationLabel} />
                  <StatCard title="Délai 1ère réponse" value={stats?.stats_cartes.temps_premiere_reponse.valeur ?? 0} variation={stats?.stats_cartes.temps_premiere_reponse.variation ?? 0} hausse={stats?.stats_cartes.temps_premiere_reponse.hausse ?? true} icon={Clock} iconColor="text-orange-500" formatter={formatDuration} loading={statsLoading} positiveIsUp={false} subtitle="dépôt ticket → 1ère réponse humaine" variationLabel={variationLabel} />
                  <StatCard title="Délai clôture" value={stats?.stats_cartes.temps_cloture.valeur ?? 0} variation={stats?.stats_cartes.temps_cloture.variation ?? 0} hausse={stats?.stats_cartes.temps_cloture.hausse ?? true} icon={Timer} iconColor="text-rose-500" formatter={formatDuration} loading={statsLoading} positiveIsUp={false} subtitle="dépôt ticket → clotûre" variationLabel={variationLabel} />
                </div>
                <HorsDomaineCard
                  count={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.count ?? 0}
                  pct={stats?.repartition_branches.find((b) => b.branche === "HORS_DOMAINE")?.pct ?? 0}
                  loading={statsLoading}
                />
              </div>
            )}

            {/* Analytics toggle */}
            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-gray-100 dark:bg-white/8" />
              <button type="button" aria-expanded={analyticsOpen} aria-controls="analytics-section" onClick={toggleAnalytics} className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-white/8 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-white/14 hover:text-gray-700 dark:hover:text-gray-300 transition-colors shrink-0">
                {(docsError || statsError) && !analyticsOpen && <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-red-500" aria-label="Erreur dans les analytiques" />}
                {analyticsOpen ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
                {analyticsOpen ? "Masquer les analytiques" : "Afficher les analytiques"}
              </button>
              <div className="flex-1 h-px bg-gray-100 dark:bg-white/8" />
            </div>

            <div id="analytics-section" className="space-y-4" hidden={!analyticsOpen}>
              <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider px-0.5">Tendances</h2>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2">
                  <TicketsBarChart nouveaux={stats?.tickets_par_jour ?? []} traitement={stats?.traitement_par_jour ?? []} loading={statsLoading} periode={periode} />
                </div>
                <div className="flex flex-col gap-4">
                  <DonutChart data={stats?.repartition_statuts ?? []} loading={statsLoading} periode={periode} />
                  <SatisfactionCard data={stats?.satisfaction ?? null} loading={statsLoading} onVoirInsatisfaits={() => setShowInsatisfaits(true)} />
                </div>
              </div>
              <h2 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider px-0.5">Activité récente</h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <RecentTickets tickets={stats?.derniers_tickets ?? []} loading={statsLoading} />
                <RecentDocs docs={docsData?.items ?? []} loading={docsLoading} error={docsError} onRetry={() => queryClient.refetchQueries({ queryKey: ["dashboard-docs", filterDomaine] })} />
              </div>
            </div>
          </div>
        )}

        {onglet === "equipe" && isChef && (
          <div id="tabpanel-equipe" role="tabpanel" aria-labelledby="tab-equipe">
            <TeamStatsPanel periode={periode} />
          </div>
        )}
      </div>
    </div>
  );
}
