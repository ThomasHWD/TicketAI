import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileX, RefreshCw, TicketX } from "lucide-react";
import { getIncidents } from "../../../../lib/api";
import DocumentRow from "./DocumentRow";
import TicketRow from "./TicketRow";

export default function IncidentsTab() {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-incidents"],
    queryFn: getIncidents,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const totalTickets = (data?.tickets_echoues.length ?? 0) + (data?.tickets_bloques.length ?? 0);
  const totalDocs = data?.documents_echoues.length ?? 0;
  const allTickets = [...(data?.tickets_echoues ?? []), ...(data?.tickets_bloques ?? [])];
  const isEmpty = !isLoading && totalTickets === 0 && totalDocs === 0;

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400 dark:text-gray-500">
          {isFetching ? "Actualisation…" : data ? "Données en temps réel" : ""}
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors duration-150 disabled:opacity-40"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} aria-hidden="true" />
          Actualiser
        </button>
      </div>

      {/* Empty state */}
      {isEmpty && (
        <div className="glass-card rounded-2xl px-6 py-20 flex flex-col items-center gap-4 text-center">
          <div className="flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10">
            <CheckCircle2 size={22} className="text-emerald-500" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              Aucun incident en cours
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5 max-w-xs mx-auto leading-relaxed">
              Tous les tickets et documents ont été traités avec succès.
            </p>
          </div>
        </div>
      )}

      {/* Documents échoués */}
      {(isLoading || totalDocs > 0) && (
        <div className="glass-card rounded-2xl px-5 py-4">
          <div className="flex items-center gap-2 mb-4">
            <FileX size={14} className="text-red-500" aria-hidden="true" />
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              Documents échoués
            </p>
            {!isLoading && (
              <span className="ml-auto text-xs tabular-nums font-mono text-gray-400 dark:text-gray-500">
                {totalDocs}
              </span>
            )}
          </div>
          {isLoading ? (
            <div className="space-y-3">
              {[0, 1].map((i) => (
                <div key={i} className="flex items-center gap-3 py-2">
                  <div className="h-3 bg-gray-100 dark:bg-white/[0.07] rounded animate-pulse w-1/3" />
                  <div className="h-3 bg-gray-100 dark:bg-white/[0.07] rounded animate-pulse w-1/4 ml-auto" />
                </div>
              ))}
            </div>
          ) : (
            data!.documents_echoues.map((doc) => (
              <DocumentRow key={doc.task_id} doc={doc} />
            ))
          )}
        </div>
      )}

      {/* Tickets échoués / bloqués */}
      {(isLoading || totalTickets > 0) && (
        <div className="glass-card rounded-2xl px-5 py-4">
          <div className="flex items-center gap-2 mb-4">
            <TicketX size={14} className="text-red-500" aria-hidden="true" />
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
              Tickets échoués / bloqués
            </p>
            {!isLoading && (
              <span className="ml-auto text-xs tabular-nums font-mono text-gray-400 dark:text-gray-500">
                {totalTickets}
              </span>
            )}
          </div>
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 dark:border-white/[0.06]">
                  <th className="px-4 py-2 text-xs font-medium text-gray-400 dark:text-gray-500">
                    Statut
                  </th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-400 dark:text-gray-500">
                    Domaine
                  </th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-400 dark:text-gray-500">
                    Question
                  </th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-400 dark:text-gray-500 whitespace-nowrap">
                    Date
                  </th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-400 dark:text-gray-500">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <>
                    {[0, 1].map((i) => (
                      <tr key={i}>
                        {[0, 1, 2, 3, 4].map((j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-3 bg-gray-100 dark:bg-white/[0.07] rounded animate-pulse w-3/4" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </>
                ) : (
                  allTickets.map((ticket) => (
                    <TicketRow key={ticket.id} ticket={ticket} />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
