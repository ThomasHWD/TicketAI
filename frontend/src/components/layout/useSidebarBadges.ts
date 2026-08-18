import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../lib/auth";
import { getIncidents, getReponsesARelire, getReponsesObsoletes } from "../../lib/api";

export function useSidebarBadges() {
  const { user, userDomaines } = useAuth();

  const { data: incidents } = useQuery({
    queryKey: ["admin-incidents"],
    queryFn: getIncidents,
    enabled: user?.role === "ADMIN",
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const hasIncidents =
    (incidents?.tickets_echoues.length ?? 0) +
    (incidents?.tickets_bloques.length ?? 0) +
    (incidents?.documents_echoues.length ?? 0) > 0;

  const { data: obsoletes } = useQuery({
    queryKey: ["reponses-obsoletes", "count"],
    queryFn: () => getReponsesObsoletes({ page: 1, limit: 1 }),
    enabled: userDomaines.length > 0,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const nbObsoletes = obsoletes?.total ?? 0;

  const { data: aRelire } = useQuery({
    queryKey: ["reponses-a-relire", "count"],
    queryFn: () => getReponsesARelire({ page: 1, limit: 1 }),
    enabled: userDomaines.length > 0,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const nbDocsARelire = aRelire?.nb_documents ?? 0;

  return {
    hasIncidents,
    badge: nbDocsARelire || nbObsoletes,
  };
}
