import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, Loader2, CheckCircle2, AlertCircle, Plus } from "lucide-react";
import { soumettreQuestion } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import type { Domaine } from "../../types.ts";

const DOMAINES: { value: Domaine; label: string }[] = [
  { value: "IT", label: "Informatique" },
  { value: "RH", label: "Ressources humaines" },
  { value: "JURIDIQUE", label: "Juridique" },
];

export default function NewTicket() {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [domaine, setDomaine] = useState<Domaine>("IT");

  const submit = useMutation({
    mutationFn: () =>
      soumettreQuestion({
        question: question.trim(),
        domaine,
        user_id: getValidatorId(),
      }),
    onSuccess: () => {
      // L'historique de l'utilisateur doit refléter la nouvelle question.
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
    },
  });

  const submitted = submit.isSuccess;
  const canSubmit = question.trim().length > 0 && !submit.isPending;

  function reset() {
    setQuestion("");
    setDomaine("IT");
    submit.reset();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (canSubmit) submit.mutate();
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
          Besoin d'un renseignement ?
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Posez votre question — Nous y répondrons dans les plus brefs délais.
        </p>
      </div>

      {submitted ? (
        /* Confirmation d'envoi */
        <div className="bg-white/50 dark:bg-white/5 backdrop-blur-2xl rounded-2xl border border-white/60 dark:border-white/10 shadow-[0_2px_24px_0_rgba(0,0,0,0.08)] p-8 flex flex-col items-center text-center gap-3">
          <span className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400">
            <CheckCircle2 size={26} />
          </span>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
            Votre question a bien été soumise
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-md">
            Elle est en cours de traitement. Vous pourrez suivre son avancement
            et consulter la réponse depuis votre historique.
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors"
          >
            <Plus size={16} />
            Poser une autre question
          </button>
        </div>
      ) : (
        /* Formulaire */
        <form
          onSubmit={handleSubmit}
          className="bg-white/50 dark:bg-white/5 backdrop-blur-2xl rounded-2xl border border-white/60 dark:border-white/10 shadow-[0_2px_24px_0_rgba(0,0,0,0.08)] p-6 space-y-5"
        >
          <div className="space-y-1.5">
            <label
              htmlFor="domaine"
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Domaine
            </label>
            <select
              id="domaine"
              value={domaine}
              onChange={(e) => setDomaine(e.target.value as Domaine)}
              className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              {DOMAINES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

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
              onChange={(e) => setQuestion(e.target.value)}
              rows={5}
              placeholder="Ex. : Combien de jours de congés puis-je reporter sur l'année suivante ?"
              className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y"
            />
          </div>

          {submit.isError && (
            <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertCircle size={16} />
              {submit.error instanceof Error
                ? submit.error.message
                : "Une erreur est survenue"}
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submit.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
            Envoyer la question
          </button>
        </form>
      )}
    </div>
  );
}
