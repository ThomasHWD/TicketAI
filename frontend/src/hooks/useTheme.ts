import { useState, useEffect, useCallback } from "react";

export type Theme = "light" | "dark";

function readTheme(): Theme {
  const saved = localStorage.getItem("theme");
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Gère le thème clair/sombre : bascule la classe `dark` sur <html> et
 * persiste le choix dans localStorage. L'application initiale se fait dans
 * index.html (anti-flash) ; ce hook garde React synchronisé.
 */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(readTheme);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }, []);

  return { theme, toggle };
}
