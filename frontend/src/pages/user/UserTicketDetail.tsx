import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2 } from "lucide-react";
import { getTicket, getReponsesByTicket } from "../../lib/api";
import type { TicketReponse, StatutTicket } from "../../types.ts";

// La réponse n'est « disponible » pour l'utilisateur qu'une fois validée
// (statut_ticket VALIDÉ) ou canonique.
function ticketStatutLabel(statut: StatutTicket, canonique: boolean) {
  if (statut === "REJETÉ") return "Sans réponse";
  if (statut === "VALIDÉ" || canonique) return "Répondu";
  return "En cours de traitement";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean) {
  if (statut === "REJETÉ")
    return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (statut === "VALIDÉ" || canonique)
    return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
}

function StatutBadge({
  statut,
  canonique,
}: {
  statut: StatutTicket;
  canonique: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique)}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique)}
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

/** Une réponse dans le fil, du point de vue de l'utilisateur (lecture seule).
 *  Seules des réponses fiables (validées ou canoniques) sont passées ici. */
function ReponseItem({ reponse }: { reponse: TicketReponse }) {
  return (
    <li className="p-6 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 size={14} aria-hidden="true" /> Réponse validée
        </span>
        <span className="text-xs text-gray-400 shrink-0">
          {formatDate(reponse.created_at)}
        </span>
      </div>
      <div className="bg-gray-50 dark:bg-white/5 rounded-xl p-4">
        <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap">
          {reponse.contenu_corrige ?? reponse.contenu}
        </p>
      </div>
    </li>
  );
}

export default function UserTicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

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
  // On ne transmet à l'utilisateur que les réponses fiables : validées / corrigées
  // ou canoniques. Les réponses provisoires (EN_ATTENTE) restent masquées.
  const reponses = (reponsesQuery.data ?? []).filter(
    (r) => r.statut === "VALIDÉE" || r.statut === "CORRIGÉE" || r.canonique,
  );
  const loading = ticketQuery.isLoading || reponsesQuery.isLoading;
  const error = ticketQuery.error || reponsesQuery.error;

  const BackButton = (
    <button
      onClick={() => navigate(-1)}
      className="group inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-lg text-gray-700 dark:text-gray-200 bg-white/80 dark:bg-white/5 backdrop-blur-xl border border-gray-200/70 dark:border-white/10 shadow-sm shadow-gray-900/5 hover:bg-white hover:text-gray-900 hover:border-gray-300 dark:hover:bg-white/10 dark:hover:text-white transition-colors"
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
      <div className="p-6 text-center text-gray-400" aria-live="polite">
        Chargement…
      </div>
    );

  if (error || !ticket) {
    return (
      <div className="p-6 space-y-4">
        {BackButton}
        <p className="text-red-400" role="alert">
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
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-0.5">
            Ma question
          </p>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100">
            {DOMAINE_LABEL[ticket.domaine] ?? ticket.domaine}
          </h1>
        </div>
        <StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} />
      </div>

      {/* Layout 2 colonnes */}
      <div className="flex gap-5 items-start">
        {/* Colonne principale : question + réponses */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Question */}
          <div className="bg-white/80 dark:bg-white/5 backdrop-blur-xl rounded-2xl border border-gray-200/70 dark:border-white/10 shadow-sm shadow-gray-900/5 p-6">
            <p className="text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wide mb-2">
              Question
            </p>
            <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap">
              {ticket.question}
            </p>
          </div>

          {/* Réponses */}
          <div className="bg-white/80 dark:bg-white/5 backdrop-blur-xl rounded-2xl border border-gray-200/70 dark:border-white/10 shadow-sm shadow-gray-900/5 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-white/10">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                Réponses
              </h2>
            </div>
            {reponses.length === 0 ? (
              <p className="px-6 py-10 text-center text-gray-400 text-sm">
                Votre question est en cours de traitement. La réponse
                s'affichera ici dès qu'elle sera disponible.
              </p>
            ) : (
              <ul
                className="divide-y divide-gray-100 dark:divide-white/10"
                aria-label="Réponses à ma question"
              >
                {reponses.map((r) => (
                  <ReponseItem key={r.id} reponse={r} />
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Colonne latérale : infos */}
        <div className="w-72 shrink-0 space-y-4">
          <div className="bg-white/80 dark:bg-white/5 backdrop-blur-xl rounded-2xl border border-gray-200/70 dark:border-white/10 shadow-sm shadow-gray-900/5 p-5 space-y-4">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              Informations
            </p>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">
                  Domaine
                </dt>
                <dd className="text-gray-700 dark:text-gray-200 font-medium">
                  {DOMAINE_LABEL[ticket.domaine] ?? ticket.domaine}
                </dd>
              </div>
              <div>
                <dt className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">
                  Posée le
                </dt>
                <dd className="text-gray-700 dark:text-gray-200">
                  {formatDate(ticket.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">
                  Statut
                </dt>
                <dd>
                  <StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} />
                </dd>
              </div>
              <div>
                <dt className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">
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
