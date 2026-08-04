import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bot,
  Check,
  Clock,
  Lock,
  Pencil,
  Sparkles,
  ThumbsUp,
  User,
  UserPlus,
  X,
} from "lucide-react";
import {
  getTicket,
  getReponsesByTicket,
  corrigerReponse,
  validerReponse,
  LockConflictError,
  getValidateursByDomaine,
  assignTicket,
  unassignTicket,
} from "../../lib/api";
import type { MembreGroupe } from "../../lib/api";
import { getValidatorId } from "../../lib/currentUser";
import { useAuth } from "../../lib/auth";
import { useTicketLock } from "../../hooks/useTicketLock";
import type { TicketReponse, StatutTicket, StatutReponse } from "../../types.ts";

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function ticketStatutLabel(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean) {
  if (closed) return "Clôturé";
  if (processing) return "En cours";
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean) {
  if (closed) return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
  if (processing) return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique) return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉ") return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-600 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
}

function StatutBadge({ statut, canonique, closed, processing }: { statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique, closed, processing)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique, closed, processing)}
    </span>
  );
}

function reponseStatutLabel(statut: StatutReponse, canonique: boolean) {
  if (statut === "VALIDÉE" || statut === "CORRIGÉE") return canonique ? "Canonique" : "Validée";
  if (statut === "REJETÉE") return "Rejetée";
  if (statut === "EN_ATTENTE") return "En attente";
  return statut;
}

