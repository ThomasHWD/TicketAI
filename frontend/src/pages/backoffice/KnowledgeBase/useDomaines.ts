import { useAuth } from "../../../lib/auth";
import type { Domaine } from "../../../types";

export function useDomaines() {
  const { userDomaines, user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  return {
    isAdmin,
    visibles: userDomaines as Domaine[],
    inscriptibles: userDomaines as Domaine[],
  };
}
