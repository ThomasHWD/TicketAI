import { getStatutMeta } from "../../lib/ticketFilters";
import type { StatutTicket } from "../../types";

export function StatusBadge({
  statut,
  canonique,
  closed,
  processing,
  reponseSource,
}: {
  statut: StatutTicket;
  canonique: boolean;
  closed: boolean;
  processing: boolean;
  reponseSource: string | null;
}) {
  const meta = getStatutMeta(statut, canonique, closed, processing, reponseSource);
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border whitespace-nowrap ${meta.badgeClass}`}
      title={meta.title}
    >
      <span className={`w-1.5 h-1.5 rounded-full bg-current shrink-0 ${meta.dotClass ?? ""}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}

export function DomaineBadge({ domaine }: { domaine: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200 dark:bg-white/10 dark:text-muted-foreground dark:border-white/10 whitespace-nowrap">
      {domaine}
    </span>
  );
}
