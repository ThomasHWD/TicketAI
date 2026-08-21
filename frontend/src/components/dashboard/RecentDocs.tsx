import { Link } from "react-router-dom";
import { FileText, FileType, File, AlertTriangle } from "lucide-react";

interface DocItem {
  doc_id: string;
  filename: string | null;
  domaine: string | null;
  nb_chunks: number;
  updated_at?: string | null;
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
  error?: boolean;
  onRetry?: () => void;
}

export default function RecentDocs({ docs, loading = false, error = false, onRetry }: RecentDocsProps) {
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

  const displayed = [...docs]
    .sort((a, b) => {
      const da = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const db = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return db - da;
    })
    .slice(0, 3);

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
          Voir tous →
        </Link>
      </div>

      {error ? (
        <div className="flex items-center gap-2 py-4 text-sm text-gray-500 dark:text-gray-400">
          <AlertTriangle size={14} className="text-red-400 shrink-0" />
          <span className="flex-1">Impossible de charger les documents</span>
          {onRetry && (
            <button onClick={onRetry} className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline shrink-0">
              Réessayer
            </button>
          )}
        </div>
      ) : displayed.length === 0 ? (
        <div className="py-5 text-center space-y-2">
          <p className="text-sm text-gray-500 dark:text-gray-400">Aucun document indexé</p>
          <Link to="/base-de-connaissances" className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline font-medium">
            Indexer votre premier document →
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {displayed.map((doc) => (
            <Link
              key={doc.doc_id}
              to="/base-de-connaissances"
              state={{ highlight: doc.doc_id }}
              className="flex items-center gap-3 p-3 rounded-xl bg-gray-50/60 dark:bg-white/4 border border-gray-100 dark:border-white/6 hover:bg-gray-100/60 dark:hover:bg-white/8 transition-colors group"
            >
              <span className="shrink-0 p-2 rounded-lg bg-white dark:bg-white/8 shadow-sm">
                <DocIcon filename={doc.filename} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate group-hover:text-emerald-700 dark:group-hover:text-emerald-400 transition-colors">
                  {doc.filename ?? "Document sans nom"}
                </p>
                {doc.domaine && (
                  <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                    {doc.domaine}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
