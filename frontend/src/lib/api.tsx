import type {
  Notification,
  Ticket,
  TicketsResponse,
  TicketReponse,
  ReponseEnAttente,
  ReponsesCanoniquesResponse,
  EditerCanoniquePayload,
  ValiderPayload,
  RejeterPayload,
  CorrigerPayload,
  Domaine,
  LockState,
  SoumettreQuestionPayload,
  SoumettreQuestionResponse,
  PoserSuiviPayload,
  CloturerPayload,
  DocumentUploadResponse,
  DocumentStatus,
  IndexedDocumentsResponse,
  DocumentChunksResponse,
} from "../types.ts";
import type { UserSummary } from "../types/index.tsx";

const BASE_URL = "/api/v1";

// ── Authentification ─────────────────────────────────────────────────
export const TOKEN_KEY = "ticketai.token";
export const USER_KEY = "ticketai.user";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** fetch enrichi du header Authorization + gestion centralisée du 401 (purge + /login). */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(input, {
    ...init,
    headers: { ...(init.headers as Record<string, string>), ...authHeaders() },
  });
  if (res.status === 401) {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
  }
  return res;
}

export interface AuthUser {
  id: string;
  email: string;
  prenom: string | null;
  nom: string | null;
  role: string;
  groupes: { id: string; nom: string; domaine: string; is_chef: boolean }[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

/** Authentifie l'utilisateur via LDAP/AD (form OAuth2). Renvoie le token + profil. */
export async function login(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    let detail = "Identifiant ou mot de passe incorrect.";
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      /* corps non JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** Renvoie le profil de l'utilisateur connecté (vérifie la validité du token). */
export async function getMe(): Promise<AuthUser> {
  const res = await apiFetch(`${BASE_URL}/auth/me`);
  if (!res.ok) throw new Error("Session invalide");
  return res.json();
}

/** Soumet une nouvelle question. Renvoie l'identifiant du job Celery à suivre. */
export async function soumettreQuestion(
  payload: SoumettreQuestionPayload,
): Promise<SoumettreQuestionResponse> {
  const res = await apiFetch(`${BASE_URL}/tickets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Erreur lors de la soumission de la question";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* corps non JSON : on garde le message par défaut */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** Levée sur un 409 (verrou détenu par un autre validateur). Porte le détenteur. */
export class LockConflictError extends Error {
  lockedByEmail: string | null;
  lockExpiresAt: string | null;
  isAssigned: boolean;
  constructor(message: string, lockedByEmail: string | null, lockExpiresAt: string | null, isAssigned = false) {
    super(message);
    this.name = "LockConflictError";
    this.lockedByEmail = lockedByEmail;
    this.lockExpiresAt = lockExpiresAt;
    this.isAssigned = isAssigned;
  }
}

/** Ajoute une précision au fil d'un ticket. Renvoie le job Celery à suivre. */
export async function poserSuivi(
  ticketId: string,
  payload: PoserSuiviPayload,
): Promise<SoumettreQuestionResponse> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/suivi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Erreur lors de l'envoi de la précision";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* corps non JSON : on garde le message par défaut */
    }
    throw new Error(detail);
  }
  return res.json();
}

/** Clôture le ticket (l'utilisateur est satisfait de la réponse). */
export async function cloturerTicket(
  ticketId: string,
  payload: CloturerPayload,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/cloturer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = "Erreur lors de la clôture du ticket";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* corps non JSON : on garde le message par défaut */
    }
    throw new Error(detail);
  }
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

export async function getReponsesEnAttente(
  domaine?: Domaine,
): Promise<ReponseEnAttente[]> {
  const params = domaine ? `?domaine=${domaine}` : "";
  const res = await apiFetch(`${BASE_URL}/reponses/en-attente${params}`);
  if (!res.ok) throw new Error("Erreur chargement réponses");
  return res.json();
}

export async function getReponsesCanoniques(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
}): Promise<ReponsesCanoniquesResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  const res = await apiFetch(`${BASE_URL}/reponses/canoniques?${query}`);
  if (!res.ok) throw new Error("Erreur chargement réponses canoniques");
  return res.json();
}

export async function editerReponseCanonique(
  reponseId: string,
  payload: EditerCanoniquePayload,
) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/editer`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Erreur édition réponse canonique");
  return res.json();
}

export async function supprimerReponseCanonique(reponseId: string) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Erreur suppression réponse canonique");
  return res.json();
}

export async function validerReponse(
  reponseId: string,
  payload: ValiderPayload,
) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/valider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur validation");
  if (!res.ok) throw new Error("Erreur validation");
  return res.json();
}

export async function rejeterReponse(
  reponseId: string,
  payload: RejeterPayload,
) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/rejeter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur rejet");
  if (!res.ok) throw new Error("Erreur rejet");
  return res.json();
}

export async function corrigerReponse(
  reponseId: string,
  payload: CorrigerPayload,
) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/corriger`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur correction");
  if (!res.ok) throw new Error("Erreur correction");
  return res.json();
}

// ── Verrou collaboratif ──────────────────────────────────────────────

/** Construit une LockConflictError à partir d'une réponse 409 (détail dict ou string). */
async function toLockConflict(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      return new LockConflictError(
        detail.message ?? fallback,
        detail.locked_by_email ?? null,
        detail.lock_expires_at ?? null,
        detail.is_assigned ?? false,
      );
    }
    return new LockConflictError(typeof detail === "string" ? detail : fallback, null, null);
  } catch {
    return new LockConflictError(fallback, null, null);
  }
}

export async function lockTicket(
  ticketId: string,
  validatorId: string,
): Promise<LockState> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Ticket verrouillé");
  if (!res.ok) throw new Error("Erreur verrouillage");
  return res.json();
}

export async function heartbeatTicket(
  ticketId: string,
  validatorId: string,
): Promise<LockState> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/heartbeat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
  });
  if (res.status === 409) throw await toLockConflict(res, "Verrou perdu");
  if (!res.ok) throw new Error("Erreur heartbeat");
  return res.json();
}

export async function unlockTicket(
  ticketId: string,
  validatorId: string,
): Promise<void> {
  // keepalive : permet à la requête d'aboutir même si l'onglet se ferme.
  await apiFetch(`${BASE_URL}/tickets/${ticketId}/unlock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ validator_id: validatorId }),
    keepalive: true,
  });
}

