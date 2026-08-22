import { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";

type Props = {
  onConfirm: () => void;
  onCancel: () => void;
};

export default function UnsavedDraftModal({ onConfirm, onCancel }: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    triggerRef.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => { triggerRef.current?.focus(); };
  }, []);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") { onCancel(); return; }
    if (e.key === "Tab" && panelRef.current) {
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled])'
      );
      if (focusable.length === 0) { e.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="unsaved-modal-title"
        tabIndex={-1}
        className="w-full max-w-sm rounded-2xl border border-gray-200/80 dark:border-white/10 bg-white dark:bg-[#141416] shadow-[0_8px_48px_0_rgba(0,0,0,0.18)] overflow-hidden outline-none"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-4 border-b border-gray-100 dark:border-white/8">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-500/10">
              <AlertTriangle size={15} className="text-amber-500" aria-hidden="true" />
            </div>
            <div>
              <h3 id="unsaved-modal-title" className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                Modifications non enregistrées
              </h3>
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                Vos modifications seront perdues si vous continuez.
              </p>
            </div>
          </div>
          <button
            onClick={onCancel}
            aria-label="Annuler"
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-200 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4">
          <button
            ref={cancelRef}
            onClick={onCancel}
            className="px-4 py-2 rounded-md border border-gray-200 dark:border-white/12 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
          >
            Continuer à éditer
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-md bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
          >
            Abandonner les modifications
          </button>
        </div>
      </div>
    </div>
  );
}
