import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, ClipboardList } from "lucide-react";

interface QueueHeroProps {
  pendingCount: number;
  assignedCount: number;
  pendingLoading: boolean;
  pendingError: boolean;
  filterDomaine: string | undefined;
  assignedColorClass: (n: number) => string;
  onRetry: () => void;
}

export function QueueHero({
  pendingCount, assignedCount,
  pendingLoading, pendingError,
  filterDomaine, assignedColorClass, onRetry,
}: QueueHeroProps) {
  if (pendingLoading) {
    return (
      <div id="queue-hero" className="glass-card rounded-2xl px-6 py-5 animate-pulse flex items-center gap-5">
        <div className="flex items-baseline gap-3 shrink-0">
          <div className="h-12 w-12 bg-gray-200 dark:bg-white/10 rounded" />
          <div className="space-y-2">
            <div className="h-4 w-44 bg-gray-200 dark:bg-white/10 rounded" />
            <div className="h-3 w-28 bg-gray-200 dark:bg-white/10 rounded" />
          </div>
        </div>
        <div className="ml-auto h-9 w-48 bg-gray-200 dark:bg-white/10 rounded-lg shrink-0" />
      </div>
    );
  }

  if (pendingError) {
    return (
      <div id="queue-hero" className="glass-card rounded-2xl px-6 py-4 flex items-center gap-3 border border-red-200 dark:border-red-500/20">
        <AlertTriangle size={16} className="text-red-500 shrink-0" />
        <p className="text-sm text-gray-600 dark:text-muted-foreground flex-1">Impossible de charger la file d'attente.</p>
        <button onClick={onRetry} className="text-xs font-medium text-emerald-700 dark:text-emerald-400 hover:underline shrink-0">
          Réessayer
        </button>
      </div>
    );
  }

  if (pendingCount === 0) {
    return (
      <div id="queue-hero" className="glass-card rounded-2xl px-6 py-3.5 flex items-center gap-3 ring-1 ring-emerald-300/50 dark:ring-emerald-500/25">
        <CheckCircle2 size={15} className="text-emerald-500 dark:text-emerald-400 shrink-0" />
        <span className="text-sm text-gray-600 dark:text-muted-foreground">
          File vide —{" "}
          <span className="font-medium text-emerald-700 dark:text-emerald-400">aucun ticket en attente</span>
          {" "}de validation.
        </span>
      </div>
    );
  }

  return (
    <Link
      id="queue-hero"
      to="/tickets"
      state={{ filter: "en_attente", domaine: filterDomaine ?? "tous" }}
      aria-label={`${pendingCount} ticket${pendingCount > 1 ? "s" : ""} en attente de validation — accéder à la file`}
      className="glass-card rounded-2xl px-6 py-5 flex items-center gap-5 ring-1 ring-amber-300/50 dark:ring-amber-500/25 hover:shadow-md transition-shadow group"
    >
      <div className="flex items-baseline gap-3 shrink-0">
        <span className="text-5xl font-bold tabular-nums tracking-tight text-gray-900 dark:text-gray-100 leading-none">
          {pendingCount}
        </span>
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300 leading-tight">
            tickets en attente de validation
          </p>
          <p className={`text-[11px] tabular-nums mt-0.5 ${assignedColorClass(assignedCount)}`}>
            {assignedCount === 0
              ? "aucun assigné à vous"
              : `${assignedCount} assigné${assignedCount > 1 ? "s" : ""} à vous`}
          </p>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2 shrink-0">
        <span className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary group-hover:bg-primary-hover text-primary-foreground text-sm font-medium transition-colors">
          <ClipboardList size={14} />
          Commencer la validation
        </span>
      </div>
    </Link>
  );
}
