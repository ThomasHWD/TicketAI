import { AlertTriangle, Archive, BadgeCheck, Search, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Onglet } from "./utils";

interface SavedAnswersHeaderProps {
  onglet: Onglet;
  nbDocsARelire: number;
  nbObsoletes: number;
  searchQuery: string;
  loading: boolean;
  error: unknown;
  total: number;
  canoniquesCount: number;
  onOngletChange: (o: Onglet) => void;
  onSearchChange: (q: string) => void;
}

function Tab({
  active,
  onClick,
  Icon,
  iconActiveClass = "text-gray-700 dark:text-gray-200",
  label,
  badge,
  badgeVariant = "neutral",
}: {
  active: boolean;
  onClick: () => void;
  Icon: LucideIcon;
  iconActiveClass?: string;
  label: string;
  badge?: number;
  badgeVariant?: "amber" | "neutral";
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`relative flex items-center gap-2 px-3 py-2.5 text-sm font-medium transition-colors whitespace-nowrap ${
        active
          ? "text-gray-900 dark:text-gray-50"
          : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
      }`}
    >
      <Icon
        size={15}
        className={active ? iconActiveClass : "text-gray-400 dark:text-gray-500"}
        aria-hidden="true"
      />
      {label}
      {badge !== undefined && badge > 0 && (
        <span
          className={`inline-flex items-center justify-center min-w-[1.25rem] px-1.5 rounded-full text-xs font-semibold tabular-nums ${
            badgeVariant === "amber"
              ? "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300"
              : "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300"
          }`}
        >
          {badge}
        </span>
      )}
      {active && (
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-gray-900 dark:bg-gray-50 rounded-full" />
      )}
    </button>
  );
}

export default function SavedAnswersHeader({
  onglet,
  nbDocsARelire,
  nbObsoletes,
  searchQuery,
  loading,
  error,
  total,
  canoniquesCount,
  onOngletChange,
  onSearchChange,
}: SavedAnswersHeaderProps) {
  const showSearch = onglet !== "a_relire";

  return (
    <>
      {/* Toolbar: tabs + search on one row */}
      <div className="flex items-center justify-between gap-4 px-4 border-b border-gray-100 dark:border-white/8">
        <div className="flex items-center gap-0.5" role="tablist">
          <Tab
            active={onglet === "canoniques"}
            onClick={() => onOngletChange("canoniques")}
            Icon={BadgeCheck}
            iconActiveClass="text-emerald-500"
            label="Canoniques"
          />
          <Tab
            active={onglet === "a_relire"}
            onClick={() => onOngletChange("a_relire")}
            Icon={AlertTriangle}
            iconActiveClass="text-amber-500"
            label="À relire"
            badge={nbDocsARelire}
            badgeVariant="amber"
          />
          <Tab
            active={onglet === "obsoletes"}
            onClick={() => onOngletChange("obsoletes")}
            Icon={Archive}
            label="Obsolètes"
            badge={nbObsoletes}
          />
        </div>

        {/* Search — right side, visible for Canoniques & Obsolètes */}
        <div
          className={`py-2 transition-all duration-150 ${
            showSearch ? "opacity-100 w-56" : "opacity-0 w-0 pointer-events-none"
          }`}
        >
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
            <input
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Chercher par question…"
              aria-label="Chercher par question"
              className="w-full pl-7 pr-7 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-white/12 bg-gray-50 dark:bg-white/5 text-gray-800 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 placeholder:text-gray-400 transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => onSearchChange("")}
                aria-label="Effacer la recherche"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Contextual banners */}
      {onglet === "a_relire" && !loading && !error && total > 0 && (
        <div className="px-5 py-3 flex items-center gap-3 border-b border-amber-100 dark:border-amber-500/15 bg-amber-50/60 dark:bg-amber-400/5">
          <AlertTriangle size={14} className="text-amber-500 shrink-0" aria-hidden="true" />
          <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
            <span className="font-semibold">{nbDocsARelire} document{nbDocsARelire > 1 ? "s" : ""} mis à jour</span>
            {" · "}
            {total} réponse{total > 1 ? "s" : ""} à vérifier —{" "}
            <span className="italic">servies en l'état jusqu'à décision humaine.</span>
          </p>
        </div>
      )}

      {onglet === "obsoletes" && (
        <div className="px-5 py-3 border-b border-gray-100 dark:border-white/8">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Ces réponses ne sont plus servies. Leurs validations sont conservées — les restaurer les remet en service telles quelles.
          </p>
        </div>
      )}

      {/* Stats bar for canoniques */}
      {onglet === "canoniques" && !loading && !error && total > 0 && (
        <div className="px-5 py-2.5 flex items-center gap-2 border-b border-gray-100 dark:border-white/8">
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {total} réponse{total > 1 ? "s" : ""} canonique{total > 1 ? "s" : ""}
          </span>
          {searchQuery.trim() && (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              · {canoniquesCount} résultat{canoniquesCount !== 1 ? "s" : ""} sur cette page
            </span>
          )}
        </div>
      )}
    </>
  );
}
