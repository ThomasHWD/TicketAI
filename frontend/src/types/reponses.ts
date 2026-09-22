import type { ReponseARelire, ChangementsVersion } from "./documents";

export type StatutReponse = "EN_ATTENTE" | "VALIDÉE" | "REJETÉE" | "CORRIGÉE";

export type Source = "LLM" | "SUGGESTION" | "CANONIQUE" | "HORS_DOMAINE";

export interface TicketReponse {
  id: string;
  ticket_id: string;
  contenu: string;
  contenu_corrige: string | null;
  // Follow-up text (relance) that triggered this response; null for the initial question's answer.
  question_suivi: string | null;
  statut: StatutReponse;
  source: Source;
  nb_validations: number;
  canonique: boolean;
  score_similarite: number | null;
  created_at: string | null;
  validator_email: string | null;
  validator_nom_complet: string | null;
  raison_rejet: string | null;
  tag: string | null;
  obsolete: boolean;
  obsolete_raison: string | null;
}

export interface ReponseEnAttente {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: string;
  reponse: string;
  source: Source;
  score_similarite: number;
  created_at: string;
}

export interface ReponseCanonique {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: string;
  contenu: string;
  contenu_corrige: string | null;
  nb_validations: number;
  occurence: number;
  /** Toujours servie, mais son document a changé : cf. `ReponseSignalee`. */
  a_relire: boolean;
  /** Décision volontaire d'exposition dans la FAQ grand public interne. */
  faq_visible: boolean;
  validated_at: string | null;
  created_at: string | null;
  tag: string | null;
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

export interface UniteBrute {
  sens: "AJOUT" | "RETRAIT" | "REECRITURE";
  avant: string | null;
  apres: string | null;
}

export interface ReponseObsolete {
  reponse_id: string;
  ticket_id: string;
  question: string;
  domaine: string;
  contenu: string;
  contenu_corrige: string | null;
  nb_validations: number;
  occurence: number;
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
  /** Sentence written at analysis time — null for responses withdrawn before reverification existed. */
  analyse_justification: string | null;
  analyse_extraits: UniteBrute[];
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

/** ANALYSE_EN_COURS is transient — no user action should be offered while it is set. */
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
  /** Same verdict but triggered by a *new* document — no previous version to diff against. */
  | "NOUVEAU_DOC"
  /** Aucun diff n'était calculable : le fichier sortant avait disparu du disque. */
  | "VERSION_SORTANTE_ILLISIBLE";

/** Still served until a human decides — hence no status field. */
export interface ReponseSignalee extends ReponseARelire {
  domaine: string;
  contenu: string;
  contenu_corrige: string | null;
  a_relire_raison: RaisonARelire | null;
  a_relire_version: number | null;
  a_relire_at: string | null;
  /** Ce que le modèle a répondu, ou pourquoi il n'a pas pu répondre. */
  analyse_justification: string | null;
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

export interface ValiderPayload {
  validator_id: string;
  faq_visible?: boolean;
}

export interface FaqVisiblePayload {
  faq_visible: boolean;
}

export interface RejeterPayload {
  validator_id: string;
  raison?: string;
}

export interface CorrigerPayload {
  contenu_corrige: string;
  validator_id: string;
  tag?: string | null;
  faq_visible?: boolean;
}
