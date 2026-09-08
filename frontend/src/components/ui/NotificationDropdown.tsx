import { CheckCheck, MessageSquare, UserPlus } from "lucide-react";
import type { Notification, Ticket } from "../../types";
import { formatNotifDate } from "../../hooks/useNotificationBell";

interface NotificationDropdownProps {
  panelId: string;
  dropdownPos: { top: number; right: number; width: number };
  dropdownRef: React.RefObject<HTMLDivElement | null>;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  showFade: boolean;
  visibleAssigned: Ticket[];
  notifications: Notification[];
  onToutLire: () => void;
  onNotifClick: (n: Notification) => void;
  onDismissAll: () => void;
  onAssignClick: (t: Ticket) => void;
}

export function NotificationDropdown({
  panelId, dropdownPos, dropdownRef, scrollRef, showFade,
  visibleAssigned, notifications,
  onToutLire, onNotifClick, onDismissAll, onAssignClick,
}: NotificationDropdownProps) {
  return (
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
              onClick={onToutLire}
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

        {visibleAssigned.length > 0 && (
          <>
            <div className="px-4 pt-3 pb-1 flex items-center justify-between">
              <p className="text-[10px] font-semibold text-violet-500 dark:text-violet-400 uppercase tracking-wider flex items-center gap-1">
                <UserPlus size={10} /> Assignations
              </p>
              <button
                onClick={onDismissAll}
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
                    onClick={() => onAssignClick(t)}
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
                    onClick={() => onNotifClick(n)}
                    className="w-full text-left px-4 py-2.5 bg-emerald-50/60 dark:bg-emerald-500/10 hover:bg-emerald-50 dark:hover:bg-emerald-500/20 transition-colors border-b border-white/50 dark:border-white/10 last:border-0"
                  >
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" aria-hidden="true" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                          {n.ticket_objet ?? n.ticket_question ?? "Ticket"}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                          Réponse disponible · {formatNotifDate(n.created_at)}
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
  );
}
