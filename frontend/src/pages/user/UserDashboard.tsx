import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, ClipboardList, Clock, Bell, Archive, ArrowRight, HelpCircle, AlertCircle, RefreshCw } from "lucide-react";
import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { useAuth } from "../../lib/auth";
import { isProcessing, statutLabel } from "../../lib/ticketStatus";
import { UserStatCard } from "../../components/user/dashboard/StatCard";
import { UserTicketRow, SkeletonRows, ErrorPanel, AllUpToDate, SubLabel } from "../../components/user/dashboard/TicketPanel";
import type { Ticket, StatutTicket } from "../../types";

type TicketExt = Ticket & { closed_at?: string | null; objet?: string | null };

function getLabel(t: TicketExt) {
  return statutLabel(t.statut_ticket as StatutTicket, t.canonique, !!t.closed_at, isProcessing(t.statut_job));
}

const LIST_THRESHOLD = 5;

export default function UserDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = getValidatorId();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["user-dash", userId],
    queryFn: () => getTickets({ userId, limit: 200 }),
    refetchInterval: 30_000,
  });

  // Shortcut N → new ticket (outside input fields)
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const active = document.activeElement;
      if (
        e.key === "n" && !e.ctrlKey && !e.metaKey && !e.altKey &&
        active?.tagName !== "INPUT" && active?.tagName !== "TEXTAREA" &&
        !(active as HTMLElement)?.isContentEditable
      ) navigate("/nouveau-ticket");
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [navigate]);

  const tickets = (data?.items ?? []) as TicketExt[];
  const total = data?.total ?? 0;
  const greeting = user?.prenom ? `Bonjour, ${user.prenom}` : "Mes demandes";

  const aConsulter   = tickets.filter((t) => getLabel(t) === "Répondu");
  const enCoursItems = tickets.filter((t) => getLabel(t) === "En cours de traitement");
  const rejetees     = tickets.filter((t) => getLabel(t) === "Rejetée");
  const clotures     = tickets.filter((t) => !!t.closed_at);

  const header = (
    <div>
      <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">{greeting}</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Votre espace personnel</p>
    </div>
  );

  // Full-page error (no cached data)
  if (isError && !data) {
    return (
      <main className="p-6 space-y-8">
        {header}
        <div className="glass-card rounded-2xl px-8 py-16 flex flex-col items-center text-center gap-6 max-w-lg mx-auto">
          <div className="p-5 rounded-2xl bg-red-50 dark:bg-red-500/10">
            <AlertCircle size={40} className="text-red-500" strokeWidth={1.5} />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">Impossible de charger vos données</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
              Vérifiez votre connexion internet et réessayez.<br />
              <span className="text-xs">Vos questions et réponses ne sont pas affectées.</span>
            </p>
          </div>
          <button type="button" onClick={() => refetch()} className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-gray-100 dark:bg-white/10 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-white/15 transition-colors">
            <RefreshCw size={16} /> Réessayer
          </button>
        </div>
      </main>
    );
  }

  // Empty state
  if (data && total === 0) {
    return (
      <main className="p-6 space-y-8">
        {header}
        <div className="glass-card rounded-2xl px-8 py-16 flex flex-col items-center text-center gap-6 max-w-lg mx-auto">
          <div className="p-5 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10">
            <HelpCircle size={40} className="text-emerald-500" strokeWidth={1.5} />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">Posez votre première question</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
              Notre équipe traite votre demande et vous propose une réponse dans les meilleurs délais.
            </p>
          </div>
          <button type="button" onClick={() => navigate("/nouveau-ticket")} className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors">
            <Plus size={16} /> Poser une question
          </button>
        </div>
      </main>
    );
  }

  const hasPendingReplies = aConsulter.length > 0;
  const hasInProgress     = enCoursItems.length > 0;
  const hasRejected       = rejetees.length > 0;
  const hasAnyItems       = hasPendingReplies || hasInProgress || hasRejected;
  const showSubLabels     = [hasPendingReplies, hasInProgress, hasRejected].filter(Boolean).length > 1;
  const hasOverflow       = total > tickets.length && tickets.length > 0;

  const sectionTitle = hasPendingReplies ? "Réponses à consulter"
    : hasInProgress ? "En cours de traitement"
    : hasRejected   ? "Demandes rejetées"
    : "Mes demandes";

  return (
    <main className="p-6 space-y-6">
      {header}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <UserStatCard icon={ClipboardList} label="Questions posées" value={data ? total : undefined} />
        <UserStatCard icon={Clock} label="En cours" value={data ? enCoursItems.length : undefined} activeColor="blue" />
        <UserStatCard icon={Bell} label="Réponse disponible" value={data ? aConsulter.length : undefined} activeColor="emerald" />
        <UserStatCard icon={Archive} label="Clôturées" labelTitle="Tickets traités et archivés par vos experts" subtext="traités et archivés" value={data ? clotures.length : undefined} />
      </div>

      {/* Main section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">{sectionTitle}</h2>
            {hasPendingReplies && (
              <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-emerald-500 text-white text-[11px] font-semibold leading-none" aria-label={`${aConsulter.length} réponse${aConsulter.length > 1 ? "s" : ""} à consulter`}>
                <span aria-hidden="true">{aConsulter.length}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <button type="button" onClick={() => navigate("/nouveau-ticket")} className="inline-flex items-center gap-1.5 py-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors">
              <Plus size={14} /> Nouvelle question
            </button>
            <span className="w-px h-4 bg-gray-200 dark:bg-white/10" />
            <button type="button" onClick={() => navigate("/historique")} className="inline-flex items-center gap-1 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
              Historique <ArrowRight size={13} />
            </button>
          </div>
        </div>

        {!hasPendingReplies && hasInProgress && !hasRejected && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Votre question est en cours de traitement — la réponse sera disponible une fois validée par un expert, généralement sous 24 h.
          </p>
        )}

        <div className="glass-card rounded-2xl overflow-hidden" aria-live="polite" aria-busy={isLoading}>
          {isLoading ? <SkeletonRows />
            : isError  ? <ErrorPanel onRetry={() => refetch()} />
            : !hasAnyItems ? <AllUpToDate />
            : (
              <div className="max-h-[520px] overflow-y-auto">
                {/* Status legend */}
                <div className="px-6 pt-3 pb-1 flex items-center gap-4" aria-label="Légende des statuts">
                  {[
                    { color: "bg-emerald-500", label: "Réponse dispo" },
                    { color: "bg-blue-500",    label: "En cours" },
                    { color: "bg-red-400",     label: "Rejetée" },
                  ].map(({ color, label }) => (
                    <span key={label} className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${color}`} aria-hidden="true" />
                      {label}
                    </span>
                  ))}
                </div>

                {hasPendingReplies && (
                  <>
                    {showSubLabels && <SubLabel>Réponses à consulter · {aConsulter.length}</SubLabel>}
                    <div className="divide-y divide-gray-100 dark:divide-white/5">
                      {aConsulter.map((t) => <UserTicketRow key={t.id} ticket={t} variant="reply" onClick={() => navigate(`/historique/${t.id}`)} />)}
                    </div>
                    {aConsulter.length > LIST_THRESHOLD && (
                      <div className="px-6 py-2.5 border-t border-gray-100 dark:border-white/5 text-center">
                        <button type="button" onClick={() => navigate("/historique")} className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors">
                          Voir les {aConsulter.length} réponses dans l'historique
                        </button>
                      </div>
                    )}
                  </>
                )}

                {hasInProgress && (
                  <>
                    {showSubLabels && <SubLabel hasBorderTop={hasPendingReplies}>En cours · {enCoursItems.length}</SubLabel>}
                    <div className="divide-y divide-gray-100 dark:divide-white/5">
                      {enCoursItems.map((t) => <UserTicketRow key={t.id} ticket={t} variant="processing" onClick={() => navigate(`/historique/${t.id}`)} />)}
                    </div>
                    {enCoursItems.length > LIST_THRESHOLD && (
                      <div className="px-6 py-2.5 border-t border-gray-100 dark:border-white/5 text-center">
                        <button type="button" onClick={() => navigate("/historique")} className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors">
                          Voir les {enCoursItems.length} tickets en cours dans l'historique
                        </button>
                      </div>
                    )}
                  </>
                )}

                {hasRejected && (
                  <>
                    <SubLabel hasBorderTop={hasPendingReplies || hasInProgress}>Rejetées · {rejetees.length}</SubLabel>
                    <div className="divide-y divide-gray-100 dark:divide-white/5">
                      {rejetees.map((t) => <UserTicketRow key={t.id} ticket={t} variant="rejected" onClick={() => navigate(`/historique/${t.id}`)} />)}
                    </div>
                    <div className="px-6 py-3 border-t border-red-100 dark:border-red-500/10 bg-red-50/40 dark:bg-red-500/[0.04] text-center">
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Consultez le détail du ticket pour connaître le motif du rejet.{" "}
                        <button type="button" onClick={() => navigate("/nouveau-ticket")} className="text-emerald-600 dark:text-emerald-400 font-medium hover:underline">
                          Reformuler votre question
                        </button>
                      </p>
                    </div>
                  </>
                )}

                {hasOverflow && (
                  <div className="px-6 py-3 border-t border-gray-100 dark:border-white/5 text-center">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {total - tickets.length} question{total - tickets.length > 1 ? "s" : ""} supplémentaire{total - tickets.length > 1 ? "s" : ""} —{" "}
                      <button type="button" onClick={() => navigate("/historique")} className="underline hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                        voir l'historique complet
                      </button>
                    </p>
                  </div>
                )}
              </div>
            )}
        </div>
      </div>
    </main>
  );
}
