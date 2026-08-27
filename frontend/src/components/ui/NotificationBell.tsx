import { useState, useRef, useEffect, useId } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, MessageSquare, UserPlus } from "lucide-react";
import {
  getMyAssignedTickets,
  getNotifications,
  marquerNotificationLue,
  toutMarquerLu,
} from "../../lib/api";
import type { Notification, Ticket } from "../../types";

function formatDate(iso: string | null) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

const DISMISSED_KEY = "assignations_dismissed";

function getDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISSED_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function saveDismissed(ids: Set<string>) {
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...ids]));
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0, width: 320 });
  const [dismissed, setDismissed] = useState<Set<string>>(getDismissed);
  const [liveMessage, setLiveMessage] = useState("");
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  const prevBadge = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showFade, setShowFade] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const panelId = useId();

  const { data: assigned = [] } = useQuery<Ticket[]>({
    queryKey: ["mes-assignations"],
    queryFn: getMyAssignedTickets,
  });

  const { data: notifications = [] } = useQuery<Notification[]>({
    queryKey: ["notifications"],
    queryFn: getNotifications,
  });

  // Retire du dismissed les tickets qui ne sont plus assignés (désassignés puis réassignés reparaîtront)
  useEffect(() => {
    if (assigned.length === 0 && dismissed.size === 0) return;
    const assignedIds = new Set(assigned.map((t) => String(t.id)));
    const next = new Set([...dismissed].filter((id) => assignedIds.has(id)));
    if (next.size !== dismissed.size) {
      setDismissed(next);
      saveDismissed(next);
    }
  }, [assigned, dismissed]);

  const visibleAssigned = assigned.filter((t) => !dismissed.has(String(t.id)));
  const totalBadge = visibleAssigned.length + notifications.length;

  // Announce new notifications to screen readers
  useEffect(() => {
    if (totalBadge > prevBadge.current) {
      setLiveMessage(`${totalBadge} notification${totalBadge > 1 ? "s" : ""}`);
    }
    prevBadge.current = totalBadge;
  }, [totalBadge]);

  function dismissAssignation(id: string) {
    const next = new Set(dismissed);
    next.add(id);
    setDismissed(next);
    saveDismissed(next);
  }

  function dismissAllAssignations() {
    const next = new Set(dismissed);
    visibleAssigned.forEach((t) => next.add(String(t.id)));
    setDismissed(next);
    saveDismissed(next);
  }

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

  // Focus management: into panel on open, back to button on close
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

  // Dismiss on click-outside or Escape
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
  }, [open]);

  // Scroll fade: show gradient when content overflows the visible area
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

  async function handleNotifClick(notif: Notification) {
    setOpen(false);
    navigate(`/historique/${notif.ticket_id}`);
    await marquerNotificationLue(notif.id);
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  async function handleToutLire() {
    await toutMarquerLu();
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  const dropdown = open ? (
    <div
      ref={dropdownRef}
      id={panelId}
      role="dialog"
      aria-label="Notifications"
      tabIndex={-1}
      style={{ top: dropdownPos.top, right: dropdownPos.right, width: dropdownPos.width }}
      className="fixed rounded-2xl glass-card z-[9999] focus:outline-none"
    >
      <div ref={scrollRef} className="max-h-[28rem] overflow-y-auto rounded-2xl">
      {/* Header — solid semi-transparent bg avoids nesting two backdrop-filter layers */}
      <div className="px-4 py-3 border-b border-white/50 dark:border-white/10 sticky top-0 bg-white/95 dark:bg-[#141416]/95 backdrop-blur-sm rounded-t-2xl flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          Notifications
        </p>
        {notifications.length > 0 && (
          <button
            onClick={handleToutLire}
            className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            <CheckCheck size={12} />
            Tout lire
          </button>
        )}
      </div>

      {visibleAssigned.length === 0 && notifications.length === 0 && (
        <p className="px-4 py-6 text-sm text-center text-gray-500 dark:text-gray-400">
          Aucune notification
        </p>
      )}

      {/* Section assignations */}
      {visibleAssigned.length > 0 && (
        <>
          <div className="px-4 pt-3 pb-1 flex items-center justify-between">
            <p className="text-[10px] font-semibold text-violet-500 dark:text-violet-400 uppercase tracking-wider flex items-center gap-1">
              <UserPlus size={10} /> Assignations
            </p>
            <button
              onClick={dismissAllAssignations}
              className="flex items-center gap-1 text-xs text-violet-500 dark:text-violet-400 hover:underline"
            >
              <CheckCheck size={12} />
              Tout effacer
            </button>
          </div>
          <ul role="list">
            {visibleAssigned.map((t) => (
              <li key={t.id}>
                <button
                  onClick={() => { navigate(`/tickets/${t.id}`); setOpen(false); dismissAssignation(String(t.id)); }}
                  className="w-full text-left px-4 py-2.5 hover:bg-white/60 dark:hover:bg-white/10 transition-colors border-b border-white/50 dark:border-white/10 last:border-0"
                >
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                    {t.objet ?? t.question}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{t.domaine}</p>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {/* Section réponses */}
      {notifications.length > 0 && (
        <>
          <div className="px-4 pt-3 pb-1">
            <p className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider flex items-center gap-1">
              <MessageSquare size={10} /> Réponses à vos tickets
            </p>
          </div>
          <ul role="list">
            {notifications.map((n) => (
              <li key={n.id}>
                <button
                  onClick={() => handleNotifClick(n)}
                  className="w-full text-left px-4 py-2.5 bg-emerald-50/60 dark:bg-emerald-500/10 hover:bg-emerald-50 dark:hover:bg-emerald-500/20 transition-colors border-b border-white/50 dark:border-white/10 last:border-0"
                >
                  <div className="flex items-start gap-2">
                    <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" aria-hidden="true" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                        {n.ticket_objet ?? n.ticket_question ?? "Ticket"}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Réponse disponible · {formatDate(n.created_at)}
                      </p>
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      </div>
      {showFade && (
        <div
          aria-hidden="true"
          className="absolute bottom-0 inset-x-0 h-10 pointer-events-none rounded-b-2xl bg-gradient-to-t from-white/90 dark:from-[#141416]/90 to-transparent"
        />
      )}
    </div>
  ) : null;

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
        className="relative min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-gray-400 transition-colors"
      >
        <Bell size={18} />
        {totalBadge > 0 && (
          <span
            className="absolute top-1 right-1 min-w-[16px] h-4 px-1 bg-amber-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center leading-none tabular-nums"
            aria-hidden="true"
          >
            {totalBadge > 9 ? "9+" : totalBadge}
          </span>
        )}
      </button>
      {createPortal(dropdown, document.body)}
    </div>
  );
}
