import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  getMyAssignedTickets,
  getNotifications,
  marquerNotificationLue,
  toutMarquerLu,
} from "../lib/api";
import type { Notification, Ticket } from "../types";

export function formatNotifDate(iso: string | null) {
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

export function useNotificationBell() {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(getDismissed);
  const [liveMessage, setLiveMessage] = useState("");
  const prevBadge = useRef(0);
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

  return {
    open, setOpen,
    liveMessage,
    visibleAssigned,
    notifications,
    totalBadge,
    dismissAssignation,
    dismissAllAssignations,
    handleNotifClick,
    handleToutLire,
  };
}
