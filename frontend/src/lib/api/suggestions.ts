import { apiFetch, BASE_URL } from "./client";

export interface SuggestionOut {
  id: string;
  contenu: string;
  lu: boolean;
  created_at: string;
  user_email: string | null;
  user_nom: string | null;
}

export async function soumettresuggestion(contenu: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/suggestions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contenu }),
  });
  if (!res.ok) throw new Error("Erreur lors de l'envoi de la suggestion");
}

export async function getSuggestions(): Promise<SuggestionOut[]> {
  const res = await apiFetch(`${BASE_URL}/suggestions`);
  if (!res.ok) throw new Error("Erreur lors du chargement des suggestions");
  return res.json();
}

export async function toggleSuggestionLu(id: string): Promise<{ lu: boolean }> {
  const res = await apiFetch(`${BASE_URL}/suggestions/${id}/lu`, { method: "PATCH" });
  if (!res.ok) throw new Error("Erreur");
  return res.json();
}
