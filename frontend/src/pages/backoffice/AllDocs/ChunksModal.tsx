import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, X } from "lucide-react";
import { getDocumentChunks } from "../../../lib/api";
import type { IndexedDocument } from "../../../types";

const PER_PAGE = 3;

export default function ChunksModal({
  doc,
  onClose,
}: {
  doc: IndexedDocument;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);

  const { data, isLoading } = useQuery({
    queryKey: ["doc-chunks", doc.doc_id],
    queryFn: () => getDocumentChunks(doc.doc_id),
  });

  const chunks = data?.chunks ?? [];
  const totalPages = Math.ceil(chunks.length / PER_PAGE);
  const visible = chunks.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
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
