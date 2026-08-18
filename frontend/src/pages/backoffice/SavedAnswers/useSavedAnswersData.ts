import { useQuery } from "@tanstack/react-query";
import { getReponsesARelire, getReponsesCanoniques, getReponsesObsoletes } from "../../../lib/api";
import { LIMIT, type Onglet } from "./utils";

export function useSavedAnswersData(onglet: Onglet, page: number) {
  const canoniques = useQuery({
    queryKey: ["reponses-canoniques", page],
    queryFn: () => getReponsesCanoniques({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "canoniques",
  });

  const obsoletes = useQuery({
    queryKey: ["reponses-obsoletes", "liste", page],
    queryFn: () => getReponsesObsoletes({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "obsoletes",
  });

  const aRelire = useQuery({
    queryKey: ["reponses-a-relire", "liste", page],
    queryFn: () => getReponsesARelire({ page, limit: LIMIT }),
    placeholderData: (prev) => prev,
    enabled: onglet === "a_relire",
  });

  const { data: compteur } = useQuery({
    queryKey: ["reponses-obsoletes", "count"],
    queryFn: () => getReponsesObsoletes({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });

  const { data: compteurARelire } = useQuery({
    queryKey: ["reponses-a-relire", "count"],
    queryFn: () => getReponsesARelire({ page: 1, limit: 1 }),
    staleTime: 60_000,
  });

  const nbObsoletes = compteur?.total ?? 0;
  const nbDocsARelire = compteurARelire?.nb_documents ?? 0;
  const requete = onglet === "canoniques" ? canoniques : onglet === "obsoletes" ? obsoletes : aRelire;

  return { canoniques, obsoletes, aRelire, nbObsoletes, nbDocsARelire, requete };
}
