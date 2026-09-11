import { useEffect, useRef } from "react";
import { Search } from "lucide-react";

const HAUTEUR_MAX = 180;

interface Props {
  valeur: string;
  onChange: (valeur: string) => void;
  onSoumettre: () => void;
  peutChercher: boolean;
  /** L'astuce clavier n'est montrée qu'à l'accueil : elle s'apprend une fois. */
  astuce?: boolean;
  autoFocus?: boolean;
}

/**
 * Le champ de question, unique élément d'action de la page.
 *
 * Il grandit avec la saisie plutôt que d'imposer une hauteur fixe : une question
 * d'une ligne ne doit pas ouvrir un pavé vide, une question de cinq lignes ne
 * doit pas défiler dans une fenêtre de deux. Le bouton reste calé en bas
 * (`items-end`) pour ne pas dériver quand le champ s'allonge, et l'astuce clavier
 * vit **hors** du cadre : à l'intérieur, elle creusait un vide sous le texte.
 */
export default function FaqComposeur({
  valeur,
  onChange,
  onSoumettre,
  peutChercher,
  astuce = false,
  autoFocus = false,
}: Props) {
  const zone = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = zone.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, HAUTEUR_MAX)}px`;
  }, [valeur]);

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSoumettre();
        }}
        className="flex items-end gap-2 rounded-3xl border border-gray-200 bg-white px-4 py-2.5 shadow-sm transition-colors focus-within:border-emerald-500/50 dark:border-white/10 dark:bg-white/[0.04] dark:focus-within:border-emerald-500/40"
      >
        <label htmlFor="question-faq" className="sr-only">
          Votre question
        </label>
        <textarea
          ref={zone}
          id="question-faq"
          value={valeur}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSoumettre();
            }
          }}
          rows={1}
          maxLength={500}
          autoFocus={autoFocus}
          placeholder="Posez votre question…"
          className="flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-6 text-gray-800 placeholder:text-gray-400 focus:outline-none dark:text-gray-100 dark:placeholder:text-gray-500"
        />
        <button
          type="submit"
          disabled={!peutChercher}
          aria-label="Rechercher"
          className="mb-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-emerald-600 text-white transition-colors hover:bg-emerald-700 disabled:bg-gray-100 disabled:text-gray-400 dark:disabled:bg-white/[0.07] dark:disabled:text-gray-500"
        >
          <Search size={16} aria-hidden="true" />
        </button>
      </form>

      {astuce && (
        <p className="mt-2 text-center text-[11px] text-gray-400 dark:text-gray-600">
          Entrée pour rechercher · Maj+Entrée pour aller à la ligne
        </p>
      )}
    </div>
  );
}
