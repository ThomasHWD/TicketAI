import { useState, useRef, useEffect, useId } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { useNotificationBell } from "../../hooks/useNotificationBell";
import { NotificationDropdown } from "./NotificationDropdown";

export default function NotificationBell() {
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0, width: 320 });
  const [showFade, setShowFade] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  const panelId = useId();
  const navigate = useNavigate();

  const {
    open, setOpen,
    liveMessage,
    visibleAssigned,
    notifications,
    totalBadge,
    dismissAssignation,
    dismissAllAssignations,
    handleNotifClick,
    handleToutLire,
  } = useNotificationBell();

  function handleToggle() {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      const panelWidth = Math.min(320, window.innerWidth - 16);
      const rightFromEdge = window.innerWidth - rect.right;
      const clampedRight = Math.max(8, Math.min(rightFromEdge, window.innerWidth - panelWidth - 8));
      setDropdownPos({ top: rect.bottom + window.scrollY + 8, right: clampedRight, width: panelWidth });
    }
    setOpen((v) => !v);
  }

  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      const firstFocusable = dropdownRef.current?.querySelector<HTMLElement>("button, [href]");
      (firstFocusable ?? dropdownRef.current)?.focus();
    } else if (wasOpen.current) {
      wasOpen.current = false;
      btnRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onMouseDown(e: MouseEvent) {
      const target = e.target as Node;
      if (
        btnRef.current && !btnRef.current.contains(target) &&
        dropdownRef.current && !dropdownRef.current.contains(target)
      ) setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, setOpen]);

  useEffect(() => {
    if (!open) return;
    const el = scrollRef.current;
    if (!el) return;
    function check() {
      if (!el) return;
      setShowFade(el.scrollHeight > el.clientHeight && el.scrollTop + el.clientHeight < el.scrollHeight - 8);
    }
    check();
    el.addEventListener("scroll", check, { passive: true });
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", check);
      ro.disconnect();
    };
  }, [open]);

  return (
    <div className="shrink-0">
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {liveMessage}
      </span>
      <button
        ref={btnRef}
        onClick={handleToggle}
        aria-label={`${totalBadge} notification${totalBadge !== 1 ? "s" : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={panelId}
        className="relative min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-muted-foreground transition-colors"
      >
        <Bell size={18} />
        {totalBadge > 0 && (
          <span
            className="absolute top-1 right-1 min-w-[16px] h-4 px-1 bg-amber-500 text-amber-950 text-[9px] font-bold rounded-full flex items-center justify-center leading-none tabular-nums"
            aria-hidden="true"
          >
            {totalBadge > 9 ? "9+" : totalBadge}
          </span>
        )}
      </button>
      {createPortal(
        open ? (
          <NotificationDropdown
            panelId={panelId}
            dropdownPos={dropdownPos}
            dropdownRef={dropdownRef}
            scrollRef={scrollRef}
            showFade={showFade}
            visibleAssigned={visibleAssigned}
            notifications={notifications}
            onToutLire={handleToutLire}
            onNotifClick={handleNotifClick}
            onDismissAll={dismissAllAssignations}
            onAssignClick={(t) => {
              navigate(`/tickets/${t.id}`);
              setOpen(false);
              dismissAssignation(String(t.id));
            }}
          />
        ) : null,
        document.body,
      )}
    </div>
  );
}
