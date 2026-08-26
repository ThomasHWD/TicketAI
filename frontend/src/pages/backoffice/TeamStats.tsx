import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Crown, FileText, CheckCircle, ChevronDown } from "lucide-react";
import { useAuth } from "../../lib/auth";
import { getGroupeMembresStats } from "../../lib/api";
import type { MembreStats } from "../../lib/api";

function displayName(m: MembreStats): string {
  if (m.prenom || m.nom) return [m.prenom, m.nom].filter(Boolean).join(" ");
  return m.email;
}

interface Props {
  periode: string;
}

export default function TeamStatsPanel({ periode }: Props) {
  const { groupesChef } = useAuth();
  const [groupeId, setGroupeId] = useState<string>(groupesChef[0]?.id ?? "");

  const { data, isLoading } = useQuery({
    queryKey: ["team-stats", groupeId, periode],
    queryFn: () => getGroupeMembresStats(groupeId, periode),
    enabled: !!groupeId,
    staleTime: 60_000,
  });

  return (
    <div className="space-y-4">
      {groupesChef.length > 1 && (
        <div className="relative w-fit">
          <select
            value={groupeId}
            onChange={(e) => setGroupeId(e.target.value)}
            aria-label="Groupe"
            className="appearance-none pl-3 pr-8 py-2 text-sm rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-white/5 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-emerald-400 cursor-pointer"
          >
            {groupesChef.map((g) => (
              <option key={g.id} value={g.id}>{g.nom} — {g.domaine}</option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>
      )}

      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-white/10 text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
              <th className="text-left px-5 py-3 font-medium">Membre</th>
              <th className="text-right px-5 py-3 font-medium">
                <span className="inline-flex items-center justify-end gap-1">
                  <CheckCircle size={12} />
                  Tickets traités
                </span>
              </th>
              <th className="text-right px-5 py-3 font-medium">
                <span className="inline-flex items-center justify-end gap-1">
                  <FileText size={12} />
                  Documents envoyés
                </span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-white/5">
            {isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}>
                  <td className="px-5 py-4">
                    <div className="h-4 w-40 bg-gray-100 dark:bg-white/10 rounded animate-pulse" />
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="h-4 w-8 bg-gray-100 dark:bg-white/10 rounded animate-pulse ml-auto" />
                  </td>
                  <td className="px-5 py-4 text-right">
                    <div className="h-4 w-8 bg-gray-100 dark:bg-white/10 rounded animate-pulse ml-auto" />
                  </td>
                </tr>
              ))}

            {!isLoading && data?.membres.map((m) => (
              <tr key={m.id} className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {displayName(m)}
                    </span>
                    {m.is_chef && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-amber-100 dark:bg-amber-400/15 text-amber-700 dark:text-amber-400 text-xs font-medium">
                        <Crown size={9} />
                        Chef
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{m.email}</p>
                </td>
                <td className="px-5 py-4 text-right">
                  <span className={`font-semibold ${m.nb_reponses_validees > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400"}`}>
                    {m.nb_reponses_validees}
                  </span>
                </td>
                <td className="px-5 py-4 text-right">
                  <span className={`font-semibold ${m.nb_documents > 0 ? "text-blue-600 dark:text-blue-400" : "text-gray-400"}`}>
                    {m.nb_documents}
                  </span>
                </td>
              </tr>
            ))}

            {!isLoading && data?.membres.length === 0 && (
              <tr>
                <td colSpan={3} className="px-5 py-10 text-center text-sm text-gray-400">
                  Aucun membre dans ce groupe.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
