import { apiFetch, BASE_URL } from "./client";
import { toLockConflict } from "./locks";
import type {
  ReponseEnAttente,
  ReponsesCanoniquesResponse,
  ReponsesObsoletesResponse,
  ReponsesARelireResponse,
  EditerCanoniquePayload,
  FaqVisiblePayload,
  ValiderPayload,
  RejeterPayload,
  CorrigerPayload,
  Domaine,
} from "../../types";

export async function getReponsesEnAttente(domaine?: Domaine): Promise<ReponseEnAttente[]> {
  const params = domaine ? `?domaine=${domaine}` : "";
  const res = await apiFetch(`${BASE_URL}/reponses/en-attente${params}`);
  if (!res.ok) throw new Error("Erreur chargement réponses");
  return res.json();
}

export async function getReponsesCanoniques(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  q?: string;
  tag?: string;
  ordre?: "date" | "occurence";
}): Promise<ReponsesCanoniquesResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.q) query.set("q", params.q);
  if (params?.tag) query.set("tag", params.tag);
  if (params?.ordre && params.ordre !== "date") query.set("ordre", params.ordre);
  const res = await apiFetch(`${BASE_URL}/reponses/canoniques?${query}`);
  if (!res.ok) throw new Error("Erreur chargement réponses canoniques");
  return res.json();
}

export async function getReponsesObsoletes(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  q?: string;
}): Promise<ReponsesObsoletesResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.q) query.set("q", params.q);
  const res = await apiFetch(`${BASE_URL}/reponses/obsoletes?${query}`);
  if (!res.ok) throw new Error("Erreur chargement réponses obsolètes");
  return res.json();
}

export async function getReponsesARelire(params?: {
  page?: number;
  limit?: number;
  domaine?: Domaine;
  q?: string;
}): Promise<ReponsesARelireResponse> {
  const query = new URLSearchParams();
  if (params?.page) query.set("page", String(params.page));
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.domaine) query.set("domaine", params.domaine);
  if (params?.q) query.set("q", params.q);
  const res = await apiFetch(`${BASE_URL}/reponses/a-relire?${query}`);
  if (!res.ok) throw new Error("Erreur chargement réponses à relire");
  return res.json();
}

/** « Toujours d'actualité » : le signalement tombe, rien d'autre ne change. */
export async function confirmerActualite(reponseId: string) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/confirmer-actualite`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Erreur confirmation de la réponse");
  return res.json();
}

export async function confirmerActualiteLot(doc_id: string, version: number) {
  const res = await apiFetch(`${BASE_URL}/reponses/confirmer-actualite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id, version }),
  });
  if (!res.ok) throw new Error("Erreur confirmation groupée");
  return res.json();
}

/** Bascule la réponse dans les obsolètes, d'où elle reste restaurable. */
export async function retirerReponse(reponseId: string) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/retirer`, { method: "POST" });
  if (!res.ok) throw new Error("Erreur retrait de la réponse");
  return res.json();
}

export async function restaurerReponse(reponseId: string) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/restaurer`, { method: "POST" });
  if (!res.ok) throw new Error("Erreur restauration de la réponse");
  return res.json();
}

export async function editerReponseCanonique(reponseId: string, payload: EditerCanoniquePayload) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/editer`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Erreur édition réponse canonique");
  return res.json();
}

export async function supprimerReponseCanonique(reponseId: string) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Erreur suppression réponse canonique");
  return res.json();
}

export async function validerReponse(reponseId: string, payload: ValiderPayload) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/valider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur validation");
  if (!res.ok) throw new Error("Erreur validation");
  return res.json();
}

export async function rejeterReponse(reponseId: string, payload: RejeterPayload) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/rejeter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur rejet");
  if (!res.ok) throw new Error("Erreur rejet");
  return res.json();
}

export async function corrigerReponse(reponseId: string, payload: CorrigerPayload) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/corriger`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw await toLockConflict(res, "Erreur correction");
  if (!res.ok) throw new Error("Erreur correction");
  return res.json();
}

export async function basculerFaqVisible(reponseId: string, payload: FaqVisiblePayload) {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/faq-visible`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Erreur mise à jour FAQ");
  return res.json();
}

export async function updateTag(reponseId: string, tag: string | null): Promise<{ tag: string | null }> {
  const res = await apiFetch(`${BASE_URL}/reponses/${reponseId}/tag`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag }),
  });
  if (!res.ok) throw new Error("Erreur mise à jour du tag");
  return res.json();
}

export async function getTags(domaine?: string, canoniques?: boolean): Promise<string[]> {
  const query = new URLSearchParams();
  if (domaine) query.set("domaine", domaine);
  if (canoniques) query.set("canoniques", "true");
  const qs = query.toString();
  const res = await apiFetch(`${BASE_URL}/tags${qs ? `?${qs}` : ""}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Erreur chargement des tags");
  return res.json();
}
