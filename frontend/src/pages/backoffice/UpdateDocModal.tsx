import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
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
import type { ReponseARelire, UniteChangement, UpdateImpact } from "../../types.ts";

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

type Etape = "pick" | "analyse" | "impact" | "submitting" | "done" | "error";

function LigneARelire({ reponse }: { reponse: ReponseARelire }) {
  return (
    <li className="rounded-lg border border-amber-200/70 dark:border-amber-500/25 bg-white/70 dark:bg-white/[0.03] px-3 py-2.5 space-y-1.5">
      <div className="flex items-start gap-2">
        <a
          href={`/tickets/${reponse.ticket_id}`}
          target="_blank"
          rel="noreferrer"
          className="flex-1 text-xs font-medium text-gray-900 dark:text-gray-100 line-clamp-2 hover:underline"
        >
          {reponse.question || <span className="italic font-normal text-gray-500">Question indisponible</span>}
        </a>
        {reponse.canonique && (
          <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 dark:bg-emerald-400/15 text-green-700 dark:text-emerald-300">
            canonique
          </span>
        )}
        <span className="shrink-0 text-[10px] text-gray-500 dark:text-gray-400 tabular-nums">
          {reponse.nb_validations} val.
        </span>
      </div>
      {reponse.contenu && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400 line-clamp-2">
          {reponse.contenu}
        </p>
      )}
    </li>
  );
}

const LIBELLE_SENS: Record<UniteChangement["sens"], string> = {
  AJOUT: "Ajouté",
  RETRAIT: "Retiré",
  REECRITURE: "Réécrit",
};

/**
 * Un changement, montré **apparié** quand c'en est un.
 *
 * Deux listes indépendantes — « ces paragraphes ont disparu », « ceux-là sont
 * apparus » — ne permettent de juger de rien. C'est le couple « 2 jours →
 * 3 jours » qui rend le changement lisible d'un coup d'œil, et c'est exactement
 * sous cette forme qu'il sera soumis au verdict.
 */
function LigneUnite({ unite }: { unite: UniteChangement }) {
  return (
    <li className="space-y-1 border-l-2 border-amber-300 dark:border-amber-500/40 pl-2.5">
      <p className="text-[10px] font-medium uppercase tracking-wider text-amber-900/70 dark:text-amber-200/70">
        {LIBELLE_SENS[unite.sens]}
      </p>
      {unite.extrait_avant && (
        <p className="text-[11px] font-mono leading-relaxed text-gray-500 dark:text-gray-500 line-through decoration-gray-400/60">
          {unite.extrait_avant}
        </p>
      )}
      {unite.extrait_apres && (
        <p className="text-[11px] font-mono leading-relaxed text-gray-700 dark:text-gray-300">
          {unite.extrait_apres}
        </p>
      )}
    </li>
  );
}

/**
 * Ce que la nouvelle version change, et ce qui sera examiné derrière.
 *
 * Ce panneau ne promet plus rien : l'aperçu n'appelle ni reranker ni LLM, il ne
 * *peut pas* dire quelles réponses seront retirées. Il montre le diff — la seule
 * chose démontrable sans rien lire — et annonce combien de réponses seront
 * soumises au jugement une fois la version en place.
 */
