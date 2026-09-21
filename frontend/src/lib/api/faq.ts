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
  /** Hints returned *only* when `resultats` is empty — server guarantees they never coexist with a sure result. */
  incertains: FaqResultat[];
}

/** Search canonical answers across all domains. Each call costs one Albert embedding — never call on keystroke. */
export async function rechercherFaq(q: string, limit?: number): Promise<FaqRecherche> {
  const params = new URLSearchParams({ q });
  if (limit) params.set("limit", String(limit));

  const res = await apiFetch(`${BASE_URL}/faq/recherche?${params}`);
  if (res.status === 429) {
    const retryAfter = Number(res.headers.get("Retry-After") ?? 0);
    const msg =
      retryAfter > 3600
        ? "Vous avez atteint votre quota de recherches pour aujourd'hui."
        : "Trop de recherches d'affilée. Patientez quelques instants.";
    throw new Error(msg);
  }
  if (!res.ok) {
    throw new Error(await extractApiErrorDetail(res, "La recherche a échoué. Réessayez."));
  }
  return res.json();
}
