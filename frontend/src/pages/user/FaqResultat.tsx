import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { renderMarkdown } from "../../components/ticket/utils";
import { DomaineBadge } from "../../components/tickets/StatusBadge";
import type { FaqResultat as Resultat } from "../../lib/api";

/**
 * Une correspondance secondaire, repliée.
 *
 * Délibérément sans carte ni ombre : ces réponses ne sont pas au même rang que
 * la première. Leur donner le même poids visuel est ce qui transformait la page
 * en grille de blocs équivalents, alors que l'écart de pertinence entre le
 * premier résultat et les suivants est en général très large.
 */
export default function FaqResultat({ resultat }: { resultat: Resultat }) {
  const [ouvert, setOuvert] = useState(false);
  const panneauId = `faq-panneau-${resultat.reponse_id}`;

  return (
    <li>
      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        aria-expanded={ouvert}
        aria-controls={panneauId}
        className="group flex w-full items-start gap-3 py-3.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-[#0d0d0d] rounded-sm"
      >
        <ChevronDown
          size={15}
          aria-hidden="true"
          className={`mt-0.5 shrink-0 text-gray-400 transition-transform duration-200 ${ouvert ? "rotate-180" : ""}`}
        />
        <span className="flex-1 text-sm text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors">
          {resultat.question}
        </span>
        <DomaineBadge domaine={resultat.domaine} />
      </button>

      {ouvert && (
        <p
          id={panneauId}
          className="pb-4 pl-[1.625rem] text-sm leading-relaxed text-gray-600 dark:text-gray-400"
        >
          {renderMarkdown(resultat.contenu)}
        </p>
      )}
    </li>
  );
}
