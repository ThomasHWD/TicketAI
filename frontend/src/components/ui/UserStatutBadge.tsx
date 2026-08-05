import { isProcessing, statutLabel, statutClass } from "../../lib/ticketStatus";
import type { Ticket, StatutTicket } from "../../types.ts";

export default function UserStatutBadge({ ticket: t }: { ticket: Ticket }) {
  const processing = isProcessing(t.statut_job);
  const closed = !!t.closed_at;
  const statut = t.statut_ticket as StatutTicket;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${statutClass(statut, t.canonique, closed, processing)}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {statutLabel(statut, t.canonique, closed, processing)}
    </span>
  );
}
