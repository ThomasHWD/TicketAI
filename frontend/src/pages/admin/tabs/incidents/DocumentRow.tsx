import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileX, Loader2, RotateCcw, CheckCircle2, Download, Trash2 } from "lucide-react";
import {
  retryDocument, deleteDocumentIncident, downloadDocumentUrl, apiFetch, type DocumentIncident,
} from "../../../../lib/api";

export default function DocumentRow({ doc }: { doc: DocumentIncident }) {
  const qc = useQueryClient();
  const [retryDone, setRetryDone] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const retryMutation = useMutation({
    mutationFn: () => retryDocument(doc.task_id),
    onSuccess: () => {
      setRetryDone(true);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["admin-incidents"] });
        qc.invalidateQueries({ queryKey: ["admin-health"] });
      }, 1000);
    },
    onError: () =>
      setRetryError("Échec du relancement — réessayez ou contactez le support si le problème persiste."),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocumentIncident(doc.task_id),
    onSuccess: () => {
      setRetryError(null);
      qc.invalidateQueries({ queryKey: ["admin-incidents"] });
      qc.invalidateQueries({ queryKey: ["admin-health"] });
    },
    onError: () =>
      setRetryError("Échec de la suppression — réessayez ou contactez le support."),
  });

  const handleDownload = async () => {
    const res = await apiFetch(downloadDocumentUrl(doc.task_id));
    if (!res.ok) { setRetryError("Fichier temporaire introuvable sur le disque."); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = doc.filename ?? "document";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 dark:border-white/8 last:border-0">
      <FileX size={15} className="shrink-0 mt-0.5 text-red-400" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{doc.filename ?? "—"}</span>
          {doc.domaine && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/8 text-muted-foreground font-mono">
              {doc.domaine}
            </span>
          )}
        </div>
        {doc.erreur && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-0.5 line-clamp-2" title={doc.erreur}>{doc.erreur}</p>
        )}
        {retryError && <p className="text-xs text-red-600 dark:text-red-400 mt-1">{retryError}</p>}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <button
          onClick={handleDownload}
          className="flex items-center gap-1 py-1 text-xs text-muted-foreground hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
        >
          <Download size={12} aria-hidden="true" /> Télécharger
        </button>
        {retryDone ? (
          <span className="flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 size={12} aria-hidden="true" /> Relancé
          </span>
        ) : (
          <button
            onClick={() => { setRetryError(null); retryMutation.mutate(); }}
            disabled={retryMutation.isPending}
            className="flex items-center gap-1 py-1 text-xs text-muted-foreground hover:text-emerald-800 dark:hover:text-emerald-400 disabled:opacity-40 transition-colors"
          >
            {retryMutation.isPending ? <Loader2 size={12} className="animate-spin" aria-hidden="true" /> : <RotateCcw size={12} aria-hidden="true" />}
            Relancer
          </button>
        )}
        {confirmDelete ? (
          <span className="flex items-center gap-1.5">
            <button
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="py-1 text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-40"
            >
              {deleteMutation.isPending ? <Loader2 size={12} className="animate-spin inline" aria-hidden="true" /> : "Confirmer"}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="py-1 text-xs text-muted-foreground hover:text-gray-600 dark:hover:text-gray-200"
            >
              Annuler
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1 py-1 text-xs text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors"
          >
            <Trash2 size={12} aria-hidden="true" /> Supprimer
          </button>
        )}
      </div>
    </div>
  );
}
