import type { StatutTicket } from "../types";

export function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

export function statutLabel(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
) {
  if (closed) return "Clôturé";
  if (processing) return "En cours de traitement";
  if (statut === "REJETÉ") return "Rejetée";
  if (statut === "VALIDÉ" || canonique) return "Répondu";
  return "En cours de traitement";
}

export function statutClass(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
) {
  if (closed)
    return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10";
  if (processing)
    return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ")
    return "bg-red-500/10 text-red-700 border-red-300/50 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (statut === "VALIDÉ" || canonique)
    return "bg-emerald-500/10 text-emerald-700 border-emerald-300/50 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  return "bg-blue-500/10 text-blue-700 border-blue-300/50 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
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
