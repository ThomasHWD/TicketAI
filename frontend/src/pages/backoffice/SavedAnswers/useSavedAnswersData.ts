import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getReponsesARelire, getReponsesCanoniques, getReponsesObsoletes, getTags } from "../../../lib/api";
import { LIMIT, type Onglet } from "./utils";

export function useSavedAnswersData(onglet: Onglet, page: number, search: string = "", domaine?: string, tag?: string) {
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const q = debouncedSearch || undefined;
  const d = domaine || undefined;

  const canoniques = useQuery({
    queryKey: ["reponses-canoniques", page, debouncedSearch, domaine, tag],
    queryFn: () => getReponsesCanoniques({ page, limit: LIMIT, q, domaine: d, tag }),
    placeholderData: (prev) => prev,
    enabled: onglet === "canoniques",
  });

  const obsoletes = useQuery({
    queryKey: ["reponses-obsoletes", "liste", page, debouncedSearch, domaine],
    queryFn: () => getReponsesObsoletes({ page, limit: LIMIT, q, domaine: d }),
    placeholderData: (prev) => prev,
    enabled: onglet === "obsoletes",
  });

  const aRelire = useQuery({
    queryKey: ["reponses-a-relire", "liste", page, debouncedSearch, domaine],
    queryFn: () => getReponsesARelire({ page, limit: LIMIT, q, domaine: d }),
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

  const tagsQuery = useQuery({
    queryKey: ["tags-canoniques", domaine],
    queryFn: () => getTags(domaine, true),
    staleTime: 0,
    gcTime: 0,
    enabled: onglet === "canoniques",
  });

  const nbObsoletes = compteur?.total ?? 0;
  const nbDocsARelire = compteurARelire?.nb_documents ?? 0;
  const requete = onglet === "canoniques" ? canoniques : onglet === "obsoletes" ? obsoletes : aRelire;
  const tagsDisponibles = tagsQuery.data ?? [];

  return { canoniques, obsoletes, aRelire, nbObsoletes, nbDocsARelire, requete, tagsDisponibles };
}
