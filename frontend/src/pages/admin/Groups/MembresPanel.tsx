import { Crown, UserMinus, Users } from "lucide-react";
import type { Groupe, MembreSummary } from "../../../types/index.tsx";
import { displayName, initials } from "./utils";

type Props = {
  groupe: Groupe;
  onChef: (membreId: string, isChef: boolean) => void;
  onRetirer: (membre: MembreSummary) => void;
};

export default function MembresPanel({ groupe, onChef, onRetirer }: Props) {
  return (
    <div className="flex flex-col w-1/2 min-h-0 overflow-hidden">
      {/* Sub-header */}
      <div className="px-5 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.015] shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
            Membres actuels
          </span>
          {groupe.membres.length > 0 && (
            <span className="text-[11px] tabular-nums text-gray-400 dark:text-gray-500">
              {groupe.membres.length}
            </span>
          )}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {groupe.membres.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 px-5 text-center">
            <Users size={20} className="text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Aucun membre</p>
            <p className="text-xs text-gray-400 dark:text-gray-600 mt-1 leading-relaxed">
              Ajoutez des gestionnaires<br />depuis le panneau de droite.
            </p>
          </div>
        ) : (
          groupe.membres.map((m: MembreSummary) => (
            <div
              key={m.email}
              className="flex items-center gap-3 px-5 py-2.5 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
            >
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-semibold ${
                  m.is_chef
                    ? "bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400"
                    : "bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300"
                }`}
              >
                {initials(m)}
              </div>

              {/* Name + meta */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
                    {displayName(m)}
                  </p>
                  {m.is_chef && (
                    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-400/10 border border-amber-200/60 dark:border-amber-400/20 text-amber-600 dark:text-amber-400 text-[10px] font-semibold shrink-0 leading-none">
                      <Crown size={8} strokeWidth={2.5} />
                      Chef
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 truncate leading-snug mt-0.5">
                  {m.departement ?? m.email}
                </p>
              </div>

              {/* Hover actions — fixed width slot so rows don't jump on reveal */}
              <div className="w-[52px] flex items-center justify-end gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => onChef(m.id, !m.is_chef)}
                  title={m.is_chef ? "Retirer le rôle de chef" : "Désigner comme chef d'équipe"}
                  className={`p-1.5 rounded-lg transition-colors ${
                    m.is_chef
                      ? "text-amber-500 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-400/10"
                      : "text-gray-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-400/10"
                  }`}
                >
                  <Crown size={13} strokeWidth={m.is_chef ? 2.5 : 1.5} />
                </button>
                <button
                  onClick={() => onRetirer(m)}
                  title="Retirer du groupe"
                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-400/10 transition-colors"
                >
                  <UserMinus size={13} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
