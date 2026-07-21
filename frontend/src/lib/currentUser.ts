// Identité validateur — SHIM TEMPORAIRE.
//
// Il n'y a pas encore d'authentification réelle. On stocke un `validator_id`
// en localStorage pour pouvoir simuler deux validateurs distincts (deux
// onglets / navigateurs) et tester le verrouillage collaboratif.
//
// À REMPLACER par un vrai AuthContext (JWT/session) quand l'auth arrivera :
// il suffira de faire pointer `getValidatorId()` vers l'utilisateur connecté.

const STORAGE_KEY = "ticketai.validator_id";
const DEFAULT_VALIDATOR_ID = "00000000-0000-0000-0000-000000000001";

export function getValidatorId(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_VALIDATOR_ID;
  } catch {
    return DEFAULT_VALIDATOR_ID;
  }
}

export function setValidatorId(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore (mode privé, etc.) */
  }
}
