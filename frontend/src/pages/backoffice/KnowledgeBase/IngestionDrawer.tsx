import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Copy,
  Database,
  FilePlus2,
  Loader2,
  PenLine,
  RefreshCw,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { uploadDocument, DocumentHomonymeError } from "../../../lib/api";
import { validateFile } from "../../../lib/documentUpload";
import { useJobs } from "../../../context/JobsContext";
import Drawer from "../../../components/ui/Drawer";
import FileDropzone from "../../../components/ui/FileDropzone";
import type { Domaine, DocumentHomonyme, DocumentUploadResponse } from "../../../types";

type Phase = "idle" | "uploading" | "duplicate" | "homonyme" | "error" | "queued";
type Mode = "upload" | "write";

const MIN_CARACTERES = 50;

const CHAMP =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 dark:border-white/12 dark:bg-white/5 dark:text-gray-100 dark:placeholder:text-gray-600";
const LABEL = "block text-xs font-medium text-gray-700 dark:text-gray-300";

function Alerte({
  ton,
  icon: Icon,
  titre,
  children,
  actions,
}: {
  ton: "ambre" | "rouge";
  icon: typeof AlertTriangle;
  titre: string;
  children: React.ReactNode;
  actions: React.ReactNode;
}) {
  const ambre = ton === "ambre";
  return (
    <div
      role="alert"
      className={`space-y-2.5 rounded-xl border px-4 py-3.5 ${
        ambre
          ? "border-amber-200 bg-amber-50/60 dark:border-amber-500/25 dark:bg-amber-500/[0.07]"
          : "border-red-200 bg-red-50/60 dark:border-red-500/25 dark:bg-red-500/10"
      }`}
    >
      <p
        className={`flex items-center gap-2 text-sm font-semibold ${
          ambre ? "text-amber-800 dark:text-amber-300" : "text-red-700 dark:text-red-400"
        }`}
      >
        <Icon size={15} className="shrink-0" aria-hidden="true" />
        {titre}
      </p>
      <p
        className={`text-xs leading-relaxed ${
          ambre ? "text-amber-900/80 dark:text-amber-200/80" : "text-red-700/80 dark:text-red-300/80"
        }`}
      >
        {children}
      </p>
      <div className="flex flex-wrap items-center gap-2 pt-0.5">{actions}</div>
    </div>
  );
}

const BTN_ALERTE_PRIMAIRE =
  "inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100";
const BTN_ALERTE_SECONDAIRE =
  "inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white/70 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-white dark:border-white/15 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10";
const BTN_ALERTE_DISCRET =
  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-black/5 dark:text-gray-400 dark:hover:bg-white/10";

/**
 * Ajout d'un document, en panneau latéral : le tableau reste visible derrière,
 * et l'ingestion ne coûte plus une navigation aller-retour.
 *
 * Les deux modes produisent le même objet — un `File`. Rédiger en clair n'est
 * qu'un raccourci pour ne pas avoir à fabriquer un `.md` sur son disque.
 */
