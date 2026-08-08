import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FilePlus2,
  Loader2,
  RefreshCw,
  X,
  XCircle,
} from "lucide-react";
import { confirmDocumentUpdate, previewDocumentUpdate } from "../../lib/api";
import FileDropzone from "../../components/ui/FileDropzone";
import { validateFile } from "../../lib/documentUpload";
import { useJobs } from "../../context/JobsContext";
import type { ImpactItem, ReponseARelire, UpdateImpact } from "../../types.ts";

/**
 * Le minimum pour cibler une mise à jour.
 *
 * Volontairement plus étroit qu'`IndexedDocument` : l'alerte homonyme de la page
 * Ingestion ouvre cette modale à partir du `detail` d'un 409, qui ne porte que
 * ces champs.
 */
export interface DocCible {
  doc_id: string;
  filename: string | null;
  version: number;
  description?: string;
}

type Etape = "pick" | "analyse" | "impact" | "submitting" | "error";

function LigneImpact({ item }: { item: ImpactItem }) {
  return (
    <li className="rounded-lg border border-red-200/70 dark:border-red-500/25 bg-white/70 dark:bg-white/[0.03] px-3 py-2.5 space-y-1.5">
      <div className="flex items-start gap-2">
        <p className="flex-1 text-xs text-gray-900 dark:text-gray-100 line-clamp-2">
          {item.question || <span className="italic text-gray-500">Question indisponible</span>}
        </p>
        {item.canonique && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300">
            canonique
          </span>
        )}
        <span className="shrink-0 text-[10px] text-gray-500 dark:text-gray-400 tabular-nums">
          {item.nb_validations} val.
        </span>
      </div>
      {item.extraits.map((extrait, i) => (
        <p
          key={item.chunks_modifies[i] ?? i}
          className="text-[11px] text-gray-600 dark:text-gray-400 font-mono leading-relaxed border-l-2 border-red-300 dark:border-red-500/40 pl-2"
        >
          {extrait}
        </p>
      ))}
    </li>
  );
}

/**
 * Une réponse à relire, ouvrable **dans un nouvel onglet**.
 *
 * Le `target="_blank"` n'est pas cosmétique : la modale est au milieu d'un flux
 * en deux temps, et naviguer perdrait l'aperçu calculé — il faudrait re-déposer
 * le fichier. On veut que la relecture puisse se faire *sans* renoncer à la mise
 * à jour, ou l'avertissement pousserait à l'ignorer pour ne pas tout refaire.
 */
function LigneARelire({ reponse }: { reponse: ReponseARelire }) {
  return (
    <li>
      <a
        href={`/tickets/${reponse.ticket_id}`}
        target="_blank"
        rel="noreferrer"
        className="group flex items-start gap-2 rounded-lg border border-amber-200/70 dark:border-amber-500/25 bg-white/70 dark:bg-white/[0.03] px-3 py-2 hover:bg-white dark:hover:bg-white/[0.07] transition-colors"
      >
        <p className="flex-1 text-xs text-gray-900 dark:text-gray-100 line-clamp-2">
          {reponse.question || <span className="italic text-gray-500">Question indisponible</span>}
        </p>
        {reponse.canonique && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300">
            canonique
          </span>
        )}
        <span className="shrink-0 text-[10px] text-gray-500 dark:text-gray-400 tabular-nums">
          {reponse.nb_validations} val.
        </span>
        <ExternalLink
          size={12}
          className="shrink-0 mt-0.5 text-gray-400 group-hover:text-amber-700 dark:group-hover:text-amber-300 transition-colors"
        />
      </a>
    </li>
  );
}

/**
 * Ce que la nouvelle version *ajoute*, en regard de ce qu'elle périme.
 *
 * L'obsolescence ne voit que les passages qui fondaient une réponse. Un article
 * ajouté ailleurs — le geste le plus courant sur une charte — ne touche aucun
 * d'eux : rien ne devient obsolète, et la réponse existante, qui l'ignore,
 * continuerait d'être servie automatiquement sans que personne ne le sache.
 *
 * D'où ce panneau : neutre et non bloquant, il ne décide de rien. Décider
 * demanderait de lire l'ajout, ce qu'aucune règle ne peut faire à la place d'un
 * humain. Masqué quand il n'y a rien à dire — ou rien de démontrable.
 */
