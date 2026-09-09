export const TOKEN_KEY = "ticketai.token";
export const USER_KEY = "ticketai.user";
export const BASE_URL = "/api/v1";

export interface AuthUser {
  id: string;
  email: string;
  prenom: string | null;
  nom: string | null;
  role: string;
  groupes: { id: string; nom: string; domaine: string; is_chef: boolean }[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * `detail` brut du corps d'erreur.
 *
 * Une chaîne pour les erreurs à afficher telles quelles, un objet pour les
 * erreurs *actionnables* dont le front doit exploiter les champs (ex. le 409
 * `DOCUMENT_HOMONYME`, qui porte le `doc_id` à mettre à jour). `null` si le
 * corps n'est pas du JSON.
 */
export async function readApiErrorDetail(res: Response): Promise<unknown> {
  try {
    return (await res.json())?.detail ?? null;
  } catch {
    return null; // corps non-JSON
  }
}

export async function extractApiErrorDetail(res: Response, fallback: string): Promise<string> {
  const detail = await readApiErrorDetail(res);
  return typeof detail === "string" ? detail : fallback;
}

export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(input, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), ...authHeaders() },
  });
  if (res.status === 401) {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
  }
  if (res.status === 503) {
    window.dispatchEvent(new CustomEvent("ticketai:maintenance"));
  }
  return res;
}
