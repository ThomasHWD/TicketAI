import { useEffect } from "react";

const SUFFIXE = "ONaCVG";

// WCAG 2.4.2 : chaque page a son titre — onglets, historique et lecteurs d'écran les distinguent.
const TITRES: Record<string, string> = {
  "/": "Tableau de bord",
  "/tickets": "Tickets",
  "/mon-suivi": "Mon suivi",
  "/reponses-enregistrees": "Réponses enregistrées",
  "/base-de-connaissances": "Base de connaissances",
  "/mon-espace": "Mon espace",
  "/faq": "Questions fréquentes",
  "/nouveau-ticket": "Nouvelle question",
  "/historique": "Mon historique",
  "/suggestion": "Faire une suggestion",
  "/admin": "Groupes",
  "/admin/config": "Configuration",
  "/admin/dashboard": "Vue globale",
};

/** Titre d'une route statique ; null pour les fiches (/tickets/:id…), qui posent leur propre titre. */
export function titreRoute(pathname: string): string | null {
  const chemin = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (chemin in TITRES) return TITRES[chemin];
  if (/^\/(tickets|historique)\/[^/]+$/.test(chemin)) return null;
  return "Page introuvable";
}

export function useDocumentTitle(titre: string | null | undefined) {
  useEffect(() => {
    if (titre) document.title = `${titre} · ${SUFFIXE}`;
  }, [titre]);
}
