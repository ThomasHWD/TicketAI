import type {
  Ticket,
  TicketsResponse,
  TicketReponse,
  ReponseEnAttente,
  ReponsesCanoniquesResponse,
  EditerCanoniquePayload,
  ValiderPayload,
  RejeterPayload,
  CorrigerPayload,
  Domaine,
  LockState,
  SoumettreQuestionPayload,
  SoumettreQuestionResponse,
} from "../types.ts";

const BASE_URL = "/api/v1";

/** Soumet une nouvelle question. Renvoie l'identifiant du job Celery à suivre. */
export async function soumettreQuestion(
  payload: SoumettreQuestionPayload,
): Promise<SoumettreQuestionResponse> {
  const res = await fetch(`${BASE_URL}/tickets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Erreur lors de la soumission de la question";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* corps non JSON : on garde le message par défaut */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** Levée sur un 409 (verrou détenu par un autre validateur). Porte le détenteur. */
export class LockConflictError extends Error {
  lockedByEmail: string | null;
  lockExpiresAt: string | null;
  constructor(message: string, lockedByEmail: string | null, lockExpiresAt: string | null) {
    super(message);
    this.name = "LockConflictError";
    this.lockedByEmail = lockedByEmail;
    this.lockExpiresAt = lockExpiresAt;
  }
}

export async function getTickets(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  statut?: string;
  userId?: string;
}): Promise<TicketsResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.statut) query.set("statut", params.statut);
  if (params?.userId) query.set("user_id", params.userId);
  const res = await fetch(`${BASE_URL}/tickets?${query}`);
  if (!res.ok) throw new Error("Erreur chargement tickets");
  return res.json();
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const res = await fetch(`${BASE_URL}/tickets/${ticketId}`);
  if (!res.ok) throw new Error("Ticket introuvable");
  return res.json();
}

export async function getReponsesByTicket(ticketId: string): Promise<TicketReponse[]> {
  const res = await fetch(`${BASE_URL}/tickets/${ticketId}/reponses`);
  if (!res.ok) throw new Error("Erreur chargement réponses");
  return res.json();
}

export async function getReponsesEnAttente(
  domaine?: Domaine,
): Promise<ReponseEnAttente[]> {
  const params = domaine ? `?domaine=${domaine}` : "";
  const res = await fetch(`${BASE_URL}/reponses/en-attente${params}`);
  if (!res.ok) throw new Error("Erreur chargement réponses");
  return res.json();
}

export async function getReponsesCanoniques(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
}): Promise<ReponsesCanoniquesResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  const res = await fetch(`${BASE_URL}/reponses/canoniques?${query}`);
  if (!res.ok) throw new Error("Erreur chargement réponses canoniques");
  return res.json();
}

export async function editerReponseCanonique(
  reponseId: string,
  payload: EditerCanoniquePayload,
) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}/editer`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Erreur édition réponse canonique");
  return res.json();
}

export async function supprimerReponseCanonique(reponseId: string) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Erreur suppression réponse canonique");
  return res.json();
}

export async function validerReponse(
  reponseId: string,
  payload: ValiderPayload,
) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}/valider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur validation");
  if (!res.ok) throw new Error("Erreur validation");
  return res.json();
}

export async function rejeterReponse(
  reponseId: string,
  payload: RejeterPayload,
) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}/rejeter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur rejet");
  if (!res.ok) throw new Error("Erreur rejet");
  return res.json();
}

export async function corrigerReponse(
  reponseId: string,
  payload: CorrigerPayload,
) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}/corriger`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur correction");
  if (!res.ok) throw new Error("Erreur correction");
  return res.json();
}

// ── Verrou collaboratif ──────────────────────────────────────────────

/** Construit une LockConflictError à partir d'une réponse 409 (détail dict ou string). */
async function toLockConflict(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      return new LockConflictError(
        detail.message ?? fallback,
        detail.locked_by_email ?? null,
        detail.lock_expires_at ?? null,
      );
    }
    return new LockConflictError(typeof detail === "string" ? detail : fallback, null, null);
  } catch {
    return new LockConflictError(fallback, null, null);
  }
}

export async function lockTicket(
  ticketId: string,
  validatorId: string,
): Promise<LockState> {
  const res = await fetch(`${BASE_URL}/tickets/${ticketId}/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Ticket verrouillé");
  if (!res.ok) throw new Error("Erreur verrouillage");
  return res.json();
}

export async function heartbeatTicket(
  ticketId: string,
  validatorId: string,
): Promise<LockState> {
  const res = await fetch(`${BASE_URL}/tickets/${ticketId}/heartbeat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Verrou perdu");
  if (!res.ok) throw new Error("Erreur heartbeat");
  return res.json();
}

export async function unlockTicket(
  ticketId: string,
  validatorId: string,
): Promise<void> {
  // keepalive : permet à la requête d'aboutir même si l'onglet se ferme.
  await fetch(`${BASE_URL}/tickets/${ticketId}/unlock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
    keepalive: true,
  });
}
