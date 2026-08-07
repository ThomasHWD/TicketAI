import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Loader2, AlertTriangle } from "lucide-react";
import { getServicesHealth, type ServiceHealth } from "../../../lib/api";

type InfraKey =
  | "postgres" | "qdrant" | "valkey"
  | "albert_embeddings" | "albert_llm" | "albert_reranker"
  | "celery_ingestion" | "celery_questions";

const INFRA_SERVICES: { key: InfraKey; label: string }[] = [
  { key: "postgres",          label: "PostgreSQL" },
  { key: "qdrant",            label: "Qdrant" },
  { key: "valkey",            label: "Valkey" },
  { key: "albert_embeddings", label: "Albert — Embeddings" },
  { key: "albert_llm",        label: "Albert — LLM" },
  { key: "albert_reranker",   label: "Albert — Reranker" },
  { key: "celery_ingestion",  label: "Celery — Ingestion" },
  { key: "celery_questions",  label: "Celery — Questions" },
];

function ServiceRow({ svc, label }: { svc: ServiceHealth; label: string }) {
  const ok = svc.status === "ok";
  return (
    <li
      title={svc.detail ?? undefined}
      className="flex items-center gap-2.5 py-2 border-b border-gray-100 dark:border-white/10 last:border-0"
    >
      <span className={`size-1.5 rounded-full shrink-0 ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
      <span className="text-sm text-gray-700 dark:text-gray-200 flex-1">{label}</span>
      {svc.latency_ms != null && ok && (
        <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
          {svc.latency_ms}ms
        </span>
      )}
      <span className={`text-xs font-medium tabular-nums ${ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"}`}>
        {ok ? "OK" : "Erreur"}
      </span>
    </li>
  );
}

function StatRow({ label, value, warn }: { label: string; value: string | number | null; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-white/10 last:border-0">
      <span className="text-sm text-gray-600 dark:text-gray-300">{label}</span>
      <span className={`text-sm font-medium tabular-nums ${warn ? "text-amber-600 dark:text-amber-400" : "text-gray-800 dark:text-gray-100"}`}>
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
    ? new Date(stats.derniere_activite).toLocaleString("fr-FR")
    : null;
  const hasAlert =
    (stats?.tickets_echoues ?? 0) > 0 ||
    (stats?.tickets_bloques ?? 0) > 0 ||
    (stats?.documents_echoues ?? 0) > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-white/70 drop-shadow">
          {isFetching ? "Actualisation…" : health ? "Données en temps réel" : ""}
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-white/80 hover:text-white transition-colors disabled:opacity-40 drop-shadow"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          Actualiser
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-gray-400 text-sm py-8 justify-center">
          <Loader2 size={15} className="animate-spin" /> Chargement…
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-6">
          <div className="glass-card rounded-2xl px-5 py-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Infrastructure</p>
            <ul>
              {health && INFRA_SERVICES.map(({ key, label }) => (
                <ServiceRow key={key} svc={health[key]} label={label} />
              ))}
            </ul>
          </div>

          <div className="space-y-4">
            <div className="glass-card rounded-2xl px-5 py-4">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Base de données</p>
              <StatRow label="Documents indexés" value={stats?.nb_documents ?? null} />
              <StatRow label="Réponses validées" value={stats?.nb_reponses_validees ?? null} />
              <StatRow label="Dernière activité" value={derniereActivite} />
            </div>

            <div className="glass-card rounded-2xl px-5 py-4">
              <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Pipeline</p>
              <StatRow label="Tickets échoués"  value={stats?.tickets_echoues ?? null}  warn={(stats?.tickets_echoues ?? 0) > 0} />
              <StatRow label="Documents échoués" value={stats?.documents_echoues ?? null} warn={(stats?.documents_echoues ?? 0) > 0} />
              <StatRow label="Tickets bloqués"  value={stats?.tickets_bloques ?? null}  warn={(stats?.tickets_bloques ?? 0) > 0} />
              <StatRow
                label="File ingestion"
                value={stats?.celery_pending_ingestion != null ? `${stats.celery_pending_ingestion} tâche(s)` : null}
                warn={(stats?.celery_pending_ingestion ?? 0) > 5}
              />
              <StatRow
                label="File questions"
                value={stats?.celery_pending_questions != null ? `${stats.celery_pending_questions} tâche(s)` : null}
                warn={(stats?.celery_pending_questions ?? 0) > 10}
              />
              <StatRow
                label="Workers ingestion"
                value={stats?.celery_workers_ingestion != null ? `${stats.celery_workers_ingestion} worker(s)` : null}
                warn={(stats?.celery_workers_ingestion ?? 0) === 0}
              />
              <StatRow
                label="Workers questions"
                value={stats?.celery_workers_questions != null ? `${stats.celery_workers_questions} worker(s)` : null}
                warn={(stats?.celery_workers_questions ?? 0) === 0}
              />
            </div>

            {hasAlert && (
              <div className="flex items-start gap-2 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3.5 py-2.5 text-sm text-amber-700 dark:text-amber-300">
                <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                <span className="flex-1">
                  {[
                    stats!.tickets_echoues > 0 && `${stats!.tickets_echoues} ticket(s) échoué(s)`,
                    stats!.tickets_bloques > 0 && `${stats!.tickets_bloques} ticket(s) bloqué(s) > 10 min`,
                    stats!.documents_echoues > 0 && `${stats!.documents_echoues} document(s) échoué(s)`,
                  ].filter(Boolean).join(" · ")}
                  {" — "}
                  <button
                    onClick={onGoIncidents}
                    className="underline underline-offset-2 hover:opacity-75 font-medium"
                  >
                    Voir les incidents
                  </button>
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
