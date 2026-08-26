import { useState, useRef, useEffect } from "react";
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
  const [dropdownPos, setDropdownPos] = useState({ top: 0, right: 0 });
  const [dismissed, setDismissed] = useState<Set<string>>(getDismissed);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

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
      setDropdownPos({ top: rect.bottom + window.scrollY + 8, right: window.innerWidth - rect.right });
    }
    setOpen((v) => !v);
  }

  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      const target = e.target as Node;
      if (
        btnRef.current && !btnRef.current.contains(target) &&
        dropdownRef.current && !dropdownRef.current.contains(target)
      ) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
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
      style={{ top: dropdownPos.top, right: dropdownPos.right }}
      className="fixed w-80 max-h-[28rem] overflow-y-auto rounded-2xl glass-card z-[9999]"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/50 dark:border-white/10 sticky top-0 glass-card rounded-t-2xl flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
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
  ) : null;

  return (
    <div className="shrink-0">
      <button
        ref={btnRef}
        onClick={handleToggle}
        className="relative p-2 rounded-lg hover:bg-white/60 dark:hover:bg-white/10 text-gray-600 dark:text-gray-400 transition-colors"
        aria-label={`${totalBadge} notification(s)`}
        aria-expanded={open}
      >
        <Bell size={18} />
        {totalBadge > 0 && (
          <span
            className="absolute top-1 right-1 min-w-[16px] h-4 px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center leading-none"
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
