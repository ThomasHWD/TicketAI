import type { StatutTicket } from "../types";

export type FilterView = "tous" | "en_attente" | "en_cours" | "clotures";

export const FILTER_TABS: { value: FilterView; label: string; title: string }[] = [
  { value: "tous",       label: "Tous",       title: "Tous les tickets ouverts" },
  { value: "en_attente", label: "En attente", title: "Tickets en attente de votre validation" },
  { value: "en_cours",   label: "Traités",    title: "Tickets traités : canoniques et déjà validés" },
  { value: "clotures",   label: "Clôturés",   title: "Tickets fermés définitivement" },
];

export const TAB_HINTS: Record<FilterView, string> = {
  tous:       "Vue complète — utilisez les onglets ou les raccourcis 1–4 pour filtrer par statut.",
  en_attente: "Ces tickets attendent votre validation — la réponse IA est prête à être vérifiée.",
  en_cours:   "Tickets traités ou canoniques — aucune action requise de votre part.",
  clotures:   "Tickets fermés définitivement — disponibles en consultation uniquement.",
};

export const LEGEND_ITEMS = [
  { color: "bg-sky-400",     label: "Nouvelle",     desc: "Pas encore répondu" },
  { color: "bg-amber-400",   label: "Suggestion",   desc: "Réponse à vérifier" },
  { color: "bg-emerald-400", label: "Traitée",       desc: "Validée ou canonique" },
  { color: "bg-red-400",     label: "Rejetée",      desc: "Rejetée" },
  { color: "bg-purple-400",  label: "Hors domaine", desc: "Hors périmètre" },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function matchesFilter(t: any, filter: FilterView): boolean {
  if (filter === "tous" || filter === "clotures") return true;
  if (filter === "en_attente")
    return t.statut_ticket === "NOUVEAU" ||
      (t.statut_ticket === "RÉPONDU" && !t.canonique);
  if (filter === "en_cours")
    return t.canonique === true || t.statut_ticket === "VALIDÉ";
  return true;
}

export interface StatutMeta {
  label: string;
  badgeClass: string;
  dotClass?: string;
  title: string;
}

export function getStatutMeta(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
  reponseSource: string | null,
): StatutMeta {
  if (closed) return {
    label: "Clôturé",
    title: "Ticket fermé",
    badgeClass: "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-400 dark:border-white/10",
  };
  if (processing) return {
    label: "En cours",
    title: "Traitement en cours par l'IA",
    badgeClass: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
    dotClass: "animate-pulse",
  };
  if (canonique) return {
    label: "Traitée",
    title: "Réponse canonique — servie automatiquement",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  };
  if (statut === "VALIDÉ") return {
    label: "Traitée",
    title: "Réponse validée par un expert",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  };
  if (statut === "RÉPONDU" && reponseSource === "HORS_DOMAINE") return {
    label: "Hors domaine",
    title: "Question hors de votre périmètre",
    badgeClass: "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/20",
  };
  if (statut === "RÉPONDU") return {
    label: "Suggestion",
    title: "Réponse proposée — votre vérification est demandée",
    badgeClass: "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20",
  };
  if (statut === "REJETÉ") return {
    label: "Rejetée",
    title: "Réponse rejetée par un validateur",
    badgeClass: "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  };
  return {
    label: "Nouvelle",
    title: "Nouveau ticket — réponse en cours de génération",
    badgeClass: "bg-sky-50 text-sky-600 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20",
  };
}

export function getListErrorMessage(error: unknown): { title: string; detail: string; loginPath?: boolean } {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return { title: "Pas de connexion", detail: "Vérifiez votre connexion internet et réessayez." };
  }
  if (error && typeof error === "object") {
    const status = (error as Record<string, unknown>).status;
    if (status === 401 || status === 403)
      return { title: "Session expirée", detail: "Votre session a expiré.", loginPath: true };
    if (typeof status === "number" && status >= 500)
      return { title: "Serveur temporairement indisponible", detail: "Réessayez dans quelques minutes." };
  }
  return { title: "Impossible de charger les tickets", detail: "Vérifiez votre connexion et réessayez." };
}
