import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { validateFile } from "../../../../lib/documentUpload";
import { useUpdateDocModal } from "../../../../hooks/useUpdateDocModal";
import FileDropzone from "../../../../components/ui/FileDropzone";
import Modal from "../../../../components/ui/Modal";
import type { UpdateImpact } from "../../../../types";
import EtapeImpact from "./EtapeImpact";
import Stepper from "./Stepper";
import { UpdateDocFooter } from "./UpdateDocFooter";
import type { DocCible } from "../../../../hooks/useUpdateDocModal";

export type { DocCible };

export default function UpdateDocModal({
  doc,
  fichierInitial,
  impactInitial,
  onClose,
  onSubmitted,
}: {
  doc: DocCible;
  fichierInitial?: File;
  impactInitial?: UpdateImpact;
  onClose: () => void;
  onSubmitted?: () => void;
}) {
  const m = useUpdateDocModal({ doc, fichierInitial, impactInitial, onSubmitted });

  return (
    <Modal
      eyebrow={m.eyebrow}
      title={doc.filename ?? doc.doc_id}
      onClose={onClose}
      footer={
        <UpdateDocFooter
          etape={m.etape}
          file={m.file}
          description={m.description}
          enCours={m.enCours}
          restauration={m.restauration}
          impact={m.impact}
          onClose={onClose}
          onRevenir={m.revenirAuChoix}
          onAnalyse={m.lancerAnalyse}
          onConfirmer={() => m.confirmer.mutate(m.impact!.staging_id)}
          onFermerErreur={() => m.fermerErreur(onClose)}
        />
      }
    >
      <Stepper etape={m.etape} />

      {m.etape === "pick" && (
        <div className="space-y-4">
          <FileDropzone
            file={m.file}
            error={m.fileError}
            onPick={(f) => {
              const err = validateFile(f);
              m.setFileError(err);
              m.setFile(err ? null : f);
            }}
          />
          <div className="space-y-1.5">
            <label htmlFor="maj-description" className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Description <span className="text-red-500" aria-hidden="true">*</span>
            </label>
            <input
              id="maj-description"
              type="text"
              value={m.description ?? ""}
              onChange={(e) => m.setDescription(e.target.value)}
              placeholder="Résumez brièvement le contenu du document…"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-white/12 dark:bg-white/5 dark:text-gray-100 dark:placeholder:text-gray-600"
              required
            />
            <p className="text-xs text-gray-500 dark:text-gray-400">Obligatoire — sert à retrouver le document dans la liste.</p>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Le document conservera son identifiant ; l'ancienne version sera archivée et restera téléchargeable.
          </p>
        </div>
      )}

      {m.etape === "analyse" && (
        <div className="flex flex-col items-center gap-4 py-12">
          <Loader2 size={22} className="animate-spin text-gray-400" />
          <div className="space-y-1 text-center">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Comparaison avec la version en ligne…</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Détection des paragraphes modifiés · quelques secondes</p>
          </div>
          <div className="h-0.5 w-40 animate-pulse rounded-full bg-emerald-300 dark:bg-emerald-500/40" />
          <p className="max-w-xs text-center text-xs text-gray-500 dark:text-gray-400">
            Aucune modification n'est appliquée avant votre confirmation.
          </p>
        </div>
      )}

      {(m.etape === "impact" || m.etape === "submitting") && m.impact && (
        <EtapeImpact impact={m.impact} />
      )}

      {m.etape === "done" && (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/15">
            <CheckCircle2 size={22} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {m.restauration ? "Restauration lancée" : "Mise à jour lancée"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">Le document sera ré-indexé en arrière-plan.</p>
          </div>
          {m.nbAAnalyser > 0 && (
            <>
              <p className="max-w-sm text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                {m.nbAAnalyser} réponse{m.nbAAnalyser > 1 ? "s" : ""}{" "}
                {m.nbAAnalyser > 1 ? "sont" : "est"} en cours d'analyse. Celles que le changement
                contredit basculeront dans Obsolètes ; les cas douteux seront déposés dans À relire,
                avec leur justification.
              </p>
              <a
                href="/reponses-enregistrees?onglet=a_relire"
                onClick={onClose}
                className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-800 transition-colors hover:bg-amber-100 dark:border-amber-500/25 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/20"
              >
                <AlertTriangle size={15} />
                Suivre l'analyse
              </a>
            </>
          )}
        </div>
      )}

      {m.etape === "error" && (
        <div className="space-y-2 rounded-xl border border-red-200 bg-red-50/60 px-4 py-3.5 dark:border-red-500/25 dark:bg-red-500/10">
          <p className="flex items-center gap-2 text-sm font-semibold text-red-700 dark:text-red-400">
            <XCircle size={15} className="shrink-0" aria-hidden="true" />
            {m.restauration ? "Restauration impossible" : "Mise à jour impossible"}
          </p>
          <p className="text-xs leading-relaxed text-red-700/80 dark:text-red-300/80">{m.erreur}</p>
        </div>
      )}
    </Modal>
  );
}
