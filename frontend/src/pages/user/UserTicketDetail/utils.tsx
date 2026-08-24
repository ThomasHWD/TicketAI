import { Lock } from "lucide-react";
import type { TicketReponse } from "../../../types";

export type FilStatut = "closed" | "processing" | "answered" | "rejected";

export const FIL_STATUT_META: Record<FilStatut, { label: string; className: string }> = {
  closed: {
    label: "Clôturé",
    className:
      "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10",
  },
  answered: {
    label: "Répondu",
    className:
      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  },
  processing: {
    label: "En traitement",
    className:
      "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  },
  rejected: {
    label: "Rejetée",
    className:
      "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  },
};

export function FilBadge({ statut }: { statut: FilStatut }) {
  const { label, className } = FIL_STATUT_META[statut];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${className}`}
    >
      {statut === "closed" ? (
        <Lock size={10} aria-hidden="true" />
      ) : (
        <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" aria-hidden="true" />
      )}
      {label}
    </span>
  );
}

export function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function reponseVisible(r: TicketReponse) {
  return r.statut === "VALIDÉE" || r.statut === "CORRIGÉE" || r.canonique;
}

export function deriveFilStatut(
  closed: boolean,
  reponses: TicketReponse[],
  processing: boolean,
): FilStatut {
  const allRejected = reponses.length > 0 && reponses.every((r) => r.statut === "REJETÉE");
  if (closed) return allRejected ? "rejected" : "closed";
  if (processing || reponses.some((r) => r.statut === "EN_ATTENTE")) return "processing";
  if (reponses.some(reponseVisible)) return "answered";
  if (allRejected) return "rejected";
  return "processing";
}
