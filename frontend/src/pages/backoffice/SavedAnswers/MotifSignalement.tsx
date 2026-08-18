import { AlertTriangle, Info } from "lucide-react";
import { RAISONS, estRaisonDeGroupe } from "./utils";
import type { ReponseSignalee } from "../../../types";

export default function MotifSignalement({ reponse }: { reponse: ReponseSignalee }) {
  const raison = reponse.a_relire_raison;
  const generique = raison && !estRaisonDeGroupe(raison) ? RAISONS[raison] : null;
  const message = reponse.analyse_justification ?? generique;
  if (!message) return null;

  const attention = raison === "CONTREDITE_PROBABLE";
  return (
    <div className={`flex items-start gap-1.5 text-xs leading-relaxed ${
      attention
        ? "text-amber-700 dark:text-amber-300"
        : "text-gray-500 dark:text-gray-400"
    }`}>
      {attention
        ? <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        : <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
      }
      <span>{message}</span>
    </div>
  );
}
