import type { UseMutationResult } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  EyeOff,
  Loader2,
  Pencil,
  X,
} from "lucide-react";
import type { ReponseSignalee } from "../../../types";
import ExpandableText from "./ExpandableText";
import InfoTooltip from "./InfoTooltip";
import MotifSignalement from "./MotifSignalement";
import { contenuServi, EN_ANALYSE } from "./utils";

interface ReponseItemProps {
  r: ReponseSignalee;
  filename: string | null;
  version: number | null;
  editingId: string | null;
  draft: string;
  isPendingEdit: boolean;
  confirmMutation: UseMutationResult<void, Error, string>;
  confirmingId: string | null;
  setConfirmingId: React.Dispatch<React.SetStateAction<string | null>>;
  confirmErrors: Set<string>;
  setConfirmErrors: React.Dispatch<React.SetStateAction<Set<string>>>;
  onEdit: (r: ReponseSignalee) => void;
  onSave: (id: string) => void;
  onCancel: () => void;
  onDraftChange: (v: string) => void;
  onRetrait: (r: ReponseSignalee) => void;
}

export function ReponseItemARelire({
  r, filename, version,
  editingId, draft, isPendingEdit,
  confirmMutation, confirmingId, setConfirmingId, confirmErrors, setConfirmErrors,
  onEdit, onSave, onCancel, onDraftChange, onRetrait,
}: ReponseItemProps) {
  const isEditing = editingId === r.reponse_id;
  const enAnalyse = r.a_relire_raison === EN_ANALYSE;
  const isConfirmError = confirmErrors.has(r.reponse_id);

  return (
    <li className={`rounded-xl border px-4 py-3 space-y-2 transition-colors ${
      enAnalyse
        ? "border-gray-200/70 dark:border-white/8 bg-gray-50/50 dark:bg-white/[0.02]"
        : "border-gray-200/70 dark:border-white/8 hover:border-gray-200 dark:hover:border-white/12"
    }`}>
      {/* Question + badges */}
      <div className="flex items-start gap-2">
        <p className={`flex-1 min-w-0 text-sm font-semibold leading-snug ${
          enAnalyse ? "text-gray-500 dark:text-gray-400" : "text-gray-900 dark:text-gray-50"
        }`}>
          {r.question}
        </p>
        <div className="flex items-center gap-1.5 shrink-0 pt-px">
          {r.canonique && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
              canonique
              <InfoTooltip content="Servie directement sans relecture humaine — vérifiez bien avant de confirmer" />
            </span>
          )}
          <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
            {r.nb_validations} validation{r.nb_validations > 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Content */}
      {isEditing ? (
        <div className="space-y-2">
          {filename && (
            <p className="text-xs text-amber-700/70 dark:text-amber-300/60">
              Document : <span className="font-medium">{filename}</span>
              {version !== null && <span className="ml-1 opacity-70">v{version}</span>}
            </p>
          )}
          <details className="group/orig rounded-lg border border-gray-200/70 dark:border-white/8 bg-gray-50/50 dark:bg-white/[0.02]">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 select-none list-none flex items-center gap-1 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
              <span className="text-gray-300 dark:text-gray-600 group-open/orig:rotate-90 transition-transform inline-block">▶</span>
              Texte actuel (référence)
            </summary>
            <p className="px-3 pb-3 text-xs text-gray-600 dark:text-gray-400 leading-relaxed whitespace-pre-wrap">
              {contenuServi(r)}
            </p>
          </details>
          <textarea
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            rows={6}
            autoFocus
            aria-label="Modifier le contenu de la réponse"
            className="w-full rounded-xl border border-gray-200 dark:border-white/15 bg-white dark:bg-white/5 px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 leading-relaxed resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          />
        </div>
      ) : (
        <ExpandableText text={contenuServi(r)} label={r.question} />
      )}

      <MotifSignalement reponse={r} />

      {isConfirmError && !isEditing && (
        <p role="alert" className="text-xs text-red-500 dark:text-red-400">
          Erreur — signalement non levé. Réessayez.
        </p>
      )}

      {/* Actions */}
      {enAnalyse ? (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
          <Loader2 size={12} className="animate-spin shrink-0" aria-hidden="true" />
          Analyse IA en cours — résultat dans quelques minutes
        </div>
      ) : (
        <div className="flex items-center justify-end gap-1.5">
          {isEditing ? (
            <>
              <button
                onClick={() => onSave(r.reponse_id)}
                disabled={!draft.trim() || isPendingEdit}
                aria-label={`Enregistrer les modifications — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                <Check size={12} aria-hidden="true" />
                Enregistrer
              </button>
              <button
                onClick={onCancel}
                aria-label={`Annuler les modifications — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 text-xs font-medium hover:bg-gray-50 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
              >
                <X size={12} aria-hidden="true" />
                Annuler
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setConfirmErrors((prev) => { const n = new Set(prev); n.delete(r.reponse_id); return n; });
                  setConfirmingId(r.reponse_id);
                  confirmMutation.mutate(r.reponse_id);
                }}
                disabled={confirmMutation.isPending}
                aria-label={`Toujours d'actualité — ${r.question}`}
                title="Lever le signalement — confirmer que cette réponse reste valide malgré la mise à jour du document"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
              >
                {confirmMutation.isPending && confirmingId === r.reponse_id
                  ? <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                  : <CheckCircle2 size={12} aria-hidden="true" />}
                Toujours d'actualité
              </button>
              <button
                onClick={() => onEdit(r)}
                aria-label={`Modifier — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-gray-200 dark:border-white/12 text-gray-500 dark:text-gray-400 text-xs font-medium hover:text-gray-700 hover:bg-gray-50 dark:hover:text-gray-200 dark:hover:bg-white/8 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400/60"
              >
                <Pencil size={12} aria-hidden="true" />
                Modifier
              </button>
              <button
                onClick={() => onRetrait(r)}
                aria-label={`Retirer du service — ${r.question}`}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-amber-200 dark:border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs font-medium hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
              >
                <EyeOff size={12} aria-hidden="true" />
                Retirer
              </button>
            </>
          )}
        </div>
      )}
    </li>
  );
}
