import { apiFetch, BASE_URL, extractApiErrorDetail } from "./client";

export interface FaqResultat {
  reponse_id: string;
  /** Formulation sous laquelle la réponse est indexée, et qui a matché la question posée. */
  question: string;
  domaine: string;
  contenu: string;
  tag: string | null;
  nb_validations: number;
  validated_at: string | null;
}

export interface FaqRecherche {
  question: string;
  resultats: FaqResultat[];
  /**
   * Pistes proposées **uniquement** quand `resultats` est vide : des réponses
   * proches sans l'être assez pour être présentées comme la réponse. Le serveur
   * garantit qu'elles ne coexistent jamais avec un résultat sûr.
   */
  incertains: FaqResultat[];
}

/**
 * Cherche parmi les réponses canoniques, tous domaines confondus.
 *
 * Chaque appel consomme un embedding Albert : ne jamais l'appeler à la frappe.
 */
export async function rechercherFaq(q: string, limit?: number): Promise<FaqRecherche> {
  const params = new URLSearchParams({ q });
  if (limit) params.set("limit", String(limit));

  const res = await apiFetch(`${BASE_URL}/faq/recherche?${params}`);
  if (res.status === 429) {
    throw new Error("Trop de recherches d'affilée. Patientez quelques instants.");
  }
  if (!res.ok) {
    throw new Error(await extractApiErrorDetail(res, "La recherche a échoué. Réessayez."));
  }
  return res.json();
}
