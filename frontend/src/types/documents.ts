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
  occurence: number;
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
