import { Loader2, RefreshCw } from "lucide-react";
import type { AlbertModelUsage } from "../../lib/api";
import { MetricBar, formatTokens, cleanModelName } from "./HealthComponents";

function ModelQuotaRow({
  model, limiteRpd, limiteTpd,
}: {
  model: AlbertModelUsage;
  limiteRpd: number | null;
  limiteTpd: number | null;
}) {
  const pctReq = limiteRpd ? Math.min((model.requetes_aujourd_hui / limiteRpd) * 100, 100) : 0;
  const pctTok = limiteTpd ? Math.min((model.tokens_aujourd_hui / limiteTpd) * 100, 100) : 0;
  const maxPct = Math.max(pctReq, pctTok);

  const dotClass    = maxPct >= 80 ? "bg-red-500"    : maxPct >= 60 ? "bg-amber-400"    : "bg-emerald-500";
  const reqBarClass = pctReq >= 80 ? "bg-red-500"    : pctReq >= 60 ? "bg-amber-400"    : "bg-emerald-500";
  const tokBarClass = pctTok >= 80 ? "bg-red-500"    : pctTok >= 60 ? "bg-amber-400"    : "bg-emerald-500";
  const reqValueClass = pctReq >= 80 ? "text-red-600 dark:text-red-400" : pctReq >= 60 ? "text-amber-600 dark:text-amber-400" : "text-gray-700 dark:text-gray-200";
  const tokValueClass = pctTok >= 80 ? "text-red-600 dark:text-red-400" : pctTok >= 60 ? "text-amber-600 dark:text-amber-400" : "text-gray-700 dark:text-gray-200";

  return (
    <li className="flex items-center gap-3 py-3 border-b border-gray-100 dark:border-white/[0.06] last:border-0">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-0.5 self-start ${dotClass}`} />
      <span className="text-sm text-gray-700 dark:text-gray-200 flex-1 min-w-0 truncate self-center">
        {cleanModelName(model.nom)}
      </span>
      <div className="shrink-0 w-36">
        <MetricBar pct={pctReq} value={model.requetes_aujourd_hui} limit={limiteRpd} barClass={reqBarClass} valueClass={reqValueClass} />
      </div>
      <div className="w-px self-stretch bg-gray-200 dark:bg-white/[0.06] shrink-0" />
      <div className="shrink-0 w-36">
        <MetricBar pct={pctTok} value={model.tokens_aujourd_hui} limit={limiteTpd} formatValue={(v) => formatTokens(Number(v))} barClass={tokBarClass} valueClass={tokValueClass} />
      </div>
    </li>
  );
}

interface AlbertQuotasCardProps {
  quotas: { modeles: AlbertModelUsage[]; limite_rpd: number | null; limite_tpd: number | null } | undefined;
  isFetching: boolean;
  onRefresh: () => void;
}

export function AlbertQuotasCard({ quotas, isFetching, onRefresh }: AlbertQuotasCardProps) {
  return (
    <div className="glass-card rounded-2xl px-5 py-4">
      <div className="flex items-center justify-between pb-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Quotas Albert — aujourd'hui
        </p>
        <button
          onClick={onRefresh}
          disabled={isFetching}
          aria-label="Actualiser les quotas Albert"
          className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors duration-150 disabled:opacity-40"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
          Actualiser
        </button>
      </div>

      {isFetching && !quotas ? (
        <div className="flex items-center gap-2 py-4 text-gray-400">
          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          <span className="text-xs">Chargement…</span>
        </div>
      ) : quotas && quotas.modeles.length > 0 ? (
        <>
          <div className="flex items-center gap-3 pb-2 border-b border-gray-100 dark:border-white/[0.06]">
            <span className="w-1.5 shrink-0" />
            <span className="flex-1 text-xs font-medium text-gray-400 dark:text-gray-500">Modèle</span>
            <div className="shrink-0 w-36">
              <p className="text-xs font-medium text-gray-400 dark:text-gray-500">Requêtes / jour</p>
              {quotas.limite_rpd != null && (
                <p className="text-[10px] text-gray-300 dark:text-gray-600">max {quotas.limite_rpd}</p>
              )}
            </div>
            <div className="w-px self-stretch bg-gray-200 dark:bg-white/[0.06] shrink-0" />
            <div className="shrink-0 w-36">
              <p className="text-xs font-medium text-gray-400 dark:text-gray-500">Jetons / jour</p>
              {quotas.limite_tpd != null && (
                <p className="text-[10px] text-gray-300 dark:text-gray-600">max {formatTokens(quotas.limite_tpd)}</p>
              )}
            </div>
          </div>
          <ul>
            {quotas.modeles.map((m) => (
              <ModelQuotaRow key={m.nom} model={m} limiteRpd={quotas.limite_rpd} limiteTpd={quotas.limite_tpd} />
            ))}
          </ul>
        </>
      ) : (
        <p className="text-xs text-gray-400 dark:text-gray-500 py-3">
          {quotas ? "Aucune activité aujourd'hui." : "Données indisponibles."}
        </p>
      )}
    </div>
  );
}
