import { Fragment, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  CheckCheck,
  Clock,
  Lock,
  Loader2,
  AlertCircle,
  Send,
  User,
} from "lucide-react";
import {
  getTicket,
  getReponsesByTicket,
  poserSuivi,
  cloturerTicket,
} from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import type { TicketReponse } from "../../types.ts";

// Statut du fil déduit de l'état réel des tours : il rebascule en « en cours »
// dès qu'une précision est en attente de validation, et revient à « Répondu »
// une fois celle-ci validée. Plus fiable que statut_ticket/canonique du ticket,
// qui ne portent que sur un seul tour.
type FilStatut = "closed" | "processing" | "answered" | "rejected";

function deriveFilStatut(
  closed: boolean,
  reponses: TicketReponse[],
  processing: boolean,
): FilStatut {
  if (closed) return "closed";
  // `processing` : précision tout juste envoyée (optimiste, avant que le worker
  // n'ait créé le tour). Une précision déjà en attente de validation prime aussi.
  if (processing || reponses.some((r) => r.statut === "EN_ATTENTE"))
    return "processing";
  if (reponses.some(reponseVisible)) return "answered";
  if (reponses.length > 0 && reponses.every((r) => r.statut === "REJETÉE"))
    return "rejected";
  return "processing";
}

const FIL_STATUT_META: Record<FilStatut, { label: string; className: string }> = {
  closed: {
    label: "Clôturé",
    className:
      "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/10",
  },
  answered: {
    label: "Répondu",
    className:
      "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20",
  },
  processing: {
    label: "En cours de traitement",
    className:
      "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20",
  },
  rejected: {
    label: "Sans réponse",
    className:
      "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20",
  },
};

