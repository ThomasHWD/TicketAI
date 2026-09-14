import type { RefObject } from "react";
import { Check, Pencil, Tag, ThumbsDown, ThumbsUp, X } from "lucide-react";
import type { TicketReponse } from "../../types";

interface EditingPanelProps {
  draft: string;
  loading: boolean;
  error: string | null;
  errorId: string;
  isHorsDomaine: boolean;
  reponseDate: string;
  onDraftChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function EditingPanel({
  draft, loading, error, errorId, isHorsDomaine, reponseDate,
  onDraftChange, onSubmit, onCancel,
}: EditingPanelProps) {
  return (
    <div className="space-y-3">
      <textarea
        className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y leading-relaxed min-h-[200px] sm:min-h-[420px] transition-shadow"
        rows={18}
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        disabled={loading}
        autoFocus
        placeholder={isHorsDomaine ? "Aucun document ne couvre ce sujet. Rédigez une réponse à partir de vos connaissances…" : undefined}
        aria-label="Contenu corrigé"
        aria-describedby={error ? errorId : undefined}
      />
      {isHorsDomaine && draft && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">Brouillon sauvegardé localement.</p>
      )}
      {error && (
        <p id={errorId} className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>
      )}
      <div className="flex items-center gap-2">
        <button
          onClick={onSubmit}
          disabled={loading || !draft.trim()}
          aria-label={`Valider la correction de la réponse du ${reponseDate}`}
          title="Soumettre la version corrigée — elle sera envoyée à l'employé"
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
        >
          <Check size={14} aria-hidden="true" />
          Valider la correction
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
        >
          <X size={14} aria-hidden="true" />
          Annuler
        </button>
      </div>
    </div>
  );
}

