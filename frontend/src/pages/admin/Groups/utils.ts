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
    .replace(/[̀-ͯ]/g, "");
}
