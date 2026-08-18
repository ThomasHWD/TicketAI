import { AlertTriangle } from "lucide-react";
import { RAISONS, estRaisonDeGroupe } from "./utils";
import type { ReponseSignalee } from "../../../types";

export default function MotifSignalement({ reponse }: { reponse: ReponseSignalee }) {
  const raison = reponse.a_relire_raison;
  const generique = raison && !estRaisonDeGroupe(raison) ? RAISONS[raison] : null;
  const message = reponse.analyse_justification ?? generique;
  if (!message) return null;

  const attention = raison === "CONTREDITE_PROBABLE";
  return (
    <p
      className={`flex items-start gap-1.5 text-xs ${
        attention
          ? "text-amber-700 dark:text-amber-300"
          : "text-gray-500 dark:text-gray-400"
      }`}
    >
      <AlertTriangle size={13} className="mt-0.5 shrink-0" />
      <span>{message}</span>
    </p>
  );
}
