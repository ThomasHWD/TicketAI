import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, SendHorizontal } from "lucide-react";
import { soumettresuggestion } from "../../lib/api";

const MIN_LENGTH = 10;
const MAX_LENGTH = 2000;

// ─── Success state ────────────────────────────────────────────────────────────

function SuccessView({ onReset }: { onReset: () => void }) {
  const navigate = useNavigate();

  return (
    <div role="status" className="flex flex-col items-center text-center gap-8 py-4 animate-in fade-in slide-in-from-bottom-3 duration-500">
      <div className="relative flex items-center justify-center w-24 h-24">
        <div className="absolute inset-0 rounded-full border border-emerald-100 dark:border-emerald-500/15 scale-[1.55] opacity-50" />
        <div className="absolute inset-0 rounded-full border border-emerald-200/70 dark:border-emerald-500/20 scale-[1.28] opacity-70" />
        <div className="w-24 h-24 rounded-full bg-emerald-50 dark:bg-emerald-500/10 flex items-center justify-center">
          <CheckCircle2
            size={40}
            strokeWidth={1.5}
            className="text-emerald-500 dark:text-emerald-400"
            aria-hidden="true"
          />
        </div>
      </div>

      <div className="space-y-2.5 max-w-xs">
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
          Merci pour votre retour&nbsp;!
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
          Votre suggestion a bien été transmise. Nous lisons chaque retour avec
          attention et agissons en conséquence.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row items-center gap-3 pt-1">
        <button
          onClick={onReset}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-5 min-h-[44px] transition-colors"
        >
          Faire une autre suggestion
        </button>
        <button
          onClick={() => navigate("/mon-espace")}
          className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors px-4 min-h-[44px]"
        >
          Retour à l'accueil
        </button>
      </div>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SuggestionBox() {
  const [contenu, setContenu] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();

  const submit = useMutation({
    mutationFn: () => soumettresuggestion(contenu.trim()),
  });

  function handleChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setContenu(e.target.value);
    const ta = e.currentTarget;
    requestAnimationFrame(() => {
      ta.style.height = "auto";
      ta.style.height = `${ta.scrollHeight}px`;
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) {
      e.preventDefault();
      submit.mutate();
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (contenu.trim().length >= MIN_LENGTH && !submit.isPending) {
      submit.mutate();
    }
  }

  function handleReset() {
    setContenu("");
    submit.reset();
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  const trimmedLength = contenu.trim().length;
  const remaining = MAX_LENGTH - contenu.length;
  const meetsMin = trimmedLength >= MIN_LENGTH;
  const canSubmit = meetsMin && !submit.isPending;

  return (
    <div className="px-4 py-12 sm:py-16">
      <div className="max-w-xl mx-auto space-y-8">

        {/* ── Hero ──────────────────────────────────────────────────────── */}
        <div className="text-center space-y-3">
          <h1 className="text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
            Aidez-nous à améliorer la plateforme
          </h1>
          <p className="text-sm sm:text-base text-gray-500 dark:text-gray-400 leading-relaxed max-w-md mx-auto">
            Une idée de fonctionnalité, un bug ou un ajustement ergonomique ?
            <br className="hidden sm:block" />
            Dites-nous tout, nous lisons chaque retour.
          </p>
        </div>

        {/* ── Card ──────────────────────────────────────────────────────── */}
        <div className="glass-card rounded-2xl p-6 sm:p-8">
          {submit.isSuccess ? (
            <SuccessView onReset={handleReset} />
          ) : (
            <form onSubmit={handleSubmit} noValidate className="space-y-5">

              {/* Textarea block */}
              <div className="space-y-2">
                <label
                  htmlFor="contenu"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Votre message
                  <span aria-hidden="true" className="text-red-500 ml-0.5">*</span>
                  <span className="sr-only"> (obligatoire)</span>
                </label>

                <textarea
                  ref={textareaRef}
                  id="contenu"
                  value={contenu}
                  onChange={handleChange}
                  onKeyDown={handleKeyDown}
                  disabled={submit.isPending}
                  required
                  aria-required="true"
                  aria-invalid={submit.isError || undefined}
                  maxLength={MAX_LENGTH}
                  placeholder="Décrivez ce qui pourrait être amélioré sur le site…"
                  className="w-full text-sm border border-gray-200 dark:border-white/15 rounded-xl px-4 py-3 text-gray-900 dark:text-gray-100 bg-white dark:bg-white/[0.06] placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 resize-none overflow-hidden disabled:opacity-50 disabled:cursor-not-allowed transition-shadow"
                  style={{ minHeight: "140px" }}
                  aria-describedby="suggestion-counter suggestion-error"
                />

                {/* Min-length signal + character counter */}
                <div className="flex items-center justify-between gap-4">
                  <p
                    id="suggestion-min"
                    className={`text-xs transition-colors duration-150 ${
                      meetsMin
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {meetsMin ? "✓ Prêt à envoyer" : `${MIN_LENGTH} caractères minimum`}
                  </p>
                  <p
                    id="suggestion-counter"
                    aria-live="polite"
                    className={`text-xs tabular-nums shrink-0 ${
                      remaining < 100
                        ? "text-amber-600 dark:text-amber-400"
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {contenu.length} / {MAX_LENGTH}
                  </p>
                </div>
              </div>

              {/* Submit block — error banner sits just above the button */}
              <div className="space-y-2">
                {/* ARIA anchor always in DOM; visible error rendered separately below */}
                <span
                  id="suggestion-error"
                  role="alert"
                  aria-live="assertive"
                  className="sr-only"
                >
                  {submit.isError &&
                    "Une erreur est survenue, veuillez réessayer. Si le problème persiste, contactez le support IT."}
                </span>

                {submit.isError && (
                  <p
                    aria-hidden="true"
                    className="flex items-start gap-1.5 text-xs text-red-600 dark:text-red-400"
                  >
                    <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
                    <span>
                      Une erreur est survenue, veuillez réessayer.{" "}
                      <span className="opacity-80">
                        Si le problème persiste, contactez le support IT.
                      </span>
                    </span>
                  </p>
                )}

                <button
                  type="submit"
                  disabled={!canSubmit}
                  aria-describedby={!meetsMin && !submit.isPending ? "suggestion-min" : undefined}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold px-5 min-h-[44px] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {submit.isPending ? (
                    <>
                      <Loader2 size={15} className="animate-spin" aria-hidden="true" />
                      Envoi en cours…
                    </>
                  ) : (
                    <>
                      <SendHorizontal size={15} strokeWidth={2.2} aria-hidden="true" />
                      Envoyer ma suggestion
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* ── Ghost back link — formulaire uniquement ───────────────────── */}
        {!submit.isSuccess && (
          <div className="text-center">
            <button
              onClick={() => navigate("/mon-espace")}
              className="text-sm text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            >
              Retour à l'accueil
            </button>
          </div>
        )}

      </div>
    </div>
  );
}
