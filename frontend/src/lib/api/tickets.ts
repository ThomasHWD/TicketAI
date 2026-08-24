import { apiFetch, extractApiErrorDetail, BASE_URL } from "./client";
import type {
  Ticket,
  TicketsResponse,
  TicketReponse,
  Domaine,
  SoumettreQuestionPayload,
  SoumettreQuestionResponse,
  PoserSuiviPayload,
  CloturerPayload,
} from "../../types";

export async function soumettreQuestion(
  payload: SoumettreQuestionPayload,
): Promise<SoumettreQuestionResponse> {
  const res = await apiFetch(`${BASE_URL}/tickets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de la soumission de la question"));
  return res.json();
}

export async function poserSuivi(
  ticketId: string,
  payload: PoserSuiviPayload,
): Promise<SoumettreQuestionResponse> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/suivi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de l'envoi de la précision"));
  return res.json();
}

export async function cloturerTicket(
  ticketId: string,
  payload: CloturerPayload,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/cloturer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de la clôture du ticket"));
  return res.json();
}

export async function getTickets(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  domaines?: string[];
  statut?: string;
  userId?: string;
  closed?: boolean;
  search?: string;
  disponibles?: boolean;
  noteMax?: number;
  periode?: string;
  exclure_canonique?: boolean;
}): Promise<TicketsResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaines?.length) query.set("domaines", params.domaines.join(","));
  else if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.statut) query.set("statut", params.statut);
  if (params?.userId) query.set("user_id", params.userId);
  if (params?.closed !== undefined) query.set("closed", String(params.closed));
  if (params?.search) query.set("search", params.search);
  if (params?.disponibles) query.set("disponibles", "true");
  if (params?.noteMax !== undefined) query.set("note_max", String(params.noteMax));
  if (params?.periode) query.set("periode", params.periode);
  if (params?.exclure_canonique) query.set("exclure_canonique", "true");
  const res = await apiFetch(`${BASE_URL}/tickets?${query}`);
  if (!res.ok) throw new Error("Erreur chargement tickets");
  return res.json();
}

export async function getParticipatedTickets(page = 1): Promise<TicketsResponse> {
  const res = await apiFetch(`${BASE_URL}/tickets/participated?page=${page}&limit=10`);
  if (!res.ok) throw new Error("Erreur chargement tickets");
  return res.json();
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}`);
  if (!res.ok) throw new Error("Ticket introuvable");
  return res.json();
}

export async function getReponsesByTicket(ticketId: string): Promise<TicketReponse[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/reponses`);
  if (!res.ok) throw new Error("Erreur chargement réponses");
  return res.json();
}
