import { Building2, History, MapPin, Phone, User, UserPlus, X } from "lucide-react";
import type { MembreGroupe } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import type { StatutTicket, Ticket } from "../../../types";
import { formatDate } from "./utils";

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

export function ticketStatutLabel(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
  failed: boolean,
  reponseSource: string | null,
) {
  if (closed) return "Clôturé";
  if (failed) return "Échec";
  if (processing) return "En attente de réponse";
  if (canonique || statut === "VALIDÉ") return "En cours";
  if (statut === "RÉPONDU") return "En attente";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
  failed: boolean,
  reponseSource: string | null,
) {
  if (closed) return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
  if (failed) return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (processing) return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20"; // En attente de réponse
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique || statut === "VALIDÉ") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
}

export function StatutBadge({
  statut,
  canonique,
  closed,
  processing,
  failed,
  reponseSource,
}: {
  statut: StatutTicket;
  canonique: boolean;
  closed: boolean;
  processing: boolean;
  failed: boolean;
  reponseSource: string | null;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique, closed, processing, failed, reponseSource)}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique, closed, processing, failed, reponseSource)}
    </span>
  );
}

interface TicketSidebarProps {
  ticket: Ticket;
  isMine: boolean;
  assignLoading: boolean;
  assignError: string | null;
  selectedAssignee: string;
  currentUserId: string | undefined;
  validateurs: MembreGroupe[];
  onShowWorkflow: () => void;
  onAssign: () => void;
  onUnassign: () => void;
  onSelectedAssigneeChange: (id: string) => void;
}

function SidebarSection({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 py-3.5 border-t border-gray-100 dark:border-white/[0.07] first:border-t-0 space-y-3">
      {children}
    </div>
  );
}

function SidebarLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-widest">
      {children}
    </p>
  );
}