interface ValidationConfirmPanelProps {
  confirmRef: RefObject<HTMLButtonElement | null>;
  loading: boolean;
  error: string | null;
  tagDraft: string;
  tags: string[];
  faqVisible: boolean;
  onTagChange: (v: string) => void;
  onFaqVisibleChange: (v: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ValidationConfirmPanel({
  confirmRef, loading, error, tagDraft, tags, faqVisible, onTagChange, onFaqVisibleChange, onConfirm, onCancel,
}: ValidationConfirmPanelProps) {
  return (
    <div role="alert" className="p-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 space-y-3">
      <p className="text-xs font-medium text-amber-700 dark:text-amber-300">
        Confirmer la validation de cette réponse générée par l'IA ?
      </p>

      <div className="space-y-1">
        <label htmlFor="tag-validation-input" className="flex items-center gap-1 text-xs text-amber-700/70 dark:text-amber-400/70">
          <Tag size={10} aria-hidden="true" />
          Catégorie <span className="text-amber-600/50 dark:text-amber-500/50">(optionnel)</span>
        </label>
        <input
          id="tag-validation-input"
          list="tag-validation-list"
          value={tagDraft}
          onChange={(e) => onTagChange(e.target.value)}
          placeholder="Ex : congés, télétravail, paie…"
          maxLength={100}
          disabled={loading}
          className="w-full px-2.5 py-1.5 text-xs rounded-md border border-amber-200 dark:border-amber-500/30 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60 disabled:opacity-50 transition-colors"
        />
        <datalist id="tag-validation-list">
          {tags.map((t) => <option key={t} value={t} />)}
        </datalist>
      </div>

      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={faqVisible}
          onChange={(e) => onFaqVisibleChange(e.target.checked)}
          disabled={loading}
          className="w-3.5 h-3.5 rounded border-amber-300 dark:border-amber-500/40 accent-emerald-600 disabled:opacity-50"
        />
        <span className="text-xs text-amber-700/80 dark:text-amber-400/80">Inclure dans la FAQ</span>
      </label>

      {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          ref={confirmRef}
          onClick={onConfirm}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
        >
          <ThumbsUp size={14} aria-hidden="true" />
          Oui, valider
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-amber-200 dark:border-amber-500/30 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors"
        >
          <X size={14} aria-hidden="true" />
          Annuler
        </button>
      </div>
    </div>
  );
}

interface RejectionPanelProps {
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  loading: boolean;
  error: string | null;
  rejectRaison: string;
  onReasonChange: (v: string) => void;
  onReject: () => void;
  onCancel: () => void;
}

export function RejectionPanel({ textareaRef, loading, error, rejectRaison, onReasonChange, onReject, onCancel }: RejectionPanelProps) {
  return (
    <div role="alert" className="p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 space-y-2.5">
      <p className="text-xs font-medium text-red-700 dark:text-red-300">Confirmer le rejet de cette réponse ?</p>
      <textarea
        ref={textareaRef}
        value={rejectRaison}
        onChange={(e) => onReasonChange(e.target.value)}
        placeholder="Raison du rejet (obligatoire)"
        rows={2}
        disabled={loading}
        className="w-full text-sm text-gray-700 dark:text-gray-100 bg-white dark:bg-white/5 border border-red-200 dark:border-red-500/30 rounded-md p-2 focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
        aria-label="Raison du rejet"
      />
      {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={onReject}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 font-medium transition-colors"
        >
          <ThumbsDown size={14} aria-hidden="true" />
          Oui, rejeter
        </button>
        <button
          onClick={onCancel}
          disabled={loading}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-500/20 transition-colors"
        >
          <X size={14} aria-hidden="true" />
          Annuler
        </button>
      </div>
    </div>
  );
}

interface ActionButtonsProps {
  isHorsDomaine: boolean;
  loading: boolean;
  reponseDate: string;
  error: string | null;
  onValider: () => void;
  onEdit: () => void;
  onReject: () => void;
  onDismissError: () => void;
}

export function ActionButtons({ isHorsDomaine, loading, reponseDate, error, onValider, onEdit, onReject, onDismissError }: ActionButtonsProps) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {!isHorsDomaine && (
        <span className="inline-flex items-center gap-1.5">
          <button
            onClick={onValider}
            disabled={loading}
            data-action="valider"
            aria-label={`Valider la réponse du ${reponseDate}`}
            title="Valider → envoie la réponse à l'employé et incrémente son score de validation (→ canonique à 3 validations)"
            className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-40 font-medium transition-colors"
          >
            <ThumbsUp size={14} aria-hidden="true" />
            Valider
          </button>
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <button
          onClick={onEdit}
          disabled={loading}
          data-action="corriger"
          aria-label={isHorsDomaine ? `Rédiger une réponse pour la demande du ${reponseDate}` : `Corriger la réponse du ${reponseDate}`}
          title={isHorsDomaine ? "Rédiger une réponse manuelle pour ce sujet non couvert" : "Modifier la réponse avant validation"}
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
        >
          <Pencil size={14} aria-hidden="true" />
          {isHorsDomaine ? "Rédiger une réponse" : "Corriger"}
        </button>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <button
          onClick={onReject}
          disabled={loading}
          data-action="rejeter"
          aria-label={`Rejeter la réponse du ${reponseDate}`}
          title="Rejeter cette réponse — elle ne sera pas envoyée à l'employé"
          className="flex items-center gap-1.5 text-sm px-4 py-2.5 rounded-md border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40 transition-colors"
        >
          <ThumbsDown size={14} aria-hidden="true" />
          Rejeter
        </button>
      </span>
      {error && (
        <p className="text-xs text-red-600 dark:text-red-400 w-full" role="alert">
          {error}{" "}
          <button onClick={onDismissError} className="underline hover:no-underline ml-1">Fermer</button>
        </p>
      )}
    </div>
  );
}

interface ContextualHelpProps {
  reponse: TicketReponse;
  isRag: boolean;
  nearCanonical: boolean;
}

export function ContextualHelp({ reponse, isRag, nearCanonical }: ContextualHelpProps) {
  return (
    <details className="group mt-0.5">
      <summary className="text-[11px] text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-600 dark:hover:text-gray-300 transition-colors list-none flex items-center gap-1 select-none">
        <span className="transition-transform group-open:rotate-90 inline-block text-[10px]" aria-hidden="true">▶</span>
        À propos de ces actions
      </summary>
      <div className="mt-2 p-3 rounded-xl bg-gray-50 dark:bg-white/[0.03] border border-gray-100 dark:border-white/[0.06] text-xs text-gray-600 dark:text-gray-300 space-y-1.5">
        <p><span className="font-medium">Valider</span> : approuve et envoie la réponse à l'employé. Chaque validation incrémente son score (seuil canonique : 3).</p>
        <p><span className="font-medium">Corriger</span> : modifie la réponse avant envoi. Le brouillon est préservé localement.</p>
        {reponse.source === "SUGGESTION" && (
          <p className="text-amber-600/80 dark:text-amber-400/80"><span className="font-medium">Suggestion</span> : réutilise une réponse validée. Assurez-vous qu'elle s'applique à ce cas précis.</p>
        )}
        {isRag && (
          <p className="text-amber-600/80 dark:text-amber-400/80"><span className="font-medium">Réponse IA</span> : générée à partir des documents internes — peut contenir des imprécisions.</p>
        )}
        {nearCanonical && (
          <p className="text-emerald-600 dark:text-emerald-400"><span className="font-medium">Promotion imminente</span> : cette réponse a {reponse.nb_validations} validation(s). La prochaine la rendra canonique.</p>
        )}
        <p><span className="font-medium">Rejeter</span> : refuse la réponse — elle ne sera pas envoyée. Un motif est obligatoire.</p>
        <p className="text-gray-500 dark:text-gray-400">
          Raccourcis :{" "}
          <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">V</kbd> Valider ·{" "}
          <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">E</kbd> Corriger ·{" "}
          <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">R</kbd> Rejeter ·{" "}
          <kbd className="font-mono px-0.5 py-px rounded border border-gray-200 dark:border-white/10">Alt+←</kbd> Retour
        </p>
      </div>
    </details>
  );
}
