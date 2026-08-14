import { useQuery } from "@tanstack/react-query";
import { RefreshCw, FileX, TicketX, Clock, CheckCircle2 } from "lucide-react";
import { getIncidents } from "../../../../lib/api";
import TicketRow from "./TicketRow";
import DocumentRow from "./DocumentRow";

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
      <div className="flex items-center justify-between">
        <p className="text-xs text-white/70 drop-shadow">
          {isFetching ? "Actualisation…" : data ? "Données en temps réel" : ""}
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 text-xs text-white/80 hover:text-white transition-colors disabled:opacity-40 drop-shadow"
        >
          <RefreshCw size={12} className={isFetching ? "animate-spin" : ""} />
          Actualiser
        </button>
      </div>

      {isEmpty && (
        <div className="glass-card rounded-2xl px-6 py-16 flex flex-col items-center gap-3 text-center">
          <CheckCircle2 size={32} className="text-emerald-500" />
          <p className="text-sm font-medium text-gray-700 dark:text-gray-200">Aucun incident en cours</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Tous les tickets et documents ont été traités avec succès.
          </p>
        </div>
      )}

      {(isLoading || totalDocs > 0) && (
        <div className="glass-card rounded-2xl px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <FileX size={15} className="text-red-500" />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
              Documents échoués
              {!isLoading && <span className="ml-1.5 text-xs text-gray-400">({totalDocs})</span>}
            </p>
          </div>
          {isLoading ? (
            <div className="space-y-3">
              {[0, 1].map((i) => (
                <div key={i} className="flex items-center gap-3 py-2">
                  <div className="h-3 bg-gray-200 dark:bg-white/10 rounded animate-pulse w-1/3" />
                  <div className="h-3 bg-gray-200 dark:bg-white/10 rounded animate-pulse w-1/4 ml-auto" />
                </div>
              ))}
            </div>
          ) : (
            data!.documents_echoues.map((doc) => <DocumentRow key={doc.task_id} doc={doc} />)
          )}
        </div>
      )}

      {(isLoading || totalTickets > 0) && (
        <div className="glass-card rounded-2xl px-5 py-4">
          <div className="flex items-center gap-2 mb-3">
            <TicketX size={15} className="text-red-500" />
            <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
              Tickets échoués / bloqués
              {!isLoading && <span className="ml-1.5 text-xs text-gray-400">({totalTickets})</span>}
            </p>
          </div>
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 dark:border-white/10">
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-400">Statut</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-400">Domaine</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-400">Question</th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap">
                    <Clock size={11} className="inline mr-1" />Date
                  </th>
                  <th className="px-4 py-2 text-xs font-medium text-gray-500 dark:text-gray-400">Action</th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <>
                    {[0, 1].map((i) => (
                      <tr key={i}>
                        {[0, 1, 2, 3, 4].map((j) => (
                          <td key={j} className="px-4 py-3">
                            <div className="h-3 bg-gray-200 dark:bg-white/10 rounded animate-pulse w-3/4" />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </>
                ) : (
                  allTickets.map((ticket) => <TicketRow key={ticket.id} ticket={ticket} />)
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
