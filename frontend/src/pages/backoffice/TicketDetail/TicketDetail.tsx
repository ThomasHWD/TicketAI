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

  if (loading)
    return <div className="p-6 text-center text-gray-500 dark:text-gray-400" aria-live="polite">Chargement…</div>;

  if (error || !ticket) {
    return (
      <div className="p-6">
        <button
          onClick={() => navigate(-1)}
          className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200 mb-4"
        >
          <ArrowLeft size={16} aria-hidden="true" className="transition-transform group-hover:-translate-x-0.5" /> Retour
        </button>
        <p className="text-red-600 dark:text-red-400" role="alert">
          {error instanceof Error ? error.message : "Ticket introuvable"}
        </p>
      </div>
    );
  }

  const userEmail = ticket.user_email;
  const userName = ticket.user_nom_complet || userEmail;

  return (
    <>
    <div className="p-6 space-y-4 max-w-6xl">
      <button
        onClick={() => navigate(-1)}
        className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200"
        aria-label="Retour à la liste des tickets"
      >
        <ArrowLeft size={16} aria-hidden="true" className="transition-transform group-hover:-translate-x-0.5" />
        Retour aux tickets
      </button>

      {!checking && readOnly && (
        <div
          className="flex items-center gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-700 dark:bg-amber-400/10 dark:border-amber-400/20 dark:text-amber-300 text-sm"
          role="status"
        >
          <Lock size={16} aria-hidden="true" />
          <span>
            {isAssigned ? "Ticket assigné à" : "Ticket en cours de traitement par"}{" "}
            <span className="font-medium">{lockedByEmail ?? "un autre validateur"}</span>. Lecture seule.
          </span>
        </div>
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-0.5">
            {ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100">{ticket.objet ?? ticket.question}</h1>
        </div>
      </div>

      <div className="flex gap-5 items-start">

        {/* Fil de conversation */}
        <div className="flex-1 min-w-0 space-y-4">
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Échange</h2>
            </div>
            <ul className="divide-y divide-gray-200 dark:divide-white/10" aria-label="Fil de conversation">

              <li className="px-5 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300">
                <div className="flex gap-3 items-start">
                  <UserAvatar name={userName ?? "?"} size={36} />
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                        {userName ?? "Utilisateur"}
                      </span>
                      <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(ticket.created_at)}</span>
                    </div>
                    <div className="bg-emerald-50 dark:bg-emerald-500/[0.08] border border-emerald-100 dark:border-emerald-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
                      <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                        {ticket.question}
                      </p>
                    </div>
                  </div>
                </div>
              </li>

              {reponses.length === 0 ? (
                <li className="px-5 py-4">
                  <div className="flex gap-3 items-start">
                    <BotAvatar pulse />
                    <div className="flex-1 space-y-1.5">
                      <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">TicketAI</span>
                      <div className="bg-blue-50/60 dark:bg-blue-500/[0.07] border border-blue-100 dark:border-blue-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Clock size={13} className="text-blue-500" aria-hidden="true" />
                          <p className="text-sm text-blue-700 dark:text-blue-300">Réponse en cours de génération…</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </li>
              ) : (
                reponses.map((r) => (
                  <ReponseItem
                    key={r.id}
                    reponse={r}
                    readOnly={readOnly}
                    userEmail={userName}
                    onChanged={refresh}
                    onLockConflict={refresh}
                  />
                ))
              )}
            </ul>
          </div>
        </div>

        {/* Colonne latérale */}
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
