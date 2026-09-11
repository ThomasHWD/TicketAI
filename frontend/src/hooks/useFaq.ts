import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { rechercherFaq } from "../lib/api";

/** En deçà, une question n'a pas assez de matière pour une recherche sémantique. */
export const LONGUEUR_MIN = 3;

/**
 * La recherche de la page FAQ : **une question à la fois**.
 *
 * Chaque recherche est indépendante — le serveur ne voit jamais les précédentes.
 * D'où le modèle de la boîte de recherche plutôt que celui du fil de discussion :
 * la question posée reste dans le champ, son résultat s'affiche dessous, et une
 * nouvelle question remplace l'ensemble. Un transcript, lui, laisserait croire
 * qu'une relance du type « et pour un apprenti ? » hérite du contexte, ce qui est
 * faux et se solderait par un résultat vide inexplicable.
 *
 * La recherche ne part qu'à la soumission : chacune consomme un embedding Albert,
 * dont le quota est de 1 000 requêtes/jour/modèle.
 */
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

  /**
   * `valeur` permet de soumettre un texte qu'on vient de poser dans le champ :
   * `setSaisie` puis `soumettre()` lirait l'état du rendu précédent.
   *
   * Le champ n'est pas vidé : il porte la recherche en cours, comme dans toute
   * barre de recherche.
   */
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
