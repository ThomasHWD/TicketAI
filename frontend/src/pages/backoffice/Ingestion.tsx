import { useCallback, useRef, useState } from "react";
import {
  UploadCloud,
  FileText,
  XCircle,
  Loader2,
  RefreshCw,
  Database,
  PenLine,
  Copy,
} from "lucide-react";
import { uploadDocument } from "../../lib/api";
import { useJobs } from "../../context/JobsContext";
import type { Domaine } from "../../types.ts";

const DOMAINES: Domaine[] = ["IT", "RH", "JURIDIQUE"];
const DOMAINE_LABELS: Record<Domaine, string> = {
  IT: "IT",
  RH: "RH",
  JURIDIQUE: "Juridique",
};
const ACCEPTED_EXTS = [".pdf", ".docx", ".txt", ".md"];
const MAX_SIZE_MB = 50;

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function validateFile(file: File): string | null {
  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  if (!ACCEPTED_EXTS.includes(ext)) {
    return `Extension non supportée : ${ext}. Formats acceptés : PDF, DOCX, TXT, MD.`;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `Fichier trop volumineux : ${formatSize(file.size)} (max ${MAX_SIZE_MB} Mo).`;
  }
  return null;
}

type Phase = "idle" | "uploading" | "duplicate" | "error";
type SourceMode = "upload" | "write";