function FilBadge({ statut }: { statut: FilStatut }) {
  const { label, className } = FIL_STATUT_META[statut];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${className}`}
    >
      {statut === "closed" ? (
        <Lock size={11} aria-hidden="true" />
      ) : (
        <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      )}
      {label}
    </span>
  );
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

const DOMAINE_LABEL: Record<string, string> = {
  IT: "Informatique",
  RH: "Ressources humaines",
  JURIDIQUE: "Juridique",
};

/** Une réponse est visible par l'utilisateur seulement si elle est fiable
 *  (validée / corrigée / canonique). Les réponses provisoires restent masquées. */
function reponseVisible(r: TicketReponse) {
  return r.statut === "VALIDÉE" || r.statut === "CORRIGÉE" || r.canonique;
}

/** Un tour « utilisateur » du fil : la question initiale ou une précision. */
function QuestionBubble({
  text,
  date,
  precision = false,
}: {
  text: string;
  date: string | null;
  precision?: boolean;
}) {
  return (
    <li className="p-6 space-y-3 bg-emerald-50/25 dark:bg-emerald-500/[0.04]">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-700 dark:text-gray-200 uppercase tracking-wide">
          <User size={13} aria-hidden="true" className="text-emerald-600 dark:text-emerald-400" />
          {precision ? "Ma précision" : "Ma question"}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
          {formatDate(date)}
        </span>
      </div>
      <div className="bg-white/80 dark:bg-white/[0.09] rounded-xl p-4 border border-white/60 dark:border-white/10">
        <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
          {text}
        </p>
      </div>
    </li>
  );
}

/** Un tour « réponse » du fil. Le contenu n'apparaît qu'une fois la réponse fiable ;
 *  sinon un état « en cours de traitement » est affiché. */
function AnswerBubble({ reponse }: { reponse: TicketReponse }) {
  if (!reponseVisible(reponse)) return <PendingAnswer date={reponse.created_at} />;
  return (
    <li className="p-6 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-400 uppercase tracking-wide">
          <CheckCircle2 size={13} aria-hidden="true" /> Réponse validée
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
          {formatDate(reponse.created_at)}
        </span>
      </div>
      <div className="bg-white/80 dark:bg-white/[0.09] rounded-xl p-4 border border-white/60 dark:border-white/10">
        <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
          {reponse.contenu_corrige ?? reponse.contenu}
        </p>
      </div>
    </li>
  );
}

function PendingAnswer({ date }: { date: string | null }) {
  return (
    <li className="p-6 space-y-2">
      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 dark:text-blue-400 uppercase tracking-wide">
        <Clock size={13} aria-hidden="true" /> Réponse en cours de traitement
      </span>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        La réponse s'affichera ici dès qu'elle aura été validée.
        {date ? ` · ${formatDate(date)}` : ""}
      </p>
    </li>
  );
}

export default function UserTicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [precision, setPrecision] = useState("");
  // Fenêtre optimiste : entre l'envoi d'une précision et l'apparition du nouveau
  // tour côté serveur, on force l'état « en cours ». On mémorise le nombre de
  // réponses au moment de l'envoi ; dès qu'il augmente, le tour a atterri.
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
    mutationFn: () => cloturerTicket(id!, { user_id: getValidatorId() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ticket", id] });
      queryClient.invalidateQueries({ queryKey: ["mes-tickets"] });
    },
  });

  const ticket = ticketQuery.data;
  // Fil complet, trié par date (le back-end renvoie déjà les réponses par created_at ASC).
  const reponses = reponsesQuery.data ?? [];
  const loading = ticketQuery.isLoading || reponsesQuery.isLoading;
  const error = ticketQuery.error || reponsesQuery.error;

  reponsesCountRef.current = reponses.length;
  // Le tour a atterri dès que le nombre de réponses augmente (précision en
  // attente OU canonique validée d'emblée) → on lève l'état optimiste.
  useEffect(() => {
    if (awaitingCount !== null && reponses.length > awaitingCount) {
      setAwaitingCount(null);
    }
  }, [reponses.length, awaitingCount]);

  const closed = !!ticket?.closed_at;
  const awaiting = awaitingCount !== null;
  // « en cours » si : envoi optimiste, fenêtre d'attente, ou job serveur en vol
  // (précision soumise ailleurs / traitement encore en cours).
  const jobEnCours =
    ticket?.statut_job === "EN_ATTENTE" || ticket?.statut_job === "EN_COURS";
  const processing = suivi.isPending || awaiting || jobEnCours;
  const filStatut = deriveFilStatut(closed, reponses, processing);
  const hasVisibleAnswer = reponses.some(reponseVisible);
  const hasPending = reponses.some((r) => r.statut === "EN_ATTENTE");
  // Tant qu'une précision est en cours (envoi optimiste, job en vol, ou tour en
  // attente de validation), on interdit clôture ET nouvelle précision.
  const suiviEnCours = processing || hasPending;
  const canSubmitSuivi = precision.trim().length > 0 && !suiviEnCours;

  const BackButton = (
    <button
      onClick={() => navigate(-1)}
      className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-700 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200"
      aria-label="Retour à mon historique"
    >
      <ArrowLeft
        size={16}
        aria-hidden="true"
        className="transition-transform group-hover:-translate-x-0.5"
      />{" "}
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

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            {DOMAINE_LABEL[ticket.domaine] ?? ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-white leading-snug">
            {ticket.objet ?? ticket.question}
          </h1>
        </div>
        <FilBadge statut={filStatut} />
      </div>

      {/* Layout 2 colonnes */}
      <div className="flex gap-5 items-start">
        {/* Colonne principale : fil de conversation + actions */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Fil : question initiale → réponse → précision → réponse … */}
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                Échange
              </h2>
            </div>
            <ul
              className="divide-y divide-gray-200 dark:divide-white/10"
              aria-label="Fil de la conversation"
            >
              <QuestionBubble text={ticket.question} date={ticket.created_at} />
              {reponses.length === 0 ? (
                <PendingAnswer date={null} />
              ) : (
                reponses.map((r) => (
                  <Fragment key={r.id}>
                    {r.question_suivi && (
                      <QuestionBubble
                        text={r.question_suivi}
                        date={r.created_at}
                        precision
                      />
                    )}
                    <AnswerBubble reponse={r} />
                  </Fragment>
                ))
              )}
            </ul>
          </div>

          {/* Actions utilisateur : uniquement après une première réponse fiable,
              tant que le ticket n'est pas clôturé. */}
          {closed ? (
            <div className="glass-card rounded-2xl p-6 flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-50 text-emerald-500 dark:bg-emerald-500/10 dark:text-emerald-400 shrink-0">
                <CheckCheck size={18} aria-hidden="true" />
              </span>
              <div>
                <p className="text-sm font-medium text-gray-800 dark:text-gray-100">
                  Demande clôturée
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Vous avez indiqué que cette réponse vous convenait.
                </p>
              </div>
            </div>
          ) : (
            hasVisibleAnswer && (
              <div className="glass-card rounded-2xl p-6 space-y-5">
                {suiviEnCours && (
                  <div className="flex items-center gap-2 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 px-3 py-2 text-xs text-blue-700 dark:text-blue-300">
                    <Clock size={14} aria-hidden="true" />
                    Votre précision est en cours de traitement. Vous pourrez la
                    clôturer ou en poser une nouvelle une fois qu'elle sera traitée.
                  </div>
                )}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    Cette réponse vous convient-elle ?
                  </p>
                  <button
                    type="button"
                    onClick={() => cloture.mutate()}
                    disabled={cloture.isPending || suiviEnCours}
                    className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {cloture.isPending ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <CheckCheck size={16} />
                    )}
                    Oui, clôturer ma demande
                  </button>
                </div>

                {cloture.isError && (
                  <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                    <AlertCircle size={16} />
                    {cloture.error instanceof Error
                      ? cloture.error.message
                      : "Une erreur est survenue"}
                  </div>
                )}

                <div className="border-t border-gray-200 dark:border-white/10 pt-5 space-y-3">
                  <label
                    htmlFor="precision"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-200"
                  >
                    Sinon, apportez une précision
                  </label>
                  <textarea
                    id="precision"
                    value={precision}
                    onChange={(e) => setPrecision(e.target.value)}
                    rows={3}
                    disabled={suiviEnCours}
                    placeholder="Ex. : Et dans le cas d'un contrat à durée déterminée ?"
                    className="w-full text-sm border border-gray-200 dark:border-white/10 rounded-lg px-3 py-2 text-gray-700 dark:text-gray-200 bg-white dark:bg-white/5 placeholder:text-gray-500 dark:placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y disabled:opacity-50 disabled:cursor-not-allowed"
                  />

                  {suivi.isError && (
                    <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
                      <AlertCircle size={16} />
                      {suivi.error instanceof Error
                        ? suivi.error.message
                        : "Une erreur est survenue"}
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => suivi.mutate()}
                    disabled={!canSubmitSuivi}
                    className="inline-flex items-center gap-2 rounded-lg bg-white/60 dark:bg-white/5 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-200 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 text-sm font-medium px-4 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {suivi.isPending ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <Send size={16} />
                    )}
                    Envoyer la précision
                  </button>
                </div>
              </div>
            )
          )}
        </div>

        {/* Colonne latérale : infos */}
        <div className="w-72 shrink-0 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4">
            <p className="text-xs font-semibold text-gray-600 dark:text-gray-300 uppercase tracking-wide">
              Informations
            </p>
            <dl className="space-y-3.5 text-sm">
              <div>
                <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
                  Domaine
                </dt>
                <dd className="text-gray-800 dark:text-gray-100 font-medium">
                  {DOMAINE_LABEL[ticket.domaine] ?? ticket.domaine}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
                  Posée le
                </dt>
                <dd className="text-gray-700 dark:text-gray-200">
                  {formatDate(ticket.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Statut
                </dt>
                <dd>
                  <FilBadge statut={filStatut} />
                </dd>
              </div>
              {closed && (
                <div>
                  <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
                    Clôturée le
                  </dt>
                  <dd className="text-gray-700 dark:text-gray-200">
                    {formatDate(ticket.closed_at)}
                  </dd>
                </div>
              )}
              <div className="pt-1 border-t border-gray-200 dark:border-white/10">
                <dt className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-0.5">
                  Référence
                </dt>
                <dd className="text-gray-500 dark:text-gray-400 font-mono text-xs break-all">
                  {ticket.id}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
