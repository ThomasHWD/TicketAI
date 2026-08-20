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
} from "lucide-react";

import { getTickets } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { useAuth } from "../../lib/auth";
import { isProcessing, statutLabel, formatDate } from "../../lib/ticketStatus";
import type { Ticket, StatutTicket } from "../../types";

// Backend returns these runtime fields; types are incomplete.
type TicketExt = Ticket & { closed_at?: string | null; objet?: string | null };

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
  gray:    { ring: "",                                          bg: "bg-gray-100 dark:bg-white/[0.08]",        icon: "text-gray-500 dark:text-gray-400",    value: "text-gray-800 dark:text-gray-100" },
  emerald: { ring: "ring-1 ring-emerald-300/60 dark:ring-emerald-500/25", bg: "bg-emerald-50 dark:bg-emerald-500/15",    icon: "text-emerald-600 dark:text-emerald-400", value: "text-emerald-700 dark:text-emerald-300" },
  blue:    { ring: "ring-1 ring-blue-200/60 dark:ring-blue-500/20",       bg: "bg-blue-50 dark:bg-blue-500/10",          icon: "text-blue-600 dark:text-blue-400",       value: "text-blue-700 dark:text-blue-300" },
};

function StatCard({
  icon: Icon,
  label,
  value,
  color = "gray",
  activeColor,
}: {
  icon: React.ElementType;
  label: string;
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
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide truncate">
          {label}
        </p>
        <p className={`text-2xl font-semibold mt-0.5 ${theme.value}`}>
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

// ─── Ticket row ──────────────────────────────────────────────────────────────

function TicketRow({
  ticket: t,
  variant,
  onClick,
}: {
  ticket: TicketExt;
  variant: "reply" | "processing";
  onClick: () => void;
}) {
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
        className={`shrink-0 w-2 h-2 rounded-full ${
          variant === "reply"
            ? "bg-emerald-500"
            : "bg-blue-400 animate-pulse"
        }`}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate leading-snug">
          {displayText(t)}
        </p>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          <span className="font-medium">{t.domaine}</span>
          <span className="mx-1.5 opacity-40">·</span>
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

  const { data, isLoading } = useQuery({
    queryKey: ["user-dash", userId],
    queryFn: () => getTickets({ userId, limit: 200 }),
  });

  const tickets = (data?.items ?? []) as TicketExt[];
  const total = data?.total ?? 0;
  const dataLoaded = data !== undefined;
  const isEmpty = dataLoaded && total === 0;

  const aConsulter = tickets.filter((t) => getLabel(t) === "Répondu");
  const enCoursItems = tickets.filter((t) => getLabel(t) === "En cours de traitement");
  const clotures = tickets.filter((t) => !!t.closed_at);

  const greeting = user?.prenom ? `Bonjour, ${user.prenom}` : "Mon espace";

  // ── État 4 — premier passage (aucun ticket) ───────────────────────────────
  if (isEmpty) {
    return (
      <div className="p-6 space-y-8">
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
              Vos questions seront traitées par nos équipes.
              Suivez l'avancement de vos demandes dans votre espace personnel.
            </p>
          </div>
          <button
            onClick={() => navigate("/nouveau-ticket")}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Poser ma première question
          </button>
        </div>
      </div>
    );
  }

  // ── États 1–3 (l'utilisateur a des tickets) ───────────────────────────────

  const hasPendingReplies = aConsulter.length > 0;
  const hasInProgress = enCoursItems.length > 0;

  const sectionTitle =
    hasInProgress && !hasPendingReplies
      ? "En cours de traitement"
      : "Réponses à consulter";

  const sectionItems = hasPendingReplies
    ? aConsulter
    : hasInProgress
      ? enCoursItems
      : [];

  const rowVariant: "reply" | "processing" = hasPendingReplies
    ? "reply"
    : "processing";

  return (
    <div className="p-6 space-y-6">
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
              <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full bg-emerald-500 text-white text-[11px] font-semibold leading-none">
                {aConsulter.length}
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/nouveau-ticket")}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 transition-colors"
            >
              <Plus size={14} />
              Nouvelle question
            </button>
            <span className="w-px h-4 bg-gray-200 dark:bg-white/10" />
            <button
              onClick={() => navigate("/historique")}
              className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              Historique
              <ArrowRight size={13} />
            </button>
          </div>
        </div>

        {/* Panneau */}
        <div className="glass-card rounded-2xl overflow-hidden">
          {isLoading ? (
            <SkeletonRows />
          ) : sectionItems.length > 0 ? (
            // États 1 & 2 — liste de tickets
            <div className="divide-y divide-gray-100 dark:divide-white/5">
              {sectionItems.map((t) => (
                <TicketRow
                  key={t.id}
                  ticket={t}
                  variant={rowVariant}
                  onClick={() => navigate(`/historique/${t.id}`)}
                />
              ))}
            </div>
          ) : (
            // État 3 — tout est à jour
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
                onClick={() => navigate("/nouveau-ticket")}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 dark:border-white/10 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors"
              >
                <Plus size={14} />
                Poser une question
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
