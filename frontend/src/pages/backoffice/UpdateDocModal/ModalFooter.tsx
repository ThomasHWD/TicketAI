import { Loader2, RefreshCw } from "lucide-react";
import type { UpdateImpact } from "../../../types";
import type { Etape } from "./index";

interface ModalFooterProps {
  etape: Etape;
  enCours: boolean;
  file: File | null;
  impact: UpdateImpact | null;
  restauration: boolean;
  onClose: () => void;
  onRevenirAuChoix: () => void;
  onLancerAnalyse: () => void;
  onConfirmer: (stagingId: string) => void;
  onCloseAndInvalidate: () => void;
}

export default function ModalFooter({
  etape,
  enCours,
  file,
  impact,
  restauration,
  onClose,
  onRevenirAuChoix,
  onLancerAnalyse,
  onConfirmer,
  onCloseAndInvalidate,
}: ModalFooterProps) {
  return (
    <div className="flex gap-2 px-6 py-4 border-t border-black/[0.06] dark:border-white/10">
      {etape === "pick" && (
        <>
          <button onClick={onClose} className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
            Annuler
          </button>
          <button onClick={onLancerAnalyse} disabled={!file} className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
            <RefreshCw size={14} />
            Analyser l'impact
          </button>
        </>
      )}

      {(etape === "impact" || etape === "submitting") && impact && (
        <>
          <button onClick={restauration ? onClose : onRevenirAuChoix} disabled={enCours} className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors">
            {restauration ? "Annuler" : "Retour"}
          </button>
          <div className="flex-1 flex flex-col gap-1">
            <button onClick={() => onConfirmer(impact.staging_id)} disabled={enCours} className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors">
              {etape === "submitting" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {restauration ? "Confirmer la restauration" : "Confirmer la mise à jour"}
            </button>
            {impact.nb_a_analyser > 0 && (
              <p className="text-center text-[11px] text-slate-500 dark:text-slate-400">
                {impact.nb_a_analyser} réponse{impact.nb_a_analyser > 1 ? "s" : ""}{" "}
                {impact.nb_a_analyser > 1 ? "seront relues" : "sera relue"}
              </p>
            )}
          </div>
        </>
      )}

      {etape === "done" && (
        <button onClick={onClose} className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
          Fermer
        </button>
      )}

      {etape === "error" && (
        <>
          <button onClick={onCloseAndInvalidate} className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
            Fermer
          </button>
          {!restauration && (
            <button onClick={onRevenirAuChoix} className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
              Choisir un autre fichier
            </button>
          )}
        </>
      )}
    </div>
  );
}
