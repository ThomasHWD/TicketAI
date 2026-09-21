import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { rechercherFaq } from "../lib/api";

/** En deçà, une question n'a pas assez de matière pour une recherche sémantique. */
export const LONGUEUR_MIN = 3;

/** One question at a time — no context between searches (prevents "et pour un apprenti?" from implying inherited context). Each search costs one Albert embedding. */
export function useFaq() {
  const [saisie, setSaisie] = useState("");
  const [requete, setRequete] = useState("");

  const recherche = useQuery({
    queryKey: ["faq", requete],
    queryFn: () => rechercherFaq(requete),
    enabled: requete.length >= LONGUEUR_MIN,
    // Reposer la même question ne doit pas rappeler Albert.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: false,
  });

  // `valeur` lets you submit text you just set — `setSaisie` then `soumettre()` would read the previous render's state.
  function soumettre(valeur?: string) {
    const question = (valeur ?? saisie).trim();
    if (question.length < LONGUEUR_MIN) return;
    if (valeur !== undefined) setSaisie(valeur);
    setRequete(question);
  }

  return {
    saisie,
    setSaisie,
    requete,
    soumettre,
    peutChercher: saisie.trim().length >= LONGUEUR_MIN,
    resultats: recherche.data?.resultats ?? [],
    incertains: recherche.data?.incertains ?? [],
    isLoading: recherche.isFetching,
    isError: recherche.isError,
    error: recherche.error,
    refetch: recherche.refetch,
    /** Vrai tant qu'aucune question n'a été posée : écran d'accueil. */
    auRepos: requete.length < LONGUEUR_MIN,
  };
}
