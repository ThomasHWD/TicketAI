import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock } from "lucide-react";
import {
  getTicket,
  getReponsesByTicket,
  getValidateursByDomaine,
  assignTicket,
  unassignTicket,
} from "../../../lib/api";
import type { MembreGroupe } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { useTicketLock } from "../../../hooks/useTicketLock";
import BackofficeThread from "./BackofficeThread";
import WorkflowModal from "./WorkflowModal";
import RerouteModal from "./RerouteModal";
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
  const [showReroute, setShowReroute] = useState(false);

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

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.altKey && e.key === "ArrowLeft" && !showWorkflow) { navigate(-1); return; }
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "v" || e.key === "V") {
        document.querySelector<HTMLButtonElement>('[data-action="valider"]')?.click();
      }
      if (e.key === "e" || e.key === "E") {
        document.querySelector<HTMLButtonElement>('[data-action="corriger"]')?.click();
      }
      if (e.key === "r" || e.key === "R") {
        document.querySelector<HTMLButtonElement>('[data-action="rejeter"]')?.click();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [navigate, showWorkflow]);

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
      setAssignError(e instanceof Error ? e.message : "Erreur lors de l'assignation. Réessayez.");
    } finally {
      setAssignLoading(false);
    }
  }

  const readOnly = !isMine;

  if (loading) {
    return (
      <div className="p-6 text-center text-sm text-gray-500 dark:text-gray-400" aria-live="polite">
        Chargement…
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="p-6 space-y-4">
        <button
          onClick={() => navigate(-1)}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
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
      <main className="px-6 py-5 max-w-6xl space-y-5">

        {/* Breadcrumb + Header */}
        <header className="space-y-3">
          <button
            onClick={() => navigate(-1)}
            className="group inline-flex items-center gap-2 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            aria-label="Retour à la liste des tickets"
            title="Retour aux tickets (Alt + ←)"
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
        <div className="flex flex-col lg:flex-row gap-6 items-start">

          {/* Thread */}
          <div className="flex-1 min-w-0">
            <BackofficeThread
              question={ticket.question}
              created_at={ticket.created_at}
              userName={userName ?? "Utilisateur"}
              domaine={ticket.domaine}
              reponses={reponses}
              readOnly={readOnly}
              reroute_source_domaine={ticket.reroute_source_domaine}
              onChanged={refresh}
              onLockConflict={refresh}
            />
          </div>

          {/* Sidebar */}
          <TicketSidebar
            ticket={ticket}
            isMine={isMine}
            hasSuivi={reponses.some((r) => r.question_suivi != null)}
            assignLoading={assignLoading}
            assignError={assignError}
            selectedAssignee={selectedAssignee}
            currentUserId={currentUser?.id}
            validateurs={validateursQuery.data ?? []}
            validateursLoading={validateursQuery.isLoading}
            onShowWorkflow={() => setShowWorkflow(true)}
            onReroute={() => setShowReroute(true)}
            onAssign={() => handleAssignAction(() => assignTicket(ticket.id, selectedAssignee))}
            onUnassign={() => handleAssignAction(() => unassignTicket(ticket.id))}
            onSelectedAssigneeChange={setSelectedAssignee}
            onClearAssignError={() => setAssignError(null)}
          />
        </div>
      </main>

      {showWorkflow && id && (
        <WorkflowModal ticketId={id} onClose={() => setShowWorkflow(false)} />
      )}
      {showReroute && ticket && (
        <RerouteModal
          ticket={ticket}
          onClose={() => setShowReroute(false)}
          onSuccess={() => { refresh(); navigate(-1); }}
        />
      )}
    </>
  );
}
