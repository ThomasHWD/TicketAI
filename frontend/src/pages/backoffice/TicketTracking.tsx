import { useState, useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Search,
  UserCheck,
  MessageSquare,
  Inbox,
  ClipboardList,
  X,
  Loader2,
} from "lucide-react";
import { getParticipatedTickets, getMyAssignedTickets } from "../../lib/api";
import type { Ticket, StatutTicket } from "../../types/tickets";

// ─── helpers ────────────────────────────────────────────────────────────────

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}

function getErrorMessage(error: unknown): { text: string; canRetry: boolean; canReload: boolean } {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return { text: "Pas de connexion internet. Vérifiez votre réseau.", canRetry: true, canReload: false };
  }
  if (error && typeof error === "object") {
    const status = (error as Record<string, unknown>).status;
    if (status === 401 || status === 403)
      return { text: "Session expirée. Rechargez la page pour vous reconnecter.", canRetry: false, canReload: true };
    if (typeof status === "number" && status >= 500)
      return { text: "Serveur temporairement indisponible. Réessayez dans quelques instants.", canRetry: true, canReload: false };
  }
  return { text: "Impossible de charger les tickets. Vérifiez votre connexion.", canRetry: true, canReload: false };
}

// ─── status badge ────────────────────────────────────────────────────────────

type BadgeVariant = "default" | "success" | "warn" | "danger" | "muted" | "processing";

function resolveVariant(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
): { variant: BadgeVariant; label: string } {
  if (closed) return { variant: "muted", label: "Clôturé" };
  if (processing) return { variant: "processing", label: "En cours" };
  if (canonique) return { variant: "success", label: "Canonique" };
  if (statut === "VALIDÉ") return { variant: "success", label: "Validée" };
  if (statut === "RÉPONDU") return { variant: "warn", label: "À valider" };
  if (statut === "REJETÉ") return { variant: "danger", label: "Rejetée" };
  return { variant: "default", label: "Nouvelle" };
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-blue-50 text-blue-700 border-blue-200/80 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  success: "bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  warn: "bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20",
  danger: "bg-red-50 text-red-700 border-red-200/80 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  muted: "bg-gray-100 text-gray-500 border-gray-200/80 dark:bg-white/10 dark:text-gray-400 dark:border-white/10",
  processing: "bg-sky-50 text-sky-700 border-sky-200/80 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20",
};

function StatutBadge({
  statut,
  canonique,
  closed,
  processing,
}: {
  statut: StatutTicket;
  canonique: boolean;
  closed: boolean;
  processing: boolean;
}) {
  const { variant, label } = resolveVariant(statut, canonique, closed, processing);
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${variantClasses[variant]}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" aria-hidden="true" />
      {label}
    </span>
  );
}

// ─── filter types ────────────────────────────────────────────────────────────

type FilterKey = "tous" | "en_attente" | "en_cours" | "clotures";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "tous",       label: "Tous" },
  { key: "en_attente", label: "En attente" },
  { key: "en_cours",   label: "Traités" },
  { key: "clotures",   label: "Clôturés" },
];

function matchesFilter(t: Ticket, filter: FilterKey): boolean {
  const closed = !!t.closed_at;
  if (filter === "clotures") return closed;
  if (closed) return false;
  if (filter === "tous") return true;
  if (filter === "en_attente")
    return t.statut_ticket === "NOUVEAU" || (t.statut_ticket === "RÉPONDU" && !t.canonique);
  if (filter === "en_cours")
    return t.canonique === true || t.statut_ticket === "VALIDÉ";
  return true;
}

function matchesSearch(t: Ticket, q: string): boolean {
  if (!q.trim()) return true;
  const needle = q.toLowerCase();
  return (
    (t.objet ?? t.question).toLowerCase().includes(needle) ||
    t.domaine.toLowerCase().includes(needle)
  );
}

// ─── empty state ─────────────────────────────────────────────────────────────

