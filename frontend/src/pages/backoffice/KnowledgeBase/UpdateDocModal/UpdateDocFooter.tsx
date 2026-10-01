import { Loader2, RefreshCw, RotateCcw } from "lucide-react";
import type { Etape } from "../../../../hooks/useUpdateDocModal";
import type { UpdateImpact } from "../../../../types";

const BTN_SECONDAIRE =
  "flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5";
const BTN_PRIMAIRE =
  "flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100";

interface UpdateDocFooterProps {
  etape: Etape;
  file: File | null;
  description: string | undefined;
  enCours: boolean;
  restauration: boolean;
  impact: UpdateImpact | null;
  onClose: () => void;
  onRevenir: () => void;
  onAnalyse: () => void;
  onConfirmer: () => void;
  onFermerErreur: () => void;
}

export function UpdateDocFooter({
  etape, file, description, enCours, restauration, impact,
  onClose, onRevenir, onAnalyse, onConfirmer, onFermerErreur,
}: UpdateDocFooterProps) {
  return (
    <div className="flex gap-2">
      {etape === "pick" && (
        <>
          <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>Annuler</button>
          <div className="flex-1">
            <button
              type="button"
              disabled={!file || !description?.trim()}
              onClick={onAnalyse}
              className={BTN_PRIMAIRE}
            >
              <RefreshCw size={14} />
              Analyser l'impact
            </button>
          </div>
        </>
      )}

      {(etape === "impact" || etape === "submitting") && impact && (
        <>
          <button type="button" onClick={restauration ? onClose : onRevenir} disabled={enCours} className={BTN_SECONDAIRE}>
            {restauration ? "Annuler" : "Retour"}
          </button>
          <div className="flex flex-1 flex-col gap-1">
            <button type="button" onClick={onConfirmer} disabled={enCours} className={BTN_PRIMAIRE}>
              {etape === "submitting" ? (
                <Loader2 size={14} className="animate-spin" />
              ) : restauration ? (
                <RotateCcw size={14} />
              ) : (
                <RefreshCw size={14} />
              )}
              {restauration ? "Confirmer la restauration" : "Confirmer la mise à jour"}
            </button>
            {impact.nb_a_analyser > 0 && (
              <p className="text-center text-[11px] text-muted-foreground">
                {impact.nb_a_analyser} réponse{impact.nb_a_analyser > 1 ? "s" : ""}{" "}
                {impact.nb_a_analyser > 1 ? "seront relues" : "sera relue"}
              </p>
            )}
          </div>
        </>
      )}

      {etape === "analyse" && (
        <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>Annuler</button>
      )}

      {etape === "done" && (
        <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>Fermer</button>
      )}

      {etape === "error" && (
        <>
          <button type="button" onClick={onFermerErreur} className={BTN_SECONDAIRE}>Fermer</button>
          {!restauration && (
            <button type="button" onClick={onRevenir} className={BTN_SECONDAIRE}>
              Choisir un autre fichier
            </button>
          )}
        </>
      )}
    </div>
  );
}
