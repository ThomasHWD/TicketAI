import { createContext, useCallback, useContext, useEffect, useState } from "react";

export interface TrackedJob {
  jobId: string;
  filename: string;
  startedAt: number;
  statut: "PENDING" | "STARTED" | "RETRY" | "SUCCESS" | "FAILURE";
  /** Absent = ingestion : les jobs déjà en localStorage restent lisibles. */
  kind?: "ingestion" | "maj";
  nb_chunks?: number;
  /**
   * Mise à jour uniquement : réponses soumises à la ré-vérification. Le job de
   * mise à jour ne retire plus rien lui-même — il ne peut donc annoncer qu'un
   * nombre de réponses à juger, jamais un nombre de réponses archivées.
   */
  nb_a_analyser?: number;
  /** Signalées sans jugement possible (version sortante illisible). */
  nb_a_relire?: number;
  erreur?: string;
}

interface JobsContextValue {
  jobs: TrackedJob[];
  addJob: (jobId: string, filename: string, kind?: TrackedJob["kind"]) => void;
  updateJob: (jobId: string, patch: Partial<TrackedJob>) => void;
  dismissJob: (jobId: string) => void;
}

const JobsContext = createContext<JobsContextValue | null>(null);

const LS_KEY = "ticketai_jobs";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

function loadFromStorage(): TrackedJob[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return [];
    const parsed: TrackedJob[] = JSON.parse(raw);
    const cutoff = Date.now() - MAX_AGE_MS;
    return parsed.filter((j) => j.startedAt > cutoff);
  } catch {
    return [];
  }
}

function saveToStorage(jobs: TrackedJob[]) {
  const active = jobs.filter(
    (j) => j.statut !== "SUCCESS" && j.statut !== "FAILURE",
  );
  localStorage.setItem(LS_KEY, JSON.stringify(active));
}

export function JobsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<TrackedJob[]>(loadFromStorage);

  useEffect(() => {
    saveToStorage(jobs);
  }, [jobs]);

  const addJob = useCallback((jobId: string, filename: string, kind: TrackedJob["kind"] = "ingestion") => {
    setJobs((prev) => [
      ...prev.filter((j) => j.jobId !== jobId),
      { jobId, filename, kind, startedAt: Date.now(), statut: "PENDING" },
    ]);
  }, []);

  const updateJob = useCallback((jobId: string, patch: Partial<TrackedJob>) => {
    setJobs((prev) =>
      prev.map((j) => (j.jobId === jobId ? { ...j, ...patch } : j)),
    );
  }, []);

  const dismissJob = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.jobId !== jobId));
  }, []);

  return (
    <JobsContext.Provider value={{ jobs, addJob, updateJob, dismissJob }}>
      {children}
    </JobsContext.Provider>
  );
}

export function useJobs() {
  const ctx = useContext(JobsContext);
  if (!ctx) throw new Error("useJobs must be used within JobsProvider");
  return ctx;
}
