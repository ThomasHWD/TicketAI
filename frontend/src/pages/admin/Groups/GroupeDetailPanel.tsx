import { AlertCircle, Check, Trash2, Users, X } from "lucide-react";
import type {
  Groupe,
  MembreSummary,
  UserSummary,
} from "../../../types/index.tsx";
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
  pendingAddId: string | null;
  pendingChefId: string | null;
  memberError: string | null;
  onClearMemberError: () => void;
  successMsg: string | null;
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
  pendingAddId,
  pendingChefId,
  memberError,
  onClearMemberError,
  successMsg,
}: Props) {
  const color = domainColor(groupe.domaine);

  return (
    <div className="glass-card rounded-2xl flex flex-col overflow-hidden">
      {/* Panel header — close button anchored top-right, separated from destructive action */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200/80 dark:border-white/10 shrink-0">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate leading-5">
            {groupe.nom}
          </h3>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${color.bg} ${color.text}`}
            >
              {groupe.domaine}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {groupe.nb_membres} membre{groupe.nb_membres !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        {/* Bouton Supprimer */}
        <button
          onClick={onDelete}
          aria-label={`Supprimer le groupe ${groupe.nom}`}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-400/10 text-xs font-medium transition-colors shrink-0"
        >
          <Trash2 size={12} aria-hidden="true" />
          Supprimer
        </button>

        {/* Croix de fermeture */}
        <button
          onClick={onClose}
          aria-label="Fermer le panneau"
          className="p-2 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors shrink-0"
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>

      {/* Success banner — auto-dismissed from parent */}
      {successMsg && (
        <div
          role="status"
          className="px-5 py-2 bg-emerald-50 dark:bg-emerald-400/10 border-b border-emerald-100 dark:border-emerald-400/20 flex items-center gap-2 shrink-0"
        >
          <Check
            size={13}
            className="text-emerald-600 dark:text-emerald-400 shrink-0"
            aria-hidden="true"
          />
          <p className="text-xs text-emerald-700 dark:text-emerald-400 flex-1">
            {successMsg}
          </p>
        </div>
      )}

      {/* Error banner */}
      {memberError && (
        <div className="px-5 py-2 bg-red-50 dark:bg-red-400/10 border-b border-red-100 dark:border-red-400/20 flex items-center gap-2 shrink-0">
          <AlertCircle
            size={13}
            className="text-red-500 dark:text-red-400 shrink-0"
            aria-hidden="true"
          />
          <p
            className="text-xs text-red-700 dark:text-red-400 flex-1"
            role="alert"
          >
            {memberError}
          </p>
          <button
            onClick={onClearMemberError}
            aria-label="Fermer l'erreur"
            className="p-0.5 text-red-400 hover:text-red-600 dark:hover:text-red-300 transition-colors"
          >
            <X size={11} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Sub-panel split */}
      <div className="flex flex-col md:flex-row flex-1 min-h-0 divide-y divide-x-0 md:divide-y-0 md:divide-x divide-gray-100 dark:divide-white/5">
        <MembresPanel
          groupe={groupe}
          pendingChefId={pendingChefId}
          onChef={onChef}
          onRetirer={onRetirer}
        />
        <CandidatsPanel
          candidates={candidates}
          search={search}
          onSearchChange={onSearchChange}
          onAdd={onAdd}
          pendingAddId={pendingAddId}
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
          <Users
            size={22}
            className="text-gray-300 dark:text-gray-600"
            aria-hidden="true"
          />
        </div>
        <p className="text-sm font-medium text-gray-500 dark:text-gray-400">
          Sélectionnez un groupe
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-600 mt-1.5 leading-relaxed">
          Choisissez un groupe dans la liste
          <br />
          pour gérer ses membres.
        </p>
      </div>
    </div>
  );
}
