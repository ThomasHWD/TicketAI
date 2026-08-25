import { useAuth } from "../../../lib/auth";
import type { Domaine } from "../../../types";

export function useDomaines() {
  const { userDomaines, user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  return {
    isAdmin,
    /** Domaines listables — restreint aux groupes de l'utilisateur, admin compris. */
    visibles: userDomaines as Domaine[],
    /** Domaines où l'utilisateur peut créer, mettre à jour et supprimer. */
    inscriptibles: userDomaines as Domaine[],
  };
}