export default function Ingestion() {
  const { addJob } = useJobs();
  const [domaine, setDomaine] = useState<Domaine>("IT");
  const [sourceMode, setSourceMode] = useState<SourceMode>("upload");

  // Upload mode state
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Write mode state
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");

  // Shared description
  const [description, setDescription] = useState("");

  // Shared flow state
  const [phase, setPhase] = useState<Phase>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duplicateDocId, setDuplicateDocId] = useState<string | null>(null);

  const pickFile = (f: File) => {
    const err = validateFile(f);
    setFileError(err);
    setFile(err ? null : f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) pickFile(f);
  }, []);

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const onDragLeave = () => setIsDragging(false);

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) pickFile(f);
    e.target.value = "";
  };

  const handleSubmit = async () => {
    setPhase("uploading");
    setUploadError(null);
    try {
      let target: File;
      if (sourceMode === "write") {
        const blob = new Blob([docContent], { type: "text/plain" });
        target = new File([blob], `${docTitle.trim() || "document"}.md`, {
          type: "text/plain",
        });
      } else {
        if (!file) return;
        target = file;
      }
      const res = await uploadDocument(target, domaine, description.trim());
      if (res.statut === "DÉJÀ_INDEXÉ") {
        setDuplicateDocId(res.doc_id ?? null);
        setPhase("duplicate");
        return;
      }
      if (res.job_id) addJob(res.job_id, res.filename);
      reset();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Erreur inattendue");
      setPhase("error");
    }
  };

  const reset = () => {
    setFile(null);
    setFileError(null);
    setUploadError(null);
    setDocTitle("");
    setDocContent("");
    setDescription("");
    setDuplicateDocId(null);
    setPhase("idle");
  };

  const isTerminal = phase === "duplicate" || phase === "error";
  const isBusy = phase === "uploading";

  const canSubmit =
    !isBusy &&
    (sourceMode === "upload"
      ? !!file && !fileError
      : docTitle.trim().length > 0 && docContent.trim().length >= 50);

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="glass-card rounded-2xl overflow-hidden">
        {/* Header */}
        <div className="px-7 pt-7 pb-6">
          <div className="flex items-center gap-3 mb-1">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-green-100 dark:bg-emerald-400/15">
              <Database size={18} className="text-green-700 dark:text-emerald-400" />
            </div>
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Indexation de documents
            </h1>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 ml-12">
            Importez ou rédigez un document pour l'indexer dans la base
            de connaissances.
          </p>
        </div>

        <hr className="border-black/[0.06] dark:border-white/10" />

        {/* Domain selector */}
        <div className="px-7 py-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
            Domaine
          </p>
          <div className="flex gap-2">
            {DOMAINES.map((d) => (
              <button
                key={d}
                onClick={() => !isBusy && setDomaine(d)}
                disabled={isBusy}
                className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors
                  ${
                    domaine === d
                      ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 border-green-300 dark:border-emerald-500/40"
                      : "bg-gray-50 dark:bg-white/5 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
                  }
                  disabled:opacity-50 disabled:cursor-not-allowed`}
              >
                {DOMAINE_LABELS[d]}
              </button>
            ))}
          </div>
        </div>

        <hr className="border-black/[0.06] dark:border-white/10" />

        {/* Source mode tabs */}
        {!isTerminal && (
          <div className="px-7 py-5 space-y-5">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
                Source
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => !isBusy && setSourceMode("upload")}
                  disabled={isBusy}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors
                    ${
                      sourceMode === "upload"
                        ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 border-green-300 dark:border-emerald-500/40"
                        : "bg-gray-50 dark:bg-white/5 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
                    }
                    disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <UploadCloud size={14} />
                  Importer un fichier
                </button>
                <button
                  onClick={() => !isBusy && setSourceMode("write")}
                  disabled={isBusy}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors
                    ${
                      sourceMode === "write"
                        ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 border-green-300 dark:border-emerald-500/40"
                        : "bg-gray-50 dark:bg-white/5 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
                    }
                    disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <PenLine size={14} />
                  Rédiger un document
                </button>
              </div>
            </div>

            {/* Upload mode */}
            {sourceMode === "upload" && (
              <div className="space-y-2">
                <div
                  onDrop={onDrop}
                  onDragOver={onDragOver}
                  onDragLeave={onDragLeave}
                  onClick={() => !isBusy && inputRef.current?.click()}
                  className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 cursor-pointer transition-colors
                    ${isBusy ? "pointer-events-none opacity-60" : ""}
                    ${
                      isDragging
                        ? "border-green-400 bg-green-50 dark:bg-emerald-400/10"
                        : "border-gray-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.03] hover:bg-gray-50 dark:hover:bg-white/[0.06]"
                    }`}
                >
                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED_EXTS.join(",")}
                    className="hidden"
                    onChange={onInputChange}
                  />
                  {file ? (
                    <>
                      <FileText size={36} className="text-green-600 dark:text-emerald-400" />
                      <div className="text-center">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {file.name}
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                          {formatSize(file.size)}
                        </p>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        Cliquez pour changer de fichier
                      </p>
                    </>
                  ) : (
                    <>
                      <UploadCloud size={36} className="text-gray-400 dark:text-white/20" />
                      <div className="text-center">
                        <p className="text-sm text-gray-700 dark:text-gray-300">
                          Glissez un fichier ici ou{" "}
                          <span className="text-green-600 dark:text-emerald-400 font-medium">
                            parcourez
                          </span>
                        </p>
                        <p className="text-xs text-gray-600 dark:text-gray-500 mt-1">
                          PDF, DOCX, TXT, MD — max {MAX_SIZE_MB} Mo
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {fileError && (
                  <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                    <XCircle size={13} />
                    {fileError}
                  </p>
                )}
              </div>
            )}

            {/* Write mode */}
            {sourceMode === "write" && (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Titre du document
                  </label>
                  <input
                    type="text"
                    value={docTitle}
                    onChange={(e) => setDocTitle(e.target.value)}
                    disabled={isBusy}
                    placeholder="Ex : Politique de télétravail 2025"
                    className="w-full px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40 disabled:opacity-50"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Contenu
                  </label>
                  <textarea
                    value={docContent}
                    onChange={(e) => setDocContent(e.target.value)}
                    disabled={isBusy}
                    placeholder="Rédigez le contenu du document ici…"
                    rows={12}
                    className="w-full px-3 py-2.5 rounded-lg text-sm font-mono border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 resize-y focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40 disabled:opacity-50"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-500">
                    Markdown ou texte brut accepté — minimum 50 caractères
                    {docContent.length > 0 && (
                      <span
                        className={`ml-1 ${docContent.trim().length >= 50 ? "text-green-600 dark:text-emerald-400" : "text-gray-400"}`}
                      >
                        ({docContent.trim().length} caractères)
                      </span>
                    )}
                  </p>
                </div>
              </div>
            )}

            {/* Description */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Description
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={isBusy}
                placeholder="Résumez brièvement le contenu du document…"
                className="w-full px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40 disabled:opacity-50"
              />
            </div>

            {/* Submit button */}
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleSubmit}
                disabled={!canSubmit}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isBusy ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    {phase === "uploading" ? "Envoi en cours…" : "Indexation en cours…"}
                  </>
                ) : (
                  <>
                    <Database size={15} />
                    Indexer
                  </>
                )}
              </button>

            </div>
          </div>
        )}

        {/* Duplicate result */}
        {phase === "duplicate" && (
          <div className="px-7 py-6 space-y-4">
            <div className="flex items-center gap-2.5 text-amber-600 dark:text-amber-400 font-medium">
              <Copy size={18} />
              Document déjà indexé
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Ce fichier est identique à un document déjà présent dans la base de connaissances.
              Aucune indexation supplémentaire n'a été effectuée.
            </p>
            {duplicateDocId && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-8 gap-y-2 text-sm">
                <dt className="text-gray-600 dark:text-gray-400 whitespace-nowrap">Identifiant existant</dt>
                <dd className="text-gray-900 dark:text-gray-100 font-mono text-xs truncate">
                  {duplicateDocId}
                </dd>
              </dl>
            )}
            <button
              onClick={reset}
              className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400 hover:underline mt-1"
            >
              <RefreshCw size={13} />
              Indexer un autre document
            </button>
          </div>
        )}

        {/* Error result */}
        {phase === "error" && (
          <div className="px-7 py-6 space-y-3">
            <div className="flex items-center gap-2.5 text-red-700 dark:text-red-400 font-medium">
              <XCircle size={18} />
              Échec de l'indexation
            </div>
            {uploadError && (
              <p className="text-sm text-red-600 dark:text-red-300">
                {uploadError}
              </p>
            )}
            <button
              onClick={reset}
              className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 hover:underline"
            >
              <RefreshCw size={13} />
              Réessayer
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
