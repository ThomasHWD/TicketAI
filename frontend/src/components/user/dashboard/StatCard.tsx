type StatColor = "gray" | "emerald" | "blue";

const STAT_COLORS: Record<StatColor, { ring: string; bg: string; icon: string; value: string }> = {
  gray:    { ring: "",                                                    bg: "bg-gray-100 dark:bg-white/[0.08]",     icon: "text-gray-500 dark:text-gray-400",       value: "text-gray-800 dark:text-gray-100" },
  emerald: { ring: "ring-1 ring-emerald-300/60 dark:ring-emerald-500/25", bg: "bg-emerald-50 dark:bg-emerald-500/15", icon: "text-emerald-600 dark:text-emerald-400",  value: "text-emerald-700 dark:text-emerald-300" },
  blue:    { ring: "ring-1 ring-blue-200/60 dark:ring-blue-500/20",       bg: "bg-blue-50 dark:bg-blue-500/10",       icon: "text-blue-600 dark:text-blue-400",        value: "text-blue-700 dark:text-blue-300" },
};

export function UserStatCard({
  icon: Icon,
  label,
  labelTitle,
  subtext,
  value,
  color = "gray",
  activeColor,
}: {
  icon: React.ElementType;
  label: string;
  labelTitle?: string;
  subtext?: string;
  value: number | undefined;
  color?: StatColor;
  activeColor?: StatColor;
}) {
  const resolved: StatColor =
    activeColor && typeof value === "number" && value > 0 ? activeColor : color;
  const theme = STAT_COLORS[resolved];

  return (
    <div className={`glass-card rounded-2xl p-5 flex items-center gap-4 ${theme.ring}`}>
      <div className={`shrink-0 p-3 rounded-xl ${theme.bg}`}>
        <Icon size={20} className={theme.icon} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-[0.06em] truncate" title={labelTitle}>
          {label}
        </p>
        <p className={`text-2xl font-semibold mt-0.5 ${theme.value}`}>
          {value === undefined ? (
            <span className="inline-block w-8 h-6 bg-gray-200 dark:bg-white/10 animate-pulse rounded" aria-label="chargement" />
          ) : value}
        </p>
        {subtext && <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 leading-none">{subtext}</p>}
      </div>
    </div>
  );
}
