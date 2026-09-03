import { useEffect, useRef } from "react";
import { FILTER_TABS, TAB_HINTS } from "../../lib/ticketFilters";
import { useTicketsList } from "../../hooks/useTicketsList";
import { TicketsToolbar } from "../../components/tickets/TicketsToolbar";
import { TicketsTable } from "../../components/tickets/TicketsTable";

export default function TicketsList() {
  const {
    page, setPage,
    search, setSearch,
    debouncedSearch,
    filter, sortDir, domainFilter,
    multiDomain, isClosed, hasFilters, isFetchingBg,
    isCountCapped, tabCounts,
    tickets, total, totalPages, from, to,
    isLoading, error, refetch,
    handleFilterChange, handleDomainChange, handleSortToggle, handleClearFilters,
    userDomaines,
  } = useTicketsList();

  const searchRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcuts: / → search · 1–4 → filter tabs · j/k → row navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inInput = target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";

      if (e.key === "/" && !inInput) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      if (inInput) return;

      if (e.key >= "1" && e.key <= "4") {
        const tab = FILTER_TABS[parseInt(e.key) - 1];
        if (tab) { e.preventDefault(); handleFilterChange(tab.value); document.getElementById(`filter-tab-${tab.value}`)?.focus(); }
        return;
      }

      const rows = Array.from(document.querySelectorAll<HTMLElement>('#tickets-table tbody tr[tabindex="0"]'));
      if (!rows.length) return;
      const activeIndex = rows.findIndex((r) => r === document.activeElement);
      if (e.key === "j") { e.preventDefault(); rows[Math.min(activeIndex + 1, rows.length - 1)]?.focus(); }
      else if (e.key === "k") { e.preventDefault(); rows[Math.max(activeIndex - 1, 0)]?.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleFilterChange]);

  return (
    <div className="p-6 space-y-5">
      {/* Live region for screen readers */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {!isLoading && !error && debouncedSearch
          ? `${tickets.length} ticket${tickets.length !== 1 ? "s" : ""} pour « ${debouncedSearch} »`
          : ""}
      </div>

      {/* Page header */}
      <div className="flex items-center gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100 tracking-tight">
            Tickets
          </h1>
          {!multiDomain && userDomaines.length > 0 && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{userDomaines[0]}</p>
          )}
        </div>
        {total > 0 && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 tabular-nums border border-gray-200/60 dark:border-white/[0.08]">
            {total}
          </span>
        )}
      </div>

      <TicketsToolbar
        filter={filter}
        sortDir={sortDir}
        domainFilter={domainFilter}
        search={search}
        tabCounts={tabCounts}
        isCountCapped={isCountCapped}
        multiDomain={multiDomain}
        userDomaines={userDomaines}
        hasFilters={hasFilters}
        searchRef={searchRef}
        onFilterChange={handleFilterChange}
        onDomainChange={handleDomainChange}
        onSortToggle={handleSortToggle}
        onSearchChange={setSearch}
        onClearFilters={handleClearFilters}
      />

      <p className="text-xs text-gray-500 dark:text-gray-400 -mt-2 px-1">
        {TAB_HINTS[filter]}
      </p>

      <TicketsTable
        tickets={tickets}
        isLoading={isLoading}
        isFetchingBg={isFetchingBg}
        error={error}
        hasFilters={hasFilters}
        isClosed={isClosed}
        multiDomain={multiDomain}
        total={total}
        from={from}
        to={to}
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        onRefetch={refetch}
      />
    </div>
  );
}
