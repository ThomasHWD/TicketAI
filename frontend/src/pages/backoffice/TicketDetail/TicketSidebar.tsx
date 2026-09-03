import { History } from "lucide-react";
import type { MembreGroupe } from "../../../lib/api";
import type { Ticket } from "../../../types";
import { AssignSection, DetailsSection, RequesterSection, SidebarSection } from "./TicketSidebarSections";

export { ticketStatutLabel, StatutBadge } from "./TicketSidebarSections";

interface TicketSidebarProps {
  ticket: Ticket;
  isMine: boolean;
  assignLoading: boolean;
  assignError: string | null;
  selectedAssignee: string;
  currentUserId: string | undefined;
  validateurs: MembreGroupe[];
  validateursLoading: boolean;
  onShowWorkflow: () => void;
  onAssign: () => void;
  onUnassign: () => void;
  onSelectedAssigneeChange: (id: string) => void;
  onClearAssignError?: () => void;
}

export default function TicketSidebar({
  ticket,
  isMine,
  assignLoading,
  assignError,
  selectedAssignee,
  currentUserId,
  validateurs,
  validateursLoading,
  onShowWorkflow,
  onAssign,
  onUnassign,
  onSelectedAssigneeChange,
  onClearAssignError,
}: TicketSidebarProps) {
  const processing = ticket.statut_job === "EN_ATTENTE" || ticket.statut_job === "EN_COURS";
  const failed = ticket.statut_job === "ÉCHOUÉ";

  return (
    <aside className="w-full lg:w-72 shrink-0">
      <div className="glass-card rounded-2xl overflow-hidden">
        <DetailsSection ticket={ticket} processing={processing} failed={failed} />
        <RequesterSection ticket={ticket} />
        <AssignSection
          ticket={ticket}
          isMine={isMine}
          assignLoading={assignLoading}
          assignError={assignError}
          selectedAssignee={selectedAssignee}
          currentUserId={currentUserId}
          validateurs={validateurs}
          validateursLoading={validateursLoading}
          onAssign={onAssign}
          onUnassign={onUnassign}
          onSelectedAssigneeChange={onSelectedAssigneeChange}
          onClearAssignError={onClearAssignError}
        />
        <SidebarSection>
          <button
            onClick={onShowWorkflow}
            className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 hover:text-gray-800 dark:hover:bg-white/10 dark:hover:text-gray-100 transition-colors"
          >
            <History size={12} aria-hidden="true" />
            Voir l'historique
          </button>
        </SidebarSection>
      </div>
    </aside>
  );
}
