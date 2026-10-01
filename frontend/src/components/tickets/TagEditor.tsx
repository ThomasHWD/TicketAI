import { useRef, useState, useEffect } from "react";
import { Tag, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getTags, updateTag } from "../../lib/api";

interface TagEditorProps {
  reponseId: string;
  domaine: string;
  currentTag: string | null;
  onUpdated?: (tag: string | null) => void;
}

export default function TagEditor({ reponseId, domaine, currentTag, onUpdated }: TagEditorProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(currentTag ?? "");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const { data: tags = [] } = useQuery({
    queryKey: ["tags-canoniques", domaine],
    queryFn: () => getTags(domaine, true),
    staleTime: 0,
  });

  const suggestions = value.trim()
    ? tags.filter((t) => t.toLowerCase().includes(value.toLowerCase()) && t !== value)
    : tags.filter((t) => t !== currentTag);

  useEffect(() => {
    if (editing) {
      setValue(currentTag ?? "");
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [editing, currentTag]);

  async function save(tag: string | null) {
    setSaving(true);
    try {
      await updateTag(reponseId, tag || null);
      queryClient.invalidateQueries({ queryKey: ["tags-canoniques", domaine] });
      onUpdated?.(tag || null);
      setEditing(false);
    } catch {
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") { e.preventDefault(); save(value.trim()); }
    if (e.key === "Escape") { setEditing(false); }
  }

  function handleBlur(e: React.FocusEvent<HTMLDivElement>) {
    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
      if (value.trim() !== (currentTag ?? "")) {
        save(value.trim());
      } else {
        setEditing(false);
      }
    }
  }

  if (!editing) {
    return currentTag ? (
      <button
        onClick={() => setEditing(true)}
        title="Modifier le tag"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300 hover:bg-violet-100 dark:hover:bg-violet-500/20 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60"
      >
        <Tag size={10} aria-hidden="true" />
        {currentTag}
      </button>
    ) : (
      <button
        onClick={() => setEditing(true)}
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-violet-600 dark:hover:text-violet-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60 rounded-sm"
      >
        <Tag size={10} aria-hidden="true" />
        Ajouter un tag
      </button>
    );
  }

  return (
    <div className="relative" onBlur={handleBlur}>
      <div className="flex items-center gap-1">
        <div className="relative">
          <Tag size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-violet-400 pointer-events-none" aria-hidden="true" />
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Nom du tag…"
            disabled={saving}
            maxLength={100}
            className="pl-6 pr-2 py-0.5 text-xs rounded-full border border-violet-300 dark:border-violet-500/40 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60 w-36 disabled:opacity-50"
          />
        </div>
        {value && (
          <button
            onMouseDown={(e) => { e.preventDefault(); save(null); }}
            aria-label="Supprimer le tag"
            className="text-muted-foreground hover:text-red-600 dark:hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/60 rounded-sm"
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </div>
      {suggestions.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 top-full mt-1 z-20 w-48 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-gray-900 shadow-md overflow-hidden"
        >
          {suggestions.slice(0, 8).map((t) => (
            <li key={t}>
              <button
                role="option"
                aria-selected={t === value}
                onMouseDown={(e) => { e.preventDefault(); save(t); }}
                className="w-full text-left px-3 py-1.5 text-xs text-violet-950 dark:text-violet-50 hover:bg-violet-50 hover:text-violet-800 dark:hover:bg-violet-500/10 dark:hover:text-violet-100 transition-colors"
              >
                {t}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
