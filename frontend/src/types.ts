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

/**
 * Une réponse enregistrée dont un passage cité a bougé. Elle sera jugée en
 * priorité — ce n'est plus une condamnation : le passage a pu perdre une virgule.
 */
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

/** Un changement du document, apparié avant ↔ après. */
export interface UniteChangement {
  sens: "AJOUT" | "RETRAIT" | "REECRITURE";
  /** Vide pour un AJOUT. */
  extrait_avant: string;
  /** Vide pour un RETRAIT. */
  extrait_apres: string;
}

/**
 * Résultat de l'aperçu : le diff réel, et **rien de plus**.
 *
 * L'aperçu n'appelle ni reranker ni LLM — il reste instantané et gratuit, y
 * compris si l'utilisateur renonce. Il ne peut donc pas dire quelles réponses
 * seront retirées : cette question ne se tranche qu'en les lisant, après
 * confirmation. Il annonce ce qui change et combien de réponses seront jugées.
 */
export interface UpdateImpact {
  staging_id: string;
  filename: string;
  version_cible: number;
  /** Renseigné quand l'aperçu vient d'une restauration. */
  restauree_depuis: number | null;
  nb_chunks_modifies: number;
  nb_total_chunks: number;
  /**
   * Réponses dont un passage cité a bougé. Ce n'est **pas** un compte de
   * réponses condamnées : elles passent en tête du budget d'analyse, rien de plus.
   */
  nb_prioritaires: number;
  /** Les prioritaires, avec le passage en cause. */
  items: ImpactItem[];
  /**
   * `false` quand le fichier de la version courante est introuvable (documents
   * backfillés) : aucun diff n'est calculable, et le panneau reste masqué plutôt
   * que d'annoncer « 0 changement », qui se lirait comme une garantie.
   */
  diff_analysable: boolean;
  /** Zéro ⇒ reformatage pur : aucune analyse ne sera même lancée. */
  nb_unites: number;
  /** Les trois premières unités, tronquées à la longueur d'un extrait. */
  unites: UniteChangement[];
  nb_ajoutes: number;
  /** Trois extraits au plus. */
  extraits_ajoutes: string[];
  nb_retires: number;
  extraits_retires: string[];
  /** Réponses qui seront jugées une fois la nouvelle version en place. */
  nb_a_analyser: number;
  /** Combien d'entre elles sont canoniques. */
  nb_canoniques: number;
  /** Les dix premières de `nb_a_analyser`, dans l'ordre où elles seront jugées. */
  a_analyser: ReponseARelire[];
  /** Réponses EN_ATTENTE (non encore validées) qui seront annulées. */
  nb_en_attente: number;
}

/**
 * Réponse que la mise à jour va soumettre à la ré-vérification. Rien ne lui
 * arrive à la confirmation : c'est une candidate au jugement, pas un verdict.
 */
export interface ReponseARelire {
  reponse_id: string;
  ticket_id: string;
  question: string;
  /** Contenu servi (contenu_corrige ?? contenu). */
  contenu: string;
  canonique: boolean;
  nb_validations: number;
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
    /** Job de mise à jour uniquement : réponses soumises à la ré-vérification. */
    nb_a_analyser?: number;
    /** Signalées sans jugement possible (version sortante illisible). */
    nb_a_relire?: number;
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

export type Source = "LLM" | "SUGGESTION" | "CANONIQUE" | "HORS_DOMAINE";

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
  /** Toujours servie, mais son document a changé : cf. `ReponseSignalee`. */
  a_relire: boolean;
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
  obsolete_raison:
    | "DOC_MIS_A_JOUR"
    | "DOC_SUPPRIMÉ"
    | "RETIRÉ_À_LA_MAIN"
    /** Un changement de la nouvelle version contredit cette réponse. */
    | "CONTREDITE_PAR_MAJ"
    | null;
  obsolete_version: number | null;
  obsolete_at: string | null;
  /**
   * La phrase qui justifie le retrait, écrite à l'analyse. Sans elle, un retrait
   * sec est indéfendable : on voit une réponse disparue et rien qui dise pourquoi.
   * null pour les réponses retirées avant l'arrivée de la ré-vérification.
   */
  analyse_justification: string | null;
  /** Les unités de changement sur lesquelles le verdict s'est appuyé. */
  analyse_extraits: UniteBrute[];
  doc_id: string | null;
  /** null si le document a été supprimé et sa ligne purgée. */
  document_filename: string | null;
  document_supprime: boolean;
}

