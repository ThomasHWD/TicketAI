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

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">

      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="glass-card rounded-2xl px-6 py-5 flex items-start justify-between gap-6 flex-wrap">
        <div className="flex items-start gap-3.5">
          <div>
            <h1 className="text-base font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
              Angles morts documentaires
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              Questions que vos documents ne permettent pas encore de traiter.
            </p>
          </div>
        </div>

        {/* Period selector */}
        <div className="flex items-center gap-0.5 p-1 rounded-xl bg-gray-100/80 dark:bg-white/[0.07] border border-gray-200/50 dark:border-white/[0.06] shrink-0">
          {PERIODES.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriode(p.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 ${
                periode === p.value
                  ? "bg-white dark:bg-white/15 text-gray-900 dark:text-gray-100 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Content ─────────────────────────────────────────────────────── */}
      {isLoading ? (
        <SkeletonList />
      ) : data.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          {/* Domain cards */}
          <div className="space-y-3">
            {data.map((entry) => (
              <div key={entry.domaine} className="glass-card rounded-2xl overflow-hidden">

                {/* Domain header */}
                <div className="px-5 py-3.5 border-b border-gray-200/60 dark:border-white/[0.08] flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-gray-800 dark:text-gray-100 tracking-tight">
                    {entry.domaine}
                  </span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 dark:bg-purple-500/15 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-purple-500/20 tabular-nums shrink-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-500 dark:bg-purple-400" aria-hidden="true" />
                    {entry.nb_tickets} ticket{entry.nb_tickets > 1 ? "s" : ""}
                  </span>
                </div>

                {/* Question rows */}
                <ul className="divide-y divide-gray-200/50 dark:divide-white/[0.06]">
                  {entry.questions.map((q) => (
                    <li key={q.id} className="group flex items-stretch">
                      <button
                        onClick={() => navigate(`/tickets/${q.id}`)}
                        className="flex-1 min-w-0 flex items-center gap-4 pl-5 pr-3 py-3.5 text-left hover:bg-gray-50/70 dark:hover:bg-white/[0.04] transition-colors duration-75"
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

                      {/* Dismiss */}
                      <button
                        onClick={() => masquer(q.id)}
                        title="Marquer comme traité"
                        className="shrink-0 flex items-center justify-center w-10 border-l border-gray-100 dark:border-white/[0.05] text-gray-300 dark:text-white/20 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all duration-100"
                      >
                        <X size={13} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="space-y-3">
      {[
        { rows: 4, widths: [72, 58, 85, 64] },
        { rows: 2, widths: [55, 78] },
      ].map(({ rows, widths }, i) => (
        <div key={i} className="animate-pulse glass-card rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-gray-200/60 dark:border-white/[0.08] flex items-center justify-between">
            <div className="h-3.5 w-20 bg-gray-200 dark:bg-white/10 rounded" />
            <div className="h-5 w-20 bg-purple-100 dark:bg-purple-500/10 rounded-full" />
          </div>
          <div className="divide-y divide-gray-200/50 dark:divide-white/[0.06]">
            {Array.from({ length: rows }).map((_, j) => (
              <div key={j} className="px-5 py-3.5 flex items-center gap-4">
                <div className="flex-1 space-y-1.5">
                  <div
                    className="h-3.5 bg-gray-100 dark:bg-white/[0.07] rounded"
                    style={{ width: `${widths[j]}%` }}
                  />
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
    <div className="glass-card rounded-2xl flex flex-col items-center gap-3 py-16 text-center px-8">
      <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10 mb-1">
        <CheckCircle2 size={22} className="text-emerald-500 dark:text-emerald-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Aucun angle mort sur cette période
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5 max-w-xs mx-auto leading-relaxed">
          Toutes les questions ont pu être traitées depuis les documents disponibles.
        </p>
      </div>
    </div>
  );
}
