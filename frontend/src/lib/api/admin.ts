import { apiFetch, extractApiErrorDetail, BASE_URL } from "./client";

export async function setChefGroupe(groupeId: string, userId: string, isChef: boolean): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/admin/groupes/${groupeId}/membres/${userId}/chef`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_chef: isChef }),
  });
  if (!res.ok) throw new Error("Erreur lors de la mise à jour du rôle.");
}

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
  latency_ms?: number;
}

export interface FunctionalStats {
  nb_documents: number;
  nb_reponses_validees: number;
  tickets_echoues: number;
  tickets_bloques: number;
  documents_echoues: number;
  celery_pending_ingestion: number | null;
  celery_pending_questions: number | null;
  celery_workers_ingestion: number | null;
  celery_workers_questions: number | null;
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
  celery_beat: ServiceHealth;
  stats: FunctionalStats;
}

export async function getServicesHealth(): Promise<ServicesHealthData> {
  const res = await apiFetch(`${BASE_URL}/admin/health`);
  if (!res.ok) throw new Error("Erreur récupération état des services");
  return res.json();
}

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
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors du relancement du ticket"));
  return res.json();
}

export async function retryDocument(taskId: string): Promise<{ task_id: string }> {
  const res = await apiFetch(`${BASE_URL}/admin/documents/${taskId}/retry`, { method: "POST" });
  if (res.status === 409) {
    throw new Error(await extractApiErrorDetail(res, "Fichier temporaire introuvable — re-uploader le document."));
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
