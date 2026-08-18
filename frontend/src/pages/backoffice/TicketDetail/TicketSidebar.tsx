import { Building2, History, MapPin, Phone, User, UserPlus, X } from "lucide-react";
import type { MembreGroupe } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import type { StatutTicket, Ticket } from "../../../types";
import { formatDate } from "./utils";

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function ticketStatutLabel(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean, reponseSource: string | null) {
  if (closed) return "Clôturé";
  if (failed) return "Échec";
  if (processing) return "En cours";
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return reponseSource === "HORS_DOMAINE" ? "Hors domaine" : "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean, reponseSource: string | null) {
  if (closed) return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
  if (failed) return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (processing) return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique) return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉ") return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "RÉPONDU" && reponseSource === "HORS_DOMAINE") return "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/20";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-600 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
}

function StatutBadge({ statut, canonique, closed, processing, failed, reponseSource }: { statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean; failed: boolean; reponseSource: string | null }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique, closed, processing, failed, reponseSource)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
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

  return (
    <div className="w-72 shrink-0 space-y-4">

      <div className="glass-card rounded-2xl p-5 space-y-4">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Informations</p>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Domaine</dt>
            <dd className="text-gray-700 dark:text-gray-200 font-medium">{ticket.domaine}</dd>
          </div>
          <div>
            <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Créé le</dt>
            <dd className="text-gray-700 dark:text-gray-200">{formatDate(ticket.created_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Statut</dt>
            <dd><StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} closed={!!ticket.closed_at} processing={isProcessing(ticket.statut_job)} failed={ticket.statut_job === "ÉCHOUÉ"} reponseSource={ticket.reponse_source ?? null} /></dd>
          </div>
          <div className="pt-1 border-t border-gray-200 dark:border-white/10">
            <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Référence</dt>
            <dd className="text-gray-500 dark:text-gray-400 font-mono text-xs break-all">{ticket.id}</dd>
          </div>
        </dl>
        <div className="pt-3 border-t border-gray-200 dark:border-white/10">
          <button
            onClick={onShowWorkflow}
            className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-200 dark:hover:bg-emerald-500/10 dark:hover:text-emerald-400 dark:hover:border-emerald-500/20 transition-colors"
          >
            <History size={13} aria-hidden="true" />
            Voir l'historique
          </button>
        </div>
      </div>

      <div className="glass-card rounded-2xl p-5 space-y-3">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Demandeur</p>
        <div className="flex items-center gap-3">
          <UserAvatar name={userName ?? "?"} size={40} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
              {userName ?? "Utilisateur inconnu"}
            </p>
            {ticket.user_titre && (
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                {ticket.user_titre}
              </p>
            )}
          </div>
        </div>
        <div className="space-y-1.5">
          {ticket.user_email && (
            <a
              href={`mailto:${ticket.user_email}`}
              className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate"
            >
              <User size={11} className="shrink-0" aria-hidden="true" />
              {ticket.user_email}
            </a>
          )}
          {ticket.user_telephone && (
            <a
              href={`tel:${ticket.user_telephone}`}
              className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
            >
              <Phone size={11} className="shrink-0" aria-hidden="true" />
              {ticket.user_telephone}
            </a>
          )}
          {ticket.user_departement && (
            <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <Building2 size={11} className="shrink-0" aria-hidden="true" />
              {ticket.user_departement}
            </p>
          )}
          {ticket.user_localisation && (
            <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <MapPin size={11} className="shrink-0" aria-hidden="true" />
              {ticket.user_localisation}
            </p>
          )}
        </div>
      </div>

      {!ticket.closed_at && (
        <div className="glass-card rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <UserPlus size={13} className="text-gray-400 dark:text-gray-500" aria-hidden="true" />
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Assignation</p>
          </div>

          {isMine ? (
            ticket.assigned_to ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2.5">
                  <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={32} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
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
                  className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
                >
                  <X size={12} aria-hidden="true" /> Remettre dans le pot commun
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <select
                  value={selectedAssignee}
                  onChange={(e) => onSelectedAssigneeChange(e.target.value)}
                  disabled={assignLoading}
                  className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-40"
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
                  className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                >
                  <UserPlus size={12} aria-hidden="true" /> Assigner
                </button>
              </div>
            )
          ) : ticket.assigned_to ? (
            <div className="flex items-center gap-2">
              <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={28} />
              <p className="text-sm text-gray-700 dark:text-gray-200 truncate">
                {ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"}
              </p>
            </div>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500">Non assigné</p>
          )}
        </div>
      )}

    </div>
  );
}