function EncadreAjouts({ impact }: { impact: UpdateImpact }) {
  if (!impact.ajouts_analysables || impact.nb_passages_ajoutes === 0) return null;

  const n = impact.nb_passages_ajoutes;
  const relire = impact.nb_a_relire;

  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/80 dark:bg-amber-400/10 px-4 py-3.5 space-y-2.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-300">
        <FilePlus2 size={16} />
        {n} passage{n > 1 ? "s" : ""} ajouté{n > 1 ? "s" : ""} par cette version.
      </p>
      <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
        {relire > 0 ? (
          <>
            {relire} réponse{relire > 1 ? "s" : ""} enregistrée{relire > 1 ? "s" : ""} de ce
            document {relire > 1 ? "n'en tiennent" : "n'en tient"} pas compte et{" "}
            {relire > 1 ? "resteront servies" : "restera servie"} telle{relire > 1 ? "s" : ""}{" "}
            quelle{relire > 1 ? "s" : ""}. Rien ne devient obsolète : à vous de juger si un de ces
            ajouts les contredit.
          </>
        ) : (
          <>Aucune réponse enregistrée ne subsiste sur ce document : rien à relire.</>
        )}
      </p>
      <ul className="space-y-1.5 max-h-32 overflow-y-auto">
        {impact.extraits_ajoutes.map((extrait, i) => (
          <li
            key={i}
            className="text-[11px] text-gray-600 dark:text-gray-400 font-mono leading-relaxed border-l-2 border-amber-300 dark:border-amber-500/40 pl-2"
          >
            {extrait}
          </li>
        ))}
      </ul>
      {n > impact.extraits_ajoutes.length && (
        <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
          … et {n - impact.extraits_ajoutes.length} autre
          {n - impact.extraits_ajoutes.length > 1 ? "s" : ""}.
        </p>
      )}

      {impact.a_relire.length > 0 && (
        <div className="pt-1 space-y-1.5 border-t border-amber-200/70 dark:border-amber-500/25">
          <p className="pt-2 text-[11px] font-medium uppercase tracking-wider text-amber-900/70 dark:text-amber-200/70">
            À relire, les plus servies d'abord
          </p>
          <ul className="space-y-1.5 max-h-40 overflow-y-auto">
            {impact.a_relire.map((r) => (
              <LigneARelire key={r.reponse_id} reponse={r} />
            ))}
          </ul>
          {relire > impact.a_relire.length && (
            <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
              … et {relire - impact.a_relire.length} autre
              {relire - impact.a_relire.length > 1 ? "s" : ""}, dans{" "}
              <span className="font-medium">Réponses enregistrées</span>.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function EcranObsolescence({ impact }: { impact: UpdateImpact }) {
  if (impact.nb_obsoletes === 0) {
    return (
      <div className="rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/80 dark:bg-emerald-400/10 px-4 py-3.5 space-y-1.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 size={16} />
          Aucune réponse enregistrée n'est remise en cause.
        </p>
        <p className="text-xs text-emerald-800/80 dark:text-emerald-200/80">
          {impact.nb_chunks_modifies} passage{impact.nb_chunks_modifies > 1 ? "s" : ""} modifié
          {impact.nb_chunks_modifies > 1 ? "s" : ""} sur {impact.nb_total_chunks}, mais aucun ne
          fondait une réponse enregistrée.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50/80 dark:bg-red-400/10 px-4 py-3.5 space-y-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-red-800 dark:text-red-300">
        <AlertTriangle size={16} />
        {impact.nb_obsoletes} réponse{impact.nb_obsoletes > 1 ? "s" : ""} enregistrée
        {impact.nb_obsoletes > 1 ? "s" : ""} {impact.nb_obsoletes > 1 ? "vont" : "va"} devenir
        obsolète{impact.nb_obsoletes > 1 ? "s" : ""}, dont {impact.nb_canoniques} canonique
        {impact.nb_canoniques > 1 ? "s" : ""}.
      </p>
      <p className="text-xs text-red-800/80 dark:text-red-200/80">
        Les passages sur lesquels elles s'appuyaient ne figurent plus dans la nouvelle version.
        Elles cesseront d'être servies ; les questions correspondantes repasseront par la
        génération sur le document à jour. Elles restent consultables dans l'onglet{" "}
        <span className="font-medium">Obsolètes</span> et peuvent y être restaurées.
      </p>
      <ul className="space-y-2 max-h-56 overflow-y-auto">
        {impact.items.map((item) => (
          <LigneImpact key={item.reponse_id} item={item} />
        ))}
      </ul>
    </div>
  );
}

function EcranImpact({ impact }: { impact: UpdateImpact }) {
  return (
    <div className="space-y-3">
      <EcranObsolescence impact={impact} />
      <EncadreAjouts impact={impact} />
    </div>
  );
}

export default function UpdateDocModal({
  doc,
  fichierInitial,
  impactInitial,
  onClose,
  onSubmitted,
}: {
  doc: DocCible;
  /** Fichier déjà choisi ailleurs (alerte homonyme) : l'analyse démarre seule. */
  fichierInitial?: File;
  /**
   * Aperçu déjà calculé (restauration d'une version) : le fichier est côté serveur,
   * la modale s'ouvre directement sur l'écran d'impact et il n'y a pas de retour
   * possible vers le choix d'un fichier.
   */
  impactInitial?: UpdateImpact;
  onClose: () => void;
  /** Job lancé — distingue une confirmation d'une simple fermeture. */
  onSubmitted?: () => void;
}) {
  const queryClient = useQueryClient();
  const { addJob } = useJobs();

  const [etape, setEtape] = useState<Etape>(
    impactInitial ? "impact" : fichierInitial ? "analyse" : "pick",
  );
  const [file, setFile] = useState<File | null>(fichierInitial ?? null);
  const [fileError, setFileError] = useState<string | null>(null);
  // `undefined` = ne pas envoyer le champ, donc conserver la description en base.
  // C'est le cas de l'alerte homonyme, qui ouvre la modale sans la connaître :
  // envoyer une chaîne vide l'effacerait.
  const [description, setDescription] = useState<string | undefined>(doc.description);
  const [impact, setImpact] = useState<UpdateImpact | null>(impactInitial ?? null);
  const [erreur, setErreur] = useState<string | null>(null);

  const echouer = (e: unknown) => {
    setErreur(e instanceof Error ? e.message : "Erreur inattendue");
    setEtape("error");
  };

  const analyse = useMutation({
    mutationFn: (f: File) => previewDocumentUpdate(doc.doc_id, f, description),
    onSuccess: (data) => {
      setImpact(data);
      setEtape("impact");
    },
    onError: echouer,
  });

  const confirmer = useMutation({
    mutationFn: (stagingId: string) => confirmDocumentUpdate(doc.doc_id, stagingId),
    onSuccess: (res) => {
      if (res.job_id) addJob(res.job_id, res.filename, "maj");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onSubmitted?.();
      onClose();
    },
    onError: echouer,
  });

  // Ouverture directe sur l'analyse : le fichier vient de la page Ingestion, il
  // n'y a pas de clic de l'utilisateur pour déclencher l'appel. Le garde-fou
  // évite un second aperçu (donc un second staging) en StrictMode.
  const analyseLancee = useRef(false);
  useEffect(() => {
    if (!fichierInitial || analyseLancee.current) return;
    analyseLancee.current = true;
    analyse.mutate(fichierInitial);
  }, [fichierInitial, analyse]);

  const lancerAnalyse = () => {
    if (!file) return;
    setEtape("analyse");
    analyse.mutate(file);
  };

  const revenirAuChoix = () => {
    setFile(null);
    setFileError(null);
    setImpact(null);
    setErreur(null);
    setEtape("pick");
  };

  const enCours = etape === "analyse" || etape === "submitting";
  // Restauration : il n'y a pas de fichier local à reprendre, le seul retour est la sortie.
  const restauration = impactInitial !== undefined;
  const depuis = impact?.restauree_depuis;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 dark:bg-black/60 backdrop-blur-sm" />
      <div
        className="relative glass-card rounded-2xl w-full max-w-xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-black/[0.06] dark:border-white/10">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">
              {depuis != null ? `Restaurer la v${depuis}` : "Mettre à jour"} — v{doc.version} → v
              {impact?.version_cible ?? doc.version + 1}
            </p>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {doc.filename ?? doc.doc_id}
            </p>
          </div>
          <button
            onClick={onClose}
            className="ml-4 shrink-0 p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {etape === "pick" && (
            <>
              <FileDropzone
                file={file}
                error={fileError}
                onPick={(f) => {
                  const err = validateFile(f);
                  setFileError(err);
                  setFile(err ? null : f);
                }}
              />
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Description
                </label>
                <input
                  type="text"
                  value={description ?? ""}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Résumez brièvement le contenu du document…"
                  className="w-full px-3 py-2 rounded-lg text-sm border border-gray-300 dark:border-white/15 bg-white/70 dark:bg-white/5 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-green-400/50 dark:focus:ring-emerald-400/40"
                />
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Le document conservera son identifiant ; l'ancienne version sera archivée et
                restera téléchargeable.
              </p>
            </>
          )}

          {etape === "analyse" && (
            <div className="flex flex-col items-center gap-3 py-12">
              <Loader2 size={22} className="animate-spin text-gray-400" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Analyse de l'impact sur les réponses enregistrées…
              </p>
            </div>
          )}

          {(etape === "impact" || etape === "submitting") && impact && (
            <>
              <EcranImpact impact={impact} />
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {impact.filename} — {impact.nb_chunks_modifies} passage
                {impact.nb_chunks_modifies > 1 ? "s" : ""} modifié
                {impact.nb_chunks_modifies > 1 ? "s" : ""} sur {impact.nb_total_chunks}.
              </p>
            </>
          )}

          {etape === "error" && (
            <div className="space-y-3">
              <p className="flex items-center gap-2 text-sm font-medium text-red-700 dark:text-red-400">
                <XCircle size={16} />
                {restauration ? "Restauration impossible" : "Mise à jour impossible"}
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">{erreur}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-2 px-6 py-4 border-t border-black/[0.06] dark:border-white/10">
          {etape === "pick" && (
            <>
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Annuler
              </button>
              <button
                onClick={lancerAnalyse}
                disabled={!file}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <RefreshCw size={14} />
                Analyser l'impact
              </button>
            </>
          )}

          {(etape === "impact" || etape === "submitting") && impact && (
            <>
              <button
                onClick={restauration ? onClose : revenirAuChoix}
                disabled={enCours}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 transition-colors"
              >
                {restauration ? "Annuler" : "Retour"}
              </button>
              <button
                onClick={() => confirmer.mutate(impact.staging_id)}
                disabled={enCours}
                className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 transition-colors
                  ${
                    impact.nb_obsoletes > 0
                      ? "bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500"
                      : "bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500"
                  }`}
              >
                {etape === "submitting" ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                {restauration ? "Confirmer la restauration" : "Confirmer la mise à jour"}
              </button>
            </>
          )}

          {etape === "error" && (
            <>
              <button
                onClick={() => {
                  // Le 409 « mise à jour en cours » peut venir d'un verrou dont la
                  // liste n'a pas connaissance : on la rafraîchit en sortant.
                  queryClient.invalidateQueries({ queryKey: ["documents"] });
                  onClose();
                }}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                Fermer
              </button>
              {!restauration && (
                <button
                  onClick={revenirAuChoix}
                  className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                >
                  Choisir un autre fichier
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
