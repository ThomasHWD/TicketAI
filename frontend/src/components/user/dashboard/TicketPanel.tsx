import { ChevronRight, AlertCircle, RefreshCw, CheckCircle2, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { formatDate } from "../../../lib/ticketStatus";
import type { Ticket } from "../../../types";

type TicketExt = Ticket & { closed_at?: string | null; objet?: string | null };
type RowVariant = "reply" | "processing" | "rejected";

function displayText(t: TicketExt): string {
  return t.objet ?? t.question;
}


export function UserTicketRow({
  ticket: t,
  variant,
  onClick,
}: {
  ticket: TicketExt;
  variant: RowVariant;
  onClick: () => void;
}) {
  const dotClass =
    variant === "reply"     ? "bg-emerald-500" :
    variant === "rejected"  ? "bg-red-400" :
                              "bg-blue-500 motion-safe:animate-pulse";

  const dotTitle =
    variant === "reply"    ? "Réponse disponible" :
    variant === "rejected" ? "Demande rejetée" :
                             "En cours de traitement";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Voir le ticket : ${displayText(t)}`}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}
      className="group flex items-center gap-4 px-6 py-4 hover:bg-gray-50 dark:hover:bg-white/[0.04] transition-colors cursor-pointer select-none"
    >
      <span className={`shrink-0 w-2 h-2 rounded-full ${dotClass}`} title={dotTitle} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
          {displayText(t)}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground flex items-center gap-1.5">
          <span className="font-medium">{t.domaine}</span>
          <span className="opacity-40">·</span>
          {formatDate(t.created_at)}
        </p>
      </div>
      <ChevronRight size={16} className="shrink-0 text-subtle group-hover:text-gray-500 dark:group-hover:text-gray-400 transition-colors" />
    </div>
  );
}


export function SkeletonRows() {
  return (
    <div className="divide-y divide-gray-100 dark:divide-white/5">
      {[58, 72, 44].map((w, i) => (
        <div key={i} className="flex items-center gap-4 px-6 py-4">
          <div className="shrink-0 w-2 h-2 rounded-full bg-gray-200 dark:bg-white/10 animate-pulse" />
          <div className="flex-1 space-y-1.5">
            <div className="h-4 bg-gray-100 dark:bg-white/[0.08] rounded animate-pulse" style={{ width: `${w}%` }} />
            <div className="h-3 w-28 bg-gray-50 dark:bg-white/[0.04] rounded animate-pulse" />
          </div>
          <div className="shrink-0 w-4 h-4 rounded bg-gray-50 dark:bg-white/[0.04] animate-pulse" />
        </div>
      ))}
    </div>
  );
}


export function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
      <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-500/10">
        <AlertCircle size={28} className="text-red-500" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Impossible de charger vos tickets
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          Vérifiez votre connexion et réessayez.
          <br />
          <span className="text-xs">Vos questions ne sont pas affectées par cette erreur.</span>
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-gray-100 dark:bg-white/10 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-white/15 transition-colors"
      >
        <RefreshCw size={14} />
        Réessayer
      </button>
    </div>
  );
}


export function AllUpToDate() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
      <div className="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10">
        <CheckCircle2 size={28} className="text-emerald-500" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">Tout est à jour</p>
        <p className="mt-1 text-sm text-muted-foreground">Vous n'avez aucune demande en attente.</p>
      </div>
      <button
        type="button"
        onClick={() => navigate("/nouveau-ticket")}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-gray-200 dark:border-white/10 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
      >
        <Plus size={14} />
        Poser une question
      </button>
    </div>
  );
}


export function SubLabel({ children, hasBorderTop = false }: { children: React.ReactNode; hasBorderTop?: boolean }) {
  return (
    <div className={`px-6 py-2 bg-gray-50/70 dark:bg-white/[0.025] ${hasBorderTop ? "border-t border-gray-100 dark:border-white/5" : ""}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        {children}
      </p>
    </div>
  );
}