function EmptyState({
  icon: Icon,
  title,
  subtitle,
  onClear,
}: {
  icon: React.ElementType;
  title: string;
  subtitle: string;
  onClear?: () => void;
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

// ─── counter chip ─────────────────────────────────────────────────────────────

function CounterChip({ icon: Icon, label, count, accent }: { icon: React.ElementType; label: string; count: number; accent?: boolean }) {
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm ${
      accent
        ? "bg-emerald-50 border-emerald-200/80 text-emerald-700 dark:bg-emerald-500/10 dark:border-emerald-500/20 dark:text-emerald-300"
        : "bg-gray-50 border-gray-200 text-gray-600 dark:bg-white/5 dark:border-white/10 dark:text-gray-400"
    }`}>
      <Icon size={13} className="opacity-70" aria-hidden="true" />
      <span className="font-semibold tabular-nums">{count}</span>
      <span className="text-xs opacity-70">{label}</span>
    </div>
  );
}

// ─── filter bar ──────────────────────────────────────────────────────────────

function FilterBar({
  filter,
  setFilter,
  search,
  setSearch,
  counts,
  searchRef,
}: {
  filter: FilterKey;
  setFilter: (k: FilterKey) => void;
  search: string;
  setSearch: (s: string) => void;
  counts: Record<FilterKey, number>;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const filterBtnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function handleFilterKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = (idx + 1) % FILTERS.length;
      filterBtnRefs.current[next]?.focus();
      setFilter(FILTERS[next].key);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = (idx - 1 + FILTERS.length) % FILTERS.length;
      filterBtnRefs.current[prev]?.focus();
      setFilter(FILTERS[prev].key);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-white/5">
      {/* radio semantics for exclusive filter selection without associated panels */}
      <div role="radiogroup" aria-label="Filtrer par statut" className="flex items-center gap-1">
        {FILTERS.map((f, idx) => (
          <button
            key={f.key}
            ref={(el) => { filterBtnRefs.current[idx] = el; }}
            role="radio"
            aria-checked={filter === f.key}
            tabIndex={filter === f.key ? 0 : -1}
            onClick={() => setFilter(f.key)}
            onKeyDown={(e) => handleFilterKeyDown(e, idx)}
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
            if (e.key === "Escape" && search) {
              e.preventDefault();
              setSearch("");
              searchRef.current?.blur();
            }
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

// ─── ticket row ───────────────────────────────────────────────────────────────

function TicketRow({ ticket }: { ticket: Ticket }) {
  const navigate = useNavigate();
  const closed = !!ticket.closed_at;
  const processing = isProcessing(ticket.statut_job);

  return (
    <tr
      className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500/60"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${ticket.id}`); }}
      tabIndex={0}
      aria-label={`Voir le ticket : ${ticket.objet ?? ticket.question}`}
    >
      <td className="px-5 py-3.5">
        <span
          className="block text-sm text-gray-700 dark:text-gray-200 truncate max-w-sm"
          title={ticket.objet ?? ticket.question}
        >
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

// ─── ticket table ─────────────────────────────────────────────────────────────

function SkeletonTable() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label="Chargement des tickets en cours"
      className="overflow-x-auto animate-pulse"
    >
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 dark:border-white/5">
            <th scope="col" className="px-5 py-2.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-12" /></th>
            <th scope="col" className="px-5 py-2.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-16" /></th>
            <th scope="col" className="px-5 py-2.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-14" /></th>
            <th scope="col" className="px-5 py-2.5"><div className="h-3 bg-gray-200 dark:bg-white/10 rounded w-12" /></th>
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

