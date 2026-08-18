import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { confirmDocumentUpdate, previewDocumentUpdate } from "../../../lib/api";
import { validateFile } from "../../../lib/documentUpload";
import { useJobs } from "../../../context/JobsContext";
import type { UpdateImpact } from "../../../types";
import ModalBody from "./ModalBody";
import ModalFooter from "./ModalFooter";

export interface DocCible {
  doc_id: string;
  filename: string | null;
  version: number;
  description?: string;
}

export type Etape = "pick" | "analyse" | "impact" | "submitting" | "done" | "error";

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
    onSuccess: (data) => { setImpact(data); setEtape("impact"); },
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

  const enCours = etape === "analyse" || etape === "submitting";
  const restauration = impactInitial !== undefined;
  const depuis = impact?.restauree_depuis;

  function handleFilePick(f: File) {
    const err = validateFile(f);
    setFileError(err);
    setFile(err ? null : f);
  }

  function revenirAuChoix() {
    setFile(null); setFileError(null); setImpact(null); setErreur(null); setEtape("pick");
  }

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
                ? restauration ? "Restauration lancée" : "Mise à jour lancée"
                : depuis != null ? `Restaurer la v${depuis}` : "Mettre à jour"}
              {etape !== "done" && (
                <> — v{doc.version} → v{impact?.version_cible ?? doc.version + 1}</>
              )}
            </p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {doc.filename ?? doc.doc_id}
            </p>
          </div>
          <button onClick={onClose} className="ml-4 shrink-0 p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors">
            <X size={16} />
          </button>
        </div>

        <ModalBody
          etape={etape}
          file={file}
          fileError={fileError}
          description={description}
          impact={impact}
          erreur={erreur}
          restauration={restauration}
          nbAAnalyser={impact?.nb_a_analyser ?? 0}
          onClose={onClose}
          onFilePick={handleFilePick}
          onDescriptionChange={setDescription}
        />

        <ModalFooter
          etape={etape}
          enCours={enCours}
          file={file}
          impact={impact}
          restauration={restauration}
          onClose={onClose}
          onRevenirAuChoix={revenirAuChoix}
          onLancerAnalyse={() => { if (file) { setEtape("analyse"); analyse.mutate(file); } }}
          onConfirmer={(stagingId) => confirmer.mutate(stagingId)}
          onCloseAndInvalidate={() => { queryClient.invalidateQueries({ queryKey: ["documents"] }); onClose(); }}
        />
      </div>
    </div>
  );
}
