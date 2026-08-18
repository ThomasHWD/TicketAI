import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ClipboardList,
  Clock,
  CheckCircle,
  Archive,
  ArrowRight,
  Plus,
  InboxIcon,
} from "lucide-react";
import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { isProcessing, statutLabel, formatDate } from "../../lib/ticketStatus";
import UserStatutBadge from "../../components/ui/UserStatutBadge";
import type { Ticket, StatutTicket } from "../../types";

function userLabel(t: Ticket) {
  return statutLabel(
    t.statut_ticket as StatutTicket,
    t.canonique,
    !!t.closed_at,
    isProcessing(t.statut_job),
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  colorClass,
  bgClass,
}: {
  icon: React.ElementType;
  label: string;
  value: number | undefined;
  colorClass: string;
  bgClass: string;
}) {
  return (
    <div className="glass-card rounded-2xl p-5 flex items-center gap-4">
      <div className={`shrink-0 p-3 rounded-xl ${bgClass}`}>
        <Icon size={20} className={colorClass} />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
          {label}
        </p>
        <p className="text-2xl font-semibold text-gray-800 dark:text-gray-100 mt-0.5">
          {value === undefined ? (
            <span className="inline-block w-8 h-6 bg-gray-200 dark:bg-white/10 animate-pulse rounded" />
          ) : (
            value
          )}
        </p>
      </div>
    </div>
  );
}

export default function UserDashboard() {
  const navigate = useNavigate();
  const userId = getValidatorId();

  const { data, isLoading } = useQuery({
    queryKey: ["user-dash", userId],
    queryFn: () => getTickets({ userId, limit: 200 }),
  });

  const tickets: Ticket[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const isEmpty = data !== undefined && total === 0;

  const aConsulter = tickets.filter((t) => userLabel(t) === "Répondu");
  const enCoursItems = tickets.filter((t) => userLabel(t) === "En cours de traitement");
  const clotures = tickets.filter((t) => !!t.closed_at);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
          <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
            Votre vue d'ensemble
          </h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={ClipboardList}
          label="Questions posées"
          value={data ? total : undefined}
          colorClass="text-gray-600 dark:text-gray-300"
          bgClass="bg-gray-100 dark:bg-white/10"
        />
        <StatCard
          icon={Clock}
          label="En cours de traitement"
          value={data ? enCoursItems.length : undefined}
          colorClass="text-blue-600 dark:text-blue-300"
          bgClass="bg-blue-500/10 dark:bg-blue-500/10"
        />
        <StatCard
          icon={CheckCircle}
          label="Réponse disponible"
          value={data ? aConsulter.length : undefined}
          colorClass="text-emerald-600 dark:text-emerald-300"
          bgClass="bg-emerald-500/10 dark:bg-emerald-500/10"
        />
        <StatCard
          icon={Archive}
          label="Clôturées"
          value={data ? clotures.length : undefined}
          colorClass="text-gray-500 dark:text-gray-400"
          bgClass="bg-gray-100 dark:bg-white/10"
        />
      </div>

      {/* Empty state */}
      {isEmpty && (
        <div className="glass-card rounded-2xl p-12 flex flex-col items-center gap-4 text-center">
          <div className="p-4 rounded-2xl bg-emerald-500/10">
            <InboxIcon size={32} className="text-emerald-500" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-800 dark:text-gray-100">
              Vous n'avez encore posé aucune question
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Notre assistant IA peut vous aider sur vos sujets RH, IT ou Legal.
            </p>
          </div>
          <button
            onClick={() => navigate("/nouveau-ticket")}
            className="mt-2 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Poser ma première question
          </button>
        </div>
      )}

      {/* Réponses à consulter */}
      {!isEmpty && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
              Réponses à consulter
            </h2>
            <button
              onClick={() => navigate("/historique")}
              className="inline-flex items-center gap-1 text-sm text-emerald-600 dark:text-emerald-400 hover:underline"
            >
              Voir tout l'historique
              <ArrowRight size={14} />
            </button>
          </div>

          <div className="glass-card rounded-2xl overflow-hidden">
            {isLoading ? (
              <div className="px-6 py-10 text-center text-sm text-gray-500 dark:text-gray-400">
                Chargement…
              </div>
            ) : aConsulter.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                      <th className="px-6 py-3 font-medium">Objet</th>
                      <th className="px-6 py-3 font-medium">Domaine</th>
                      <th className="px-6 py-3 font-medium">Répondu le</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-white/5">
                    {aConsulter.map((t) => (
                      <tr
                        key={t.id}
                        className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer"
                        onClick={() => navigate(`/historique/${t.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            navigate(`/historique/${t.id}`);
                          }
                        }}
                        tabIndex={0}
                        role="link"
                        aria-label={`Consulter la réponse : ${t.objet ?? t.question}`}
                      >
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                          <span className="block truncate max-w-xs" title={t.objet ?? t.question}>
                            {t.objet ?? t.question}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                          {t.domaine}
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                          {formatDate(t.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : enCoursItems.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-green-100 dark:bg-emerald-400/10 text-green-700 dark:text-emerald-300 text-left">
                      <th className="px-6 py-3 font-medium">Objet</th>
                      <th className="px-6 py-3 font-medium">Domaine</th>
                      <th className="px-6 py-3 font-medium">Posée le</th>
                      <th className="px-6 py-3 font-medium">Statut</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-white/5">
                    {enCoursItems.map((t) => (
                      <tr
                        key={t.id}
                        className="hover:bg-gray-50 dark:hover:bg-white/5 transition-colors cursor-pointer"
                        onClick={() => navigate(`/historique/${t.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            navigate(`/historique/${t.id}`);
                          }
                        }}
                        tabIndex={0}
                        role="link"
                        aria-label={`Voir : ${t.objet ?? t.question}`}
                      >
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                          <span className="block truncate max-w-xs" title={t.objet ?? t.question}>
                            {t.objet ?? t.question}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-gray-400">
                          {t.domaine}
                        </td>
                        <td className="px-6 py-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                          {formatDate(t.created_at)}
                        </td>
                        <td className="px-6 py-4">
                          <UserStatutBadge ticket={t} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="px-6 py-10 flex flex-col items-center gap-3 text-center">
                <div className="p-3 rounded-xl bg-emerald-500/10">
                  <CheckCircle size={22} className="text-emerald-500" />
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
                    Tout est à jour
                  </p>
                  <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                    Vous n'avez aucune demande en attente. Posez une nouvelle question ?
                  </p>
                </div>
                <button
                  onClick={() => navigate("/nouveau-ticket")}
                  className="mt-1 inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium transition-colors"
                >
                  <Plus size={15} />
                  Poser une question
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
