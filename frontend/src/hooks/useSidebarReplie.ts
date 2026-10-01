import { useEffect, useState, useSyncExternalStore } from "react";

// WCAG 1.4.10 : à 200 % de zoom, un écran 1440 px n'offre plus que 720 px CSS. Sous ce seuil la
// sidebar se replie d'elle-même (224 px → 56 px) ; au-dessus, le choix de l'utilisateur est mémorisé.
const ETROIT = "(max-width: 1099px)";
const CLE = "ticketai.sidebar";

function abonner(cb: () => void) {
  const mq = window.matchMedia(ETROIT);
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}
const estEtroit = () => window.matchMedia(ETROIT).matches;

function lirePreference(): boolean {
  try {
    return localStorage.getItem(CLE) === "replie";
  } catch {
    return false;
  }
}

export function useSidebarReplie() {
  const etroit = useSyncExternalStore(abonner, estEtroit);
  const [prefere, setPrefere] = useState(lirePreference);
  // En largeur étroite, déplier est un geste ponctuel : il ne touche pas à la préférence mémorisée.
  const [ouvertPonctuel, setOuvertPonctuel] = useState(false);

  useEffect(() => {
    if (!etroit) setOuvertPonctuel(false);
  }, [etroit]);

  const replie = etroit ? !ouvertPonctuel : prefere;

  function basculer() {
    if (etroit) {
      setOuvertPonctuel((v) => !v);
      return;
    }
    setPrefere((v) => {
      try {
        localStorage.setItem(CLE, v ? "deplie" : "replie");
      } catch { /* stockage indisponible : vaut pour la session */ }
      return !v;
    });
  }

  return { replie, basculer };
}
