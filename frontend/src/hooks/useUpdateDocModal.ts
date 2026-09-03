import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { confirmDocumentUpdate, previewDocumentUpdate } from "../lib/api";
import { useJobs } from "../context/JobsContext";
import type { UpdateImpact } from "../types";

export interface DocCible {
  doc_id: string;
  filename: string | null;
  version: number;
  description?: string;
}

export type Etape = "pick" | "analyse" | "impact" | "submitting" | "done" | "error";

interface UseUpdateDocModalOpts {
  doc: DocCible;
  fichierInitial?: File;
  impactInitial?: UpdateImpact;
  onSubmitted?: () => void;
}

export function useUpdateDocModal({ doc, fichierInitial, impactInitial, onSubmitted }: UseUpdateDocModalOpts) {
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
    setFile(null); setFileError(null); setImpact(null); setErreur(null);
    setEtape("pick");
  }

  function lancerAnalyse() {
    if (!file) return;
    setEtape("analyse");
    analyse.mutate(file);
  }

  function fermerErreur(onClose: () => void) {
    queryClient.invalidateQueries({ queryKey: ["documents"] });
    onClose();
  }

  const eyebrow =
    etape === "done"
      ? (restauration ? "Restauration lancée" : "Mise à jour lancée")
      : `${depuis != null ? `Restaurer la v${depuis}` : "Mettre à jour"} · v${doc.version} → v${impact?.version_cible ?? doc.version + 1}`;

  return {
    etape, file, setFile, fileError, setFileError, description, setDescription,
    impact, erreur, enCours, restauration, nbAAnalyser, eyebrow,
    confirmer, revenirAuChoix, lancerAnalyse, fermerErreur,
  };
}
