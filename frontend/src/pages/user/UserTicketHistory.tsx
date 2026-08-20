import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Inbox, Plus, Search, X } from "lucide-react";
import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { formatDate } from "../../lib/ticketStatus";
import UserStatutBadge from "../../components/ui/UserStatutBadge";
import type { Ticket } from "../../types";

const PAGE_SIZE = 10;

// ─── filtering ───────────────────────────────────────────────────────────────

type Tab = "toutes" | "en_traitement" | "repondues" | "cloturees";

const TABS: { value: Tab; label: string }[] = [
  { value: "toutes",        label: "Toutes" },
  { value: "en_traitement", label: "En traitement" },
  { value: "repondues",     label: "Répondues" },
  { value: "cloturees",     label: "Clôturées" },
];

function matchesTab(t: Ticket, tab: Tab): boolean {
  const closed = !!t.closed_at;
  const processing = t.statut_job === "EN_ATTENTE" || t.statut_job === "EN_COURS";
  switch (tab) {
    case "toutes":        return true;
    case "cloturees":     return closed;
    case "en_traitement": return !closed && (processing || t.statut_ticket === "NOUVEAU" || (t.statut_ticket === "RÉPONDU" && !t.canonique));
    case "repondues":     return !closed && !processing && (t.statut_ticket === "VALIDÉ" || t.canonique);
  }
}

function matchesSearch(t: Ticket, q: string): boolean {
  if (!q) return true;
  return (t.objet ?? t.question).toLowerCase().includes(q.toLowerCase());
}

// ─── sub-components ──────────────────────────────────────────────────────────

function DomainChip({ domaine }: { domaine: string }) {
  return (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 whitespace-nowrap">
      {domaine}
    </span>
  );
}

function SkeletonRow() {
  return (
    <tr className="animate-pulse" aria-hidden="true">
      <td className="px-5 py-4">
        <div className="h-4 rounded-md bg-gray-100 dark:bg-white/5 w-3/4" />
      </td>
      <td className="px-5 py-4">
        <div className="h-5 rounded-full bg-gray-100 dark:bg-white/5 w-16" />
      </td>
      <td className="px-5 py-4">
        <div className="h-4 rounded-md bg-gray-100 dark:bg-white/5 w-28" />
      </td>
      <td className="px-5 py-4">
        <div className="h-5 rounded-full bg-gray-100 dark:bg-white/5 w-24" />
      </td>
    </tr>
  );
}

