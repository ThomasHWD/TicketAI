import { Loader2 } from "lucide-react";
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
    <form
      onSubmit={onSubmit}
      className="px-4 py-4 flex flex-col gap-3 bg-gray-50/60 dark:bg-white/[0.02]"
    >
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="create-group-nom"
          className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
        >
          Nom du groupe
        </label>
        <input
          id="create-group-nom"
          required
          autoFocus
          value={form.nom}
          onChange={(e) => onChange({ ...form, nom: e.target.value })}
          placeholder="ex : Ressources humaines"
          className="px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="create-group-domaine"
          className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400"
        >
          Domaine
        </label>
        <DomaineCombobox
          id="create-group-domaine"
          value={form.domaine}
          onChange={(v) => onChange({ ...form, domaine: v })}
          existing={domaines}
        />
      </div>
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isPending}
          className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-md bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
        >
          {isPending ? <Loader2 size={13} className="animate-spin" /> : "Créer le groupe"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-2 rounded-md border border-gray-200 dark:border-white/10 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 transition-colors"
        >
          Annuler
        </button>
      </div>
    </form>
  );
}
