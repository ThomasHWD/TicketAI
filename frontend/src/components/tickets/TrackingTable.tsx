import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Search, X } from "lucide-react";
import type { Ticket, StatutTicket } from "../../types";
import type { FilterKey } from "../../hooks/useTicketTracking";


function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
}

function getErrorMessage(error: unknown): { text: string; canRetry: boolean; canReload: boolean } {
  if (typeof navigator !== "undefined" && !navigator.onLine)
    return { text: "Pas de connexion internet. Vérifiez votre réseau.", canRetry: true, canReload: false };
  if (error && typeof error === "object") {
    const status = (error as Record<string, unknown>).status;
    if (status === 401 || status === 403)
      return { text: "Session expirée. Rechargez la page pour vous reconnecter.", canRetry: false, canReload: true };
    if (typeof status === "number" && status >= 500)
      return { text: "Serveur temporairement indisponible. Réessayez dans quelques instants.", canRetry: true, canReload: false };
  }
  return { text: "Impossible de charger les tickets. Vérifiez votre connexion.", canRetry: true, canReload: false };
}


type BadgeVariant = "default" | "success" | "warn" | "danger" | "muted" | "processing";

const variantClasses: Record<BadgeVariant, string> = {
  default:    "bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  success:    "bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  warn:       "bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20",
  danger:     "bg-red-50 text-red-700 border-red-200/80 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  muted:      "bg-gray-100 text-gray-500 border-gray-200/80 dark:bg-white/10 dark:text-gray-400 dark:border-white/10",
  processing: "bg-sky-50 text-sky-700 border-sky-200/80 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20",
};

function resolveVariant(
  statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean,
): { variant: BadgeVariant; label: string } {
  if (closed)     return { variant: "muted",      label: "Clôturé" };
  if (processing) return { variant: "processing", label: "En cours" };
  if (canonique)  return { variant: "success",    label: "Canonique" };
  if (statut === "VALIDÉ")   return { variant: "success", label: "Validée" };
  if (statut === "RÉPONDU")  return { variant: "warn",    label: "À valider" };
  if (statut === "REJETÉ")   return { variant: "danger",  label: "Rejetée" };
  return { variant: "default", label: "Nouvelle" };
}

function StatutBadge({ statut, canonique, closed, processing }: {
  statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean;
}) {
  const { variant, label } = resolveVariant(statut, canonique, closed, processing);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${variantClasses[variant]}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" aria-hidden="true" />
      {label}
    </span>
  );
}


const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "tous",       label: "Tous" },
  { key: "en_attente", label: "En attente" },
  { key: "en_cours",   label: "Traités" },
  { key: "clotures",   label: "Clôturés" },
];

