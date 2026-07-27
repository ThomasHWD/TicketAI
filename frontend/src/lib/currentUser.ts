// Identité de l'utilisateur courant.
//
// Depuis la mise en place de l'authentification LDAP/JWT, l'id renvoyé est celui
// de l'utilisateur connecté (lu depuis le profil stocké par l'AuthProvider).
// Le backend fait de toute façon autorité : il dérive l'identité du token JWT.
// Cette fonction reste exposée pour les rares endroits qui ont besoin de l'id
// utilisateur côté client (ex. filtre « mes tickets »).

import { USER_KEY, type AuthUser } from "./api";

// Fallback UUID quand aucun utilisateur n'est connecté (ne devrait pas arriver
// derrière une route protégée).
const FALLBACK_ID = "00000000-0000-0000-0000-000000000001";

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
