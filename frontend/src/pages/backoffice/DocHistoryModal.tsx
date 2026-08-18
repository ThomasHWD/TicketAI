import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, History, Loader2, RotateCcw, X } from "lucide-react";
import { downloadDocumentVersion, getDocumentVersions, restoreDocumentVersion } from "../../lib/api";
import { formatSize } from "../../lib/documentUpload";
import type { DocumentVersion, UpdateImpact } from "../../types";
import type { DocCible } from "./UpdateDocModal";

function dateCourte(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function LigneVersion({
  v,
  docId,
  peutRestaurer,
  onRestaurer,
  restaurationEnCours,
}: {
  v: DocumentVersion;
  docId: string;
  peutRestaurer: boolean;
  /** Prépare la restauration ; l'appelant enchaîne sur l'écran d'impact. */
  onRestaurer: (version: number) => void;
  restaurationEnCours: number | null;
}) {
  const [downloading, setDownloading] = useState(false);
  const enAttente = restaurationEnCours === v.version;

  return (
    <li
      className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors
        ${
          v.courante
            ? "border-green-300 dark:border-emerald-500/40 bg-green-50/70 dark:bg-emerald-400/10"
            : "border-black/[0.06] dark:border-white/10 bg-white/60 dark:bg-white/[0.03]"
        }`}
    >
      <span
        className={`shrink-0 w-11 text-center px-1.5 py-1 rounded-lg text-xs font-semibold tabular-nums
          ${
            v.courante
              ? "bg-green-100 dark:bg-emerald-400/20 text-green-700 dark:text-emerald-300"
              : "bg-gray-100 dark:bg-white/[0.06] text-gray-600 dark:text-gray-400"
          }`}
      >
        v{v.version}
      </span>

      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-900 dark:text-gray-100 truncate">
          {v.filename}
          {v.courante && (
            <span className="ml-2 text-[11px] font-medium text-green-700 dark:text-emerald-300">
              version courante
            </span>
          )}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
          {dateCourte(v.created_at)}
          {v.auteur && ` · ${v.auteur}`}
          {v.taille_octets != null && ` · ${formatSize(v.taille_octets)}`}
          {` · ${v.nb_chunks} chunk${v.nb_chunks > 1 ? "s" : ""}`}
          {v.restauree_depuis != null && ` · restaurée depuis la v${v.restauree_depuis}`}
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={async () => {
            setDownloading(true);
            try {
              await downloadDocumentVersion(docId, v.version, v.filename);
            } finally {
              setDownloading(false);
            }
          }}
          disabled={!v.fichier_disponible || downloading}
          title={v.fichier_disponible ? "Télécharger cette version" : "Fichier archivé introuvable"}
          className="p-1.5 rounded-lg border border-gray-300 dark:border-white/15 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {downloading ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <Download size={13} />
          )}
        </button>
        {!v.courante && peutRestaurer && (
          <button
            onClick={() => onRestaurer(v.version)}
            disabled={!v.fichier_disponible || restaurationEnCours !== null}
            title={
              v.fichier_disponible
                ? "Restaurer cette version"
                : "Fichier archivé introuvable : restauration impossible"
            }
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-white/15 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {enAttente ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <RotateCcw size={13} />
            )}
            Restaurer
          </button>
        )}
      </div>
    </li>
  );
}

export default function DocHistoryModal({
  doc,
  peutRestaurer,
  onClose,
  onImpact,
}: {
  doc: DocCible;
  /** Miroir de `check_domain_write` : sans droit d'écriture, l'historique reste en lecture. */
  peutRestaurer: boolean;
  onClose: () => void;
  /**
   * L'aperçu d'impact de la restauration est prêt : à l'appelant d'ouvrir
   * `UpdateDocModal` dessus. La restauration passe par le même écran, et le même
   * bouton de confirmation, qu'une mise à jour classique.
   */
  onImpact: (impact: UpdateImpact) => void;
}) {
  const [erreur, setErreur] = useState<string | null>(null);

  // Clé alignée sur l'invalidation `document_updated` de `useSSE`.
  const { data, isLoading, isError } = useQuery({
    queryKey: ["doc-versions", doc.doc_id],
    queryFn: () => getDocumentVersions(doc.doc_id),
  });

  const restaurer = useMutation({
    mutationFn: (version: number) => restoreDocumentVersion(doc.doc_id, version),
    onMutate: () => setErreur(null),
    onSuccess: onImpact,
    onError: (e) => setErreur(e instanceof Error ? e.message : "Erreur inattendue"),
  });

  const versions = data?.items ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-black/[0.06] dark:border-white/10">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">
              <History size={13} />
              Historique des versions
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
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {erreur && (
            <p className="rounded-lg border border-red-200 dark:border-red-500/30 bg-red-50/80 dark:bg-red-400/10 px-3 py-2 text-xs text-red-700 dark:text-red-300">
              {erreur}
            </p>
          )}

          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 size={22} className="animate-spin text-gray-400" />
            </div>
          ) : isError ? (
            <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
              Impossible de charger l'historique.
            </p>
          ) : (
            <>
              <ul className="space-y-2">
                {versions.map((v) => (
                  <LigneVersion
                    key={v.version}
                    v={v}
                    docId={doc.doc_id}
                    peutRestaurer={peutRestaurer}
                    onRestaurer={restaurer.mutate}
                    restaurationEnCours={restaurer.isPending ? restaurer.variables : null}
                  />
                ))}
              </ul>
              {peutRestaurer && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Restaurer une version ne revient pas en arrière : son contenu devient la version
                  suivante. L'impact sur les réponses enregistrées est affiché avant confirmation.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
