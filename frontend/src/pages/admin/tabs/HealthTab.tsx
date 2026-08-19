import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { getServicesHealth, type ServiceHealth } from "../../../lib/api";

type InfraKey =
  | "postgres" | "qdrant" | "valkey"
  | "albert_embeddings" | "albert_llm" | "albert_reranker"
  | "celery_ingestion" | "celery_questions" | "celery_beat";

const INFRA_SERVICES: { key: InfraKey; label: string }[] = [
  { key: "postgres",          label: "PostgreSQL" },
  { key: "qdrant",            label: "Qdrant" },
  { key: "valkey",            label: "Valkey" },
  { key: "albert_embeddings", label: "Albert — Embeddings" },
  { key: "albert_llm",        label: "Albert — LLM" },
  { key: "albert_reranker",   label: "Albert — Reranker" },
  { key: "celery_ingestion",  label: "Celery — Ingestion" },
  { key: "celery_questions",  label: "Celery — Questions" },
  { key: "celery_beat",       label: "Celery — Clôture auto" },
];

function ServiceRow({ svc, label }: { svc: ServiceHealth; label: string }) {
  const ok = svc.status === "ok";
  return (
    <li
      title={svc.detail ?? undefined}
      className="flex items-center gap-3 py-2.5 border-b border-gray-100 dark:border-white/[0.06] last:border-0"
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      <span className="flex-1 text-sm text-gray-700 dark:text-gray-200">{label}</span>
      {svc.latency_ms != null && ok && (
        <span className="font-mono text-xs text-gray-400 dark:text-gray-500 tabular-nums">
          {svc.latency_ms} ms
        </span>
      )}
      <span className={`text-xs font-medium min-w-[3rem] text-right ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
        {ok ? "OK" : "Erreur"}
      </span>
    </li>
  );
}

function MetricChip({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | number | null;
  mono?: boolean;
}) {
  return (
    <div className="glass-card rounded-xl px-4 py-3.5">
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`mt-1 text-sm font-semibold text-gray-900 dark:text-gray-50 tabular-nums ${mono ? "font-mono" : ""}`}>
        {value ?? "—"}
      </p>
    </div>
  );
}

function PipelineRow({
  label,
  value,
  warn = false,
  danger = false,
}: {
  label: string;
  value: number | null;
  warn?: boolean;
  danger?: boolean;
}) {
  const valueClass = danger
    ? "text-red-600 dark:text-red-400"
    : warn
    ? "text-amber-600 dark:text-amber-400"
    : "text-gray-700 dark:text-gray-200";

  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-white/[0.06] last:border-0">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className={`font-mono text-sm font-medium tabular-nums ${valueClass}`}>
        {value ?? "—"}
      </span>
    </div>
  );
}

export default function HealthTab({ onGoIncidents }: { onGoIncidents: () => void }) {
  const { data: health, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-health"],
    queryFn: getServicesHealth,
    retry: 1,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });

  const stats = health?.stats;

  const derniereActivite = stats?.derniere_activite
    ? new Date(stats.derniere_activite).toLocaleString("fr-FR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  const hasAlert =
    (stats?.tickets_echoues ?? 0) > 0 ||
    (stats?.tickets_bloques ?? 0) > 0 ||
    (stats?.documents_echoues ?? 0) > 0;

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400 dark:text-gray-500">
          {isFetching ? "Actualisation…" : health ? "Données en temps réel" : ""}
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors duration-150 disabled:opacity-40"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
          Actualiser
        </button>
      </div>

      {/* Alert banner */}
      {!isLoading && hasAlert && (
        <div className="flex items-start gap-2.5 rounded-xl border border-amber-200 dark:border-amber-500/25 bg-amber-50 dark:bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          <AlertTriangle size={14} className="shrink-0 mt-0.5 text-amber-500" aria-hidden="true" />
          <span className="flex-1 leading-snug">
            {[
              (stats!.tickets_echoues ?? 0) > 0 &&
                `${stats!.tickets_echoues} ticket${stats!.tickets_echoues > 1 ? "s" : ""} échoué${stats!.tickets_echoues > 1 ? "s" : ""}`,
              (stats!.tickets_bloques ?? 0) > 0 &&
                `${stats!.tickets_bloques} ticket${stats!.tickets_bloques > 1 ? "s" : ""} bloqué${stats!.tickets_bloques > 1 ? "s" : ""}`,
              (stats!.documents_echoues ?? 0) > 0 &&
                `${stats!.documents_echoues} document${stats!.documents_echoues > 1 ? "s" : ""} échoué${stats!.documents_echoues > 1 ? "s" : ""}`,
            ]
              .filter(Boolean)
              .join(" · ")}
            {" — "}
            <button
              onClick={onGoIncidents}
              className="underline underline-offset-2 font-semibold hover:opacity-75 transition-opacity"
            >
              Voir les incidents
            </button>
          </span>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-20 text-gray-400">
          <Loader2 size={16} className="animate-spin" aria-hidden="true" />
          <span className="text-sm">Chargement…</span>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Metric chips */}
          <div className="grid grid-cols-3 gap-4">
            <MetricChip label="Documents indexés" value={stats?.nb_documents ?? null} mono />
            <MetricChip label="Réponses canoniques" value={stats?.nb_reponses_validees ?? null} mono />
            <MetricChip label="Dernière activité" value={derniereActivite} />
          </div>

          {/* Services + Pipeline */}
          <div className="grid grid-cols-2 gap-4">
            {/* Infrastructure */}
            <div className="glass-card rounded-2xl px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 pb-2">
                Infrastructure
              </p>
              <ul>
                {INFRA_SERVICES.map(({ key, label }) =>
                  health ? <ServiceRow key={key} svc={health[key]} label={label} /> : null
                )}
              </ul>
            </div>

            {/* Pipeline */}
            <div className="glass-card rounded-2xl px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 pb-2">
                Pipeline
              </p>

              {/* Incidents */}
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-300 dark:text-white/20 pt-1 pb-0.5">
                Incidents
              </p>
              <PipelineRow
                label="Tickets échoués"
                value={stats?.tickets_echoues ?? null}
                danger={(stats?.tickets_echoues ?? 0) > 0}
              />
              <PipelineRow
                label="Documents échoués"
                value={stats?.documents_echoues ?? null}
                danger={(stats?.documents_echoues ?? 0) > 0}
              />
              <PipelineRow
                label="Tickets bloqués"
                value={stats?.tickets_bloques ?? null}
                warn={(stats?.tickets_bloques ?? 0) > 0}
              />
              <PipelineRow
                label="Réponses à relire"
                value={stats?.reponses_a_relire ?? null}
                warn={(stats?.reponses_a_relire ?? 0) > 0}
              />

              {/* Capacité */}
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-300 dark:text-white/20 pt-4 pb-0.5">
                Capacité
              </p>
              <PipelineRow
                label="File ingestion"
                value={stats?.celery_pending_ingestion ?? null}
                warn={(stats?.celery_pending_ingestion ?? 0) > 5}
              />
              <PipelineRow
                label="File questions"
                value={stats?.celery_pending_questions ?? null}
                warn={(stats?.celery_pending_questions ?? 0) > 10}
              />
              <PipelineRow
                label="Workers ingestion"
                value={stats?.celery_workers_ingestion ?? null}
                danger={(stats?.celery_workers_ingestion ?? 1) === 0}
              />
              <PipelineRow
                label="Workers questions"
                value={stats?.celery_workers_questions ?? null}
                danger={(stats?.celery_workers_questions ?? 1) === 0}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
