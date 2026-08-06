import { FilBadge, formatDate, type FilStatut } from "./utils";
import type { Ticket } from "../../../types.ts";

interface TicketInfoSidebarProps {
  ticket: Ticket;
  filStatut: FilStatut;
}

export default function TicketInfoSidebar({ ticket, filStatut }: TicketInfoSidebarProps) {
  const closed = !!ticket.closed_at;
  return (
    <div className="w-72 shrink-0 space-y-4">
      <div className="glass-card rounded-2xl p-5 space-y-4">
        <p className="text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wide">
          Informations
        </p>
        <dl className="space-y-3.5 text-sm">
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">Domaine</dt>
            <dd className="text-gray-800 dark:text-gray-100 font-medium">{ticket.domaine}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">Posée le</dt>
            <dd className="text-gray-700 dark:text-gray-200">{formatDate(ticket.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Statut</dt>
            <dd>
              <FilBadge statut={filStatut} />
            </dd>
          </div>
          {closed && (
            <div>
              <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
                Clôturée le
              </dt>
              <dd className="text-gray-700 dark:text-gray-200">{formatDate(ticket.closed_at)}</dd>
            </div>
          )}
          <div className="pt-1 border-t border-gray-200 dark:border-white/10">
            <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
              Référence
            </dt>
            <dd className="text-gray-500 dark:text-gray-400 font-mono text-xs break-all">
              {ticket.id}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
