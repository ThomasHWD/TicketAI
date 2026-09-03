import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Plus,
  ClipboardList,
  Clock,
  Bell,
  Archive,
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  ChevronRight,
  AlertCircle,
  RefreshCw,
} from "lucide-react";

import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { useAuth } from "../../lib/auth";
import { isProcessing, statutLabel, formatDate } from "../../lib/ticketStatus";
import type { Ticket, StatutTicket } from "../../types";

// Backend returns these runtime fields; types are incomplete.
type TicketExt = Ticket & { closed_at?: string | null; objet?: string | null };
type RowVariant = "reply" | "processing" | "rejected";

function getLabel(t: TicketExt) {
  return statutLabel(
    t.statut_ticket as StatutTicket,
    t.canonique,
    !!t.closed_at,
    isProcessing(t.statut_job),
  );
}

function displayText(t: TicketExt): string {
  return t.objet ?? t.question;
}

// ─── Stat card ───────────────────────────────────────────────────────────────

type StatColor = "gray" | "emerald" | "blue";

const STAT_COLORS: Record<StatColor, { ring: string; bg: string; icon: string; value: string }> = {
  gray:    { ring: "",                                                    bg: "bg-gray-100 dark:bg-white/[0.08]",     icon: "text-gray-500 dark:text-gray-400",       value: "text-gray-800 dark:text-gray-100" },
  emerald: { ring: "ring-1 ring-emerald-300/60 dark:ring-emerald-500/25", bg: "bg-emerald-50 dark:bg-emerald-500/15", icon: "text-emerald-600 dark:text-emerald-400",  value: "text-emerald-700 dark:text-emerald-300" },
  blue:    { ring: "ring-1 ring-blue-200/60 dark:ring-blue-500/20",       bg: "bg-blue-50 dark:bg-blue-500/10",       icon: "text-blue-600 dark:text-blue-400",        value: "text-blue-700 dark:text-blue-300" },
};

function StatCard({
  icon: Icon,
  label,
  labelTitle,
  subtext,
  value,
  color = "gray",
  activeColor,
}: {
  icon: React.ElementType;
  label: string;
  labelTitle?: string;
  subtext?: string;
  value: number | undefined;
  color?: StatColor;
  activeColor?: StatColor;
}) {
  const resolved: StatColor =
    activeColor && typeof value === "number" && value > 0 ? activeColor : color;
  const theme = STAT_COLORS[resolved];

  return (
    <div className={`glass-card rounded-2xl p-5 flex items-center gap-4 ${theme.ring}`}>
      <div className={`shrink-0 p-3 rounded-xl ${theme.bg}`}>
        <Icon size={20} className={theme.icon} />
      </div>
      <div className="min-w-0">
        <p
          className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-[0.06em] truncate"
          title={labelTitle}
        >
          {label}
        </p>
        <p className={`text-2xl font-semibold mt-0.5 ${theme.value}`}>
          {value === undefined ? (
            <span
              className="inline-block w-8 h-6 bg-gray-200 dark:bg-white/10 animate-pulse rounded"
              aria-label="chargement"
            />
          ) : (
            value
          )}
        </p>
        {subtext && (
          <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5 leading-none">{subtext}</p>
        )}
      </div>
    </div>
  );
}

// ─── Ticket row ──────────────────────────────────────────────────────────────

