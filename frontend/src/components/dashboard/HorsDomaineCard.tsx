import { useNavigate } from "react-router-dom";
import { BookX, CheckCircle2, ArrowRight } from "lucide-react";

interface HorsDomaineCardProps {
  count: number;
  pct: number;
  loading?: boolean;
}

export default function HorsDomaineCard({ count, pct, loading = false }: HorsDomaineCardProps) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="glass-card rounded-2xl p-5 animate-pulse flex items-center gap-5">
        <div className="w-9 h-9 rounded-xl bg-gray-200 dark:bg-white/10 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-3.5 bg-gray-200 dark:bg-white/10 rounded w-40" />
          <div className="h-3 bg-gray-100 dark:bg-white/5 rounded w-24" />
        </div>
        <div className="h-8 w-16 bg-gray-200 dark:bg-white/10 rounded" />
      </div>
    );
  }

  if (count === 0) {
    return (
      <div className="glass-card rounded-2xl p-5 flex items-center gap-4">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 shrink-0">
          <CheckCircle2 size={16} className="text-emerald-500 dark:text-emerald-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
            Documentation complète
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Toutes les questions de la période ont pu être traitées.
          </p>
        </div>
      </div>
    );
  }

  return (
    <button
      onClick={() => navigate("/angles-morts")}
      className="glass-card rounded-2xl p-5 flex items-center gap-4 w-full text-left hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-purple-50 dark:bg-purple-500/10 shrink-0">
        <BookX size={16} className="text-purple-600 dark:text-purple-400" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
          Sujets non couverts
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Questions sans réponse documentaire cette période
        </p>
      </div>

      <div className="text-right shrink-0">
        <p className="text-2xl font-bold text-purple-600 dark:text-purple-400 tabular-nums leading-none">
          {count}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 tabular-nums">
          {pct}% des tickets
        </p>
      </div>

      <ArrowRight
        size={15}
        className="text-gray-300 dark:text-white/20 shrink-0 group-hover:text-gray-500 dark:group-hover:text-gray-400 group-hover:translate-x-0.5 transition-all duration-100"
      />
    </button>
  );
}
