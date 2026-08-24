import { useState, useRef, useEffect } from "react";
import {
  Download,
  Eye,
  File,
  FileText,
  FileType,
  History,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { downloadDocument } from "../../../lib/api";
import DropdownMenu, { type MenuAction } from "../../../components/ui/DropdownMenu";
import type { IndexedDocument } from "../../../types";

export interface ActionsDocument {
  onVoir: (doc: IndexedDocument) => void;
  onHistorique: (doc: IndexedDocument) => void;
  onMettreAJour: (doc: IndexedDocument) => void;
  onSupprimer: (doc: IndexedDocument) => void;
}

const TH =
  "px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500";

function IconeFichier({ filename }: { filename: string | null }) {
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileType size={15} className="shrink-0 text-red-400" />;
  if (ext === "docx") return <FileText size={15} className="shrink-0 text-blue-400" />;
  return <File size={15} className="shrink-0 text-gray-400 dark:text-gray-500" />;
}

function dateCourte(iso: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}

function LigneDocument({
  doc,
  peutEcrire,
  actions,
  highlightDocId,
}: {
  doc: IndexedDocument;
  peutEcrire: boolean;
  actions: ActionsDocument;
  highlightDocId?: string;
}) {
  const [telechargement, setTelechargement] = useState(false);
  const [erreurTelechargement, setErreurTelechargement] = useState(false);
  const enMaj = doc.statut === "EN_MAJ";
  const rowRef = useRef<HTMLTableRowElement>(null);
  const isHighlighted = doc.doc_id === highlightDocId;

  useEffect(() => {
    if (isHighlighted && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isHighlighted]);

  async function telecharger() {
    setTelechargement(true);
    setErreurTelechargement(false);
    try {
      await downloadDocument(doc.doc_id, doc.filename);
    } catch {
      setErreurTelechargement(true);
    } finally {
      setTelechargement(false);
    }
  }

  const motifEnMaj = "Une mise à jour de ce document est déjà en cours.";
  const motifDroits = "Vous n'êtes pas membre du domaine de ce document.";

  const menu: MenuAction[] = [
    { label: "Voir le contenu indexé", icon: Eye, onSelect: () => actions.onVoir(doc) },
    { label: "Télécharger", icon: Download, onSelect: telecharger, disabled: telechargement },
    {
      label: `Historique (${doc.nb_versions} version${doc.nb_versions > 1 ? "s" : ""})`,
      icon: History,
      onSelect: () => actions.onHistorique(doc),
    },
    {
      label: "Mettre à jour",
      icon: RefreshCw,
      onSelect: () => actions.onMettreAJour(doc),
      disabled: !peutEcrire || enMaj,
      disabledReason: enMaj ? motifEnMaj : motifDroits,
    },
    {
      label: "Supprimer",
      icon: Trash2,
      onSelect: () => actions.onSupprimer(doc),
      disabled: !peutEcrire || enMaj,
      disabledReason: enMaj ? motifEnMaj : motifDroits,
      danger: true,
    },
  ];

  return (
    <tr
      ref={rowRef}
      className={`group transition-colors hover:bg-gray-50/70 dark:hover:bg-white/[0.025] ${isHighlighted ? "ring-1 ring-inset ring-emerald-400/60 bg-emerald-50/40 dark:bg-emerald-500/8" : ""}`}
    >
      <td className="px-5 py-3">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5">
            <IconeFichier filename={doc.filename} />
          </span>
          <div className="min-w-0">
            <button
              type="button"
              onClick={() => actions.onVoir(doc)}
              title={doc.filename ?? undefined}
              className="block max-w-md truncate text-left text-sm font-medium text-gray-900 hover:underline dark:text-gray-100"
            >
              {doc.filename ?? "—"}
            </button>
            <p className="mt-0.5 max-w-md truncate text-xs text-gray-400 dark:text-gray-500">
              {doc.description || <span className="italic">Aucune description</span>}
            </p>
            {erreurTelechargement && (
              <p className="mt-1 flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                Téléchargement impossible.{" "}
                <button
                  type="button"
                  onClick={telecharger}
                  className="underline underline-offset-2 hover:no-underline"
                >
                  Réessayer
                </button>
              </p>
            )}
          </div>
        </div>
      </td>

      <td className="whitespace-nowrap px-5 py-3">
        {doc.domaine && (
          <span className="inline-flex rounded-md bg-gray-100 px-1.5 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-white/8 dark:text-gray-400">
            {doc.domaine}
          </span>
        )}
      </td>

      <td className="whitespace-nowrap px-5 py-3">
        {enMaj ? (
          <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
            <Loader2 size={11} className="animate-spin" />
            Mise à jour…
          </span>
        ) : (
          <span className="text-xs tabular-nums text-gray-500 dark:text-gray-400">
            v{doc.version}
          </span>
        )}
      </td>

      <td className="whitespace-nowrap px-5 py-3 text-xs tabular-nums text-gray-400 dark:text-gray-500">
        {doc.nb_chunks}
      </td>

      <td className="whitespace-nowrap px-5 py-3 text-xs tabular-nums text-gray-400 dark:text-gray-500">
        {dateCourte(doc.updated_at)}
      </td>

      <td className="px-2 py-3">
        <div className="flex items-center justify-end gap-1">
          {telechargement && <Loader2 size={13} className="animate-spin text-gray-400" />}
          <DropdownMenu actions={menu} ariaLabel={`Actions sur ${doc.filename ?? doc.doc_id}`} />
        </div>
      </td>
    </tr>
  );
}

export default function DocumentsTable({
  docs,
  estInscriptible,
  actions,
  highlightDocId,
}: {
  docs: IndexedDocument[];
  /** Un document n'est modifiable que par un membre de son domaine. */
  estInscriptible: (doc: IndexedDocument) => boolean;
  actions: ActionsDocument;
  highlightDocId?: string;
}) {
  return (
    <div className="overflow-x-auto">
    <table className="w-full">
      <caption className="sr-only">Documents indexés</caption>
      <thead>
        <tr className="border-b border-gray-100 dark:border-white/8">
          <th className={TH}>Document</th>
          <th className={TH}>Domaine</th>
          <th className={TH}>Version</th>
          <th className={TH} title="Passages de texte extraits et indexés pour la recherche IA">Passages</th>
          <th className={TH}>Mis à jour</th>
          <th className="w-12" />
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50 dark:divide-white/[0.04]">
        {docs.map((doc) => (
          <LigneDocument
            key={doc.doc_id}
            doc={doc}
            peutEcrire={estInscriptible(doc)}
            actions={actions}
            highlightDocId={highlightDocId}
          />
        ))}
      </tbody>
    </table>
    </div>
  );
}
