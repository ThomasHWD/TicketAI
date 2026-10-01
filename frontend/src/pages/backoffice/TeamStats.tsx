import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Crown, FileText, CheckCircle, ChevronDown, ChevronUp, ChevronsUpDown, RefreshCw } from "lucide-react";
import { useAuth } from "../../lib/auth";
import { getGroupeMembresStats } from "../../lib/api";
import type { MembreStats } from "../../lib/api";

function displayName(m: MembreStats): string {
  if (m.prenom || m.nom) return [m.prenom, m.nom].filter(Boolean).join(" ");
  return m.email;
}

const PERIODE_LABELS: Record<string, string> = {
  semaine: "Cette semaine",
  mois: "Ce mois",
  annee: "Cette année",
};

type SortKey = "nb_reponses_validees" | "nb_documents";
type SortDir = "asc" | "desc";

interface Props {
  periode: string;
}

export default function TeamStatsPanel({ periode }: Props) {
  const { groupesChef } = useAuth();
  const [groupeId, setGroupeId] = useState<string>(groupesChef[0]?.id ?? "");
  const [sortKey, setSortKey] = useState<SortKey>("nb_reponses_validees");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["team-stats", groupeId, periode],
    queryFn: () => getGroupeMembresStats(groupeId, periode),
    enabled: !!groupeId,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  if (!groupeId) {
    return (
      <div className="glass-card rounded-2xl px-5 py-10 text-center text-sm text-muted-foreground">
        Vous n'êtes chef d'aucun groupe.
      </div>
    );
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = data?.membres
    ? [...data.membres].sort((a, b) => {
        const dir = sortDir === "asc" ? 1 : -1;
        return (a[sortKey] - b[sortKey]) * dir;
      })
    : [];

  const currentGroupe = groupesChef.find((g) => g.id === groupeId);
  const periodeLabel = PERIODE_LABELS[periode] ?? periode;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {groupesChef.length > 1 ? (
          <div className="relative w-fit max-w-full">
            <select
              value={groupeId}
              onChange={(e) => setGroupeId(e.target.value)}
              aria-label="Sélectionner un groupe"
              className="appearance-none pl-3 pr-8 py-2 text-sm rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 cursor-pointer max-w-full"
            >
              {groupesChef.map((g) => (
                <option key={g.id} value={g.id}>{g.nom} — {g.domaine}</option>
              ))}
            </select>
            <ChevronDown size={14} aria-hidden="true" className="absolute right-2.5 top-1/2 -translate-y-1/2 text-subtle pointer-events-none" />
          </div>
        ) : currentGroupe && (
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {currentGroupe.nom} <span className="font-normal text-muted-foreground">—</span> {currentGroupe.domaine}
          </p>
        )}
        <span className="text-xs text-muted-foreground shrink-0">{periodeLabel}</span>
      </div>

      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Statistiques des membres de l'équipe</caption>
            <thead>
              <tr className="border-b border-gray-100 dark:border-white/10 text-muted-foreground text-xs uppercase tracking-wide">
                <th scope="col" className="text-left px-5 py-3 font-medium">Membre</th>
                <th
                  scope="col"
                  aria-sort={sortKey === "nb_reponses_validees" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  className="text-right px-5 py-3 font-medium"
                >
                  <button
                    onClick={() => handleSort("nb_reponses_validees")}
                    aria-label={
                      sortKey === "nb_reponses_validees"
                        ? `Trier par Tickets traités, ordre ${sortDir === "asc" ? "croissant" : "décroissant"}`
                        : "Trier par Tickets traités"
                    }
                    className={`inline-flex items-center justify-end gap-1 w-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 rounded ${
                      sortKey === "nb_reponses_validees"
                        ? "text-gray-800 dark:text-gray-100"
                        : "hover:text-gray-700 dark:hover:text-gray-200"
                    }`}
                  >
                    <CheckCircle size={12} aria-hidden="true" />
                    Tickets traités
                    {sortKey === "nb_reponses_validees"
                      ? sortDir === "desc"
                        ? <ChevronDown size={11} aria-hidden="true" />
                        : <ChevronUp size={11} aria-hidden="true" />
                      : <ChevronsUpDown size={11} className="text-subtle" aria-hidden="true" />
                    }
                  </button>
                </th>
                <th
                  scope="col"
                  aria-sort={sortKey === "nb_documents" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  className="text-right px-5 py-3 font-medium"
                >
                  <button
                    onClick={() => handleSort("nb_documents")}
                    aria-label={
                      sortKey === "nb_documents"
                        ? `Trier par Documents ajoutés, ordre ${sortDir === "asc" ? "croissant" : "décroissant"}`
                        : "Trier par Documents ajoutés"
                    }
                    className={`inline-flex items-center justify-end gap-1 w-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1 rounded ${
                      sortKey === "nb_documents"
                        ? "text-gray-800 dark:text-gray-100"
                        : "hover:text-gray-700 dark:hover:text-gray-200"
                    }`}
                  >
                    <FileText size={12} aria-hidden="true" />
                    Documents ajoutés
                    {sortKey === "nb_documents"
                      ? sortDir === "desc"
                        ? <ChevronDown size={11} aria-hidden="true" />
                        : <ChevronUp size={11} aria-hidden="true" />
                      : <ChevronsUpDown size={11} className="text-subtle" aria-hidden="true" />
                    }
                  </button>
                </th>
              </tr>
            </thead>
            <tbody
              className="divide-y divide-gray-100 dark:divide-white/5"
              aria-live="polite"
              aria-busy={isLoading}
            >
              {isLoading && (
                <>
                  <tr className="sr-only">
                    <td colSpan={3}>Chargement des statistiques…</td>
                  </tr>
                  {Array.from({ length: 4 }).map((_, i) => (
                    <tr key={`skeleton-${i}`}>
                      <td className="px-5 py-4">
                        <div className="h-4 w-40 bg-gray-200 dark:bg-white/10 rounded motion-safe:animate-pulse" />
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="h-4 w-8 bg-gray-200 dark:bg-white/10 rounded motion-safe:animate-pulse ml-auto" />
                      </td>
                      <td className="px-5 py-4 text-right">
                        <div className="h-4 w-8 bg-gray-200 dark:bg-white/10 rounded motion-safe:animate-pulse ml-auto" />
                      </td>
                    </tr>
                  ))}
                </>
              )}

              {isError && (
                <tr>
                  <td colSpan={3} className="px-5 py-10 text-center text-sm">
                    <p className="text-red-600 dark:text-red-400 mb-3">Erreur de chargement.</p>
                    <button
                      onClick={() => refetch()}
                      className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-400 underline underline-offset-2 hover:no-underline transition-all duration-150"
                    >
                      <RefreshCw size={13} aria-hidden="true" />
                      Réessayer
                    </button>
                  </td>
                </tr>
              )}

              {!isLoading && !isError && sorted.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.08] motion-safe:transition-colors">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-gray-100">
                        {displayName(m)}
                      </span>
                      {m.is_chef && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-400/15 text-indigo-700 dark:text-indigo-300 text-xs font-medium">
                          <Crown size={11} aria-hidden="true" />
                          Chef
                        </span>
                      )}
                    </div>
                    {(m.prenom || m.nom) && (
                      <p className="text-xs text-muted-foreground mt-0.5">{m.email}</p>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    <span className={`font-semibold ${m.nb_reponses_validees > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground"}`}>
                      {m.nb_reponses_validees}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <span className={`font-semibold ${m.nb_documents > 0 ? "text-blue-600 dark:text-blue-400" : "text-muted-foreground"}`}>
                      {m.nb_documents}
                    </span>
                  </td>
                </tr>
              ))}

              {!isLoading && !isError && data?.membres.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-5 py-10 text-center text-sm text-muted-foreground">
                    Aucun membre dans ce groupe.
                  </td>
                </tr>
              )}
            </tbody>

            {!isLoading && !isError && sorted.length > 0 && (
              <tfoot>
                <tr className="border-t border-gray-100 dark:border-white/10 text-xs text-muted-foreground">
                  <td className="px-5 py-3 font-medium">Total équipe</td>
                  <td className="px-5 py-3 text-right font-semibold text-gray-700 dark:text-gray-300">
                    {data?.membres.reduce((s, m) => s + m.nb_reponses_validees, 0) ?? 0}
                  </td>
                  <td className="px-5 py-3 text-right font-semibold text-gray-700 dark:text-gray-300">
                    {data?.membres.reduce((s, m) => s + m.nb_documents, 0) ?? 0}
                  </td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