export default function IngestionDrawer({
  domaines,
  onClose,
  onIndexed,
  onDemanderMaj,
  onVoirDocument,
}: {
  domaines: Domaine[];
  onClose: () => void;
  /** Un job d'indexation vient d'être enfilé. */
  onIndexed: () => void;
  /** L'utilisateur choisit de mettre à jour l'homonyme plutôt que d'en créer un second. */
  onDemanderMaj: (doc: DocumentHomonyme, fichier: File) => void;
  /** Retrouve dans le tableau le document déjà indexé. */
  onVoirDocument: (filename: string) => void;
}) {
  const { addJob } = useJobs();

  const [mode, setMode] = useState<Mode>("upload");
  const [domaine, setDomaine] = useState<Domaine>(domaines[0] ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [titre, setTitre] = useState("");
  const [contenu, setContenu] = useState("");
  const [description, setDescription] = useState("");

  const [phase, setPhase] = useState<Phase>("idle");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DocumentUploadResponse | null>(null);
  const [homonyme, setHomonyme] = useState<DocumentHomonyme | null>(null);
  const [envoye, setEnvoye] = useState<File | null>(null);
  const [dernierNom, setDernierNom] = useState("");

  const construireFichier = (): File | null => {
    if (mode !== "write") return file;
    const blob = new Blob([contenu], { type: "text/plain" });
    return new File([blob], `${titre.trim() || "document"}.md`, { type: "text/plain" });
  };

  async function envoyer(cible: File, forceNouveau = false) {
    setPhase("uploading");
    setUploadError(null);
    setDuplicate(null);
    setHomonyme(null);
    setEnvoye(cible);
    try {
      const res = await uploadDocument(cible, domaine, description.trim(), forceNouveau);
      if (res.statut === "DÉJÀ_INDEXÉ") {
        setDuplicate(res);
        setPhase("duplicate");
        return;
      }
      if (res.job_id) addJob(res.job_id, res.filename);
      setDernierNom(res.filename);
      onIndexed();
      setPhase("queued");
    } catch (err) {
      if (err instanceof DocumentHomonymeError) {
        setHomonyme(err.document);
        setPhase("homonyme");
        return;
      }
      setUploadError(err instanceof Error ? err.message : "Erreur inattendue");
      setPhase("error");
    }
  }

  /** Vide le formulaire sans fermer : on enchaîne souvent plusieurs documents. */
  function reinitialiser() {
    setFile(null);
    setFileError(null);
    setTitre("");
    setContenu("");
    setDescription("");
    setUploadError(null);
    setDuplicate(null);
    setHomonyme(null);
    setEnvoye(null);
    setPhase("idle");
  }

  const occupe = phase === "uploading";
  const pretAEnvoyer =
    !occupe &&
    !!domaine &&
    description.trim().length > 0 &&
    (mode === "upload"
      ? !!file && !fileError
      : titre.trim().length > 0 && contenu.trim().length >= MIN_CARACTERES);

  if (phase === "queued") {
    return (
      <Drawer
        title="Indexation lancée"
        onClose={onClose}
        footer={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
            >
              Fermer
            </button>
            <button
              type="button"
              onClick={reinitialiser}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
            >
              <FilePlus2 size={14} />
              Ajouter un autre
            </button>
          </div>
        }
      >
        <div className="flex flex-col items-center gap-4 py-10 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/15">
            <CheckCircle2 size={22} className="text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{dernierNom}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Découpage et indexation en cours en arrière-plan.
            </p>
          </div>
          <p className="max-w-xs text-xs leading-relaxed text-gray-400 dark:text-gray-500">
            Le document apparaîtra dans la liste dès que ses chunks seront écrits dans l'index. La
            progression est suivie en bas à droite de l'écran.
          </p>
        </div>
      </Drawer>
    );
  }

  return (
    <Drawer
      title="Ajouter un document"
      description="Il sera découpé, vectorisé et interrogeable par le moteur de réponse."
      onClose={onClose}
      footer={
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={occupe}
            className="flex-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 dark:border-white/12 dark:text-gray-300 dark:hover:bg-white/5"
          >
            Annuler
          </button>
          <button
            type="button"
            onClick={() => {
              const cible = construireFichier();
              if (cible) envoyer(cible);
            }}
            disabled={!pretAEnvoyer}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
          >
            {occupe ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Envoi en cours…
              </>
            ) : (
              <>
                <Database size={14} />
                Indexer
              </>
            )}
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Mode de saisie */}
        <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-0.5 dark:border-white/10 dark:bg-white/5">
          {(
            [
              { key: "upload", label: "Importer un fichier", icon: UploadCloud },
              { key: "write", label: "Rédiger", icon: PenLine },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => !occupe && setMode(key)}
              disabled={occupe}
              aria-pressed={mode === key}
              className={`flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                mode === key
                  ? "bg-white text-gray-900 shadow-sm dark:bg-white/10 dark:text-gray-100"
                  : "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>

        {/* Avertissements — inline, le formulaire reste rempli derrière */}
        {phase === "duplicate" && duplicate && (
          <Alerte
            ton="ambre"
            icon={Copy}
            titre="Document déjà indexé à l'identique"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => {
                    onVoirDocument(duplicate.filename);
                    onClose();
                  }}
                  className={BTN_ALERTE_PRIMAIRE}
                >
                  <ArrowRight size={13} />
                  Voir le document
                </button>
                <button type="button" onClick={reinitialiser} className={BTN_ALERTE_SECONDAIRE}>
                  <RefreshCw size={13} />
                  Choisir un autre fichier
                </button>
              </>
            }
          >
            Ce fichier est déjà indexé sous «&nbsp;{duplicate.filename}&nbsp;»
            {duplicate.domaine ? ` (${duplicate.domaine}` : ""}
            {duplicate.domaine && duplicate.version ? `, v${duplicate.version}` : ""}
            {duplicate.domaine ? ")" : ""}. Son contenu n'a pas changé : il n'y a rien à mettre à
            jour.
          </Alerte>
        )}

        {phase === "homonyme" && homonyme && (
          <Alerte
            ton="ambre"
            icon={AlertTriangle}
            titre="Un document porte déjà ce nom"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => envoye && onDemanderMaj(homonyme, envoye)}
                  className={BTN_ALERTE_PRIMAIRE}
                >
                  <RefreshCw size={13} />
                  Mettre à jour ce document
                </button>
                <button
                  type="button"
                  onClick={() => envoye && envoyer(envoye, true)}
                  className={BTN_ALERTE_SECONDAIRE}
                >
                  <Database size={13} />
                  Créer un nouveau document
                </button>
                <button type="button" onClick={reinitialiser} className={BTN_ALERTE_DISCRET}>
                  Annuler
                </button>
              </>
            }
          >
            «&nbsp;{homonyme.filename}&nbsp;» existe déjà en {homonyme.domaine} (v{homonyme.version},{" "}
            {homonyme.nb_chunks} chunk{homonyme.nb_chunks > 1 ? "s" : ""}), avec un contenu
            différent. L'indexer tel quel créerait un second document : les deux versions
            répondraient alors aux mêmes questions, en se contredisant.
          </Alerte>
        )}

        {phase === "error" && (
          <Alerte
            ton="rouge"
            icon={XCircle}
            titre="Échec de l'indexation"
            actions={
              <button
                type="button"
                onClick={() => envoye && envoyer(envoye)}
                className={BTN_ALERTE_PRIMAIRE}
              >
                <RefreshCw size={13} />
                Réessayer
              </button>
            }
          >
            {uploadError}
          </Alerte>
        )}

        {/* Source */}
        {mode === "upload" ? (
          <FileDropzone
            file={file}
            error={fileError}
            disabled={occupe}
            onPick={(f) => {
              const err = validateFile(f);
              setFileError(err);
              setFile(err ? null : f);
            }}
          />
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="ing-titre" className={LABEL}>
                Titre du document
              </label>
              <input
                id="ing-titre"
                type="text"
                value={titre}
                onChange={(e) => setTitre(e.target.value)}
                disabled={occupe}
                placeholder="Ex : Politique de télétravail 2025"
                className={CHAMP}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="ing-contenu" className={LABEL}>
                Contenu
              </label>
              <textarea
                id="ing-contenu"
                value={contenu}
                onChange={(e) => setContenu(e.target.value)}
                disabled={occupe}
                rows={12}
                placeholder="Rédigez le contenu du document ici…"
                className={`${CHAMP} resize-y font-mono leading-relaxed`}
              />
              <p className="text-xs text-gray-400 dark:text-gray-500">
                Markdown ou texte brut — minimum {MIN_CARACTERES} caractères
                {contenu.length > 0 && (
                  <span
                    className={`ml-1 tabular-nums ${
                      contenu.trim().length >= MIN_CARACTERES
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-gray-400"
                    }`}
                  >
                    ({contenu.trim().length})
                  </span>
                )}
              </p>
            </div>
          </div>
        )}

        {/* Métadonnées communes */}
        <div className="space-y-1.5">
          <span className={LABEL}>Domaine</span>
          {domaines.length === 0 ? (
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Aucun domaine ne vous est attribué : demandez un rattachement à un administrateur.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              {domaines.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => !occupe && setDomaine(d)}
                  disabled={occupe}
                  aria-pressed={domaine === d}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                    domaine === d
                      ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-white/8 dark:text-gray-400 dark:hover:bg-white/12"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="ing-description" className={LABEL}>
            Description <span className="text-red-500" aria-hidden="true">*</span>
          </label>
          <input
            id="ing-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={occupe}
            placeholder="Résumez brièvement le contenu du document…"
            className={CHAMP}
            required
          />
          <p className="text-xs text-gray-400 dark:text-gray-500">
            Obligatoire — sert à retrouver le document dans la liste (non indexée).
          </p>
        </div>
      </div>
    </Drawer>
  );
}
