import { Link } from "react-router-dom";
import { FileText, FileType, File } from "lucide-react";

interface DocItem {
  doc_id: string;
  filename: string | null;
  domaine: string | null;
  nb_chunks: number;
}

function DocIcon({ filename }: { filename: string | null }) {
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileType size={16} className="text-red-500" />;
  if (ext === "docx") return <FileText size={16} className="text-blue-500" />;
  return <File size={16} className="text-gray-400" />;
}

interface RecentDocsProps {
  docs: DocItem[];
  loading?: boolean;
}

export default function RecentDocs({ docs, loading = false }: RecentDocsProps) {
  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl animate-pulse space-y-3">
        <div className="h-5 bg-gray-200 dark:bg-white/10 rounded w-1/2" />
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-12 bg-gray-200 dark:bg-white/10 rounded" />
        ))}
      </div>
    );
  }

  const displayed = docs.slice(0, 3);

  return (
    <div className="glass-card p-5 rounded-2xl space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Derniers documents
        </h3>
        <Link
          to="/base-de-connaissances"
          className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline font-medium"
        >
          Tous →
        </Link>
      </div>

      {displayed.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
          Aucun document indexé
        </p>
      ) : (
        <div className="space-y-2">
          {displayed.map((doc) => (
            <div
              key={doc.doc_id}
              className="flex items-center gap-3 p-3 rounded-xl bg-gray-50/60 dark:bg-white/4 border border-gray-100 dark:border-white/6"
            >
              <span className="shrink-0 p-2 rounded-lg bg-white dark:bg-white/8 shadow-sm">
                <DocIcon filename={doc.filename} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                  {doc.filename ?? "Document sans nom"}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  {doc.domaine && (
                    <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                      {doc.domaine}
                    </span>
                  )}
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    {doc.nb_chunks} chunk{doc.nb_chunks > 1 ? "s" : ""}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
