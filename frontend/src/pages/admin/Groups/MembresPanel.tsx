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
    <div className="flex flex-col w-1/2 min-h-0">
      <div className="px-5 py-3 border-b border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-white/[0.02]">
        <p className="text-xs py-[10.8px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Membres
          <span className="ml-2 font-normal text-gray-400 dark:text-gray-500 normal-case tracking-normal">
            {groupe.membres.length}
          </span>
        </p>
      </div>
      <div className="overflow-y-auto flex-1">
        {groupe.membres.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Users size={22} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Aucun membre.</p>
            <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">
              Ajoutez des gestionnaires depuis le panneau de droite.
            </p>
          </div>
        ) : (
          groupe.membres.map((m: MembreSummary) => (
            <div
              key={m.email}
              className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors group"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                    m.is_chef ? "bg-amber-100 dark:bg-amber-400/15" : "bg-gray-100 dark:bg-white/10"
                  }`}
                >
                  <span
                    className={`text-xs font-semibold ${
                      m.is_chef
                        ? "text-amber-700 dark:text-amber-400"
                        : "text-gray-600 dark:text-gray-300"
                    }`}
                  >
                    {initials(m)}
                  </span>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                      {displayName(m)}
                    </p>
                    {m.is_chef && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 text-xs font-medium shrink-0">
                        <Crown size={9} />
                        Chef
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
                    {m.departement ?? m.email}
                  </p>
                </div>
              </div>
              <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all shrink-0">
                <button
                  onClick={() => onChef(m.id, !m.is_chef)}
                  title={m.is_chef ? "Retirer le rôle de chef" : "Désigner comme chef"}
                  className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-colors ${
                    m.is_chef
                      ? "text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-400/10"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10"
                  }`}
                >
                  <Crown size={11} />
                  {m.is_chef ? "Rétrograder" : "Chef"}
                </button>
                <button
                  onClick={() => onRetirer(m)}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs transition-colors"
                >
                  <UserMinus size={11} />
                  Retirer
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
