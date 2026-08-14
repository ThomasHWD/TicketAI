import { ChevronRight, Loader2, Users } from "lucide-react";
import type { Groupe } from "../../../types/index.tsx";

type Props = {
  groupes: Groupe[];
  isLoading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export default function GroupList({ groupes, isLoading, selectedId, onSelect }: Props) {
  return (
    <div className="glass-card rounded-2xl overflow-hidden w-68 shrink-0" style={{ width: "17rem" }}>
      <div className="px-4 py-3.5 border-b border-gray-200 dark:border-white/10">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Groupes
          </span>
          {groupes.length > 0 && (
            <span className="text-xs font-medium text-gray-400 dark:text-gray-500 tabular-nums">
              {groupes.length}
            </span>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="px-5 py-10 text-center">
          <Loader2 size={18} className="animate-spin mx-auto text-gray-300 dark:text-gray-600" />
        </div>
      ) : groupes.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <Users size={24} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
          <p className="text-sm text-gray-500 dark:text-gray-400">Aucun groupe créé.</p>
          <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">
            Cliquez sur « Nouveau groupe ».
          </p>
        </div>
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-white/5">
          {groupes.map((g) => {
            const isSelected = selectedId === g.id;
            return (
              <button
                key={g.id}
                onClick={() => onSelect(g.id)}
                className={`w-full text-left px-4 py-3 transition-colors flex items-center gap-3 group ${
                  isSelected
                    ? "bg-emerald-50 dark:bg-emerald-400/10"
                    : "hover:bg-gray-50 dark:hover:bg-white/5"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold font-mono transition-colors ${
                    isSelected
                      ? "bg-emerald-600 text-white"
                      : "bg-gray-100 dark:bg-white/10 text-gray-500 dark:text-gray-400"
                  }`}
                >
                  {g.domaine.slice(0, 2)}
                </div>
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-sm font-medium truncate transition-colors ${
                      isSelected
                        ? "text-emerald-800 dark:text-emerald-300"
                        : "text-gray-800 dark:text-gray-100"
                    }`}
                  >
                    {g.nom}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    {g.nb_membres} membre{g.nb_membres !== 1 ? "s" : ""}
                  </p>
                </div>
                <ChevronRight
                  size={14}
                  className={`shrink-0 transition-all ${
                    isSelected
                      ? "text-emerald-500 opacity-100"
                      : "text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100"
                  }`}
                />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
