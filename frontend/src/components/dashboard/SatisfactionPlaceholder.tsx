import { SmilePlus, Sparkles } from "lucide-react";

export default function SatisfactionPlaceholder() {
  return (
    <div className="glass-card p-5 rounded-2xl flex flex-col items-center justify-center gap-4 min-h-[180px] border border-dashed border-gray-200 dark:border-white/10 relative overflow-hidden">
      {/* Fond décoratif */}
      <div className="absolute inset-0 bg-gradient-to-br from-emerald-50/40 to-transparent dark:from-emerald-900/10 dark:to-transparent pointer-events-none" />

      <div className="relative flex flex-col items-center gap-3 text-center">
        <div className="p-3 rounded-2xl bg-emerald-100 dark:bg-emerald-900/30">
          <SmilePlus size={24} className="text-emerald-600 dark:text-emerald-400" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            Satisfaction utilisateurs
          </h3>
          <p className="text-xs text-muted-foreground mt-1 max-w-xs">
            Le suivi de la satisfaction sera disponible prochainement.
          </p>
        </div>
        <span className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
          <Sparkles size={11} />
          Coming soon
        </span>
      </div>
    </div>
  );
}
