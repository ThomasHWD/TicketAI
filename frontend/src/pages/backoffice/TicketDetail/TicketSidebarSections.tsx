import { Building2, Check, Copy, MapPin, Phone, User, UserPlus, X } from "lucide-react";
import { useState } from "react";
import type { MembreGroupe } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import type { StatutTicket, Ticket } from "../../../types";
import { formatDate } from "./utils";

// ─── Primitives ───────────────────────────────────────────────────────────────

export function SidebarSection({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 py-3.5 border-t border-gray-100 dark:border-white/[0.07] first:border-t-0 space-y-3">
      {children}
    </div>
  );
}

export function SidebarLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-[0.06em]">
      {children}
    </p>
  );
}

// ─── StatutBadge ─────────────────────────────────────────────────────────────

export function ticketStatutLabel(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean) {
  if (closed) return "Clôturé";
  if (failed) return "Échec";
  if (processing) return "En attente de réponse";
  if (canonique || statut === "VALIDÉ") return "Traité";
  if (statut === "RÉPONDU") return "En attente";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean) {
  if (closed)    return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
  if (failed)    return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (processing) return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique || statut === "VALIDÉ") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
}

export function StatutBadge({ statut, canonique, closed, processing, failed }: {
  statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean; failed: boolean;
}) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique, closed, processing, failed)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique, closed, processing, failed)}
    </span>
  );
}

// ─── DetailsSection ───────────────────────────────────────────────────────────

export function DetailsSection({ ticket, processing, failed }: { ticket: Ticket; processing: boolean; failed: boolean }) {
  const [copied, setCopied] = useState(false);
  function copyRef() {
    const text = ticket.id;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }
  function fallbackCopy(text: string) {
    const el = document.createElement("textarea");
    el.value = text;
    el.style.position = "fixed";
    el.style.opacity = "0";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  }
  return (
    <SidebarSection>
      <SidebarLabel>Détails</SidebarLabel>
      <dl className="space-y-2.5 text-sm">
        <div className="flex items-start justify-between gap-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 shrink-0">Statut</dt>
          <dd>
            <StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} closed={!!ticket.closed_at} processing={processing} failed={failed} />
          </dd>
        </div>
        <div className="flex items-start justify-between gap-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400 mt-px shrink-0">Créé le</dt>
          <dd className="text-xs text-gray-600 dark:text-gray-300 text-right">{formatDate(ticket.created_at)}</dd>
        </div>
        {ticket.closed_at && (
          <div className="flex items-start justify-between gap-2">
            <dt className="text-xs text-gray-500 dark:text-gray-400 mt-px shrink-0">Clôturé le</dt>
            <dd className="text-xs text-gray-600 dark:text-gray-300 text-right">{formatDate(ticket.closed_at)}</dd>
          </div>
        )}
        <div className="flex items-start justify-between gap-2">
          <dt className="text-xs text-gray-500 dark:text-gray-400 mt-px shrink-0">Référence</dt>
          <dd className="flex items-center gap-1 min-w-0">
            <span className="text-xs font-mono text-gray-500 dark:text-gray-400 cursor-default" title={`Référence complète : ${ticket.id}`}>
              {ticket.id.slice(0, 8)}…
            </span>
            <button onClick={copyRef} className="shrink-0 p-0.5 rounded text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 transition-colors" aria-label="Copier la référence" title="Copier la référence complète">
              {copied ? <Check size={11} className="text-emerald-500" aria-hidden="true" /> : <Copy size={11} aria-hidden="true" />}
            </button>
          </dd>
        </div>
      </dl>
    </SidebarSection>
  );
}

// ─── RequesterSection ─────────────────────────────────────────────────────────

