import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import type { Domaine } from "../../../types";

async function fetchDomaines(): Promise<Domaine[]> {
  const res = await apiFetch("/api/v1/admin/domaines");
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

/**
 * Les domaines visibles, et ceux sur lesquels on peut écrire.
 *
 * Un ADMIN voit tout le catalogue mais n'écrit que dans ses propres domaines :
 * la distinction est celle de `check_domain_write` côté API, et la confondre
 * ferait proposer des actions que le serveur refusera en 403.
 */
export function useDomaines() {
  const { userDomaines, user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const { data: adminDomaines = [] } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });

  return {
    isAdmin,
    /** Domaines listables. */
    visibles: (isAdmin ? adminDomaines : userDomaines) as Domaine[],
    /** Domaines où l'utilisateur peut créer, mettre à jour et supprimer. */
    inscriptibles: userDomaines as Domaine[],
  };
}
