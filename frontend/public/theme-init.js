// Fichier externe et non <script> inline : la CSP de nginx (script-src 'self') bloque tout script inline.
// Chargé de façon bloquante dans <head> pour poser la classe `dark` avant le premier rendu (pas de flash).
(function () {
  try {
    var t = localStorage.getItem("theme");
    if (!t) t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    if (t === "dark") document.documentElement.classList.add("dark");
    window.__TK_THEME__ = t;
  } catch (e) { window.__TK_THEME__ = "dark"; }
})();