export function RequesterSection({ ticket }: { ticket: Ticket }) {
  const userName = ticket.user_nom_complet || ticket.user_email;
  return (
    <SidebarSection>
      <SidebarLabel>Demandeur</SidebarLabel>
      <div className="flex items-center gap-2.5">
        <UserAvatar name={userName ?? "?"} size={32} />
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-tight">{userName ?? "Utilisateur inconnu"}</p>
          {ticket.user_titre && <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{ticket.user_titre}</p>}
        </div>
      </div>
      <div className="space-y-1.5">
        {ticket.user_email && (
          <a href={`mailto:${ticket.user_email}`} className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate">
            <User size={11} className="shrink-0" aria-hidden="true" />{ticket.user_email}
          </a>
        )}
        {ticket.user_telephone && (
          <a href={`tel:${ticket.user_telephone}`} className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors">
            <Phone size={11} className="shrink-0" aria-hidden="true" />{ticket.user_telephone}
          </a>
        )}
        {ticket.user_departement && (
          <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <Building2 size={11} className="shrink-0" aria-hidden="true" />{ticket.user_departement}
          </p>
        )}
        {ticket.user_localisation && (
          <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <MapPin size={11} className="shrink-0" aria-hidden="true" />{ticket.user_localisation}
          </p>
        )}
      </div>
    </SidebarSection>
  );
}

// ─── AssignSection ────────────────────────────────────────────────────────────

interface AssignSectionProps {
  ticket: Ticket;
  isMine: boolean;
  assignLoading: boolean;
  assignError: string | null;
  selectedAssignee: string;
  currentUserId: string | undefined;
  validateurs: MembreGroupe[];
  validateursLoading: boolean;
  onAssign: () => void;
  onUnassign: () => void;
  onSelectedAssigneeChange: (id: string) => void;
  onClearAssignError?: () => void;
}

export function AssignSection({
  ticket, isMine, assignLoading, assignError, selectedAssignee,
  currentUserId, validateurs, validateursLoading,
  onAssign, onUnassign, onSelectedAssigneeChange, onClearAssignError,
}: AssignSectionProps) {
  if (ticket.closed_at) return null;
  const assigneeName = ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur";
  return (
    <SidebarSection>
      <SidebarLabel>Assignation</SidebarLabel>
      {isMine ? (
        ticket.assigned_to ? (
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <UserAvatar name={assigneeName} size={28} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate leading-tight">{assigneeName}</p>
                {ticket.assigned_to_email && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{ticket.assigned_to_email}</p>}
              </div>
            </div>
            {assignError && (
              <p className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                {assignError}
                {onClearAssignError && <button onClick={onClearAssignError} className="underline hover:no-underline shrink-0" aria-label="Fermer l'erreur">Fermer</button>}
              </p>
            )}
            <button onClick={onUnassign} disabled={assignLoading} className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-md border border-gray-200 dark:border-white/15 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors">
              <X size={11} aria-hidden="true" />Remettre dans le pot commun
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <select value={selectedAssignee} onChange={(e) => onSelectedAssigneeChange(e.target.value)} disabled={assignLoading} aria-label="Assigner à" className="w-full text-xs text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-md px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-40">
              <option value="">{validateursLoading ? "Chargement…" : validateurs.length === 0 ? "Aucun validateur disponible" : "Assigner à…"}</option>
              {validateurs.filter((v) => v.id !== currentUserId).map((v) => (
                <option key={v.id} value={v.id}>{[v.prenom, v.nom].filter(Boolean).join(" ") || v.email}</option>
              ))}
            </select>
            {assignError && (
              <p className="text-xs text-red-600 dark:text-red-400 flex items-center gap-1.5">
                {assignError}
                {onClearAssignError && <button onClick={onClearAssignError} className="underline hover:no-underline shrink-0" aria-label="Fermer l'erreur">Fermer</button>}
              </p>
            )}
            <button onClick={onAssign} disabled={assignLoading || !selectedAssignee} className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors">
              <UserPlus size={11} aria-hidden="true" />Assigner
            </button>
          </div>
        )
      ) : ticket.assigned_to ? (
        <div className="flex items-center gap-2">
          <UserAvatar name={assigneeName} size={28} />
          <p className="text-xs text-gray-700 dark:text-gray-200 truncate">{assigneeName}</p>
        </div>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400">Non assigné</p>
      )}
    </SidebarSection>
  );
}
