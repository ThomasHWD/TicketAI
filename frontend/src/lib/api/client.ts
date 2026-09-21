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

/** Raw `detail` from the error body — string for display-only, object for actionable errors (e.g. 409 `DOCUMENT_HOMONYME`), null if not JSON. */
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
