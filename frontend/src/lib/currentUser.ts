// Exposed for the rare client-side spots that need the user id (e.g. "mes tickets" filter) — backend always has authority via JWT.

import { USER_KEY, type AuthUser } from "./api";

const FALLBACK_ID = "00000000-0000-0000-0000-000000000001";  // should never be reached behind a protected route

export function getValidatorId(): string {
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return FALLBACK_ID;
    const user = JSON.parse(raw) as AuthUser;
    return user.id ?? FALLBACK_ID;
  } catch {
    return FALLBACK_ID;
  }
}
