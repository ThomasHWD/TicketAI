import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import Modal from "../../../components/ui/Modal";
import type { IndexedDocument } from "../../../types";

export default function DeleteConfirm({
  doc,
  onConfirm,
  onCancel,
  isPending,
  erreur,
}: {
  doc: IndexedDocument;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
  erreur: string | null;
}) {
  return (
    <Modal
      title="Supprimer ce document ?"
      onClose={onCancel}
      widthClass="max-w-md"
      footer={
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700 disabled:opacity-50"
          >
            {isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            Supprimer définitivement
          </button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50/60 px-4 py-3 dark:border-red-500/25 dark:bg-red-500/10">
          <AlertTriangle
            size={16}
            className="mt-0.5 shrink-0 text-red-600 dark:text-red-400"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
              {doc.filename ?? doc.doc_id}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-red-700 dark:text-red-300">
              Ses {doc.nb_chunks} passage{doc.nb_chunks > 1 ? "s" : ""} seront retirés de l'index, et
              le fichier ainsi que ses {doc.nb_versions} version
              {doc.nb_versions > 1 ? "s" : ""} archivée{doc.nb_versions > 1 ? "s" : ""} seront
              effacés. Cette action est irréversible.
            </p>
          </div>
        </div>

        <p className="text-xs leading-relaxed text-muted-foreground">
          Les réponses validées construites avec ce document sont retirées du service. Celles que
          leurs autres sources suffisent à justifier y sont remises automatiquement après
          vérification ; les autres restent restaurables depuis l'onglet Obsolètes des réponses
          enregistrées.
        </p>

        {erreur && (
          <p className="rounded-lg border border-red-200 bg-red-50/70 px-3 py-2 text-xs text-red-700 dark:border-red-500/25 dark:bg-red-500/10 dark:text-red-300">
            {erreur}
          </p>
        )}
      </div>
    </Modal>
  );
}
