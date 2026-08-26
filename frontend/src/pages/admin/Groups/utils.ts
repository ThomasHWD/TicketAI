import type { UserSummary } from "../../../types/index.tsx";

const DOMAIN_PALETTE = [
  { bg: "bg-violet-100 dark:bg-violet-400/15", text: "text-violet-700 dark:text-violet-400" },
  { bg: "bg-amber-100 dark:bg-amber-400/15", text: "text-amber-700 dark:text-amber-400" },
  { bg: "bg-sky-100 dark:bg-sky-400/15", text: "text-sky-700 dark:text-sky-400" },
  { bg: "bg-teal-100 dark:bg-teal-400/15", text: "text-teal-700 dark:text-teal-400" },
  { bg: "bg-rose-100 dark:bg-rose-400/15", text: "text-rose-700 dark:text-rose-400" },
  { bg: "bg-orange-100 dark:bg-orange-400/15", text: "text-orange-700 dark:text-orange-400" },
  { bg: "bg-indigo-100 dark:bg-indigo-400/15", text: "text-indigo-700 dark:text-indigo-400" },
  { bg: "bg-pink-100 dark:bg-pink-400/15", text: "text-pink-700 dark:text-pink-400" },
] as const;

export function domainColor(domaine: string) {
  let hash = 0;
  for (let i = 0; i < domaine.length; i++) hash = (hash * 31 + domaine.charCodeAt(i)) & 0xffff;
  return DOMAIN_PALETTE[hash % DOMAIN_PALETTE.length];
}

export function displayName(u: UserSummary) {
  return u.prenom && u.nom ? `${u.prenom} ${u.nom}` : u.email;
}

export function initials(u: UserSummary) {
  if (u.prenom && u.nom) return `${u.prenom[0]}${u.nom[0]}`.toUpperCase();
  return u.email.slice(0, 2).toUpperCase();
}

export function normalize(s: string) {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "");
}

const USER_MESSAGES = {
  create: "Impossible de créer ce groupe. Réessayez ou rechargez la page.",
  add: "Impossible d'ajouter ce membre. Réessayez ou rechargez la page.",
  chef: "Impossible de modifier ce rôle. Actualisez la page et réessayez.",
  delete: "Impossible de supprimer ce groupe. Réessayez ou rechargez la page.",
  remove: "Impossible de retirer ce membre. Actualisez la page et réessayez.",
} as const;

export function toFrenchError(err: unknown, context: keyof typeof USER_MESSAGES): string {
  const raw = err instanceof Error ? err.message.toLowerCase() : "";
  if (raw.includes("failed to fetch") || raw.includes("networkerror") || raw.includes("503") || raw.includes("network request failed")) {
    return "Service temporairement indisponible. Vérifiez votre connexion et réessayez.";
  }
  if (raw.includes("already") || raw.includes("409") || raw.includes("unique")) {
    if (context === "create") return "Un groupe avec ce nom existe déjà.";
    if (context === "add") return "Ce gestionnaire est déjà membre de ce groupe.";
    return "Opération en conflit avec l'état actuel. Actualisez et réessayez.";
  }
  if (raw.includes("403") || raw.includes("forbidden")) {
    return "Action non autorisée. Vérifiez vos droits d'accès.";
  }
  if (raw.includes("404") || raw.includes("not found")) {
    return "Ressource introuvable. Actualisez la page et réessayez.";
  }
  return USER_MESSAGES[context];
}
