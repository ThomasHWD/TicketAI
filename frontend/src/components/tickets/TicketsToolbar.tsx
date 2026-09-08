import { useRef } from "react";
import {
  ChevronDown, ChevronUp, Layers, Search, HelpCircle, X,
} from "lucide-react";
import {
  FILTER_TABS, LEGEND_ITEMS,
  type FilterView,
} from "../../lib/ticketFilters";

interface TicketsToolbarProps {
  filter: FilterView;
  sortDir: "desc" | "asc";
  domainFilter: string;
  search: string;
  tabCounts: Partial<Record<FilterView, number>>;
  isCountCapped: boolean;
  multiDomain: boolean;
  userDomaines: string[];
  hasFilters: boolean;
  searchRef: React.RefObject<HTMLInputElement | null>;
  onFilterChange: (v: FilterView) => void;
  onDomainChange: (v: string) => void;
  onSortToggle: () => void;
  onSearchChange: (v: string) => void;
  onClearFilters: () => void;
}

export function TicketsToolbar({
  filter, sortDir, domainFilter, search,
  tabCounts, isCountCapped, multiDomain, userDomaines,
  hasFilters, searchRef,
  onFilterChange, onDomainChange, onSortToggle, onSearchChange, onClearFilters,
}: TicketsToolbarProps) {
  const legendRef = useRef<HTMLDetailsElement>(null);

  function handleFilterKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const tabs = FILTER_TABS.map((t) => t.value);
    const currentIndex = tabs.indexOf(filter);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = tabs[(currentIndex + 1) % tabs.length];
      onFilterChange(next);
      document.getElementById(`filter-tab-${next}`)?.focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
      onFilterChange(prev);
      document.getElementById(`filter-tab-${prev}`)?.focus();
    }
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* Filtres statut */}
      <div
        className="flex items-center gap-1 flex-1 min-w-0"
        role="tablist"
        aria-label="Filtres par statut"
        aria-orientation="horizontal"
        onKeyDown={handleFilterKeyDown}
      >
        {FILTER_TABS.map((tab) => {
          const count = tabCounts[tab.value];
          const active = filter === tab.value;
          return (
            <button
              key={tab.value}
              id={`filter-tab-${tab.value}`}
              role="tab"
              aria-selected={active}
              aria-controls="tickets-table"
              tabIndex={active ? 0 : -1}
              title={tab.title}
              onClick={() => onFilterChange(tab.value)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 min-h-[44px] border-b-2 text-sm font-medium transition-colors duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-offset-1 ${
                active
                  ? "border-emerald-500 text-gray-900 dark:text-gray-100"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-white/20"
              }`}
            >
              {tab.label}
              {count !== undefined && count > 0 && (
                <span
                  className={`inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums leading-none ${
                    active
                      ? "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300"
                      : "bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400"
                  }`}
                  title={isCountCapped && tab.value !== "tous" ? "Compteur approximatif (plus de 200 tickets)" : undefined}
                >
                  {isCountCapped && tab.value !== "tous" ? `~${count}` : count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" aria-hidden="true" />

      {/* Filtre domaine */}
      {multiDomain && (
        <div className="relative shrink-0 inline-flex items-center">
          <Layers size={12} className="absolute left-2.5 text-gray-500 dark:text-gray-400 pointer-events-none" aria-hidden="true" />
          <select
            value={domainFilter}
            onChange={(e) => onDomainChange(e.target.value)}
            className="pl-7 pr-6 py-1.5 min-h-[44px] text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 appearance-none transition-shadow"
            aria-label="Filtrer par domaine"
          >
            <option value="tous">Tous les domaines</option>
            {userDomaines.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
      )}

      {/* Recherche */}
      <div className="relative shrink-0">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400 pointer-events-none" aria-hidden="true" />
        <input
          ref={searchRef}
          type="text"
          placeholder="Rechercher… (/ pour cibler)"
          aria-label="Rechercher un ticket"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-8 pr-7 py-1.5 min-h-[44px] text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-48 transition-shadow"
        />
        {search && (
          <button
            onClick={() => { onSearchChange(""); searchRef.current?.focus(); }}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus-visible:ring-1 focus-visible:ring-emerald-400"
            aria-label="Effacer la recherche"
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Tri */}
      <button
        onClick={onSortToggle}
        className={`shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 min-h-[44px] rounded-lg text-xs font-medium transition-colors border focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 ${
          sortDir === "asc"
            ? "bg-gray-100 dark:bg-white/10 text-gray-700 dark:text-gray-200 border-gray-300 dark:border-white/20"
            : "bg-white dark:bg-white/5 text-gray-500 dark:text-gray-400 border-gray-200 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
        }`}
        aria-label={`Trier par date : ${sortDir === "desc" ? "plus récent en premier" : "plus ancien en premier"}`}
        aria-pressed={sortDir === "asc"}
      >
        {sortDir === "desc"
          ? <ChevronDown size={12} aria-hidden="true" />
          : <ChevronUp size={12} aria-hidden="true" />
        }
        {sortDir === "desc" ? "Plus récent" : "Plus ancien"}
      </button>

      {/* Effacer filtres */}
      {hasFilters && (
        <button
          onClick={onClearFilters}
          className="shrink-0 inline-flex items-center gap-1 min-h-[44px] px-2 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 rounded-md"
          aria-label="Effacer tous les filtres"
        >
          <X size={11} aria-hidden="true" />
          Effacer
        </button>
      )}

      {/* Légende */}
      <details
        ref={legendRef}
        className="relative shrink-0"
        onBlur={(e) => {
          if (!legendRef.current?.contains(e.relatedTarget as Node)) {
            legendRef.current?.removeAttribute("open");
          }
        }}
      >
        <summary className="inline-flex items-center gap-1 min-h-[44px] px-2 text-xs text-gray-500 dark:text-gray-400 cursor-pointer list-none select-none hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 rounded-md">
          <HelpCircle size={12} aria-hidden="true" />
          <span>Légende</span>
        </summary>
        <div className="absolute right-0 top-full mt-1 z-20 glass-card rounded-xl p-3 w-64 border border-gray-100 dark:border-white/10 shadow-lg space-y-3">
          <div className="space-y-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 pb-1 border-b border-gray-100 dark:border-white/5">
              Statut du ticket
            </p>
            {LEGEND_ITEMS.map(({ color, label, desc }) => (
              <div key={label} className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full shrink-0 ${color}`} aria-hidden="true" />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{label}</span>
                <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto pl-2 text-right">{desc}</span>
              </div>
            ))}
          </div>
          <div className="pt-2 border-t border-gray-100 dark:border-white/5">
            <p className="text-[10px] text-gray-500 dark:text-gray-400">
              Raccourcis :{" "}
              <kbd className="font-mono bg-gray-100 dark:bg-white/10 px-0.5 rounded text-gray-600 dark:text-gray-300">j</kbd>
              /<kbd className="font-mono bg-gray-100 dark:bg-white/10 px-0.5 rounded text-gray-600 dark:text-gray-300">k</kbd> naviguer ·{" "}
              <kbd className="font-mono bg-gray-100 dark:bg-white/10 px-0.5 rounded text-gray-600 dark:text-gray-300">/</kbd> rechercher ·{" "}
              <kbd className="font-mono bg-gray-100 dark:bg-white/10 px-0.5 rounded text-gray-600 dark:text-gray-300">1–4</kbd> onglets
            </p>
          </div>
        </div>
      </details>
    </div>
  );
}
