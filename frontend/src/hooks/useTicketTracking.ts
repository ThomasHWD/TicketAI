import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getParticipatedTickets, getMyAssignedTickets } from "../lib/api";
import type { Ticket } from "../types";

export type FilterKey = "tous" | "en_attente" | "en_cours" | "clotures";
export type TabKey = "assigned" | "participated";

const LIMIT = 10;

function isProcessingTicket(t: Ticket) {
  return t.statut_job === "EN_ATTENTE" || t.statut_job === "EN_COURS";
}

export function matchesTrackingFilter(t: Ticket, filter: FilterKey): boolean {
  const closed = !!t.closed_at;
  if (filter === "clotures") return closed;
  if (closed) return false;
  if (filter === "tous") return true;
  if (filter === "en_attente")
    return t.statut_ticket === "NOUVEAU" || (t.statut_ticket === "RÉPONDU" && !t.canonique);
  if (filter === "en_cours")
    return t.canonique === true || t.statut_ticket === "VALIDÉ";
  return true;
}

export function matchesSearch(t: Ticket, q: string): boolean {
  if (!q.trim()) return true;
  const needle = q.toLowerCase();
  return (
    (t.objet ?? t.question).toLowerCase().includes(needle) ||
    t.domaine.toLowerCase().includes(needle)
  );
}

export function useTicketTracking() {
  const [tab, setTabState] = useState<TabKey>("assigned");
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<FilterKey>("tous");
  const [search, setSearch] = useState("");

  const {
    data: participatedData,
    isLoading: participatedLoading,
    isFetching: participatedFetching,
    error: participatedError,
    refetch: refetchParticipated,
  } = useQuery({
    queryKey: ["tickets", "participated", page],
    queryFn: () => getParticipatedTickets(page),
    placeholderData: (prev) => prev,
  });

  const {
    data: assignedTickets = [],
    isLoading: assignedLoading,
    isFetching: assignedFetching,
    error: assignedError,
    refetch: refetchAssigned,
  } = useQuery<Ticket[]>({
    queryKey: ["mes-assignations"],
    queryFn: getMyAssignedTickets,
  });

  const participatedTickets = participatedData?.items ?? [];
  const total = participatedData?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) setPage(totalPages);
  }, [totalPages, page]);

  const activeTickets = tab === "assigned" ? assignedTickets : participatedTickets;

  const filteredTickets = useMemo(
    () => activeTickets.filter((t) => matchesTrackingFilter(t, filter) && matchesSearch(t, search)),
    [activeTickets, filter, search],
  );

  const counts = useMemo<Record<FilterKey, number>>(
    () => ({
      tous:       activeTickets.filter((t) => matchesTrackingFilter(t, "tous")).length,
      en_attente: activeTickets.filter((t) => matchesTrackingFilter(t, "en_attente")).length,
      en_cours:   activeTickets.filter((t) => matchesTrackingFilter(t, "en_cours")).length,
      clotures:   activeTickets.filter((t) => matchesTrackingFilter(t, "clotures")).length,
    }),
    [activeTickets],
  );

  const assignedEnAttente = useMemo(
    () => assignedTickets.filter((t) => matchesTrackingFilter(t, "en_attente")).length,
    [assignedTickets],
  );

  const isFetchingBg = tab === "assigned"
    ? (assignedFetching && !assignedLoading)
    : (participatedFetching && !participatedLoading);

  const hasActiveFilters = filter !== "tous" || !!search;

  function handleTabChange(t: TabKey) {
    setTabState(t);
    setFilter("tous");
    setSearch("");
    setPage(1);
  }

  function handleClearFilters() {
    setFilter("tous");
    setSearch("");
  }

  // derived ticket state
  function isTicketProcessing(t: Ticket) { return isProcessingTicket(t); }
  function isTicketClosed(t: Ticket) { return !!t.closed_at; }

  return {
    tab, filter, search, page,
    setFilter, setSearch, setPage,
    filteredTickets, counts, assignedEnAttente,
    assignedTickets, participatedTickets,
    total, totalPages, from, to,
    isFetchingBg, hasActiveFilters,
    isTicketProcessing, isTicketClosed,
    // query state per tab
    loading: tab === "assigned" ? assignedLoading : participatedLoading,
    error: (tab === "assigned" ? assignedError : participatedError) as Error | null,
    onRetry: tab === "assigned" ? refetchAssigned : refetchParticipated,
    handleTabChange, handleClearFilters,
  };
}