function EcranChangements({ impact }: { impact: UpdateImpact }) {
  const restantes = impact.nb_unites - impact.unites.length;
  const aAnalyser = impact.nb_a_analyser;

  return (
    <div className="rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50/80 dark:bg-amber-400/10 px-4 py-3.5 space-y-2.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900 dark:text-amber-300">
        <FilePlus2 size={16} />
        {impact.nb_unites} changement{impact.nb_unites > 1 ? "s" : ""} dans le document
      </p>

      <ul className="space-y-2">
        {impact.unites.map((u, i) => (
          <LigneUnite key={i} unite={u} />
        ))}
      </ul>
      {restantes > 0 && (
        <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
          … et {restantes} autre{restantes > 1 ? "s" : ""}.
        </p>
      )}

      {aAnalyser > 0 ? (
        <div className="space-y-2.5 pt-1">
          <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
            {aAnalyser} réponse{aAnalyser > 1 ? "s" : ""} enregistrée{aAnalyser > 1 ? "s" : ""}{" "}
            {aAnalyser > 1 ? "seront relues" : "sera relue"} après la mise à jour
            {impact.nb_canoniques > 0 && `, dont ${impact.nb_canoniques} canonique${impact.nb_canoniques > 1 ? "s" : ""}`}
            . Seules celles que le changement contredit seront retirées du service ; les
            autres ne bougeront pas.
          </p>
          <ul className="space-y-2 max-h-64 overflow-y-auto">
            {impact.a_analyser.map((r) => (
              <LigneARelire key={r.reponse_id} reponse={r} />
            ))}
          </ul>
          {aAnalyser > impact.a_analyser.length && (
            <p className="text-[11px] text-amber-900/70 dark:text-amber-200/70">
              … et {aAnalyser - impact.a_analyser.length} autre
              {aAnalyser - impact.a_analyser.length > 1 ? "s" : ""}.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-amber-900/80 dark:text-amber-200/80">
          Aucune réponse enregistrée ne s'appuie sur ce document.
        </p>
      )}
    </div>
  );
}

/** Les réponses qui seront jugées en premier : un passage qu'elles citent a bougé. */
function EncadrePrioritaires({ impact }: { impact: UpdateImpact }) {
  const n = impact.nb_prioritaires;
  if (n === 0) return null;

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-500/30 bg-slate-50/80 dark:bg-slate-400/10 px-4 py-3.5 space-y-2">
      <p className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
        <Archive size={16} />
        {n} réponse{n > 1 ? "s" : ""} {n > 1 ? "citent" : "cite"} un passage modifié
      </p>
      <p className="text-xs text-slate-600/90 dark:text-slate-300/80">
        {n > 1 ? "Elles seront examinées" : "Elle sera examinée"} en premier. Un passage
        modifié ne condamne rien à lui seul — une virgule corrigée suffit à le faire
        apparaître ici. Le retrait du service n'est prononcé que si le changement contredit
        réellement la réponse.
      </p>
      <ul className="space-y-1 pt-0.5">
        {impact.items.slice(0, 3).map((item) => (
          <li
            key={item.reponse_id}
            className="text-[11px] text-slate-600 dark:text-slate-400 line-clamp-1"
          >
            • {item.question}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Le cas où il n'y a rien à dire : reformatage, ou diff impossible. */
function EcranSansChangement({ impact }: { impact: UpdateImpact }) {
  if (!impact.diff_analysable) {
    return (
      <div className="rounded-xl border border-slate-200 dark:border-slate-500/30 bg-slate-50/80 dark:bg-slate-400/10 px-4 py-3.5 space-y-1.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300">
          <AlertTriangle size={16} />
          La version en ligne n'a pas pu être relue.
        </p>
        <p className="text-xs text-slate-600/90 dark:text-slate-300/80">
          Son fichier est introuvable sur le disque : aucune comparaison n'est possible et
          rien ne peut être jugé. Les réponses enregistrées du document seront déposées dans
          l'onglet À relire, à vérifier à la main.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/80 dark:bg-emerald-400/10 px-4 py-3.5 space-y-1.5">
      <p className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
        <CheckCircle2 size={16} />
        Cette version ne dit rien de nouveau.
      </p>
      <p className="text-xs text-emerald-800/80 dark:text-emerald-200/80">
        Mise en forme, espaces, export : le fond est identique. Aucune réponse enregistrée
        ne sera examinée ni dérangée.
      </p>
    </div>
  );
}

function EcranImpact({ impact }: { impact: UpdateImpact }) {
  const aDuNeuf = impact.diff_analysable && impact.nb_unites > 0;
  const enAttente = impact.nb_en_attente;

  return (
    <div className="space-y-3">
      {aDuNeuf ? (
        <>
          <EcranChangements impact={impact} />
          <EncadrePrioritaires impact={impact} />
        </>
      ) : (
        <EcranSansChangement impact={impact} />
      )}
      {aDuNeuf && enAttente > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400 px-1">
          {enAttente} réponse{enAttente > 1 ? "s" : ""} en attente de validation{" "}
          {enAttente > 1 ? "seront annulées et regénérées" : "sera annulée et regénérée"} sur
          la nouvelle version.
        </p>
      )}
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
      setEtape("done");
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
  const nbAAnalyser = impact?.nb_a_analyser ?? 0;

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
              {etape === "done"
                ? restauration ? "Restauration lancée" : "Mise à jour lancée"
                : depuis != null
                  ? `Restaurer la v${depuis}`
                  : "Mettre à jour"}{" "}
              {etape !== "done" && (
                <>— v{doc.version} → v{impact?.version_cible ?? doc.version + 1}</>
              )}
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
                Comparaison avec la version en ligne…
              </p>
            </div>
          )}

          {(etape === "impact" || etape === "submitting") && impact && (
            <EcranImpact impact={impact} />
          )}

          {etape === "done" && (
            <div className="flex flex-col items-center gap-4 py-10 text-center">
              <CheckCircle2 size={40} className="text-emerald-500" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {restauration ? "Restauration lancée" : "Mise à jour lancée"}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Le document sera ré-indexé en arrière-plan.
                </p>
              </div>
              {nbAAnalyser > 0 && (
                <>
                  {/* L'analyse ne rend son verdict qu'après la ré-indexation : dire
                      « à vérifier » tout de suite enverrait l'utilisateur sur une
                      liste qui ne veut encore rien dire. */}
                  <p className="text-xs text-gray-500 dark:text-gray-400 max-w-xs">
                    {nbAAnalyser} réponse{nbAAnalyser > 1 ? "s" : ""} {nbAAnalyser > 1 ? "sont" : "est"}{" "}
                    en cours d'analyse. Celles que le changement contredit basculeront dans
                    Obsolètes ; les cas douteux seront déposés dans À relire, avec leur
                    justification.
                  </p>
                  <a
                    href="/reponses-enregistrees?onglet=a_relire"
                    onClick={onClose}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium transition-colors"
                  >
                    <AlertTriangle size={15} />
                    Suivre l'analyse
                  </a>
                </>
              )}
            </div>
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
              <div className="flex-1 flex flex-col gap-1">
                <button
                  onClick={() => confirmer.mutate(impact.staging_id)}
                  disabled={enCours}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 hover:bg-green-700 dark:bg-emerald-600 dark:hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors"
                >
                  {etape === "submitting" ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RefreshCw size={14} />
                  )}
                  {restauration ? "Confirmer la restauration" : "Confirmer la mise à jour"}
                </button>
                {impact.nb_a_analyser > 0 && (
                  <p className="text-center text-[11px] text-slate-500 dark:text-slate-400">
                    {impact.nb_a_analyser} réponse{impact.nb_a_analyser > 1 ? "s" : ""}{" "}
                    {impact.nb_a_analyser > 1 ? "seront relues" : "sera relue"}
                  </p>
                )}
              </div>
            </>
          )}

          {etape === "done" && (
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 dark:border-white/15 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
            >
              Fermer
            </button>
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
