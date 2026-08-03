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
}: StatCardProps) {
  if (loading) {
    return (
      <div className="glass-card p-5 rounded-2xl space-y-3 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-white/10 rounded w-2/3" />
        <div className="h-8 bg-gray-200 dark:bg-white/10 rounded w-1/2" />
        <div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-1/3" />
      </div>
    );
  }

  const isNeutral = variation === 0;
  const TrendIcon = isNeutral ? Minus : hausse ? TrendingUp : TrendingDown;
  const trendColor = isNeutral
    ? "text-gray-400"
    : hausse
      ? "text-emerald-500"
      : "text-red-500";
  const trendBg = isNeutral
    ? "bg-gray-100 dark:bg-white/5"
    : hausse
      ? "bg-emerald-50 dark:bg-emerald-400/10"
      : "bg-red-50 dark:bg-red-400/10";

  return (
    <div className="glass-card p-5 rounded-2xl space-y-3 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-600 dark:text-gray-400">{title}</span>
        <span className={`p-2 rounded-xl bg-gray-50 dark:bg-white/5 ${iconColor}`}>
          <Icon size={16} />
        </span>
      </div>
      <div className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">
        {value.toLocaleString("fr-FR")}
        {suffix && <span className="text-lg font-normal text-gray-500 ml-1">{suffix}</span>}
      </div>
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${trendBg} ${trendColor}`}>
        <TrendIcon size={12} />
        <span>
          {isNeutral ? "Stable" : `${variation > 0 ? "+" : ""}${variation}%`}
          {!isNeutral && <span className="text-gray-500 dark:text-gray-400 font-normal ml-1">vs période préc.</span>}
        </span>
      </div>
    </div>
  );
}
