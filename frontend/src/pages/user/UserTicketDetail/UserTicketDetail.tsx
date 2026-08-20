import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { getTicket, getReponsesByTicket, poserSuivi, cloturerTicket } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { getValidatorId } from "../../../lib/currentUser";
import { deriveFilStatut, FilBadge } from "./utils";
import ConversationThread from "./ConversationThread";
import TicketActions from "./TicketActions";
import TicketInfoSidebar from "./TicketInfoSidebar";

function LoadingSkeleton() {
  return (
    <div className="p-6 space-y-5 max-w-5xl animate-pulse" aria-hidden="true">
      <div className="h-4 w-32 rounded-md bg-gray-100 dark:bg-white/5" />
      <div className="space-y-2">
        <div className="h-3 w-20 rounded bg-gray-100 dark:bg-white/5" />
        <div className="h-6 w-2/3 rounded-lg bg-gray-100 dark:bg-white/5" />
      </div>
      <div className="glass-card rounded-2xl h-64" />
    </div>
  );
}

export default function UserTicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [precision, setPrecision] = useState("");
  const [showRating, setShowRating] = useState(false);
  const [noteQualite, setNoteQualite] = useState<number | null>(null);
  const [noteDelai, setNoteDelai] = useState<number | null>(null);
  const [awaitingCount, setAwaitingCount] = useState<number | null>(null);
  const reponsesCountRef = useRef(0);

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

  const suivi = useMutation({
    mutationFn: () =>
      poserSuivi(id!, { question: precision.trim(), user_id: getValidatorId() }),
    onSuccess: () => {
      setPrecision("");
      setAwaitingCount(reponsesCountRef.current);
      queryClient.invalidateQueries({ queryKey: ["ticket", id, "reponses"] });
      queryClient.invalidateQueries({ queryKey: ["ticket", id] });
    },
  });

  const cloture = useMutation({
    mutationFn: (withNotes: boolean) =>
      cloturerTicket(id!, {
        user_id: getValidatorId(),
        ...(withNotes && { note_qualite: noteQualite, note_delai: noteDelai }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", id] });
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
    },
  });

  const ticket = ticketQuery.data;
  const reponses = reponsesQuery.data ?? [];
  const loading = ticketQuery.isLoading || reponsesQuery.isLoading;
  const error = ticketQuery.error || reponsesQuery.error;

  reponsesCountRef.current = reponses.length;

  useEffect(() => {
    if (awaitingCount !== null && reponses.length > awaitingCount) setAwaitingCount(null);
  }, [reponses.length, awaitingCount]);

  const closed = !!ticket?.closed_at;
  const isOwner = !!ticket && ticket.user_id === user?.id;
  const awaiting = awaitingCount !== null;
  const jobEnCours =
    ticket?.statut_job === "EN_ATTENTE" || ticket?.statut_job === "EN_COURS";
  const processing = suivi.isPending || awaiting || jobEnCours;
  const filStatut = deriveFilStatut(closed, reponses, processing);
  const hasVisibleAnswer = reponses.some(
    (r) => r.statut === "VALIDÉE" || r.statut === "CORRIGÉE" || r.canonique,
  );
  const hasPending = reponses.some((r) => r.statut === "EN_ATTENTE");
  const suiviEnCours = processing || hasPending;
  const canSubmitSuivi = precision.trim().length > 0 && !suiviEnCours;

  const BackButton = (
    <button
      onClick={() => navigate("/historique")}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors group"
      aria-label="Retour à mon historique"
    >
      <ArrowLeft
        size={15}
        aria-hidden="true"
        className="transition-transform duration-150 group-hover:-translate-x-0.5"
      />
      Retour à l'historique
    </button>
  );

  if (loading) return <LoadingSkeleton />;

  if (error || !ticket) {
    return (
      <div className="p-6 space-y-4 max-w-5xl">
        {BackButton}
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {error instanceof Error ? error.message : "Question introuvable"}
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5 max-w-5xl">
      {BackButton}

      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-0.5 flex-1 min-w-0">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white leading-snug">
            {ticket.objet ?? ticket.question}
          </h1>
        </div>
        <div className="shrink-0 pt-1">
          <FilBadge statut={filStatut} />
        </div>
      </div>

      {/* Content — conversation left, sidebar right */}
      <div className="flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 min-w-0 space-y-4 w-full">
          <ConversationThread
            question={ticket.question}
            created_at={ticket.created_at}
            reponses={reponses}
          />
          {isOwner && (
            <TicketActions
              closed={closed}
              hasVisibleAnswer={hasVisibleAnswer}
              suiviEnCours={suiviEnCours}
              cloture={cloture}
              showRating={showRating}
              setShowRating={setShowRating}
              noteQualite={noteQualite}
              noteDelai={noteDelai}
              setNoteQualite={setNoteQualite}
              setNoteDelai={setNoteDelai}
              precision={precision}
              setPrecision={setPrecision}
              suivi={{ ...suivi, mutate: () => suivi.mutate() }}
              canSubmitSuivi={canSubmitSuivi}
            />
          )}
        </div>
        <TicketInfoSidebar ticket={ticket} filStatut={filStatut} />
      </div>
    </div>
  );
}
