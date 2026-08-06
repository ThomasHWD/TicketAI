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
    mutationFn: () => poserSuivi(id!, { question: precision.trim(), user_id: getValidatorId() }),
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
      onClick={() => navigate(-1)}
      className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200"
      aria-label="Retour à mon historique"
    >
      <ArrowLeft size={16} aria-hidden="true" className="transition-transform group-hover:-translate-x-0.5" />
      Retour à l'historique
    </button>
  );

  if (loading)
    return (
      <div className="p-6 text-center text-gray-500 dark:text-gray-400" aria-live="polite">
        Chargement…
      </div>
    );

  if (error || !ticket) {
    return (
      <div className="p-6 space-y-4">
        {BackButton}
        <p className="text-red-600 dark:text-red-400" role="alert">
          {error instanceof Error ? error.message : "Question introuvable"}
        </p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      {BackButton}

      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white leading-snug">
            {ticket.objet ?? ticket.question}
          </h1>
        </div>
        <FilBadge statut={filStatut} />
      </div>

      <div className="flex gap-5 items-start">
        <div className="flex-1 min-w-0 space-y-4">
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
