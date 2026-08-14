import { Link } from "react-router-dom";
import { Copy, AlertTriangle, XCircle, ArrowRight, RefreshCw, Database } from "lucide-react";
import type { DocumentHomonyme, DocumentUploadResponse } from "../../../types.ts";

type Props = {
  phase: "duplicate" | "homonyme" | "error";
  duplicate: DocumentUploadResponse | null;
  homonyme: DocumentHomonyme | null;
  uploadError: string | null;
  onReset: () => void;
  onUpdate: () => void;
  onForceNew: () => void;
};

export default function PhaseResult({ phase, duplicate, homonyme, uploadError, onReset, onUpdate, onForceNew }: Props) {
  if (phase === "duplicate" && duplicate) {
    return (
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
            onClick={onReset}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
          >
            <RefreshCw size={14} />
            Choisir un autre fichier
          </button>
        </div>
      </div>
    );
  }

  if (phase === "homonyme" && homonyme) {
    return (
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
            onClick={onUpdate}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white transition-colors"
          >
            <RefreshCw size={14} />
            Mettre à jour ce document
          </button>
          <button
            onClick={onForceNew}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
          >
            <Database size={14} />
            Créer un nouveau document
          </button>
          <button
            onClick={onReset}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            Annuler
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-7 py-6 space-y-3">
      <div className="flex items-center gap-2.5 text-red-700 dark:text-red-400 font-medium">
        <XCircle size={18} />
        Échec de l'indexation
      </div>
      {uploadError && (
        <p className="text-sm text-red-600 dark:text-red-300">{uploadError}</p>
      )}
      <button
        onClick={onReset}
        className="flex items-center gap-2 text-sm text-red-700 dark:text-red-400 hover:underline"
      >
        <RefreshCw size={13} />
        Réessayer
      </button>
    </div>
  );
}
