export type Domaine = string;

export interface GroupeSummary {
  id: string;
  nom: string;
  domaine: string;
}

export interface UserSummary {
  id: string;
  email: string;
  prenom: string | null;
  nom: string | null;
  role: string;
  departement: string | null;
  groupes: GroupeSummary[];
}

export interface MembreSummary extends UserSummary {
  is_chef: boolean;
}

export interface Groupe extends GroupeSummary {
  created_at: string | null;
  nb_membres: number;
  membres: MembreSummary[];
}

export type StatutTicket = "NOUVEAU" | "RÉPONDU" | "VALIDÉ" | "REJETÉ";

export type StatutReponse = "EN_ATTENTE" | "VALIDÉE" | "REJETÉE" | "CORRIGÉE";

export type Source = "LLM" | "SUGGESTION" | "CANONIQUE";

export interface Ticket {
  id: string;
  question: string;
  domaine: Domaine;
  statut_ticket: StatutTicket;
  statut_job: string;
  user_id: string | null;
  user_email: string | null;
  canonique: boolean;
  created_at: string | null;
  // Verrou collaboratif : renseigné uniquement si un bail est actif.
  locked_by: string | null;
  locked_by_email: string | null;
  lock_expires_at: string | null;
}

export interface LockState {
  ticket_id: string;
  is_mine: boolean;
  locked_by: string | null;
  locked_by_email: string | null;
  lock_expires_at: string | null;
}

export interface TicketsResponse {
  total: number;
  page: number;
  limit: number;
  items: Ticket[];
}

export interface TicketReponse {
  id: string;
  ticket_id: string;
  contenu: string;
  statut: StatutReponse;
  source: Source;
  nb_validations: number;
  canonique: boolean;
  score_similarite: number | null;
  raison_rejet?: string | null;
  created_at: string | null;
}

export interface ReponseEnAttente {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: Domaine;
  reponse: string;
  source: Source;
  score_similarite: number;
  created_at: string;
}

export interface ValiderPayload {
  validator_id: string;
}

export interface RejeterPayload {
  validator_id: string;
  raison?: string;
}

export interface CorrigerPayload {
  validator_id: string;
  contenu_corrige: string;
}
