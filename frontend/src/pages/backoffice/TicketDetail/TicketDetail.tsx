import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building2, Clock, History, Lock, MapPin, Phone, User, UserPlus, X } from "lucide-react";
import {
  getTicket,
  getReponsesByTicket,
  getValidateursByDomaine,
  assignTicket,
  unassignTicket,
} from "../../../lib/api";
import type { MembreGroupe } from "../../../lib/api";
import UserAvatar from "../../../components/ui/UserAvatar";
import { useAuth } from "../../../lib/auth";
import { useTicketLock } from "../../../hooks/useTicketLock";
import type { StatutTicket } from "../../../types.ts";
import { formatDate, BotAvatar } from "./utils";
import ReponseItem from "./ReponseItem";
import WorkflowModal from "./WorkflowModal";

function isProcessing(statutJob: string) {
  return statutJob === "EN_ATTENTE" || statutJob === "EN_COURS";
}

function ticketStatutLabel(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean, reponseSource: string | null) {
  if (closed) return "Clôturé";
  if (failed) return "Échec";
  if (processing) return "En cours";
  if (canonique) return "Canonique";
  if (statut === "VALIDÉ") return "Validée";
  if (statut === "RÉPONDU") return reponseSource === "HORS_DOMAINE" ? "Hors domaine" : "Suggestion";
  if (statut === "REJETÉ") return "Rejetée";
  return "Nouvelle";
}

function ticketStatutClass(statut: StatutTicket, canonique: boolean, closed: boolean, processing: boolean, failed: boolean, reponseSource: string | null) {
  if (closed) return "bg-gray-100 text-gray-600 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
  if (failed) return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (processing) return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "REJETÉ") return "bg-red-50 text-red-600 border-red-200 dark:bg-red-500/10 dark:text-red-300 dark:border-red-500/20";
  if (canonique) return "bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-500/20";
  if (statut === "VALIDÉ") return "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/10 dark:text-blue-300 dark:border-blue-500/20";
  if (statut === "RÉPONDU" && reponseSource === "HORS_DOMAINE") return "bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-500/10 dark:text-purple-300 dark:border-purple-500/20";
  if (statut === "RÉPONDU") return "bg-yellow-50 text-yellow-600 border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-300 dark:border-yellow-500/20";
  return "bg-gray-100 text-gray-500 border-gray-200 dark:bg-white/10 dark:text-gray-300 dark:border-white/15";
}

function StatutBadge({ statut, canonique, closed, processing, failed, reponseSource }: { statut: StatutTicket; canonique: boolean; closed: boolean; processing: boolean; failed: boolean; reponseSource: string | null }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${ticketStatutClass(statut, canonique, closed, processing, failed, reponseSource)}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />
      {ticketStatutLabel(statut, canonique, closed, processing, failed, reponseSource)}
    </span>
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
  const [showWorkflow, setShowWorkflow] = useState(false);

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

  return (
    <>
    <div className="p-6 space-y-4 max-w-6xl">
      <button
        onClick={() => navigate(-1)}
        className="group inline-flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full bg-white/60 dark:bg-white/5 backdrop-blur-xl border border-white/60 dark:border-white/10 text-gray-600 dark:text-gray-300 hover:bg-emerald-50/70 hover:text-emerald-700 hover:border-emerald-200/60 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-400 dark:hover:border-emerald-400/20 shadow-sm transition-all duration-200"
        aria-label="Retour à la liste des tickets"
      >
        <ArrowLeft size={16} aria-hidden="true" className="transition-transform group-hover:-translate-x-0.5" />
        Retour aux tickets
      </button>

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

      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-0.5">
            {ticket.domaine}
          </p>
          <h1 className="text-xl font-semibold text-gray-800 dark:text-gray-100">{ticket.objet ?? ticket.question}</h1>
        </div>
      </div>

      <div className="flex gap-5 items-start">

        {/* Fil de conversation */}
        <div className="flex-1 min-w-0 space-y-4">
          <div className="glass-card rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-white/10">
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Échange</h2>
            </div>
            <ul className="divide-y divide-gray-200 dark:divide-white/10" aria-label="Fil de conversation">

              <li className="px-5 py-4 animate-in fade-in slide-in-from-bottom-1 duration-300">
                <div className="flex gap-3 items-start">
                  <UserAvatar name={userName ?? "?"} size={36} />
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
                <dd><StatutBadge statut={ticket.statut_ticket} canonique={ticket.canonique} closed={!!ticket.closed_at} processing={isProcessing(ticket.statut_job)} failed={ticket.statut_job === "ÉCHOUÉ"} reponseSource={ticket.reponse_source ?? null} /></dd>
              </div>
              <div className="pt-1 border-t border-gray-200 dark:border-white/10">
                <dt className="text-gray-500 dark:text-gray-400 text-xs mb-0.5">Référence</dt>
                <dd className="text-gray-500 dark:text-gray-400 font-mono text-xs break-all">{ticket.id}</dd>
              </div>
            </dl>
            <div className="pt-3 border-t border-gray-200 dark:border-white/10">
              <button
                onClick={() => setShowWorkflow(true)}
                className="w-full flex items-center justify-center gap-2 text-xs font-medium px-3 py-2 rounded-xl border border-gray-200 dark:border-white/15 text-gray-600 dark:text-gray-300 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-200 dark:hover:bg-emerald-500/10 dark:hover:text-emerald-400 dark:hover:border-emerald-500/20 transition-colors"
              >
                <History size={13} aria-hidden="true" />
                Voir l'historique
              </button>
            </div>
          </div>

          <div className="glass-card rounded-2xl p-5 space-y-3">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Demandeur</p>
            <div className="flex items-center gap-3">
              <UserAvatar name={userName ?? "?"} size={40} />
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
                  {userName ?? "Utilisateur inconnu"}
                </p>
                {ticket.user_titre && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                    {ticket.user_titre}
                  </p>
                )}
              </div>
            </div>
            <div className="space-y-1.5">
              {ticket.user_email && (
                <a
                  href={`mailto:${ticket.user_email}`}
                  className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate"
                >
                  <User size={11} className="shrink-0" aria-hidden="true" />
                  {ticket.user_email}
                </a>
              )}
              {ticket.user_telephone && (
                <a
                  href={`tel:${ticket.user_telephone}`}
                  className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors"
                >
                  <Phone size={11} className="shrink-0" aria-hidden="true" />
                  {ticket.user_telephone}
                </a>
              )}
              {ticket.user_departement && (
                <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <Building2 size={11} className="shrink-0" aria-hidden="true" />
                  {ticket.user_departement}
                </p>
              )}
              {ticket.user_localisation && (
                <p className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <MapPin size={11} className="shrink-0" aria-hidden="true" />
                  {ticket.user_localisation}
                </p>
              )}
            </div>
          </div>

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
                      <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={32} />
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
                  <UserAvatar name={ticket.assigned_to_nom_complet ?? ticket.assigned_to_email ?? "Validateur"} size={28} />
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

    {showWorkflow && id && (
      <WorkflowModal ticketId={id} onClose={() => setShowWorkflow(false)} />
    )}
    </>
  );
}
