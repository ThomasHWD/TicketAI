import type { Source } from "./reponses";

export type StatutTicket = "NOUVEAU" | "RÉPONDU" | "VALIDÉ" | "REJETÉ";

export interface Ticket {
  id: string;
  question: string;
  // Titre court saisi à la création, affiché à la place de la question dans les tableaux
  // (null pour les anciens tickets → fallback sur la question à l'affichage).
  objet: string | null;
  domaine: string;
  statut_ticket: StatutTicket;
  statut_job: string;
  user_id: string | null;
  user_email: string | null;
  user_nom_complet: string | null;
  user_departement: string | null;
  user_titre: string | null;
  user_telephone: string | null;
  user_localisation: string | null;
  canonique: boolean;
  created_at: string | null;
  // Clôture par l'utilisateur (null = ouvert).
  closed_at: string | null;
  // Notes de satisfaction (1–5), collectées à la clôture (null si non renseignées).
  note_qualite: number | null;
  note_delai: number | null;
  // Verrou collaboratif : renseigné uniquement si un bail est actif.
  locked_by: string | null;
  locked_by_email: string | null;
  lock_expires_at: string | null;
  // Assignation à un validateur spécifique
  assigned_to: string | null;
  assigned_to_email: string | null;
  assigned_to_nom_complet: string | null;
  reponse_source: Source | null;
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

export interface SoumettreQuestionPayload {
  question: string;
  objet: string;
  domaine: string;
  user_id?: string | null;
}

export interface SoumettreQuestionResponse {
  job_id: string;
  question: string;
  domaine: string;
  statut: string;
}

export interface PoserSuiviPayload {
  question: string;
  user_id?: string | null;
}

export interface CloturerPayload {
  user_id?: string | null;
  note_qualite?: number | null;
  note_delai?: number | null;
}

export type WorkflowEventType =
  | "CREE"
  | "REPONSE_GENEREE"
  | "SUIVI"
  | "VALIDE"
  | "CORRIGE"
  | "REJETE"
  | "ASSIGNE"
  | "DESASSIGNE"
  | "CLOTURE";

export interface WorkflowEvent {
  type: WorkflowEventType;
  at: string | null;
  actor_email: string | null;
  actor_nom_complet: string | null;
  meta: Record<string, string | null>;
}
