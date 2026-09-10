import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Archive, BadgeCheck, Check, ChevronDown, Loader2, Search, SlidersHorizontal, Tag, X } from "lucide-react";
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
  tag: string | undefined;
  tagsDisponibles: string[];
  onOngletChange: (o: Onglet) => void;
  onSearchChange: (q: string) => void;
  onDomaine: (d: string | undefined) => void;
  onTag: (t: string | undefined) => void;
}

function Tab({
  id, active, onClick, Icon, iconActiveClass = "text-gray-700 dark:text-gray-200",
  label, badge, badgeAriaLabel, badgeVariant = "neutral", tabIndex = 0, onKeyDown, controls,
}: {
  id: string; active: boolean; onClick: () => void; Icon: LucideIcon;
  iconActiveClass?: string; label: string; badge?: number; badgeAriaLabel?: string;
  badgeVariant?: "amber" | "neutral"; tabIndex?: number;
  onKeyDown?: (e: React.KeyboardEvent<HTMLButtonElement>) => void; controls: string;
}) {
  return (
    <button
      id={id} role="tab" aria-selected={active} aria-controls={controls}
      tabIndex={tabIndex} onClick={onClick} onKeyDown={onKeyDown}
      className={`relative flex items-center gap-2 px-3 py-2.5 text-sm font-medium transition-colors whitespace-nowrap rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 ${
        active ? "text-gray-900 dark:text-gray-50" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
      }`}
    >
      <Icon size={15} className={active ? iconActiveClass : "text-gray-500 dark:text-gray-400"} aria-hidden="true" />
      {label}
      {badge !== undefined && badge > 0 && (
        <span aria-label={badgeAriaLabel} className={`inline-flex items-center justify-center min-w-[1.25rem] px-1.5 rounded-full text-xs font-semibold tabular-nums ${
          badgeVariant === "amber"
            ? "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300"
            : "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300"
        }`}>
          {badge}
        </span>
      )}
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-emerald-500 rounded-full" aria-hidden="true" />}
    </button>
  );
}

