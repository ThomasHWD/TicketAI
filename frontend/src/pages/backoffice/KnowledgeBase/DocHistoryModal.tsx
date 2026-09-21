import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, History, Loader2, RotateCcw } from "lucide-react";
import {
  downloadDocumentVersion,
  getDocumentVersions,
  restoreDocumentVersion,
} from "../../../lib/api";
import { formatSize } from "../../../lib/documentUpload";
import Modal from "../../../components/ui/Modal";
import type { DocumentVersion, UpdateImpact } from "../../../types";
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
  onRestaurer: (version: number) => void;
  restaurationEnCours: number | null;
}) {
  const [downloading, setDownloading] = useState(false);
  const enAttente = restaurationEnCours === v.version;

  return (
    <li className="group relative flex gap-3 pb-4 last:pb-0">
      {/* Fil de la frise, interrompu sous la dernière version */}
      <span
        aria-hidden="true"
        className="absolute bottom-0 left-[13px] top-7 w-px bg-gray-200 group-last:hidden dark:bg-white/10"
      />

      <span
        className={`z-10 mt-0.5 flex h-[27px] w-[27px] shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold tabular-nums
          ${
            v.courante
              ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/15 dark:text-emerald-300"
              : "border-gray-200 bg-white text-gray-500 dark:border-white/12 dark:bg-[#141416] dark:text-gray-400"
          }`}
      >
        v{v.version}
      </span>

      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-gray-900 dark:text-gray-100">
              {v.filename}
              {v.courante && (
                <span className="ml-2 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                  version courante
                </span>
              )}
            </p>
            <p className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">
              {dateCourte(v.created_at)}
              {v.auteur && ` · ${v.auteur}`}
              {v.taille_octets != null && ` · ${formatSize(v.taille_octets)}`}
              {` · ${v.nb_chunks} passage${v.nb_chunks > 1 ? "s" : ""}`}
              {v.restauree_depuis != null && ` · restaurée depuis la v${v.restauree_depuis}`}
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={async () => {
                setDownloading(true);
                try {
                  await downloadDocumentVersion(docId, v.version, v.filename);
                } finally {
                  setDownloading(false);
                }
              }}
              disabled={!v.fichier_disponible || downloading}
              title={
                v.fichier_disponible ? "Télécharger cette version" : "Fichier archivé introuvable"
              }
              className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:hover:bg-white/10 dark:hover:text-gray-200"
            >
              {downloading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Download size={14} />
              )}
            </button>

            {!v.courante && peutRestaurer && (
              <button
                type="button"
                onClick={() => onRestaurer(v.version)}
                disabled={!v.fichier_disponible || restaurationEnCours !== null}
                title={
                  v.fichier_disponible
                    ? "Restaurer cette version"
                    : "Fichier archivé introuvable : restauration impossible"
                }
                className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:border-white/12 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-200"
              >
                {enAttente ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <RotateCcw size={12} />
                )}
                Restaurer
              </button>
            )}
          </div>
        </div>
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
  /** Restoration impact preview ready — caller opens `UpdateDocModal` on it; restore and update share the same confirmation screen. */
  onImpact: (impact: UpdateImpact) => void;
}) {
  const [erreur, setErreur] = useState<string | null>(null);

  // Clé alignée sur l'invalidation `document_updated` de `useSSE`.
  const { data, isLoading, isError, refetch } = useQuery({
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
    <Modal
      eyebrow={
        <>
          <History size={12} />
          Historique des versions
        </>
      }
      title={doc.filename ?? doc.doc_id}
      onClose={onClose}
      widthClass="max-w-2xl"
      footer={
        peutRestaurer ? (
          <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
            Restaurer une version ne revient pas en arrière : son contenu devient la version
            suivante. L'impact sur les réponses enregistrées est affiché avant confirmation.
          </p>
        ) : undefined
      }
    >
      {erreur && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2 text-xs text-red-700 dark:border-red-500/25 dark:bg-red-500/10 dark:text-red-300">
          {erreur}
        </p>
      )}

      {isLoading ? (
        <div className="flex justify-center py-14">
          <Loader2 size={20} className="animate-spin text-gray-400" />
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <p className="text-sm text-red-600 dark:text-red-400">
            Impossible de charger l'historique.
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
          >
            Réessayer
          </button>
        </div>
      ) : (
        <ol className="space-y-0">
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
        </ol>
      )}
    </Modal>
  );
}
