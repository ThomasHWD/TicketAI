import { Link } from "react-router-dom";
import { BookX, ArrowRight } from "lucide-react";
import { nombreFr } from "../../lib/format";

interface HorsDomaineCardProps {
  count: number;
  pct: number;
  loading?: boolean;
}

export default function HorsDomaineCard({ count, pct, loading = false }: HorsDomaineCardProps) {
  if (loading) {
    return (
      <div className="glass-card rounded-2xl px-4 py-2.5 animate-pulse flex items-center gap-3">
        <div className="w-6 h-6 rounded-lg bg-gray-200 dark:bg-white/10 shrink-0" />
        <div className="h-3.5 w-48 bg-gray-200 dark:bg-white/10 rounded flex-1" />
        <div className="h-6 w-20 bg-gray-100 dark:bg-white/5 rounded-lg shrink-0" />
      </div>
    );
  }

  if (count === 0) return null;

  return (
    <Link
      to="/angles-morts"
      className="glass-card rounded-2xl px-4 py-2.5 flex items-center gap-3 w-full hover:shadow-md transition-shadow group"
      aria-label={`${count} sujet${count > 1 ? "s" : ""} non couvert${count > 1 ? "s" : ""} — voir les angles morts de la base de connaissances`}
      title="Sujets abordés par des tickets mais sans document de référence dans la base de connaissances"
    >
      <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-amber-50 dark:bg-amber-500/10 shrink-0">
        <BookX size={12} className="text-amber-600 dark:text-amber-400" />
      </div>

      <span className="text-sm text-gray-600 dark:text-muted-foreground flex-1 min-w-0">
        <span className="font-semibold text-gray-900 dark:text-gray-100 tabular-nums">{count}</span>
        {" "}sujet{count > 1 ? "s" : ""} non couvert{count > 1 ? "s" : ""} cette période
        <span className="text-muted-foreground ml-1.5 tabular-nums">({nombreFr(pct)} %)</span>
        <span className="block text-[11px] text-muted-foreground mt-0.5">questions sans document correspondant</span>
      </span>

      <span className="shrink-0 flex items-center gap-1 text-xs font-medium text-amber-700 dark:text-amber-400 group-hover:text-amber-700 dark:group-hover:text-amber-300 transition-colors">
        Voir le détail
        <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform duration-100" />
      </span>
    </Link>
  );
}