/** Une unité telle qu'elle est figée en base : texte intégral, non tronqué. */
export interface UniteBrute {
  sens: "AJOUT" | "RETRAIT" | "REECRITURE";
  avant: string | null;
  apres: string | null;
}

export interface ReponsesObsoletesResponse {
  total: number;
  page: number;
  limit: number;
  items: ReponseObsolete[];
}

/**
 * Ce qu'une version de document a changé, figé au moment de la mise à jour.
 *
 * Les unités intégrales ne sont pas renvoyées ici : elles pèsent jusqu'à 256 Ko
 * et servent au worker, pas à l'écran, qui n'affiche que les extraits.
 */
export interface ChangementsVersion {
  nb_unites?: number;
  nb_ajoutes: number;
  nb_retires: number;
  /** Trois extraits au plus par sens. */
  extraits_ajoutes: string[];
  extraits_retires: string[];
}

/**
 * Pourquoi une réponse attend une relecture. Chaque valeur dit ce que la machine
 * n'a pas pu trancher — ce n'est pas un détail d'affichage : `ANALYSE_EN_COURS`
 * est un état transitoire sur lequel aucune action ne doit être proposée.
 */
export type RaisonARelire =
  /** Verdict CONTREDITE sur une réponse qui ne cite pas le document : plafonné. */
  | "CONTREDITE_PROBABLE"
  /** Transitoire : la version est en ligne, le verdict n'est pas encore rendu. */
  | "ANALYSE_EN_COURS"
  /** Albert n'a pas répondu, ou une version plus récente a rendu ce lot caduc. */
  | "ANALYSE_INDISPONIBLE"
  /** Budget d'appels épuisé pour cette mise à jour. */
  | "ANALYSE_PARTIELLE"
  /** Document réécrit au-delà du plafond : signalé en bloc, sans jugement. */
  | "REECRITURE_MASSIVE"
  /** Verdict INCERTAIN : le modèle a vu les changements sans pouvoir conclure. */
  | "DOC_MODIFIÉ"
  /** Aucun diff n'était calculable : le fichier sortant avait disparu du disque. */
  | "VERSION_SORTANTE_ILLISIBLE";

/**
 * Réponse toujours servie sur laquelle une mise à jour de document a laissé un
 * doute. Elle continue d'être servie jusqu'à ce qu'un humain tranche — d'où
 * l'absence de tout champ d'état.
 */
export interface ReponseSignalee extends ReponseARelire {
  domaine: Domaine;
  contenu: string;
  contenu_corrige: string | null;
  a_relire_raison: RaisonARelire | null;
  a_relire_version: number | null;
  a_relire_at: string | null;
  /** Ce que le modèle a répondu, ou pourquoi il n'a pas pu répondre. */
  analyse_justification: string | null;
  /** Les unités qui ont fondé ce signalement, propres à cette réponse. */
  analyse_extraits: UniteBrute[];
  doc_id: string | null;
  document_filename: string | null;
  document_supprime: boolean;
  /** null pour les documents mis à jour avant l'arrivée de la colonne. */
  changements: ChangementsVersion | null;
}

export interface ReponsesARelireResponse {
  total: number;
  /** Ce que compte le badge : « 2 documents » se traite, « 39 réponses » se subit. */
  nb_documents: number;
  page: number;
  limit: number;
  items: ReponseSignalee[];
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
