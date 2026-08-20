import type { ReactNode } from "react";
import { Star } from "lucide-react";
import { FilBadge, formatDate, type FilStatut } from "./utils";
import type { Ticket } from "../../../types";

interface TicketInfoSidebarProps {
  ticket: Ticket;
  filStatut: FilStatut;
  joursAutoCloture: number;
}

function clotureValue(remaining: number, dateMs: number): string {
  if (remaining <= 0) return "Imminente";
  if (remaining < 3_600_000) return "Dans moins d'1 h";
  if (remaining < 86_400_000) return `Dans ${Math.floor(remaining / 3_600_000)} h`;
  if (remaining < 2 * 86_400_000) return "Demain";
  return new Date(dateMs).toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="text-sm text-gray-800 dark:text-gray-100">{children}</dd>
    </div>
  );
}

function StarDisplay({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          size={13}
          aria-hidden="true"
          className={
            i < value
              ? "text-amber-400 fill-amber-400"
              : "text-gray-300 dark:text-gray-600"
          }
        />
      ))}
      <span className="ml-1.5 text-xs text-gray-500 dark:text-gray-400">{value} / 5</span>
    </div>
  );
}

export default function TicketInfoSidebar({ ticket, filStatut, joursAutoCloture }: TicketInfoSidebarProps) {
  const closed = !!ticket.closed_at;
  const hasRatings = ticket.note_qualite !== null || ticket.note_delai !== null;

  const showCountdown =
    ticket.statut_ticket === "VALIDÉ" && !closed && !!ticket.validated_at;
  const dateClotureMs = showCountdown
    ? new Date(ticket.validated_at!).getTime() + joursAutoCloture * 86_400_000
    : null;
  const remaining = dateClotureMs !== null ? dateClotureMs - Date.now() : null;
  const isUrgent = remaining !== null && remaining < 86_400_000;
  const isWarning = remaining !== null && remaining < 2 * 86_400_000;

  return (
    <div className="w-full lg:w-72 shrink-0">
      <div className="glass-card rounded-2xl p-5 space-y-5">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          Informations
        </p>

        <dl className="space-y-4">
          <InfoRow label="Domaine">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700 dark:bg-white/10 dark:text-gray-300">
              {ticket.domaine}
            </span>
          </InfoRow>

          <InfoRow label="Posée le">{formatDate(ticket.created_at)}</InfoRow>

          <InfoRow label="Statut">
            <FilBadge statut={filStatut} />
          </InfoRow>

          {showCountdown && remaining !== null && dateClotureMs !== null && (
            <InfoRow label="Clôture automatique prévue">
              <span
                role="status"
                className={`text-sm tabular-nums ${
                  isUrgent
                    ? "font-medium text-red-600 dark:text-red-400"
                    : isWarning
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-gray-800 dark:text-gray-100"
                }`}
              >
                {clotureValue(remaining, dateClotureMs)}
              </span>
            </InfoRow>
          )}

          {closed && (
            <InfoRow label="Clôturée le">{formatDate(ticket.closed_at)}</InfoRow>
          )}
        </dl>

        {hasRatings && (
          <div className="pt-4 border-t border-gray-100 dark:border-white/[0.06] space-y-4">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Évaluation
            </p>
            <dl className="space-y-3.5">
              {ticket.note_qualite !== null && (
                <InfoRow label="Qualité de la réponse">
                  <StarDisplay value={ticket.note_qualite} />
                </InfoRow>
              )}
              {ticket.note_delai !== null && (
                <InfoRow label="Rapidité">
                  <StarDisplay value={ticket.note_delai} />
                </InfoRow>
              )}
            </dl>
          </div>
        )}

        <div className="pt-4 border-t border-gray-100 dark:border-white/[0.06]">
          <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Référence</dt>
          <dd className="text-xs text-gray-400 dark:text-gray-500 font-mono truncate" title={ticket.id}>
            {ticket.id}
          </dd>
        </div>
      </div>
    </div>
  );
}
