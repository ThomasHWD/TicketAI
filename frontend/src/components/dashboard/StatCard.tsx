import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface StatCardProps {
  title: string;
  value: number;
  variation: number;
  hausse: boolean;
  icon: React.ElementType;
  iconColor?: string;
  iconBg?: string;
  loading?: boolean;
  suffix?: string;
  subtitle?: string;
  variationUnit?: string;
  formatter?: (value: number) => string;
  positiveIsUp?: boolean;
  featured?: boolean;
}

export default function StatCard({
  title,
  value,
  variation,
  hausse,
  icon: Icon,
  iconColor = "text-emerald-500",
  iconBg,
  loading = false,
  suffix = "",
  subtitle,
  variationUnit = "%",
  formatter,
  positiveIsUp = true,
  featured = false,
}: StatCardProps) {
  if (loading) {
    return (
      <div className="glass-card p-4 rounded-2xl animate-pulse space-y-3">
        <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-2/3" />
        <div className="h-7 bg-gray-200 dark:bg-white/10 rounded w-3/5" />
        <div className="flex items-center justify-between mt-auto">
          <div className="w-7 h-7 bg-gray-200 dark:bg-white/10 rounded-lg" />
          <div className="h-4 w-12 bg-gray-200 dark:bg-white/10 rounded-full" />
        </div>
      </div>
    );
  }

  const isNeutral = variation === 0;
  const TrendIcon = isNeutral ? Minus : hausse ? TrendingUp : TrendingDown;
  const isGood = positiveIsUp ? hausse : !hausse;
  const trendColor = isNeutral
    ? "text-gray-400 dark:text-gray-500"
    : isGood
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-500 dark:text-red-400";
  const trendBg = isNeutral
    ? "bg-gray-100 dark:bg-white/8"
    : isGood
      ? "bg-emerald-50 dark:bg-emerald-400/12"
      : "bg-red-50 dark:bg-red-400/12";

  const displayValue = formatter
    ? formatter(value)
    : value.toLocaleString("fr-FR");
  const subtitleId = subtitle ? `sc-sub-${title.replace(/\s+/g, "-").toLowerCase()}` : undefined;

  return (
    <div className={`glass-card p-4 rounded-2xl flex flex-col gap-2.5 ${featured ? "ring-1 ring-amber-300/50 dark:ring-amber-500/25" : ""}`}>
      {/* Label — en haut pour contextualiser le chiffre immédiatement */}
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider leading-none">
        {title}
      </p>

      {/* Valeur */}
      <div>
        <div
          aria-describedby={subtitleId}
          className={`font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100 leading-none ${featured ? "text-3xl" : formatter ? "text-xl" : "text-2xl"}`}
        >
          {displayValue}
          {!formatter && suffix && (
            <span className="text-base font-normal text-gray-400 dark:text-gray-500 ml-0.5">{suffix}</span>
          )}
        </div>
        {subtitle && (
          <p id={subtitleId} className="text-[11px] text-gray-400 dark:text-gray-500 mt-1 leading-none">{subtitle}</p>
        )}
      </div>

      {/* Icône + tendance — épinglés en bas */}
      <div className="flex items-center justify-between mt-auto">
        <div className={`w-7 h-7 flex items-center justify-center rounded-lg ${iconBg ?? "bg-gray-50 dark:bg-white/8"} ${iconColor}`}>
          <Icon size={14} />
        </div>
        <div
          className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold tabular-nums ${trendBg} ${trendColor}`}
          title={!isNeutral && !positiveIsUp ? (isGood ? "Amélioration" : "Dégradation") : undefined}
        >
          <TrendIcon size={9} />
          <span>
            {isNeutral
              ? "Stable"
              : `${variation > 0 ? "+" : ""}${variation}${variationUnit}`}
          </span>
        </div>
      </div>
    </div>
  );
}
