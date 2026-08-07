/**
 * Règles de validation d'un fichier avant envoi au backend.
 *
 * Miroir volontaire des contrôles de `POST /documents` : le serveur reste seul
 * juge (extension, taille, magic bytes), ces fonctions évitent simplement un
 * aller-retour réseau pour un fichier manifestement irrecevable. Partagées par
 * la page Ingestion et la modale de mise à jour.
 */

export const ACCEPTED_EXTS = [".pdf", ".docx", ".txt", ".md"];
export const MAX_SIZE_MB = 50;

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

/** Message d'erreur à afficher, ou `null` si le fichier est acceptable. */
export function validateFile(file: File): string | null {
  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  if (!ACCEPTED_EXTS.includes(ext)) {
    return `Extension non supportée : ${ext}. Formats acceptés : PDF, DOCX, TXT, MD.`;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return `Fichier trop volumineux : ${formatSize(file.size)} (max ${MAX_SIZE_MB} Mo).`;
  }
  return null;
}
