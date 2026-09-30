import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLES =
  'button:not([disabled]):not([tabindex="-1"]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

type Options = {
  onClose: () => void;
  /** Élément focalisé à l'ouverture (défaut : premier focusable de la boîte). */
  initialFocus?: RefObject<HTMLElement | null>;
  /** false pendant une mutation : Échap ne doit pas fermer une action en cours. */
  closeOnEscape?: boolean;
};

/**
 * Piège à focus unique des boîtes modales : focus initial, Tab/Maj+Tab bouclés dans la boîte,
 * Échap, retour du focus à l'élément qui l'avait à l'ouverture. Les focusables sont relus à
 * chaque Tab — un contenu qui apparaît après un chargement reste dans le piège.
 */
export function useDialogFocus(ref: RefObject<HTMLElement | null>, { onClose, initialFocus, closeOnEscape = true }: Options) {
  const latest = useRef({ onClose, closeOnEscape });
  useEffect(() => {
    latest.current = { onClose, closeOnEscape };
  });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? dialog.querySelector<HTMLElement>(FOCUSABLES))?.focus();

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (latest.current.closeOnEscape) {
          e.preventDefault();
          latest.current.onClose();
        }
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const focusables = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLES)];
      if (focusables.length === 0) { e.preventDefault(); return; }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const inside = dialog.contains(document.activeElement);
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus(); }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previous?.focus();
    };
    // Ouverture/fermeture uniquement : les refs sont stables, les callbacks passent par `latest`.
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
