import { apiFetch, extractApiErrorDetail, BASE_URL } from "./client";
import type {
  Domaine,
  DocumentUploadResponse,
  DocumentStatus,
  IndexedDocumentsResponse,
  DocumentChunksResponse,
} from "../../types.ts";

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
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de l'envoi du document"));
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
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur suppression document"));
}

/**
 * Télécharge le fichier original.
 *
 * Passe par fetch et non par un `<a href>` : le token est un Bearer en localStorage,
 * une navigation directe part donc sans en-tête `Authorization` et se fait refuser.
 */
export async function downloadDocument(docId: string, filename: string | null): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/download`);
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur téléchargement du document"));

  const url = URL.createObjectURL(await res.blob());
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename ?? docId;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
