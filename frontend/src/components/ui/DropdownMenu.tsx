import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MoreHorizontal, type LucideIcon } from "lucide-react";

export interface MenuAction {
  label: string;
  icon: LucideIcon;
  onSelect: () => void;
  disabled?: boolean;
  /** Raison de l'inactivation, affichée en `title` — un bouton grisé sans motif est une impasse. */
  disabledReason?: string;
  /** Action destructrice : rouge, et séparée du reste. */
  danger?: boolean;
}

const MENU_WIDTH = 236;
const MARGIN = 8;

/** Actions menu in a portal — trigger sits inside an `overflow-hidden` card; in-place rendering gets clipped. Position is screen-coordinates; scroll closes it rather than letting it float. */
export default function DropdownMenu({
  actions,
  ariaLabel,
}: {
  actions: MenuAction[];
  ariaLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger || !menu) return;

    const rect = trigger.getBoundingClientRect();
    const height = menu.offsetHeight;
    const dessous = rect.bottom + 6;
    const top = dessous + height > window.innerHeight - MARGIN ? rect.top - height - 6 : dessous;

    setPosition({
      top: Math.max(MARGIN, top),
      left: Math.max(MARGIN, rect.right - MENU_WIDTH),
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const surClicExterieur = (e: MouseEvent) => {
      const cible = e.target as Node;
      if (menuRef.current?.contains(cible) || triggerRef.current?.contains(cible)) return;
      setOpen(false);
    };
    const surTouche = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const fermer = () => setOpen(false);

    document.addEventListener("mousedown", surClicExterieur);
    document.addEventListener("keydown", surTouche);
    window.addEventListener("resize", fermer);
    // `true` : capture les défilements de n'importe quel conteneur, pas seulement window.
    window.addEventListener("scroll", fermer, true);
    return () => {
      document.removeEventListener("mousedown", surClicExterieur);
      document.removeEventListener("keydown", surTouche);
      window.removeEventListener("resize", fermer);
      window.removeEventListener("scroll", fermer, true);
    };
  }, [open]);

  const dernierNonDanger = actions.map((a) => !!a.danger).lastIndexOf(false);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className={`rounded-lg p-1.5 transition-colors
          ${open ? "bg-gray-100 text-gray-700 dark:bg-white/10 dark:text-gray-200" : "text-muted-foreground hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-white/10 dark:hover:text-gray-200"}
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500`}
      >
        <MoreHorizontal size={16} />
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{ top: position.top, left: position.left, width: MENU_WIDTH }}
            className="fixed z-[60] overflow-hidden rounded-xl border border-gray-200 bg-white p-1 shadow-xl
              dark:border-white/12 dark:bg-[#1a1a1d] dark:shadow-black/50"
          >
            {actions.map((action, i) => (
              <div key={action.label}>
                {action.danger && i === dernierNonDanger + 1 && i > 0 && (
                  <div className="my-1 border-t border-gray-100 dark:border-white/8" />
                )}
                <button
                  type="button"
                  role="menuitem"
                  disabled={action.disabled}
                  title={action.disabled ? action.disabledReason : undefined}
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpen(false);
                    action.onSelect();
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors
                    disabled:cursor-not-allowed disabled:opacity-40
                    ${
                      action.danger
                        ? "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/8"
                    }`}
                >
                  <action.icon size={15} className="shrink-0 opacity-70" />
                  {action.label}
                </button>
              </div>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
