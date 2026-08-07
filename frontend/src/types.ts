export type Domaine = string;

export interface IndexedDocument {
  doc_id: string;
  filename: string | null;
  domaine: Domaine | null;
  stored_path: string | null;
  description: string;
  nb_chunks: number;
  version: number;
  statut: "ACTIF" | "EN_MAJ";
  nb_versions: number;
  updated_at: string | null;
}

export interface IndexedDocumentsResponse {
  total: number;
  items: IndexedDocument[];
}

export interface DocumentChunk {
  chunk_index: number;
  contenu: string;
}

export interface DocumentChunksResponse {
  doc_id: string;
  chunks: DocumentChunk[];
}

export interface DocumentUploadResponse {
  job_id: string | null;
  filename: string;
  statut: "EN_ATTENTE" | "DÉJÀ_INDEXÉ";
  doc_id?: string;
}

export interface DocumentStatus {
  job_id: string;
  statut: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | "RETRY";
  resultat?: {
    filename: string;
    doc_id: string;
    stored_path: string;
    nb_chunks: number;
  };
  erreur?: string;
}

export interface Notification {
  id: string;
  ticket_id: string;
  reponse_id: string | null;
  type: "REPONSE_VALIDEE";
  read_at: string | null;
  created_at: string | null;
  ticket_objet: string | null;
  ticket_question: string | null;
}

export type StatutTicket = "NOUVEAU" | "RÉPONDU" | "VALIDÉ" | "REJETÉ";

export type StatutReponse = "EN_ATTENTE" | "VALIDÉE" | "REJETÉE" | "CORRIGÉE";

export type Source = "LLM" | "SUGGESTION" | "CANONIQUE";

export interface Ticket {
  id: string;
  question: string;
  // Titre court saisi à la création, affiché à la place de la question dans les tableaux
  // (null pour les anciens tickets → fallback sur la question à l'affichage).
  objet: string | null;
  domaine: Domaine;
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
  contenu_corrige: string | null;
  // Texte de la précision (relance) ayant déclenché cette réponse ; null pour
  // la réponse à la question initiale.
  question_suivi: string | null;
  statut: StatutReponse;
  source: Source;
  nb_validations: number;
  canonique: boolean;
  score_similarite: number | null;
  created_at: string | null;
  validator_email: string | null;
  validator_nom_complet: string | null;
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

export interface SoumettreQuestionPayload {
  question: string;
  objet: string;
  domaine: Domaine;
  user_id?: string | null;
}

export interface SoumettreQuestionResponse {
  job_id: string;
  question: string;
  domaine: Domaine;
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

export interface ReponseCanonique {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: Domaine;
  contenu: string;
  contenu_corrige: string | null;
  nb_validations: number;
  occurence: number;
  validated_at: string | null;
  created_at: string | null;
}

export interface ReponsesCanoniquesResponse {
  total: number;
  page: number;
  limit: number;
  items: ReponseCanonique[];
}

export interface EditerCanoniquePayload {
  contenu: string;
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