export function FilterBar({
  filter, setFilter, search, setSearch, counts, searchRef,
}: {
  filter: FilterKey;
  setFilter: (k: FilterKey) => void;
  search: string;
  setSearch: (s: string) => void;
  counts: Record<FilterKey, number>;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function handleKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = (idx + 1) % FILTERS.length;
      btnRefs.current[next]?.focus();
      setFilter(FILTERS[next].key);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = (idx - 1 + FILTERS.length) % FILTERS.length;
      btnRefs.current[prev]?.focus();
      setFilter(FILTERS[prev].key);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-white/5">
      <div role="radiogroup" aria-label="Filtrer par statut" className="flex items-center gap-1">
        {FILTERS.map((f, idx) => (
          <button
            key={f.key}
            ref={(el) => { btnRefs.current[idx] = el; }}
            role="radio"
            aria-checked={filter === f.key}
            tabIndex={filter === f.key ? 0 : -1}
            onClick={() => setFilter(f.key)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className={`inline-flex items-center gap-1.5 px-2.5 min-h-[44px] border-b-2 -mb-px text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500/60 ${
              filter === f.key
                ? "border-emerald-500 text-gray-900 dark:text-gray-100"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:border-white/20"
            }`}
          >
            {f.label}
            {counts[f.key] > 0 && f.key !== "tous" && (
              <span className={`inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-[10px] font-semibold tabular-nums leading-none ${
                filter === f.key
                  ? "bg-emerald-100 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-300"
                  : "bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400"
              }`}>
                {counts[f.key]}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="relative ml-auto">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" aria-hidden="true" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape" && search) { e.preventDefault(); setSearch(""); searchRef.current?.blur(); }
          }}
          placeholder="Rechercher… (/ pour cibler)"
          aria-label="Rechercher un ticket"
          className="pl-7 pr-7 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 focus-visible:border-transparent dark:bg-white/5 dark:border-white/10 dark:text-gray-200 dark:placeholder:text-gray-500 w-48"
        />
        {search && (
          <button
            onClick={() => { setSearch(""); searchRef.current?.focus(); }}
            aria-label="Effacer la recherche"
            className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
          >
            <X size={12} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}


export function TrackingTicketRow({ ticket }: { ticket: Ticket }) {
  const navigate = useNavigate();
  const closed = !!ticket.closed_at;
  const processing = ticket.statut_job === "EN_ATTENTE" || ticket.statut_job === "EN_COURS";

  return (
    <tr
      className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500/60"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${ticket.id}`); }}
      tabIndex={0}
      aria-label={`Voir le ticket : ${ticket.objet ?? ticket.question}`}
    >
      <td className="px-5 py-3.5">
        <span className="block text-sm text-gray-700 dark:text-gray-200 truncate max-w-sm" title={ticket.objet ?? ticket.question}>
          {ticket.objet ?? ticket.question}
        </span>
      </td>
      <td className="px-5 py-3.5 whitespace-nowrap">
        <span className="text-xs text-gray-500 dark:text-gray-400">{ticket.domaine}</span>
      </td>
      <td className="px-5 py-3.5 whitespace-nowrap">
        <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">{formatDate(ticket.created_at)}</span>
      </td>
      <td className="px-5 py-3.5">
        <StatutBadge
          statut={ticket.statut_ticket as StatutTicket}
          canonique={ticket.canonique}
          closed={closed}
          processing={processing}
        />
      </td>
    </tr>
  );
}


function SkeletonTable() {
  return (
    <div role="status" aria-live="polite" aria-busy="true" aria-label="Chargement des tickets en cours" className="overflow-x-auto animate-pulse">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 dark:border-white/5">
            {["w-12", "w-16", "w-14", "w-12"].map((w, i) => (
              <th key={i} scope="col" className="px-5 py-2.5">
                <div className={`h-3 bg-gray-200 dark:bg-white/10 rounded ${w}`} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50 dark:divide-white/[0.03]">
          {[...Array(5)].map((_, i) => (
            <tr key={i}>
              <td className="px-5 py-3.5"><div className="h-4 bg-gray-200 dark:bg-white/10 rounded w-64" /></td>
              <td className="px-5 py-3.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-20" /></td>
              <td className="px-5 py-3.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-20" /></td>
              <td className="px-5 py-3.5"><div className="h-5 bg-gray-200 dark:bg-white/10 rounded-full w-20" /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmptyState({ icon: Icon, title, subtitle, onClear }: {
  icon: React.ElementType; title: string; subtitle: string; onClear?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-white/5 flex items-center justify-center">
        <Icon size={18} className="text-gray-500 dark:text-gray-400" aria-hidden="true" />
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{title}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 max-w-xs">{subtitle}</p>
      {onClear && (
        <button
          onClick={onClear}
          className="mt-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60 rounded-md px-1"
        >
          Effacer les filtres
        </button>
      )}
    </div>
  );
}

export function TrackingTicketTable({
  tickets, loading, error, emptyIcon, emptyTitle, emptySubtitle, onRetry, onClear,
}: {
  tickets: Ticket[];
  loading: boolean;
  error?: Error | null;
  emptyIcon: React.ElementType;
  emptyTitle: string;
  emptySubtitle: string;
  onRetry?: () => void;
  onClear?: () => void;
}) {
  if (loading) return <SkeletonTable />;

  if (error) {
    const { text, canRetry, canReload } = getErrorMessage(error);
    return (
      <div role="alert" className="py-16 text-center space-y-3">
        <p className="text-sm text-red-500 dark:text-red-400">{text}</p>
        {canRetry && onRetry && (
          <button
            onClick={onRetry}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-gray-100 hover:bg-gray-200 dark:bg-white/10 dark:hover:bg-white/15 text-gray-700 dark:text-gray-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
          >
            Réessayer
          </button>
        )}
        {canReload && (
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1.5 text-xs font-medium rounded-md bg-emerald-600 hover:bg-emerald-700 text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
          >
            Recharger la page
          </button>
        )}
      </div>
    );
  }

  if (!tickets.length) {
    return <EmptyState icon={emptyIcon} title={emptyTitle} subtitle={emptySubtitle} onClear={onClear} />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 dark:border-white/5 text-left">
            {["Objet", "Domaine", "Créé le", "Statut"].map((h) => (
              <th key={h} scope="col" className="px-5 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50 dark:divide-white/[0.03]">
          {tickets.map((t) => <TrackingTicketRow key={t.id} ticket={t} />)}
        </tbody>
      </table>
    </div>
  );
}
