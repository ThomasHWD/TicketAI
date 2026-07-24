import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Files,
  Trash2,
  Eye,
  Loader2,
  AlertTriangle,
  X,
  ChevronLeft,
  ChevronRight,
  Search,
  Download,
} from "lucide-react";
import { listDocuments, getDocumentChunks, deleteDocument } from "../../lib/api";
import type { Domaine, IndexedDocument } from "../../types.ts";

const DOMAINES: Array<Domaine | undefined> = [undefined, "IT", "RH", "JURIDIQUE"];
const DOMAINE_LABELS: Record<string, string> = {
  IT: "IT",
  RH: "RH",
  JURIDIQUE: "Juridique",
};


function ChunksModal({
  doc,
  onClose,
}: {
  doc: IndexedDocument;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const PER_PAGE = 3;

  const { data, isLoading } = useQuery({
    queryKey: ["doc-chunks", doc.doc_id],
    queryFn: () => getDocumentChunks(doc.doc_id),
  });

  const chunks = data?.chunks ?? [];
  const totalPages = Math.ceil(chunks.length / PER_PAGE);
  const visible = chunks.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-black/[0.06] dark:border-white/10">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">
              Chunks du document
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
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 size={22} className="animate-spin text-gray-400" />
            </div>
          ) : visible.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
              Aucun chunk trouvé.
            </p>
          ) : (
            visible.map((chunk) => (
              <div
                key={chunk.chunk_index}
                className="rounded-xl border border-black/[0.06] dark:border-white/10 bg-white/60 dark:bg-white/[0.03] overflow-hidden"
              >
                <div className="px-3 py-1.5 bg-gray-50/80 dark:bg-white/[0.04] border-b border-black/[0.04] dark:border-white/[0.06]">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Chunk #{chunk.chunk_index + 1}
                  </span>
                </div>
                <p className="px-3 py-3 text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed font-mono">
                  {chunk.contenu}
                </p>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-black/[0.06] dark:border-white/10">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} />
              Précédent
            </button>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {page + 1} / {totalPages} — {chunks.length} chunks
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page === totalPages - 1}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Suivant
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function DeleteConfirm({
  doc,
  onConfirm,
  onCancel,
  isPending,
}: {
  doc: IndexedDocument;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onCancel}
    >
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-sm p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-red-100 dark:bg-red-400/15 shrink-0">
            <AlertTriangle size={18} className="text-red-600 dark:text-red-400" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Supprimer ce document ?
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-[220px]">
              {doc.filename ?? doc.doc_id}
            </p>
          </div>
        </div>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          Tous les chunks indexés seront supprimés de Qdrant et le fichier sera définitivement effacé.
          Cette action est irréversible.
        </p>
        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={isPending}
            className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500 text-white disabled:opacity-50 transition-colors"
          >
            {isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            Supprimer
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AllDocs() {
  const queryClient = useQueryClient();
  const [domaine, setDomaine] = useState<Domaine | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [viewing, setViewing] = useState<IndexedDocument | null>(null);
  const [confirming, setConfirming] = useState<IndexedDocument | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["documents", domaine],
    queryFn: () => listDocuments(domaine),
  });

  const { mutate: doDelete, isPending: isDeleting } = useMutation({
    mutationFn: (doc: IndexedDocument) => deleteDocument(doc.doc_id),
    onSuccess: () => {
      setConfirming(null);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const q = search.trim().toLowerCase();
  const docs = (data?.items ?? []).filter(
    (d) =>
      !q ||
      d.filename?.toLowerCase().includes(q) ||
      d.description?.toLowerCase().includes(q),
  );

  return (
    <>
      <div className="p-6 max-w-4xl mx-auto">
        <div className="glass-card rounded-2xl overflow-hidden">
          {/* Header */}
          <div className="px-7 pt-7 pb-6">
            <div className="flex items-center gap-3 mb-1">
              <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-green-100 dark:bg-emerald-400/15">
                <Files size={18} className="text-green-700 dark:text-emerald-400" />
              </div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Documents indexés
              </h1>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 ml-12">
              Consultez et gérez les documents importés.
            </p>
          </div>

          <hr className="border-black/[0.06] dark:border-white/10" />

          {/* Domain filter */}
          <div className="px-7 py-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
              Filtrer par domaine
            </p>
            <div className="flex flex-wrap gap-2">
              {DOMAINES.map((d) => (
                <button
                  key={d ?? "tous"}
                  onClick={() => setDomaine(d)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors
                    ${
                      domaine === d
                        ? "bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300 border-green-300 dark:border-emerald-500/40"
                        : "bg-gray-50 dark:bg-white/5 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-white/10 hover:bg-gray-100 dark:hover:bg-white/10"
                    }`}
                >
                  {d ? DOMAINE_LABELS[d] : "Tous"}
                </button>
              ))}
            </div>
          </div>

          <hr className="border-black/[0.06] dark:border-white/10" />

          {/* Search */}
          <div className="px-7 py-4">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rechercher par titre ou description…"
                className="w-full pl-9 pr-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40"
              />
            </div>
          </div>

          <hr className="border-black/[0.06] dark:border-white/10" />

          {/* Content */}
          <div className="px-7 py-5">
            {isLoading ? (
              <div className="flex justify-center py-12">
                <Loader2 size={22} className="animate-spin text-gray-400" />
              </div>
            ) : isError ? (
              <p className="text-sm text-red-600 dark:text-red-400 text-center py-8">
                Impossible de charger les documents.
              </p>
            ) : docs.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-12">
                {q
                  ? "Aucun document ne correspond à la recherche."
                  : `Aucun document indexé${domaine ? ` en ${DOMAINE_LABELS[domaine]}` : ""}.`}
              </p>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  {docs.length} document{docs.length > 1 ? "s" : ""}
                  {q && data && docs.length !== data.total ? ` sur ${data.total}` : ""}
                </p>
                {docs.map((doc) => (
                  <div
                    key={doc.doc_id}
                    className="flex items-center gap-4 px-4 py-3.5 rounded-xl border border-black/[0.06] dark:border-white/10 bg-white/60 dark:bg-white/[0.03] hover:bg-white/80 dark:hover:bg-white/[0.05] transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {doc.filename ?? "—"}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 truncate">
                        {doc.description || <span className="italic">Aucune description</span>}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {doc.nb_chunks} chunk{doc.nb_chunks > 1 ? "s" : ""}
                      </span>
                      <button
                        onClick={() => setViewing(doc)}
                        title="Voir les chunks"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-white/15 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
                      >
                        <Eye size={13} />
                        Voir
                      </button>
                      <a
                        href={`/api/v1/documents/${doc.doc_id}/download`}
                        download={doc.filename ?? undefined}
                        title="Télécharger"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-300 dark:border-white/15 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
                      >
                        <Download size={13} />
                        Télécharger
                      </a>
                      <button
                        onClick={() => setConfirming(doc)}
                        title="Supprimer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-red-200 dark:border-red-500/25 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
                      >
                        <Trash2 size={13} />
                        Supprimer
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {viewing && <ChunksModal doc={viewing} onClose={() => setViewing(null)} />}

      {confirming && (
        <DeleteConfirm
          doc={confirming}
          onConfirm={() => doDelete(confirming)}
          onCancel={() => setConfirming(null)}
          isPending={isDeleting}
        />
      )}
    </>
  );
}
