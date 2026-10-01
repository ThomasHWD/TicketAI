// Nombres affichés au format français : virgule décimale (« 43,2 » et jamais « 43.2 »).
const UNE_DECIMALE_MAX = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const UNE_DECIMALE = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** 43.2 → « 43,2 » ; 40 → « 40 ». */
export const nombreFr = (n: number) => UNE_DECIMALE_MAX.format(n);

/** Note sur 5 : 4 → « 4,0 ». */
export const noteFr = (n: number) => UNE_DECIMALE.format(n);
