import { useRef } from "react";
import { AlertTriangle, Archive, BadgeCheck, Loader2, Search, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Onglet } from "./utils";

interface SavedAnswersHeaderProps {
  onglet: Onglet;
  nbDocsARelire: number;
  nbObsoletes: number;
  searchQuery: string;
  loading: boolean;
  isFetching: boolean;
  error: unknown;
  total: number;
  canoniquesCount: number;
  domaines: string[];
  domaine: string | undefined;
  onOngletChange: (o: Onglet) => void;
  onSearchChange: (q: string) => void;
  onDomaine: (d: string | undefined) => void;
}

function Tab({
  id,
  active,
  onClick,
  Icon,
  iconActiveClass = "text-gray-700 dark:text-gray-200",
  label,
  badge,
  badgeAriaLabel,
  badgeVariant = "neutral",
  tabIndex = 0,
  onKeyDown,
  controls,
}: {
  id: string;
  active: boolean;
  onClick: () => void;
  Icon: LucideIcon;
  iconActiveClass?: string;
  label: string;
  badge?: number;
  badgeAriaLabel?: string;
  badgeVariant?: "amber" | "neutral";
  tabIndex?: number;
  onKeyDown?: (e: React.KeyboardEvent<HTMLButtonElement>) => void;
  controls: string;
}) {
  return (
    <button
      id={id}
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      tabIndex={tabIndex}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={`relative flex items-center gap-2 px-3 py-2.5 text-sm font-medium transition-colors whitespace-nowrap rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 ${
        active
          ? "text-gray-900 dark:text-gray-50"
          : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
      }`}
    >
      <Icon
        size={15}
        className={active ? iconActiveClass : "text-gray-500 dark:text-gray-400"}
        aria-hidden="true"
      />
      {label}
      {badge !== undefined && badge > 0 && (
        <span
          aria-label={badgeAriaLabel}
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
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-emerald-500 rounded-full" aria-hidden="true" />
      )}
    </button>
  );
}

const ONGLETS: Onglet[] = ["canoniques", "a_relire", "obsoletes"];

export default function SavedAnswersHeader({
  onglet,
  nbDocsARelire,
  nbObsoletes,
  searchQuery,
  loading,
  isFetching,
  error,
  total,
  canoniquesCount,
  domaines,
  domaine,
  onOngletChange,
  onSearchChange,
  onDomaine,
}: SavedAnswersHeaderProps) {
  const tablistRef = useRef<HTMLDivElement>(null);
  const searching = isFetching && searchQuery.trim().length > 0;

  function handleTabKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, idx: number) {
    let next = idx;
    if (e.key === "ArrowRight") { e.preventDefault(); next = (idx + 1) % ONGLETS.length; }
    else if (e.key === "ArrowLeft") { e.preventDefault(); next = (idx - 1 + ONGLETS.length) % ONGLETS.length; }
    else if (e.key === "Home") { e.preventDefault(); next = 0; }
    else if (e.key === "End") { e.preventDefault(); next = ONGLETS.length - 1; }
    else return;
    onOngletChange(ONGLETS[next]);
    const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[next]?.focus();
  }

  return (
    <>
      {/* Toolbar: tabs + search on one row */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 border-b border-gray-100 dark:border-white/8">
        <div
          ref={tablistRef}
          className="flex items-center gap-0.5"
          role="tablist"
          aria-label="Onglets — réponses enregistrées"
        >
          <Tab
            id="tab-canoniques"
            controls="panel-canoniques"
            active={onglet === "canoniques"}
            onClick={() => onOngletChange("canoniques")}
            Icon={BadgeCheck}
            iconActiveClass="text-emerald-500"
            label="Canoniques"
            tabIndex={onglet === "canoniques" ? 0 : -1}
            onKeyDown={(e) => handleTabKeyDown(e, 0)}
          />
          <Tab
            id="tab-a_relire"
            controls="panel-a_relire"
            active={onglet === "a_relire"}
            onClick={() => onOngletChange("a_relire")}
            Icon={AlertTriangle}
            iconActiveClass="text-amber-500"
            label="À relire"
            badge={nbDocsARelire}
            badgeAriaLabel={`${nbDocsARelire} document${nbDocsARelire > 1 ? "s" : ""} à relire`}
            badgeVariant="amber"
            tabIndex={onglet === "a_relire" ? 0 : -1}
            onKeyDown={(e) => handleTabKeyDown(e, 1)}
          />
          <Tab
            id="tab-obsoletes"
            controls="panel-obsoletes"
            active={onglet === "obsoletes"}
            onClick={() => onOngletChange("obsoletes")}
            Icon={Archive}
            label="Obsolètes"
            badge={nbObsoletes}
            badgeAriaLabel={`${nbObsoletes} réponse${nbObsoletes > 1 ? "s" : ""} obsolète${nbObsoletes > 1 ? "s" : ""}`}
            tabIndex={onglet === "obsoletes" ? 0 : -1}
            onKeyDown={(e) => handleTabKeyDown(e, 2)}
          />
        </div>

        {/* Filtre domaine — visible seulement si l'utilisateur a plusieurs domaines */}
        {domaines.length > 1 && (
          <div className="py-2 flex items-center gap-1" role="group" aria-label="Filtrer par domaine">
            {([undefined, ...domaines] as Array<string | undefined>).map((d) => (
              <button
                key={d ?? "tous"}
                type="button"
                onClick={() => onDomaine(d)}
                aria-pressed={domaine === d}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  domaine === d
                    ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-200"
                }`}
              >
                {d ?? "Tous"}
              </button>
            ))}
            <span aria-hidden="true" className="ml-1 h-4 w-px bg-gray-200 dark:bg-white/10" />
          </div>
        )}

        {/* Search — visible for all tabs */}
        <div className="py-2 w-56">
          <div className="relative">
            {searching ? (
              <Loader2 size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-emerald-500 animate-spin pointer-events-none" aria-hidden="true" />
            ) : (
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
            )}
            <input
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Chercher par question…"
              aria-label="Chercher par question"
              className="w-full pl-7 pr-7 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-white/12 bg-gray-50 dark:bg-white/5 text-gray-800 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 placeholder:text-gray-400 transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => onSearchChange("")}
                aria-label="Effacer la recherche"
                className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 flex items-center justify-center rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 transition-colors"
              >
                <X size={12} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Contextual banners */}
      {onglet === "a_relire" && !loading && !error && total > 0 && (
        <div className="px-5 py-3 flex items-start gap-3 border-b border-amber-100 dark:border-amber-500/15 bg-amber-50/60 dark:bg-amber-400/5">
          <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
              <span className="font-semibold">{nbDocsARelire} document{nbDocsARelire > 1 ? "s" : ""} mis à jour</span>
              {" — "}
              {total} réponse{total > 1 ? "s" : ""} concernée{total > 1 ? "s" : ""} à vérifier{" "}
              <span className="italic">(servies en l'état jusqu'à décision humaine).</span>
            </p>
            <p className="text-xs text-amber-800/60 dark:text-amber-300/50">
              Pour chaque réponse : confirmez si elle reste valide, modifiez-la si besoin, ou retirez-la du service si elle est dépassée.
            </p>
          </div>
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
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {total} réponse{total > 1 ? "s" : ""} canonique{total > 1 ? "s" : ""}
          </span>
          {searchQuery.trim() && (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              · {canoniquesCount} résultat{canoniquesCount !== 1 ? "s" : ""} pour «&nbsp;{searchQuery.trim()}&nbsp;»
            </span>
          )}
        </div>
      )}
    </>
  );
}
