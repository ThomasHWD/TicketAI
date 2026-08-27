import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, X } from "lucide-react";
import { getHorsDomaine, masquerAngleMort } from "../../../lib/api/stats";

export const PERIODES = [
  { value: "semaine", label: "Cette semaine" },
  { value: "mois",    label: "Ce mois" },
  { value: "annee",   label: "Cette année" },
] as const;
export type PeriodeId = typeof PERIODES[number]["value"];

const UNDO_DELAY = 6_000;

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
}

export default function AnglesMorts({ periode }: { periode: PeriodeId }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [undoId, setUndoId] = useState<string | null>(null);
  const [erreurMasquer, setErreurMasquer] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data = [], isLoading } = useQuery({
    queryKey: ["angles-morts", periode],
    queryFn: () => getHorsDomaine(periode),
    staleTime: 60_000,
  });

  const { mutate: masquer } = useMutation({
    mutationFn: masquerAngleMort,
    onSuccess: () => {
      setUndoId(null);
      queryClient.invalidateQueries({ queryKey: ["angles-morts"] });
    },
    onError: () => {
      setUndoId(null);
      setErreurMasquer("Impossible de marquer ce ticket comme traité. Réessayez.");
    },
  });

  const handleDismiss = (id: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setErreurMasquer(null);
    setUndoId(id);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      masquer(id);
    }, UNDO_DELAY);
  };

  const handleUndo = () => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setUndoId(null);
  };

  const filteredData = data
    .map((entry) => ({
      ...entry,
      questions: entry.questions.filter((q) => q.id !== undoId),
    }))
    .filter((entry) => entry.questions.length > 0);

  if (isLoading) return <Skeleton />;
  if (data.length === 0 && !undoId) return <EmptyState />;

  return (
    <>
      {erreurMasquer && (
        <div role="alert" className="mx-5 mt-3 flex items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2 text-xs text-red-700 dark:border-red-500/25 dark:bg-red-500/10 dark:text-red-300">
          <span>{erreurMasquer}</span>
          <button
            type="button"
            onClick={() => setErreurMasquer(null)}
            aria-label="Fermer"
            className="shrink-0 rounded p-0.5 hover:bg-red-100 dark:hover:bg-red-500/20 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-400"
          >
            <X size={11} aria-hidden="true" />
          </button>
        </div>
      )}
      {filteredData.length > 0 && (
        <div className="divide-y divide-gray-100 dark:divide-white/[0.06]">
          {filteredData.map((entry) => (
            <div key={entry.domaine}>
              <div className="flex items-center justify-between gap-3 bg-gray-50/60 dark:bg-white/[0.02] px-5 py-2.5 border-b border-gray-100 dark:border-white/[0.06]">
                <span className="text-xs font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
                  {entry.domaine}
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums bg-purple-50 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-purple-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-500 dark:bg-purple-400" aria-hidden="true" />
                  {entry.nb_tickets} ticket{entry.nb_tickets > 1 ? "s" : ""}
                </span>
              </div>
              <ul className="divide-y divide-gray-100 dark:divide-white/[0.04]">
                {entry.questions.map((q) => (
                  <li key={q.id} className="group flex items-stretch">
                    <button
                      type="button"
                      onClick={() => navigate(`/tickets/${q.id}`)}
                      className="flex-1 min-w-0 flex items-center gap-4 pl-5 pr-3 py-3.5 text-left hover:bg-gray-50/70 dark:hover:bg-white/[0.03] transition-colors duration-75"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 dark:text-gray-100 truncate leading-snug">
                          {q.objet ?? q.question.slice(0, 100)}
                        </p>
                        {q.objet && (
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                            {q.question.slice(0, 120)}
                          </p>
                        )}
                      </div>
                      <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 tabular-nums">
                        {formatDate(q.created_at)}
                      </span>
                      <ArrowRight
                        size={13}
                        className="text-gray-300 dark:text-white/20 shrink-0 group-hover:text-gray-500 dark:group-hover:text-gray-400 group-hover:translate-x-0.5 transition-all duration-75"
                        aria-hidden="true"
                      />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDismiss(q.id)}
                      aria-label="Marquer comme traité"
                      title="Marquer comme traité"
                      className="shrink-0 flex items-center justify-center w-10 border-l border-gray-100 dark:border-white/[0.05] text-gray-300 dark:text-white/20 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 opacity-40 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500 transition-all duration-100"
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      {undoId && <UndoToast onUndo={handleUndo} delay={UNDO_DELAY} />}
    </>
  );
}

function UndoToast({ onUndo, delay }: { onUndo: () => void; delay: number }) {
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setStarted(true), 30);
    return () => clearTimeout(t);
  }, []);

  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-3 bg-gray-900 dark:bg-white text-white dark:text-gray-900 rounded-xl shadow-xl text-sm font-medium whitespace-nowrap overflow-hidden"
    >
      <div
        aria-hidden="true"
        className="absolute bottom-0 left-0 h-0.5 w-full bg-emerald-500 origin-left"
        style={{
          transform: started ? "scaleX(0)" : "scaleX(1)",
          transition: started ? `transform ${delay}ms linear` : "none",
        }}
      />
      <span>Question traitée</span>
      <div className="w-px h-4 bg-white/20 dark:bg-gray-900/20" aria-hidden="true" />
      <button
        onClick={onUndo}
        className="text-emerald-400 dark:text-emerald-600 hover:text-emerald-300 dark:hover:text-emerald-700 font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 rounded px-0.5 transition-colors"
      >
        Annuler
      </button>
    </div>,
    document.body,
  );
}

function Skeleton() {
  return (
    <div role="status" aria-label="Chargement des angles morts…" className="animate-pulse divide-y divide-gray-100 dark:divide-white/[0.06]">
      {[
        { rows: 4, widths: [72, 58, 85, 64] },
        { rows: 2, widths: [55, 78, 0, 0] },
      ].map(({ rows, widths }, i) => (
        <div key={i}>
          <div className="bg-gray-50/60 dark:bg-white/[0.02] px-5 py-2.5 border-b border-gray-100 dark:border-white/[0.06] flex items-center justify-between">
            <div className="h-3 w-14 bg-gray-200 dark:bg-white/10 rounded" />
            <div className="h-4 w-20 bg-purple-100 dark:bg-purple-500/10 rounded-full" />
          </div>
          <div className="divide-y divide-gray-100 dark:divide-white/[0.04]">
            {Array.from({ length: rows }).map((_, j) => (
              <div key={j} className="px-5 py-3.5 flex items-center gap-4">
                <div className="flex-1">
                  <div className="h-3.5 bg-gray-100 dark:bg-white/[0.07] rounded" style={{ width: `${widths[j]}%` }} />
                </div>
                <div className="h-3 w-16 bg-gray-100 dark:bg-white/[0.05] rounded shrink-0" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center px-8">
      <div className="flex items-center justify-center w-11 h-11 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 mb-1">
        <CheckCircle2 size={20} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Aucun angle mort sur cette période</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 max-w-xs mx-auto leading-relaxed">
          Toutes les questions ont pu être traitées depuis les documents disponibles.
        </p>
      </div>
    </div>
  );
}
