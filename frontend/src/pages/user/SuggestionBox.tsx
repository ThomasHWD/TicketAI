import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send, Loader2, CheckCircle2, AlertCircle, Lightbulb } from "lucide-react";
import { soumettresuggestion } from "../../lib/api";

export default function SuggestionBox() {
  const [contenu, setContenu] = useState("");

  const submit = useMutation({
    mutationFn: () => soumettresuggestion(contenu.trim()),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (contenu.trim().length >= 10) submit.mutate();
  }

  if (submit.isSuccess) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="glass-card rounded-2xl p-10 flex flex-col items-center text-center gap-4">
          <span className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500 dark:text-emerald-400">
            <CheckCircle2 size={30} />
          </span>
          <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">
            Merci pour votre retour !
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm">
            Votre suggestion a bien été transmise à l'équipe. Elle sera étudiée dans les meilleurs délais.
          </p>
          <button
            onClick={() => { setContenu(""); submit.reset(); }}
            className="mt-1 text-sm text-emerald-600 dark:text-emerald-400 hover:underline"
          >
            Envoyer une autre suggestion
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-5">
      {/* Header */}
      <div className="glass-card rounded-2xl px-6 py-5 flex items-start gap-3.5">
        <span className="mt-0.5 flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-xl bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
          <Lightbulb size={16} />
        </span>
        <div>
          <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
            Suggérer une amélioration
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Le site est en phase de test — vos retours sont précieux.
          </p>
        </div>
      </div>

      {/* Formulaire */}
      <form onSubmit={handleSubmit} className="glass-card rounded-2xl p-6 space-y-4">
        <div className="space-y-1.5">
          <label
            htmlFor="contenu"
            className="block text-sm font-medium text-gray-700 dark:text-gray-200"
          >
            Votre suggestion
          </label>
          <textarea
            id="contenu"
            value={contenu}
            onChange={(e) => setContenu(e.target.value)}
            rows={6}
            maxLength={2000}
            placeholder="Ex. : Il serait utile de pouvoir filtrer les tickets par date..."
            className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2.5 text-gray-900 dark:text-gray-200 bg-white/80 dark:bg-white/5 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y"
          />
          <p className="text-xs text-gray-400 dark:text-gray-500 text-right">
            {contenu.length} / 2000
          </p>
        </div>

        {submit.isError && (
          <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <AlertCircle size={15} />
            Une erreur est survenue, veuillez réessayer.
          </div>
        )}

        <button
          type="submit"
          disabled={contenu.trim().length < 10 || submit.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submit.isPending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          Envoyer
        </button>
      </form>
    </div>
  );
}