function EmptyState({
  isFiltered,
  onNew,
  onReset,
}: {
  isFiltered: boolean;
  onNew: () => void;
  onReset: () => void;
}) {
  return (
    <tr>
      <td colSpan={4}>
        <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
          <div className="w-11 h-11 rounded-2xl bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 flex items-center justify-center mb-4 shadow-sm">
            <Inbox size={20} className="text-gray-400 dark:text-gray-500" aria-hidden="true" />
          </div>
          {isFiltered ? (
            <>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Aucun résultat
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
                Aucune question ne correspond à ce filtre.
              </p>
              <button
                onClick={onReset}
                className="text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:underline"
              >
                Effacer les filtres
              </button>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Aucune question pour l'instant
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-5">
                Vos échanges avec le service d'assistance apparaîtront ici.
              </p>
              <button
                onClick={onNew}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors"
              >
                <Plus size={15} aria-hidden="true" />
                Poser ma première question
              </button>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

// ─── main ────────────────────────────────────────────────────────────────────

export default function UserTicketHistory() {
  const navigate = useNavigate();
  const userId = getValidatorId();

  const [activeTab, setActiveTab] = useState<Tab>("toutes");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { setPage(1); }, [activeTab, debouncedSearch]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["mes-tickets", userId],
    queryFn: () => getTickets({ limit: 200, userId }),
    staleTime: 30_000,
  });

  const allTickets: Ticket[] = data?.items ?? [];

  const counts = useMemo<Record<Tab, number>>(() => ({
    toutes:        allTickets.length,
    en_traitement: allTickets.filter((t) => matchesTab(t, "en_traitement")).length,
    repondues:     allTickets.filter((t) => matchesTab(t, "repondues")).length,
    cloturees:     allTickets.filter((t) => matchesTab(t, "cloturees")).length,
  }), [allTickets]);

  const filtered = useMemo(
    () => allTickets.filter((t) => matchesTab(t, activeTab) && matchesSearch(t, debouncedSearch)),
    [allTickets, activeTab, debouncedSearch],
  );

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const from = filtered.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, filtered.length);
  const pageTickets = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const isFiltered = activeTab !== "toutes" || !!debouncedSearch;

  function resetFilters() {
    setActiveTab("toutes");
    setSearch("");
  }

  return (
    <div className="p-6 space-y-5">

      {/* ── Page header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100 tracking-tight">
            Mon historique
          </h1>
          {!isLoading && allTickets.length > 0 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-300 tabular-nums border border-gray-200/60 dark:border-white/[0.08]">
              {allTickets.length}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate("/nouveau-ticket")}
          className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium px-3 py-1.5 rounded-md transition-colors shrink-0"
        >
          <Plus size={14} aria-hidden="true" />
          Nouvelle question
        </button>
      </div>

      {/* ── Toolbar : onglets | recherche ───────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <nav className="flex items-center gap-1 flex-1 min-w-0" aria-label="Filtrer par statut">
          {TABS.map((tab) => {
            const count = counts[tab.value];
            const active = activeTab === tab.value;
            return (
              <button
                key={tab.value}
                onClick={() => setActiveTab(tab.value)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 border-b-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-500 ${
                  active
                    ? "border-emerald-500 text-gray-900 dark:text-gray-100"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:border-gray-300 dark:hover:border-white/20"
                }`}
              >
                {tab.label}
                {count > 0 && (
                  <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold tabular-nums leading-none bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Séparateur */}
        <div className="w-px h-5 bg-gray-200 dark:bg-white/10 shrink-0" aria-hidden="true" />

        {/* Recherche */}
        <div className="relative shrink-0">
          <Search
            size={13}
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
            aria-hidden="true"
          />
          <input
            type="search"
            placeholder="Rechercher…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-7 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-gray-800 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 w-48 transition-shadow"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label="Effacer la recherche"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              <X size={12} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-white/5 bg-gray-50/60 dark:bg-white/[0.02]">
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide w-full">
                  Objet
                </th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                  Domaine
                </th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap">
                  Posée le
                </th>
                <th className="px-5 py-3 text-left text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap">
                  Statut
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-white/[0.04]">
              {isLoading && (
                <>
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                  <SkeletonRow />
                </>
              )}
              {!isLoading && error && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-5 py-10 text-center text-sm text-red-500 dark:text-red-400"
                    role="alert"
                  >
                    {error instanceof Error ? error.message : "Erreur de chargement"}
                  </td>
                </tr>
              )}
              {!isLoading && !error && pageTickets.length === 0 && (
                <EmptyState
                  isFiltered={isFiltered}
                  onNew={() => navigate("/nouveau-ticket")}
                  onReset={resetFilters}
                />
              )}
              {!isLoading &&
                pageTickets.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => navigate(`/historique/${t.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(`/historique/${t.id}`);
                      }
                    }}
                    tabIndex={0}
                    role="link"
                    aria-label={`Voir le détail de : ${t.objet ?? t.question}`}
                    className="group hover:bg-gray-50/80 dark:hover:bg-white/[0.03] transition-colors duration-100 cursor-pointer focus-within:bg-gray-50/80 dark:focus-within:bg-white/[0.03] focus-visible:outline-none"
                  >
                    <td className="px-5 py-4">
                      <span
                        className="block truncate font-medium text-gray-800 dark:text-gray-200 group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors duration-100"
                        title={t.objet ?? t.question}
                      >
                        {t.objet ?? t.question}
                      </span>
                    </td>
                    <td className="px-5 py-4">
                      <DomainChip domaine={t.domaine} />
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap">
                      <span className="text-xs text-gray-400 dark:text-gray-500">
                        {formatDate(t.created_at)}
                      </span>
                    </td>
                    <td className="px-5 py-4 whitespace-nowrap">
                      <UserStatutBadge ticket={t} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* ── Pagination ──────────────────────────────────────────────── */}
        {!isLoading && filtered.length > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 dark:border-white/5 bg-gray-50/40 dark:bg-white/[0.01]">
            <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums" aria-live="polite">
              {from}–{to} sur {filtered.length} question{filtered.length > 1 ? "s" : ""}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                aria-label="Page précédente"
                className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={14} aria-hidden="true" />
              </button>
              <span className="text-xs text-gray-500 dark:text-gray-400 px-2 tabular-nums font-medium">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                aria-label="Page suivante"
                className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 dark:hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