function TicketRow({
  ticket: t,
  variant,
  onClick,
}: {
  ticket: TicketExt;
  variant: RowVariant;
  onClick: () => void;
}) {
  const dotClass =
    variant === "reply"
      ? "bg-emerald-500"
      : variant === "rejected"
        ? "bg-red-400"
        : "bg-blue-500 motion-safe:animate-pulse";

  const dotTitle =
    variant === "reply"
      ? "Réponse disponible"
      : variant === "rejected"
        ? "Demande rejetée"
        : "En cours de traitement";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Voir le ticket : ${displayText(t)}`}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group flex items-center gap-4 px-6 py-4 hover:bg-gray-50 dark:hover:bg-white/[0.04] transition-colors cursor-pointer select-none"
    >
      <span
        className={`shrink-0 w-2 h-2 rounded-full ${dotClass}`}
        title={dotTitle}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
          {displayText(t)}
        </p>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
          <span className="font-medium">{t.domaine}</span>
          <span className="opacity-40">·</span>
          {formatDate(t.created_at)}
        </p>
      </div>
      <ChevronRight
        size={16}
        className="shrink-0 text-gray-300 dark:text-gray-600 group-hover:text-gray-500 dark:group-hover:text-gray-400 transition-colors"
      />
    </div>
  );
}

// ─── Skeleton rows (loading state) ───────────────────────────────────────────

function SkeletonRows() {
  return (
    <div className="divide-y divide-gray-100 dark:divide-white/5">
      {[58, 72, 44].map((w, i) => (
        <div key={i} className="flex items-center gap-4 px-6 py-4">
          <div className="shrink-0 w-2 h-2 rounded-full bg-gray-200 dark:bg-white/10 animate-pulse" />
          <div className="flex-1 space-y-1.5">
            <div
              className="h-4 bg-gray-100 dark:bg-white/[0.08] rounded animate-pulse"
              style={{ width: `${w}%` }}
            />
            <div className="h-3 w-28 bg-gray-50 dark:bg-white/[0.04] rounded animate-pulse" />
          </div>
          <div className="shrink-0 w-4 h-4 rounded bg-gray-50 dark:bg-white/[0.04] animate-pulse" />
        </div>
      ))}
    </div>
  );
}

// ─── Error panel (panel-level refresh failure) ────────────────────────────────

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
      <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-500/10">
        <AlertCircle size={28} className="text-red-500" />
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Impossible de charger vos tickets
        </p>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Vérifiez votre connexion et réessayez.
          <br />
          <span className="text-xs">Vos questions ne sont pas affectées par cette erreur.</span>
        </p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-gray-100 dark:bg-white/10 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-white/15 transition-colors"
      >
        <RefreshCw size={14} />
        Réessayer
      </button>
    </div>
  );
}

// ─── Panel sub-section label ──────────────────────────────────────────────────

function SubLabel({ children, hasBorderTop = false }: { children: React.ReactNode; hasBorderTop?: boolean }) {
  return (
    <div className={`px-6 py-2 bg-gray-50/70 dark:bg-white/[0.025] ${hasBorderTop ? "border-t border-gray-100 dark:border-white/5" : ""}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {children}
      </p>
    </div>
  );
}

// ─── Shared page header ───────────────────────────────────────────────────────

