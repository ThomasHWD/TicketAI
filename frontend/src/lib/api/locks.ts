import { apiFetch, BASE_URL } from "./client";
import type { LockState } from "../../types.ts";

export class LockConflictError extends Error {
  lockedByEmail: string | null;
  lockExpiresAt: string | null;
  isAssigned: boolean;
  constructor(message: string, lockedByEmail: string | null, lockExpiresAt: string | null, isAssigned = false) {
    super(message);
    this.name = "LockConflictError";
    this.lockedByEmail = lockedByEmail;
    this.lockExpiresAt = lockExpiresAt;
    this.isAssigned = isAssigned;
  }
}

export async function toLockConflict(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      return new LockConflictError(
        detail.message ?? fallback,
        detail.locked_by_email ?? null,
        detail.lock_expires_at ?? null,
        detail.is_assigned ?? false,
      );
    }
    return new LockConflictError(typeof detail === "string" ? detail : fallback, null, null);
  } catch {
    return new LockConflictError(fallback, null, null);
  }
}

export async function lockTicket(ticketId: string, validatorId: string): Promise<LockState> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Ticket verrouillé");
  if (!res.ok) throw new Error("Erreur verrouillage");
  return res.json();
}

export async function heartbeatTicket(ticketId: string, validatorId: string): Promise<LockState> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/heartbeat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Verrou perdu");
  if (!res.ok) throw new Error("Erreur heartbeat");
  return res.json();
}

export async function unlockTicket(ticketId: string, validatorId: string): Promise<void> {
  // keepalive : permet à la requête d'aboutir même si l'onglet se ferme.
  await apiFetch(`${BASE_URL}/tickets/${ticketId}/unlock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
    keepalive: true,
  });
}
