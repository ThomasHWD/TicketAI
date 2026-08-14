import type { UserSummary } from "../../../types/index.tsx";

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
