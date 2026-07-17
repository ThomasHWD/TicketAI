export type Domaine = "IT" | "RH" | "JURIDIQUE";

export type StatutTicket = "NOUVEAU" | "RÉPONDU" | "VALIDÉ" | "REJETÉ";

export interface Ticket {
  id: string;
  question: string;
  domaine: Domaine;
  statut_ticket: StatutTicket;
  statut_job: string;
  user_id: string | null;
  user_email: string | null;
  created_at: string | null;
}

export interface TicketsResponse {
  total: number;
  page: number;
  limit: number;
  items: Ticket[];
}

export interface ReponseEnAttente {
  id: string;
  ticket_id: string;
  contenu: string;
  statut: string;
  source: string;
  score_similarite: number | null;
  created_at: string | null;
}

export interface ValiderPayload {
  validator_id: string;
}

export interface RejeterPayload {
  validator_id: string;
  raison?: string;
}

export interface CorrigerPayload {
  contenu_corrige: string;
  validator_id: string;
}
