import { Search, UserPlus, X } from "lucide-react";
import type { UserSummary } from "../../../types/index.tsx";
import { displayName, initials } from "./utils";

type Props = {
  candidates: UserSummary[];
  search: string;
  onSearchChange: (v: string) => void;
  onAdd: (userId: string) => void;
};

export default function CandidatsPanel({
  candidates,
  search,
  onSearchChange,
  onAdd,
}: Props) {
  return (
    <div className="flex flex-col w-1/2 min-h-0">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-white/[0.02]">
        <div className="relative">
          <Search
            size={13}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
          />
          <input
            type="text"
            placeholder="Nom ou département…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-8 pr-8 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
          {search && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>
      <div className="overflow-y-auto flex-1 max-h-80">
        {candidates.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <UserPlus size={22} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Aucun résultat.</p>
          </div>
        ) : (
          candidates.map((u) => (
            <div
              key={u.email}
              className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-full bg-gray-100 dark:bg-white/10 flex items-center justify-center shrink-0">
                  <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
                    {initials(u)}
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                    {displayName(u)}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
                    {u.departement ?? u.email}
                  </p>
                </div>
              </div>
              <button
                onClick={() => onAdd(u.id ?? u.email)}
                className="opacity-0 group-hover:opacity-100 flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-400/10 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100 dark:hover:bg-emerald-400/20 text-xs font-medium transition-all shrink-0"
              >
                <UserPlus size={11} />
                Ajouter
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
