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

/** FAQ question field. Auto-grows with input; button stays bottom-aligned so it doesn't drift; keyboard hint is outside the frame (inside caused empty space under text). */
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
          className="flex-1 resize-none bg-transparent py-1.5 text-[15px] leading-6 text-gray-800 placeholder:text-muted-foreground focus:outline-none dark:text-gray-100"
        />
        <button
          type="submit"
          disabled={!peutChercher}
          aria-label="Rechercher"
          className="mb-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary-hover disabled:bg-gray-100 disabled:text-gray-400 dark:disabled:bg-white/[0.07] dark:disabled:text-gray-500"
        >
          <Search size={16} aria-hidden="true" />
        </button>
      </form>

      {astuce && (
        <p className="mt-2 text-center text-[11px] text-muted-foreground">
          Entrée pour rechercher · Maj+Entrée pour aller à la ligne
        </p>
      )}
    </div>
  );
}
