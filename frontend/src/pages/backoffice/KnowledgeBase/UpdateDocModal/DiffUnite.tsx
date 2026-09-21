import type { UniteChangement } from "../../../../types";

const SENS: Record<UniteChangement["sens"], { label: string; classes: string }> = {
  AJOUT: {
    label: "Ajouté",
    classes: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  },
  RETRAIT: {
    label: "Retiré",
    classes: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  },
  REECRITURE: {
    label: "Réécrit",
    classes: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  },
};

/** Before↔after diff unit. Both sides shown together because the pair makes the change judgeable; text nodes without `<span>` wrappers because tests query by text. */
export default function DiffUnite({ unite }: { unite: UniteChangement }) {
  const sens = SENS[unite.sens];

  return (
    <li className="overflow-hidden rounded-lg border border-gray-200 dark:border-white/10">
      <div className="border-b border-gray-100 bg-gray-50/80 px-2.5 py-1.5 dark:border-white/8 dark:bg-white/[0.04]">
        <span
          className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${sens.classes}`}
        >
          {sens.label}
        </span>
      </div>

      <div className="divide-y divide-gray-100 font-mono text-[11px] leading-relaxed dark:divide-white/8">
        {unite.extrait_avant && (
          <div className="flex gap-2 bg-red-50/60 px-2.5 py-1.5 text-red-900 dark:bg-red-500/10 dark:text-red-200/90">
            <span aria-hidden="true" className="select-none text-red-400 dark:text-red-500/60">
              −
            </span>
            {unite.extrait_avant}
          </div>
        )}
        {unite.extrait_apres && (
          <div className="flex gap-2 bg-emerald-50/60 px-2.5 py-1.5 text-emerald-900 dark:bg-emerald-500/10 dark:text-emerald-200/90">
            <span aria-hidden="true" className="select-none text-emerald-500 dark:text-emerald-500/60">
              +
            </span>
            {unite.extrait_apres}
          </div>
        )}
      </div>
    </li>
  );
}