export default function TicketSidebar({
  ticket,
  isMine,
  assignLoading,
  assignError,
  selectedAssignee,
  currentUserId,
  validateurs,
  onShowWorkflow,
  onAssign,
  onUnassign,
  onSelectedAssigneeChange,
}: TicketSidebarProps) {
  const userName = ticket.user_nom_complet || ticket.user_email;
  const processing = isProcessing(ticket.statut_job);
  const failed = ticket.statut_job === "ÉCHOUÉ";

  return (
    <aside className="w-72 shrink-0">
      <div className="glass-card rounded-2xl overflow-hidden">

        {/* Statut & Détails */}
        <SidebarSection>
          <SidebarLabel>Détails</SidebarLabel>
          <dl className="space-y-2.5 text-sm">
            <div className="flex items-start justify-between gap-2">
              <dt className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 shrink-0">Statut</dt>
              <dd>
                <StatutBadge
                  statut={ticket.statut_ticket}
                  canonique={ticket.canonique}
                  closed={!!ticket.closed_at}
                  processing={processing}
                  failed={failed}
                  reponseSource={ticket.reponse_source ?? null}
                />
              </dd>
            </div>
            <div className="flex items-start justify-between gap-2">
              <dt className="text-xs text-gray-400 dark:text-gray-500 mt-px shrink-0">Créé le</dt>
              <dd className="text-xs text-gray-600 dark:text-gray-300 text-right">{formatDate(ticket.created_at)}</dd>
            </div>
            {ticket.closed_at && (
              <div className="flex items-start justify-between gap-2">
                <dt className="text-xs text-gray-400 dark:text-gray-500 mt-px shrink-0">Clôturé le</dt>
                <dd className="text-xs text-gray-600 dark:text-gray-300 text-right">{formatDate(ticket.closed_at)}</dd>
              </div>
            )}
            <div className="flex items-start justify-between gap-2">
              <dt className="text-xs text-gray-400 dark:text-gray-500 mt-px shrink-0">Référence</dt>
              <dd className="text-xs font-mono text-gray-400 dark:text-gray-500 truncate min-w-0" title={ticket.id}>{ticket.id}</dd>
            </div>
          </dl>
        </SidebarSection>

        {/* Demandeur */}
        <SidebarSection>
          <SidebarLabel>Demandeur</SidebarLabel>
          <div className="flex items-center gap-2.5">
            <UserAvatar name={userName ?? "?"} size={32} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-tight">
                {userName ?? "Utilisateur inconnu"}
              </p>
              {ticket.user_titre && (
                <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">{ticket.user_titre}</p>
              )}
            </div>
          </div>
          <div className="space-y-1.5">
            {ticket.user_email && (
              <a
                href={`mailto:${ticket.user_email}`}
                className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate"
              >
                <User size={11} className="shrink-0" aria-hidden="true" />
                {ticket.user_email}
              </a>
            )}
            {ticket.user_telephone && (
              <a
                href={`tel:${ticket.user_telephone}`}
                className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
              >
                <Phone size={11} className="shrink-0" aria-hidden="true" />
                {ticket.user_telephone}
              </a>
            )}
            {ticket.user_departement && (
              <p className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
                <Building2 size={11} className="shrink-0" aria-hidden="true" />
                {ticket.user_departement}
              </p>
            )}
            {ticket.user_localisation && (
              <p className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
                <MapPin size={11} className="shrink-0" aria-hidden="true" />
                {ticket.user_localisation}
              </p>
            )}
          </div>
        </SidebarSection>

        {/* Assignation */}
        {!ticket.closed_at && (
          <SidebarSection>
            <SidebarLabel>Assignation</SidebarLabel>
            {isMine ? (
              ticket.assigned_to ? (
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2">
                    <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={28} />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate leading-tight">
                        {ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"}
                      </p>
                      {ticket.assigned_to_email && (
                        <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{ticket.assigned_to_email}</p>
                      )}
                    </div>
                  </div>
                  {assignError && <p className="text-xs text-red-600 dark:text-red-400">{assignError}</p>}
                  <button
                    onClick={onUnassign}
                    disabled={assignLoading}
                    className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 dark:border-white/15 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
                  >
                    <X size={11} aria-hidden="true" />
                    Remettre dans le pot commun
                  </button>
                </div>
              ) : (
                <div className="space-y-2">
                  <select
                    value={selectedAssignee}
                    onChange={(e) => onSelectedAssigneeChange(e.target.value)}
                    disabled={assignLoading}
                    className="w-full text-xs text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-40"
                  >
                    <option value="">Assigner à…</option>
                    {validateurs
                      .filter((v) => v.id !== currentUserId)
                      .map((v) => (
                        <option key={v.id} value={v.id}>
                          {[v.prenom, v.nom].filter(Boolean).join(" ") || v.email}
                        </option>
                      ))}
                  </select>
                  {assignError && <p className="text-xs text-red-600 dark:text-red-400">{assignError}</p>}
                  <button
                    onClick={onAssign}
                    disabled={assignLoading || !selectedAssignee}
                    className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                  >
                    <UserPlus size={11} aria-hidden="true" />
                    Assigner
                  </button>
                </div>
              )
            ) : ticket.assigned_to ? (
              <div className="flex items-center gap-2">
                <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={28} />
                <p className="text-xs text-gray-700 dark:text-gray-200 truncate">
                  {ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"}
                </p>
              </div>
            ) : (
              <p className="text-xs text-gray-400 dark:text-gray-500">Non assigné</p>
            )}
          </SidebarSection>
        )}

        {/* Actions */}
        <SidebarSection>
          <button
            onClick={onShowWorkflow}
            className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-lg border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 hover:text-gray-800 dark:hover:bg-white/10 dark:hover:text-gray-100 transition-colors"
          >
            <History size={12} aria-hidden="true" />
            Voir l'historique
          </button>
        </SidebarSection>

      </div>
    </aside>
  );
}
