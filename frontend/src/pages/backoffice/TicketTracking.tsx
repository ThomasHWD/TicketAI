import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Loader2, MessageSquare, UserCheck, Inbox, ClipboardList } from "lucide-react";
import { useTicketTracking, type TabKey } from "../../hooks/useTicketTracking";
import { FilterBar, TrackingTicketTable } from "../../components/tickets/TrackingTable";

const TABS: { key: TabKey; label: string; icon: React.ElementType }[] = [
  { key: "assigned",    label: "Assignés à moi",    icon: UserCheck },
  { key: "participated", label: "Mes participations", icon: ClipboardList },
];

export default function TicketTracking() {
  const {
    tab, filter, search, page,
    setFilter, setSearch, setPage,
    filteredTickets, counts, assignedEnAttente,
    assignedTickets, total, totalPages, from, to,
    isFetchingBg, hasActiveFilters,
    loading, error, onRetry,
    handleTabChange, handleClearFilters,
  } = useTicketTracking();

  const searchRef = useRef<HTMLInputElement>(null);
  const mainTabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Keyboard shortcuts: / → search · 1–4 → filters · j/k → row navigation
  useEffect(() => {
    const FILTER_KEYS = ["tous", "en_attente", "en_cours", "clotures"] as const;
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inInput = target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";
      if (e.key === "/" && !inInput) { e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select(); return; }
      if (inInput) return;
      if (e.key >= "1" && e.key <= "4") {
        const f = FILTER_KEYS[parseInt(e.key) - 1];
        if (f) { e.preventDefault(); setFilter(f); }
        return;
      }
      const rows = Array.from(document.querySelectorAll<HTMLElement>('tbody tr[tabindex="0"]'));
      if (!rows.length) return;
      const idx = rows.findIndex((r) => r === document.activeElement);
      if (e.key === "j") { e.preventDefault(); rows[Math.min(idx + 1, rows.length - 1)]?.focus(); }
      else if (e.key === "k") { e.preventDefault(); rows[Math.max(idx - 1, 0)]?.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [setFilter]);

  function handleMainTabKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = (idx + 1) % TABS.length;
      mainTabRefs.current[next]?.focus();
      handleTabChange(TABS[next].key);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = (idx - 1 + TABS.length) % TABS.length;
      mainTabRefs.current[prev]?.focus();
      handleTabChange(TABS[prev].key);
    }
  }

  const emptyTitle = hasActiveFilters
    ? "Aucun ticket ne correspond à vos filtres."
    : tab === "assigned"
    ? "Aucun ticket ne vous est assigné."
    : "Vous n'avez encore participé à aucun ticket.";

  const emptySubtitle = hasActiveFilters
    ? "Modifiez vos critères ou effacez les filtres."
    : tab === "assigned"
    ? "Les tickets assignés directement à votre compte apparaîtront ici."
    : "Les tickets sur lesquels vous avez commenté ou validé apparaîtront ici.";

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Mon suivi</h1>
        <div className="flex items-center gap-2">
          <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm ${
            assignedEnAttente > 0
              ? "bg-emerald-50 border-emerald-200/80 text-emerald-700 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-300"
              : "bg-gray-50 border-gray-200 text-gray-600 dark:bg-white/5 dark:border-white/10 dark:text-muted-foreground"
          }`}>
            <UserCheck size={13} className="opacity-70" aria-hidden="true" />
            <span className="font-semibold tabular-nums">{assignedEnAttente}</span>
            <span className="text-xs">à valider</span>
          </div>
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm bg-gray-50 border-gray-200 text-gray-600 dark:bg-white/5 dark:border-white/10 dark:text-muted-foreground">
            <MessageSquare size={13} className="opacity-70" aria-hidden="true" />
            <span className="font-semibold tabular-nums">{total}</span>
            <span className="text-xs">participations</span>
          </div>
        </div>
      </div>

      {/* Card */}
      <div className="glass-card rounded-2xl overflow-hidden">

        {/* Tab bar */}
        <div role="tablist" aria-label="Vue des tickets" className="flex items-center border-b border-gray-200 dark:border-white/10 px-5">
          {TABS.map(({ key, label, icon: Icon }, idx) => (
            <button
              key={key}
              ref={(el) => { mainTabRefs.current[idx] = el; }}
              role="tab"
              id={`tracking-tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`tracking-panel-${key}`}
              tabIndex={tab === key ? 0 : -1}
              onClick={() => handleTabChange(key)}
              onKeyDown={(e) => handleMainTabKeyDown(e, idx)}
              className={`relative flex items-center gap-2 py-3.5 pr-5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500/60 ${
                tab === key
                  ? "text-gray-900 dark:text-gray-100"
                  : "text-muted-foreground hover:text-gray-700 dark:hover:text-gray-200"
              }`}
            >
              <Icon size={14} className={tab === key ? "text-emerald-500" : "opacity-50"} aria-hidden="true" />
              {label}
              {key === "assigned" && assignedTickets.length > 0 && (
                <span className={`inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold ${
                  tab === key ? "bg-primary text-primary-foreground" : "bg-gray-200 text-gray-600 dark:bg-white/10 dark:text-muted-foreground"
                }`}>
                  {assignedTickets.length}
                </span>
              )}
              {tab === key && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" aria-hidden="true" />}
            </button>
          ))}
        </div>

        {isFetchingBg && (
          <div role="status" aria-live="polite" aria-label="Actualisation en cours" className="px-5 py-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground border-b border-gray-100 dark:border-white/5">
            <Loader2 size={11} className="animate-spin" aria-hidden="true" />
            Actualisation…
          </div>
        )}

        {/* Tab panel */}
        <div role="tabpanel" id={`tracking-panel-${tab}`} aria-labelledby={`tracking-tab-${tab}`}>
          <FilterBar
            filter={filter}
            setFilter={setFilter}
            search={search}
            setSearch={setSearch}
            counts={counts}
            searchRef={searchRef}
          />

          <TrackingTicketTable
            tickets={filteredTickets}
            loading={loading}
            error={error}
            onRetry={onRetry}
            onClear={hasActiveFilters ? handleClearFilters : undefined}
            emptyIcon={tab === "assigned" ? UserCheck : Inbox}
            emptyTitle={emptyTitle}
            emptySubtitle={emptySubtitle}
          />

          {/* Pagination — participations uniquement */}
          {tab === "participated" && !loading && total > 0 && (
            <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 dark:border-white/5 text-xs text-muted-foreground">
              <span className="tabular-nums">{from}–{to} sur {total}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                  aria-label="Page précédente"
                >
                  <ChevronLeft size={14} aria-hidden="true" />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                  aria-label="Page suivante"
                >
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <p role="note" aria-label="Raccourcis clavier" className="text-[11px] text-muted-foreground text-right select-none">
        Raccourcis&nbsp;: <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> naviguer · <kbd className="font-mono">/</kbd> rechercher · <kbd className="font-mono">1–4</kbd> filtres · <kbd className="font-mono">Échap</kbd> quitter la recherche
      </p>
    </div>
  );
}
