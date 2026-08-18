import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

/**
 * Coquille de boîte de dialogue centrée : en-tête, corps défilant, pied fixe.
 *
 * Volontairement *non* portée dans un portail : les modales de cette page sont
 * rendues à la racine de la page, et les tests existants (`updateImpact`,
 * `documentVersions`) montent le composant directement.
 */
export default function Modal({
  eyebrow,
  title,
  onClose,
  children,
  footer,
  widthClass = "max-w-xl",
}: {
  /** Ligne de contexte au-dessus du titre (petites capitales). */
  eyebrow?: ReactNode;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  widthClass?: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        aria-label="Fermer la fenêtre"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-gray-900/25 dark:bg-black/60"
      />

      <div
        className={`relative flex max-h-[86vh] w-full ${widthClass} flex-col overflow-hidden
          rounded-2xl border border-gray-200 bg-white shadow-2xl
          dark:border-white/10 dark:bg-[#141416]`}
      >
        <header className="flex items-start gap-4 border-b border-gray-100 px-6 py-4 dark:border-white/8">
          <div className="min-w-0 flex-1">
            {eyebrow && (
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                {eyebrow}
              </p>
            )}
            <h2 className="truncate text-base font-semibold tracking-tight text-gray-900 dark:text-gray-50">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="-mr-1.5 shrink-0 rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-white/10 dark:hover:text-gray-200"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>

        {footer && (
          <footer className="border-t border-gray-100 px-6 py-4 dark:border-white/8">{footer}</footer>
        )}
      </div>
    </div>
  );
}
