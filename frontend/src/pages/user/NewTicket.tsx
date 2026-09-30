import { useRef } from "react";
import { Link } from "react-router-dom";
import {
  Send, Loader2, CheckCircle2, AlertCircle, Plus, ArrowRight, ChevronDown,
} from "lucide-react";
import {
  useNewTicket, isMac, isTouchDevice, isValidationError, getErrorMessage,
} from "../../hooks/useNewTicket";

export default function NewTicket() {
  const objetRef = useRef<HTMLInputElement>(null);
  const tk = useNewTicket();

  function reset() {
    tk.resetState();
    setTimeout(() => objetRef.current?.focus(), 0);
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Besoin d'un renseignement ?</h1>
        <p className="text-sm text-gray-600 dark:text-muted-foreground mt-1">Décrivez votre demande, un expert vous répondra.</p>
        <p className="text-sm text-muted-foreground mt-2">
          Votre question a peut-être déjà une réponse —{" "}
          <Link
            to="/faq"
            className="font-medium text-emerald-700 dark:text-emerald-400 hover:underline underline-offset-2"
          >
            consulter les questions fréquentes
          </Link>
        </p>
      </div>

      {tk.submitted ? (
        <div role="status" className="glass-card rounded-2xl p-6 flex flex-col items-center text-center gap-3">
          <span className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">
            <CheckCircle2 size={26} aria-hidden="true" />
          </span>
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Votre question a bien été soumise</h2>
          <p className="text-sm text-muted-foreground max-w-md">
            Elle est en cours d'analyse. Vous recevrez une réponse dans votre espace personnel, généralement sous 24 heures ouvrées.
          </p>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={reset}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary hover:bg-primary-hover text-primary-foreground text-sm font-medium px-4 py-3 transition-colors"
            >
              <Plus size={14} aria-hidden="true" />
              Poser une autre question
            </button>
            <Link
              to="/mon-espace"
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 dark:border-white/10 text-gray-600 dark:text-muted-foreground hover:bg-gray-50 dark:hover:bg-white/5 text-sm font-medium px-4 py-3 transition-colors"
            >
              Mes questions
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={tk.handleSubmit} className="glass-card rounded-2xl p-6 space-y-5">
          {/* Objet */}
          <div className="space-y-1.5">
            <label htmlFor="objet" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Objet</label>
            <input
              ref={objetRef}
              id="objet"
              type="text"
              value={tk.objet}
              onChange={(e) => { tk.setObjet(e.target.value); if (tk.submit.isError) tk.submit.reset(); }}
              maxLength={255}
              required
              autoFocus
              aria-invalid={tk.fieldInvalid}
              placeholder="Ex. : Report de congés"
              className={`w-full text-sm border ${tk.fieldBorder} rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500`}
            />
            {tk.objet.length > 200 && (
              <p aria-live="polite" className={`text-[11px] text-right tabular-nums ${tk.objet.length >= 240 ? "text-red-600 dark:text-red-400" : "text-amber-700 dark:text-amber-400"}`}>
                {tk.objet.length} / 255
              </p>
            )}
          </div>

          {/* Question */}
          <div className="space-y-1.5">
            <label htmlFor="question" className="block text-sm font-medium text-gray-700 dark:text-gray-200">Votre question</label>
            <textarea
              id="question"
              value={tk.question}
              onChange={(e) => { tk.setQuestion(e.target.value); if (tk.submit.isError) tk.submit.reset(); }}
              onKeyDown={tk.handleTextareaKeyDown}
              rows={5}
              required
              maxLength={2000}
              aria-invalid={tk.fieldInvalid}
              placeholder="Ex. : Combien de jours de congés puis-je reporter sur l'année suivante ?"
              className={`w-full text-sm border ${tk.fieldBorder} rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 resize-y`}
            />
            {tk.question.length > 1800 ? (
              <p aria-live="polite" className={`text-[11px] text-right tabular-nums ${tk.question.length >= 2000 ? "text-red-600 dark:text-red-400" : "text-amber-700 dark:text-amber-400"}`}>
                {tk.question.length} / 2000
              </p>
            ) : tk.question.length > 0 && tk.question.trim().length < 10 ? (
              <p aria-live="polite" className="text-[11px] text-amber-700 dark:text-amber-400">
                Décrivez votre situation en quelques mots pour obtenir une réponse précise.
              </p>
            ) : !isTouchDevice ? (
              <p className="text-[11px] text-muted-foreground">
                {isMac ? "⌘+Entrée pour envoyer" : "Ctrl+Entrée pour envoyer"}
              </p>
            ) : null}
          </div>

          {/* Domaine */}
          <div className="space-y-1.5">
            <label
              htmlFor={tk.domaines.length !== 1 ? "domaine" : undefined}
              className="block text-sm font-medium text-gray-700 dark:text-gray-200"
            >
              Domaine
            </label>
            {tk.domainesError ? (
              <p className="text-sm text-red-600 dark:text-red-400">Impossible de charger les domaines. Rechargez la page.</p>
            ) : tk.domaines.length === 1 ? (
              <p className="text-sm text-gray-700 dark:text-gray-200 px-3 py-2">{tk.domaines[0]}</p>
            ) : (
              <div className="relative">
                <select
                  id="domaine"
                  value={tk.domaine}
                  onChange={(e) => { tk.setDomaine(e.target.value as typeof tk.domaine); if (tk.submit.isError) tk.submit.reset(); }}
                  disabled={tk.domainesLoading}
                  aria-invalid={tk.fieldInvalid}
                  className={`w-full appearance-none text-sm border ${tk.fieldBorder} rounded-lg px-3 py-2 pr-8 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:opacity-50`}
                >
                  {tk.domainesLoading
                    ? <option value="">Chargement…</option>
                    : tk.domaines.map((d) => <option key={d} value={d}>{d}</option>)
                  }
                </select>
                <ChevronDown size={14} aria-hidden="true" className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle" />
              </div>
            )}
            {!tk.domainesError && (
              <p className="text-[11px] text-muted-foreground">Ce choix détermine quel service traitera votre demande.</p>
            )}
          </div>

          {/* Error */}
          {tk.submit.isError && (
            <div role="alert" className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 px-3 py-2.5 text-sm text-red-600 dark:text-red-400">
              <AlertCircle size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
              <span className="flex-1">{getErrorMessage(tk.submit.error)}</span>
              {!isValidationError(tk.submit.error) && (
                <button type="button" onClick={() => tk.submit.mutate()} aria-label="Réessayer l'envoi de la question" className="shrink-0 text-xs font-medium underline underline-offset-2 hover:no-underline">
                  Réessayer
                </button>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={!tk.canSubmit}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary hover:bg-primary-hover text-primary-foreground text-sm font-medium px-4 py-3 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {tk.submit.isPending
              ? <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              : <Send size={14} aria-hidden="true" />
            }
            Envoyer la question
          </button>
        </form>
      )}
    </div>
  );
}
