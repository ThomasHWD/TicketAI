import { useState } from "react";
import { uploadDocument, DocumentHomonymeError } from "../lib/api";
import { validateFile } from "../lib/documentUpload";
import { useJobs } from "../context/JobsContext";
import type { Domaine, DocumentHomonyme, DocumentUploadResponse } from "../types";

export type Phase = "idle" | "uploading" | "duplicate" | "homonyme" | "error" | "queued";
export type Mode = "upload" | "write";

export const MIN_CARACTERES = 50;

export function useIngestionDrawer(domaines: Domaine[], onIndexed: () => void) {
  const { addJob } = useJobs();

  const [mode, setMode] = useState<Mode>("upload");
  const [domaine, setDomaine] = useState<Domaine>(domaines[0] ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [titre, setTitre] = useState("");
  const [contenu, setContenu] = useState("");
  const [description, setDescription] = useState("");

  const [phase, setPhase] = useState<Phase>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DocumentUploadResponse | null>(null);
  const [homonyme, setHomonyme] = useState<DocumentHomonyme | null>(null);
  const [envoye, setEnvoye] = useState<File | null>(null);
  const [dernierNom, setDernierNom] = useState("");

  function construireFichier(): File | null {
    if (mode !== "write") return file;
    const blob = new Blob([contenu], { type: "text/plain" });
    return new File([blob], `${titre.trim() || "document"}.md`, { type: "text/plain" });
  }

  async function envoyer(cible: File, forceNouveau = false) {
    setPhase("uploading");
    setUploadError(null);
    setDuplicate(null);
    setHomonyme(null);
    setEnvoye(cible);
    try {
      const res = await uploadDocument(cible, domaine, description.trim(), forceNouveau);
      if (res.statut === "DÉJÀ_INDEXÉ") {
        setDuplicate(res);
        setPhase("duplicate");
        return;
      }
      if (res.job_id) addJob(res.job_id, res.filename);
      setDernierNom(res.filename);
      onIndexed();
      setPhase("queued");
    } catch (err) {
      if (err instanceof DocumentHomonymeError) {
        setHomonyme(err.document);
        setPhase("homonyme");
        return;
      }
      setUploadError(err instanceof Error ? err.message : "Erreur inattendue");
      setPhase("error");
    }
  }

  function reinitialiser() {
    setFile(null);
    setFileError(null);
    setTitre("");
    setContenu("");
    setDescription("");
    setUploadError(null);
    setDuplicate(null);
    setHomonyme(null);
    setEnvoye(null);
    setPhase("idle");
  }

  function pickFile(f: File) {
    const err = validateFile(f);
    setFileError(err);
    setFile(err ? null : f);
  }

  const occupe = phase === "uploading";
  const pretAEnvoyer =
    !occupe &&
    !!domaine &&
    description.trim().length > 0 &&
    (mode === "upload"
      ? !!file && !fileError
      : titre.trim().length > 0 && contenu.trim().length >= MIN_CARACTERES);

  return {
    mode, setMode,
    domaine, setDomaine,
    file, fileError, pickFile,
    titre, setTitre,
    contenu, setContenu,
    description, setDescription,
    phase,
    uploadError,
    duplicate,
    homonyme,
    envoye,
    dernierNom,
    occupe,
    pretAEnvoyer,
    construireFichier,
    envoyer,
    reinitialiser,
  };
}
