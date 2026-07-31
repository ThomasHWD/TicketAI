import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw, Loader2, RotateCcw, Download,
  FileX, TicketX, Clock, CheckCircle2, Trash2,
} from "lucide-react";
import {
  getIncidents, retryTicket, deleteTicketIncident,
  retryDocument, deleteDocumentIncident,
  downloadDocumentUrl, apiFetch, type TicketIncident, type DocumentIncident,
} from "../../../lib/api";

function IncidentBadge({ label, variant }: { label: string; variant: "red" | "amber" }) {
  const cls =
    variant === "red"
      ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400"
      : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function TicketRow({ ticket }: { ticket: TicketIncident }) {
  const qc = useQueryClient();
  const [retryDone, setRetryDone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin-incidents"] });
    qc.invalidateQueries({ queryKey: ["admin-health"] });
  };

  const retryMutation = useMutation({
    mutationFn: () => retryTicket(ticket.id),
    onSuccess: () => { setRetryDone(true); setTimeout(invalidate, 1000); },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteTicketIncident(ticket.id),
    onSuccess: invalidate,
  });

  const isEchoue = ticket.statut_job === "ÉCHOUÉ";
  const date = new Date(ticket.created_at).toLocaleString("fr-FR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });

  return (
    <tr className="border-b border-gray-100 dark:border-white/8 hover:bg-gray-50/50 dark:hover:bg-white/3 transition-colors">
      <td className="px-4 py-3">
        <IncidentBadge label={isEchoue ? "ÉCHOUÉ" : "BLOQUÉ"} variant={isEchoue ? "red" : "amber"} />
      </td>
      <td className="px-4 py-3">
        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/8 text-gray-600 dark:text-gray-300 font-mono">
          {ticket.domaine}
        </span>
      </td>
      <td className="px-4 py-3 max-w-xs">
        <p className="text-sm text-gray-800 dark:text-gray-200 truncate" title={ticket.question}>{ticket.question}</p>
        {ticket.erreur && (
          <p className="text-xs text-red-500 dark:text-red-400 truncate mt-0.5" title={ticket.erreur}>{ticket.erreur}</p>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-500 dark:text-gray-400 tabular-nums whitespace-nowrap">{date}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          {retryDone ? (
            <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={12} /> Relancé
            </span>
          ) : (
            <button
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
              className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-300 hover:text-emerald-600 dark:hover:text-emerald-400 disabled:opacity-40 transition-colors"
            >
              {retryMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
              Relancer
            </button>
          )}
          {confirmDelete ? (
            <span className="flex items-center gap-1.5">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-40"
              >
                {deleteMutation.isPending ? <Loader2 size={12} className="animate-spin inline" /> : "Confirmer"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              >
                Annuler
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              <Trash2 size={12} /> Supprimer
            </button>
          )}
          {retryMutation.isError && (
            <p className="text-xs text-red-500 w-full">{(retryMutation.error as Error).message}</p>
          )}
        </div>
      </td>
    </tr>
  );
}

function DocumentRow({ doc }: { doc: DocumentIncident }) {
  const qc = useQueryClient();
  const [retryDone, setRetryDone] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const retryMutation = useMutation({
    mutationFn: () => retryDocument(doc.task_id),
    onSuccess: () => {
      setRetryDone(true);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["admin-incidents"] });
        qc.invalidateQueries({ queryKey: ["admin-health"] });
      }, 1000);
    },
    onError: (e: Error) => setRetryError(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocumentIncident(doc.task_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-incidents"] });
      qc.invalidateQueries({ queryKey: ["admin-health"] });
    },
    onError: (e: Error) => setRetryError(e.message),
  });

  const handleDownload = async () => {
    const res = await apiFetch(downloadDocumentUrl(doc.task_id));
    if (!res.ok) { setRetryError("Fichier temporaire introuvable sur le disque."); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = doc.filename ?? "document";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 dark:border-white/8 last:border-0">
      <FileX size={15} className="shrink-0 mt-0.5 text-red-400" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{doc.filename ?? "—"}</span>
          {doc.domaine && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-white/8 text-gray-500 dark:text-gray-400 font-mono">
              {doc.domaine}
            </span>
          )}
        </div>
        {doc.erreur && (
          <p className="text-xs text-red-500 dark:text-red-400 mt-0.5 line-clamp-2" title={doc.erreur}>{doc.erreur}</p>
        )}
        {retryError && <p className="text-xs text-red-500 dark:text-red-400 mt-1">{retryError}</p>}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <button
          onClick={handleDownload}
          className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
        >
          <Download size={12} /> Télécharger
        </button>
        {retryDone ? (
          <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 size={12} /> Relancé
          </span>
        ) : (
          <button
            onClick={() => { setRetryError(null); retryMutation.mutate(); }}
            disabled={retryMutation.isPending}
            className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 disabled:opacity-40 transition-colors"
          >
            {retryMutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
            Relancer
          </button>
        )}
        {confirmDelete ? (
          <span className="flex items-center gap-1.5">
            <button
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
              className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-40"
            >
              {deleteMutation.isPending ? <Loader2 size={12} className="animate-spin inline" /> : "Confirmer"}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              Annuler
            </button>
          </span>
        ) : (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
          >
            <Trash2 size={12} /> Supprimer
          </button>
        )}
      </div>
    </div>
  );
}

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