// ── Documents ────────────────────────────────────────────────────────

export async function uploadDocument(
  file: File,
  domaine: Domaine,
  description = "",
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ domaine });
  if (description) params.set("description", description);
  const res = await apiFetch(`${BASE_URL}/documents?${params}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = "Erreur lors de l'envoi du document";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* corps non JSON */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getDocumentStatus(jobId: string): Promise<DocumentStatus> {
  const res = await apiFetch(`${BASE_URL}/documents/${jobId}/status`);
  if (!res.ok) throw new Error("Erreur récupération statut");
  return res.json();
}

export async function listDocuments(domaine?: Domaine, domaines?: string[]): Promise<IndexedDocumentsResponse> {
  const q = new URLSearchParams();
  if (domaines?.length) q.set("domaines", domaines.join(","));
  else if (domaine) q.set("domaine", domaine);
  const params = q.toString() ? `?${q}` : "";
  const res = await apiFetch(`${BASE_URL}/documents${params}`);
  if (!res.ok) throw new Error("Erreur chargement documents");
  return res.json();
}

export async function getDocumentChunks(docId: string): Promise<DocumentChunksResponse> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/chunks`);
  if (!res.ok) throw new Error("Erreur chargement chunks");
  return res.json();
}

export async function deleteDocument(docId: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erreur suppression document");
}

export async function setChefGroupe(groupeId: string, userId: string, isChef: boolean): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/admin/groupes/${groupeId}/membres/${userId}/chef`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_chef: isChef }),
  });
  if (!res.ok) throw new Error("Erreur lors de la mise à jour du rôle.");
}

// ── Configuration du site ────────────────────────────────────────────

export interface BannerConfig {
  active: boolean;
  message: string;
  url: string;
}

export interface SiteConfigData {
  banner: BannerConfig;
}

export async function getSiteConfig(): Promise<SiteConfigData> {
  const res = await apiFetch(`${BASE_URL}/admin/config`);
  if (!res.ok) throw new Error("Erreur chargement configuration");
  return res.json();
}

export async function setSiteConfig(key: string, value: unknown): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/admin/config/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error("Erreur mise à jour configuration");
}

export type ServiceStatusValue = "ok" | "error";

export interface ServiceHealth {
  status: ServiceStatusValue;
  detail?: string;
}

export interface FunctionalStats {
  nb_documents: number;
  nb_reponses_validees: number;
  tickets_echoues: number;
  tickets_bloques: number;
  documents_echoues: number;
  celery_pending_ingestion: number | null;
  celery_pending_questions: number | null;
  derniere_activite: string | null;
}

export interface ServicesHealthData {
  postgres: ServiceHealth;
  qdrant: ServiceHealth;
  valkey: ServiceHealth;
  albert_embeddings: ServiceHealth;
  albert_llm: ServiceHealth;
  albert_reranker: ServiceHealth;
  celery_ingestion: ServiceHealth;
  celery_questions: ServiceHealth;
  stats: FunctionalStats;
}

export async function getServicesHealth(): Promise<ServicesHealthData> {
  const res = await apiFetch(`${BASE_URL}/admin/health`);
  if (!res.ok) throw new Error("Erreur récupération état des services");
  return res.json();
}

// ── Incidents ────────────────────────────────────────────────────────

export interface DocumentIncident {
  task_id: string;
  filename: string | null;
  domaine: string | null;
  erreur: string | null;
}

export interface TicketIncident {
  id: string;
  question: string;
  domaine: string;
  statut_job: string;
  erreur: string | null;
  created_at: string;
}

export interface IncidentsData {
  tickets_echoues: TicketIncident[];
  tickets_bloques: TicketIncident[];
  documents_echoues: DocumentIncident[];
}

export async function getIncidents(): Promise<IncidentsData> {
  const res = await apiFetch(`${BASE_URL}/admin/incidents`);
  if (!res.ok) throw new Error("Erreur récupération incidents");
  return res.json();
}

export async function deleteTicketIncident(ticketId: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/admin/tickets/${ticketId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erreur lors de la suppression");
}

export async function retryTicket(ticketId: string): Promise<{ job_id: string }> {
  const res = await apiFetch(`${BASE_URL}/admin/tickets/${ticketId}/retry`, { method: "POST" });
  if (!res.ok) {
    let detail = "Erreur lors du relancement du ticket";
    try { const b = await res.json(); if (typeof b?.detail === "string") detail = b.detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export async function retryDocument(taskId: string): Promise<{ task_id: string }> {
  const res = await apiFetch(`${BASE_URL}/admin/documents/${taskId}/retry`, { method: "POST" });
  if (res.status === 409) {
    const b = await res.json().catch(() => ({}));
    throw new Error(b?.detail ?? "Fichier temporaire introuvable — re-uploader le document.");
  }
  if (!res.ok) throw new Error("Erreur lors du relancement du document");
  return res.json();
}

export function downloadDocumentUrl(taskId: string): string {
  return `${BASE_URL}/admin/documents/${taskId}/download`;
}

export async function deleteDocumentIncident(taskId: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/admin/documents/${taskId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erreur lors de la suppression");
}

// ── Assignation ────────────────────────────────────────────────────────────────

export type MembreGroupe = Pick<UserSummary, "id" | "email" | "prenom" | "nom">;

export async function getValidateursByDomaine(domaine: string): Promise<MembreGroupe[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/domaines/${domaine}/validateurs`);
  if (!res.ok) throw new Error("Erreur chargement validateurs");
  return res.json();
}

