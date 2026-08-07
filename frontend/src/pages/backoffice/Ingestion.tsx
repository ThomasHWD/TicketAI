import { useState } from "react";
import { Link } from "react-router-dom";
import {
  UploadCloud,
  XCircle,
  Loader2,
  RefreshCw,
  Database,
  PenLine,
  Copy,
  AlertTriangle,
  ArrowRight,
} from "lucide-react";
import { apiFetch, uploadDocument, DocumentHomonymeError } from "../../lib/api";
import { useJobs } from "../../context/JobsContext";
import { useAuth } from "../../lib/auth";
import { useQuery } from "@tanstack/react-query";
import FileDropzone from "../../components/ui/FileDropzone";
import { validateFile } from "../../lib/documentUpload";
import UpdateDocModal from "./UpdateDocModal";
import type { Domaine, DocumentHomonyme, DocumentUploadResponse } from "../../types.ts";

async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/admin/domaines");
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}

type Phase = "idle" | "uploading" | "duplicate" | "homonyme" | "error";
type SourceMode = "upload" | "write";

export default function Ingestion() {
  const { addJob } = useJobs();
  const { userDomaines, user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const { data: adminDomaines = [] } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
    staleTime: 5 * 60 * 1000,
    enabled: isAdmin,
  });

  const availableDomaines: Domaine[] = isAdmin ? adminDomaines : userDomaines;

  const [domaine, setDomaine] = useState<Domaine>("");
  // Initialise au premier domaine disponible une fois chargé
  if (!domaine && availableDomaines.length > 0) setDomaine(availableDomaines[0]);
  const [sourceMode, setSourceMode] = useState<SourceMode>("upload");

  // Upload mode state
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  // Write mode state
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");

  // Shared description
  const [description, setDescription] = useState("");

  // Shared flow state
  const [phase, setPhase] = useState<Phase>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DocumentUploadResponse | null>(null);
  const [homonyme, setHomonyme] = useState<DocumentHomonyme | null>(null);
  // Le fichier envoyé, conservé tel quel : c'est lui que la modale de mise à
  // jour analyse si l'utilisateur choisit cette issue, sans nouveau dépôt.
  const [submitted, setSubmitted] = useState<File | null>(null);
  const [updateOpen, setUpdateOpen] = useState(false);

  /** Construit le fichier à envoyer selon le mode (import ou rédaction). */
  const buildFile = (): File | null => {
    if (sourceMode !== "write") return file;
    const blob = new Blob([docContent], { type: "text/plain" });
    return new File([blob], `${docTitle.trim() || "document"}.md`, { type: "text/plain" });
  };

  const submit = async (target: File, forceNouveau = false) => {
    setPhase("uploading");
    setUploadError(null);
    setSubmitted(target);
    try {
      const res = await uploadDocument(target, domaine, description.trim(), forceNouveau);
      if (res.statut === "DÉJÀ_INDEXÉ") {
        setDuplicate(res);
        setPhase("duplicate");
        return;
      }
      if (res.job_id) addJob(res.job_id, res.filename);
      reset();
    } catch (err) {
      if (err instanceof DocumentHomonymeError) {
        setHomonyme(err.document);
        setPhase("homonyme");
        return;
      }
      setUploadError(err instanceof Error ? err.message : "Erreur inattendue");
      setPhase("error");
    }
  };

  const handleSubmit = () => {
    const target = buildFile();
    if (target) submit(target);
  };

  const reset = () => {
    setFile(null);
    setFileError(null);
    setUploadError(null);
    setDocTitle("");
    setDocContent("");
    setDescription("");
    setDuplicate(null);
    setHomonyme(null);
    setSubmitted(null);
    setPhase("idle");
  };

  // Le formulaire cède la place à un écran de résultat — qui, hors erreur, propose
  // désormais une suite (voir le document, mettre à jour) plutôt qu'un cul-de-sac.
  const hideForm = phase === "duplicate" || phase === "homonyme" || phase === "error";
  const isBusy = phase === "uploading";

  const canSubmit =
    !isBusy &&
    (sourceMode === "upload"
      ? !!file && !fileError
      : docTitle.trim().length > 0 && docContent.trim().length >= 50);

  return (
    <>
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

        {/* Domain selector — masqué si un seul domaine disponible */}
        {availableDomaines.length > 1 && (
          <>
            <div className="px-7 py-5">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
                Domaine
              </p>
              <div className="flex gap-2">
                {availableDomaines.map((d) => (
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
                    {d}
                  </button>
                ))}
              </div>
            </div>
            <hr className="border-black/[0.06] dark:border-white/10" />
          </>
        )}

        {/* Source mode tabs */}
        {!hideForm && (
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
              <FileDropzone
                file={file}
                error={fileError}
                disabled={isBusy}
                onPick={(f) => {
                  const err = validateFile(f);
                  setFileError(err);
                  setFile(err ? null : f);
                }}
              />
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

        {/* Contenu strictement identique : il n'y a rien à mettre à jour, on oriente. */}
        {phase === "duplicate" && duplicate && (
          <div className="px-7 py-6 space-y-4">
            <div className="flex items-center gap-2.5 text-amber-600 dark:text-amber-400 font-medium">
              <Copy size={18} />
              Document déjà indexé à l'identique
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Ce fichier est déjà indexé sous «&nbsp;{duplicate.filename}&nbsp;»
              {duplicate.domaine ? ` (${duplicate.domaine}` : ""}
              {duplicate.domaine && duplicate.version ? `, v${duplicate.version}` : ""}
              {duplicate.domaine ? ")" : ""}. Son contenu n'a pas changé : il n'y a rien à mettre
              à jour.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to={`/documents-indexes?q=${encodeURIComponent(duplicate.filename)}`}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white transition-colors"
              >
                <ArrowRight size={14} />
                Voir le document
              </Link>
              <button
                onClick={reset}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                <RefreshCw size={14} />
                Choisir un autre fichier
              </button>
            </div>
          </div>
        )}

        {/* Même nom, contenu différent : c'est très probablement une nouvelle version. */}
        {phase === "homonyme" && homonyme && (
          <div className="px-7 py-6 space-y-4">
            <div className="flex items-center gap-2.5 text-amber-600 dark:text-amber-400 font-medium">
              <AlertTriangle size={18} />
              Un document porte déjà ce nom
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              «&nbsp;{homonyme.filename}&nbsp;» existe déjà en {homonyme.domaine} (v
              {homonyme.version}, {homonyme.nb_chunks} chunk{homonyme.nb_chunks > 1 ? "s" : ""}),
              avec un contenu différent. L'indexer tel quel créerait un second document : les deux
              versions répondraient alors aux mêmes questions, en se contredisant.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => setUpdateOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white transition-colors"
              >
                <RefreshCw size={14} />
                Mettre à jour ce document
              </button>
              <button
                onClick={() => submitted && submit(submitted, true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                <Database size={14} />
                Créer un nouveau document
              </button>
              <button
                onClick={reset}
                className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
              >
                Annuler
              </button>
            </div>
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

    {/* Le fichier est déjà choisi : la modale ouvre directement sur l'analyse d'impact. */}
    {updateOpen && homonyme && submitted && (
      <UpdateDocModal
        doc={homonyme}
        fichierInitial={submitted}
        // Annulation : on revient à l'alerte, les trois issues restent offertes.
        onClose={() => setUpdateOpen(false)}
        onSubmitted={reset}
      />
    )}
    </>
  );
}
