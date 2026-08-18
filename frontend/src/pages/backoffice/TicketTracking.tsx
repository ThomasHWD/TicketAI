import { useState, useMemo } from "react";
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
  if (statut === "VALIDÉ") return { variant: "default", label: "Validée" };
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
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      {label}
    </span>
  );
}

// ─── filter types ────────────────────────────────────────────────────────────

// Mirror TicketsList FilterView exactly (same keys, labels, and predicates).
type FilterKey = "tous" | "en_attente" | "en_cours" | "clotures";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "tous",       label: "Tous" },
  { key: "en_attente", label: "En attente" },
  { key: "en_cours",   label: "Répondus" },
  { key: "clotures",   label: "Clôturés" },
];

function matchesFilter(t: Ticket, filter: FilterKey): boolean {
  const closed = !!t.closed_at;
  if (filter === "clotures") return closed;
  if (closed) return false; // "tous", "en_attente", "en_cours" exclude closed tickets
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

function EmptyState({ icon: Icon, title, subtitle }: { icon: React.ElementType; title: string; subtitle: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <div className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-white/5 flex items-center justify-center">
        <Icon size={18} className="text-gray-400 dark:text-gray-500" />
      </div>
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{title}</p>
      <p className="text-xs text-gray-400 dark:text-gray-500 max-w-xs">{subtitle}</p>
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
      <Icon size={13} className="opacity-70" />
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
}: {
  filter: FilterKey;
  setFilter: (k: FilterKey) => void;
  search: string;
  setSearch: (s: string) => void;
  counts: Record<FilterKey, number>;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-white/5">
      <div className="flex items-center gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
              filter === f.key
                ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                : "text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-white/5"
            }`}
          >
            {f.label}
            {counts[f.key] > 0 && f.key !== "tous" && (
              <span className={`text-[10px] font-semibold tabular-nums leading-none ${filter === f.key ? "opacity-60" : "opacity-50"}`}>
                {counts[f.key]}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="relative ml-auto">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Rechercher…"
          className="pl-7 pr-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent dark:bg-white/5 dark:border-white/10 dark:text-gray-200 dark:placeholder:text-gray-500 w-44"
        />
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
      className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors cursor-pointer"
      onClick={() => navigate(`/tickets/${ticket.id}`)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${ticket.id}`); }}
      tabIndex={0}
      role="link"
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
        <span className="text-xs text-gray-400 dark:text-gray-500">{ticket.domaine}</span>
      </td>
      <td className="px-5 py-3.5 whitespace-nowrap">
        <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">{formatDate(ticket.created_at)}</span>
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

function TicketTable({
  tickets,
  loading,
  error,
  emptyIcon,
  emptyTitle,
  emptySubtitle,
}: {
  tickets: Ticket[];
  loading: boolean;
  error?: Error | null;
  emptyIcon: React.ElementType;
  emptyTitle: string;
  emptySubtitle: string;
}) {
  if (loading) {
    return (
      <div className="py-16 text-center text-sm text-gray-400 dark:text-gray-500">Chargement…</div>
    );
  }
  if (error) {
    return (
      <div className="py-16 text-center text-sm text-red-500 dark:text-red-400">
        {error instanceof Error ? error.message : "Erreur de chargement"}
      </div>
    );
  }
  if (tickets.length === 0) {
    return <EmptyState icon={emptyIcon} title={emptyTitle} subtitle={emptySubtitle} />;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-100 dark:border-white/5 text-left">
            <th className="px-5 py-2.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">Objet</th>
            <th className="px-5 py-2.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">Domaine</th>
            <th className="px-5 py-2.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">Créé le</th>
            <th className="px-5 py-2.5 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">Statut</th>
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

  const { data: participatedData, isLoading: participatedLoading, error: participatedError } = useQuery({
    queryKey: ["tickets", "participated", page],
    queryFn: () => getParticipatedTickets(page),
    placeholderData: (prev) => prev,
  });

  const { data: assignedTickets = [], isLoading: assignedLoading } = useQuery<Ticket[]>({
    queryKey: ["mes-assignations"],
    queryFn: getMyAssignedTickets,
  });

  const participatedTickets = participatedData?.items ?? [];
  const total = participatedData?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  // filter & search applied only to the active tab's data
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

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">

      {/* page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">Mon suivi</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Tickets qui vous sont assignés et tickets auxquels vous avez contribué.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <CounterChip icon={UserCheck} label="assignés" count={assignedTickets.length} accent={assignedTickets.length > 0} />
          <CounterChip icon={MessageSquare} label="participations" count={total} />
        </div>
      </div>

      {/* glass card */}
      <div className="glass-card rounded-2xl overflow-hidden">

        {/* tab bar */}
        <div className="flex items-center border-b border-gray-200 dark:border-white/10 px-5">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => handleTabChange(key)}
              className={`relative flex items-center gap-2 py-3.5 pr-5 text-sm font-medium transition-colors ${
                tab === key
                  ? "text-gray-900 dark:text-gray-100"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              }`}
            >
              <Icon size={14} className={tab === key ? "text-emerald-500" : "opacity-50"} />
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
                <span className="absolute bottom-0 left-0 right-5 h-0.5 bg-emerald-500 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* filter bar */}
        <FilterBar
          filter={filter}
          setFilter={setFilter}
          search={search}
          setSearch={setSearch}
          counts={counts}
        />

        {/* ticket table */}
        <TicketTable
          tickets={filteredTickets}

          loading={tab === "assigned" ? assignedLoading : participatedLoading}
          error={tab === "participated" ? (participatedError as Error | null) : null}
          emptyIcon={tab === "assigned" ? UserCheck : Inbox}
          emptyTitle={
            filter !== "all" || search
              ? "Aucun ticket ne correspond à vos filtres."
              : tab === "assigned"
              ? "Aucun ticket ne vous est assigné."
              : "Vous n'avez encore participé à aucun ticket."
          }
          emptySubtitle={
            filter !== "all" || search
              ? "Essayez un filtre différent ou effacez la recherche."
              : tab === "assigned"
              ? "Les tickets assignés directement à votre compte apparaîtront ici."
              : "Les tickets sur lesquels vous avez commenté ou validé apparaîtront ici."
          }
        />

        {/* pagination — participations only */}
        {tab === "participated" && !participatedLoading && total > 0 && (
          <div className="flex items-center justify-between px-5 py-3.5 border-t border-gray-100 dark:border-white/5 text-xs text-gray-400 dark:text-gray-500">
            <span className="tabular-nums">{from}–{to} sur {total}</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Page précédente"
              >
                <ChevronLeft size={14} />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Page suivante"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
