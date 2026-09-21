import { apiFetch, extractApiErrorDetail, readApiErrorDetail, BASE_URL } from "./client";
import type {
  Domaine,
  DocumentUploadResponse,
  DocumentHomonyme,
  DocumentStatus,
  DocumentVersionsResponse,
  IndexedDocumentsResponse,
  DocumentChunksResponse,
  UpdateImpact,
} from "../../types";

/** Dedicated error class (not a message) because the caller needs `doc_id` to offer an in-place update. */
export class DocumentHomonymeError extends Error {
  // Declared then assigned, not a parameter property — project compiles with `erasableSyntaxOnly`.
  readonly document: DocumentHomonyme;

  constructor(document: DocumentHomonyme) {
    super(`Un document « ${document.filename} » existe déjà dans ce domaine.`);
    this.name = "DocumentHomonymeError";
    this.document = document;
  }
}

function estHomonyme(detail: unknown): detail is DocumentHomonyme {
  return typeof detail === "object" && detail !== null && "code" in detail
    && (detail as { code: unknown }).code === "DOCUMENT_HOMONYME";
}

export async function uploadDocument(
  file: File,
  domaine: Domaine,
  description = "",
  forceNouveau = false,
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams({ domaine });
  if (description) params.set("description", description);
  if (forceNouveau) params.set("force_nouveau", "true");
  const res = await apiFetch(`${BASE_URL}/documents?${params}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const detail = await readApiErrorDetail(res);
    if (estHomonyme(detail)) throw new DocumentHomonymeError(detail);
    throw new Error(typeof detail === "string" ? detail : "Erreur lors de l'envoi du document");
  }
  return res.json();
}

export async function previewDocumentUpdate(
  docId: string,
  file: File,
  description?: string,
): Promise<UpdateImpact> {
  const form = new FormData();
  form.append("file", file);
  const params = new URLSearchParams();
  if (description !== undefined) params.set("description", description);
  const query = params.toString() ? `?${params}` : "";
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/versions/preview${query}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de l'analyse d'impact"));
  return res.json();
}

export async function confirmDocumentUpdate(
  docId: string,
  stagingId: string,
): Promise<DocumentUploadResponse & { version: number }> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/versions/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ staging_id: stagingId }),
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de la mise à jour"));
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

/** Download via fetch not `<a href>` — Bearer token is in localStorage, direct navigation has no Authorization header. */
async function telecharger(url: string, nom: string, erreur: string): Promise<void> {
  const res = await apiFetch(url);
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, erreur));

  const objectUrl = URL.createObjectURL(await res.blob());
  try {
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = nom;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export async function downloadDocument(docId: string, filename: string | null): Promise<void> {
  await telecharger(
    `${BASE_URL}/documents/${docId}/download`,
    filename ?? docId,
    "Erreur téléchargement du document",
  );
}

export async function getDocumentVersions(docId: string): Promise<DocumentVersionsResponse> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/versions`);
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur chargement de l'historique"));
  return res.json();
}

export async function downloadDocumentVersion(
  docId: string,
  version: number,
  filename: string,
): Promise<void> {
  await telecharger(
    `${BASE_URL}/documents/${docId}/versions/${version}/download`,
    filename,
    "Erreur téléchargement de la version",
  );
}

/** Stages a version restore — same impact flow as an update; confirm with `confirmDocumentUpdate`. Modifies nothing. */
export async function restoreDocumentVersion(
  docId: string,
  version: number,
): Promise<UpdateImpact> {
  const res = await apiFetch(`${BASE_URL}/documents/${docId}/versions/${version}/restaurer`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await extractApiErrorDetail(res, "Erreur lors de la restauration"));
  return res.json();
}
