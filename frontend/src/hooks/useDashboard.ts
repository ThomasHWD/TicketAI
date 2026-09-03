import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../lib/auth";
import { getDashboardStats, listDocuments, getTickets, getMyAssignedTickets } from "../lib/api";

export type Periode = "semaine" | "mois" | "annee";
export type Onglet = "overview" | "equipe";

export const PERIODES: { value: Periode; label: string }[] = [
  { value: "semaine", label: "Semaine" },
  { value: "mois",    label: "Mois" },
  { value: "annee",   label: "Année" },
];

export function formatDuration(seconds: number): string {
  if (seconds === 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}j`);
  if (h > 0) parts.push(`${h}h`);
  return parts.length > 0 ? parts.join(" ") : "< 1 h";
}

export function useDashboard() {
  const { userDomaines } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const [refreshing, setRefreshing]         = useState(false);
  const [refreshError, setRefreshError]     = useState(false);
  const [lastUpdated, setLastUpdated]       = useState<Date | null>(null);
  const [analyticsOpen, setAnalyticsOpen]   = useState(() => localStorage.getItem("dashboard-analytics") === "1");
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => localStorage.getItem("onboarding-dashboard") === "1");

  const onglet        = (searchParams.get("onglet") as Onglet)   || "overview";
  const periode       = (searchParams.get("periode") as Periode) || "semaine";
  const domaine       = searchParams.get("domaine") ?? (userDomaines.length === 1 ? userDomaines[0] : "");
  const filterDomaine = domaine || undefined;

  const { data: stats, isLoading: statsLoading, isError: statsError, dataUpdatedAt: statsUpdatedAt } = useQuery({
    queryKey: ["dashboard-stats", filterDomaine, periode],
    queryFn:  () => getDashboardStats(filterDomaine, periode),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: onglet === "overview",
  });

  const { data: docsData, isLoading: docsLoading, isError: docsError, dataUpdatedAt: docsUpdatedAt } = useQuery({
    queryKey: ["dashboard-docs", filterDomaine],
    queryFn:  () => listDocuments(undefined, filterDomaine ? [filterDomaine] : userDomaines.length > 0 ? userDomaines : undefined),
    staleTime: 120_000,
    refetchOnWindowFocus: false,
    enabled: onglet === "overview",
  });

  const { data: pendingData, isLoading: pendingLoading, isError: pendingError, dataUpdatedAt: pendingUpdatedAt } = useQuery({
    queryKey: ["dashboard-pending", filterDomaine],
    queryFn:  () => getTickets({
      statut: "RÉPONDU",
      exclure_canonique: true,
      limit: 100,
      domaines: filterDomaine ? [filterDomaine] : userDomaines.length > 0 ? userDomaines : undefined,
    }),
    staleTime: 30_000,
    enabled: onglet === "overview",
  });

  const { data: assignedData } = useQuery({
    queryKey: ["my-assigned-tickets"],
    queryFn:  getMyAssignedTickets,
    staleTime: 30_000,
    enabled: onglet === "overview",
  });

  useEffect(() => {
    const timestamps = [statsUpdatedAt, docsUpdatedAt, pendingUpdatedAt].filter((t) => t > 0);
    if (timestamps.length > 0) setLastUpdated(new Date(Math.max(...timestamps)));
  }, [statsUpdatedAt, docsUpdatedAt, pendingUpdatedAt]);

  const pendingCount  = pendingData?.total ?? 0;
  const assignedCount = assignedData?.length ?? 0;
  const isDataStale   = [statsUpdatedAt, docsUpdatedAt, pendingUpdatedAt].some((t) => t > 0 && Date.now() - t > 2 * 60_000);
  const variationLabel = { semaine: "vs sem. préc.", mois: "vs mois préc.", annee: "vs an préc." }[periode];

  function assignedColorClass(n: number): string {
    if (n === 0) return "text-gray-400 dark:text-gray-500";
    if (n <= 3)  return "text-emerald-600 dark:text-emerald-400";
    if (n <= 7)  return "text-amber-600 dark:text-amber-400";
    return "text-red-600 dark:text-red-400";
  }

  function formatLastUpdated(d: Date): string {
    const mins = Math.floor((Date.now() - d.getTime()) / 60_000);
    if (mins < 1) return "à l'instant";
    if (mins === 1) return "il y a 1 min";
    return `il y a ${mins} min`;
  }

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshError(false);
    await Promise.all([
      queryClient.refetchQueries({ queryKey: ["dashboard-stats", filterDomaine, periode] }),
      queryClient.refetchQueries({ queryKey: ["dashboard-docs", filterDomaine] }),
      queryClient.refetchQueries({ queryKey: ["dashboard-pending", filterDomaine] }),
      queryClient.refetchQueries({ queryKey: ["my-assigned-tickets"] }),
    ]);
    setRefreshing(false);
    const hadError =
      queryClient.getQueryState(["dashboard-stats", filterDomaine, periode])?.status === "error" ||
      queryClient.getQueryState(["dashboard-docs", filterDomaine])?.status === "error" ||
      queryClient.getQueryState(["dashboard-pending", filterDomaine])?.status === "error";
    if (hadError) setRefreshError(true);
    else setLastUpdated(new Date());
  }

  function dismissOnboarding() {
    setOnboardingDismissed(true);
    localStorage.setItem("onboarding-dashboard", "1");
  }

  function showOnboarding() {
    setOnboardingDismissed(false);
    localStorage.removeItem("onboarding-dashboard");
  }

  function toggleAnalytics() {
    const next = !analyticsOpen;
    setAnalyticsOpen(next);
    localStorage.setItem("dashboard-analytics", next ? "1" : "0");
  }

  function setPeriode(p: Periode) {
    setSearchParams((prev) => { const n = new URLSearchParams(prev); n.set("periode", p); return n; }, { replace: true });
  }

  function setDomaine(d: string) {
    setSearchParams((prev) => { const n = new URLSearchParams(prev); if (d) n.set("domaine", d); else n.delete("domaine"); return n; }, { replace: true });
  }

  function setOnglet(o: Onglet) {
    setSearchParams((prev) => { const n = new URLSearchParams(prev); if (o === "overview") n.delete("onglet"); else n.set("onglet", o); return n; }, { replace: true });
  }

  return {
    // URL-derived state
    onglet, periode, domaine, filterDomaine,
    // UI state
    refreshing, refreshError, lastUpdated, analyticsOpen, onboardingDismissed,
    // Queries
    stats, statsLoading, statsError,
    docsData, docsLoading, docsError,
    pendingLoading, pendingError,
    // Derived
    pendingCount, assignedCount, isDataStale, variationLabel,
    // Helpers
    assignedColorClass, formatLastUpdated,
    // Actions
    handleRefresh, dismissOnboarding, showOnboarding, toggleAnalytics,
    setPeriode, setDomaine, setOnglet,
    queryClient,
    // Pass-through
    userDomaines,
  };
}
