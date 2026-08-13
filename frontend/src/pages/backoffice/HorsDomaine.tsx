import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, X } from "lucide-react";
import { getHorsDomaine, masquerAngleMort } from "../../lib/api/stats";

const PERIODES = [
  { value: "semaine", label: "Cette semaine" },
  { value: "mois",    label: "Ce mois" },
  { value: "annee",   label: "Cette année" },
] as const;

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}

export default function HorsDomaine() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [periode, setPeriode] = useState<"semaine" | "mois" | "annee">("mois");

  const { data = [], isLoading } = useQuery({
    queryKey: ["angles-morts", periode],
    queryFn: () => getHorsDomaine(periode),
    staleTime: 60_000,
  });

  const { mutate: masquer } = useMutation({
    mutationFn: masquerAngleMort,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["angles-morts"] }),
  });

  const totalTickets = data.reduce((s, d) => s + d.nb_tickets, 0);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-200/60 dark:border-white/[0.08]">
          <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Sujets non couverts
          </h1>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            Questions que vos documents ne permettent pas encore de traiter.
          </p>
        </div>
        <div className="px-4 py-2 flex items-center justify-between gap-4">
          <div className="flex items-center gap-0.5">
            {PERIODES.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriode(p.value)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  periode === p.value
                    ? "bg-gray-100 dark:bg-white/10 text-gray-900 dark:text-gray-100"
                    : "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {!isLoading && data.length > 0 && (
            <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums shrink-0">
              {totalTickets} ticket{totalTickets > 1 ? "s" : ""} sans couverture
            </span>
          )}
        </div>
      </div>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      {isLoading ? (
        <SkeletonList />
      ) : data.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          {data.map((entry) => (
            <div key={entry.domaine} className="glass-card rounded-2xl overflow-hidden">
              {/* Domain label */}
              <div className="px-5 py-2.5 border-b border-gray-200/60 dark:border-white/[0.08] flex items-center justify-between gap-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  {entry.domaine}
                </span>
                <span className="text-xs font-medium text-purple-600 dark:text-purple-400 tabular-nums shrink-0">
                  {entry.nb_tickets} ticket{entry.nb_tickets > 1 ? "s" : ""}
                </span>
              </div>

              {/* Questions */}
              <ul className="divide-y divide-gray-200/50 dark:divide-white/[0.06]">
                {entry.questions.map((q) => (
                  <li key={q.id} className="group flex items-center">
                    <button
                      onClick={() => navigate(`/tickets/${q.id}`)}
                      className="flex-1 min-w-0 flex items-center gap-3 pl-5 pr-3 py-3 text-left hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 dark:text-gray-100 truncate">
                          {q.objet ?? q.question.slice(0, 100)}
                        </p>
                        {q.objet && (
                          <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                            {q.question.slice(0, 120)}
                          </p>
                        )}
                      </div>
                      <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0 tabular-nums">
                        {formatDate(q.created_at)}
                      </span>
                      <ArrowRight
                        size={13}
                        className="text-gray-300 dark:text-white/20 shrink-0 group-hover:text-gray-400 dark:group-hover:text-gray-400 transition-colors"
                        aria-hidden="true"
                      />
                    </button>

                    {/* Dismiss button */}
                    <button
                      onClick={() => masquer(q.id)}
                      title="Marquer comme traité"
                      className="shrink-0 flex items-center justify-center w-8 h-8 mr-2 rounded-lg text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all"
                    >
                      <X size={13} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {[4, 2].map((rows, i) => (
        <div key={i} className="animate-pulse glass-card rounded-2xl overflow-hidden">
          <div className="px-5 py-2.5 border-b border-gray-200/60 dark:border-white/[0.08] flex items-center justify-between">
            <div className="h-2.5 w-16 bg-gray-200 dark:bg-white/10 rounded" />
            <div className="h-2.5 w-12 bg-purple-100 dark:bg-purple-500/10 rounded" />
          </div>
          <div className="divide-y divide-gray-200/50 dark:divide-white/[0.06]">
            {Array.from({ length: rows }).map((_, j) => (
              <div key={j} className="px-5 py-3 flex items-center gap-3">
                <div className="flex-1">
                  <div className="h-3.5 bg-gray-100 dark:bg-white/[0.07] rounded" style={{ width: `${50 + j * 12}%` }} />
                </div>
                <div className="h-3 w-14 bg-gray-100 dark:bg-white/[0.05] rounded shrink-0" />
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
    <div className="glass-card rounded-2xl flex flex-col items-center gap-2 py-14 text-center">
      <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 mb-1">
        <CheckCircle2 size={16} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
        Aucun angle mort sur cette période
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-500 max-w-xs leading-relaxed">
        Toutes les questions ont pu être traitées depuis les documents disponibles.
      </p>
    </div>
  );
}
