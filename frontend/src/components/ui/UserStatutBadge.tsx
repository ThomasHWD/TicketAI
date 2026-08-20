import { isProcessing, statutLabel } from "../../lib/ticketStatus";
import type { Ticket, StatutTicket } from "../../types";

type Variant = "processing" | "answered" | "closed" | "rejected";

const STYLES: Record<Variant, string> = {
  processing:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  answered:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  closed:
    "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10",
  rejected:
    "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
};

function resolveVariant(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
): Variant {
  if (closed) return "closed";
  if (processing) return "processing";
  if (statut === "REJETÉ") return "rejected";
  if (statut === "VALIDÉ" || canonique) return "answered";
  return "processing";
}

export default function UserStatutBadge({ ticket: t }: { ticket: Ticket }) {
  const processing = isProcessing(t.statut_job);
  const closed = !!t.closed_at;
  const statut = t.statut_ticket as StatutTicket;
  const variant = resolveVariant(statut, t.canonique, closed, processing);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${STYLES[variant]}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      {statutLabel(statut, t.canonique, closed, processing)}
    </span>
  );
}
