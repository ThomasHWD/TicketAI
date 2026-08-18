import { AlertTriangle, Archive, BadgeCheck, Search, X } from "lucide-react";
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

function tabCls(active: boolean) {
  return `flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
    active
      ? "border-emerald-500 text-gray-800 dark:text-gray-100"
      : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
  }`;
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
  return (
    <>
      {/* Onglets */}
      <div className="flex items-center gap-1 px-4 border-b border-gray-200 dark:border-white/10" role="tablist">
        <button role="tab" aria-selected={onglet === "canoniques"} onClick={() => onOngletChange("canoniques")} className={tabCls(onglet === "canoniques")}>
          <BadgeCheck size={16} className="text-emerald-500" aria-hidden="true" />
          Canoniques
        </button>
        <button role="tab" aria-selected={onglet === "a_relire"} onClick={() => onOngletChange("a_relire")} className={tabCls(onglet === "a_relire")}>
          <AlertTriangle size={16} className="text-amber-500" aria-hidden="true" />
          À relire
          {nbDocsARelire > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300">
              {nbDocsARelire}
            </span>
          )}
        </button>
        <button role="tab" aria-selected={onglet === "obsoletes"} onClick={() => onOngletChange("obsoletes")} className={tabCls(onglet === "obsoletes")}>
          <Archive size={16} className="text-gray-400" aria-hidden="true" />
          Obsolètes
          {nbObsoletes > 0 && (
            <span className="inline-flex items-center justify-center min-w-[1.25rem] px-1.5 py-0.5 rounded-full text-xs font-medium tabular-nums bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-300">
              {nbObsoletes}
            </span>
          )}
        </button>
      </div>

      {/* Bandeaux contextuels */}
      {onglet === "obsoletes" && (
        <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
          Ces réponses ne sont plus servies : le passage du document sur lequel elles s'appuyaient
          a changé. Leurs validations sont conservées — les restaurer les remet en service telles quelles.
        </p>
      )}
      {onglet === "a_relire" && (
        <p className="px-6 py-3 text-sm text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
          Ces réponses <span className="font-medium">continuent d'être servies</span> : le
          document dont elles sont issues a changé ailleurs que dans les passages qui les
          fondaient. Rien ne prouve qu'elles soient fausses — rien ne prouve l'inverse non plus.
          Lisez ce qui a changé, puis tranchez.
        </p>
      )}
      {onglet === "a_relire" && !loading && !error && total > 0 && (
        <div className="px-6 py-3 flex items-center justify-between border-b border-amber-100 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-400/5">
          <p className="text-sm font-medium text-amber-900 dark:text-amber-300">
            {nbDocsARelire} document{nbDocsARelire > 1 ? "s" : ""} mis à jour
            {" · "}
            {total} réponse{total > 1 ? "s" : ""} à vérifier
          </p>
        </div>
      )}

      {/* Barre de recherche — Canoniques & Obsolètes */}
      {onglet !== "a_relire" && (
        <div className="px-6 py-3 border-b border-gray-200 dark:border-white/10">
          <div className="relative max-w-sm">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
            <input
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Chercher par question…"
              aria-label="Chercher par question"
              className="w-full pl-8 pr-8 py-1.5 text-sm rounded-xl border border-gray-200 dark:border-white/15 bg-white/60 dark:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 placeholder:text-gray-400"
            />
            {searchQuery && (
              <button onClick={() => onSearchChange("")} aria-label="Effacer la recherche" className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Bandeau de stats — Canoniques */}
      {onglet === "canoniques" && !loading && !error && total > 0 && (
        <div className="px-6 py-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-white/10">
          <span>
            {total} réponse{total > 1 ? "s" : ""} canonique{total > 1 ? "s" : ""} active{total > 1 ? "s" : ""}
          </span>
          {searchQuery.trim() && (
            <span className="text-emerald-600 dark:text-emerald-400">
              · {canoniquesCount} résultat{canoniquesCount !== 1 ? "s" : ""} sur cette page
            </span>
          )}
        </div>
      )}
    </>
  );
}
