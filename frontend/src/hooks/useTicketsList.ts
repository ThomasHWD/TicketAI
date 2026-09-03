import { useState, useEffect, useMemo, useCallback } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTickets } from "../lib/api";
import { useAuth } from "../lib/auth";
import { matchesFilter, type FilterView } from "../lib/ticketFilters";
import type { Domaine, Ticket } from "../types";

const LIMIT = 10;

export function useTicketsList() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { userDomaines } = useAuth();

  const locationState = location.state as { filter?: FilterView; domaine?: string } | null;

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filter, setFilter] = useState<FilterView>(
    (searchParams.get("filter") as FilterView) ?? locationState?.filter ?? "tous"
  );
  const [sortDir, setSortDir] = useState<"desc" | "asc">(
    (searchParams.get("sort") as "desc" | "asc") ?? "desc"
  );
  const [domainFilter, setDomainFilter] = useState<string>(
    searchParams.get("domain") ?? locationState?.domaine ?? "tous"
  );

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { setPage(1); }, [debouncedSearch, filter, domainFilter, sortDir]);

  const handleFilterChange = useCallback((value: FilterView) => {
    setFilter(value);
    setSearchParams((prev) => { prev.set("filter", value); return prev; });
  }, [setSearchParams]);

  const handleDomainChange = useCallback((value: string) => {
    setDomainFilter(value);
    setSearchParams((prev) => { prev.set("domain", value); return prev; });
  }, [setSearchParams]);

  const handleSortToggle = useCallback(() => {
    const next = sortDir === "desc" ? "asc" : "desc";
    setSortDir(next);
    setSearchParams((prev) => { prev.set("sort", next); return prev; });
  }, [sortDir, setSearchParams]);

  const handleClearFilters = useCallback(() => {
    setSearch("");
    handleFilterChange("tous");
    handleDomainChange("tous");
    setSearchParams({});
  }, [handleFilterChange, handleDomainChange, setSearchParams]);

  const multiDomain = userDomaines.length > 1;
  const queryDomaines = domainFilter === "tous" ? userDomaines : undefined;
  const queryDomaine = domainFilter !== "tous" ? domainFilter as Domaine : undefined;
  const isClosed = filter === "clotures";

  const { data: countData } = useQuery({
    queryKey: ["tickets", "counts", userDomaines, domainFilter],
    queryFn: () => getTickets({ limit: 200, closed: false, domaines: queryDomaines, domaine: queryDomaine, disponibles: true }),
    staleTime: 30_000,
  });

  const isCountCapped = (countData?.total ?? 0) > 200;

  const tabCounts = useMemo(() => {
    const items = countData?.items ?? [];
    return {
      tous:       countData?.total ?? 0,
      en_attente: items.filter((t) => matchesFilter(t, "en_attente")).length,
      en_cours:   items.filter((t) => matchesFilter(t, "en_cours")).length,
    };
  }, [countData]);

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["tickets", isClosed ? "closed" : "open", page, userDomaines, domainFilter, debouncedSearch, filter],
    queryFn: () => getTickets({
      page,
      limit: LIMIT,
      closed: isClosed,
      domaines: queryDomaines,
      domaine: queryDomaine,
      disponibles: isClosed ? undefined : true,
      search: debouncedSearch || undefined,
    }),
    placeholderData: (prev) => prev,
  });

  const tickets: Ticket[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = total === 0 ? 0 : (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  const filtered = tickets.filter((t) => matchesFilter(t, filter));
  const sorted = sortDir === "asc"
    ? [...filtered].sort((a, b) =>
        new Date(a.created_at ?? 0).getTime() - new Date(b.created_at ?? 0).getTime()
      )
    : filtered;

  const hasFilters = !!debouncedSearch || filter !== "tous";
  const isFetchingBg = isFetching && !isLoading;

  return {
    // state
    page, setPage,
    search, setSearch,
    debouncedSearch,
    filter, sortDir, domainFilter,
    // computed
    multiDomain, isClosed, hasFilters, isFetchingBg,
    isCountCapped, tabCounts,
    tickets: sorted,
    total, totalPages, from, to,
    // query state
    isLoading, isFetching, error, refetch,
    // handlers
    handleFilterChange, handleDomainChange, handleSortToggle, handleClearFilters,
    // auth
    userDomaines,
  };
}
