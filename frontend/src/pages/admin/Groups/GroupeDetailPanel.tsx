import { Trash2, Users, X } from "lucide-react";
import type { Groupe, MembreSummary, UserSummary } from "../../../types/index.tsx";
import CandidatsPanel from "./CandidatsPanel";
import MembresPanel from "./MembresPanel";

type Props = {
  groupe: Groupe;
  candidates: UserSummary[];
  search: string;
  onSearchChange: (v: string) => void;
  onClose: () => void;
  onDelete: () => void;
  onAdd: (userId: string) => void;
  onChef: (membreId: string, isChef: boolean) => void;
  onRetirer: (membre: MembreSummary) => void;
};

export default function GroupeDetailPanel({
  groupe,
  candidates,
  search,
  onSearchChange,
  onClose,
  onDelete,
  onAdd,
  onChef,
  onRetirer,
}: Props) {
  return (
    <div
      className="glass-card rounded-2xl overflow-hidden flex-1 flex flex-col"
      style={{ minHeight: "480px" }}
    >
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-white/10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-600 shrink-0">
            <span className="text-xs font-bold text-white font-mono">
              {groupe.domaine.slice(0, 2)}
            </span>
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {groupe.nom}
            </h3>
            <p className="text-xs text-gray-400 dark:text-gray-500 font-mono">{groupe.domaine}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-200 dark:border-red-400/20 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs font-medium transition-colors"
          >
            <Trash2 size={12} />
            Supprimer
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 divide-x divide-gray-100 dark:divide-white/5">
        <MembresPanel groupe={groupe} onChef={onChef} onRetirer={onRetirer} />
        <CandidatsPanel
          candidates={candidates}
          search={search}
          onSearchChange={onSearchChange}
          onAdd={onAdd}
        />
      </div>
    </div>
  );
}

export function EmptyDetailPanel() {
  return (
    <div
      className="flex-1 flex items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 dark:border-white/10"
      style={{ minHeight: "480px" }}
    >
      <div className="text-center">
        <Users size={28} className="mx-auto text-gray-300 dark:text-gray-600 mb-3" />
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
          Sélectionnez un groupe
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-600 mt-1">pour gérer ses membres</p>
      </div>
    </div>
  );
}
