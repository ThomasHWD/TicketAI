import { Trash2, Users, X } from "lucide-react";
import type { Groupe, MembreSummary, UserSummary } from "../../../types/index.tsx";
import { domainColor } from "./utils";
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
  const color = domainColor(groupe.domaine);

  return (
    <div className="glass-card rounded-2xl flex flex-col overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center gap-4 px-6 py-4 border-b border-gray-200/80 dark:border-white/10 shrink-0">
        <div
          className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 text-sm font-bold ${color.bg} ${color.text}`}
        >
          {groupe.domaine.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate leading-5">
            {groupe.nom}
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide ${color.bg} ${color.text}`}
            >
              {groupe.domaine}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {groupe.nb_membres} membre{groupe.nb_membres !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs font-medium transition-colors"
          >
            <Trash2 size={12} />
            Supprimer
          </button>
          <div className="w-px h-4 bg-gray-200 dark:bg-white/10 mx-0.5" />
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Sub-panel split */}
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
    <div className="glass-card rounded-2xl flex flex-col items-center justify-center">
      <div className="text-center max-w-xs">
        <div className="w-12 h-12 rounded-2xl bg-gray-100 dark:bg-white/8 flex items-center justify-center mx-auto mb-4">
          <Users size={22} className="text-gray-300 dark:text-gray-600" />
        </div>
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
          Sélectionnez un groupe
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-600 mt-1.5 leading-relaxed">
          Choisissez un groupe dans la liste<br />pour gérer ses membres.
        </p>
      </div>
    </div>
  );
}
