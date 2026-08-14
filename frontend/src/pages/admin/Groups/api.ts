import { apiFetch } from "../../../lib/api";
import type { Groupe, UserSummary } from "../../../types/index.tsx";

export async function fetchGroupes(): Promise<Groupe[]> {
  const res = await apiFetch("/api/v1/admin/groupes");
  return res.json();
}

export async function fetchGestionnaires(): Promise<UserSummary[]> {
  const res = await apiFetch("/api/v1/admin/gestionnaires");
  return res.json();
}

export async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/admin/domaines");
  return res.json();
}

export async function createGroupe(body: { nom: string; domaine: string }): Promise<Groupe> {
  const res = await apiFetch("/api/v1/admin/groupes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.detail ?? "Erreur lors de la création.");
  }
  return res.json();
}

export async function deleteGroupe(id: string): Promise<void> {
  await apiFetch(`/api/v1/admin/groupes/${id}`, { method: "DELETE" });
}

export async function addMembre(groupeId: string, userId: string): Promise<Groupe> {
  const res = await apiFetch(`/api/v1/admin/groupes/${groupeId}/membres/${userId}`, {
    method: "POST",
  });
  return res.json();
}

export async function removeMembre(groupeId: string, userId: string): Promise<void> {
  await apiFetch(`/api/v1/admin/groupes/${groupeId}/membres/${userId}`, { method: "DELETE" });
}
