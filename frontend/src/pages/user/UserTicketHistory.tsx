import { useState, useMemo, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Plus, Search, X } from "lucide-react";
import { getTickets } from "../../lib/api";
import { getSiteConfig } from "../../lib/api/admin";
import { getValidatorId } from "../../lib/currentUser";
import { TicketHistoryTable } from "../../components/user/TicketHistoryTable";
import type { Ticket } from "../../types";

const PAGE_SIZE = 10;

type Tab = "toutes" | "en_traitement" | "repondues" | "cloturees";
const TABS: { value: Tab; label: string }[] = [
  { value: "toutes",        label: "Toutes" },
  { value: "en_traitement", label: "En traitement" },
  { value: "repondues",     label: "Répondues" },
  { value: "cloturees",     label: "Clôturées" },
];
const VALID_TABS: Tab[] = ["toutes", "en_traitement", "repondues", "cloturees"];

function matchesTab(t: Ticket, tab: Tab): boolean {
  const closed = !!t.closed_at;
  const processing = t.statut_job === "EN_ATTENTE" || t.statut_job === "EN_COURS";
  switch (tab) {
    case "toutes":        return true;
    case "cloturees":     return closed;
    case "en_traitement": return !closed && (processing || t.statut_ticket === "NOUVEAU" || (t.statut_ticket === "RÉPONDU" && !t.canonique));
    case "repondues":     return !closed && !processing && (t.statut_ticket === "VALIDÉ" || t.canonique);
  }
}

export default function UserTicketHistory() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const userId = getValidatorId();

  const rawTab = searchParams.get("tab") as Tab;
  const activeTab: Tab = VALID_TABS.includes(rawTab) ? rawTab : "toutes";
  const page = Math.max(1, parseInt(searchParams.get("page") ?? "1", 10) || 1);
  const debouncedSearch = searchParams.get("q") ?? "";
  const [inputSearch, setInputSearch] = useState(debouncedSearch);

  useEffect(() => { setInputSearch(debouncedSearch); }, [debouncedSearch]);

  useEffect(() => {
    const t = setTimeout(() => {
      setSearchParams((prev) => {
        if (inputSearch) prev.set("q", inputSearch); else prev.delete("q");
        prev.delete("page");
        return prev;
      }, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [inputSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  function setActiveTab(tab: Tab) {
    setSearchParams((prev) => { prev.set("tab", tab); prev.delete("page"); return prev; }, { replace: true });
  }

  function setPage(updater: (p: number) => number) {
    setSearchParams((prev) => { prev.set("page", String(updater(page))); return prev; }, { replace: true });
  }

  function resetFilters() {
    setInputSearch("");
    setSearchParams((prev) => { prev.delete("tab"); prev.delete("q"); prev.delete("page"); return prev; }, { replace: true });
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ["mes-tickets", userId],
    queryFn: () => getTickets({ limit: 400, userId }),
    staleTime: 30_000,
  });

  const { data: siteConfig } = useQuery({
    queryKey: ["site-config"],
    queryFn: getSiteConfig,
    staleTime: 5 * 60_000,
  });
  const joursAutoCloture = siteConfig?.jours_auto_cloture ?? 7;

  const allTickets: Ticket[] = useMemo(() => data?.items ?? [], [data]);
  const totalCount = data?.total ?? allTickets.length;
  const isTruncated = !isLoading && (data?.total ?? 0) > allTickets.length;

  const counts = useMemo<Record<Tab, number>>(() => ({
    toutes:        allTickets.length,
    en_traitement: allTickets.filter((t) => matchesTab(t, "en_traitement")).length,
    repondues:     allTickets.filter((t) => matchesTab(t, "repondues")).length,
    cloturees:     allTickets.filter((t) => matchesTab(t, "cloturees")).length,
  }), [allTickets]);

  const filtered = useMemo(
    () => allTickets.filter((t) =>
      matchesTab(t, activeTab) &&
      (!debouncedSearch || (t.objet ?? t.question).toLowerCase().includes(debouncedSearch.toLowerCase()))
    ),
    [allTickets, activeTab, debouncedSearch],
  );

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const from = filtered.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, filtered.length);
  const pageTickets = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const isFiltered = activeTab !== "toutes" || !!debouncedSearch;

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100 tracking-tight">Mon historique</h1>
        {!isLoading && totalCount > 0 && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 tabular-nums border border-gray-200/60 dark:border-white/[0.08]">
            {totalCount}
          </span>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <nav className="flex items-center gap-1 flex-1 min-w-0" aria-label="Filtrer par statut">
          {TABS.map((tab) => {
            const count = counts[tab.value];
            const active = activeTab === tab.value;
            return (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                aria-current={active ? "true" : undefined}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 border-b-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500 ${
                  active
                    ? "border-emerald-500 text-gray-900 dark:text-gray-100"
                    : "border-transparent text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-white/20"
                }`}
              >
                {tab.label}
                {count > 0 && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums leading-none bg-gray-100 text-muted-foreground dark:bg-white/10">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="hidden sm:block w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" aria-hidden="true" />

        <div className="relative shrink-0 w-full sm:w-48">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle pointer-events-none" aria-hidden="true" />
          <input
            type="search" placeholder="Rechercher…" aria-label="Rechercher dans l'historique"
            value={inputSearch} onChange={(e) => setInputSearch(e.target.value)}
            className="pl-8 pr-7 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500 w-full transition-shadow"
          />
          {inputSearch && (
            <button onClick={() => setInputSearch("")} aria-label="Effacer la recherche" className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center justify-center w-6 h-6 text-muted-foreground hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
              <X size={12} aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="hidden sm:block w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" aria-hidden="true" />

        <button onClick={() => navigate("/nouveau-ticket")} className="inline-flex items-center gap-1.5 shrink-0 text-sm font-medium px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors">
          <Plus size={14} className="text-emerald-500" aria-hidden="true" />
          Nouvelle question
        </button>
      </div>

      {isTruncated && (
        <div role="status" className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 text-xs text-amber-700 dark:text-amber-400">
          <AlertCircle size={13} className="shrink-0" aria-hidden="true" />
          Seules les {allTickets.length} questions les plus récentes sont affichées ({data?.total} au total).
        </div>
      )}

      <TicketHistoryTable
        tickets={pageTickets}
        isLoading={isLoading}
        error={error}
        isFiltered={isFiltered}
        joursAutoCloture={joursAutoCloture}
        from={from}
        to={to}
        page={page}
        totalPages={totalPages}
        filteredCount={filtered.length}
        onRetry={() => queryClient.invalidateQueries({ queryKey: ["mes-tickets", userId] })}
        onNew={() => navigate("/nouveau-ticket")}
        onReset={resetFilters}
        onPageChange={setPage}
      />
    </div>
  );
}
