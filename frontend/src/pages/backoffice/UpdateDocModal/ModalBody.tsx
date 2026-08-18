import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import FileDropzone from "../../../components/ui/FileDropzone";
import type { UpdateImpact } from "../../../types";
import EcranImpact from "./EcranImpact";
import type { Etape } from "./index";

interface ModalBodyProps {
  etape: Etape;
  file: File | null;
  fileError: string | null;
  description: string | undefined;
  impact: UpdateImpact | null;
  erreur: string | null;
  restauration: boolean;
  nbAAnalyser: number;
  onClose: () => void;
  onFilePick: (f: File) => void;
  onDescriptionChange: (v: string) => void;
}

export default function ModalBody({
  etape,
  file,
  fileError,
  description,
  impact,
  erreur,
  restauration,
  nbAAnalyser,
  onClose,
  onFilePick,
  onDescriptionChange,
}: ModalBodyProps) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
      {etape === "pick" && (
        <>
          <FileDropzone file={file} error={fileError} onPick={onFilePick} />
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
            <input
              type="text"
              value={description ?? ""}
              onChange={(e) => onDescriptionChange(e.target.value)}
              placeholder="Résumez brièvement le contenu du document…"
              className="w-full px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40"
            />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Le document conservera son identifiant ; l'ancienne version sera archivée et restera téléchargeable.
          </p>
        </>
      )}

      {etape === "analyse" && (
        <div className="flex flex-col items-center gap-3 py-12">
          <Loader2 size={22} className="animate-spin text-gray-400" />
          <p className="text-sm text-gray-500 dark:text-gray-400">Comparaison avec la version en ligne…</p>
        </div>
      )}

      {(etape === "impact" || etape === "submitting") && impact && (
        <EcranImpact impact={impact} />
      )}

      {etape === "done" && (
        <div className="flex flex-col items-center gap-4 py-10 text-center">
          <CheckCircle2 size={40} className="text-emerald-500" />
          <div className="space-y-1">
            <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              {restauration ? "Restauration lancée" : "Mise à jour lancée"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Le document sera ré-indexé en arrière-plan.</p>
          </div>
          {nbAAnalyser > 0 && (
            <>
              <p className="text-xs text-gray-500 dark:text-gray-400 max-w-xs">
                {nbAAnalyser} réponse{nbAAnalyser > 1 ? "s" : ""}{" "}
                {nbAAnalyser > 1 ? "sont" : "est"} en cours d'analyse. Celles que le changement
                contredit basculeront dans Obsolètes ; les cas douteux seront déposés dans À
                relire, avec leur justification.
              </p>
              <a
                href="/reponses-enregistrees?onglet=a_relire"
                onClick={onClose}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium transition-colors"
              >
                <AlertTriangle size={15} />
                Suivre l'analyse
              </a>
            </>
          )}
        </div>
      )}

      {etape === "error" && (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm font-medium text-red-700 dark:text-red-400">
            <XCircle size={16} />
            {restauration ? "Restauration impossible" : "Mise à jour impossible"}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-400">{erreur}</p>
        </div>
      )}
    </div>
  );
}
