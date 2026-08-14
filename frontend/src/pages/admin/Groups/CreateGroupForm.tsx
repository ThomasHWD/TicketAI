import { FolderOpen, Loader2 } from "lucide-react";
import DomaineCombobox from "./DomaineCombobox";

type Props = {
  form: { nom: string; domaine: string };
  onChange: (form: { nom: string; domaine: string }) => void;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
  isPending: boolean;
  error: string | null;
  domaines: string[];
};

export default function CreateGroupForm({
  form,
  onChange,
  onSubmit,
  onCancel,
  isPending,
  error,
  domaines,
}: Props) {
  return (
    <div className="glass-card rounded-2xl">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200 dark:border-white/10 rounded-t-2xl">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-400/15 shrink-0">
          <FolderOpen size={15} className="text-emerald-700 dark:text-emerald-400" />
        </div>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Nouveau groupe</h2>
      </div>
      <form onSubmit={onSubmit} className="px-6 py-5 flex flex-wrap gap-4 items-end">
        <div className="flex flex-col gap-1.5 flex-1 min-w-48">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Nom du groupe
          </label>
          <input
            required
            value={form.nom}
            onChange={(e) => onChange({ ...form, nom: e.target.value })}
            placeholder="ex : Ressources humaines"
            className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        <div className="flex flex-col gap-1.5 w-44">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Domaine
          </label>
          <DomaineCombobox
            value={form.domaine}
            onChange={(v) => onChange({ ...form, domaine: v })}
            existing={domaines}
          />
        </div>
        <div className="flex flex-col gap-2">
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={isPending}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
            >
              {isPending ? <Loader2 size={14} className="animate-spin" /> : "Créer"}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 rounded-lg border border-gray-200 dark:border-white/10 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
            >
              Annuler
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
