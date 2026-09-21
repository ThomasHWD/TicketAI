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

/** Response whose cited passage changed — judged first but not condemned; the passage may have just lost a comma. */
export interface ImpactItem {
  reponse_id: string;
  question: string;
  canonique: boolean;
  nb_validations: number;
  chunks_modifies: number[];
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

export interface UniteChangement {
  sens: "AJOUT" | "RETRAIT" | "REECRITURE";
  /** Vide pour un AJOUT. */
  extrait_avant: string;
  /** Vide pour un RETRAIT. */
  extrait_apres: string;
}

/** Response flagged for reverification — nothing happens at confirm time; it's a candidate for judgment, not a verdict. */
export interface ReponseARelire {
  reponse_id: string;
  ticket_id: string;
  question: string;
  /** Contenu servi (contenu_corrige ?? contenu). */
  contenu: string;
  canonique: boolean;
  nb_validations: number;
  occurence: number;
}

/** Preview result — no reranker or LLM; cannot predict which responses will be withdrawn, only announces what changed and how many will be analyzed. */
export interface UpdateImpact {
  staging_id: string;
  filename: string;
  version_cible: number;
  /** Renseigné quand l'aperçu vient d'une restauration. */
  restauree_depuis: number | null;
  nb_chunks_modifies: number;
  nb_total_chunks: number;
  /** Responses with a cited passage that changed — not condemned, just first in the analysis budget. */
  nb_prioritaires: number;
  items: ImpactItem[];
  /** `false` when current file is missing (backfilled docs) — panel hides rather than showing "0 changes", which would read as a guarantee. */
  diff_analysable: boolean;
  /** Zéro ⇒ reformatage pur : aucune analyse ne sera même lancée. */
  nb_unites: number;
  unites: UniteChangement[];
  nb_ajoutes: number;
  extraits_ajoutes: string[];
  nb_retires: number;
  extraits_retires: string[];
  nb_a_analyser: number;
  nb_canoniques: number;
  a_analyser: ReponseARelire[];
  nb_en_attente: number;
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
    nb_a_analyser?: number;
    /** Signalées sans jugement possible (version sortante illisible). */
    nb_a_relire?: number;
  };
  erreur?: string;
}

/** What a document version changed, frozen at update time. Full units excluded — up to 256 KB, worker-only; UI shows excerpts only. */
export interface ChangementsVersion {
  nb_unites?: number;
  nb_ajoutes: number;
  nb_retires: number;
  extraits_ajoutes: string[];
  extraits_retires: string[];
}