function FilterPill({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 ${
        active
          ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
          : "text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/8 dark:hover:text-gray-200"
      }`}
    >
      {label}
    </button>
  );
}

function TagCombobox({
  tags, value, onChange,
}: { tags: string[]; value: string | undefined; onChange: (t: string | undefined) => void }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const showSearch = tags.length > 5;
  const filtered = search.trim()
    ? tags.filter((t) => t.toLowerCase().includes(search.toLowerCase()))
    : tags;

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setSearch("");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  function select(t: string | undefined) {
    onChange(t);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-haspopup="listbox"
          className={`flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60 ${
            value
              ? "bg-violet-600 text-white dark:bg-violet-500"
              : "text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-white/8 dark:hover:text-gray-200"
          }`}
        >
          <Tag size={10} aria-hidden="true" />
          <span className="max-w-[12rem] truncate">{value ?? "Tag"}</span>
          {!value && <ChevronDown size={10} aria-hidden="true" className="opacity-50 shrink-0" />}
        </button>
        {value && (
          <button
            type="button"
            onClick={() => select(undefined)}
            aria-label="Effacer le filtre tag"
            className="flex items-center justify-center w-5 h-5 rounded text-violet-400 hover:text-violet-700 dark:hover:text-violet-300 transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-500/60"
          >
            <X size={10} aria-hidden="true" />
          </button>
        )}
      </div>

      {open && (
        <div
          className="absolute left-0 top-full mt-1.5 z-30 w-52 rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 shadow-lg overflow-hidden"
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
        >
          {showSearch && (
            <div className="p-2 border-b border-gray-100 dark:border-white/8">
              <div className="relative">
                <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
                <input
                  ref={inputRef}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Chercher un tag…"
                  className="w-full pl-6 pr-2 py-1 text-xs rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/5 text-gray-800 dark:text-gray-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-violet-500/60 placeholder:text-gray-400"
                />
              </div>
            </div>
          )}
          <ul role="listbox" aria-label="Tags disponibles" className="max-h-52 overflow-y-auto py-1">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-xs text-gray-400 dark:text-gray-500 text-center">
                Aucun résultat
              </li>
            ) : (
              filtered.map((t) => (
                <li key={t} role="option" aria-selected={t === value}>
                  <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); select(t === value ? undefined : t); }}
                    className={`w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs text-left transition-colors ${
                      t === value
                        ? "text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-500/10 font-medium"
                        : "text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
                    }`}
                  >
                    <span className="truncate">{t}</span>
                    {t === value && <Check size={10} aria-hidden="true" className="shrink-0" />}
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

const ONGLETS: Onglet[] = ["canoniques", "a_relire", "obsoletes"];

export default function SavedAnswersHeader({
  onglet, nbDocsARelire, nbObsoletes, searchQuery, loading, isFetching, error, total,
  canoniquesCount, domaines, domaine, tag, tagsDisponibles, onOngletChange, onSearchChange, onDomaine, onTag,
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

  const hasDomainFilter = domaines.length > 1;
  const hasTagFilter = tagsDisponibles.length > 0;
  const showFilterBar = onglet === "canoniques" && (hasDomainFilter || hasTagFilter);
  const filtresActifs = domaine !== undefined || tag !== undefined;

  return (
    <>
      {/* Ligne 1 — onglets + recherche */}
      <div className="flex items-center justify-between gap-4 px-4 border-b border-gray-100 dark:border-white/8">
        <div
          ref={tablistRef}
          className="flex items-center gap-0.5"
          role="tablist"
          aria-label="Onglets — réponses enregistrées"
        >
          <Tab
            id="tab-canoniques" controls="panel-canoniques"
            active={onglet === "canoniques"} onClick={() => onOngletChange("canoniques")}
            Icon={BadgeCheck} iconActiveClass="text-emerald-500" label="Canoniques"
            tabIndex={onglet === "canoniques" ? 0 : -1} onKeyDown={(e) => handleTabKeyDown(e, 0)}
          />
          <Tab
            id="tab-a_relire" controls="panel-a_relire"
            active={onglet === "a_relire"} onClick={() => onOngletChange("a_relire")}
            Icon={AlertTriangle} iconActiveClass="text-amber-500" label="À relire"
            badge={nbDocsARelire}
            badgeAriaLabel={`${nbDocsARelire} document${nbDocsARelire > 1 ? "s" : ""} à relire`}
            badgeVariant="amber"
            tabIndex={onglet === "a_relire" ? 0 : -1} onKeyDown={(e) => handleTabKeyDown(e, 1)}
          />
          <Tab
            id="tab-obsoletes" controls="panel-obsoletes"
            active={onglet === "obsoletes"} onClick={() => onOngletChange("obsoletes")}
            Icon={Archive} label="Obsolètes"
            badge={nbObsoletes}
            badgeAriaLabel={`${nbObsoletes} réponse${nbObsoletes > 1 ? "s" : ""} obsolète${nbObsoletes > 1 ? "s" : ""}`}
            tabIndex={onglet === "obsoletes" ? 0 : -1} onKeyDown={(e) => handleTabKeyDown(e, 2)}
          />
        </div>

        <div className="py-2 w-56 shrink-0">
          <div className="relative">
            {searching
              ? <Loader2 size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-emerald-500 animate-spin pointer-events-none" aria-hidden="true" />
              : <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
            }
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

      {/* Ligne 2 — barre de filtres (canoniques uniquement) */}
      {showFilterBar && (
        <div
          className="px-5 py-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-gray-100 dark:border-white/8 bg-gray-50/40 dark:bg-white/[0.01]"
          aria-label="Filtres"
        >
          <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 shrink-0">
            <SlidersHorizontal size={12} aria-hidden="true" />
            Filtres
          </div>

          {hasDomainFilter && (
            <div className="flex items-center gap-1.5" role="group" aria-label="Filtrer par domaine">
              <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">Domaine</span>
              <div className="flex items-center gap-1">
                <FilterPill label="Tous" active={domaine === undefined} onClick={() => onDomaine(undefined)} />
                {domaines.map((d) => (
                  <FilterPill key={d} label={d} active={domaine === d} onClick={() => onDomaine(d)} />
                ))}
              </div>
            </div>
          )}

          {hasTagFilter && (
            <div className="flex items-center gap-1.5" role="group" aria-label="Filtrer par tag">
              <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">Tag</span>
              <TagCombobox tags={tagsDisponibles} value={tag} onChange={onTag} />
            </div>
          )}

          {filtresActifs && (
            <button
              type="button"
              onClick={() => { onDomaine(undefined); onTag(undefined); }}
              className="ml-auto flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60 rounded-sm shrink-0"
            >
              <X size={11} aria-hidden="true" />
              Réinitialiser
            </button>
          )}
        </div>
      )}

      {/* Bandeaux contextuels */}
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

      {/* Barre de stats (canoniques) */}
      {onglet === "canoniques" && !loading && !error && total > 0 && (
        <div className="px-5 py-2.5 flex items-center gap-2 border-b border-gray-100 dark:border-white/8">
          <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
            {total} réponse{total > 1 ? "s" : ""} canonique{total > 1 ? "s" : ""}
          </span>
          {tag && (
            <>
              <span aria-hidden="true" className="text-gray-200 dark:text-gray-700">·</span>
              <span className="inline-flex items-center gap-1 text-xs text-violet-600 dark:text-violet-400 font-medium">
                tag : {tag}
              </span>
            </>
          )}
          {searchQuery.trim() && (
            <>
              <span aria-hidden="true" className="text-gray-200 dark:text-gray-700">·</span>
              <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                {canoniquesCount} résultat{canoniquesCount !== 1 ? "s" : ""} pour «&nbsp;{searchQuery.trim()}&nbsp;»
              </span>
            </>
          )}
        </div>
      )}
    </>
  );
}
