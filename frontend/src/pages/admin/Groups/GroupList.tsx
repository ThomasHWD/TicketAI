import { ChevronRight, Loader2, Plus, Users } from "lucide-react";
import type { Groupe } from "../../../types/index.tsx";
import { domainColor } from "./utils";
import CreateGroupForm from "./CreateGroupForm";

type FormState = { nom: string; domaine: string };

type Props = {
  groupes: Groupe[];
  isLoading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  showCreate: boolean;
  onToggleCreate: () => void;
  form: FormState;
  onFormChange: (f: FormState) => void;
  onFormSubmit: (e: React.FormEvent) => void;
  onCancelCreate: () => void;
  isCreating: boolean;
  createError: string | null;
  domaines: string[];
};

export default function GroupList({
  groupes,
  isLoading,
  selectedId,
  onSelect,
  showCreate,
  onToggleCreate,
  form,
  onFormChange,
  onFormSubmit,
  onCancelCreate,
  isCreating,
  createError,
  domaines,
}: Props) {
  return (
    <div className="glass-card rounded-2xl flex flex-col overflow-hidden">
      {/* Panel header */}
      <div className="px-4 py-3 border-b border-gray-200/80 dark:border-white/10 shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
            Groupes
            {groupes.length > 0 && (
              <span className="ml-2 font-medium normal-case tracking-normal text-gray-500 dark:text-gray-400">
                {groupes.length}
              </span>
            )}
          </span>
          <button
            onClick={onToggleCreate}
            title={showCreate ? "Annuler" : "Nouveau groupe"}
            className={`p-1 rounded-md transition-colors ${
              showCreate
                ? "text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/8"
                : "text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-400/10"
            }`}
          >
            <Plus
              size={14}
              className={`transition-transform duration-150 ${showCreate ? "rotate-45" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Inline create form */}
      {showCreate && (
        <div className="border-b border-gray-200/80 dark:border-white/10 shrink-0">
          <CreateGroupForm
            form={form}
            onChange={onFormChange}
            onSubmit={onFormSubmit}
            onCancel={onCancelCreate}
            isPending={isCreating}
            error={createError}
            domaines={domaines}
          />
        </div>
      )}

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={16} className="animate-spin text-gray-300 dark:text-gray-600" />
          </div>
        ) : groupes.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14 px-6 text-center">
            <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-white/8 flex items-center justify-center mb-3">
              <Users size={18} className="text-gray-400 dark:text-gray-600" />
            </div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Aucun groupe</p>
            <p className="text-xs text-gray-400 dark:text-gray-600 mt-1 leading-relaxed">
              Utilisez le <Plus size={10} className="inline" /> ci-dessus pour en créer un.
            </p>
          </div>
        ) : (
          <div className="py-1">
            {groupes.map((g) => {
              const isSelected = selectedId === g.id;
              const color = domainColor(g.domaine);
              return (
                <button
                  key={g.id}
                  onClick={() => onSelect(g.id)}
                  className={`relative w-full text-left px-3 py-2.5 transition-colors flex items-center gap-3 group ${
                    isSelected
                      ? "bg-gray-100/80 dark:bg-white/8"
                      : "hover:bg-gray-50 dark:hover:bg-white/5"
                  }`}
                >
                  {/* Active left pip */}
                  {isSelected && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r-full bg-emerald-500" />
                  )}

                  {/* Domain avatar */}
                  <div
                    className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold ${color.bg} ${color.text}`}
                  >
                    {g.domaine.slice(0, 2).toUpperCase()}
                  </div>

                  {/* Text */}
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-sm font-medium truncate ${
                        isSelected
                          ? "text-gray-900 dark:text-gray-100"
                          : "text-gray-700 dark:text-gray-200"
                      }`}
                    >
                      {g.nom}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {g.nb_membres} membre{g.nb_membres !== 1 ? "s" : ""}
                    </p>
                  </div>

                  {/* Chevron */}
                  <ChevronRight
                    size={13}
                    className={`shrink-0 transition-opacity ${
                      isSelected
                        ? "text-gray-500 dark:text-gray-400 opacity-100"
                        : "text-gray-300 dark:text-gray-600 opacity-0 group-hover:opacity-100"
                    }`}
                  />
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
