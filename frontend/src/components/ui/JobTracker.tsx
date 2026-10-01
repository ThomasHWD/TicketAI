import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileText, Loader2, X, XCircle } from "lucide-react";
import { getDocumentStatus } from "../../lib/api";
import { type TrackedJob, useJobs } from "../../context/JobsContext";

/** Job completion summary. Update jobs announce what begins (responses queued for review), not what's concluded — saying "4 obsolete" here would be wrong; most will survive. */
function resume(job: TrackedJob): string {
  const chunks = `${job.nb_chunks} chunk${(job.nb_chunks ?? 0) > 1 ? "s" : ""}`;
  if (job.kind !== "maj") return `Indexé — ${chunks}`;
  const n = job.nb_a_analyser ?? 0;
  if (n > 0) return `Mis à jour — ${n} réponse${n > 1 ? "s" : ""} en cours d'analyse`;
  const relire = job.nb_a_relire ?? 0;
  if (relire > 0) return `Mis à jour — ${relire} réponse${relire > 1 ? "s" : ""} à relire`;
  return `Mis à jour — ${chunks}`;
}

function JobCard({ job }: { job: TrackedJob }) {
  const { updateJob, dismissJob } = useJobs();
  const isTerminal = job.statut === "SUCCESS" || job.statut === "FAILURE";

  const { data } = useQuery({
    queryKey: ["job-tracker", job.jobId],
    queryFn: () => getDocumentStatus(job.jobId),
    enabled: !isTerminal,
    refetchInterval: isTerminal ? false : 5000,
  });

  useEffect(() => {
    if (!data) return;
    if (data.statut === "SUCCESS") {
      updateJob(job.jobId, {
        statut: "SUCCESS",
        nb_chunks: data.resultat?.nb_chunks,
        nb_a_analyser: data.resultat?.nb_a_analyser,
        nb_a_relire: data.resultat?.nb_a_relire,
      });
    } else if (data.statut === "FAILURE") {
      updateJob(job.jobId, { statut: "FAILURE", erreur: data.erreur });
    } else if (data.statut !== job.statut) {
      updateJob(job.jobId, { statut: data.statut });
    }
  }, [data, job.jobId, job.statut, updateJob]);

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-xl border text-sm transition-colors
        ${
          job.statut === "SUCCESS"
            ? "bg-emerald-50/90 dark:bg-emerald-400/10 border-emerald-200 dark:border-emerald-500/30"
            : job.statut === "FAILURE"
              ? "bg-red-50/90 dark:bg-red-400/10 border-red-200 dark:border-red-500/30"
              : "bg-white/80 dark:bg-white/[0.06] border-black/[0.07] dark:border-white/10"
        }`}
    >
      {/* Icône statut */}
      <div className="mt-0.5 shrink-0">
        {job.statut === "SUCCESS" ? (
          <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" />
        ) : job.statut === "FAILURE" ? (
          <XCircle size={15} className="text-red-600 dark:text-red-400" />
        ) : (
          <Loader2 size={15} className="animate-spin text-subtle" />
        )}
      </div>

      {/* Contenu */}
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 dark:text-gray-100 truncate text-xs leading-snug">
          {job.filename}
        </p>
        <p className="text-xs mt-0.5 leading-snug">
          {job.statut === "SUCCESS" ? (
            <span className="text-emerald-700 dark:text-emerald-400">{resume(job)}</span>
          ) : job.statut === "FAILURE" ? (
            <span className="text-red-600 dark:text-red-400 line-clamp-2">
              {job.erreur ?? (job.kind === "maj" ? "Échec de la mise à jour" : "Échec de l'indexation")}
            </span>
          ) : (
            <span className="text-muted-foreground">
              {job.statut !== "STARTED"
                ? "En attente…"
                : job.kind === "maj"
                  ? "Mise à jour en cours…"
                  : "Indexation en cours…"}
            </span>
          )}
        </p>
      </div>

      {/* Bouton fermer (jobs terminés uniquement) */}
      {isTerminal && (
        <button
          onClick={() => dismissJob(job.jobId)}
          className="shrink-0 mt-0.5 p-0.5 rounded text-muted-foreground hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
}

export default function JobTracker() {
  const { jobs } = useJobs();

  if (jobs.length === 0) return null;

  const active = jobs.filter((j) => j.statut !== "SUCCESS" && j.statut !== "FAILURE").length;

  return (
    <div className="fixed bottom-5 right-5 z-40 w-72 space-y-2">
      {/* En-tête discret si plusieurs jobs */}
      {jobs.length > 1 && (
        <div className="flex items-center gap-2 px-1">
          <FileText size={12} className="text-subtle" />
          <span className="text-xs text-muted-foreground">
            {active > 0 ? `${active} traitement${active > 1 ? "s" : ""} en cours` : "Traitements terminés"}
          </span>
        </div>
      )}
      {[...jobs].reverse().map((job) => (
        <JobCard key={job.jobId} job={job} />
      ))}
    </div>
  );
}
