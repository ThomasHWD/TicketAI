import { useState, useEffect } from "react";
import type { Ticket } from "../../types";

function clotureLabel(remaining: number, dateMs: number): string {
  if (remaining <= 0) return "Clôture auto imminente";
  if (remaining < 3_600_000) return "Clôture auto dans moins d'1 h";
  if (remaining < 86_400_000) return `Clôture auto dans ${Math.floor(remaining / 3_600_000)} h`;
  if (remaining < 2 * 86_400_000) return "Clôture auto demain";
  return `Clôture auto le ${new Date(dateMs).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}`;
}

export function AutoClotureTimer({ ticket, joursConfig }: { ticket: Ticket; joursConfig: number }) {
  const eligible =
    ticket.statut_ticket === "VALIDÉ" && !ticket.closed_at && !!ticket.validated_at;

  const dateClotureMs = eligible
    ? new Date(ticket.validated_at!).getTime() + joursConfig * 86_400_000
    : 0;

  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!eligible) return;
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, [eligible]);

  if (!eligible) return null;

  const remaining = dateClotureMs - now;
  const isUrgent  = remaining < 86_400_000;
  const isWarning = remaining < 2 * 86_400_000;

  return (
    <span
      aria-label={`Clôture automatique le ${new Date(dateClotureMs).toLocaleDateString("fr-FR")}`}
      className={`block text-[11px] leading-none mt-1.5 tabular-nums ${
        isUrgent  ? "font-medium text-red-600 dark:text-red-400"
        : isWarning ? "text-amber-700 dark:text-amber-400"
        : "text-muted-foreground"
      }`}
    >
      {clotureLabel(remaining, dateClotureMs)}
    </span>
  );
}