function reponseStatutClass(statut: StatutReponse, canonique: boolean) {
  if (statut === "REJETÉE") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if ((statut === "VALIDÉE" || statut === "CORRIGÉE") && canonique)
    return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉE" || statut === "CORRIGÉE")
    return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  return "bg-yellow-50 text-yellow-600 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}


const SOURCE_LABEL: Record<string, { label: string; icon: typeof Bot }> = {
  SUGGESTION: { label: "Suggestion", icon: Sparkles },
  CANONIQUE: { label: "Canonique", icon: Bot },
};

/** Avatar pour le demandeur (utilisateur) */
function UserAvatar({ email }: { email: string | null }) {
  const initial = email ? email[0].toUpperCase() : "U";
  return (
    <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0 ring-2 ring-white dark:ring-white/10 text-sm font-semibold">
      {initial}
    </span>
  );
}

/** Avatar IA (réponse en attente ou canonique) */
function BotAvatar({ pulse = false }: { pulse?: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-500 dark:bg-emerald-600 text-white shrink-0 ring-2 ring-white dark:ring-black/40 shadow-md shadow-emerald-600/40${pulse ? " animate-pulse" : ""}`}
      aria-hidden="true"
    >
      <Bot size={16} strokeWidth={1.75} />
    </span>
  );
}

/** Avatar pour un validateur humain */
function ValidatorAvatar({ email }: { email: string | null }) {
  const initial = email ? email[0].toUpperCase() : "V";
  return (
    <span
      className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 shrink-0 ring-2 ring-white dark:ring-white/10 text-sm font-semibold"
      aria-hidden="true"
    >
      {initial}
    </span>
  );
}

function ReponseItem({
  reponse,
  readOnly,
  userEmail,
  onChanged,
  onLockConflict,
}: {
  reponse: TicketReponse;
  readOnly: boolean;
  userEmail: string | null;
  onChanged: () => void;
  onLockConflict: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(reponse.contenu);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canAct = reponse.statut === "EN_ATTENTE" && !readOnly;
  const sourceInfo = SOURCE_LABEL[reponse.source];
  const isPending = reponse.statut === "EN_ATTENTE";
  const isCanonique = reponse.canonique;
  const showBot = isPending || isCanonique;
  const authorLabel = showBot
    ? "TicketAI"
    : (reponse.validator_nom_complet ?? reponse.validator_email ?? "Validateur");
  const authorClass = showBot
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-violet-700 dark:text-violet-300";

  function handleError(e: unknown) {
    if (e instanceof LockConflictError) { onLockConflict(e.message); return; }
    setError(e instanceof Error ? e.message : "Erreur");
  }

  async function handleValider() {
    setLoading(true); setError(null);
    try {
      await validerReponse(reponse.id, { validator_id: getValidatorId() });
      onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  async function handleCorriger() {
    if (!draft.trim() || draft === reponse.contenu) { setEditing(false); return; }
    setLoading(true); setError(null);
    try {
      await corrigerReponse(reponse.id, { contenu_corrige: draft, validator_id: getValidatorId() });
      setEditing(false); onChanged();
    } catch (e) { handleError(e); } finally { setLoading(false); }
  }

  function handleCancel() { setDraft(reponse.contenu); setEditing(false); setError(null); }

  return (
    <li className="px-5 py-4 space-y-3 animate-in fade-in slide-in-from-bottom-1 duration-300">
      {/* Précision de relance */}
      {reponse.question_suivi && (
        <div className="flex gap-3 items-start">
          <UserAvatar email={userEmail} />
          <div className="flex-1 min-w-0 space-y-1.5">
            <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">Précision de l'utilisateur</span>
            <div className="bg-emerald-50 dark:bg-emerald-500/[0.08] border border-emerald-100 dark:border-emerald-500/20 rounded-2xl rounded-tl-sm px-4 py-3">
              <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                {reponse.question_suivi}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Réponse IA ou validateur humain */}
      <div className="flex gap-3 items-start">
        {showBot ? (
          <BotAvatar pulse={isPending} />
        ) : (
          <ValidatorAvatar email={reponse.validator_email ?? null} />
        )}
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-semibold ${authorClass}`}>{authorLabel}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(reponse.created_at)}</span>
            <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${reponseStatutClass(reponse.statut, reponse.canonique)}`}>
              <span className="w-1 h-1 rounded-full bg-current" />
              {reponseStatutLabel(reponse.statut, reponse.canonique)}
            </span>
            {sourceInfo && reponse.source !== "CANONIQUE" && (
              <span className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
                <sourceInfo.icon size={11} aria-hidden="true" />
                {sourceInfo.label}
              </span>
            )}
            {reponse.score_similarite != null && (
              <span className="text-xs text-gray-400 dark:text-gray-500">
                · {(reponse.score_similarite * 100).toFixed(0)} % similarité
              </span>
            )}
          </div>

          {editing ? (
            <div className="space-y-3">
              <textarea
                className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl p-4 focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-y leading-relaxed min-h-[420px]"
                rows={18}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={loading}
                autoFocus
                aria-label="Contenu corrigé"
              />
              {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCorriger}
                  disabled={loading || !draft.trim()}
                  className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                >
                  <Check size={14} aria-hidden="true" /> Valider la correction
                </button>
                <button
                  onClick={handleCancel}
                  disabled={loading}
                  className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 transition-colors"
                >
                  <X size={14} aria-hidden="true" /> Annuler
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-white/90 dark:bg-white/[0.07] border border-gray-200/70 dark:border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <p className="text-sm text-gray-800 dark:text-gray-100 leading-relaxed whitespace-pre-wrap">
                {reponse.contenu_corrige ?? reponse.contenu}
              </p>
            </div>
          )}

          {canAct && !editing && (
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleValider}
                disabled={loading}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
              >
                <ThumbsUp size={14} aria-hidden="true" /> Valider
              </button>
              <button
                onClick={() => setEditing(true)}
                disabled={loading}
                className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
              >
                <Pencil size={14} aria-hidden="true" /> Corriger
              </button>
              {error && <p className="text-xs text-red-600 dark:text-red-400" role="alert">{error}</p>}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

export default function TicketDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { isMine, lockedByEmail, isAssigned, checking } = useTicketLock(id);
  const { user: currentUser } = useAuth();
  const [assignError, setAssignError] = useState<string | null>(null);
  const [assignLoading, setAssignLoading] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState("");

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
  const userInitial = userName ? userName[0].toUpperCase() : "U";
  const assigneeInitial = (ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "V")[0].toUpperCase();

  return (
    <div className="p-6 space-y-4 max-w-6xl">
      <button
        onClick={() => navigate(-1)}
        className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200"
        aria-label="Retour à la liste des tickets"
      >
        <ArrowLeft size={16} aria-hidden="true" className="transition-transform group-hover:-translate-x-0.5" />
        Retour aux tickets
      </button>

      {/* Bandeau lecture seule */}
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

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-0.5">
            {ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100">{ticket.objet ?? ticket.question}</h1>
        </div>
      </div>

      {/* Layout 2 colonnes */}
      <div className="flex gap-5 items-start">

        {/* Colonne principale : fil de conversation */}
        <div className="flex-1 min-w-0 space-y-4">
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Échange</h2>
            </div>
            <ul className="divide-y divide-gray-200 dark:divide-white/10" aria-label="Fil de conversation">

              {/* Question initiale */}
              <li className="px-5 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300">
                <div className="flex gap-3 items-start">
                  <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0 ring-2 ring-white dark:ring-white/10 text-sm font-semibold">
                    {userInitial}
                  </span>
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

              {/* Réponses */}
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
        <div className="w-72 shrink-0 space-y-4">

          {/* Infos ticket */}
          <div className="glass-card rounded-2xl p-5 space-y-4">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Informations</p>
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Domaine</dt>
                <dd className="text-gray-700 dark:text-gray-200 font-medium">{ticket.domaine}</dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Créé le</dt>
                <dd className="text-gray-700 dark:text-gray-200">{formatDate(ticket.created_at)}</dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Statut</dt>
                <dd><StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} closed={!!ticket.closed_at} processing={isProcessing(ticket.statut_job)} /></dd>
              </div>
              <div>
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Traitement</dt>
                <dd className="text-gray-700 dark:text-gray-200">{ticket.statut_job}</dd>
              </div>
              <div className="pt-1 border-t border-gray-200 dark:border-white/10">
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Référence</dt>
                <dd className="text-gray-500 dark:text-gray-400 font-mono text-xs break-all">{ticket.id}</dd>
              </div>
            </dl>
          </div>

          {/* Demandeur */}
          <div className="glass-card rounded-2xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Demandeur</p>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 shrink-0 text-sm font-semibold ring-2 ring-white dark:ring-white/10">
                {userInitial}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                  {userName ?? "Utilisateur inconnu"}
                </p>
                {ticket.user_departement && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                    {ticket.user_departement}
                  </p>
                )}
              </div>
            </div>
            {ticket.user_email && (
              <a
                href={`mailto:${ticket.user_email}`}
                className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate"
              >
                <User size={11} className="shrink-0" aria-hidden="true" />
                {ticket.user_email}
              </a>
            )}
          </div>

          {/* Assignation */}
          {!ticket.closed_at && (
            <div className="glass-card rounded-2xl p-5 space-y-3">
              <div className="flex items-center gap-2">
                <UserPlus size={13} className="text-gray-400 dark:text-gray-500" aria-hidden="true" />
                <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Assignation</p>
              </div>

              {isMine ? (
                ticket.assigned_to ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2.5">
                      <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 shrink-0 text-sm font-semibold ring-2 ring-white dark:ring-white/10">
                        {assigneeInitial}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                          {ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"}
                        </p>
                        {ticket.assigned_to_email && (
                          <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{ticket.assigned_to_email}</p>
                        )}
                      </div>
                    </div>
                    {assignError && <p className="text-xs text-red-600 dark:text-red-400">{assignError}</p>}
                    <button
                      onClick={() => handleAssignAction(() => unassignTicket(ticket.id))}
                      disabled={assignLoading}
                      className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/10 disabled:opacity-40 transition-colors"
                    >
                      <X size={12} aria-hidden="true" /> Remettre dans le pot commun
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <select
                      value={selectedAssignee}
                      onChange={(e) => setSelectedAssignee(e.target.value)}
                      disabled={assignLoading}
                      className="w-full text-sm text-gray-700 dark:text-gray-100 bg-gray-50 dark:bg-white/5 border border-gray-300 dark:border-white/10 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-40"
                    >
                      <option value="">Assigner à…</option>
                      {(validateursQuery.data ?? [])
                        .filter((v) => v.id !== currentUser?.id)
                        .map((v) => (
                          <option key={v.id} value={v.id}>
                            {[v.prenom, v.nom].filter(Boolean).join(" ") || v.email}
                          </option>
                        ))}
                    </select>
                    {assignError && <p className="text-xs text-red-600 dark:text-red-400">{assignError}</p>}
                    <button
                      onClick={() => handleAssignAction(() => assignTicket(ticket.id, selectedAssignee))}
                      disabled={assignLoading || !selectedAssignee}
                      className="w-full flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded-xl bg-emerald-500 text-white hover:bg-emerald-600 disabled:opacity-40 font-medium transition-colors"
                    >
                      <UserPlus size={12} aria-hidden="true" /> Assigner
                    </button>
                  </div>
                )
              ) : ticket.assigned_to ? (
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-violet-100 dark:bg-violet-500/20 text-violet-700 dark:text-violet-300 shrink-0 text-xs font-semibold">
                    {assigneeInitial}
                  </span>
                  <p className="text-sm text-gray-700 dark:text-gray-200 truncate">
                    {ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"}
                  </p>
                </div>
              ) : (
                <p className="text-xs text-gray-400 dark:text-gray-500">Non assigné</p>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
