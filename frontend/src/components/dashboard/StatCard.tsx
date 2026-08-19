import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface StatCardProps {
  title: string;
  value: number;
  variation: number;
  hausse: boolean;
  icon: React.ElementType;
  iconColor?: string;
  loading?: boolean;
  suffix?: string;
  subtitle?: string;
  variationUnit?: string;
  formatter?: (value: number) => string;
}

export default function StatCard({
  title,
  value,
  variation,
  hausse,
  icon: Icon,
  iconColor = "text-emerald-500",
  loading = false,
  suffix = "",
  subtitle,
  variationUnit = "%",
  formatter,
}: StatCardProps) {
  if (loading) {
    return (
      <div className="glass-card p-4 rounded-xl animate-pulse space-y-3">
        <div className="flex items-center justify-between">
          <div className="w-7 h-7 bg-gray-200 dark:bg-white/10 rounded-lg" />
          <div className="h-4 w-12 bg-gray-200 dark:bg-white/10 rounded-full" />
        </div>
        <div className="h-7 bg-gray-200 dark:bg-white/10 rounded w-3/5" />
        <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-2/3" />
      </div>
    );
  }

  const isNeutral = variation === 0;
  const TrendIcon = isNeutral ? Minus : hausse ? TrendingUp : TrendingDown;
  const trendColor = isNeutral
    ? "text-gray-400 dark:text-gray-500"
    : hausse
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-500 dark:text-red-400";
  const trendBg = isNeutral
    ? "bg-gray-100 dark:bg-white/8"
    : hausse
      ? "bg-emerald-50 dark:bg-emerald-400/12"
      : "bg-red-50 dark:bg-red-400/12";

  const displayValue = formatter
    ? formatter(value)
    : value.toLocaleString("fr-FR");

  return (
    <div className="glass-card p-4 rounded-xl flex flex-col gap-3">
      {/* Icon + trend */}
      <div className="flex items-center justify-between">
        <div className={`w-7 h-7 flex items-center justify-center rounded-lg bg-gray-50 dark:bg-white/8 ${iconColor}`}>
          <Icon size={14} />
        </div>
        <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold tabular-nums ${trendBg} ${trendColor}`}>
          <TrendIcon size={9} />
          <span>
            {isNeutral
              ? "Stable"
              : `${variation > 0 ? "+" : ""}${variation}${variationUnit}`}
          </span>
        </div>
      </div>

      {/* Value */}
      <div>
        <div className={`font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100 leading-none ${formatter ? "text-xl" : "text-2xl"}`}>
          {displayValue}
          {!formatter && suffix && (
            <span className="text-base font-normal text-gray-400 dark:text-gray-500 ml-0.5">{suffix}</span>
          )}
        </div>
        {subtitle && (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1 leading-none">{subtitle}</p>
        )}
      </div>

      {/* Label */}
      <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider leading-none mt-auto">
        {title}
      </p>
    </div>
  );
}
