import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Send,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Plus,
  ArrowRight,
  ChevronDown,
} from "lucide-react";
import { apiFetch, soumettreQuestion } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import type { Domaine } from "../../types";

async function fetchDomaines(): Promise<string[]> {
  const res = await apiFetch("/api/v1/tickets/domaines");
  return res.json();
}

const isMac =
  typeof navigator !== "undefined" && /Macintosh|Mac OS X/.test(navigator.userAgent);
const isTouchDevice =
  typeof navigator !== "undefined" && navigator.maxTouchPoints > 0;

// extractApiErrorDetail returns the fallback string for 422 FastAPI validation
// errors (detail is an array, not a string), so we match on that known fallback.
function isValidationError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message;
  return (
    msg.includes("422") ||
    msg.includes("Unprocessable") ||
    msg === "Erreur lors de la soumission de la question"
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const msg = error.message;
    if (isValidationError(error)) {
      return "Votre question est incomplète. Vérifiez les champs et réessayez.";
    }
    if (msg.includes("401") || msg.includes("403")) {
      return "Votre session a expiré. Rechargez la page et reconnectez-vous.";
    }
    if (msg.includes("500") || msg.includes("502") || msg.includes("503")) {
      return "Une erreur est survenue de notre côté. Réessayez dans quelques instants.";
    }
  }
  return "Votre question n'a pas pu être envoyée. Réessayez ou contactez votre administrateur.";
}

