import { Loader2, Search, UserPlus, X } from "lucide-react";
import type { UserSummary } from "../../../types/index.tsx";
import { displayName, initials } from "./utils";

type Props = {
  candidates: UserSummary[];
  search: string;
  onSearchChange: (v: string) => void;
  onAdd: (userId: string) => void;
  pendingAddId: string | null;
};

export default function CandidatsPanel({ candidates, search, onSearchChange, onAdd, pendingAddId }: Props) {
  return (
    <div className="flex flex-col w-full md:w-1/2 min-h-0 overflow-hidden">
      {/* Sub-header with search */}
      <div className="px-4 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.015] shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground block mb-2.5">
          Ajouter des gestionnaires
        </span>
        <div className="relative">
          <Search
            size={12}
            aria-hidden="true"
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-subtle pointer-events-none"
          />
          <input
            type="text"
            placeholder="Nom ou département…"
            aria-label="Rechercher un gestionnaire à ajouter"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-7 pr-7 py-1.5 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs text-gray-900 dark:text-gray-100 placeholder:text-muted-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
          />
          {search && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              aria-label="Effacer la recherche"
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              <X size={11} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* Candidates list */}
      <div className="flex-1 overflow-y-auto">
        {candidates.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 px-5 text-center">
            <UserPlus size={20} className="text-subtle mb-3" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">
              {search ? "Aucun résultat" : "Tous les gestionnaires sont membres"}
            </p>
            {search && (
              <button
                onClick={() => onSearchChange("")}
                className="mt-2 text-xs text-emerald-700 dark:text-emerald-400 hover:underline transition-colors"
              >
                Effacer la recherche
              </button>
            )}
          </div>
        ) : (
          candidates.map((u) => {
            const isPending = pendingAddId === (u.id ?? u.email);
            return (
              <div
                key={u.id ?? u.email}
                className="flex items-center gap-3 px-5 py-2.5 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
              >
                <div
                  aria-hidden="true"
                  className="w-7 h-7 rounded-full bg-gray-100 dark:bg-white/10 flex items-center justify-center shrink-0"
                >
                  <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
                    {initials(u)}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
                    {displayName(u)}
                  </p>
                  <p className="text-xs text-muted-foreground truncate leading-snug mt-0.5">
                    {u.departement ?? u.email}
                  </p>
                </div>
                {/* Fixed slot — no layout jump on hover */}
                <div className="w-[68px] flex items-center justify-end shrink-0">
                  {isPending ? (
                    <span className="flex items-center gap-1 px-2.5 py-1 text-xs text-emerald-700 dark:text-emerald-400">
                      <Loader2 size={11} className="animate-spin" aria-hidden="true" />
                      Ajout…
                    </span>
                  ) : (
                    <button
                      onClick={() => onAdd(u.id ?? u.email)}
                      aria-label={`Ajouter ${displayName(u)} au groupe`}
                      disabled={pendingAddId !== null}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-400/20 disabled:opacity-30 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
                    >
                      <UserPlus size={11} aria-hidden="true" />
                      Ajouter
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
