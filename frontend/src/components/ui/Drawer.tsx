import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * Panneau latéral (slide-over) monté en portail.
 *
 * Le composant est *monté à l'ouverture* : l'appelant le rend conditionnellement.
 * L'animation d'entrée est donc jouée depuis un `requestAnimationFrame` — sans
 * ce délai d'une frame, le navigateur applique l'état final sans transition.
 */
export default function Drawer({
  title,
  description,
  onClose,
  children,
  footer,
  widthClass = "max-w-xl",
}: {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  widthClass?: string;
}) {
  const [entered, setEntered] = useState(false);
  const asideRef = useRef<HTMLElement>(null);
  const titleId = useId();

  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const el = asideRef.current;
    if (!el) return;
    const selector =
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusables = el.querySelectorAll<HTMLElement>(selector);
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const prev = document.activeElement as HTMLElement | null;
    first?.focus();

    function trap(e: KeyboardEvent) {
      if (e.key !== "Tab" || focusables.length === 0) return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }

    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      prev?.focus();
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button
        type="button"
        aria-label="Fermer le panneau"
        onClick={onClose}
        className={`absolute inset-0 cursor-default bg-gray-900/25 dark:bg-black/60 transition-opacity duration-200 ${
          entered ? "opacity-100" : "opacity-0"
        }`}
      />

      <aside
        ref={asideRef}
        className={`relative flex h-full w-full ${widthClass} flex-col
          border-l border-gray-200 bg-white shadow-2xl
          dark:border-white/10 dark:bg-[#141416]
          transition-transform duration-300 ease-out
          ${entered ? "translate-x-0" : "translate-x-full"}`}
      >
        <header className="flex items-start gap-4 border-b border-gray-100 px-6 py-4 dark:border-white/8">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-base font-semibold tracking-tight text-gray-900 dark:text-gray-50">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{description}</p>
            )}
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
      </aside>
    </div>,
    document.body,
  );
}
