import { useEffect, useRef, type RefObject } from "react";

export function useDialogFocus(ref: RefObject<HTMLElement | null>, onCancel: () => void) {
  const onCancelRef = useRef(onCancel);
  useEffect(() => { onCancelRef.current = onCancel; });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const focusables = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]):not([tabindex="-1"]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const previously = document.activeElement as HTMLElement | null;
    first?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") { onCancelRef.current(); return; }
      if (e.key !== "Tab") return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previously?.focus();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
