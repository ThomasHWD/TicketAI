import type { ReponseSignalee } from "../../../types";

export function contenuServi(r: { contenu: string; contenu_corrige: string | null }): string {
  return r.contenu_corrige ?? r.contenu;
}

const RELATIF = new Intl.RelativeTimeFormat("fr-FR", { numeric: "auto" });
const SEUILS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

export function depuis(iso: string | null): string {
  if (!iso) return "—";
  const secondes = (Date.now() - new Date(iso).getTime()) / 1000;
  for (const [unite, taille] of SEUILS) {
    if (secondes >= taille) return RELATIF.format(-Math.floor(secondes / taille), unite);
  }
  return RELATIF.format(-Math.floor(secondes), "second");
}

export const LIMIT = 10;
export const SEUIL_EXPANSION = 350;

export type Onglet = "canoniques" | "obsoletes" | "a_relire";

export type CibleSuppression = { reponse_id: string; question: string; obsolete: boolean };

export type GroupeARelire = {
  cle: string;
  doc_id: string | null;
  version: number | null;
  filename: string | null;
  document_supprime: boolean;
  raison: ReponseSignalee["a_relire_raison"];
  changements: ReponseSignalee["changements"];
  reponses: ReponseSignalee[];
};

export function grouper(items: ReponseSignalee[]): GroupeARelire[] {
  const groupes = new Map<string, GroupeARelire>();
  for (const r of items) {
    const cle = `${r.doc_id ?? "?"}#${r.a_relire_version ?? "?"}`;
    const groupe = groupes.get(cle);
    if (groupe) {
      groupe.reponses.push(r);
    } else {
      groupes.set(cle, {
        cle,
        doc_id: r.doc_id,
        version: r.a_relire_version,
        filename: r.document_filename,
        document_supprime: r.document_supprime,
        raison: r.a_relire_raison,
        changements: r.changements,
        reponses: [r],
      });
    }
  }
  return [...groupes.values()];
}

export const RAISONS: Record<NonNullable<ReponseSignalee["a_relire_raison"]>, string> = {
  CONTREDITE_PROBABLE:
    "L'analyse juge cette réponse contredite, mais elle ne cite pas ce document : à confirmer avant tout retrait.",
  ANALYSE_EN_COURS: "Analyse en cours — le verdict n'est pas encore rendu.",
  ANALYSE_INDISPONIBLE:
    "Le service d'analyse n'a pas pu se prononcer : cette réponse est signalée par précaution.",
  ANALYSE_PARTIELLE:
    "Le budget d'analyse de cette mise à jour a été épuisé avant d'atteindre cette réponse.",
  REECRITURE_MASSIVE:
    "Le document a été réécrit en profondeur : trop de changements pour juger réponse par réponse.",
  DOC_MODIFIÉ: "L'analyse n'a pas su conclure : à trancher à la main.",
  NOUVEAU_DOC:
    "Un document vient d'être ajouté et pourrait concerner cette réponse : l'analyse n'a pas su conclure.",
  VERSION_SORTANTE_ILLISIBLE:
    "La version précédente n'a pas pu être relue : impossible de dire ce qui a changé.",
};

export const EN_ANALYSE = "ANALYSE_EN_COURS";

export const RAISONS_DE_GROUPE = ["VERSION_SORTANTE_ILLISIBLE", "REECRITURE_MASSIVE"] as const;

export function estRaisonDeGroupe(raison: ReponseSignalee["a_relire_raison"]): boolean {
  return RAISONS_DE_GROUPE.some((r) => r === raison);
}
