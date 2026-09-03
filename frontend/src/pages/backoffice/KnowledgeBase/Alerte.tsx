import { AlertTriangle } from "lucide-react";

export const BTN_ALERTE_PRIMAIRE =
  "inline-flex items-center gap-1.5 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100";
export const BTN_ALERTE_SECONDAIRE =
  "inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white/70 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:border-white/15 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10";
export const BTN_ALERTE_DISCRET =
  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 dark:text-gray-400 dark:hover:bg-white/10";

export function Alerte({
  ton,
  icon: Icon,
  titre,
  children,
  actions,
}: {
  ton: "ambre" | "rouge";
  icon: typeof AlertTriangle;
  titre: string;
  children: React.ReactNode;
  actions: React.ReactNode;
}) {
  const ambre = ton === "ambre";
  return (
    <div
      role="alert"
      className={`space-y-2.5 rounded-xl border px-4 py-3.5 ${
        ambre
          ? "border-amber-200 bg-amber-50/60 dark:border-amber-500/25 dark:bg-amber-500/[0.07]"
          : "border-red-200 bg-red-50/60 dark:border-red-500/25 dark:bg-red-500/10"
      }`}
    >
      <p
        className={`flex items-center gap-2 text-sm font-semibold ${
          ambre ? "text-amber-800 dark:text-amber-300" : "text-red-700 dark:text-red-400"
        }`}
      >
        <Icon size={15} className="shrink-0" aria-hidden="true" />
        {titre}
      </p>
      <p
        className={`text-xs leading-relaxed ${
          ambre ? "text-amber-900/80 dark:text-amber-200/80" : "text-red-700/80 dark:text-red-300/80"
        }`}
      >
        {children}
      </p>
      <div className="flex flex-wrap items-center gap-2 pt-0.5">{actions}</div>
    </div>
  );
}
