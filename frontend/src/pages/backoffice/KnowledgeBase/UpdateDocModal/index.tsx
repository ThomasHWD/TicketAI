import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { confirmDocumentUpdate, previewDocumentUpdate } from "../../../../lib/api";
import { validateFile } from "../../../../lib/documentUpload";
import { useJobs } from "../../../../context/JobsContext";
import FileDropzone from "../../../../components/ui/FileDropzone";
import Modal from "../../../../components/ui/Modal";
import type { UpdateImpact } from "../../../../types";
import EtapeImpact from "./EtapeImpact";
import Stepper from "./Stepper";

export interface DocCible {
  doc_id: string;
  filename: string | null;
  version: number;
  description?: string;
}

export type Etape = "pick" | "analyse" | "impact" | "submitting" | "done" | "error";

const BTN_SECONDAIRE =
  "flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5";
const BTN_PRIMAIRE =
  "flex w-full items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100";

/**
 * Assistant de mise à jour (et de restauration) d'un document, en quatre temps :
 * choisir le fichier, l'analyser, lire l'impact, confirmer.
 *
 * L'aperçu n'appelle ni reranker ni LLM : il reste instantané et gratuit même si
 * l'utilisateur renonce. Il ne peut donc pas annoncer quelles réponses seront
 * retirées, et l'écran d'impact ne doit jamais laisser croire qu'il le sait.
 */
