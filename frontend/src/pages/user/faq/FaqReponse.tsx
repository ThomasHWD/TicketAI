import { AlertCircle } from "lucide-react";
import { renderMarkdown } from "../../../components/ticket/utils";
import { DomaineBadge } from "../../../components/tickets/StatusBadge";
import type { FaqResultat as Resultat } from "../../../lib/api";
import FaqRepli from "./FaqRepli";
import FaqResultat from "./FaqResultat";

interface Props {
  question: string;
  resultats: Resultat[];
  /** Pistes du second rang, non vides seulement quand `resultats` l'est. */
  incertains: Resultat[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  onReessayer: () => void;
}

/**
 * Le résultat de la recherche en cours.
 *
 * Un seul bloc, remplacé à chaque nouvelle question : rien ne s'empile, donc
 * rien ne suggère qu'une question hérite de la précédente.
 */
export default function FaqReponse({
  question,
  resultats,
  incertains,
  isLoading,
  isError,
  error,
  onReessayer,
}: Props) {
  const [principal, ...secondaires] = resultats;

  if (isLoading) {
    return (
      <div className="space-y-2.5 motion-safe:animate-pulse" aria-hidden="true">
        <div className="h-4 w-2/3 rounded bg-gray-200 dark:bg-white/10" />
        <div className="h-3 w-full rounded bg-gray-100 dark:bg-white/5" />
        <div className="h-3 w-full rounded bg-gray-100 dark:bg-white/5" />
        <div className="h-3 w-4/5 rounded bg-gray-100 dark:bg-white/5" />
      </div>
    );
  }

  if (isError) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-600 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-400"
      >
        <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
        <span className="flex-1">
          {error instanceof Error ? error.message : "La recherche a échoué."}
        </span>
        <button
          type="button"
          onClick={onReessayer}
          className="shrink-0 text-xs font-medium underline underline-offset-2 hover:no-underline"
        >
          Réessayer
        </button>
      </div>
    );
  }

  // Rien d'assez proche pour être présenté comme la réponse, mais des voisins
  // plausibles : on les propose comme pistes, sans les annoncer comme des
  // réponses — c'est exactement leur statut.
  if (!principal && incertains.length > 0) {
    return (
      <div className="space-y-5">
        <p className="text-[15px] leading-7 text-gray-700 dark:text-gray-300">
          Rien ne correspond exactement à votre question. Peut-être cherchiez-vous ceci&nbsp;?
        </p>
        <ul className="divide-y divide-gray-100 dark:divide-white/5">
          {incertains.map((resultat) => (
            <FaqResultat key={resultat.reponse_id} resultat={resultat} />
          ))}
        </ul>
        <FaqRepli question={question} sousTitre="Si aucune de ces pistes ne répond à votre besoin." />
      </div>
    );
  }

  if (!principal) {
    return (
      <div className="space-y-4">
        <p className="text-[15px] leading-7 text-gray-700 dark:text-gray-300">
          Aucune réponse ne correspond à cette question pour le moment.
        </p>
        <FaqRepli question={question} sousTitre="Sa réponse rejoindra ensuite cette page." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <article className="space-y-2.5">
        <div className="flex items-start gap-3">
          <h2 className="flex-1 text-base font-semibold text-gray-900 dark:text-gray-50">
            {principal.question}
          </h2>
          <DomaineBadge domaine={principal.domaine} />
        </div>
        {/* Pas de `whitespace-pre-wrap` : `renderMarkdown` pose ses propres
            `<br />`, les deux ensemble doubleraient les sauts de ligne. */}
        <p className="text-[15px] leading-7 text-gray-700 dark:text-gray-300">
          {renderMarkdown(principal.contenu)}
        </p>
      </article>

      {secondaires.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-xs font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
            Autres réponses proches
          </h3>
          <ul className="divide-y divide-gray-100 dark:divide-white/5">
            {secondaires.map((resultat) => (
              <FaqResultat key={resultat.reponse_id} resultat={resultat} />
            ))}
          </ul>
        </div>
      )}

      <FaqRepli question={question} sousTitre="Si aucune de ces réponses ne convient à votre situation." />
    </div>
  );
}
