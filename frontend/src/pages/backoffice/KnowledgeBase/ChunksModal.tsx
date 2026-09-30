import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, Layers } from "lucide-react";
import { getDocumentChunks } from "../../../lib/api";
import Modal from "../../../components/ui/Modal";
import type { IndexedDocument } from "../../../types";

const PAR_PAGE = 3;

/** Shows the document as actually indexed — the chunks in order, not the source file. This is the text the search engine sees. */
export default function ChunksModal({
  doc,
  onClose,
}: {
  doc: IndexedDocument;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["doc-chunks", doc.doc_id],
    queryFn: () => getDocumentChunks(doc.doc_id),
  });

  const chunks = data?.chunks ?? [];
  const nbPages = Math.ceil(chunks.length / PAR_PAGE);
  const visibles = chunks.slice(page * PAR_PAGE, (page + 1) * PAR_PAGE);

  return (
    <Modal
      eyebrow={
        <>
          <Layers size={12} />
          Contenu indexé
        </>
      }
      title={doc.filename ?? doc.doc_id}
      onClose={onClose}
      widthClass="max-w-2xl"
      footer={
        nbPages > 1 ? (
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-white/10 dark:hover:text-gray-200"
            >
              <ChevronLeft size={14} />
              Précédent
            </button>
            <span aria-live="polite" className="text-xs tabular-nums text-muted-foreground">
              {page + 1} / {nbPages} · {chunks.length} passage{chunks.length > 1 ? "s" : ""}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(nbPages - 1, p + 1))}
              disabled={page === nbPages - 1}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-gray-100 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-white/10 dark:hover:text-gray-200"
            >
              Suivant
              <ChevronRight size={14} />
            </button>
          </div>
        ) : undefined
      }
    >
      {isLoading ? (
        <div className="flex justify-center py-14">
          <Loader2 size={20} className="animate-spin text-subtle" />
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-3 py-10 text-center">
          <p className="text-sm text-red-600 dark:text-red-400">
            Impossible de charger le contenu indexé.
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
          >
            Réessayer
          </button>
        </div>
      ) : visibles.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Aucun passage indexé.
        </p>
      ) : (
        <div className="space-y-3">
          {visibles.map((chunk) => (
            <article
              key={chunk.chunk_index}
              className="overflow-hidden rounded-xl border border-gray-200 dark:border-white/10"
            >
              <div className="border-b border-gray-100 bg-gray-50/80 px-3 py-1.5 dark:border-white/8 dark:bg-white/[0.04]">
                <span className="text-[11px] font-medium tabular-nums text-muted-foreground">
                  Passage {chunk.chunk_index + 1} sur {chunks.length}
                </span>
              </div>
              <p className="whitespace-pre-wrap px-3.5 py-3 font-mono text-xs leading-relaxed text-gray-700 dark:text-gray-300">
                {chunk.contenu}
              </p>
            </article>
          ))}
        </div>
      )}
    </Modal>
  );
}
