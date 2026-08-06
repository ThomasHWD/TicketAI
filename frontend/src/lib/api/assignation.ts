import { apiFetch, extractApiErrorDetail, BASE_URL } from "./client";
import type { Ticket, WorkflowEvent } from "../../types.ts";
import type { UserSummary } from "../../types/index.tsx";

export type MembreGroupe = Pick<UserSummary, "id" | "email" | "prenom" | "nom">;

export async function getValidateursByDomaine(domaine: string): Promise<MembreGroupe[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/domaines/${domaine}/validateurs`);
  if (!res.ok) throw new Error("Erreur chargement validateurs");
  return res.json();
}

export async function assignTicket(ticketId: string, assigneeId: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/assigner`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assignee_id: assigneeId }),
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de l'assignation"));
  return res.json();
}

export async function unassignTicket(ticketId: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/desassigner`, { method: "POST" });
  if (!res.ok) throw new Error("Erreur lors de la désassignation");
  return res.json();
}

export async function getTicketWorkflow(ticketId: string): Promise<WorkflowEvent[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/workflow`);
  if (!res.ok) throw new Error("Erreur lors du chargement du workflow");
  return res.json();
}

export async function getMyAssignedTickets(): Promise<Ticket[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/mes-assignations`);
  if (!res.ok) throw new Error("Erreur chargement assignations");
  return res.json();
}