export default function NewTicket() {
  const queryClient = useQueryClient();
  const [objet, setObjet] = useState("");
  const [question, setQuestion] = useState("");
  const [domaine, setDomaine] = useState<Domaine>("");
  const objetRef = useRef<HTMLInputElement>(null);

  const {
    data: domaines = [],
    isLoading: domainesLoading,
    isError: domainesError,
  } = useQuery({
    queryKey: ["admin", "domaines"],
    queryFn: fetchDomaines,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (domaines.length > 0 && !domaine) setDomaine(domaines[0] as Domaine);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domaines]); // Intentional: set default only when list first loads

  const submit = useMutation({
    mutationFn: () =>
      soumettreQuestion({
        question: question.trim(),
        objet: objet.trim(),
        domaine,
        user_id: getValidatorId(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
    },
  });

  const submitted = submit.isSuccess;
  const isDirty = (objet.length > 0 || question.length > 0) && !submitted;

  const canSubmit =
    objet.trim().length > 0 &&
    question.trim().length >= 10 &&
    domaine.length > 0 &&
    !submit.isPending &&
    !domainesLoading;

  // Guard browser close/refresh when the form has content
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  function reset() {
    setObjet("");
    setQuestion("");
    setDomaine(domaines[0] ?? "");
    submit.reset();
    setTimeout(() => objetRef.current?.focus(), 0);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) submit.mutate();
  }

  function handleTextareaKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canSubmit) {
      e.preventDefault();
      submit.mutate();
    }
  }

  const fieldError = submit.isError && isValidationError(submit.error);
  const fieldBorder = fieldError
    ? "border-red-300 dark:border-red-500/50"
    : "border-gray-200 dark:border-white/10";
  // aria-invalid signals the erroneous state to screen readers
  const fieldInvalid: true | undefined = fieldError ? true : undefined;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Besoin d'un renseignement ?
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Décrivez votre demande — un expert de votre domaine vous répondra.
        </p>
      </div>

      {submitted ? (
        /* Confirmation d'envoi */
        <div
          role="status"
          className="glass-card rounded-2xl p-6 flex flex-col items-center text-center gap-3"
        >
          <span className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400">
            <CheckCircle2 size={26} aria-hidden="true" />
          </span>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            Votre question a bien été soumise
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
            Elle est en cours d'analyse. Vous recevrez une réponse dans votre
            espace personnel, généralement sous 24 heures ouvrées.
          </p>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-3 transition-colors"
            >
              <Plus size={14} aria-hidden="true" />
              Poser une autre question
            </button>
            <Link
              to="/mon-espace"
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-white/5 text-sm font-medium px-4 py-3 transition-colors"
            >
              Mes questions
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </div>
      ) : (
        /* Formulaire — ordre : Objet → Question → Domaine */
        <form
          onSubmit={handleSubmit}
          className="glass-card rounded-2xl p-6 space-y-5"
        >
          {/* Objet */}
          <div className="space-y-1.5">
            <label
              htmlFor="objet"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Objet
            </label>
            <input
              ref={objetRef}
              id="objet"
              type="text"
              value={objet}
              onChange={(e) => {
                setObjet(e.target.value);
                if (submit.isError) submit.reset();
              }}
              maxLength={255}
              required
              autoFocus
              aria-invalid={fieldInvalid}
              placeholder="Ex. : Report de congés"
              className={`w-full text-sm border ${fieldBorder} rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-gray-500 dark:placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500`}
            />
            {objet.length > 200 && (
              <p
                aria-live="polite"
                className={`text-[11px] text-right tabular-nums ${
                  objet.length >= 240 ? "text-red-500" : "text-amber-500"
                }`}
              >
                {objet.length} / 255
              </p>
            )}
          </div>

          {/* Question */}
          <div className="space-y-1.5">
            <label
              htmlFor="question"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Votre question
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(e) => {
                setQuestion(e.target.value);
                if (submit.isError) submit.reset();
              }}
              onKeyDown={handleTextareaKeyDown}
              rows={5}
              required
              maxLength={2000}
              aria-invalid={fieldInvalid}
              placeholder="Ex. : Combien de jours de congés puis-je reporter sur l'année suivante ?"
              className={`w-full text-sm border ${fieldBorder} rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-gray-500 dark:placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 resize-y`}
            />
            {question.length > 1800 ? (
              <p
                aria-live="polite"
                className={`text-[11px] text-right tabular-nums ${
                  question.length >= 2000 ? "text-red-500" : "text-amber-500"
                }`}
              >
                {question.length} / 2000
              </p>
            ) : question.length > 0 && question.trim().length < 10 ? (
              <p aria-live="polite" className="text-[11px] text-amber-500">
                Décrivez votre situation en quelques mots pour obtenir une réponse précise.
              </p>
            ) : !isTouchDevice ? (
              <p className="text-[11px] text-gray-400 dark:text-gray-500">
                {isMac ? "⌘+Entrée pour envoyer" : "Ctrl+Entrée pour envoyer"}
              </p>
            ) : null}
          </div>

          {/* Domaine */}
          <div className="space-y-1.5">
            <label
              htmlFor={domaines.length !== 1 ? "domaine" : undefined}
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Domaine
            </label>
            {domainesError ? (
              <p className="text-sm text-red-600 dark:text-red-400">
                Impossible de charger les domaines. Rechargez la page.
              </p>
            ) : domaines.length === 1 ? (
              <p className="text-sm text-gray-700 dark:text-gray-200 px-3 py-2">
                {domaines[0]}
              </p>
            ) : (
              <div className="relative">
                <select
                  id="domaine"
                  value={domaine}
                  onChange={(e) => {
                    setDomaine(e.target.value as Domaine);
                    if (submit.isError) submit.reset();
                  }}
                  disabled={domainesLoading}
                  aria-invalid={fieldInvalid}
                  className={`w-full appearance-none text-sm border ${fieldBorder} rounded-lg px-3 py-2 pr-8 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50`}
                >
                  {domainesLoading ? (
                    <option value="">Chargement…</option>
                  ) : (
                    domaines.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))
                  )}
                </select>
                <ChevronDown
                  size={14}
                  aria-hidden="true"
                  className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500"
                />
              </div>
            )}
            {!domainesError && (
              <p className="text-[11px] text-gray-400 dark:text-gray-500">
                Ce choix détermine quel service traitera votre demande.
              </p>
            )}
          </div>

          {submit.isError && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-3 py-2.5 text-sm text-red-600 dark:text-red-400"
            >
              <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
              <span className="flex-1">{getErrorMessage(submit.error)}</span>
              {!isValidationError(submit.error) && (
                <button
                  type="button"
                  onClick={() => submit.mutate()}
                  aria-label="Réessayer l'envoi de la question"
                  className="shrink-0 text-xs font-medium underline underline-offset-2 hover:no-underline"
                >
                  Réessayer
                </button>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-4 py-3 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submit.isPending ? (
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
            ) : (
              <Send size={14} aria-hidden="true" />
            )}
            Envoyer la question
          </button>
        </form>
      )}
    </div>
  );
}
