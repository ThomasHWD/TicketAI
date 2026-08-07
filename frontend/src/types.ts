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
  /** Renseignés sur `DÉJÀ_INDEXÉ` : ceux du document déjà en base. */
  domaine?: Domaine;
  version?: number;
}

/** Une réponse enregistrée que la nouvelle version du document va rendre obsolète. */
export interface ImpactItem {
  reponse_id: string;
  question: string;
  canonique: boolean;
  nb_validations: number;
  chunks_modifies: number[];
  /** Extraits tronqués des passages disparus, trois au plus. */
  extraits: string[];
}

export interface DocumentVersion {
  version: number;
  filename: string;
  taille_octets: number | null;
  nb_chunks: number;
  /** Version d'origine si celle-ci est née d'une restauration. */
  restauree_depuis: number | null;
  courante: boolean;
  auteur: string | null;
  /** `false` si l'archive a disparu du disque : ni téléchargement ni restauration. */
  fichier_disponible: boolean;
  created_at: string | null;
  remplacee_at: string | null;
}

export interface DocumentVersionsResponse {
  doc_id: string;
  version_courante: number;
  items: DocumentVersion[];
}

/** Résultat de l'aperçu : impact **exact**, calculé sans rien modifier. */
export interface UpdateImpact {
  staging_id: string;
  filename: string;
  version_cible: number;
  /** Renseigné quand l'aperçu vient d'une restauration. */
  restauree_depuis: number | null;
  nb_chunks_modifies: number;
  nb_total_chunks: number;
  nb_obsoletes: number;
  nb_canoniques: number;
  items: ImpactItem[];
  /**
   * Détection en miroir : les passages que la nouvelle version *ajoute*. Aucun
   * n'entraîne d'obsolescence — seule une lecture humaine peut dire si un ajout
   * contredit une réponse existante. `false` quand le fichier de la version
   * courante est introuvable (documents backfillés) : rien n'est alors
   * démontrable, et le panneau reste masqué plutôt que d'annoncer « 0 ajout ».
   */
  ajouts_analysables: boolean;
  nb_passages_ajoutes: number;
  /** Trois extraits au plus. */
  extraits_ajoutes: string[];
  /** Réponses enregistrées du document qui survivent, et ignorent donc l'ajout. */
  nb_a_relire: number;
}

/** `detail` du 409 de `POST /documents` quand un document porte déjà ce nom dans le domaine. */
export interface DocumentHomonyme {
  code: "DOCUMENT_HOMONYME";
  doc_id: string;
  filename: string;
  domaine: Domaine;
  version: number;
  nb_chunks: number;
}

export interface DocumentStatus {
  job_id: string;
  statut: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE" | "RETRY";
  resultat?: {
    filename: string;
    doc_id: string;
    stored_path: string;
    nb_chunks: number;
    /** Job de mise à jour uniquement : réponses enregistrées devenues obsolètes. */
    nb_obsoletes?: number;
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

/** Réponse retirée du service parce que le document qui la fondait a changé. */
export interface ReponseObsolete {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: Domaine;
  contenu: string;
  contenu_corrige: string | null;
  nb_validations: number;
  canonique: boolean;
  obsolete_raison: "DOC_MIS_A_JOUR" | "DOC_SUPPRIMÉ" | null;
  obsolete_version: number | null;
  obsolete_at: string | null;
  doc_id: string | null;
  /** null si le document a été supprimé et sa ligne purgée. */
  document_filename: string | null;
  document_supprime: boolean;
}

export interface ReponsesObsoletesResponse {
  total: number;
  page: number;
  limit: number;
  items: ReponseObsolete[];
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
