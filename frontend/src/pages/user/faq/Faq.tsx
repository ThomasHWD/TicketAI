import { useFaq } from "../../../hooks/useFaq";
import FaqComposeur from "./FaqComposeur";
import FaqReponse from "./FaqReponse";

// Safe to edit — no semantic impact on search results.
const EXEMPLES = [
  "Combien de jours de congés puis-je reporter ?",
  "Quel matériel est fourni pour le télétravail ?",
  "Comment déclarer mon abonnement de transport ?",
];

export default function Faq() {
  const faq = useFaq();

  const composeur = (astuce: boolean) => (
    <FaqComposeur
      valeur={faq.saisie}
      onChange={faq.setSaisie}
      onSoumettre={faq.soumettre}
      peutChercher={faq.peutChercher}
      astuce={astuce}
      autoFocus
    />
  );

  // At rest: input centered, nothing else — no question means nothing to show.
  if (faq.auRepos) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <div className="w-full max-w-2xl space-y-6 pb-16">
          <h1 className="text-center text-2xl font-semibold text-gray-800 dark:text-gray-100">
            Que cherchez-vous&nbsp;?
          </h1>
          {composeur(true)}
          <div className="flex flex-wrap justify-center gap-2">
            {EXEMPLES.map((exemple) => (
              <button
                key={exemple}
                type="button"
                onClick={() => faq.soumettre(exemple)}
                className="rounded-full border border-gray-200 px-3 py-1.5 text-xs text-gray-500 transition-colors hover:border-gray-300 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-white/10 dark:text-gray-400 dark:hover:border-white/20 dark:hover:text-gray-200"
              >
                {exemple}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 px-6 pb-24 pt-6">
      {composeur(false)}

      {/* One question at a time — result below always reflects the field above, nothing else. */}
      <p aria-live="polite" className="sr-only">
        {faq.isLoading
          ? "Recherche en cours"
          : faq.isError
            ? ""
            : `${faq.resultats.length} réponse${faq.resultats.length > 1 ? "s" : ""} trouvée${faq.resultats.length > 1 ? "s" : ""} pour ${faq.requete}`}
      </p>

      <FaqReponse
        question={faq.requete}
        resultats={faq.resultats}
        incertains={faq.incertains}
        isLoading={faq.isLoading}
        isError={faq.isError}
        error={faq.error}
        onReessayer={faq.refetch}
      />
    </div>
  );
}
