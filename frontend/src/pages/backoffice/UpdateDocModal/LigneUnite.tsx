import type { UniteChangement } from "../../../types.ts";

const LIBELLE_SENS: Record<UniteChangement["sens"], string> = {
  AJOUT: "Ajouté",
  RETRAIT: "Retiré",
  REECRITURE: "Réécrit",
};

export default function LigneUnite({ unite }: { unite: UniteChangement }) {
  return (
    <li className="space-y-1 border-l-2 border-amber-300 dark:border-amber-500/40 pl-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wider text-amber-900/70 dark:text-amber-200/70">
        {LIBELLE_SENS[unite.sens]}
      </p>
      {unite.extrait_avant && (
        <p className="text-[11px] font-mono leading-relaxed text-gray-500 dark:text-gray-500 line-through decoration-gray-400/60">
          {unite.extrait_avant}
        </p>
      )}
      {unite.extrait_apres && (
        <p className="text-[11px] font-mono leading-relaxed text-gray-700 dark:text-gray-300">
          {unite.extrait_apres}
        </p>
      )}
    </li>
  );
}
