import { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Lock,
  UserCheck,
  Search,
  ArrowUpDown,
  Inbox,
  Layers,
} from "lucide-react";
import { getTickets } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import type { Ticket, StatutTicket, Domaine } from "../../types";

// ─── helpers ────────────────────────────────────────────────────────────────

function isLocked(t: Ticket): boolean {
  return !!(t.lock_expires_at && new Date(t.lock_expires_at) > new Date());
}

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function formatDateShort(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);
  if (diffDays === 0) {
    return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" }).format(d);
  }
  if (diffDays < 7) return `il y a ${diffDays}j`;
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short" }).format(d);
}

function formatDateFull(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

type FilterView = "tous" | "en_attente" | "en_cours" | "clotures";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function matchesFilter(t: any, filter: FilterView): boolean {
  if (filter === "tous" || filter === "clotures") return true;
  if (filter === "en_attente")
    return t.statut_ticket === "NOUVEAU" ||
      (t.statut_ticket === "RÉPONDU" && !t.canonique);
  if (filter === "en_cours")
    return t.canonique === true || t.statut_ticket === "VALIDÉ";
  return true;
}

function serverStatut(_filter: FilterView): string | undefined {
  return undefined;
}

const FILTER_TABS: { value: FilterView; label: string }[] = [
  { value: "tous",        label: "Tous" },
  { value: "en_attente",  label: "En attente" },
  { value: "en_cours",    label: "Répondus" },
  { value: "clotures",    label: "Clôturés" },
];

interface StatutMeta {
  label: string;
  badgeClass: string;
  dotClass?: string;
}

function getStatutMeta(
  statut: StatutTicket,
  canonique: boolean,
  closed: boolean,
  processing: boolean,
  reponseSource: string | null,
): StatutMeta {
  if (closed) return {
    label: "Clôturé",
    badgeClass: "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-400 dark:border-white/10",
  };
  if (processing) return {
    label: "En cours",
    badgeClass: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
    dotClass: "animate-pulse",
  };
  if (canonique) return {
    label: "Canonique",
    badgeClass: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  };
  if (statut === "VALIDÉ") return {
    label: "Validée",
    badgeClass: "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  };
  if (statut === "RÉPONDU" && reponseSource === "HORS_DOMAINE") return {
    label: "Hors domaine",
    badgeClass: "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/20",
  };
  if (statut === "RÉPONDU") return {
    label: "Suggestion",
    badgeClass: "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-500/20",
  };
  if (statut === "REJETÉ") return {
    label: "Rejetée",
    badgeClass: "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  };
  return {
    label: "Nouvelle",
    badgeClass: "bg-sky-50 text-sky-600 border-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:border-sky-500/20",
  };
}

// ─── sub-components ──────────────────────────────────────────────────────────

function StatusBadge({ statut, canonique, closed, processing, reponseSource }: {
  statut: StatutTicket;
  canonique: boolean;
  closed: boolean;
  processing: boolean;
  reponseSource: string | null;
}) {
  const meta = getStatutMeta(statut, canonique, closed, processing, reponseSource);
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border whitespace-nowrap ${meta.badgeClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full bg-current shrink-0 ${meta.dotClass ?? ""}`} aria-hidden="true" />
      {meta.label}
    </span>
  );
}

function DomaineBadge({ domaine }: { domaine: string }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200 dark:bg-white/10 dark:text-slate-300 dark:border-white/10 whitespace-nowrap">
      {domaine}
    </span>
  );
}

function EmptyState({ hasFilters, isClosed, colSpan }: { hasFilters: boolean; isClosed: boolean; colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan}>
        <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
          <div className="w-12 h-12 rounded-2xl bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 flex items-center justify-center shadow-sm">
            <Inbox size={20} className="text-gray-400 dark:text-gray-500" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {hasFilters ? "Aucun résultat" : isClosed ? "Aucun ticket clôturé" : "Aucun ticket ouvert"}
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              {hasFilters ? "Essayez d'autres filtres." : isClosed ? "Aucun ticket n'a encore été clôturé." : "Tous les tickets ont été traités."}
            </p>
          </div>
        </div>
      </td>
    </tr>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

const LIMIT = 25;

const SKELETON_WIDTHS = ["w-3/4", "w-2/3", "w-4/5", "w-1/2", "w-3/5", "w-5/6"];

export default function TicketsList() {
  const navigate = useNavigate();
  const location = useLocation();
  const { userDomaines } = useAuth();

  const multiDomain = userDomaines.length > 1;

  const locationState = location.state as { filter?: FilterView; domaine?: string } | null;

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [filter, setFilter] = useState<FilterView>(locationState?.filter ?? "tous");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [domainFilter, setDomainFilter] = useState<string>(locationState?.domaine ?? "tous");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { setPage(1); }, [debouncedSearch, filter, domainFilter]);

  const queryDomaines = domainFilter === "tous" ? userDomaines : undefined;
  const queryDomaine = domainFilter !== "tous" ? domainFilter as Domaine : undefined;

  const { data: countData } = useQuery({
    queryKey: ["tickets", "counts", userDomaines, domainFilter],
    queryFn: () => getTickets({ limit: 200, closed: false, domaines: queryDomaines, domaine: queryDomaine, disponibles: true }),
    staleTime: 30_000,
  });

  const tabCounts = useMemo(() => {
    const items = countData?.items ?? [];
    return {
      tous: countData?.total ?? 0,
      en_attente: items.filter((t) => matchesFilter(t, "en_attente")).length,
      en_cours: items.filter((t) => matchesFilter(t, "en_cours")).length,
      clotures: 0,
    } satisfies Record<FilterView, number>;
  }, [countData]);

  const isClosed = filter === "clotures";

  const { data, isLoading, error } = useQuery({
    queryKey: ["tickets", isClosed ? "closed" : "open", page, userDomaines, domainFilter, debouncedSearch, filter],
    queryFn: () => getTickets({
      page,
      limit: LIMIT,
      closed: isClosed,
      domaines: queryDomaines,
      domaine: queryDomaine,
      disponibles: isClosed ? undefined : true,
      search: debouncedSearch || undefined,
      statut: serverStatut(filter),
    }),
    placeholderData: (prev) => prev,
  });

  const tickets: Ticket[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / LIMIT);
  const from = total === 0 ? 0 : (page - 1) * LIMIT + 1;
  const to = Math.min(page * LIMIT, total);

  const filtered = tickets.filter((t) => matchesFilter(t, filter));
  const sorted = sortDir === "asc"
    ? [...filtered].sort((a, b) =>
        new Date(a.created_at ?? 0).getTime() - new Date(b.created_at ?? 0).getTime()
      )
    : filtered;

  const hasFilters = !!debouncedSearch || filter !== "tous";

  return (
    <div className="p-6 space-y-5">
      {/* ── Page header ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100 tracking-tight">
          Tickets
        </h1>
        {total > 0 && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 tabular-nums border border-gray-200/60 dark:border-white/[0.08]">
            {total}
          </span>
        )}
      </div>

      {/* ── Toolbar : filtres | recherche + tri ───────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Filtres statut */}
        <nav className="flex items-center gap-1 flex-1 min-w-0" aria-label="Filtres par statut">
          {FILTER_TABS.map((tab) => {
            const count = tabCounts[tab.value];
            const active = filter === tab.value;
            return (
              <button
                key={tab.value}
                onClick={() => setFilter(tab.value)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 border-b-2 text-sm font-medium transition-colors duration-150 ${
                  active
                    ? "border-emerald-500 text-gray-900 dark:text-gray-100"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-white/20"
                }`}
              >
                {tab.label}
                {count > 0 && (
                  <span
                    className={`inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums leading-none ${
                      active
                        ? "bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300"
                        : "bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400"
                    }`}
                  >
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Séparateur */}
        <div className="w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" aria-hidden="true" />

        {/* Filtre domaine — uniquement si plusieurs groupes */}
        {multiDomain && (
          <div className="relative shrink-0 inline-flex items-center gap-1.5">
            <Layers size={12} className="absolute left-2.5 text-gray-400 dark:text-gray-500 pointer-events-none" aria-hidden="true" />
            <select
              value={domainFilter}
              onChange={(e) => setDomainFilter(e.target.value)}
              className="pl-7 pr-6 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 appearance-none transition-shadow"
              aria-label="Filtrer par domaine"
            >
              <option value="tous">Tous les domaines</option>
              {userDomaines.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
        )}

        {/* Recherche */}
        <div className="relative shrink-0">
          <Search
            size={13}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
          />
          <input
            type="search"
            placeholder="Rechercher…"
            aria-label="Rechercher un ticket"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-48 transition-shadow"
          />
        </div>

        {/* Tri */}
        <button
          onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5"
          aria-label={`Trier par date : ${sortDir === "desc" ? "plus récent" : "plus ancien"}`}
        >
          <ArrowUpDown size={12} aria-hidden="true" />
          {sortDir === "desc" ? "Plus récent" : "Plus ancien"}
        </button>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-white/5 bg-gray-50/60 dark:bg-white/[0.02]">
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide w-full">
                  Objet
                </th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap hidden sm:table-cell">
                  Créé
                </th>
                {multiDomain && (
                  <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap hidden md:table-cell">
                    Domaine
                  </th>
                )}
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap">
                  Statut
                </th>
                <th className="px-5 py-3 w-8 hidden sm:table-cell" aria-hidden="true" />
              </tr>
            </thead>

            <tbody className="divide-y divide-gray-50 dark:divide-white/[0.04]">
              {/* Loading skeleton */}
              {isLoading && Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td className="px-5 py-4">
                    <div className="space-y-1.5">
                      <div className={`h-3.5 bg-gray-100 dark:bg-white/5 rounded ${SKELETON_WIDTHS[i % SKELETON_WIDTHS.length]}`} />
                      <div className="h-2.5 bg-gray-50 dark:bg-white/[0.03] rounded w-1/3" />
                    </div>
                  </td>
                  <td className="px-5 py-4 hidden sm:table-cell">
                    <div className="h-3 bg-gray-100 dark:bg-white/5 rounded w-16" />
                  </td>
                  {multiDomain && (
                    <td className="px-5 py-4 hidden md:table-cell">
                      <div className="h-5 bg-gray-100 dark:bg-white/5 rounded w-12" />
                    </td>
                  )}
                  <td className="px-5 py-4">
                    <div className="h-5 bg-gray-100 dark:bg-white/5 rounded-full w-20" />
                  </td>
                  <td className="px-5 py-4 hidden sm:table-cell" />
                </tr>
              ))}

              {/* Error */}
              {!isLoading && error && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-sm text-red-500 dark:text-red-400">
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}

              {/* Empty */}
              {!isLoading && !error && sorted.length === 0 && (
                <EmptyState hasFilters={hasFilters} isClosed={isClosed} colSpan={multiDomain ? 5 : 4} />
              )}

              {/* Rows */}
              {!isLoading && !error && sorted.map((t: Ticket) => {
                const locked = isLocked(t);
                const processing = isProcessing(t.statut_job);
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const tx = t as any;
                const title: string = tx.objet ?? t.question;
                const closed = !!tx.closed_at;
                const reponseSource: string | null = tx.reponse_source ?? null;
                const assignedNom: string | null = tx.assigned_to_nom_complet ?? tx.assigned_to_email ?? null;
                const lockedEmail: string = t.locked_by_email ?? "un validateur";
                const userEmail: string | null = t.user_email;

                return (
                  <tr
                    key={t.id}
                    className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors duration-100 cursor-pointer focus-within:bg-gray-50/80 dark:focus-within:bg-white/[0.03]"
                    onClick={() => navigate(`/tickets/${t.id}`)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate(`/tickets/${t.id}`); }}
                    tabIndex={0}
                    role="link"
                    aria-label={`Voir le ticket : ${title}${locked ? ` (pris en charge par ${lockedEmail})` : ""}`}
                  >
                    {/* Objet */}
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2 min-w-0">
                        {locked && (
                          <span
                            className="shrink-0 inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-50 text-amber-500 ring-1 ring-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20"
                            title={`Pris en charge par ${lockedEmail}`}
                          >
                            <Lock size={9} aria-hidden="true" />
                          </span>
                        )}
                        <div className="min-w-0 flex-1">
                          <span
                            className="block truncate text-gray-800 dark:text-gray-200 font-medium text-sm group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors duration-100"
                            title={title}
                          >
                            {title}
                          </span>
                          {userEmail && (
                            <span className="block truncate text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                              {userEmail}
                            </span>
                          )}
                        </div>
                        {assignedNom && (
                          <span
                            className="shrink-0 hidden lg:inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-violet-50 text-violet-600 border border-violet-100 dark:bg-violet-500/10 dark:text-violet-300 dark:border-violet-500/20"
                            title={`Assigné à ${assignedNom}`}
                          >
                            <UserCheck size={9} aria-hidden="true" />
                            {assignedNom}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Date */}
                    <td
                      className="px-5 py-4 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap hidden sm:table-cell"
                      title={formatDateFull(t.created_at)}
                    >
                      {formatDateShort(t.created_at)}
                    </td>

                    {/* Domaine */}
                    {multiDomain && (
                      <td className="px-5 py-4 hidden md:table-cell">
                        <DomaineBadge domaine={t.domaine} />
                      </td>
                    )}

                    {/* Statut */}
                    <td className="px-5 py-4 whitespace-nowrap">
                      <StatusBadge
                        statut={t.statut_ticket as StatutTicket}
                        canonique={t.canonique}
                        closed={closed}
                        processing={processing}
                        reponseSource={reponseSource}
                      />
                    </td>

                    {/* Arrow */}
                    <td className="px-5 py-4 hidden sm:table-cell">
                      <ChevronRight
                        size={14}
                        className="text-gray-300 dark:text-gray-600 group-hover:text-gray-500 dark:group-hover:text-gray-400 group-hover:translate-x-0.5 transition-all duration-150"
                        aria-hidden="true"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* ── Pagination ─────────────────────────────────────────────────── */}
        {!isLoading && total > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.01]">
            <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
              {from}–{to} sur {total} ticket{total > 1 ? "s" : ""}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label="Page précédente"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400 px-2 tabular-nums font-medium">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
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
