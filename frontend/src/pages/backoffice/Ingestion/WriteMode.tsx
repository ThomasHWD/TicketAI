type Props = {
  docTitle: string;
  docContent: string;
  isBusy: boolean;
  onTitleChange: (v: string) => void;
  onContentChange: (v: string) => void;
};

export default function WriteMode({ docTitle, docContent, isBusy, onTitleChange, onContentChange }: Props) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Titre du document
        </label>
        <input
          type="text"
          value={docTitle}
          onChange={(e) => onTitleChange(e.target.value)}
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
          onChange={(e) => onContentChange(e.target.value)}
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
  );
}
