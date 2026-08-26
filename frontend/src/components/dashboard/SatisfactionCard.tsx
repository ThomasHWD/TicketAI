import { useId } from "react";
import { SmilePlus } from "lucide-react";
import { STAR_PATH } from "../ui/StarPicker";

interface SatisfactionData {
  avg_qualite: number | null;
  avg_delai: number | null;
  nb_avec_notes: number;
}

interface SatisfactionCardProps {
  data: SatisfactionData | null;
  loading?: boolean;
  onVoirInsatisfaits?: () => void;
}

/**
 * Étoiles fractionnelles via SVG linearGradient.
 * La classe de couleur est posée sur le <svg> pour que currentColor
 * se résolve correctement dans les paths ET dans les stops du gradient.
 */
export function StarRating({ value, size = 15 }: { value: number; size?: number }) {
  const instanceId = useId();
  const full = Math.floor(value);
  const frac = value - full; // 0.0 – 0.99
  const uid = `${instanceId}-sg`;
  const gap = 3;
  const w = 24 * 5 + gap * 4;

  return (
    <svg
      width={(size / 24) * w}
      height={size}
      viewBox={`0 0 ${w} 24`}
      className="text-gray-200 dark:text-gray-700"
      aria-label={`${value.toFixed(1)} sur 5`}
    >
      <defs>
        {/* gradient pour l'étoile partiellement remplie */}
        <linearGradient id={uid} x1="0" x2="1" y1="0" y2="0">
          <stop offset={`${frac * 100}%`} stopColor="#fbbf24" />
          <stop offset={`${frac * 100}%`} stopColor="currentColor" />
        </linearGradient>
      </defs>

      {[0, 1, 2, 3, 4].map((i) => {
        const fill =
          i < full
            ? "#fbbf24"
            : i === full && frac > 0
              ? `url(#${uid})`
              : "currentColor";
        return (
          <path
            key={i}
            d={STAR_PATH}
            fill={fill}
            transform={`translate(${i * (24 + gap)}, 0)`}
          />
        );
      })}
    </svg>
  );
}

/** Métrique compacte pour le bas de la card */
function SubMetric({ label, value }: { label: string; value: number | null }) {
  const pct = value !== null ? Math.round((value / 5) * 100) : 0;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </span>
      {value !== null ? (
        <>
          <div className="flex items-baseline gap-1.5">
            <span className="text-xl font-bold text-gray-800 dark:text-gray-100 leading-none">
              {value.toFixed(1)}
            </span>
            <StarRating value={value} size={12} />
          </div>
          <div className="h-1 rounded-full bg-gray-100 dark:bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-400 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </>
      ) : (
        <span className="text-xl font-bold text-gray-300 dark:text-gray-600">—</span>
      )}
    </div>
  );
}

export default function SatisfactionCard({ data, loading = false, onVoirInsatisfaits }: SatisfactionCardProps) {
  const isEmpty = !data || (data.avg_qualite === null && data.avg_delai === null);

  const globalScore =
    data?.avg_qualite != null && data?.avg_delai != null
      ? (data.avg_qualite + data.avg_delai) / 2
      : (data?.avg_qualite ?? data?.avg_delai ?? null);

  if (loading) {
    return (
      <div className="glass-card h-full p-5 rounded-2xl animate-pulse flex flex-col gap-4">
        <div className="h-4 bg-gray-200 dark:bg-white/10 rounded w-2/5" />
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <div className="h-14 w-20 bg-gray-200 dark:bg-white/10 rounded-xl" />
          <div className="h-4 w-28 bg-gray-200 dark:bg-white/10 rounded" />
        </div>
        <div className="grid grid-cols-2 gap-4 pt-3 border-t border-gray-100 dark:border-white/5">
          <div className="space-y-2">
            <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-3/4" />
            <div className="h-6 bg-gray-200 dark:bg-white/10 rounded w-1/2" />
            <div className="h-1.5 bg-gray-200 dark:bg-white/10 rounded" />
          </div>
          <div className="space-y-2">
            <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-3/4" />
            <div className="h-6 bg-gray-200 dark:bg-white/10 rounded w-1/2" />
            <div className="h-1.5 bg-gray-200 dark:bg-white/10 rounded" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card h-full flex flex-col p-5 rounded-2xl relative overflow-hidden">
      {/* fond décoratif */}
      <div className="absolute inset-0 bg-gradient-to-br from-amber-50/40 via-transparent to-transparent dark:from-amber-900/8 dark:to-transparent pointer-events-none" />

      {/* Header */}
      <div className="relative shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SmilePlus size={15} className="text-amber-500 dark:text-amber-400 shrink-0" />
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
            Satisfaction
          </h3>
        </div>
        {!isEmpty && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {data!.nb_avec_notes} avis
          </span>
        )}
      </div>

      {/* Zone centrale — remplit tout l'espace disponible */}
      <div className="relative flex-1 flex flex-col items-center justify-center py-4 gap-3">
        {isEmpty ? (
          <>
            <svg
              width={28 * 5 + 3 * 4}
              height={28}
              viewBox={`0 0 ${24 * 5 + 3 * 4} 24`}
              className="text-gray-200 dark:text-gray-700"
              aria-hidden="true"
            >
              {[0, 1, 2, 3, 4].map((i) => (
                <path key={i} d={STAR_PATH} fill="currentColor" transform={`translate(${i * 27}, 0)`} />
              ))}
            </svg>
            <p className="text-xs text-gray-400 dark:text-gray-600 text-center max-w-[160px]">
              Aucune évaluation sur cette période
            </p>
          </>
        ) : (
          <>
            <div className="flex flex-col items-center gap-1">
              <div className="flex items-baseline gap-2">
                <span className="text-5xl font-bold text-gray-900 dark:text-gray-100 tracking-tight leading-none tabular-nums">
                  {globalScore!.toFixed(1)}
                </span>
                <span className="text-lg text-gray-500 dark:text-gray-400 font-normal">/&nbsp;5</span>
              </div>
            </div>
            <StarRating value={globalScore!} size={22} />
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              Score moyen
            </span>
          </>
        )}
      </div>

      {/* Métriques individuelles — épinglées en bas */}
      {!isEmpty && (
        <div className="relative shrink-0 border-t border-gray-100 dark:border-white/8 pt-4 grid grid-cols-2 gap-4 divide-x divide-gray-100 dark:divide-white/8">
          <SubMetric label="Qualité réponse" value={data!.avg_qualite} />
          <div className="pl-4">
            <SubMetric label="Rapidité" value={data!.avg_delai} />
          </div>
        </div>
      )}

      {/* Bouton tickets insatisfaits */}
      {!isEmpty && onVoirInsatisfaits && (
        <button
          onClick={onVoirInsatisfaits}
          className="relative mt-3 w-full text-xs font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors text-center py-1.5 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-900/20"
        >
          Voir les tickets insatisfaits →
        </button>
      )}
    </div>
  );
}