function PageHeader({ greeting }: { greeting: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-800 dark:text-gray-100">
        {greeting}
      </h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
        Votre espace personnel TicketAI
      </p>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function UserDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = getValidatorId();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["user-dash", userId],
    queryFn: () => getTickets({ userId, limit: 200 }),
    refetchInterval: 30_000,
  });

  // Raccourci clavier N → nouvelle question (hors champs de saisie)
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const active = document.activeElement;
      if (
        e.key === "n" &&
        !e.ctrlKey && !e.metaKey && !e.altKey &&
        active?.tagName !== "INPUT" &&
        active?.tagName !== "TEXTAREA" &&
        !(active as HTMLElement)?.isContentEditable
      ) {
        navigate("/nouveau-ticket");
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [navigate]);

  const tickets = (data?.items ?? []) as TicketExt[];
  const total = data?.total ?? 0;
  const dataLoaded = data !== undefined;
  const isEmpty = dataLoaded && total === 0;

  const aConsulter   = tickets.filter((t) => getLabel(t) === "Répondu");
  const enCoursItems = tickets.filter((t) => getLabel(t) === "En cours de traitement");
  const rejetees     = tickets.filter((t) => getLabel(t) === "Rejetée");
  const clotures     = tickets.filter((t) => !!t.closed_at);

  const greeting = user?.prenom ? `Bonjour, ${user.prenom}` : "Mes demandes";

  // ── Erreur au chargement initial (aucune donnée en cache) ─────────────────
  if (isError && !data) {
    return (
      <main className="p-6 space-y-8">
        <PageHeader greeting={greeting} />
        <div className="glass-card rounded-2xl px-8 py-16 flex flex-col items-center text-center gap-6 max-w-lg mx-auto">
          <div className="p-5 rounded-2xl bg-red-50 dark:bg-red-500/10">
            <AlertCircle size={40} className="text-red-500" strokeWidth={1.5} />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">
              Impossible de charger vos données
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
              Vérifiez votre connexion internet et réessayez.
              <br />
              <span className="text-xs">Vos questions et réponses ne sont pas affectées.</span>
            </p>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-gray-100 dark:bg-white/10 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-white/15 transition-colors"
          >
            <RefreshCw size={16} />
            Réessayer
          </button>
        </div>
      </main>
    );
  }

  // ── État vide — aucune question soumise ───────────────────────────────────
  if (isEmpty) {
    return (
      <main className="p-6 space-y-8">
        <PageHeader greeting={greeting} />

        <div className="glass-card rounded-2xl px-8 py-16 flex flex-col items-center text-center gap-6 max-w-lg mx-auto">
          <div className="p-5 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10">
            <HelpCircle size={40} className="text-emerald-500" strokeWidth={1.5} />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold text-gray-800 dark:text-gray-100">
              Posez votre première question
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs mx-auto leading-relaxed">
              Notre équipe traite votre demande et vous propose une réponse
              dans les meilleurs délais.
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate("/nouveau-ticket")}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Poser une question
          </button>
        </div>
      </main>
    );
  }

  // ── États actifs ──────────────────────────────────────────────────────────

  const hasPendingReplies = aConsulter.length > 0;
  const hasInProgress     = enCoursItems.length > 0;
  const hasRejected       = rejetees.length > 0;
  const hasAnyItems       = hasPendingReplies || hasInProgress || hasRejected;

  const visibleSections = [hasPendingReplies, hasInProgress, hasRejected].filter(Boolean).length;
  const showSubLabels   = visibleSections > 1;

  const sectionTitle =
    hasPendingReplies
      ? "Réponses à consulter"
      : hasInProgress
        ? "En cours de traitement"
        : hasRejected
          ? "Demandes rejetées"
          : "Mes demandes";

  const fetchedCount = tickets.length;
  const hasOverflow  = total > fetchedCount && fetchedCount > 0;

  // Seuil à partir duquel on propose un lien "voir dans l'historique"
  const LIST_THRESHOLD = 5;

  return (
    <main className="p-6 space-y-6">
      {/* En-tête */}
      <PageHeader greeting={greeting} />

      {/* Grille de statistiques */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={ClipboardList}
          label="Questions posées"
          value={data ? total : undefined}
        />
        <StatCard
          icon={Clock}
          label="En cours"
          value={data ? enCoursItems.length : undefined}
          activeColor="blue"
        />
        <StatCard
          icon={Bell}
          label="Réponse disponible"
          value={data ? aConsulter.length : undefined}
          activeColor="emerald"
        />
        <StatCard
          icon={Archive}
          label="Clôturées"
          labelTitle="Tickets traités et archivés par vos experts"
          subtext="traités et archivés"
          value={data ? clotures.length : undefined}
        />
      </div>

      {/* Section principale */}
      <div className="space-y-3">
        {/* En-tête de section */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
              {sectionTitle}
            </h2>
            {hasPendingReplies && (
              <span
                className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-emerald-500 text-white text-[11px] font-semibold leading-none"
                aria-label={`${aConsulter.length} réponse${aConsulter.length > 1 ? "s" : ""} à consulter`}
              >
                <span aria-hidden="true">{aConsulter.length}</span>
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => navigate("/nouveau-ticket")}
              className="inline-flex items-center gap-1.5 py-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors"
            >
              <Plus size={14} />
              Nouvelle question
            </button>
            <span className="w-px h-4 bg-gray-200 dark:bg-white/10" />
            <button
              type="button"
              onClick={() => navigate("/historique")}
              className="inline-flex items-center gap-1 py-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              Historique
              <ArrowRight size={13} />
            </button>
          </div>
        </div>

        {/* Hint contextuel : visible uniquement quand seule la section "en cours" est affichée */}
        {!hasPendingReplies && hasInProgress && !hasRejected && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Votre question est en cours de traitement — la réponse sera disponible
            une fois validée par un expert de votre domaine, généralement sous 24 h.
          </p>
        )}

        {/* Panneau principal */}
        <div
          className="glass-card rounded-2xl overflow-hidden"
          aria-live="polite"
          aria-busy={isLoading}
        >
          {isLoading ? (
            <SkeletonRows />
          ) : isError ? (
            <ErrorPanel onRetry={() => refetch()} />
          ) : !hasAnyItems ? (
            // Tout est à jour
            <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
              <div className="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-500/10">
                <CheckCircle2 size={28} className="text-emerald-500" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  Tout est à jour
                </p>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Vous n'avez aucune demande en attente.
                </p>
              </div>
              <button
                type="button"
                onClick={() => navigate("/nouveau-ticket")}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-gray-200 dark:border-white/10 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                <Plus size={14} />
                Poser une question
              </button>
            </div>
          ) : (
            // Sections actives
            <div className="max-h-[520px] overflow-y-auto">
              {/* Légende des points de statut — toujours visible, accessible touch/SR */}
              <div className="px-6 pt-3 pb-1 flex items-center gap-4" aria-label="Légende des statuts">
                <span className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" role="img" aria-label="Point vert" />
                  Réponse dispo
                </span>
                <span className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" role="img" aria-label="Point bleu" />
                  En cours
                </span>
                <span className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" role="img" aria-label="Point rouge" />
                  Rejetée
                </span>
              </div>

              {/* ① Réponses à consulter */}
              {hasPendingReplies && (
                <>
                  {showSubLabels && (
                    <SubLabel>Réponses à consulter · {aConsulter.length}</SubLabel>
                  )}
                  <div className="divide-y divide-gray-100 dark:divide-white/5">
                    {aConsulter.map((t) => (
                      <TicketRow
                        key={t.id}
                        ticket={t}
                        variant="reply"
                        onClick={() => navigate(`/historique/${t.id}`)}
                      />
                    ))}
                  </div>
                  {aConsulter.length > LIST_THRESHOLD && (
                    <div className="px-6 py-2.5 border-t border-gray-100 dark:border-white/5 text-center">
                      <button
                        type="button"
                        onClick={() => navigate("/historique")}
                        className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors"
                      >
                        Voir les {aConsulter.length} réponses dans l'historique
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* ② En cours de traitement */}
              {hasInProgress && (
                <>
                  {showSubLabels && (
                    <SubLabel hasBorderTop={hasPendingReplies}>
                      En cours · {enCoursItems.length}
                    </SubLabel>
                  )}
                  <div className="divide-y divide-gray-100 dark:divide-white/5">
                    {enCoursItems.map((t) => (
                      <TicketRow
                        key={t.id}
                        ticket={t}
                        variant="processing"
                        onClick={() => navigate(`/historique/${t.id}`)}
                      />
                    ))}
                  </div>
                  {enCoursItems.length > LIST_THRESHOLD && (
                    <div className="px-6 py-2.5 border-t border-gray-100 dark:border-white/5 text-center">
                      <button
                        type="button"
                        onClick={() => navigate("/historique")}
                        className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:underline transition-colors"
                      >
                        Voir les {enCoursItems.length} tickets en cours dans l'historique
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* ③ Demandes rejetées */}
              {hasRejected && (
                <>
                  <SubLabel hasBorderTop={hasPendingReplies || hasInProgress}>
                    Rejetées · {rejetees.length}
                  </SubLabel>
                  <div className="divide-y divide-gray-100 dark:divide-white/5">
                    {rejetees.map((t) => (
                      <TicketRow
                        key={t.id}
                        ticket={t}
                        variant="rejected"
                        onClick={() => navigate(`/historique/${t.id}`)}
                      />
                    ))}
                  </div>
                  {/* Aide contextuelle : que faire d'une demande rejetée */}
                  <div className="px-6 py-3 border-t border-red-100 dark:border-red-500/10 bg-red-50/40 dark:bg-red-500/[0.04] text-center">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Consultez le détail du ticket pour connaître le motif du rejet.{" "}
                      <button
                        type="button"
                        onClick={() => navigate("/nouveau-ticket")}
                        className="text-emerald-600 dark:text-emerald-400 font-medium hover:underline"
                      >
                        Reformuler votre question
                      </button>
                    </p>
                  </div>
                </>
              )}

              {/* Avertissement de troncature (dépassement limit: 200) */}
              {hasOverflow && (
                <div className="px-6 py-3 border-t border-gray-100 dark:border-white/5 text-center">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {total - fetchedCount} question{total - fetchedCount > 1 ? "s" : ""} supplémentaire{total - fetchedCount > 1 ? "s" : ""} —{" "}
                    <button
                      type="button"
                      onClick={() => navigate("/historique")}
                      className="underline hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                    >
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
