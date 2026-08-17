import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  X,
  XCircle,
} from "lucide-react";
import { confirmDocumentUpdate, previewDocumentUpdate } from "../../../lib/api";
import FileDropzone from "../../../components/ui/FileDropzone";
import { validateFile } from "../../../lib/documentUpload";
import { useJobs } from "../../../context/JobsContext";
import type { UpdateImpact } from "../../../types";
import EcranImpact from "./EcranImpact";

export interface DocCible {
  doc_id: string;
  filename: string | null;
  version: number;
  description?: string;
}

type Etape = "pick" | "analyse" | "impact" | "submitting" | "done" | "error";

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

  const lancerAnalyse = () => {
    if (!file) return;
    setEtape("analyse");
    analyse.mutate(file);
  };

  const revenirAuChoix = () => {
    setFile(null);
    setFileError(null);
    setImpact(null);
    setErreur(null);
    setEtape("pick");
  };

  const enCours = etape === "analyse" || etape === "submitting";
  const restauration = impactInitial !== undefined;
  const depuis = impact?.restauree_depuis;
  const nbAAnalyser = impact?.nb_a_analyser ?? 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-black/[0.06] dark:border-white/10">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">
              {etape === "done"
                ? restauration
                  ? "Restauration lancée"
                  : "Mise à jour lancée"
                : depuis != null
                  ? `Restaurer la v${depuis}`
                  : "Mettre à jour"}
              {etape !== "done" && (
                <> — v{doc.version} → v{impact?.version_cible ?? doc.version + 1}</>
              )}
            </p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {doc.filename ?? doc.doc_id}
            </p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 shrink-0 p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {etape === "pick" && (
            <>
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
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Description
                </label>
                <input
                  type="text"
                  value={description ?? ""}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Résumez brièvement le contenu du document…"
                  className="w-full px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40"
                />
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Le document conservera son identifiant ; l'ancienne version sera archivée et restera
                téléchargeable.
              </p>
            </>
          )}

          {etape === "analyse" && (
            <div className="flex flex-col items-center gap-3 py-12">
              <Loader2 size={22} className="animate-spin text-gray-400" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Comparaison avec la version en ligne…
              </p>
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
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Le document sera ré-indexé en arrière-plan.
                </p>
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

        {/* Footer */}
        <div className="flex gap-2 px-6 py-4 border-t border-black/[0.06] dark:border-white/10">
          {etape === "pick" && (
            <>
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={lancerAnalyse}
                disabled={!file}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <RefreshCw size={14} />
                Analyser l'impact
              </button>
            </>
          )}

          {(etape === "impact" || etape === "submitting") && impact && (
            <>
              <button
                onClick={restauration ? onClose : revenirAuChoix}
                disabled={enCours}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
              >
                {restauration ? "Annuler" : "Retour"}
              </button>
              <div className="flex-1 flex flex-col gap-1">
                <button
                  onClick={() => confirmer.mutate(impact.staging_id)}
                  disabled={enCours}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors"
                >
                  {etape === "submitting" ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RefreshCw size={14} />
                  )}
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
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
            >
              Fermer
            </button>
          )}

          {etape === "error" && (
            <>
              <button
                onClick={() => {
                  queryClient.invalidateQueries({ queryKey: ["documents"] });
                  onClose();
                }}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Fermer
              </button>
              {!restauration && (
                <button
                  onClick={revenirAuChoix}
                  className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Choisir un autre fichier
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