export default function UpdateDocModal({
  doc,
  fichierInitial,
  impactInitial,
  onClose,
  onSubmitted,
}: {
  doc: DocCible;
  fichierInitial?: File;
  /** Fourni par la restauration d'une version : l'aperçu est déjà calculé. */
  impactInitial?: UpdateImpact;
  onClose: () => void;
  onSubmitted?: () => void;
}) {
  const queryClient = useQueryClient();
  const { addJob } = useJobs();

  const [etape, setEtape] = useState<Etape>(
    impactInitial ? "impact" : fichierInitial ? "analyse" : "pick",
  );
  const [file, setFile] = useState<File | null>(fichierInitial ?? null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [description, setDescription] = useState<string | undefined>(doc.description);
  const [impact, setImpact] = useState<UpdateImpact | null>(impactInitial ?? null);
  const [erreur, setErreur] = useState<string | null>(null);

  const echouer = (e: unknown) => {
    setErreur(e instanceof Error ? e.message : "Erreur inattendue");
    setEtape("error");
  };

  const analyse = useMutation({
    mutationFn: (f: File) => previewDocumentUpdate(doc.doc_id, f, description),
    onSuccess: (data) => {
      setImpact(data);
      setEtape("impact");
    },
    onError: echouer,
  });

  const confirmer = useMutation({
    mutationFn: (stagingId: string) => confirmDocumentUpdate(doc.doc_id, stagingId),
    onMutate: () => setEtape("submitting"),
    onSuccess: (res) => {
      if (res.job_id) addJob(res.job_id, res.filename, "maj");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onSubmitted?.();
      setEtape("done");
    },
    onError: echouer,
  });

  const analyseLancee = useRef(false);
  useEffect(() => {
    if (!fichierInitial || analyseLancee.current) return;
    analyseLancee.current = true;
    analyse.mutate(fichierInitial);
  }, [fichierInitial, analyse]);

  const enCours = etape === "analyse" || etape === "submitting";
  const restauration = impactInitial !== undefined;
  const depuis = impact?.restauree_depuis;
  const nbAAnalyser = impact?.nb_a_analyser ?? 0;

  function revenirAuChoix() {
    setFile(null);
    setFileError(null);
    setImpact(null);
    setErreur(null);
    setEtape("pick");
  }

  const eyebrow =
    etape === "done" ? (
      restauration ? (
        "Restauration lancée"
      ) : (
        "Mise à jour lancée"
      )
    ) : (
      <>
        {depuis != null ? `Restaurer la v${depuis}` : "Mettre à jour"} · v{doc.version} → v
        {impact?.version_cible ?? doc.version + 1}
      </>
    );

  return (
    <Modal
      eyebrow={eyebrow}
      title={doc.filename ?? doc.doc_id}
      onClose={onClose}
      footer={
        <div className="flex gap-2">
          {etape === "pick" && (
            <>
              <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>
                Annuler
              </button>
              <div className="flex-1">
                <button
                  type="button"
                  disabled={!file}
                  onClick={() => {
                    if (!file) return;
                    setEtape("analyse");
                    analyse.mutate(file);
                  }}
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
              <button
                type="button"
                onClick={restauration ? onClose : revenirAuChoix}
                disabled={enCours}
                className={BTN_SECONDAIRE}
              >
                {restauration ? "Annuler" : "Retour"}
              </button>
              <div className="flex flex-1 flex-col gap-1">
                <button
                  type="button"
                  onClick={() => confirmer.mutate(impact.staging_id)}
                  disabled={enCours}
                  className={BTN_PRIMAIRE}
                >
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
                  <p className="text-center text-[11px] text-gray-400 dark:text-gray-500">
                    {impact.nb_a_analyser} réponse{impact.nb_a_analyser > 1 ? "s" : ""}{" "}
                    {impact.nb_a_analyser > 1 ? "seront relues" : "sera relue"}
                  </p>
                )}
              </div>
            </>
          )}

          {etape === "analyse" && (
            <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>
              Annuler
            </button>
          )}

          {etape === "done" && (
            <button type="button" onClick={onClose} className={BTN_SECONDAIRE}>
              Fermer
            </button>
          )}

          {etape === "error" && (
            <>
              <button
                type="button"
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ["documents"] });
                  onClose();
                }}
                className={BTN_SECONDAIRE}
              >
                Fermer
              </button>
              {!restauration && (
                <button type="button" onClick={revenirAuChoix} className={BTN_SECONDAIRE}>
                  Choisir un autre fichier
                </button>
              )}
            </>
          )}
        </div>
      }
    >
      <Stepper etape={etape} />

      {etape === "pick" && (
        <div className="space-y-4">
          <FileDropzone
            file={file}
            error={fileError}
            onPick={(f) => {
              const err = validateFile(f);
              setFileError(err);
              setFile(err ? null : f);
            }}
          />
          <div className="space-y-1.5">
            <label
              htmlFor="maj-description"
              className="text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Description
            </label>
            <input
              id="maj-description"
              type="text"
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Résumez brièvement le contenu du document…"
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:border-white/12 dark:bg-white/5 dark:text-gray-100 dark:placeholder:text-gray-600"
            />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Le document conservera son identifiant ; l'ancienne version sera archivée et restera
            téléchargeable.
          </p>
        </div>
      )}

      {etape === "analyse" && (
        <div className="flex flex-col items-center gap-3 py-14">
          <Loader2 size={20} className="animate-spin text-gray-400" />
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Comparaison avec la version en ligne…
          </p>
          <p className="max-w-xs text-center text-xs text-gray-400 dark:text-gray-500">
            Aucune modification n'est appliquée à ce stade.
          </p>
        </div>
      )}

      {(etape === "impact" || etape === "submitting") && impact && <EtapeImpact impact={impact} />}

      {etape === "done" && (
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/15">
            <CheckCircle2 size={22} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {restauration ? "Restauration lancée" : "Mise à jour lancée"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Le document sera ré-indexé en arrière-plan.
            </p>
          </div>
          {nbAAnalyser > 0 && (
            <>
              <p className="max-w-sm text-xs leading-relaxed text-gray-500 dark:text-gray-400">
                {nbAAnalyser} réponse{nbAAnalyser > 1 ? "s" : ""}{" "}
                {nbAAnalyser > 1 ? "sont" : "est"} en cours d'analyse. Celles que le changement
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

      {etape === "error" && (
        <div className="space-y-2 rounded-xl border border-red-200 bg-red-50/60 px-4 py-3.5 dark:border-red-500/25 dark:bg-red-500/10">
          <p className="flex items-center gap-2 text-sm font-semibold text-red-700 dark:text-red-400">
            <XCircle size={15} className="shrink-0" aria-hidden="true" />
            {restauration ? "Restauration impossible" : "Mise à jour impossible"}
          </p>
          <p className="text-xs leading-relaxed text-red-700/80 dark:text-red-300/80">{erreur}</p>
        </div>
      )}
    </Modal>
  );
}
