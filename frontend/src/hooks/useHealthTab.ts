import { useQuery } from "@tanstack/react-query";
import { getAlbertQuotas, getServicesHealth } from "../lib/api";

export function useHealthTab() {
  const { data: health, isLoading, isFetching, isError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["admin-health"],
    queryFn: getServicesHealth,
    retry: 1,
    staleTime: 0,
    refetchOnWindowFocus: false,
    refetchInterval: 30_000,
  });

  const { data: quotas, isFetching: isQuotaFetching, refetch: refetchQuotas } = useQuery({
    queryKey: ["admin-albert-quotas"],
    queryFn: getAlbertQuotas,
    retry: 1,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    refetchInterval: 5 * 60_000,
  });

  const stats = health?.stats;

  const derniereActivite = stats?.derniere_activite
    ? new Date(stats.derniere_activite).toLocaleString("fr-FR", {
        day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      })
    : null;

  const lastUpdated = dataUpdatedAt > 0
    ? new Date(dataUpdatedAt).toLocaleTimeString("fr-FR", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      })
    : null;

  const hasAlert =
    (stats?.tickets_echoues ?? 0) > 0 ||
    (stats?.tickets_bloques ?? 0) > 0 ||
    (stats?.documents_echoues ?? 0) > 0;

  return {
    health, isLoading, isFetching, isError, refetch,
    quotas, isQuotaFetching, refetchQuotas,
    stats, derniereActivite, lastUpdated, hasAlert,
  };
}
