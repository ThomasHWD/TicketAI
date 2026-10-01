import { useEffect, useSyncExternalStore } from "react";

// Raccourcis de la fiche ticket (V / E / R, Alt+←). WCAG 2.1.4 : désactivables, et aucun n'engage
// seul une validation — V amène le focus sur « Valider », c'est Entrée qui confirme. Une validation
// compte pour la promotion canonique : une touche égarée ne doit pas pouvoir l'ajouter.

const CLE = "ticketai.raccourcis";
const EVENEMENT = "ticketai:raccourcis";

function lireActifs(): boolean {
  try {
    return localStorage.getItem(CLE) !== "off";
  } catch {
    return true;
  }
}

export function setRaccourcisActifs(actifs: boolean) {
  try {
    localStorage.setItem(CLE, actifs ? "on" : "off");
  } catch { /* stockage indisponible : le choix vaut pour la session */ }
  window.dispatchEvent(new Event(EVENEMENT));
}

function abonner(cb: () => void) {
  window.addEventListener(EVENEMENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENEMENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function useRaccourcisActifs() {
  return useSyncExternalStore(abonner, lireActifs);
}

const ACTIONS: Record<string, string> = { v: "valider", e: "corriger", r: "rejeter" };

/** Panneau d'actions visé : celui de la réponse qui a le focus, sinon l'unique présent — jamais « le premier ». */
function panneauVise(): HTMLElement | null {
  const panneaux = [...document.querySelectorAll<HTMLElement>("[data-reponse-actions]")];
  const focus = document.activeElement;
  const avecFocus = panneaux.find((p) => (p.closest("[data-reponse-item]") ?? p).contains(focus));
  if (avecFocus) return avecFocus;
  return panneaux.length === 1 ? panneaux[0] : null;
}

function saisieEnCours(cible: EventTarget | null) {
  const el = cible as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function useRaccourcisReponse(onRetour: () => void) {
  const actifs = useRaccourcisActifs();

  useEffect(() => {
    if (!actifs) return;
    const handler = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.repeat) return;
      // Une modale ouverte garde le clavier pour elle : rien ne doit agir sur la page en dessous.
      if (document.querySelector('[aria-modal="true"]')) return;
      if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); onRetour(); return; }
      if (e.altKey || e.ctrlKey || e.metaKey || saisieEnCours(e.target)) return;

      const action = ACTIONS[e.key.toLowerCase()];
      if (!action) return;
      const bouton = panneauVise()?.querySelector<HTMLButtonElement>(`[data-action="${action}"]:not(:disabled)`);
      if (!bouton) return;
      e.preventDefault();
      if (action === "valider") bouton.focus(); // focus() fait défiler jusqu'au bouton
      else bouton.click();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [actifs, onRetour]);
}
