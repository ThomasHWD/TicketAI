import { useRef, useState } from "react";
import { UploadCloud, FileText, XCircle } from "lucide-react";
import { ACCEPTED_EXTS, MAX_SIZE_MB, formatSize } from "../../lib/documentUpload";

/** File drop zone. Controlled — validation and storage stay with the caller because Ingestion and UpdateDoc handle files differently. */
export default function FileDropzone({
  file,
  onPick,
  error,
  disabled = false,
}: {
  file: File | null;
  onPick: (file: File) => void;
  error?: string | null;
  disabled?: boolean;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files[0];
    if (f) onPick(f);
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onPick(f);
    e.target.value = "";
  };

  return (
    <div className="space-y-2">
      <div
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={() => setIsDragging(false)}
        onClick={() => !disabled && inputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 cursor-pointer transition-colors
          ${disabled ? "pointer-events-none opacity-60" : ""}
          ${
            isDragging
              ? "border-green-400 bg-green-50 dark:bg-emerald-400/10"
              : "border-gray-200 dark:border-white/10 bg-white/50 dark:bg-white/[0.03] hover:bg-gray-50 dark:hover:bg-white/[0.06]"
          }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTS.join(",")}
          className="hidden"
          onChange={onInputChange}
        />
        {file ? (
          <>
            <FileText size={36} className="text-green-600 dark:text-emerald-400" />
            <div className="text-center">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{file.name}</p>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                {formatSize(file.size)}
              </p>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-500">
              Cliquez pour changer de fichier
            </p>
          </>
        ) : (
          <>
            <UploadCloud size={36} className="text-gray-400 dark:text-white/20" />
            <div className="text-center">
              <p className="text-sm text-gray-700 dark:text-gray-300">
                Glissez un fichier ici ou{" "}
                <span className="text-green-600 dark:text-emerald-400 font-medium">parcourez</span>
              </p>
              <p className="text-xs text-gray-600 dark:text-gray-500 mt-1">
                PDF, DOCX, TXT, MD — max {MAX_SIZE_MB} Mo
              </p>
            </div>
          </>
        )}
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
          <XCircle size={13} />
          {error}
        </p>
      )}
    </div>
  );
}
