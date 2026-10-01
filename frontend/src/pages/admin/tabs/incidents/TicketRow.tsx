import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, CheckCircle2, Trash2 } from "lucide-react";
import { retryTicket, deleteTicketIncident, type TicketIncident } from "../../../../lib/api";
import IncidentBadge from "./IncidentBadge";

export default function TicketRow({ ticket }: { ticket: TicketIncident }) {
  const qc = useQueryClient();
  const [retryDone, setRetryDone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin-incidents"] });
    qc.invalidateQueries({ queryKey: ["admin-health"] });
  };

  const retryMutation = useMutation({
    mutationFn: () => retryTicket(ticket.id),
    onSuccess: () => {
      setRetryDone(true);
      setTimeout(() => { invalidate(); setRetryDone(false); }, 3000);
    },
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
          <p className="text-xs text-red-600 dark:text-red-400 truncate mt-0.5" title={ticket.erreur}>{ticket.erreur}</p>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground tabular-nums whitespace-nowrap">{date}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          {retryDone ? (
            <span className="flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 size={12} aria-hidden="true" /> Relancé
            </span>
          ) : (
            <button
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
              className="flex items-center gap-1 py-1 text-xs text-gray-600 dark:text-gray-300 hover:text-emerald-800 dark:hover:text-emerald-400 disabled:opacity-40 transition-colors"
            >
              {retryMutation.isPending ? <Loader2 size={12} className="animate-spin" aria-hidden="true" /> : <RotateCcw size={12} aria-hidden="true" />}
              Relancer
            </button>
          )}
          {confirmDelete ? (
            <span className="flex items-center gap-1.5">
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="py-1 text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-40"
              >
                {deleteMutation.isPending ? <Loader2 size={12} className="animate-spin inline" aria-hidden="true" /> : "Confirmer"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="py-1 text-xs text-muted-foreground hover:text-gray-600 dark:hover:text-gray-200"
              >
                Annuler
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1 py-1 text-xs text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              <Trash2 size={12} aria-hidden="true" /> Supprimer
            </button>
          )}
          {retryMutation.isError && (
            <p className="text-xs text-red-600 dark:text-red-400 w-full">
              Échec du relancement — réessayez ou contactez le support si le problème persiste.
            </p>
          )}
        </div>
      </td>
    </tr>
  );
}
