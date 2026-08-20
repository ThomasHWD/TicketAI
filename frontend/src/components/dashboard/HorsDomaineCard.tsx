import { useNavigate } from "react-router-dom";
import { BookX, ArrowRight } from "lucide-react";

interface HorsDomaineCardProps {
  count: number;
  pct: number;
  loading?: boolean;
}

export default function HorsDomaineCard({ count, pct, loading = false }: HorsDomaineCardProps) {
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="glass-card rounded-xl px-4 py-2.5 animate-pulse flex items-center gap-3">
        <div className="w-6 h-6 rounded-lg bg-gray-200 dark:bg-white/10 shrink-0" />
        <div className="h-3.5 w-48 bg-gray-200 dark:bg-white/10 rounded flex-1" />
        <div className="h-6 w-20 bg-gray-100 dark:bg-white/5 rounded-lg shrink-0" />
      </div>
    );
  }

  if (count === 0) return null;

  return (
    <button
      onClick={() => navigate("/angles-morts")}
      className="glass-card rounded-xl px-4 py-2.5 flex items-center gap-3 w-full text-left hover:shadow-md transition-shadow group"
    >
      <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-purple-50 dark:bg-purple-500/10 shrink-0">
        <BookX size={12} className="text-purple-600 dark:text-purple-400" />
      </div>

      <span className="text-sm text-gray-600 dark:text-gray-400 flex-1 min-w-0">
        <span className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">{count}</span>
        {" "}sujet{count > 1 ? "s" : ""} non couvert{count > 1 ? "s" : ""} cette période
        <span className="text-gray-400 dark:text-gray-500 ml-1.5 tabular-nums">({pct}%)</span>
      </span>

      <span className="shrink-0 flex items-center gap-1 text-xs font-medium text-purple-600 dark:text-purple-400 group-hover:text-purple-700 dark:group-hover:text-purple-300 transition-colors">
        Voir le détail
        <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform duration-100" />
      </span>
    </button>
  );
}