function TicketTable({
  tickets,
  loading,
  error,
  emptyIcon,
  emptyTitle,
  emptySubtitle,
  onRetry,
  onClear,
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

  if (tickets.length === 0) {
    return (
      <EmptyState
        icon={emptyIcon}
        title={emptyTitle}
        subtitle={emptySubtitle}
        onClear={onClear}
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 dark:border-white/5 text-left">
            <th scope="col" className="px-5 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Objet</th>
            <th scope="col" className="px-5 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Domaine</th>
            <th scope="col" className="px-5 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Créé le</th>
            <th scope="col" className="px-5 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Statut</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50 dark:divide-white/[0.03]">
          {tickets.map((t) => (
            <TicketRow key={t.id} ticket={t} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

const LIMIT = 10;
type TabKey = "assigned" | "participated";

export default function TicketTracking() {
  const [tab, setTab] = useState<TabKey>("assigned");
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<FilterKey>("tous");
  const [search, setSearch] = useState("");

  const searchRef = useRef<HTMLInputElement>(null);
  const mainTabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const {
    data: participatedData,
    isLoading: participatedLoading,
    isFetching: participatedFetching,
    error: participatedError,
    refetch: refetchParticipated,
  } = useQuery({
    queryKey: ["tickets", "participated", page],
    queryFn: () => getParticipatedTickets(page),
    placeholderData: (prev) => prev,
  });

  const {
    data: assignedTickets = [],
    isLoading: assignedLoading,
    isFetching: assignedFetching,
    error: assignedError,
    refetch: refetchAssigned,
  } = useQuery<Ticket[]>({
    queryKey: ["mes-assignations"],
    queryFn: getMyAssignedTickets,
  });

  const participatedTickets = participatedData?.items ?? [];
  const total = participatedData?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  // reset page if data shrinks (e.g. background refetch returns fewer results)
  useEffect(() => {
    if (totalPages > 0 && page > totalPages) {
      setPage(totalPages);
    }
  }, [totalPages, page]);

  const activeTickets = tab === "assigned" ? assignedTickets : participatedTickets;
  const filteredTickets = useMemo(
    () => activeTickets.filter((t) => matchesFilter(t, filter) && matchesSearch(t, search)),
    [activeTickets, filter, search],
  );

  const counts = useMemo<Record<FilterKey, number>>(
    () => ({
      tous:       activeTickets.filter((t) => matchesFilter(t, "tous")).length,
      en_attente: activeTickets.filter((t) => matchesFilter(t, "en_attente")).length,
      en_cours:   activeTickets.filter((t) => matchesFilter(t, "en_cours")).length,
      clotures:   activeTickets.filter((t) => matchesFilter(t, "clotures")).length,
    }),
    [activeTickets],
  );

  // tickets needing validation among assigned — always from assignedTickets, not the active tab
  const assignedEnAttente = useMemo(
    () => assignedTickets.filter((t) => matchesFilter(t, "en_attente")).length,
    [assignedTickets],
  );

  const isFetchingBg = tab === "assigned"
    ? (assignedFetching && !assignedLoading)
    : (participatedFetching && !participatedLoading);

  const hasActiveFilters = filter !== "tous" || !!search;

  function handleClearFilters() {
    setFilter("tous");
    setSearch("");
  }

  const tabs: { key: TabKey; label: string; icon: React.ElementType }[] = [
    { key: "assigned", label: "Assignés à moi", icon: UserCheck },
    { key: "participated", label: "Mes participations", icon: ClipboardList },
  ];

  function handleTabChange(t: TabKey) {
    setTab(t);
    setFilter("tous");
    setSearch("");
    setPage(1);
  }

  function handleMainTabKeyDown(e: React.KeyboardEvent, idx: number) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = (idx + 1) % tabs.length;
      mainTabRefs.current[next]?.focus();
      handleTabChange(tabs[next].key);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = (idx - 1 + tabs.length) % tabs.length;
      mainTabRefs.current[prev]?.focus();
      handleTabChange(tabs[prev].key);
    }
  }

  // global keyboard shortcuts: / → search, 1–4 → filters, j/k → row navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inInput = target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA";

      if (e.key === "/" && !inInput) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
        return;
      }
      if (inInput) return;

      if (e.key >= "1" && e.key <= "4") {
        const idx = parseInt(e.key) - 1;
        const f = FILTERS[idx];
        if (f) { e.preventDefault(); setFilter(f.key); }
        return;
      }

      const rows = Array.from(document.querySelectorAll<HTMLElement>('tbody tr[tabindex="0"]'));
      if (rows.length === 0) return;
      const activeIndex = rows.findIndex((r) => r === document.activeElement);
      if (e.key === "j") { e.preventDefault(); rows[Math.min(activeIndex + 1, rows.length - 1)]?.focus(); }
      else if (e.key === "k") { e.preventDefault(); rows[Math.max(activeIndex - 1, 0)]?.focus(); }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Mon suivi</h1>
        <div className="flex items-center gap-2">
          <CounterChip
            icon={UserCheck}
            label="à valider"
            count={assignedEnAttente}
            accent={assignedEnAttente > 0}
          />
          <CounterChip icon={MessageSquare} label="participations" count={total} />
        </div>
      </div>

      {/* glass card */}
      <div className="glass-card rounded-2xl overflow-hidden">

        {/* tab bar */}
        <div
          role="tablist"
          aria-label="Vue des tickets"
          className="flex items-center border-b border-gray-200 dark:border-white/10 px-5"
        >
          {tabs.map(({ key, label, icon: Icon }, idx) => (
            <button
              key={key}
              ref={(el) => { mainTabRefs.current[idx] = el; }}
              role="tab"
              id={`tracking-tab-${key}`}
              aria-selected={tab === key}
              aria-controls={`tracking-panel-${key}`}
              tabIndex={tab === key ? 0 : -1}
              onClick={() => handleTabChange(key)}
              onKeyDown={(e) => handleMainTabKeyDown(e, idx)}
              className={`relative flex items-center gap-2 py-3.5 pr-5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500/60 ${
                tab === key
                  ? "text-gray-900 dark:text-gray-100"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              <Icon size={14} className={tab === key ? "text-emerald-500" : "opacity-50"} aria-hidden="true" />
              {label}
              {key === "assigned" && assignedTickets.length > 0 && (
                <span className={`inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold ${
                  tab === key
                    ? "bg-emerald-500 text-white"
                    : "bg-gray-200 text-gray-600 dark:bg-white/10 dark:text-gray-400"
                }`}>
                  {assignedTickets.length}
                </span>
              )}
              {tab === key && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-emerald-500 rounded-full" aria-hidden="true" />
              )}
            </button>
          ))}
        </div>

        {/* background refetch indicator — outside tablist to comply with ARIA tablist children rule */}
        {isFetchingBg && (
          <div
            role="status"
            aria-live="polite"
            aria-label="Actualisation en cours"
            className="px-5 py-1.5 flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-white/5"
          >
            <Loader2 size={11} className="animate-spin" aria-hidden="true" />
            Actualisation…
          </div>
        )}

        {/* tab panel */}
        <div
          role="tabpanel"
          id={`tracking-panel-${tab}`}
          aria-labelledby={`tracking-tab-${tab}`}
        >
          {/* filter bar */}
          <FilterBar
            filter={filter}
            setFilter={setFilter}
            search={search}
            setSearch={setSearch}
            counts={counts}
            searchRef={searchRef}
          />

          {/* ticket table */}
          <TicketTable
            tickets={filteredTickets}
            loading={tab === "assigned" ? assignedLoading : participatedLoading}
            error={tab === "assigned" ? (assignedError as Error | null) : (participatedError as Error | null)}
            onRetry={tab === "assigned" ? refetchAssigned : refetchParticipated}
            onClear={hasActiveFilters ? handleClearFilters : undefined}
            emptyIcon={tab === "assigned" ? UserCheck : Inbox}
            emptyTitle={
              hasActiveFilters
                ? "Aucun ticket ne correspond à vos filtres."
                : tab === "assigned"
                ? "Aucun ticket ne vous est assigné."
                : "Vous n'avez encore participé à aucun ticket."
            }
            emptySubtitle={
              hasActiveFilters
                ? "Modifiez vos critères ou effacez les filtres."
                : tab === "assigned"
                ? "Les tickets assignés directement à votre compte apparaîtront ici."
                : "Les tickets sur lesquels vous avez commenté ou validé apparaîtront ici."
            }
          />

          {/* pagination — participations only */}
          {tab === "participated" && !participatedLoading && total > 0 && (
            <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 dark:border-white/5 text-xs text-gray-500 dark:text-gray-400">
              <span className="tabular-nums">{from}–{to} sur {total}</span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                  aria-label="Page précédente"
                >
                  <ChevronLeft size={14} aria-hidden="true" />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/60"
                  aria-label="Page suivante"
                >
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* keyboard hint — role="note" for AT discoverability */}
      <p role="note" aria-label="Raccourcis clavier" className="text-[11px] text-gray-500 dark:text-gray-400 text-right select-none">
        Raccourcis&nbsp;: <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> naviguer · <kbd className="font-mono">/</kbd> rechercher · <kbd className="font-mono">1–4</kbd> filtres · <kbd className="font-mono">Échap</kbd> quitter la recherche
      </p>
    </div>
  );
}
