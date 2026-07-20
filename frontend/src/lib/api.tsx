import type {
  Ticket,
  TicketsResponse,
  TicketReponse,
  ReponseEnAttente,
  ValiderPayload,
  RejeterPayload,
  CorrigerPayload,
  Domaine,
} from "../types.ts";

const BASE_URL = "/api/v1";

export async function getTickets(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  statut?: string;
}): Promise<TicketsResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.statut) query.set("statut", params.statut);
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

export async function validerReponse(
  reponseId: string,
  payload: ValiderPayload,
) {
  const res = await fetch(`${BASE_URL}/reponses/${reponseId}/valider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
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
  if (!res.ok) throw new Error("Erreur correction");
  return res.json();
}