export async function assignTicket(ticketId: string, assigneeId: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/assigner`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assignee_id: assigneeId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? "Erreur lors de l'assignation");
  }
  return res.json();
}

export async function unassignTicket(ticketId: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE_URL}/tickets/${ticketId}/desassigner`, { method: "POST" });
  if (!res.ok) throw new Error("Erreur lors de la désassignation");
  return res.json();
}

export async function getMyAssignedTickets(): Promise<Ticket[]> {
  const res = await apiFetch(`${BASE_URL}/tickets/mes-assignations`);
  if (!res.ok) throw new Error("Erreur chargement assignations");
  return res.json();
}

// ── Notifications ──────────────────────────────────────────────────────────────

export async function getNotifications(): Promise<Notification[]> {
  const res = await apiFetch(`${BASE_URL}/notifications`);
  if (!res.ok) throw new Error("Erreur chargement notifications");
  return res.json();
}

export async function marquerNotificationLue(id: string): Promise<void> {
  await apiFetch(`${BASE_URL}/notifications/${id}/lire`, { method: "POST" });
}

export async function toutMarquerLu(): Promise<void> {
  await apiFetch(`${BASE_URL}/notifications/tout-lire`, { method: "POST" });
}

// ── Stats dashboard ────────────────────────────────────────────────────────────

export interface StatCarte {
  valeur: number;
  variation: number;
  hausse: boolean;
}

export interface RepartitionStatut {
  statut: string;
  count: number;
  pct: number;
}

export interface DayCount {
  date: string;
  count: number;
}

export interface TicketSummaryDashboard {
  id: string;
  objet: string;
  domaine: string;
  statut_ticket: string;
  statut_job: string;
  created_at: string | null;
}

export interface DashboardStats {
  periode: string;
  stats_cartes: {
    nouveaux: StatCarte;
    en_cours: StatCarte;
    tickets_clotures: StatCarte;
    repondu_canonique: StatCarte;
    temps_premiere_reponse: StatCarte;
    temps_cloture: StatCarte;
  };
  repartition_statuts: RepartitionStatut[];
  tickets_par_jour: DayCount[];
  traitement_par_jour: DayCount[];
  derniers_tickets: TicketSummaryDashboard[];
}

export async function getDashboardStats(
  domaine?: string,
  periode = "semaine",
): Promise<DashboardStats> {
  const params = new URLSearchParams({ periode });
  if (domaine) params.set("domaine", domaine);
  const res = await apiFetch(`${BASE_URL}/stats/dashboard?${params}`);
  if (!res.ok) throw new Error("Erreur chargement statistiques");
  return res.json();
}

// ── Stats équipe (chef de groupe) ─────────────────────────────────────────────

export interface MembreStats {
  id: string;
  email: string;
  prenom: string | null;
  nom: string | null;
  is_chef: boolean;
  nb_reponses_validees: number;
  nb_documents: number;
}

export interface GroupeMembresStats {
  groupe: { id: string; nom: string; domaine: string };
  membres: MembreStats[];
}

export async function getGroupeMembresStats(groupeId: string, periode = "semaine"): Promise<GroupeMembresStats> {
  const res = await apiFetch(`${BASE_URL}/stats/groupe/${groupeId}/membres?periode=${periode}`);
  if (!res.ok) throw new Error("Erreur chargement statistiques équipe");
  return res.json();
}
