import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Clock, Lock } from "lucide-react";
import {
  getTicket,
  getReponsesByTicket,
  getValidateursByDomaine,
  assignTicket,
  unassignTicket,
} from "../../../lib/api";
import type { MembreGroupe } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import { useAuth } from "../../../lib/auth";
import { useTicketLock } from "../../../hooks/useTicketLock";
import { formatDate, BotAvatar } from "./utils";
import ReponseItem from "./ReponseItem";
import WorkflowModal from "./WorkflowModal";
import TicketSidebar from "./TicketSidebar";

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { isMine, lockedByEmail, isAssigned, checking } = useTicketLock(id);
  const { user: currentUser } = useAuth();
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignLoading, setAssignLoading] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState("");
  const [showWorkflow, setShowWorkflow] = useState(false);

  const ticketQuery = useQuery({
    queryKey: ["ticket", id],
    queryFn: () => getTicket(id!),
    enabled: !!id,
  });

  const reponsesQuery = useQuery({
    queryKey: ["ticket", id, "reponses"],
    queryFn: () => getReponsesByTicket(id!),
    enabled: !!id,
  });

  const ticket = ticketQuery.data;
  const reponses = reponsesQuery.data ?? [];
  const loading = ticketQuery.isLoading || reponsesQuery.isLoading;
  const error = ticketQuery.error || reponsesQuery.error;

  const validateursQuery = useQuery<MembreGroupe[]>({
    queryKey: ["validateurs", ticket?.domaine],
    queryFn: () => getValidateursByDomaine(ticket!.domaine),
    enabled: !!ticket && isMine,
    staleTime: 60_000,
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["ticket", id] });
    queryClient.invalidateQueries({ queryKey: ["tickets"] });
    queryClient.invalidateQueries({ queryKey: ["mes-assignations"] });
  }

  async function handleAssignAction(action: () => Promise<unknown>) {
    setAssignLoading(true); setAssignError(null);
    try {
      await action();
      setSelectedAssignee("");
      refresh();
    } catch (e) {
      setAssignError(e instanceof Error ? e.message : "Erreur");
    } finally {
      setAssignLoading(false);
    }
  }

  const readOnly = !isMine;

  if (loading) {
    return (
      <div className="p-6 text-center text-sm text-gray-400 dark:text-gray-500" aria-live="polite">
        Chargement…
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="p-6 space-y-4">
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-gray-400 dark:text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Retour aux tickets
        </button>
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error instanceof Error ? error.message : "Ticket introuvable"}
        </p>
      </div>
    );
  }

  const userEmail = ticket.user_email;
  const userName = ticket.user_nom_complet || userEmail;

  return (
    <>
      <div className="px-6 py-5 max-w-6xl space-y-5">

        {/* Breadcrumb + Header */}
        <header className="space-y-3">
          <button
            onClick={() => navigate(-1)}
            className="group inline-flex items-center gap-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            aria-label="Retour à la liste des tickets"
          >
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-gray-100 dark:bg-white/10 group-hover:bg-gray-200 dark:group-hover:bg-white/15 transition-colors">
              <ArrowLeft size={13} aria-hidden="true" />
            </span>
            Retour aux tickets
          </button>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50 leading-snug">
            {ticket.objet ?? ticket.question}
          </h1>
        </header>

        {/* Lock banner */}
        {!checking && readOnly && (
          <div
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 dark:bg-amber-400/10 dark:border-amber-400/20 dark:text-amber-300 text-sm"
            role="status"
          >
            <Lock size={14} aria-hidden="true" className="shrink-0" />
            <span>
              {isAssigned ? "Assigné à" : "En cours de traitement par"}{" "}
              <span className="font-medium">{lockedByEmail ?? "un autre validateur"}</span>. Lecture seule.
            </span>
          </div>
        )}

        {/* Two-column body */}
        <div className="flex gap-6 items-start">

          {/* Thread */}
          <div className="flex-1 min-w-0 space-y-3">

            {/* Original question */}
            <article
              className="glass-card rounded-2xl p-5 animate-in fade-in slide-in-from-bottom-1 duration-300"
              aria-label="Question originale"
            >
              <div className="flex gap-3.5 items-start">
                <UserAvatar name={userName ?? "?"} size={36} />
                <div className="flex-1 min-w-0 space-y-2.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                      {userName ?? "Utilisateur"}
                    </span>
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      {formatDate(ticket.created_at)}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-white/10 px-2 py-0.5 rounded-full">
                      Demande
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                    {ticket.question}
                  </p>
                </div>
              </div>
            </article>

            {/* Responses */}
            {reponses.length === 0 ? (
              <article
                className="glass-card rounded-2xl p-5 animate-in fade-in slide-in-from-bottom-1 duration-300"
                aria-label="Réponse en cours"
              >
                <div className="flex gap-3.5 items-start">
                  <BotAvatar pulse />
                  <div className="flex-1 space-y-1">
                    <span className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">TicketAI</span>
                    <div className="flex items-center gap-2 mt-1">
                      <Clock size={13} className="text-blue-400" aria-hidden="true" />
                      <p className="text-sm text-blue-600 dark:text-blue-300">Réponse en cours de génération…</p>
                    </div>
                  </div>
                </div>
              </article>
            ) : (
              <div className="space-y-3" role="feed" aria-label="Fil de réponses">
                {reponses.map((r) => (
                  <ReponseItem
                    key={r.id}
                    reponse={r}
                    readOnly={readOnly}
                    userEmail={userName}
                    onChanged={refresh}
                    onLockConflict={refresh}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Sidebar */}
          <TicketSidebar
            ticket={ticket}
            isMine={isMine}
            assignLoading={assignLoading}
            assignError={assignError}
            selectedAssignee={selectedAssignee}
            currentUserId={currentUser?.id}
            validateurs={validateursQuery.data ?? []}
            onShowWorkflow={() => setShowWorkflow(true)}
            onAssign={() => handleAssignAction(() => assignTicket(ticket.id, selectedAssignee))}
            onUnassign={() => handleAssignAction(() => unassignTicket(ticket.id))}
            onSelectedAssigneeChange={setSelectedAssignee}
          />
        </div>
      </div>

      {showWorkflow && id && (
        <WorkflowModal ticketId={id} onClose={() => setShowWorkflow(false)} />
      )}
    </>
  );
}
